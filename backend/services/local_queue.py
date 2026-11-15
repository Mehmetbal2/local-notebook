import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

logger = logging.getLogger("local_notebook.queue")


@dataclass
class LocalJob:
    job_id: str


class LocalTaskQueue:
    """In-process async task queue compatible with the ARQ pool interface used by local-Notebook."""

    def __init__(
        self,
        functions: list[Any],
        on_startup: Callable[[dict], Any] | None = None,
        on_shutdown: Callable[[dict], Any] | None = None,
        max_jobs: int = 4,
        max_tries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        self.ctx: dict[str, Any] = {"redis": self}
        self._on_startup = on_startup
        self._on_shutdown = on_shutdown
        self._semaphore = asyncio.Semaphore(max(1, max_jobs))
        self._default_max_tries = max(1, max_tries)
        self._retry_delay = max(0.1, retry_delay)
        self._functions: dict[str, tuple[Callable, int]] = {}
        self._active_tasks: set[asyncio.Task] = set()
        self._jobs: dict[str, asyncio.Task] = {}
        self._cancelled_jobs: set[str] = set()
        self._closed = False

        for item in functions:
            if hasattr(item, "coroutine") and hasattr(item, "name"):
                fn = item.coroutine
                name = item.name or fn.__name__
                tries = getattr(item, "max_tries", None) or self._default_max_tries
            else:
                fn = item
                name = fn.__name__
                tries = self._default_max_tries
            self._functions[name] = (fn, tries)

    async def start(self) -> None:
        if self._on_startup is not None:
            await self._on_startup(self.ctx)
        logger.info("Embedded local task queue started (functions=%s)", list(self._functions.keys()))

    async def enqueue_job(self, function_name: str, *args: Any, **kwargs: Any) -> LocalJob:
        if self._closed:
            raise RuntimeError("Task queue is closed")
        if function_name not in self._functions:
            raise ValueError(f"Unknown task function: {function_name}")

        job_id = kwargs.pop("_job_id", None) or uuid4().hex
        task = asyncio.create_task(
            self._execute(job_id, function_name, args, kwargs),
            name=f"local-job-{function_name}-{job_id[:8]}",
        )
        self._active_tasks.add(task)
        self._jobs[job_id] = task

        def _forget(done: asyncio.Task, key: str = job_id) -> None:
            self._active_tasks.discard(done)
            if self._jobs.get(key) is done:
                self._jobs.pop(key, None)
            self._cancelled_jobs.discard(key)

        task.add_done_callback(_forget)
        return LocalJob(job_id=job_id)

    def cancel_job(self, job_id: str | None) -> bool:
        """Cancel a queued or running job. Returns False when the job is unknown or already finished."""
        task = self._jobs.get(job_id or "")
        if task is None or task.done():
            return False
        self._cancelled_jobs.add(job_id or "")
        task.cancel()
        return True

    async def wait_job(self, job_id: str | None, timeout: float = 5.0) -> None:
        """Wait (bounded) for a job to finish, e.g. after cancel_job, so its cleanup has run."""
        task = self._jobs.get(job_id or "")
        if task is None or task.done():
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            pass

    async def _execute(
        self,
        job_id: str,
        function_name: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        fn, max_tries = self._functions[function_name]
        async with self._semaphore:
            for attempt in range(1, max_tries + 1):
                try:
                    job_ctx = dict(self.ctx)
                    job_ctx["job_id"] = job_id
                    job_ctx["job_try"] = attempt
                    return await fn(job_ctx, *args, **kwargs)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if job_id in self._cancelled_jobs:
                        # A job the user cancelled must not start over.
                        logger.info("Local task %s (job_id=%s) stopped after cancellation: %s", function_name, job_id, exc)
                        return None
                    if attempt >= max_tries:
                        logger.exception(
                            "Local task %s (job_id=%s) failed after %d attempt(s): %s",
                            function_name,
                            job_id,
                            attempt,
                            exc,
                        )
                        return None
                    logger.warning(
                        "Local task %s (job_id=%s) attempt %d/%d failed (%s), retrying...",
                        function_name,
                        job_id,
                        attempt,
                        max_tries,
                        exc,
                    )
                    await asyncio.sleep(self._retry_delay * attempt)

    async def ping(self) -> bool:
        return not self._closed

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._active_tasks:
            for task in list(self._active_tasks):
                task.cancel()
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
        if self._on_shutdown is not None:
            try:
                await self._on_shutdown(self.ctx)
            except Exception as exc:
                logger.debug("Error during local queue shutdown: %s", exc)
        logger.info("Embedded local task queue stopped")


_active_local_queue: LocalTaskQueue | None = None


def get_active_local_queue() -> LocalTaskQueue | None:
    return _active_local_queue


def set_active_local_queue(queue: LocalTaskQueue | None) -> None:
    global _active_local_queue
    _active_local_queue = queue

