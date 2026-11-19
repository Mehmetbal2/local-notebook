import asyncio
import fcntl
import logging
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Awaitable, Callable
from urllib.parse import urlparse

import httpx

import config
from paths import PROJECT_ROOT, get_data_dir
from utils.arabic_text import normalize_arabic_for_embedding
from utils.i18n import msg as ui_msg

logger = logging.getLogger("embedding_service")


def _embedding_pid_file() -> Path:
    run_dir = get_data_dir() / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / "embedding.pid"


def _embedding_port_file() -> Path:
    run_dir = get_data_dir() / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / "embedding.port"


def _running_port() -> int | None:
    port_file = _embedding_port_file()
    if not port_file.exists():
        return None
    try:
        return int(port_file.read_text().strip())
    except (ValueError, OSError):
        return None


def _embedding_lock_file() -> Path:
    run_dir = get_data_dir() / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / "embedding.lock"


def _embedding_log_file() -> Path:
    log_dir = get_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "embedding.log"


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _running_pid(pid_file: Path) -> int | None:
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
        return pid if _pid_is_alive(pid) else None
    except (ValueError, OSError):
        return None


def _is_port_bound(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def is_local_embedding_url(url: str) -> bool:
    if not url:
        return True
    try:
        parsed = urlparse(url if "://" in url else f"http://{url}")
        return (parsed.hostname or "") in ("127.0.0.1", "localhost", "0.0.0.0")
    except Exception:
        return False


def _default_local_model_dir() -> Path:
    return get_data_dir() / "models" / "bge-m3"


def _terminate_pid(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(20):
            time.sleep(0.15)
            if not _pid_is_alive(pid):
                break
        else:
            os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def _spawn_local_embedding_process(port: int) -> tuple[int | None, str | None]:
    lock_path = _embedding_lock_file()
    with open(lock_path, "w") as lock_fp:
        fcntl.flock(lock_fp, fcntl.LOCK_EX)
        try:
            pid_file = _embedding_pid_file()
            port_file = _embedding_port_file()
            existing_pid = _running_pid(pid_file)
            if existing_pid is not None:
                recorded_port = _running_port()
                if recorded_port == port or (recorded_port is None and _is_port_bound(port)):
                    if recorded_port is None:
                        port_file.write_text(f"{port}\n")
                    return existing_pid, None
                logger.info(
                    "Local embedding service PID %s is running on port %s, restarting on port %s...",
                    existing_pid,
                    recorded_port,
                    port,
                )
                _terminate_pid(existing_pid)
                pid_file.unlink(missing_ok=True)
                port_file.unlink(missing_ok=True)

            if _is_port_bound(port):
                return -1, None

            model_env = os.getenv("MODEL", "").strip()
            default_model_dir = _default_local_model_dir()
            if not model_env and not (default_model_dir / "config.json").exists():
                err = ui_msg("local_model_dir_missing", path=str(default_model_dir))
                logger.warning(err)
                return None, err

            server_dir = PROJECT_ROOT / "services" / "embedding"
            server_script = server_dir / "server.py"
            if not server_script.exists():
                err = f"Local embedding server script not found at {server_script}"
                logger.warning(err)
                return None, err

            venv_python = PROJECT_ROOT / ".venv" / "bin" / "python"
            python_bin = str(venv_python) if venv_python.exists() else sys.executable

            env = os.environ.copy()
            env["PORT"] = str(port)
            env.setdefault("LOCAL_NOTEBOOK_DATA_DIR", str(get_data_dir()))

            log_file = _embedding_log_file()
            with open(log_file, "ab") as log_fp, open(os.devnull, "rb") as devnull_fp:
                proc = subprocess.Popen(
                    [python_bin, "server.py"],
                    cwd=str(server_dir),
                    stdin=devnull_fp,
                    stdout=log_fp,
                    stderr=subprocess.STDOUT,
                    env=env,
                    start_new_session=True,
                )
            pid_file.write_text(f"{proc.pid}\n")
            port_file.write_text(f"{port}\n")
            logger.info("Started local embedding service (PID %s) on port %s", proc.pid, port)
            return proc.pid, None
        finally:
            fcntl.flock(lock_fp, fcntl.LOCK_UN)


def stop_local_embedding_service(respect_pinned: bool = True) -> None:
    if respect_pinned and os.getenv("START_EMBEDDING", "").strip() == "1":
        logger.info("Skipping stop_local_embedding_service because START_EMBEDDING=1 is set")
        return

    lock_path = _embedding_lock_file()
    with open(lock_path, "w") as lock_fp:
        fcntl.flock(lock_fp, fcntl.LOCK_EX)
        try:
            pid_file = _embedding_pid_file()
            port_file = _embedding_port_file()
            pid = _running_pid(pid_file)
            if pid is not None:
                logger.info("Stopping local embedding service (PID %s)...", pid)
                _terminate_pid(pid)
            try:
                pid_file.unlink(missing_ok=True)
                port_file.unlink(missing_ok=True)
            except OSError:
                pass
        finally:
            fcntl.flock(lock_fp, fcntl.LOCK_UN)


def _tail_embedding_log(lines: int = 5) -> str:
    log_file = _embedding_log_file()
    if not log_file.exists():
        return ""
    try:
        content = log_file.read_text(errors="replace").strip().splitlines()
        return " | ".join(content[-lines:]) if content else ""
    except Exception:
        return ""


async def ensure_local_embedding_service(
    base_url: str | None = None,
    wait: bool = True,
    timeout: float = 45.0,
) -> dict:
    default_port = int(os.getenv("EMBEDDING_PORT", "8001"))
    clean_base = (base_url or "").strip().rstrip("/")
    if not clean_base:
        clean_base = config.default_local_embedding_url()
    if clean_base.endswith("/embeddings"):
        clean_base = clean_base[: -len("/embeddings")]

    health_url = f"{clean_base}/health"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(health_url)
            if resp.status_code == 200:
                return {"ok": True, "base_url": clean_base, **resp.json()}
    except Exception as exc:
        if not is_local_embedding_url(clean_base):
            return {"ok": False, "base_url": clean_base, "error": str(exc)}

    if not is_local_embedding_url(clean_base):
        return {"ok": False, "base_url": clean_base, "error": f"Remote local service unreachable: {clean_base}"}

    parsed = urlparse(clean_base)
    port = parsed.port or default_port
    pid, spawn_err = await asyncio.to_thread(_spawn_local_embedding_process, port)
    if pid is None:
        return {"ok": False, "base_url": clean_base, "error": spawn_err or "Could not start local embedding server"}

    if not wait:
        return {"ok": True, "starting": True, "base_url": clean_base, "pid": pid}

    deadline = time.monotonic() + timeout
    last_err = "Service is starting"
    while time.monotonic() < deadline:
        await asyncio.sleep(0.4)
        if pid > 0 and not _pid_is_alive(pid):
            log_tail = await asyncio.to_thread(_tail_embedding_log, 3)
            return {
                "ok": False,
                "base_url": clean_base,
                "error": log_tail or "Local embedding process exited unexpectedly",
            }
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(health_url)
                if resp.status_code == 200:
                    return {"ok": True, "base_url": clean_base, **resp.json()}
        except Exception as exc:
            last_err = str(exc)

    return {"ok": False, "base_url": clean_base, "error": last_err}


async def _get_config() -> tuple[str, str, str, str]:
    mode, base_url, model, api_key = await config.resolve_embedding_config()

    if not base_url:
        raise RuntimeError(
            "Embedding base URL is not configured. Set base_url in Settings > Embedding. "
            "Docker deployments cannot use localhost; see the Settings hint."
        )
    # API mode (custom) needs an explicit model;
    # in local mode the service ignores the model field (it uses its MODEL env at startup), so an empty string is passed through.
    if mode == "api" and not model:
        raise RuntimeError(
            "Embedding model is not configured. Select a model in Settings > Embedding."
        )
    if not api_key:
        api_key = "local"

    return mode, base_url.rstrip("/"), model, api_key


EMBED_BATCH_SIZE = 10


# A provider that is briefly overloaded (429/5xx) or slow should not fail a whole file:
# a failed parse is retried by the task queue from the start, which repeats every
# (paid) LLM summary call. Retry the single batch instead.
EMBED_MAX_ATTEMPTS = max(1, int(os.getenv("EMBED_MAX_ATTEMPTS", "3")))
_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


async def _post_embedding_batch(
    url: str,
    payload: dict,
    headers: dict,
    mode: str,
    base_url: str,
    batch_no: int,
) -> httpx.Response:
    last_error: Exception | None = None
    local_restart_tried = False
    for attempt in range(1, EMBED_MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, json=payload, headers=headers)
            logger.info(f"[embed] batch {batch_no} status={resp.status_code}")
            resp.raise_for_status()
            return resp
        except httpx.ConnectError:
            if mode == "local" and is_local_embedding_url(base_url) and not local_restart_tried:
                local_restart_tried = True
                started = await ensure_local_embedding_service(base_url, wait=True)
                if not started.get("ok"):
                    raise RuntimeError(
                        f"Cannot connect to the local embedding service ({base_url}): {started.get('error', '')}"
                    )
                last_error = RuntimeError(f"Local embedding service restarted ({base_url})")
                continue  # the service is up now; try again without waiting
            last_error = RuntimeError(
                f"Cannot connect to the embedding service ({base_url}). "
                "Configure the embedding service address in Settings first. "
                "For local mode, start it with: cd services/embedding && python server.py"
            )
        except httpx.ReadTimeout:
            last_error = RuntimeError(
                f"Embedding service timed out ({base_url}). "
                "Check whether the embedding service is running correctly."
            )
        except httpx.HTTPStatusError as e:
            error = RuntimeError(
                f"Embedding service returned error {e.response.status_code}: {e.response.text}"
            )
            if e.response.status_code not in _RETRYABLE_STATUS:
                raise error
            last_error = error
        if attempt < EMBED_MAX_ATTEMPTS:
            delay = min(10.0, 1.5 * 2 ** (attempt - 1))
            logger.warning(
                "[embed] batch %s failed (%s); retrying in %.1fs (%d/%d)",
                batch_no,
                last_error,
                delay,
                attempt,
                EMBED_MAX_ATTEMPTS,
            )
            await asyncio.sleep(delay)
    assert last_error is not None
    raise last_error


async def embed_texts(
    texts: list[str],
    progress_callback: Callable[[int], Awaitable[None]] | None = None,
) -> list[list[float]]:
    if not texts:
        return []

    mode, base_url, model, api_key = await _get_config()

    batch_size = EMBED_BATCH_SIZE

    clean_base = base_url.rstrip("/")
    if clean_base.endswith("/embeddings"):
        url = clean_base
    else:
        url = f"{clean_base}/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    logger.info(f"[embed] mode={mode} url={url} model={model} input_count={len(texts)} batch_size={batch_size}")

    all_results: list[list[float]] = [[] for _ in texts]

    for batch_start in range(0, len(texts), batch_size):
        batch = [
            normalize_arabic_for_embedding(text)
            for text in texts[batch_start:batch_start + batch_size]
        ]

        payload: dict = {"model": model, "input": batch}
        resp = await _post_embedding_batch(
            url, payload, headers, mode, base_url, batch_start // batch_size + 1
        )

        data = resp.json()
        items = sorted(data["data"], key=lambda x: x["index"])
        for i, item in enumerate(items):
            all_results[batch_start + i] = item["embedding"]
        if progress_callback:
            await progress_callback(len(batch))

    return all_results


async def embed_single(text: str) -> list[float]:
    results = await embed_texts([text])
    return results[0]


def embed_single_sync(text: str) -> list[float]:
    return asyncio.run(embed_single(text))


async def health_check() -> dict:
    mode, base_url, model, _ = await _get_config()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{base_url}/health")
            if resp.status_code == 200:
                return {"ok": True, "mode": mode, "model": model, "detail": resp.json()}
            return {"ok": False, "mode": mode, "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"ok": False, "mode": mode, "error": str(e)}
