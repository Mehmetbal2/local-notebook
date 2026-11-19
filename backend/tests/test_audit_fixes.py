"""Regression tests for the problems found in the 19 Nov 2026 audit."""

import asyncio
import inspect
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(BACKEND_DIR / "packages") not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR / "packages"))

import httpx  # noqa: E402

from services import embedding_service  # noqa: E402
from services import web_discovery  # noqa: E402
from workers import tasks as tasks_module  # noqa: E402


class ProjectSummaryRefreshTests(unittest.TestCase):
    def test_refresh_task_resolves_the_llm_helper(self):
        """refresh_project_summary_task used _resolve_llm without importing it (NameError)."""
        source = inspect.getsource(tasks_module.refresh_project_summary_task)
        self.assertIn("from services.summary_service import _resolve_llm", source)


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}
        self.text = "busy" if status >= 400 else ""

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://x/embeddings")
            raise httpx.HTTPStatusError("error", request=request, response=self)


class _Client:
    def __init__(self, responses):
        self._responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        return self._responses.pop(0)


class EmbeddingRetryTests(unittest.TestCase):
    def _run(self, responses):
        async def no_sleep(_):
            return None

        with mock.patch.object(embedding_service.httpx, "AsyncClient", lambda **kw: _Client(responses)), \
             mock.patch.object(embedding_service.asyncio, "sleep", no_sleep):
            return asyncio.run(
                embedding_service._post_embedding_batch(
                    "http://x/embeddings", {}, {}, "api", "http://x", 1
                )
            )

    def test_transient_overload_is_retried(self):
        ok = _Resp(200, {"data": []})
        resp = self._run([_Resp(503), _Resp(429), ok])
        self.assertIs(resp, ok)

    def test_client_errors_are_not_retried(self):
        responses = [_Resp(400), _Resp(200)]
        with self.assertRaises(RuntimeError):
            self._run(responses)
        self.assertEqual(len(responses), 1, "a 400 must fail at once")


class WebDiscoveryBudgetTests(unittest.TestCase):
    def test_query_expansion_budget_fits_a_slow_provider(self):
        # Phase 2 runs after results are shown; 15 s made it time out on every call.
        if "WEB_DISCOVERY_QUERY_TIMEOUT" not in os.environ:
            self.assertGreaterEqual(web_discovery.QUERY_LLM_TIMEOUT, 45)


if __name__ == "__main__":
    unittest.main()
