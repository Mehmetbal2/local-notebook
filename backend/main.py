import os
import re
import sys
import time
from pathlib import Path

os.environ.setdefault("GRPC_DNS_RESOLVER", "native")
os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
sys.path.insert(0, os.path.join(_BACKEND_DIR, "packages"))

import asyncio
import logging
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from arq.worker import Worker
from dotenv import load_dotenv
from fastapi import FastAPI

from version import __version__
from fastapi.middleware.cors import CORSMiddleware

from paths import BACKEND_DIR, PROJECT_ROOT, get_data_dir, get_upload_dir

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(BACKEND_DIR / ".env")

_models_cache_dir = get_data_dir() / "models"
os.environ.setdefault("HF_HOME", str(_models_cache_dir / "huggingface"))
os.environ.setdefault("MODELSCOPE_CACHE", str(_models_cache_dir / "modelscope"))
os.environ.setdefault("TORCH_HOME", str(_models_cache_dir / "torch"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("local_notebook")


class _MilvusLiteNoiseFilter(logging.Filter):
    """Drop the gRPC error Milvus Lite logs each time an index is created.

    Milvus Lite does not implement AllocTimestamp; pymilvus calls it while waiting for a new
    index and carries on without it. The full traceback landed in the log (and in the admin
    diagnostics) as an ERROR although nothing failed. Other gRPC errors are kept.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        if not isinstance(exc, NotImplementedError):
            return True
        tb = record.exc_info[2]
        while tb is not None:
            if tb.tb_frame.f_code.co_name == "AllocTimestamp":
                return False
            tb = tb.tb_next
        return True


logging.getLogger("grpc._server").addFilter(_MilvusLiteNoiseFilter())


def _generate_admin_password() -> str:
    import secrets

    return secrets.token_urlsafe(12)


def _write_admin_password_file(password: str) -> str | None:
    """Persist a generated password with owner-only permissions so it never lands in logs."""
    try:
        path = get_data_dir() / "admin_password.txt"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(password + "\n")
        return str(path)
    except Exception:
        logger.exception("Could not write the generated admin password file")
        return None


async def _ensure_admin_user(db) -> None:
    """Create the admin account without ever leaving the known default password in place."""
    from sqlalchemy import select

    from dependencies.auth import hash_password, verify_password
    from models.user import User

    admin_username = (os.getenv("ADMIN_USERNAME") or "admin").strip() or "admin"
    env_password = (os.getenv("ADMIN_PASSWORD") or "").strip()
    env_is_insecure = not env_password or env_password.lower() == "admin"

    result = await db.execute(select(User).where(User.username == admin_username))
    admin_user = result.scalar_one_or_none()

    if admin_user is None:
        # A configured strong password is honoured; the default or an unset value is not.
        password = None if env_is_insecure else env_password
        generated = password is None
        if generated:
            password = _generate_admin_password()
            path = _write_admin_password_file(password)
            if path:
                logger.warning(
                    "Created the initial admin user '%s' with a generated password. "
                    "Read it from %s and delete that file after signing in.",
                    admin_username,
                    path,
                )
            else:
                logger.warning("Generated admin password for '%s': %s", admin_username, password)
        admin_user = User(
            username=admin_username,
            password_hash=hash_password(password),
            role="admin",
        )
        db.add(admin_user)
        await db.commit()
        if not generated:
            logger.info("Initial admin user is ready: %s", admin_username)
        return

    if admin_user.role != "admin":
        admin_user.role = "admin"
        await db.commit()
        logger.info("Initial admin user is ready: %s", admin_username)

    if verify_password("admin", admin_user.password_hash):
        if env_is_insecure:
            password = _generate_admin_password()
        else:
            # An explicit strong ADMIN_PASSWORD in the environment wins over a random one.
            password = env_password
        admin_user.password_hash = hash_password(password)
        await db.commit()
        if env_is_insecure:
            path = _write_admin_password_file(password)
            if path:
                logger.warning(
                    "The admin account still used the default password 'admin'; it has been rotated. "
                    "Read the new password from %s and delete that file after signing in.",
                    path,
                )
            else:
                logger.warning("Rotated admin password for '%s': %s", admin_username, password)
        else:
            logger.warning(
                "The admin account still used the default password 'admin'; it now uses ADMIN_PASSWORD "
                "from the environment."
            )


def _cors_ports(frontend_port: str, extra_ports: str = "") -> list[str]:
    """The frontend's own port, the Vite dev-server default, and any listed in CORS_ALLOW_PORTS."""
    ports: list[str] = []
    for raw in [frontend_port or "8080", "5173", *extra_ports.split(",")]:
        port = raw.strip()
        if port.isdigit() and 0 < int(port) < 65536 and port not in ports:
            ports.append(port)
    return ports


def _cors_origin_regex(frontend_port: str, extra_ports: str = "") -> str:
    """Allow the app's own origin on localhost and private LAN addresses only."""
    ports = "|".join(re.escape(port) for port in _cors_ports(frontend_port, extra_ports))
    return (
        r"^https?://(?:"
        r"localhost|127\.0\.0\.1|\[::1\]|"
        r"10(?:\.\d{1,3}){3}|"
        r"192\.168(?:\.\d{1,3}){2}|"
        r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}"
        r"):(?:" + ports + r")$"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.started_at = time.time()

    # A staged restore must be applied before any database or Milvus connection opens.
    try:
        from services.backup_service import apply_pending_restore

        applied = apply_pending_restore()
        if applied:
            logger.warning(
                "Applied a staged restore; the previous data was moved to %s",
                applied.get("safety"),
            )
            for warning in applied.get("warnings") or []:
                logger.warning("Restore note: %s", warning)
    except Exception:
        logger.exception("Could not apply a staged restore")

    # Old pre-restore copies, unfetched backup archives and replaced restore uploads.
    try:
        from services.backup_service import prune_backups

        prune_backups()
    except Exception:
        logger.warning("Could not clean up old backup files", exc_info=True)

    from database import engine, Base, ensure_runtime_schema
    import models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await ensure_runtime_schema(conn, logger)
    logger.info("Database tables verified")

    from database import AsyncSessionLocal
    import config
    from services.feature_agent_trace_service import cleanup_expired_feature_agent_traces

    await cleanup_expired_feature_agent_traces()

    async with AsyncSessionLocal() as db:
        await _ensure_admin_user(db)
        await config.load_settings(db)
    logger.info("Settings cache loaded")

    try:
        if await config.get_setting("embedding_source", "local") == "local":
            from services.embedding_service import ensure_local_embedding_service
            emb_local_url = (await config.get_setting("embedding_local_url", "")).strip() or config.default_local_embedding_url()
            app.state.embedding_startup_task = asyncio.create_task(
                ensure_local_embedding_service(emb_local_url, wait=False)
            )
    except Exception:
        logger.exception("Could not auto-start local embedding service")

    # One-time repair of notes saved from chat with citations resolved against the wrong turn.
    try:
        from routes.feature_routes import CHAT_NOTE_REPAIR_SETTING, repair_chat_note_citations

        if await config.get_setting(CHAT_NOTE_REPAIR_SETTING, "") != "1":
            async with AsyncSessionLocal() as db:
                repaired = await repair_chat_note_citations(db)
                await config.set_setting(CHAT_NOTE_REPAIR_SETTING, "1", db)
            logger.info("Chat note citations checked; %d note(s) corrected", repaired)
    except Exception:
        logger.exception("Could not repair chat note citations")

    upload_dir = get_upload_dir()
    os.makedirs(upload_dir, exist_ok=True)

    try:
        from services.ocr_client import cleanup_ocr_cache

        removed = await asyncio.to_thread(cleanup_ocr_cache)
        if removed:
            logger.info(f"Removed {removed} old OCR cache folder(s)")
    except Exception:
        logger.exception("Could not clean the OCR cache")

    redis_url = os.getenv("REDIS_URL", "memory://").strip()
    worker = None
    worker_task = None
    local_queue = None

    if redis_url.startswith(("redis://", "rediss://", "unix://")):
        try:
            app.state.redis = await create_pool(RedisSettings.from_dsn(redis_url))
            logger.info(f"Redis connected: {redis_url}")
        except Exception as exc:
            logger.info(
                f"External Redis unavailable ({exc}) — switching to embedded local task queue"
            )
            app.state.redis = None
    else:
        app.state.redis = None

    from workers.tasks import WorkerSettings

    if app.state.redis is not None:
        worker = Worker(
            functions=WorkerSettings.functions,
            on_startup=WorkerSettings.on_startup,
            on_shutdown=WorkerSettings.on_shutdown,
            redis_settings=RedisSettings.from_dsn(redis_url),
            max_jobs=WorkerSettings.max_jobs,
            job_timeout=WorkerSettings.job_timeout,
            max_tries=WorkerSettings.max_tries,
            retry_jobs=WorkerSettings.retry_jobs,
            handle_signals=False,
        )
        worker_task = asyncio.create_task(worker.async_run())
        logger.info("Embedded ARQ worker started")
    else:
        from services.local_queue import LocalTaskQueue, set_active_local_queue

        local_queue = LocalTaskQueue(
            functions=WorkerSettings.functions,
            on_startup=WorkerSettings.on_startup,
            on_shutdown=WorkerSettings.on_shutdown,
            max_jobs=WorkerSettings.max_jobs,
            max_tries=WorkerSettings.max_tries,
            retry_delay=WorkerSettings.retry_delay,
        )
        set_active_local_queue(local_queue)
        await local_queue.start()
        app.state.redis = local_queue

    yield

    if local_queue is not None:
        from services.local_queue import set_active_local_queue
        set_active_local_queue(None)
        await local_queue.aclose()
    else:
        if worker and worker_task and not worker_task.done():
            if worker.main_task and not worker.main_task.done():
                worker.main_task.cancel()
            try:
                await asyncio.wait_for(worker_task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                worker_task.cancel()
            logger.info("Embedded ARQ worker stopped")
        if app.state.redis:
            await app.state.redis.aclose()
    await engine.dispose()
    logger.info("Shutdown complete")


class UILanguageMiddleware:
    """Make the interface language sent by the frontend (X-UI-Language, falling back
    to Accept-Language) available to `utils.i18n.msg` for the whole request,
    including streamed responses."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        from utils.i18n import reset_language, set_language

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        token = set_language(headers.get("x-ui-language") or headers.get("accept-language"))
        try:
            await self.app(scope, receive, send)
        finally:
            reset_language(token)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Local Notebook",
        description="Local-first research notebook with passage-level citations",
        version=__version__,
        lifespan=lifespan,
    )

    # The app is served from its own origin (frontend port) and may be opened from another
    # device on the LAN. Allow those origins, not "any origin with credentials".
    cors_kwargs = {
        "allow_origin_regex": _cors_origin_regex(
            os.getenv("FRONTEND_PORT") or "8080", os.getenv("CORS_ALLOW_PORTS") or ""
        ),
        "allow_credentials": True,
        "allow_methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        "allow_headers": ["*"],
    }
    extra_origins = [
        origin.strip()
        for origin in (os.getenv("CORS_ALLOW_ORIGINS") or "").split(",")
        if origin.strip()
    ]
    if extra_origins:
        cors_kwargs["allow_origins"] = extra_origins
    app.add_middleware(CORSMiddleware, **cors_kwargs)

    app.add_middleware(UILanguageMiddleware)

    from routes import (
        admin_router,
        auth_router,
        chat_router,
        direct_file_router,
        feature_router,
        file_router,
        project_router,
        session_router,
        search_router,
        settings_router,
        web_source_router,
        workflow_router,
    )

    app.include_router(auth_router,        prefix="/api")
    app.include_router(admin_router,       prefix="/api")
    app.include_router(settings_router,    prefix="/api")
    app.include_router(project_router,     prefix="/api")
    app.include_router(file_router,        prefix="/api")
    app.include_router(direct_file_router, prefix="/api")
    app.include_router(feature_router,     prefix="/api")
    app.include_router(session_router,     prefix="/api")
    app.include_router(chat_router,        prefix="/api")
    app.include_router(workflow_router,    prefix="/api")
    app.include_router(web_source_router,  prefix="/api")
    app.include_router(search_router,      prefix="/api")

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/health/redis", tags=["health"])
    async def health_redis() -> dict:
        if app.state.redis is None:
            return {"status": "unavailable"}
        try:
            await app.state.redis.ping()
            return {"status": "ok"}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("DEBUG", "false").lower() == "true",
    )
