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


class MediaTokenTests(unittest.TestCase):
    def test_media_token_is_not_an_access_token(self):
        from fastapi import HTTPException

        from dependencies.auth import create_media_token, decode_token, hash_password, token_matches_user

        user = mock.Mock(id="u1", password_hash=hash_password("parola"))
        media = create_media_token(user)
        payload = decode_token(media, expected_type="media")
        self.assertTrue(token_matches_user(payload, user))
        with self.assertRaises(HTTPException):
            decode_token(media, expected_type="access")

    def test_query_string_accepts_only_media_tokens(self):
        from fastapi import HTTPException

        from dependencies import auth

        user = mock.Mock(id="u1", username="ayse", role="user", password_hash=auth.hash_password("parola"))
        db = mock.Mock()
        db.get = mock.AsyncMock(return_value=user)
        access = auth.create_access_token(auth.token_payload_for(user))
        media = auth.create_media_token(user)

        async def resolve(header, query):
            return await auth.get_current_user_query_or_header(header_token=header, query_token=query, db=db)

        self.assertIs(asyncio.run(resolve(None, media)), user)
        self.assertIs(asyncio.run(resolve(access, None)), user)
        with self.assertRaises(HTTPException):
            asyncio.run(resolve(None, access))
        with self.assertRaises(HTTPException):
            asyncio.run(resolve(media, None))


class SecretKeyTests(unittest.TestCase):
    def test_placeholders_and_short_keys_are_not_used(self):
        from dependencies import auth

        for value in ("please-change-this-in-production", "change-me-in-production", "short-key", ""):
            self.assertFalse(auth._is_usable_secret_key(value), value)
        self.assertTrue(auth._is_usable_secret_key("k" * 40))


class LoginThrottleTests(unittest.TestCase):
    def test_failures_lock_the_pair_then_expire(self):
        from utils.login_throttle import LoginThrottle

        now = [1000.0]
        throttle = LoginThrottle(max_failures=3, max_per_address=5, window=60, clock=lambda: now[0])
        for _ in range(3):
            self.assertEqual(throttle.retry_after("1.2.3.4", "ayse"), 0)
            throttle.record_failure("1.2.3.4", "ayse")
        self.assertGreater(throttle.retry_after("1.2.3.4", "Ayse"), 0)
        self.assertEqual(throttle.retry_after("5.6.7.8", "ayse"), 0)
        self.assertEqual(throttle.retry_after("1.2.3.4", "mehmet"), 0)
        throttle.record_failure("1.2.3.4", "mehmet")
        throttle.record_failure("1.2.3.4", "ali")
        self.assertGreater(throttle.retry_after("1.2.3.4", "zeynep"), 0)  # per-address limit
        now[0] += 61
        self.assertEqual(throttle.retry_after("1.2.3.4", "ayse"), 0)

    def test_success_clears_the_pair(self):
        from utils.login_throttle import LoginThrottle

        throttle = LoginThrottle(max_failures=2, max_per_address=10, window=60)
        throttle.record_failure("a", "u")
        throttle.record_success("a", "u")
        throttle.record_failure("a", "u")
        self.assertEqual(throttle.retry_after("a", "u"), 0)


class LoginRaceTests(unittest.TestCase):
    def test_simultaneous_attempts_cannot_exceed_the_limit(self):
        from utils.login_throttle import LoginThrottle

        throttle = LoginThrottle(max_failures=5, max_per_address=50, window=60)
        allowed = [throttle.begin_attempt("1.2.3.4", "admin") for _ in range(30)]
        self.assertEqual(sum(1 for wait, _ in allowed if wait == 0), 5)

    def test_success_does_not_count_against_the_address(self):
        from utils.login_throttle import LoginThrottle

        throttle = LoginThrottle(max_failures=3, max_per_address=3, window=60)
        for user in ("a", "b", "c", "d", "e"):
            wait, stamp = throttle.begin_attempt("10.0.0.1", user)
            self.assertEqual(wait, 0)
            throttle.record_success("10.0.0.1", user, stamp)


class LoginPerUserTests(unittest.TestCase):
    def test_spoofed_addresses_do_not_bypass_the_per_user_limit(self):
        from utils.login_throttle import LoginThrottle

        throttle = LoginThrottle(max_failures=3, max_per_address=50, window=60, max_per_user=10)
        allowed = sum(1 for i in range(100) if throttle.begin_attempt(f"10.0.{i}.1", "admin")[0] == 0)
        self.assertEqual(allowed, 10)
        self.assertEqual(throttle.begin_attempt("10.9.9.9", "ayse")[0], 0)


class SegmentBlockLookupTests(unittest.TestCase):
    def test_many_blocks_are_matched_quickly_and_correctly(self):
        import time

        from services.segment_service import segment_service

        blocks = [{"pos_start": i * 351, "pos_end": i * 351 + 350, "block_id": f"b{i}"} for i in range(60000)]
        start = time.perf_counter()
        for pos in range(0, 60000 * 351, 351):
            segment_service._find_block_ids(blocks, pos, pos + 400)
        self.assertLess(time.perf_counter() - start, 3.0)
        self.assertEqual(segment_service._find_block_ids(blocks, 340, 360), ["b0", "b1"])
        shuffled = list(reversed(blocks[:5]))
        self.assertEqual(segment_service._find_block_ids(shuffled, 340, 360), ["b1", "b0"])


class DocxTableLimitTests(unittest.TestCase):
    def test_huge_table_is_written_as_text(self):
        import docx

        from services.export_service import ExportService

        document = docx.Document()
        lines = ["|" + "|".join(["x"] * 5000) + "|"] + ["|a|"] * 2000
        ExportService()._add_markdown_table(document, lines, lambda *args: None)
        self.assertEqual(len(document.tables), 0)
        small = docx.Document()
        ExportService()._add_markdown_table(small, ["|a|b|", "|---|---|", "|1|2|"], lambda *args: None)
        self.assertEqual(len(small.tables), 1)


class DataFolderPermissionTests(unittest.TestCase):
    def test_existing_world_readable_folder_is_closed(self):
        import paths

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        folder = tmp / "data"
        folder.mkdir(mode=0o755)
        folder.chmod(0o755)
        paths._restrict_once(folder)
        self.assertEqual(folder.stat().st_mode & 0o777, 0o700)


class FourthRoundTests(unittest.TestCase):
    def test_tag_stripping_is_linear(self):
        import re
        import time

        start = time.perf_counter()
        re.sub(r"<[^<>]+>", "", "<" * 200000)
        self.assertLess(time.perf_counter() - start, 1.0)
        source = open(os.path.join(BACKEND_DIR, "services", "export_service.py"), encoding="utf-8").read()
        self.assertNotIn("re.sub(r'<[^>]+>', '', text)", source)

    def test_epub_ids_pointing_to_one_file_are_read_once(self):
        from workers.parsers.epub_parser import EpubParser

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        path = os.path.join(tmp, "alias.epub")
        container = (
            '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
            '</rootfiles></container>'
        )
        manifest = "".join(f'<item id="c{i}" href="c1.xhtml" media-type="application/xhtml+xml"/>' for i in range(300))
        spine = "".join(f'<itemref idref="c{i}"/>' for i in range(300))
        opf = (
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">x</dc:identifier>'
            '<dc:title>T</dc:title><dc:language>tr</dc:language></metadata>'
            f'<manifest>{manifest}</manifest><spine>{spine}</spine></package>'
        )
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip")
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("OEBPS/content.opf", opf)
            archive.writestr("OEBPS/c1.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Tek bölüm metni.</p></body></html>')
        try:
            result = EpubParser()._parse_sync(path)
        except ImportError:
            self.skipTest("ebooklib is not installed")
        self.assertEqual(len([b for b in result.blocks if "Tek bölüm" in (b.content or "")]), 1)

    def test_long_user_names_do_not_grow_throttle_keys(self):
        from utils.login_throttle import LoginThrottle

        throttle = LoginThrottle(max_failures=3, max_per_address=50, window=60, max_per_user=10)
        throttle.begin_attempt("1.2.3.4", "x" * 1_000_000)
        self.assertTrue(all(len(key) < 200 for key in throttle._failures))

    def test_overlong_login_is_refused_without_touching_the_throttle(self):
        import httpx
        from fastapi import FastAPI

        from routes import auth_routes
        from utils.login_throttle import login_throttle

        app = FastAPI()
        app.include_router(auth_routes.router, prefix="/api")
        before = len(login_throttle._failures)

        async def run():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.post("/api/auth/login", data={"username": "a" * 5000, "password": "x"})

        response = asyncio.run(run())
        self.assertEqual(response.status_code, 401)
        self.assertEqual(len(login_throttle._failures), before)


class FifthRoundTests(unittest.TestCase):
    def test_inline_markdown_regex_is_linear_on_unclosed_brackets(self):
        import time

        from services.export_service import ExportService

        regex = ExportService._INLINE_TOKEN_RE
        for payload in ("[" * 50000, "[a" * 25000, "[^" * 25000, "[x](" * 12000):
            start = time.perf_counter()
            list(regex.finditer(payload))
            self.assertLess(time.perf_counter() - start, 0.5, payload[:4])
        tokens = [m.group(0) for m in regex.finditer("Bkz. [kaynak](https://ex.org/a) ve [^1] **kalın**")]
        self.assertEqual(tokens, ["[kaynak](https://ex.org/a)", "[^1]", "**kalın**"])

    def test_oversized_pdf_image_is_not_decoded(self):
        from workers.parsers.pymupdf_parser import PyMuPDFParser

        doc = mock.Mock()
        doc.xref_get_key.side_effect = lambda xref, key: ("int", "100000" if key == "Width" else "100000")
        self.assertFalse(PyMuPDFParser._image_size_ok(doc, 5, {"width": 100000, "height": 100000}))
        doc.xref_get_key.side_effect = lambda xref, key: ("int", "1200" if key == "Width" else "800")
        self.assertTrue(PyMuPDFParser._image_size_ok(doc, 5, {"width": 1200, "height": 800}))

    def test_docker_stack_does_not_publish_redis_or_milvus(self):
        import re

        text = open(os.path.join(BACKEND_DIR, "..", "docker-compose.yml"), encoding="utf-8").read()
        services = dict(re.findall(r"^  ([a-z][\w-]*):\n((?:(?:    .*|\s*)\n)*)", text, re.M))
        for name in ("redis", "milvus"):
            block = "\n".join(line for line in services[name].splitlines() if not line.strip().startswith("#"))
            self.assertNotIn("ports:", block, name)
        self.assertIn("ports:", services["backend"])


class HtmlTableScanTests(unittest.TestCase):
    def test_unclosed_tables_are_linear(self):
        import time

        from services.segment_service import _html_table_spans

        start = time.perf_counter()
        self.assertEqual(_html_table_spans("<table>" * 200000), [])
        self.assertLess(time.perf_counter() - start, 1.0)
        text = "a<TABLE border=1><tr><td>x</td></tr></table>b<table>c</table>"
        self.assertEqual([text[s:e] for s, e in _html_table_spans(text)],
                         ["<TABLE border=1><tr><td>x</td></tr></table>", "<table>c</table>"])


class HtmlImageLimitTests(unittest.TestCase):
    def test_repeated_local_image_is_copied_once_and_count_is_capped(self):
        from workers.parsers.html_parser import HtmlParser

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        Path(tmp, "big.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 4096)
        html = "<html><body>" + "".join(f'<p>p{i}</p><img src="big.png" alt="r{i}">' for i in range(400)) + "</body></html>"
        doc = Path(tmp, "doc.html")
        doc.write_text(html, encoding="utf-8")
        try:
            result = HtmlParser()._parse_sync(str(doc), "file-1")
        except RuntimeError as exc:
            self.skipTest(str(exc))
        self.assertLessEqual(len(result.images), HtmlParser.MAX_IMAGES)
        written = list(Path(tmp, "images", "file-1").glob("*"))
        self.assertEqual(len(written), 1)


class PdfImageLimitTests(unittest.TestCase):
    def test_image_reused_on_many_pages_is_written_once(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("PyMuPDF is not installed")
        from workers.parsers.pymupdf_parser import PyMuPDFParser

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 300, 300), False)
        pix.set_rect(pix.irect, (200, 50, 50))
        pix.save(str(tmp / "i.png"))
        doc = pymupdf.open()
        xref = None
        for i in range(40):
            page = doc.new_page()
            page.insert_text((72, 72), f"Sayfa {i}")
            rect = pymupdf.Rect(72, 100, 372, 400)
            if xref is None:
                xref = page.insert_image(rect, filename=str(tmp / "i.png"))
            else:
                page.insert_image(rect, xref=xref)
        doc.save(str(tmp / "d.pdf"))
        result = PyMuPDFParser(image_dir=tmp / "imgs").parse(str(tmp / "d.pdf"))
        self.assertEqual(len(result.images), 40)
        self.assertEqual(len(list((tmp / "imgs").glob("*.png"))), 1)


class EpubSpineTests(unittest.TestCase):
    def test_repeated_spine_entries_are_read_once(self):
        from workers.parsers.epub_parser import EpubParser

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        path = os.path.join(tmp, "repeat.epub")
        container = (
            '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
            '</rootfiles></container>'
        )
        spine = "".join('<itemref idref="c1"/>' for _ in range(500))
        opf = (
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">x</dc:identifier>'
            '<dc:title>T</dc:title><dc:language>tr</dc:language></metadata>'
            '<manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/></manifest>'
            f'<spine>{spine}</spine></package>'
        )
        chapter = '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Tek bölüm metni.</p></body></html>'
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip")
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("OEBPS/content.opf", opf)
            archive.writestr("OEBPS/c1.xhtml", chapter)
        try:
            result = EpubParser()._parse_sync(path)
        except ImportError:
            self.skipTest("ebooklib is not installed")
        texts = [block.content for block in result.blocks if "Tek bölüm" in (block.content or "")]
        self.assertEqual(len(texts), 1)


class ServiceUrlTests(unittest.TestCase):
    def test_only_plain_http_addresses_are_accepted(self):
        from utils.service_url import InvalidServiceURL, checked_service_url

        for good in ("http://127.0.0.1:8001", "https://api.openai.com/v1", " http://192.168.1.20:11434/v1 "):
            self.assertEqual(checked_service_url(good), good.strip())
        for bad in ("file:///etc/passwd", "gopher://x", "http://", "localhost:8001", "http://user:pass@host/",
                    "http://host:99999/", "javascript:alert(1)", ""):
            with self.subTest(bad=bad), self.assertRaises(InvalidServiceURL):
                checked_service_url(bad)


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


class PinnedConnectionTests(unittest.TestCase):
    def test_connection_goes_to_the_checked_address(self):
        import socket

        import httpx

        from services import searxng_client as sx

        seen = []

        def handler(request):
            seen.append((str(request.url), request.headers.get("host"), request.extensions.get("sni_hostname")))
            return httpx.Response(200, text="ok")

        answers = iter([
            [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 443))],
            [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
        ])

        async def fake_getaddrinfo(host, port, type=0):
            return next(answers)

        async def run():
            loop = asyncio.get_running_loop()
            with mock.patch.object(loop, "getaddrinfo", side_effect=fake_getaddrinfo), \
                    mock.patch.object(sx, "WEB_FETCH_ALLOW_PRIVATE", False):
                async with httpx.AsyncClient(transport=sx._PublicOnlyTransport(httpx.MockTransport(handler))) as client:
                    response = await client.get("https://rebind.example/page")
                    self.assertEqual(str(response.url), "https://rebind.example/page")
                    # The same name now answers with a loopback address: refused.
                    with self.assertRaises(sx.SearxngError):
                        await client.get("https://rebind.example/again")

        asyncio.run(run())
        self.assertEqual(seen, [("https://93.184.215.14/page", "rebind.example", "rebind.example")])


class UploadGuardTests(unittest.TestCase):
    def _app(self):
        from fastapi import Body, FastAPI, UploadFile

        from utils.upload_guard import UploadGuardMiddleware

        users = {"user-token": mock.Mock(is_admin=False), "admin-token": mock.Mock(is_admin=True)}

        async def authenticate(token):
            return users.get(token)

        app = FastAPI()

        @app.post("/api/up")
        async def up(file: UploadFile):
            return {"n": len(await file.read())}

        @app.post("/api/admin/restore")
        async def restore(file: UploadFile):
            return {"n": len(await file.read())}

        @app.post("/api/json")
        async def take_json(payload: dict = Body(...)):
            return {"keys": len(payload)}

        app.add_middleware(
            UploadGuardMiddleware,
            max_upload_bytes=1024 * 1024,
            max_request_bytes=256 * 1024,
            authenticate=authenticate,
        )
        return app

    def test_auth_and_size_are_checked_before_the_body(self):
        import httpx

        user = {"Authorization": "Bearer user-token"}
        admin = {"Authorization": "Bearer admin-token"}
        big = b"x" * (2 * 1024 * 1024)

        async def streamed():
            yield b'--b\r\nContent-Disposition: form-data; name="file"; filename="a.txt"\r\n\r\n'
            for _ in range(40):
                yield b"y" * 65536

        async def streamed_json():
            yield b'{"a": "'
            for _ in range(10):
                yield b"z" * 65536

        async def run():
            transport = httpx.ASGITransport(app=self._app())
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                post = client.post
                return [
                    (await post("/api/up", files={"file": ("a.txt", b"x")})).status_code,
                    (await post("/api/up", files={"file": ("a.txt", b"x")},
                                headers={"Authorization": "Bearer revoked"})).status_code,
                    (await post("/api/up", files={"file": ("a.txt", b"x" * 10)}, headers=user)).status_code,
                    (await post("/api/up", files={"file": ("a.txt", big)}, headers=user)).status_code,
                    (await post("/api/up", content=streamed(), headers={
                        **user, "Content-Type": "multipart/form-data; boundary=b"})).status_code,
                    (await post("/api/admin/restore", files={"file": ("a.zip", big)}, headers=user)).status_code,
                    (await post("/api/admin/restore", files={"file": ("a.zip", big)}, headers=admin)).status_code,
                    (await post("/api/json", json={"a": 1})).status_code,
                    (await post("/api/json", json={"a": "z" * (512 * 1024)})).status_code,
                    (await post("/api/json", content=streamed_json(),
                                headers={"Content-Type": "application/json"})).status_code,
                ]

        self.assertEqual(asyncio.run(run()), [401, 401, 200, 413, 413, 403, 200, 200, 413, 413])


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


class SixthRoundTests(unittest.TestCase):
    """AI Scan alerts #82-#86 (25 Nov 2026)."""

    def test_long_paragraph_split_keeps_former_cuts(self):
        from workers.parsers.text_split import split_long_text

        # Expected cuts recorded with the former (re-slicing) splitter.
        cases = {
            "Birinci cümle burada biter. İkinci cümle biraz daha uzun ve virgülsüz devam eder! Üçüncü? Evet.":
                ["Birinci cümle burada biter.", "İkinci cümle biraz daha uzun ve", "virgülsüz devam eder! Üçüncü? Evet."],
            "Ortalama 3.57 ve p = .05 değeri tablo 2'de verildi; ayrıntı için ekteki hesaba bakın lütfen.":
                ["Ortalama 3.57 ve p = .05 değeri tablo", "2'de verildi; ayrıntı için ekteki", "hesaba bakın lütfen."],
            "Formül $a^2 + b^2 = c^2$ satır içinde kalmalı ve bölünmemeli diye uzun bir açıklama ekliyoruz.":
                ["Formül $a^2 + b^2 = c^2$ satır içinde", "kalmalı ve bölünmemeli diye uzun bir", "açıklama ekliyoruz."],
            "a" * 102: ["a" * 40, "a" * 40, "a" * 22],
            "kısa   boşluklar     arasında    kelimeler   var    ve     bölme    sonrası  boşluk  atlanmalı   hep":
                ["kısa   boşluklar     arasında", "kelimeler   var    ve     bölme", "sonrası  boşluk  atlanmalı   hep"],
        }
        for text, expected in cases.items():
            self.assertEqual(split_long_text(text, 40, "。！？!?؛;؟۔.:"), expected)

    def test_one_huge_paragraph_splits_in_linear_time(self):
        import time

        from workers.parsers import html_parser, txt_parser

        text = "abc " * 750_000  # 3 MB, no sentence punctuation
        for module in (txt_parser, html_parser):
            start = time.perf_counter()
            chunks = module._split_long_paragraph(text)
            self.assertLess(time.perf_counter() - start, 5, module.__name__)
            self.assertEqual("".join(c.replace(" ", "") for c in chunks), text.replace(" ", ""))

    def test_unclosed_table_and_break_tags_are_linear(self):
        import time

        from services.segment_service import _TABLE_OPEN_RE, _html_table_spans
        from workers.parsers.html_parser import HtmlParser

        start = time.perf_counter()
        self.assertEqual(_html_table_spans("<table " * 60000 + "x"), [])
        self.assertIsNone(_TABLE_OPEN_RE.search("<table " * 60000))
        self.assertLess(time.perf_counter() - start, 1)
        self.assertEqual(_html_table_spans('a <table class="t"><tr><td>1</td></tr></table> b'), [(2, 46)])

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        path = tmp / "b.html"
        path.write_text("<html><body><p>Merhaba</p>" + "<br " * 60000 + "</body></html>", encoding="utf-8")
        start = time.perf_counter()
        asyncio.run(HtmlParser().parse(str(path)))
        self.assertLess(time.perf_counter() - start, 5)

    # ---------- PDF ----------

    def _pymupdf(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("PyMuPDF is not installed")
        return pymupdf

    def _doc_with_content(self, content: bytes):
        pymupdf = self._pymupdf()
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Merhaba")
        doc.update_stream(page.get_contents()[0], content)
        return pymupdf.open(stream=doc.tobytes(deflate=True), filetype="pdf")

    def test_highly_compressed_page_is_measured_without_expanding_it(self):
        from workers.parsers.pdf_limits import page_content_size

        bomb = self._doc_with_content(b"BT /helv 11 Tf 72 700 Td (A) Tj ET\n" + b" " * (4 * 1024 * 1024))
        raw = len(bomb.xref_stream_raw(bomb[0].get_contents()[0]))
        self.assertLess(raw, 64 * 1024)
        self.assertIsNone(page_content_size(bomb, bomb[0], 1024 * 1024))
        self.assertGreater(page_content_size(bomb, bomb[0], 8 * 1024 * 1024), 4 * 1024 * 1024)

    def test_ascii85_flate_chain_is_decoded_with_a_bound(self):
        import base64
        import zlib

        from workers.parsers.pdf_limits import page_content_size

        def doc_with(content: bytes):
            pymupdf = self._pymupdf()
            doc = pymupdf.open()
            page = doc.new_page()
            page.insert_text((72, 72), "Merhaba")
            xref = page.get_contents()[0]
            doc.update_stream(xref, base64.a85encode(zlib.compress(content)) + b"~>", compress=False)
            doc.xref_set_key(xref, "Filter", "[/ASCII85Decode /FlateDecode]")
            return pymupdf.open(stream=doc.tobytes(), filetype="pdf")

        small = doc_with(b"BT /helv 11 Tf 72 700 Td (Rapor) Tj ET\n")
        self.assertIn("Rapor", small[0].get_text())
        self.assertEqual(page_content_size(small, small[0], 1024 * 1024), len(small.xref_stream(small[0].get_contents()[0])))
        bomb = doc_with(b"BT /helv 11 Tf 72 700 Td (A) Tj ET\n" + b" " * (4 * 1024 * 1024))
        self.assertIsNone(page_content_size(bomb, bomb[0], 1024 * 1024))

    def test_form_drawn_many_times_counts_every_drawing(self):
        pymupdf = self._pymupdf()
        from workers.parsers.pdf_limits import page_content_size

        src = pymupdf.open()
        src.new_page().insert_text((72, 72), "İç form metni")
        doc = pymupdf.open()
        page = doc.new_page()
        page.show_pdf_page(pymupdf.Rect(0, 0, 300, 300), src, 0)
        once = page_content_size(doc, page, 1024 * 1024)
        self.assertIsNotNone(once)
        name = next(n for _x, n, invoker, _b in page.get_xobjects() if invoker == 0)
        drawing = b"q /" + name.encode() + b" Do Q "
        doc.update_stream(page.get_contents()[-1], drawing * 20000)
        self.assertIsNone(page_content_size(doc, doc[0], 1024 * 1024))

    def test_shared_stream_on_many_pages_hits_the_document_budget(self):
        from workers.parsers.pdf_limits import PdfBudget, PdfTooLarge

        pymupdf = self._pymupdf()
        doc = pymupdf.open()
        first = doc.new_page()
        first.insert_text((72, 72), "Merhaba")
        shared = first.get_contents()[0]
        resources = doc.xref_get_key(first.xref, "Resources")[1]
        doc.update_stream(shared, b"BT /helv 11 Tf 72 700 Td (A) Tj ET\n" + b" " * (600 * 1024))
        for _ in range(9):
            xref = doc.new_page().xref
            doc.xref_set_key(xref, "Contents", f"{shared} 0 R")
            doc.xref_set_key(xref, "Resources", resources)
        doc = pymupdf.open(stream=doc.tobytes(deflate=True), filetype="pdf")
        self.assertEqual(doc.page_count, 10)
        self.assertEqual({doc[i].get_contents()[0] for i in range(10)}, {doc[0].get_contents()[0]})
        budget = PdfBudget(doc, page_limit=1024 * 1024, total_limit=2 * 1024 * 1024)
        with self.assertRaises(PdfTooLarge):
            list(budget.pages(range(doc.page_count)))
        with self.assertRaises(PdfTooLarge):
            PdfBudget(doc, max_pages=5)

    def test_text_extraction_never_decodes_images(self):
        pymupdf = self._pymupdf()
        from workers.parsers.pdf_limits import text_flags

        self.assertFalse(text_flags(pymupdf) & pymupdf.TEXT_PRESERVE_IMAGES)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 64, 64), False)
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Metin")
        page.insert_image(pymupdf.Rect(72, 100, 272, 300), pixmap=pix)
        types = {b["type"] for b in page.get_text("dict", flags=text_flags(pymupdf))["blocks"]}
        self.assertEqual(types, {0})

    def test_parser_refuses_documents_over_the_limits(self):
        pymupdf = self._pymupdf()
        from workers.parsers import pdf_limits, pymupdf_parser
        from workers.parsers.pdf_limits import PdfTooLarge

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        bomb = self._doc_with_content(b"BT /helv 11 Tf 72 700 Td (A) Tj ET\n" + b" " * (2 * 1024 * 1024))
        bomb.save(str(tmp / "bomb.pdf"))
        with mock.patch.object(pdf_limits, "PDF_MAX_PAGE_CONTENT_BYTES", 1024 * 1024):
            with self.assertRaises(PdfTooLarge):
                pymupdf_parser.PyMuPDFParser().parse(str(tmp / "bomb.pdf"))

        doc = pymupdf.open()
        for i in range(5):
            doc.new_page().insert_text((72, 72), f"Sayfa {i} " + "metin " * 40)
        doc.save(str(tmp / "ok.pdf"))
        self.assertEqual(pymupdf_parser.PyMuPDFParser().parse(str(tmp / "ok.pdf")).page_count, 5)
        with mock.patch.object(pymupdf_parser, "PDF_MAX_TEXT_CHARS", 300):
            with self.assertRaises(PdfTooLarge):
                pymupdf_parser.PyMuPDFParser().parse(str(tmp / "ok.pdf"))

    def test_web_pdf_text_is_capped(self):
        pymupdf = self._pymupdf()
        from agent.tools import web_search
        from workers import deep_research
        from workers.parsers.pdf_limits import extract_plain_text

        doc = pymupdf.open()
        for i in range(3):
            doc.new_page().insert_text((72, 72), f"Sayfa {i} kaynak metni")
        data = doc.tobytes()
        self.assertIn("Sayfa 2 kaynak metni", extract_plain_text(data, max_pages=12, max_chars=10_000))
        self.assertEqual(len(extract_plain_text(data, max_pages=12, max_chars=10)), 10)
        self.assertIn("kaynak", web_search._pdf_text(data, "kaynak"))
        self.assertIn("Sayfa 0", deep_research._pdf_text(data))

        bomb = self._doc_with_content(b"BT /helv 11 Tf 72 700 Td (A) Tj ET\n" + b" " * (9 * 1024 * 1024))
        self.assertEqual(extract_plain_text(bomb.tobytes(deflate=True), max_pages=12, max_chars=10_000), "")
        self.assertEqual(extract_plain_text(b"not a pdf", max_pages=12, max_chars=10_000), "")


class SeventhRoundTests(unittest.TestCase):
    """AI Scan alerts #87-#92 (27 Nov 2026)."""

    def _pymupdf(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("PyMuPDF is not installed")
        return pymupdf

    def _form_page(self, drawing_template: bytes, times: int):
        """A page drawing its form XObject `times` times; returns (doc, form name)."""
        pymupdf = self._pymupdf()
        src = pymupdf.open()
        src.new_page().insert_text((72, 72), "İç form metni")
        doc = pymupdf.open()
        page = doc.new_page()
        page.show_pdf_page(pymupdf.Rect(0, 0, 300, 300), src, 0)
        name = next(n for _x, n, invoker, _b in page.get_xobjects() if invoker == 0)
        doc.update_stream(page.get_contents()[-1], drawing_template.replace(b"NAME", name.encode()) * times)
        return pymupdf.open(stream=doc.tobytes(), filetype="pdf"), name

    def test_drawings_with_comments_or_name_escapes_are_counted(self):
        from workers.parsers.pdf_limits import page_content_size

        for template in (b"q /NAME %yorum\n Do Q ", b"q /NAME%x\r\nDo Q "):
            doc, _ = self._form_page(template, 20000)
            self.assertIsNone(page_content_size(doc, doc[0], 1024 * 1024), template)
        doc, name = self._form_page(b"q /NAME Do Q ", 1)
        escaped = "".join(f"#{ord(c):02X}" if i == len(name) - 1 else c for i, c in enumerate(name))
        doc.update_stream(doc[0].get_contents()[-1], (b"q /" + escaped.encode() + b" Do Q ") * 20000)
        self.assertIn("Do", doc[0].read_contents().decode("latin-1"))
        self.assertIsNone(page_content_size(doc, doc[0], 1024 * 1024))

    def test_indirect_filter_is_resolved(self):
        import zlib

        pymupdf = self._pymupdf()
        from workers.parsers.pdf_limits import page_content_size

        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Merhaba")
        xref = page.get_contents()[0]
        content = b"BT /helv 11 Tf 72 700 Td (A) Tj ET\n" + b" " * (4 * 1024 * 1024)
        doc.update_stream(xref, zlib.compress(content), compress=False)
        filter_xref = doc.get_new_xref()
        doc.update_object(filter_xref, "/FlateDecode")
        doc.xref_set_key(xref, "Filter", f"{filter_xref} 0 R")
        doc = pymupdf.open(stream=doc.tobytes(), filetype="pdf")
        xref = doc[0].get_contents()[0]
        self.assertEqual(doc.xref_get_key(xref, "Filter")[0], "xref")
        self.assertEqual(len(doc.xref_stream(xref)), len(content))
        self.assertIsNone(page_content_size(doc, doc[0], 1024 * 1024))
        self.assertEqual(page_content_size(doc, doc[0], 8 * 1024 * 1024), len(content))

    def test_isolated_parser_is_stopped_at_the_memory_limit(self):
        from workers.parsers import isolation

        with mock.patch.object(isolation, "PARSER_ISOLATION", True):
            self.assertEqual(isolation.run_isolated(len, "abc"), 3)
            with self.assertRaises(isolation.ParserLimitExceeded):
                isolation.run_isolated(_allocate, 600, memory_mb=200, timeout=60)
            with self.assertRaises(isolation.ParserLimitExceeded):
                isolation.run_isolated(time_sleep, 30, timeout=1)
            with self.assertRaises(ValueError):
                isolation.run_isolated(int, "sayı değil")

    def test_isolated_pdf_parse_returns_blocks(self):
        pymupdf = self._pymupdf()
        from workers.parsers import isolation
        from workers.parsers.pdf_limits import PdfTooLarge
        from workers.parsers.pymupdf_parser import parse_file

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        doc = pymupdf.open()
        doc.new_page().insert_text((72, 72), "Metin from the child process")
        doc.save(str(tmp / "ok.pdf"))
        with mock.patch.object(isolation, "PARSER_ISOLATION", True):
            result = isolation.run_isolated(parse_file, str(tmp / "ok.pdf"), None)
            self.assertIn("Metin from the child process", result.text)
            many = pymupdf.open()
            for _ in range(3):
                many.new_page()
            many.save(str(tmp / "many.pdf"))
            with mock.patch.dict(os.environ, {"PDF_MAX_PAGES": "2"}):
                with self.assertRaises(PdfTooLarge):
                    isolation.run_isolated(_parse_with_page_limit, str(tmp / "many.pdf"))

    def _epub(self, path: Path, manifest_items: str, files: dict, spine: str = "") -> None:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            z.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
            )
            z.writestr(
                "OEBPS/content.opf",
                '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
                '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">x</dc:identifier><dc:title>t</dc:title>'
                f'<dc:language>tr</dc:language></metadata><manifest>{manifest_items}</manifest><spine>{spine}</spine></package>',
            )
            for name, data in files.items():
                z.writestr("OEBPS/" + name, data)

    def test_epub_manifest_repeating_one_file_is_refused(self):
        from workers.parsers import epub_parser

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        chapter = "<html><body><p>" + "metin " * 200_000 + "</p></body></html>"  # ~1.2 MB, compresses well
        items = "".join(f'<item id="c{i}" href="c.xhtml" media-type="application/xhtml+xml"/>' for i in range(10))
        self._epub(tmp / "b.epub", items, {"c.xhtml": chapter}, '<itemref idref="c0"/>')
        epub_parser.check_manifest_size(str(tmp / "b.epub"))  # 12 MB in total: allowed by default
        with mock.patch.object(epub_parser, "ARCHIVE_MAX_UNCOMPRESSED_BYTES", 5 * 1024 * 1024):
            with self.assertRaises(RuntimeError):
                epub_parser.check_manifest_size(str(tmp / "b.epub"))

    def test_epub_nested_tables_are_not_copied_per_level(self):
        from workers.parsers.epub_parser import EpubParser

        depth = 40
        html = "<html><body>" + "<table><tr><td>" * depth + "BÜYÜK " * 1000 + "</td></tr></table>" * depth + "<p>son</p></body></html>"
        blocks = EpubParser()._extract_chapter_blocks(html.encode())
        total = sum(len(b[0]) for b in blocks)
        self.assertLess(total, len("BÜYÜK ") * 1000 * 2)
        self.assertEqual(blocks[-1][0], "son")
        simple = EpubParser()._extract_chapter_blocks(
            b"<html><body><h1>Bas<p>ic</p></h1><table><thead><tr><th>A</th><th>B</th></tr></thead>"
            b"<tbody><tr><td>1</td><td>2</td></tr></tbody></table><ul><li>madde</li></ul></body></html>"
        )
        self.assertEqual(
            [b[0] for b in simple],
            ["Bas ic", "ic", "| A | B |\n| --- | --- |\n| 1 | 2 |", "madde"],
        )


def _allocate(mb: int) -> int:
    chunks = [bytearray(1024 * 1024) for _ in range(mb)]
    import time

    time.sleep(5)
    return len(chunks)


def time_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


def _parse_with_page_limit(path: str):
    import importlib

    from workers.parsers import pdf_limits, pymupdf_parser

    importlib.reload(pdf_limits)
    importlib.reload(pymupdf_parser)
    return pymupdf_parser.parse_file(path)


class EighthRoundTests(unittest.TestCase):
    """AI Scan alerts #93-#95 (27 Nov 2026)."""

    def test_nested_page_containers_are_read_once(self):
        from workers.parsers.html_parser import HtmlParser

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        body = '<div class="PageText">' * 300 + "<p>" + "tekrar " * 500 + "</p>" + "</div>" * 300
        (tmp / "p.html").write_text(f"<html><body>{body}</body></html>", encoding="utf-8")
        result = asyncio.run(HtmlParser().parse(str(tmp / "p.html")))
        self.assertEqual(result.text.count("tekrar"), 500)

    def test_docx_and_txt_parse_in_child_process(self):
        from workers.parsers import isolation
        from workers.parsers.docx_parser import DocxParser
        from workers.parsers.txt_parser import TxtParser

        try:
            import docx
        except ImportError:
            self.skipTest("python-docx is not installed")
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        document = docx.Document()
        document.add_paragraph("Birinci paragraf.")
        document.add_paragraph("İkinci paragraf.")
        document.save(str(tmp / "d.docx"))
        (tmp / "t.txt").write_text("Başlık\n\nMetin satırı burada.", encoding="utf-8")
        with mock.patch.object(isolation, "PARSER_ISOLATION", True), mock.patch.object(
            isolation, "run_isolated", wraps=isolation.run_isolated
        ) as spy:
            self.assertIn("İkinci paragraf.", asyncio.run(DocxParser().parse(str(tmp / "d.docx"))).text)
            self.assertIn("Metin satırı burada.", asyncio.run(TxtParser().parse(str(tmp / "t.txt"))).text)
        self.assertEqual(spy.call_count, 2)

    def test_web_page_noise_removal_is_linear(self):
        import time

        from services.searxng_client import extract_html

        deep = "<html><body>" + '<div class="cookie">' * 3000 + "x " * 2000 + "</div>" * 3000 + "</body></html>"
        start = time.perf_counter()
        self.assertGreater(len(extract_html(deep, "https://ex.org/")["text"]), 1000)
        self.assertLess(time.perf_counter() - start, 3)
        page = (
            '<html><body><div class="cookie-banner"><p>Çerezleri kabul edin</p></div>'
            '<div class="content has-sidebar"><article>' + "<p>" + "Makale metni. " * 60 + "</p>" * 1
            + "</article><div class='sidebar'><p>Kısa yan kutu</p></div></div></body></html>"
        )
        text = extract_html(page, "https://ex.org/")["text"]
        self.assertIn("Makale metni.", text)
        self.assertNotIn("Çerezleri", text)
        self.assertNotIn("yan kutu", text)


class NinthRoundTests(unittest.TestCase):
    """AI Scan alerts #96-#97 (27 Nov 2026)."""

    def test_many_author_meta_tags_are_linear(self):
        import time

        from bs4 import BeautifulSoup

        from services.searxng_client import _meta_all

        html = "<html><head>" + "".join(f'<meta name="citation_author" content="Yazar {i}">' for i in range(30000)) + "</head></html>"
        soup = BeautifulSoup(html, "html.parser")
        start = time.perf_counter()
        values = _meta_all(soup, "citation_author")
        self.assertLess(time.perf_counter() - start, 2)
        self.assertEqual(values[:2], ["Yazar 0", "Yazar 1"])
        self.assertLessEqual(len(values), 100)
        dup = BeautifulSoup('<meta name="a" content="x"><meta name="a" content="x"><meta name="a" content="y">', "html.parser")
        self.assertEqual(_meta_all(dup, "a"), ["x", "y"])

    def test_ocr_chunks_are_written_one_at_a_time(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("PyMuPDF is not installed")
        from services import ocr_client
        from workers.parsers import pdf_limits

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        doc = pymupdf.open()
        for i in range(45):
            doc.new_page().insert_text((72, 72), f"Sayfa {i} {tmp.name}")
        doc.save(str(tmp / "uzun.pdf"))

        seen: list = []

        async def fake_single(self, file_path, page_count):
            folder = os.path.dirname(file_path)
            seen.append((page_count, len(os.listdir(folder))))
            return ocr_client.OCRResult(markdown=f"parca {page_count}", content_list=[], success=True, page_count=page_count)

        client = ocr_client.PDFOCRClient(base_url="https://ocr.example.org", api_key="k", model=f"m-{tmp.name}")
        with mock.patch.object(ocr_client.PDFOCRClient, "_parse_pdf_single", fake_single), mock.patch.object(
            ocr_client, "OCR_PDF_CHUNK_PAGES", 20
        ):
            result = asyncio.run(client.parse_pdf(str(tmp / "uzun.pdf")))
            self.assertTrue(result.success, result.error_message)
            self.assertEqual([count for count, _ in seen], [20, 20, 5])
            self.assertEqual({files for _, files in seen}, {1})
            with mock.patch.object(pdf_limits, "PDF_MAX_PAGES", 30):
                refused = asyncio.run(client.parse_pdf(str(tmp / "uzun.pdf")))
            self.assertFalse(refused.success)
            self.assertIn("45", refused.error_message)


class TenthRoundTests(unittest.TestCase):
    """AI Scan alerts #98-#100 (27 Nov 2026)."""

    def _run_with_db(self, body):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from database import Base
        from models.auth_session import AuthSession
        from models.user import User

        async def main():
            engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all, tables=[User.__table__, AuthSession.__table__])
            maker = async_sessionmaker(engine, expire_on_commit=False)
            try:
                async with maker() as db:
                    await body(db)
            finally:
                await engine.dispose()

        asyncio.run(main())

    def test_logout_revokes_access_refresh_and_media_tokens(self):
        from fastapi import HTTPException

        from dependencies import auth
        from models.user import User

        async def body(db):
            user = User(id="u1", username="ayse", password_hash=auth.hash_password("parola-123"), role="user")
            db.add(user)
            await db.commit()
            tokens = auth.issue_tokens(user, await auth.start_session(db, user))
            self.assertEqual((await auth._get_user_from_token(tokens["access_token"], db)).id, "u1")
            self.assertEqual((await auth._get_user_from_token(tokens["media_token"], db, expected_type="media")).id, "u1")
            sid = auth.decode_token(tokens["access_token"])["sid"]
            self.assertTrue(await auth.revoke_session(db, sid))
            for token, kind in ((tokens["access_token"], "access"), (tokens["media_token"], "media")):
                with self.assertRaises(HTTPException):
                    await auth._get_user_from_token(token, db, expected_type=kind)
            with self.assertRaises(HTTPException):
                await auth.rotate_refresh(db, auth.decode_token(tokens["refresh_token"], expected_type="refresh"))

        self._run_with_db(body)

    def test_refresh_token_works_once_and_reuse_revokes_the_session(self):
        from fastapi import HTTPException

        from dependencies import auth
        from models.user import User

        async def body(db):
            user = User(id="u2", username="mehmet", password_hash=auth.hash_password("parola-456"), role="user")
            db.add(user)
            await db.commit()
            first = auth.issue_tokens(user, await auth.start_session(db, user))
            payload = auth.decode_token(first["refresh_token"], expected_type="refresh")
            second = auth.issue_tokens(user, await auth.rotate_refresh(db, payload))
            self.assertEqual((await auth._get_user_from_token(second["access_token"], db)).id, "u2")
            with self.assertRaises(HTTPException):  # the first refresh token again: a copy
                await auth.rotate_refresh(db, payload)
            with self.assertRaises(HTTPException):  # ...which signed the whole session out
                await auth._get_user_from_token(second["access_token"], db)
            legacy = auth.create_access_token(auth.token_payload_for(user), refresh=True)
            with self.assertRaises(HTTPException):
                await auth.rotate_refresh(db, auth.decode_token(legacy, expected_type="refresh"))
            other = auth.issue_tokens(user, await auth.start_session(db, user))
            self.assertEqual((await auth._get_user_from_token(other["access_token"], db)).id, "u2")

        self._run_with_db(body)

    def test_search_cache_is_bounded_and_forgets_deleted_files(self):
        from services import project_search as ps

        ps._file_cache.clear()
        ps._cache_bytes = 0
        self.addCleanup(ps._file_cache.clear)
        with mock.patch.dict(os.environ, {"PROJECT_SEARCH_CACHE_MB": "1"}):
            for i in range(40):
                text = "metin " * 10_000  # ~120 KB per entry
                entry = ps._FileIndex(stamp="s", paged=False, blocks=[(text, text, 0)], size=2 * 2 * len(text))
                ps._cache_put(f"f{i}", entry)
                self.assertLessEqual(ps._cache_bytes, 1024 * 1024)
            self.assertIn("f39", ps._file_cache)
            self.assertNotIn("f0", ps._file_cache)
            ps.forget_file("f39")
            self.assertNotIn("f39", ps._file_cache)
            self.assertEqual(ps._cache_bytes, sum(e.size for e in ps._file_cache.values()))


class EleventhRoundTests(unittest.TestCase):
    """AI Scan alerts #101-#103 (27 Nov 2026)."""

    def _run_with_file_db(self, body):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from database import Base
        from models.auth_session import AuthSession
        from models.user import User

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)

        async def main():
            engine = create_async_engine(f"sqlite+aiosqlite:///{tmp / 'auth.db'}")
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all, tables=[User.__table__, AuthSession.__table__])
            maker = async_sessionmaker(engine, expire_on_commit=False)
            try:
                await body(maker)
            finally:
                await engine.dispose()

        asyncio.run(main())

    def test_concurrent_refresh_with_one_token_lets_only_one_through(self):
        from fastapi import HTTPException

        from dependencies import auth
        from models.user import User

        async def body(maker):
            async with maker() as db:
                user = User(id="u3", username="zeynep", password_hash=auth.hash_password("parola-789"), role="user")
                db.add(user)
                await db.commit()
                tokens = auth.issue_tokens(user, await auth.start_session(db, user))
            payload = auth.decode_token(tokens["refresh_token"], expected_type="refresh")

            async def attempt():
                async with maker() as db:
                    try:
                        return await auth.rotate_refresh(db, dict(payload))
                    except HTTPException:
                        return None

            results = await asyncio.gather(*(attempt() for _ in range(4)))
            self.assertEqual(sum(r is not None for r in results), 1)
            async with maker() as db:  # the replays revoked the session
                self.assertFalse(await auth.session_is_active(db, auth.decode_token(tokens["access_token"])))

        self._run_with_file_db(body)

    def test_upload_guard_refuses_signed_out_sessions(self):
        import database

        from dependencies import auth
        from models.user import User
        from utils import upload_guard

        async def body(maker):
            async with maker() as db:
                user = User(id="u4", username="ali", password_hash=auth.hash_password("parola-000"), role="admin")
                db.add(user)
                await db.commit()
                tokens = auth.issue_tokens(user, await auth.start_session(db, user))
            with mock.patch.object(database, "AsyncSessionLocal", maker):
                self.assertIsNotNone(await upload_guard._uploader(tokens["access_token"]))
                async with maker() as db:
                    await auth.revoke_session(db, auth.decode_token(tokens["access_token"])["sid"])
                self.assertIsNone(await upload_guard._uploader(tokens["access_token"]))

        self._run_with_file_db(body)

    def test_same_name_upload_gets_its_own_file(self):
        from routes.file_routes import _reserve_upload_path

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        first = _reserve_upload_path(tmp, "rapor.pdf")
        second = _reserve_upload_path(tmp, "rapor.pdf")
        third = _reserve_upload_path(tmp, "rapor.pdf")
        self.assertEqual([p.name for p in (first, second, third)], ["rapor.pdf", "rapor (2).pdf", "rapor (3).pdf"])
        with self.assertRaises(ValueError):
            _reserve_upload_path(tmp, "../dışarı.pdf")
