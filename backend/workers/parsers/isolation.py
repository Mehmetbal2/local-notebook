"""Run a document parser in a child process with a memory and time limit.

Parsing libraries (MuPDF, EbookLib, BeautifulSoup) expand compressed input in
memory, and a crafted file can always find one more way to make them expand
far more than its size suggests. The size checks in front of each parser stop
the known ways; this is the backstop for the rest: the parser runs in its own
process, which is killed when its memory (resident set) or running time passes
the limit, so the backend process and the other users are unaffected.
"""
from __future__ import annotations

import logging
import os
import pickle
import signal
import subprocess
import sys
import threading
import time
import traceback
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


PARSER_MAX_MEMORY_MB = _env_int("PARSER_MAX_MEMORY_MB", 2048)
PARSER_TIMEOUT_SECONDS = _env_int("PARSER_TIMEOUT_SECONDS", 1800)
# Set PARSER_ISOLATION=0 to parse in the backend process (debugging only).
PARSER_ISOLATION = os.getenv("PARSER_ISOLATION", "1").strip().lower() not in ("0", "false", "no", "off")

_POLL_SECONDS = 0.1


class ParserLimitExceeded(RuntimeError):
    """The parser process went over its memory or time limit; the message is user-facing."""


def _rss_bytes(pid: int) -> Optional[int]:
    """Resident memory of a process, or None when it cannot be read."""
    try:
        with open(f"/proc/{pid}/status", "rb") as status:
            for line in status:
                if line.startswith(b"VmRSS:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    try:
        import psutil  # optional

        return psutil.Process(pid).memory_info().rss
    except Exception:
        pass
    try:
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, timeout=2)
        return int(out.stdout.strip()) * 1024 if out.stdout.strip() else None
    except Exception:
        return None


def _child_main() -> None:
    """Entry point of the child: read (func, args, memory) from stdin, write the outcome to the result pipe."""
    result_fd = int(sys.argv[1])
    func, args, memory_bytes = pickle.loads(sys.stdin.buffer.read())
    try:
        import resource

        # A hard cap where the system enforces it (Linux). The parent watches the
        # resident size as well, because macOS ignores RLIMIT_AS.
        cap = memory_bytes * 4
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    except Exception:
        pass
    try:
        outcome = ("ok", func(*args))
    except MemoryError:
        outcome = ("memory", None)
    except BaseException as exc:  # sent back and raised in the parent
        logger.debug("isolated parser failed: %s", traceback.format_exc())
        outcome = ("error", (type(exc).__module__, type(exc).__name__, str(exc)))
    with os.fdopen(result_fd, "wb") as out:
        pickle.dump(outcome, out, protocol=pickle.HIGHEST_PROTOCOL)


def _rebuild_error(module: str, name: str, message: str) -> BaseException:
    """The parser's exception type when it is a built-in or one of ours, else RuntimeError."""
    if module == "builtins" or module.startswith(("workers.", "utils.")):
        try:
            cls = getattr(sys.modules.get(module) or __import__(module, fromlist=[name]), name)
            if isinstance(cls, type) and issubclass(cls, Exception):
                return cls(message)
        except Exception:
            pass
    return RuntimeError(message)


def run_isolated(
    func: Callable[..., Any],
    *args: Any,
    memory_mb: Optional[int] = None,
    timeout: Optional[float] = None,
) -> Any:
    """Call `func(*args)` in a child process and return its result.

    `func` must be a module-level function and its arguments and result
    picklable. Exceptions raised by `func` are raised here again (as the same
    class for built-in and this project's own exceptions, RuntimeError
    otherwise). When the child passes the memory or time limit it is killed and
    ParserLimitExceeded is raised.

    The child is a fresh interpreter started with `-c`, so nothing of the
    backend's own entry module runs in it.
    """
    from utils.i18n import msg as ui_msg

    if not PARSER_ISOLATION or os.name != "posix":
        return func(*args)
    memory_bytes = (memory_mb or PARSER_MAX_MEMORY_MB) * 1024 * 1024
    limit_seconds = timeout or PARSER_TIMEOUT_SECONDS
    deadline = time.monotonic() + limit_seconds
    payload = pickle.dumps((func, args, memory_bytes), protocol=pickle.HIGHEST_PROTOCOL)

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p and os.path.isdir(p))
    read_fd, write_fd = os.pipe()
    try:
        process = subprocess.Popen(
            [sys.executable, "-c", "from workers.parsers.isolation import _child_main; _child_main()", str(write_fd)],
            stdin=subprocess.PIPE,
            pass_fds=(write_fd,),
            env=env,
            cwd=os.getcwd(),
        )
    finally:
        os.close(write_fd)

    received: dict = {}

    def read_result() -> None:
        with os.fdopen(read_fd, "rb") as source:
            received["data"] = source.read()

    def write_input() -> None:
        try:
            process.stdin.write(payload)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    reader = threading.Thread(target=read_result, daemon=True)
    writer = threading.Thread(target=write_input, daemon=True)
    reader.start()
    writer.start()

    reason = None
    while True:
        reader.join(_POLL_SECONDS)
        if not reader.is_alive():
            break
        rss = _rss_bytes(process.pid)
        if rss is not None and rss > memory_bytes:
            reason = "memory"
            break
        if time.monotonic() > deadline:
            reason = "time"
            break
    if process.poll() is None:
        if reason is None:
            try:
                process.wait(10)
            except subprocess.TimeoutExpired:
                pass
        if process.poll() is None:
            process.kill()
    process.wait()
    reader.join(5)

    if reason is None:
        data = received.get("data") or b""
        if data:
            status, result = pickle.loads(data)
            if status == "ok":
                return result
            if status == "error":
                raise _rebuild_error(*result)
            reason = "memory"
        elif process.returncode in (-signal.SIGKILL, 137):
            reason = "memory"  # killed by the system, usually for memory
        else:
            logger.warning("Parser process exited with code %s and no result", process.returncode)
            raise RuntimeError(ui_msg("parser_failed", code=process.returncode))
    logger.warning("Parser process stopped: %s limit (%s)", reason, getattr(func, "__name__", func))
    if reason == "time":
        raise ParserLimitExceeded(ui_msg("parser_time_limit", limit=max(1, int(limit_seconds) // 60)))
    raise ParserLimitExceeded(ui_msg("parser_memory_limit", limit=memory_bytes // (1024 * 1024)))
