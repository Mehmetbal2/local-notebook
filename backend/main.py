import os
import sys
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


@asynccontextmanager
async def lifespan(app: FastAPI):
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
        from sqlalchemy import select
        from dependencies.auth import hash_password
        from models.user import User

        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD", "admin")
        result = await db.execute(select(User).where(User.username == admin_username))
        admin_user = result.scalar_one_or_none()
        if admin_user is None:
            admin_user = User(
                username=admin_username,
                password_hash=hash_password(admin_password),
                role="admin",
            )
            db.add(admin_user)
            await db.commit()
            logger.info("Initial admin user is ready: %s", admin_username)
        elif admin_user.role != "admin":
            admin_user.role = "admin"
            await db.commit()
            logger.info("Initial admin user is ready: %s", admin_username)

        await config.load_settings(db)
    logger.info("Settings cache loaded")

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
        title="local-Notebook",
        description="Local-first knowledge base and chat for paper reading",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
        return {"status": "ok", "version": "0.1.0"}

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
