"""Regression tests for reliability fixes that are easy to break silently.

Covered here:
- "Author - Year - Title" detection with hyphens inside the author name.
- Milvus Lite client initialization is serialized across threads.
- Background LLM calls respect one process-wide concurrency cap.
"""

import asyncio
import contextlib
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import config
from services import summary_service, vector_service
from services.source_naming import is_bibliographic_name
from workers import tasks as tasks_module


class BibliographicNameTests(unittest.TestCase):
    def test_hyphenated_author_names_are_recognized(self):
        names = [
            "Ebü'l-Hasan Ali b. Muhammed el-Mâverdî - 1986 - Edebü'd-dünyâ ve'd-dîn",
            "Jean-Paul Sartre - 1943 - L'Être et le néant",
            "Author-Name - 1408/1988 - Title",
            "Author - t.y. - Title",
            "Author - n.d. - Title",
        ]
        for name in names:
            with self.subTest(name=name):
                self.assertTrue(is_bibliographic_name(name))

    def test_non_bibliographic_names_are_rejected(self):
        names = [
            "Kitap",
            "Author - Title",
            "Author - 1986 Title",
            "- 1986 - Title",
            "",
        ]
        for name in names:
            with self.subTest(name=name):
                self.assertFalse(is_bibliographic_name(name))


class MilvusClientLockTests(unittest.TestCase):
    def test_concurrent_get_client_creates_one_client(self):
        state = {"in_flight": 0, "max_in_flight": 0, "created": 0}
        state_lock = threading.Lock()

        def fake_create(uri):
            with state_lock:
                state["in_flight"] += 1
                state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
            time.sleep(0.05)
            with state_lock:
                state["in_flight"] -= 1
                state["created"] += 1
            return object()

        original_client = vector_service._client
        original_uri = vector_service.MILVUS_URI
        vector_service._client = None
        try:
            with mock.patch.object(
                vector_service, "get_milvus_uri", return_value="/tmp/fake-milvus.db"
            ), mock.patch.object(
                vector_service, "_create_milvus_client", side_effect=fake_create
            ):
                results = []

                def worker():
                    results.append(vector_service._get_client())

                threads = [threading.Thread(target=worker) for _ in range(8)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()
        finally:
            vector_service._client = original_client
            vector_service.MILVUS_URI = original_uri

        self.assertEqual(state["max_in_flight"], 1)
        self.assertEqual(state["created"], 1)
        self.assertEqual(len(results), 8)
        self.assertEqual(len({id(result) for result in results}), 1)


class _FakeMessage:
    def extract_text(self):
        return "summary"


class _FakeResult:
    def __init__(self):
        self.usage = None
        self.message = _FakeMessage()


class GlobalLlmConcurrencyTests(unittest.TestCase):
    def test_background_llm_calls_respect_process_limit(self):
        state = {"current": 0, "max": 0}

        async def fake_generate(**kwargs):
            state["current"] += 1
            state["max"] = max(state["max"], state["current"])
            await asyncio.sleep(0.05)
            state["current"] -= 1
            return _FakeResult()

        async def fake_record_model_usage(**kwargs):
            return None

        async def run():
            with mock.patch.object(
                summary_service, "create_llm_chat_provider", return_value=object()
            ), mock.patch.object(
                summary_service, "generate", side_effect=fake_generate
            ), mock.patch.object(
                summary_service, "record_model_usage", side_effect=fake_record_model_usage
            ):
                await asyncio.gather(
                    *[
                        summary_service._llm_complete("prompt", "key", None, "model")
                        for _ in range(8)
                    ]
                )

        asyncio.run(run())

        expected = min(8, summary_service.LLM_MAX_CONCURRENCY)
        self.assertEqual(state["max"], expected)
        self.assertLessEqual(state["current"], 0)


class MilvusStartupRetryTests(unittest.TestCase):
    def test_retries_only_lock_errors_until_success(self):
        calls = {"count": 0}

        def flaky_create(uri):
            calls["count"] += 1
            if calls["count"] < 3:
                raise RuntimeError("Open local milvus failed")
            return "client"

        with mock.patch.object(
            vector_service, "_create_milvus_client", side_effect=flaky_create
        ), mock.patch.object(vector_service.time, "sleep", return_value=None):
            result = vector_service._create_client_with_retry("/tmp/milvus.db")

        self.assertEqual(result, "client")
        self.assertEqual(calls["count"], 3)

    def test_other_errors_are_not_retried(self):
        calls = {"count": 0}

        def failing_create(uri):
            calls["count"] += 1
            raise RuntimeError("connection refused")

        with mock.patch.object(
            vector_service, "_create_milvus_client", side_effect=failing_create
        ), mock.patch.object(vector_service.time, "sleep", return_value=None):
            with self.assertRaises(RuntimeError):
                vector_service._create_client_with_retry("/tmp/milvus.db")

        self.assertEqual(calls["count"], 1)


class BackupServiceTests(unittest.TestCase):
    def _make_db(self, path: Path, users: list[str]) -> None:
        import sqlite3

        conn = sqlite3.connect(path)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS users (id TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS files (id TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS projects (id TEXT)")
            conn.executemany("INSERT INTO users VALUES (?)", [(u,) for u in users])
            conn.commit()
        finally:
            conn.close()

    def _env(self, data_dir: Path) -> dict:
        db_path = data_dir / "local_notebook.db"
        return {
            "LOCAL_NOTEBOOK_DATA_DIR": str(data_dir),
            "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
            "MILVUS_URI": str(data_dir / "milvus.db"),
        }

    def test_backup_and_restore_round_trip(self):
        import os
        import sqlite3
        import tempfile
        from unittest import mock

        from services import backup_service

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            db_path = data_dir / "local_notebook.db"
            self._make_db(db_path, ["original"])

            with mock.patch.dict(os.environ, self._env(data_dir)):
                archive = backup_service.create_backup_archive(include_uploads=False)
                self.assertTrue(archive.exists())

                self._make_db(db_path, ["changed"])
                backup_service.stage_restore_archive(archive)
                result = backup_service.apply_pending_restore()

            self.assertIsNotNone(result)
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute("SELECT id FROM users").fetchall()
            finally:
                conn.close()
            self.assertEqual(rows, [("original",)])
            self.assertTrue(Path(result["safety"]).exists())

    def _make_vector_store(self, path: Path) -> None:
        """Build a miniature Milvus Lite directory: one collection, one data file."""
        collection = path / "collections" / "local_notebook_text_segments_v1"
        (collection / "partitions" / "_default" / "data").mkdir(parents=True)
        (collection / "wal").mkdir(parents=True)
        (path / "LOCK").write_text("", encoding="utf-8")
        (path / ".database-staging").mkdir()
        (path / ".database-staging" / "scratch").write_text("scratch", encoding="utf-8")
        (collection / "partitions" / "_default" / "data" / "data_000001_000002.parquet").write_bytes(
            b"PAR1-vector-data-PAR1"
        )
        (collection / "manifest.json").write_text(
            '{"partitions": {"_default": {"data_files": '
            '["data/data_000001_000002.parquet"], "delta_files": []}}}',
            encoding="utf-8",
        )

    def test_backup_restores_milvus_directory(self):
        import os
        import tempfile
        import zipfile
        from unittest import mock

        from services import backup_service

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            self._make_db(data_dir / "local_notebook.db", ["original"])
            vectors = data_dir / "milvus.db"
            self._make_vector_store(vectors)

            with mock.patch.dict(os.environ, self._env(data_dir)):
                archive = backup_service.create_backup_archive(include_uploads=False)
                names = set(zipfile.ZipFile(archive).namelist())
                self.assertIn("milvus.db/collections/local_notebook_text_segments_v1/manifest.json", names)
                self.assertNotIn("milvus.db/LOCK", names)
                self.assertFalse(any(name.startswith("milvus.db/.database-staging") for name in names))

                # Damage the live store, then restore the backup over it.
                (vectors / "collections").mkdir(exist_ok=True)
                for child in vectors.rglob("*"):
                    if child.is_file():
                        child.unlink()
                backup_service.stage_restore_archive(archive)
                result = backup_service.apply_pending_restore()

            self.assertTrue(result["vectors_restored"])
            restored = vectors / "collections" / "local_notebook_text_segments_v1"
            self.assertTrue((restored / "partitions" / "_default" / "data" / "data_000001_000002.parquet").exists())
            self.assertIn("data_000001_000002", (restored / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse((vectors / "LOCK").exists())

    def test_backup_without_vectors_keeps_existing_store(self):
        import os
        import tempfile
        import zipfile
        from unittest import mock

        from services import backup_service

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            self._make_db(data_dir / "local_notebook.db", ["original"])
            vectors = data_dir / "milvus.db"
            self._make_vector_store(vectors)

            with mock.patch.dict(os.environ, self._env(data_dir)):
                archive = backup_service.create_backup_archive(include_vectors=False)
                names = zipfile.ZipFile(archive).namelist()
                self.assertFalse(any(name.startswith("milvus.db/") for name in names))

                backup_service.stage_restore_archive(archive)
                result = backup_service.apply_pending_restore()

            self.assertFalse(result["vectors_restored"])
            self.assertTrue(result["warnings"])
            self.assertTrue(
                (vectors / "collections" / "local_notebook_text_segments_v1" / "manifest.json").exists()
            )

    def test_restore_rejects_path_traversal(self):
        import os
        import tempfile
        import zipfile
        from unittest import mock

        from services import backup_service

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            self._make_db(data_dir / "local_notebook.db", ["original"])
            archive_path = Path(tmp) / "evil.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../escape.txt", "nope")
                archive.writestr("local_notebook.db", b"not a database")

            with mock.patch.dict(os.environ, self._env(data_dir)):
                with self.assertRaises(ValueError):
                    backup_service.stage_restore_archive(archive_path)


class _FakeFile:
    def __init__(self):
        self.id = "file-1"
        self.file_name = "Book - 2020 - Title.txt"
        self.file_type = "txt"
        self.project_id = "project-1"
        self.file_path = "book.txt"
        self.status = "pending"
        self.error_message = None
        self.processing_current = 0
        self.processing_total = None
        self.processing_message = None
        self.summary = None
        self.keywords = None
        self.updated_at = None


class _FakeProject:
    owner_user_id = "user-1"


class _FakeSegment:
    def __init__(self, index, content):
        self.segment_index = index
        self.content = content
        self.pos_start = 0
        self.pos_end = len(content)
        self.block_ids = ["block-1"]


class _FakeSplitResult:
    def __init__(self):
        self.segments = [_FakeSegment(0, "first segment"), _FakeSegment(1, "second segment")]
        self.warnings = []


class _FakeDB:
    def __init__(self, db_file):
        self.db_file = db_file
        self.events = []

    async def get(self, model, ident):
        if getattr(model, "__name__", "") == "File":
            return self.db_file
        return _FakeProject()

    async def execute(self, statement):
        self.events.append("execute")

    def add_all(self, items):
        self.events.append(("add_all", len(items)))

    async def flush(self):
        self.events.append("flush")

    async def rollback(self):
        self.events.append("rollback")


class ParseOrderTests(unittest.TestCase):
    """A failed embedding must not discard already paid-for summaries."""

    def test_segments_are_committed_before_embedding(self):
        db_file = _FakeFile()
        db = _FakeDB(db_file)
        blocks = [
            {
                "id": "block-1",
                "type": "paragraph",
                "content": "text",
                "position": {"start": 0, "end": 4},
                "page": 0,
            }
        ]

        @contextlib.asynccontextmanager
        async def fake_safe_session(session_factory):
            yield db

        async def fake_extract(file_type, file_path, **kwargs):
            return "text", blocks, []

        async def fake_describe(file_name, raw_images, **kwargs):
            return []

        async def fake_cancel_check(file_id):
            return None

        async def fake_commit(session):
            db.events.append("commit")

        async def fake_commit_progress(*args, **kwargs):
            return None

        async def fake_embedding_config():
            return "key", "http://embedding.local", "model", "key"

        async def fake_get_setting(key, default=None):
            return default

        async def fake_resolve_llm():
            return None

        async def fake_embed_texts(contents, **kwargs):
            db.events.append("embed")
            raise RuntimeError("embedding down")

        queued: list = []

        async def fake_queue_rebuild(file_id, output_language):
            queued.append((file_id, output_language))

        async def run():
            with mock.patch.object(tasks_module, "_safe_session", fake_safe_session), \
                 mock.patch.object(tasks_module, "_queue_vector_rebuild", fake_queue_rebuild), \
                 mock.patch.object(tasks_module, "_extract_text_and_blocks", fake_extract), \
                 mock.patch.object(tasks_module, "_describe_images", fake_describe), \
                 mock.patch.object(tasks_module, "_raise_if_file_cancelled", fake_cancel_check), \
                 mock.patch.object(tasks_module, "_shielded_commit", fake_commit), \
                 mock.patch.object(tasks_module, "_commit_file_progress", fake_commit_progress), \
                 mock.patch("services.vector_service.delete_by_file", lambda *args, **kwargs: None), \
                 mock.patch.object(config, "resolve_embedding_config", fake_embedding_config), \
                 mock.patch.object(config, "get_setting", fake_get_setting), \
                 mock.patch.object(summary_service, "_resolve_llm", fake_resolve_llm), \
                 mock.patch(
                     "services.segment_service.segment_service.split_text_with_warnings",
                     return_value=_FakeSplitResult(),
                 ), \
                 mock.patch("services.embedding_service.embed_texts", fake_embed_texts):
                # The content is stored, so the failure must not reach the queue (whose retry
                # would re-run every summary); a vector-only rebuild is queued instead.
                result = await tasks_module.parse_file_task(
                    {"session_factory": None}, db_file.id, "Turkish"
                )
                self.assertEqual(result.get("status"), "failed")
                self.assertTrue(result.get("content_saved"))

        asyncio.run(run())

        commit_index = db.events.index("commit")
        embed_index = db.events.index("embed")
        self.assertLess(commit_index, embed_index)
        self.assertTrue(
            any(event == ("add_all", 2) for event in db.events[:embed_index]),
            "segments must be persisted before the embedding call",
        )
        self.assertEqual(db_file.status, "failed")
        # The raw exception text stays in the log; the record shows only the kind of failure.
        self.assertTrue(db_file.error_message)
        self.assertNotIn("embedding down", db_file.error_message)
        self.assertEqual(queued, [(db_file.id, "Turkish")])


if __name__ == "__main__":
    unittest.main()
