"""Tests for the fixes made for GitHub code scanning (CodeQL) alerts, 23 Nov 2026:
path joins under the upload root, regexes that cannot backtrack, no admin password
in logs, and error text that does not reveal exception details."""

import asyncio
import logging
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(BACKEND_DIR / "packages") not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR / "packages"))

from paths import safe_join  # noqa: E402


class SafeJoinTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "uploads"
        self.root.mkdir()

    def test_plain_parts_stay_inside(self):
        path = safe_join(self.root, "3f2a-project", "Makale (2).pdf")
        self.assertEqual(path, Path(os.path.realpath(self.root)) / "3f2a-project" / "Makale (2).pdf")

    def test_traversal_is_refused(self):
        for parts in (("..",), ("..", "etc"), ("a", "..", ".."), ("/etc/passwd",), ("a/../../b",)):
            with self.subTest(parts=parts), self.assertRaises(ValueError):
                safe_join(self.root, *parts)

    def test_symlink_out_of_root_is_refused(self):
        outside = Path(self._tmp.name) / "outside"
        outside.mkdir()
        (self.root / "link").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            safe_join(self.root, "link", "x.txt")

    def test_root_itself_is_allowed(self):
        self.assertEqual(safe_join(self.root), Path(os.path.realpath(self.root)))


class RegexBacktrackingTests(unittest.TestCase):
    """Inputs that used to take seconds (or, for [S…] references, hours) finish at once."""

    def _fast(self, fn, *args, limit=0.5):
        start = time.perf_counter()
        fn(*args)
        self.assertLess(time.perf_counter() - start, limit)

    def test_source_reference_pattern(self):
        from workers.deep_research import _SOURCE_REF_RE

        self._fast(_SOURCE_REF_RE.search, "[s0," + " 0," * 5000)
        self.assertEqual(_SOURCE_REF_RE.findall("bkz. [S1, S2; 3] ve [s 4]"), ["S1, S2; 3", "s 4"])

    def test_citation_token_pattern(self):
        from routes.feature_routes import _CITATION_TOKEN_RE

        self._fast(_CITATION_TOKEN_RE.sub, "", "[citation_" * 20000)
        self.assertEqual(_CITATION_TOKEN_RE.sub("", "Başlık [citation_3] metin [citation:4]"), "Başlık  metin ")

    def test_markdown_block_patterns(self):
        from agent import blocks_builder as bb

        long_spaces = " " * 50000
        self._fast(bb._HEADING_RE.match, "#" + long_spaces + "\x00")
        self._fast(bb._LIST_RE.match, "-" + long_spaces)
        self._fast(bb._is_table_row, "|" * 20000 + long_spaces + "x")
        self._fast(bb._is_table_separator, long_spaces + "x")

    def test_markdown_block_behaviour(self):
        from agent import blocks_builder as bb

        self.assertEqual(bb._HEADING_RE.match("##   Giriş ").group(2).strip(), "Giriş")
        self.assertIsNone(bb._HEADING_RE.match("####### çok"))
        self.assertEqual(bb._LIST_RE.match("  1)   madde").group(1).strip(), "madde")
        self.assertTrue(bb._is_table_row("  | a | b |  "))
        self.assertFalse(bb._is_table_row("|"))
        self.assertFalse(bb._is_table_row("a | b"))
        for sep in ("|---|---|", " | :-- | --: |", "--- | ---", ":---"):
            self.assertTrue(bb._is_table_separator(sep), sep)
        for not_sep in ("| - |", "|: --|", "text", ""):
            self.assertFalse(bb._is_table_separator(not_sep), not_sep)


class PublicErrorMessageTests(unittest.TestCase):
    def setUp(self):
        from utils import i18n

        token = i18n.set_language("en")
        self.addCleanup(i18n.reset_language, token)

    def test_details_are_not_echoed(self):
        from kosong.chat_provider import APIConnectionError, APIStatusError, APITimeoutError
        from utils.errors import error_kind, public_error_message

        secret = "Incorrect API key provided: sk-abc***xyz at http://10.0.0.5:8000/v1 /srv/app/x.py"
        cases = {
            APIStatusError(401, secret): "auth",
            APIStatusError(429, secret): "rate_limit",
            APIStatusError(400, "This model's maximum context length is 8192 tokens"): "context",
            APIStatusError(503, secret): "provider",
            APIStatusError(422, secret): "bad_request",
            APITimeoutError(secret): "timeout",
            APIConnectionError(secret): "connect",
            asyncio.TimeoutError(): "timeout",
            RuntimeError(secret): "unknown",
        }
        for exc, kind in cases.items():
            with self.subTest(exc=type(exc).__name__, kind=kind):
                self.assertEqual(error_kind(exc), kind)
                message = public_error_message(exc)
                self.assertNotIn("sk-", message)
                self.assertNotIn("10.0.0.5", message)
                self.assertNotIn("/srv/", message)
        self.assertIn("422", public_error_message(APIStatusError(422, secret)))


class AdminPasswordNotLoggedTests(unittest.TestCase):
    def _db(self, existing=None):
        result = mock.Mock()
        result.scalar_one_or_none.return_value = existing
        db = mock.Mock()
        db.execute = mock.AsyncMock(return_value=result)
        db.commit = mock.AsyncMock()
        return db

    def _run(self, db):
        import main

        with mock.patch.dict(os.environ, {"ADMIN_PASSWORD": "", "ADMIN_USERNAME": "admin"}), \
                mock.patch.object(main, "_write_admin_password_file", return_value=None), \
                mock.patch.object(main, "_generate_admin_password", return_value="Gen3rated-Secret-Value"), \
                self.assertLogs(level=logging.DEBUG) as logs:
            logging.getLogger("probe").debug("start")
            with self.assertRaises(RuntimeError):
                asyncio.run(main._ensure_admin_user(db))
        self.assertFalse(any("Gen3rated-Secret-Value" in line for line in logs.output))

    def test_new_admin_without_password_file_is_not_created_or_logged(self):
        db = self._db()
        self._run(db)
        db.add.assert_not_called()
        db.commit.assert_not_awaited()

    def test_default_password_rotation_without_file_keeps_nothing_half_done(self):
        from dependencies.auth import hash_password

        user = mock.Mock(role="admin", password_hash=hash_password("admin"))
        db = self._db(existing=user)
        old_hash = user.password_hash
        self._run(db)
        self.assertEqual(user.password_hash, old_hash)
        db.commit.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
