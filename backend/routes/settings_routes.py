import logging
import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

import config
from dependencies.auth import get_current_admin, get_current_user
from dependencies.database import get_db
from schemas.settings import (
    SETTING_DEFAULTS,
    SETTING_KEYS,
    SettingsResponse,
    SettingsUpdate,
)
from kosong._generate import generate
from kosong.chat_provider import ChatProviderError
from kosong.message import Message
from models.user import User
from services.llm_provider import create_llm_chat_provider, normalize_llm_api_format
from services.usage_service import record_model_usage
from utils.errors import public_error_message
from utils.service_url import service_url_problem
from utils.i18n import msg as ui_msg

router = APIRouter(prefix="/settings", tags=["settings"])
logger = logging.getLogger("settings_routes")


async def _full_settings() -> dict[str, str | None]:
    import os
    cached = config.get_all_cached()
    merged: dict[str, str | None] = {}
    for key in SETTING_KEYS:
        merged[key] = cached.get(key) or os.getenv(key.upper()) or SETTING_DEFAULTS.get(key) or None
    return merged


@router.get("", response_model=SettingsResponse)
async def get_settings(
    _: str = Depends(get_current_admin),
) -> SettingsResponse:
    all_settings = await _full_settings()
    return SettingsResponse(settings=all_settings)


async def _require_no_active_files(db: AsyncSession) -> None:
    from sqlalchemy import select, func
    from models.file import File

    active_result = await db.execute(
        select(func.count()).select_from(File).where(File.status.in_(["pending", "processing"]))
    )
    active_count = active_result.scalar() or 0
    if active_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ui_msg("embedding_active_files_blocked", count=active_count),
        )


def _output_language_for(db_file) -> str | None:
    """The language a file was processed in, else the language of the current request."""
    from utils.i18n import current_language

    stored = (getattr(db_file, "output_language", None) or "").strip()
    if stored:
        return stored
    return {"tr": "Turkish", "zh": "Chinese"}.get(current_language(), "English")


async def _queue_reembed_all(db: AsyncSession, queue) -> int:
    """Mark every parsed file for a vector rebuild and queue it. Returns how many were queued.

    Rebuilding uses the segments and summaries already stored in SQLite, so no OCR or LLM
    call is repeated. Called after the shared collections were dropped.
    """
    from uuid import uuid4
    from sqlalchemy import select
    from models.file import File
    from models.segment import Segment

    seg_file_ids = select(Segment.file_id).distinct()
    result = await db.execute(
        select(File).where(
            File.id.in_(seg_file_ids),
            File.status.in_(["ready", "failed", "cancelled"]),
        )
    )
    files = list(result.scalars().all())
    to_enqueue: list[tuple[str, str, str | None]] = []
    for f in files:
        new_job_id = uuid4().hex
        f.status = "pending"
        f.job_id = new_job_id
        f.error_message = None
        f.processing_current = 0
        f.processing_total = None
        f.processing_message = ui_msg("reembedding_vectors")
        to_enqueue.append((f.id, new_job_id, _output_language_for(f)))
    await db.commit()

    enqueued = 0
    for fid, new_job_id, language in to_enqueue:
        try:
            await queue.enqueue_job("reembed_file_task", fid, language, _job_id=new_job_id)
            enqueued += 1
        except Exception as exc:
            logger.warning("Could not enqueue reembed_file_task for %s: %s", fid, exc)
    return enqueued


@router.patch("", response_model=SettingsResponse)
async def update_settings(
    body: SettingsUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> SettingsResponse:
    filtered = {
        k: v for k, v in body.settings.items() if k in SETTING_KEYS
    }
    if not filtered:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No valid setting keys provided.",
        )

    old_source = await config.get_setting("embedding_source", "")
    new_source = filtered.get("embedding_source", old_source)
    old_model = await config.get_setting("embedding_model", "")
    new_model = filtered.get("embedding_model", old_model)
    source_changed = bool(old_source and new_source and new_source != old_source)
    model_changed = bool(
        new_source == "custom"
        and "embedding_model" in filtered
        and (old_model or "").strip() != (new_model or "").strip()
    )
    embedding_changed = source_changed or model_changed

    if embedding_changed:
        await _require_no_active_files(db)

    if embedding_changed and not body.force:
        from sqlalchemy import select, func
        from models.file import File
        count_result = await db.execute(
            select(func.count()).select_from(File).where(File.status == "ready")
        )
        file_count = count_result.scalar() or 0
        if file_count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ui_msg("embedding_switch_blocked", count=file_count),
            )

    if embedding_changed and body.force:
        import asyncio
        from services.vector_service import reset_shared_collections
        try:
            await asyncio.to_thread(reset_shared_collections)
        except Exception as exc:
            logger.exception("Failed to reset shared Milvus collections after embedding switch")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ui_msg("vector_reset_failed", error=str(exc)),
            )

    for key, value in filtered.items():
        if key.endswith("_url") and str(value or "").strip():
            problem = service_url_problem(str(value))
            if problem:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=problem)
            filtered[key] = str(value).strip()

    await config.set_many(filtered, db)

    if "embedding_source" in filtered or "embedding_local_url" in filtered:
        import asyncio
        from services.embedding_service import (
            ensure_local_embedding_service,
            stop_local_embedding_service,
        )
        effective_source = filtered.get("embedding_source") or await config.get_setting("embedding_source", "local")
        if effective_source == "local":
            local_url = (
                filtered.get("embedding_local_url")
                or await config.get_setting("embedding_local_url", "")
                or config.default_local_embedding_url()
            ).strip()
            await ensure_local_embedding_service(local_url, wait=False)
        elif filtered.get("embedding_source") == "custom":
            await asyncio.to_thread(stop_local_embedding_service)

    if embedding_changed and body.force:
        # The old vectors were dropped above. Rebuild them with the new model right away;
        # otherwise every source stays "ready" while search silently finds nothing until
        # someone remembers to press "Re-index".
        queue = getattr(request.app.state, "redis", None)
        if queue is None:
            logger.warning("Embedding model switched but the task queue is unavailable; vectors were not rebuilt")
        else:
            queued = await _queue_reembed_all(db, queue)
            logger.info("Embedding model switched; queued %d file(s) for a vector rebuild", queued)

    all_settings = await _full_settings()
    return SettingsResponse(settings=all_settings)


@router.get("/preflight")
async def preflight_check(
    _: str = Depends(get_current_user),
) -> dict:
    # Check the user's raw settings directly instead of the resolve_*_config fallbacks;
    # otherwise a default model would make an unconfigured service look configured.
    llm_ready = bool(
        (await config.get_setting("llm_api_key", ""))
        and (await config.get_setting("llm_base_url", ""))
        and (await config.get_setting("llm_model", ""))
    )

    emb_source = await config.get_setting("embedding_source", "local")
    if emb_source == "custom":
        embedding_ready = bool(
            (await config.get_setting("embedding_api_key", ""))
            and (await config.get_setting("embedding_base_url", ""))
            and (await config.get_setting("embedding_model", ""))
        )
    else:  # local
        from services.embedding_service import _default_local_model_dir, is_local_embedding_url
        local_url = (await config.get_setting("embedding_local_url", "")).strip() or config.default_local_embedding_url()
        if is_local_embedding_url(local_url):
            embedding_ready = (_default_local_model_dir() / "config.json").exists() or bool(os.getenv("MODEL", "").strip())
        else:
            embedding_ready = bool(local_url)

    missing = []
    if not llm_ready:
        missing.append(ui_msg("preflight_llm"))
    if not embedding_ready:
        missing.append(ui_msg("preflight_embedding"))

    web_search_ready, _ = await config.resolve_web_search_config()

    return {
        "ready": llm_ready and embedding_ready,
        "llm_ready": llm_ready,
        "embedding_ready": embedding_ready,
        "web_search_ready": web_search_ready,
        "missing": missing,
    }


@router.get("/{key}")
async def get_single_setting(
    key: str,
    _: str = Depends(get_current_admin),
) -> dict:
    if key not in SETTING_KEYS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown setting key: {key}",
        )
    value = await config.get_setting(key)
    return {"key": key, "value": value}


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_setting(
    key: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> None:
    if key not in SETTING_KEYS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown setting key: {key}",
        )
    await config.set_setting(key, None, db)


class ChatModelTestRequest(BaseModel):
    # the source field is kept for compatibility with external callers
    source: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_format: str | None = None


class EmbeddingTestRequest(BaseModel):
    # source works like ChatModelTestRequest: the frontend can test after switching the radio without saving first
    source: str | None = None
    mode: str = "local"
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None


def _test_error(exc: BaseException) -> str:
    """Connection-test failure text: the kind of error, with the details only in the log."""
    logger.warning("Connection test failed: %s", exc, exc_info=True)
    return ui_msg("test_failed", reason=public_error_message(exc))


async def _mark_verified(key: str, ok: bool, db: AsyncSession) -> None:
    try:
        await config.set_setting(key, "true" if ok else "false", db)
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass


async def _test_chat_completions(
    api_key: str, base_url: str, model: str, payload_messages: list,
    verified_key: str, db: AsyncSession,
) -> dict:
    """Shared HTTP probe for LLM / VLM test endpoints."""
    payload = {"model": model, "messages": payload_messages, "max_tokens": 1}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        clean_base = base_url.rstrip("/")
        target_url = clean_base if clean_base.endswith("/chat/completions") else f"{clean_base}/chat/completions"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(target_url, json=payload, headers=headers)
        if resp.status_code in (200, 201):
            await _mark_verified(verified_key, True, db)
            return {"ok": True, "msg": ui_msg("conn_ok"), "verified": True}
        await _mark_verified(verified_key, False, db)
        return {"ok": False, "msg": ui_msg("service_returned", status=resp.status_code)}
    except httpx.ConnectError:
        await _mark_verified(verified_key, False, db)
        return {"ok": False, "msg": ui_msg("cannot_connect")}
    except Exception as exc:
        await _mark_verified(verified_key, False, db)
        return {"ok": False, "msg": _test_error(exc)}


async def _test_llm_provider(
    api_key: str,
    base_url: str | None,
    model: str,
    api_format: str,
    verified_key: str,
    db: AsyncSession,
    user_id: str,
) -> dict:
    try:
        chat_provider = create_llm_chat_provider(
            api_key=api_key,
            base_url=base_url,
            model=model,
            api_format=api_format,
            max_tokens=1,
            stream=False,
        )
        result = await generate(
            chat_provider=chat_provider,
            system_prompt="",
            tools=[],
            history=[Message(role="user", content="hi")],
        )
        await record_model_usage(user_id=user_id, model=model, usage=result.usage)
        await _mark_verified(verified_key, True, db)
        return {"ok": True, "msg": ui_msg("conn_ok"), "verified": True}
    except ChatProviderError as exc:
        await _mark_verified(verified_key, False, db)
        return {"ok": False, "msg": _test_error(exc)}
    except Exception as exc:
        await _mark_verified(verified_key, False, db)
        return {"ok": False, "msg": _test_error(exc)}


def _require_chat_params(
    api_key: str | None,
    base_url: str | None,
    model: str | None,
    *,
    require_base_url: bool = True,
) -> None:
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")
    if require_base_url and not base_url:
        raise HTTPException(status_code=400, detail="Base URL is required")
    problem = service_url_problem(base_url) if base_url else None
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    if not model:
        raise HTTPException(status_code=400, detail="Model is required")


async def _resolve_test_config(
    body: ChatModelTestRequest,
    kind: str,  # "llm" | "vlm"
) -> tuple[str | None, str | None, str | None, str]:
    """Resolve api_key/base_url/model/api_format directly from test request."""
    api_format = normalize_llm_api_format(body.api_format) if kind == "llm" else "openai"
    return body.api_key, body.base_url, body.model, api_format


@router.post("/test/llm")
async def test_llm(
    body: ChatModelTestRequest,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
) -> dict:
    api_key, base_url, model, api_format = await _resolve_test_config(body, kind="llm")
    _require_chat_params(api_key, base_url, model)

    return await _test_llm_provider(
        api_key,
        base_url,
        model,
        api_format,
        "llm_verified",
        db,
        current_admin.id,
    )


@router.post("/test/easy-task-llm")
async def test_easy_task_llm(
    body: ChatModelTestRequest,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
) -> dict:
    api_key, base_url, model, api_format = await _resolve_test_config(body, kind="llm")
    _require_chat_params(api_key, base_url, model)

    return await _test_llm_provider(
        api_key,
        base_url,
        model,
        api_format,
        "easy_task_llm_verified",
        db,
        current_admin.id,
    )


@router.post("/test/vlm")
async def test_vlm(
    body: ChatModelTestRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict:
    api_key, base_url, model, _ = await _resolve_test_config(body, kind="vlm")
    _require_chat_params(api_key, base_url, model)

    return await _test_chat_completions(
        api_key, base_url, model,
        [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        "vlm_verified", db,
    )


class OCRTestRequest(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


@router.post("/test/ocr")
async def test_ocr(
    body: OCRTestRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict:
    from services.ocr_client import health_check

    _, default_url, default_model, default_key = await config.resolve_ocr_config()
    api_key = (body.api_key if body.api_key is not None else (default_key or "")).strip()
    base_url = (body.base_url if body.base_url is not None else (default_url or "")).strip().rstrip("/")
    model = (body.model if body.model is not None else (default_model or "")).strip()

    if not api_key:
        return {"ok": False, "msg": ui_msg("missing_api_key")}
    if not base_url:
        return {"ok": False, "msg": ui_msg("missing_base_url")}
    problem = service_url_problem(base_url)
    if problem:
        return {"ok": False, "msg": problem}
    base_url = base_url.strip()
    if not model:
        return {"ok": False, "msg": ui_msg("missing_model")}

    try:
        result = await health_check(base_url=base_url, api_key=api_key, model=model)
        await _mark_verified("ocr_verified", bool(result.get("ok")), db)
        return result
    except Exception as exc:
        await _mark_verified("ocr_verified", False, db)
        return {"ok": False, "msg": _test_error(exc)}


class FunASRTestRequest(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


@router.post("/test/funasr")
async def test_funasr(
    body: FunASRTestRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict:
    from services.funasr_client import FunASRClient

    _, default_url, default_model, default_key = await config.resolve_funasr_config()
    api_key = (body.api_key if body.api_key is not None else (default_key or "")).strip()
    base_url = (body.base_url if body.base_url is not None else (default_url or "")).strip().rstrip("/")
    model = (body.model if body.model is not None else (default_model or "")).strip()

    if not api_key:
        return {"ok": False, "msg": ui_msg("missing_api_key")}
    if not base_url:
        return {"ok": False, "msg": ui_msg("missing_base_url")}
    problem = service_url_problem(base_url)
    if problem:
        return {"ok": False, "msg": problem}
    base_url = base_url.strip()
    if not model:
        return {"ok": False, "msg": ui_msg("missing_model")}

    ok, msg = await FunASRClient(base_url=base_url, api_key=api_key, model=model).health_check()
    await _mark_verified("funasr_verified", ok, db)
    if ok:
        return {"ok": True, "msg": msg, "verified": True}
    return {"ok": False, "msg": msg}


class TTSTestRequest(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    voice: str | None = None


@router.post("/test/tts")
async def test_tts(
    body: TTSTestRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict:
    from services.tts_client import TTSClient

    _, default_url, default_model, default_key, default_voice = await config.resolve_tts_config()
    api_key = (body.api_key if body.api_key is not None else (default_key or "")).strip()
    base_url = (body.base_url if body.base_url is not None else (default_url or "")).strip().rstrip("/")
    model = (body.model if body.model is not None else (default_model or "")).strip()
    voice = (body.voice if body.voice is not None else (default_voice or "deniz")).strip() or "deniz"

    if not api_key:
        return {"ok": False, "msg": "API anahtarı yapılandırılmadı"}
    if not base_url:
        return {"ok": False, "msg": "Base URL yapılandırılmadı"}
    problem = service_url_problem(base_url)
    if problem:
        return {"ok": False, "msg": problem}
    base_url = base_url.strip()
    if not model:
        return {"ok": False, "msg": "Model adı yapılandırılmadı"}

    ok, msg = await TTSClient.health_check(
        base_url=base_url,
        api_key=api_key,
        model=model,
        voice=voice,
    )
    await _mark_verified("tts_verified", ok, db)
    if ok:
        return {"ok": True, "msg": msg, "verified": True}
    return {"ok": False, "msg": msg}


class ReindexRequest(BaseModel):
    confirm: bool = False


@router.post("/embedding/reindex")
async def reindex_all_documents(
    request: Request,
    body: ReindexRequest | None = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict:
    """Drop shared Milvus collections and re-vectorize all parsed files from SQLite segments without re-running OCR/LLM/VLM."""
    import asyncio
    from services.vector_service import reset_shared_collections

    if not body or not body.confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ui_msg("reindex_confirm_required"))

    await _require_no_active_files(db)

    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail=ui_msg("queue_unavailable_file"))

    try:
        await asyncio.to_thread(reset_shared_collections)
    except Exception as exc:
        logger.exception("Failed to reset shared Milvus collections before re-indexing")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ui_msg("vector_reset_failed", error=str(exc)),
        )

    enqueued = await _queue_reembed_all(db, redis)

    return {
        "ok": True,
        "count": enqueued,
        "msg": ui_msg("reindex_queued", count=enqueued),
    }


@router.post("/embedding/local/start")
async def start_local_embedding(
    body: EmbeddingTestRequest | None = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict:
    from pathlib import Path
    from services.embedding_service import ensure_local_embedding_service

    base_url = (
        (body.base_url if body and body.base_url else "")
        or await config.get_setting("embedding_local_url", "")
        or config.default_local_embedding_url()
    ).strip()
    problem = service_url_problem(base_url)
    if problem:
        return {"ok": False, "base_url": "", "msg": problem}

    started = await ensure_local_embedding_service(base_url, wait=True)
    if started.get("ok") and not started.get("starting"):
        raw_model = str(started.get("model") or "bge-m3")
        model_label = Path(raw_model).name if "/" in raw_model or "\\" in raw_model else raw_model
        dim = started.get("dim") or 1024
        await _mark_verified("embedding_verified", True, db)
        return {
            "ok": True,
            "base_url": started.get("base_url", base_url),
            "model": model_label,
            "dim": dim,
            "msg": ui_msg("conn_ok_embedding", model=model_label, dim=dim),
            "verified": True,
        }
    return {
        "ok": False,
        "base_url": base_url,
        "msg": started.get("error") or ui_msg("cannot_connect_url", url=base_url),
    }


@router.post("/test/embedding")
async def test_embedding(
    body: EmbeddingTestRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict:
    # resolve from body.source so an old embedding_source in the DB is not used
    if body.source == "local":
        from services.embedding_service import ensure_local_embedding_service
        base_url = (
            body.base_url
            or await config.get_setting("embedding_local_url", "")
            or config.default_local_embedding_url()
        ).strip()
        started = await ensure_local_embedding_service(base_url, wait=True)
        if not started.get("ok"):
            await _mark_verified("embedding_verified", False, db)
            return {
                "ok": False,
                "msg": started.get("error") or ui_msg("cannot_connect_url", url=base_url),
            }
        model = body.model or "bge-m3"
        api_key = "local"
    elif body.source == "custom":
        api_key = body.api_key or ""
        base_url = body.base_url or ""
        model = body.model or ""
    else:
        # compatibility with old callers
        _, default_url, default_model, default_key = await config.resolve_embedding_config()
        base_url = body.base_url or default_url
        model = body.model or default_model
        api_key = body.api_key or default_key

    if not base_url:
        return {"ok": False, "msg": ui_msg("missing_service_url")}
    problem = service_url_problem(base_url)
    if problem:
        await _mark_verified("embedding_verified", False, db)
        return {"ok": False, "msg": problem}
    base_url = base_url.strip()

    payload: dict = {"model": model, "input": ["test text"]}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        from pathlib import Path
        clean_base = base_url.rstrip("/")
        target_url = clean_base if clean_base.endswith("/embeddings") else f"{clean_base}/embeddings"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(target_url, json=payload, headers=headers)
        if resp.status_code in (200, 201):
            data = resp.json()
            dim = len(data.get("data", [{}])[0].get("embedding", []))
            raw_model = str(data.get("model") or model or "bge-m3")
            model_label = Path(raw_model).name if ("/" in raw_model and raw_model.startswith("/")) else raw_model
            await _mark_verified("embedding_verified", True, db)
            return {"ok": True, "msg": ui_msg("conn_ok_embedding", model=model_label, dim=dim), "verified": True}
        await _mark_verified("embedding_verified", False, db)
        return {"ok": False, "msg": ui_msg("service_returned", status=resp.status_code)}
    except httpx.ConnectError:
        await _mark_verified("embedding_verified", False, db)
        return {"ok": False, "msg": ui_msg("cannot_connect_url", url=base_url)}
    except Exception as exc:
        await _mark_verified("embedding_verified", False, db)
        return {"ok": False, "msg": _test_error(exc)}


class WebSearchTestRequest(BaseModel):
    base_url: str | None = None


@router.post("/test/web-search")
async def test_web_search(
    body: WebSearchTestRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict:
    base_url = (body.base_url or "").strip().rstrip("/") or await config.resolve_searxng_url()
    problem = service_url_problem(base_url)
    if problem:
        return {"ok": False, "msg": problem}
    base_url = base_url.strip()
    return await _test_searxng(base_url, db)


async def _test_searxng(base_url: str, db: AsyncSession) -> dict:
    from services import searxng_client as sx

    if not base_url.startswith(("http://", "https://")):
        return {"ok": False, "msg": ui_msg("missing_base_url")}
    try:
        results = await sx.search(base_url, "test", timeout=20)
    except sx.SearxngError as exc:
        await _mark_verified("web_search_verified", False, db)
        if exc.code == "unreachable":
            return {"ok": False, "msg": ui_msg("searxng_cannot_connect", url=base_url)}
        if exc.code == "json_disabled":
            return {"ok": False, "msg": ui_msg("searxng_json_disabled")}
        if exc.code == "rate_limited":
            return {"ok": False, "msg": ui_msg("searxng_rate_limited")}
        if exc.code == "timeout":
            return {"ok": False, "msg": ui_msg("conn_timeout_url", url=base_url)}
        return {"ok": False, "msg": ui_msg("service_returned", status=exc.status or str(exc))}
    engines = sorted({e for r in results for e in r.engines})
    if not results:
        await _mark_verified("web_search_verified", False, db)
        return {"ok": False, "msg": ui_msg("searxng_no_results")}
    await _mark_verified("web_search_verified", True, db)
    return {
        "ok": True,
        "msg": ui_msg("searxng_ok", count=len(results), engines=", ".join(engines[:6]) or "-"),
        "verified": True,
    }
