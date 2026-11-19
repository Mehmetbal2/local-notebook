"""Tests for the follow-up items of the 19 Nov 2026 audit (backup links, cleanup, CORS,
vector search cache, log noise, task retries)."""

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

from services import backup_service  # noqa: E402
from services import vector_service  # noqa: E402


class _DataDir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        patcher = mock.patch.object(backup_service, "get_data_dir", return_value=self.data)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)
        backup_service._downloads.clear()
        self.addCleanup(backup_service._downloads.clear)


class BackupDownloadTokenTests(_DataDir):
    def _archive(self, name="local-notebook-backup-1.zip") -> Path:
        path = self.data / "backups" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"zip")
        return path

    def test_token_is_single_use(self):
        archive = self._archive()
        token = backup_service.register_download(archive)
        self.assertEqual(backup_service.claim_download(token), archive)
        self.assertIsNone(backup_service.claim_download(token))

    def test_unknown_token_is_rejected(self):
        self.assertIsNone(backup_service.claim_download("not-a-token"))

    def test_expired_token_is_rejected_and_file_removed(self):
        archive = self._archive()
        token = backup_service.register_download(archive)
        path, _ = backup_service._downloads[token]
        backup_service._downloads[token] = (path, time.time() - 1)
        self.assertIsNone(backup_service.claim_download(token))
        self.assertFalse(archive.exists())


class PruneBackupsTests(_DataDir):
    def test_keeps_newest_pre_restore_copies(self):
        backups = self.data / "backups"
        names = [f"pre-restore-2026111{i}-120000" for i in range(5)]
        for name in names:
            (backups / name).mkdir(parents=True)
            (backups / name / "local_notebook.db").write_bytes(b"x" * 10)
        result = backup_service.prune_backups(keep_pre_restore=2)
        remaining = sorted(p.name for p in backups.iterdir())
        self.assertEqual(remaining, names[-2:])
        self.assertEqual(result["freed_bytes"], 30)

    def test_removes_stale_unfetched_archive_but_not_waiting_one(self):
        backups = self.data / "backups"
        backups.mkdir(parents=True)
        stale = backups / "local-notebook-backup-old.zip"
        waiting = backups / "local-notebook-backup-waiting.zip"
        for path in (stale, waiting):
            path.write_bytes(b"zip")
            old = time.time() - backup_service.DOWNLOAD_TTL_SECONDS - 60
            os.utime(path, (old, old))
        backup_service.register_download(waiting)
        backup_service.prune_backups()
        self.assertFalse(stale.exists())
        self.assertTrue(waiting.exists())

    def test_removes_replaced_restore_uploads_only(self):
        restore = self.data / "restore"
        current = restore / "20261119-100000-000001"
        replaced = restore / "20261119-090000-000001"
        current.mkdir(parents=True)
        replaced.mkdir(parents=True)
        (restore / "pending.json").write_text(f'{{"staging": "{current}"}}', encoding="utf-8")
        backup_service.prune_backups()
        self.assertTrue(current.exists())
        self.assertFalse(replaced.exists())
        self.assertTrue((restore / "pending.json").exists())


class CorsTests(unittest.TestCase):
    def setUp(self):
        import main

        self.main = main

    def _allowed(self, origin, frontend="8080", extra=""):
        return re.match(self.main._cors_origin_regex(frontend, extra), origin) is not None

    def test_frontend_and_vite_ports_are_allowed(self):
        self.assertTrue(self._allowed("http://localhost:8080"))
        self.assertTrue(self._allowed("http://192.168.1.20:5173"))

    def test_extra_ports_are_configurable(self):
        self.assertFalse(self._allowed("http://localhost:3000"))
        self.assertTrue(self._allowed("http://localhost:3000", extra="3000, 4000"))

    def test_public_hosts_and_junk_ports_stay_blocked(self):
        self.assertFalse(self._allowed("http://example.com:8080"))
        self.assertFalse(self._allowed("http://localhost:8080.evil.com"))
        self.assertEqual(self.main._cors_ports("8080", "abc,99999,8080"), ["8080", "5173"])


class _FakeClient:
    def __init__(self, dim=8):
        self.dim = dim
        self.collections = {vector_service.TEXT_COLLECTION}
        self.describe_calls = 0
        self.load_calls = 0
        self.fail_search = False

    def has_collection(self, name, **_):
        return name in self.collections

    def load_collection(self, name, **_):
        self.load_calls += 1

    def describe_collection(self, name, **_):
        self.describe_calls += 1
        return {"fields": [{"name": "embedding", "params": {"dim": self.dim}}]}

    def search(self, **_):
        if self.fail_search:
            raise RuntimeError("collection not loaded")
        return [[]]


class VectorSearchCacheTests(unittest.TestCase):
    def setUp(self):
        self.client = _FakeClient()
        patcher = mock.patch.object(vector_service, "_get_client", return_value=self.client)
        patcher.start()
        self.addCleanup(patcher.stop)
        vector_service._search_ready.clear()
        self.addCleanup(vector_service._search_ready.clear)

    def test_repeated_searches_describe_the_collection_once(self):
        for _ in range(5):
            vector_service.search("p1", [0.0] * 8)
        self.assertEqual(self.client.describe_calls, 1)
        self.assertEqual(self.client.load_calls, 1)

    def test_drop_invalidates_the_cache(self):
        vector_service.search("p1", [0.0] * 8)
        self.client.collections.clear()
        vector_service._forget_collection(vector_service.TEXT_COLLECTION)
        self.assertEqual(vector_service.search("p1", [0.0] * 8), [])

    def test_dim_mismatch_is_still_reported(self):
        vector_service.search("p1", [0.0] * 8)
        with self.assertRaises(RuntimeError):
            vector_service.search("p1", [0.0] * 16)

    def test_failed_search_on_a_vanished_collection_returns_empty(self):
        vector_service.search("p1", [0.0] * 8)
        self.client.fail_search = True
        self.client.collections.clear()
        self.assertEqual(vector_service.search("p1", [0.0] * 8), [])
        self.assertEqual(vector_service._search_ready, {})


class MilvusLiteNoiseFilterTests(unittest.TestCase):
    def setUp(self):
        import main

        self.filter = main._MilvusLiteNoiseFilter()

    def _record(self, fn_name):
        def AllocTimestamp():  # noqa: N802 - mirrors the gRPC servicer method name
            raise NotImplementedError("Method not implemented!")

        def Other():  # noqa: N802
            raise NotImplementedError("Method not implemented!")

        try:
            (AllocTimestamp if fn_name == "AllocTimestamp" else Other)()
        except NotImplementedError:
            exc_info = sys.exc_info()
        return logging.LogRecord(
            "grpc._server", logging.ERROR, __file__, 1,
            "Exception calling application: %s", ("Method not implemented!",), exc_info,
        )

    def test_alloc_timestamp_error_is_dropped(self):
        self.assertFalse(self.filter.filter(self._record("AllocTimestamp")))

    def test_other_grpc_errors_are_kept(self):
        self.assertTrue(self.filter.filter(self._record("Other")))
        plain = logging.LogRecord("grpc._server", logging.ERROR, __file__, 1, "boom", (), None)
        self.assertTrue(self.filter.filter(plain))


class TaskRetryPolicyTests(unittest.TestCase):
    def test_reembed_and_refresh_have_explicit_retry_limits(self):
        from workers.tasks import WorkerSettings

        limits = {
            getattr(item, "name", None) or getattr(item, "__name__", ""): getattr(item, "max_tries", None)
            for item in WorkerSettings.functions
        }
        self.assertEqual(limits.get("reembed_file_task"), 2)
        self.assertEqual(limits.get("refresh_project_summary_task"), 2)


class UsageDateTests(unittest.TestCase):
    def test_defaults_to_the_machine_time_zone(self):
        from datetime import datetime

        from services import usage_service

        with mock.patch.dict(os.environ, {"USAGE_TIMEZONE": ""}):
            self.assertEqual(usage_service.current_usage_date(), datetime.now().astimezone().date())
        with mock.patch.dict(os.environ, {"USAGE_TIMEZONE": "Not/AZone"}):
            self.assertEqual(usage_service.current_usage_date(), datetime.now().astimezone().date())

    def test_explicit_zone_is_respected(self):
        from datetime import datetime, timezone

        from services import usage_service

        with mock.patch.dict(os.environ, {"USAGE_TIMEZONE": "UTC"}):
            self.assertEqual(usage_service.current_usage_date(), datetime.now(timezone.utc).date())


class SessionTitlePlaceholderTests(unittest.TestCase):
    def test_translated_default_titles_count_as_unnamed(self):
        from services.session_title_service import is_placeholder_session_title

        for title in ("", "New chat", "Yeni sohbet", "新对话", "  Yeni sohbet  "):
            self.assertTrue(is_placeholder_session_title(title), title)
        self.assertFalse(is_placeholder_session_title("Mâverdî ve Fârâbî"))


if __name__ == "__main__":
    unittest.main()
