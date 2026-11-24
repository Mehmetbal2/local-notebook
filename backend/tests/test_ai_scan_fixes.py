"""Tests for the fixes made for GitHub "AI Scan" code scanning alerts, 24 Nov 2026:
tokens die with a password change, web fetches stay on the public internet,
uploads are checked before they are read, zip bombs and huge citation ranges are
refused, and the DOCX export cannot embed local files."""

import asyncio
import io
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parents[1]
for extra in (BACKEND_DIR, BACKEND_DIR / "packages"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))


class TokenRevocationTests(unittest.TestCase):
    def test_password_change_invalidates_old_tokens(self):
        from dependencies.auth import (
            create_access_token,
            decode_token,
            hash_password,
            token_matches_user,
            token_payload_for,
        )

        user = mock.Mock(id="u1", username="ayse", role="user", password_hash=hash_password("eski-parola-1"))
        access = create_access_token(token_payload_for(user))
        refresh = create_access_token(token_payload_for(user), refresh=True)
        self.assertTrue(token_matches_user(decode_token(access), user))
        self.assertTrue(token_matches_user(decode_token(refresh, expected_type="refresh"), user))

        user.password_hash = hash_password("yeni-parola-2")
        self.assertFalse(token_matches_user(decode_token(access), user))
        self.assertFalse(token_matches_user(decode_token(refresh, expected_type="refresh"), user))

    def test_tokens_without_fingerprint_are_rejected(self):
        from dependencies.auth import create_access_token, decode_token, hash_password, token_matches_user

        user = mock.Mock(id="u1", password_hash=hash_password("parola"))
        legacy = create_access_token({"sub": "u1", "username": "ayse", "role": "user"})
        self.assertFalse(token_matches_user(decode_token(legacy), user))


class CitationRangeTests(unittest.TestCase):
    def test_huge_range_is_not_expanded(self):
        from agent.citation_parser import CitationParser

        parser = CitationParser.__new__(CitationParser)
        self.assertEqual(parser._expand_range("1", "3"), ["citation_1", "citation_2", "citation_3"])
        self.assertEqual(parser._expand_range("0", "999999999"), ["citation_0", "citation_999999999"])
        self.assertEqual(parser._expand_range("f_1", "f_999999999"), ["citation_f_1", "citation_f_999999999"])
        self.assertEqual(len(parser._expand_range("1", "200")), 200)


class ZipArchiveLimitTests(unittest.TestCase):
    def test_zip_bomb_is_refused_and_normal_archive_passes(self):
        from workers.parsers import base

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        bomb = os.path.join(tmp, "bomb.epub")
        with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("mimetype", "application/epub+zip")
            archive.writestr("OEBPS/big.xhtml", b"\0" * (3 * 1024 * 1024))
        ok = os.path.join(tmp, "ok.epub")
        with zipfile.ZipFile(ok, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("OEBPS/chapter.xhtml", "<p>Merhaba</p>")

        with mock.patch.object(base, "ARCHIVE_MAX_UNCOMPRESSED_BYTES", 1024 * 1024):
            with self.assertRaises(RuntimeError):
                base.check_zip_archive(bomb)
            base.check_zip_archive(ok)
        plain = os.path.join(tmp, "not-a-zip.doc")
        Path(plain).write_bytes(b"\xd0\xcf\x11\xe0 old Word file")
        base.check_zip_archive(plain)


class PublicDestinationTests(unittest.TestCase):
    def test_non_public_addresses_are_blocked(self):
        from services import searxng_client as sx

        blocked = [
            "http://127.0.0.1:8081/api/admin/users",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.5/",
            "http://192.168.1.1/",
            "http://[::1]/",
            "http://[::ffff:127.0.0.1]/",
            "http://100.64.0.1/",
            "http://0.0.0.0/",
            "http://localhost:6379/",
            "ftp://example.org/file",
            "file:///etc/passwd",
        ]
        for url in blocked:
            with self.subTest(url=url), mock.patch.object(sx, "WEB_FETCH_ALLOW_PRIVATE", False):
                with self.assertRaises(sx.SearxngError) as ctx:
                    asyncio.run(sx.check_public_destination(url))
                self.assertEqual(ctx.exception.code, "blocked")

    def test_public_address_and_opt_in(self):
        from services import searxng_client as sx

        with mock.patch.object(sx, "WEB_FETCH_ALLOW_PRIVATE", False):
            asyncio.run(sx.check_public_destination("https://93.184.215.14/page"))
        with mock.patch.object(sx, "WEB_FETCH_ALLOW_PRIVATE", True):
            asyncio.run(sx.check_public_destination("http://192.168.1.10/intranet"))

    def test_redirect_to_private_address_is_blocked(self):
        import httpx

        from services import searxng_client as sx

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "93.184.215.14":
                return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})
            return httpx.Response(200, text="secret")

        async def run():
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                follow_redirects=True,
                event_hooks={"request": [sx._check_request_destination]},
            ) as client:
                await client.get("http://93.184.215.14/redirect")

        with mock.patch.object(sx, "WEB_FETCH_ALLOW_PRIVATE", False):
            with self.assertRaises(sx.SearxngError) as ctx:
                asyncio.run(run())
        self.assertEqual(ctx.exception.code, "blocked")


class UploadGuardTests(unittest.TestCase):
    def _app(self):
        from fastapi import FastAPI, UploadFile

        from utils.upload_guard import UploadGuardMiddleware

        app = FastAPI()

        @app.post("/api/up")
        async def up(file: UploadFile):
            return {"n": len(await file.read())}

        @app.post("/api/admin/restore")
        async def restore(file: UploadFile):
            return {"n": len(await file.read())}

        app.add_middleware(UploadGuardMiddleware, max_bytes=1024 * 1024)
        return app

    def test_auth_and_size_are_checked_before_the_body(self):
        import httpx

        from dependencies.auth import create_access_token

        headers = {"Authorization": "Bearer " + create_access_token({"sub": "u1"})}
        big = b"x" * (2 * 1024 * 1024)

        async def streamed():
            yield b'--b\r\nContent-Disposition: form-data; name="file"; filename="a.txt"\r\n\r\n'
            for _ in range(40):
                yield b"y" * 65536

        async def run():
            transport = httpx.ASGITransport(app=self._app())
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return [
                    (await client.post("/api/up", files={"file": ("a.txt", b"x")})).status_code,
                    (await client.post("/api/up", files={"file": ("a.txt", b"x")},
                                       headers={"Authorization": "Bearer nope"})).status_code,
                    (await client.post("/api/up", files={"file": ("a.txt", b"x" * 10)}, headers=headers)).status_code,
                    (await client.post("/api/up", files={"file": ("a.txt", big)}, headers=headers)).status_code,
                    (await client.post("/api/up", content=streamed(), headers={
                        **headers, "Content-Type": "multipart/form-data; boundary=b"})).status_code,
                    (await client.post("/api/admin/restore", files={"file": ("a.zip", big)}, headers=headers)).status_code,
                    (await client.post("/api/up", json={"a": 1})).status_code,
                ]

        self.assertEqual(asyncio.run(run()), [401, 401, 200, 413, 413, 200, 422])


@unittest.skipUnless(shutil.which("pandoc"), "pandoc is not installed")
class DocxExportLocalFileTests(unittest.TestCase):
    def test_markdown_images_do_not_embed_local_files(self):
        from services.export_service import ExportService

        secret_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, secret_dir)
        secret = os.path.join(secret_dir, "secret.png")
        with open(secret, "wb") as handle:
            handle.write(b"\x89PNG\r\n\x1a\nSECRET-BYTES")

        stream = ExportService()._convert_markdown_to_docx_with_pandoc(
            f"# Rapor\n\n![gizli]({secret})\n\nMetin ![x](file://{secret}).\n"
        )
        archive = zipfile.ZipFile(io.BytesIO(stream.getvalue()))
        self.assertEqual([name for name in archive.namelist() if "media" in name], [])
        self.assertFalse(any(b"SECRET-BYTES" in archive.read(name) for name in archive.namelist()))
        self.assertIn("Metin", archive.read("word/document.xml").decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
