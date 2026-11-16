import asyncio
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_cache: dict[str, str] = {}
_lock: asyncio.Lock = asyncio.Lock()


async def load_settings(db: AsyncSession) -> None:
    from models.settings import Setting

    async with _lock:
        result = await db.execute(select(Setting))
        rows = result.scalars().all()
        _cache.clear()
        for row in rows:
            if row.value is not None:
                _cache[row.key] = row.value


async def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    if key in _cache:
        return _cache[key]
    return os.getenv(key.upper(), default)


async def _upsert_setting(
    key: str, value: Optional[str], db: AsyncSession
) -> None:
    """Insert or update a single setting row (caller holds _lock)."""
    from models.settings import Setting

    result = await db.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()

    if row is None:
        row = Setting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)


def _update_cache(key: str, value: Optional[str]) -> None:
    if value is None:
        _cache.pop(key, None)
    else:
        _cache[key] = value


async def set_setting(key: str, value: Optional[str], db: AsyncSession) -> None:
    async with _lock:
        await _upsert_setting(key, value, db)
        await db.commit()
        _update_cache(key, value)


async def set_many(settings: dict[str, Optional[str]], db: AsyncSession) -> None:
    async with _lock:
        for key, value in settings.items():
            await _upsert_setting(key, value, db)
        await db.commit()
        for key, value in settings.items():
            _update_cache(key, value)


def get_all_cached() -> dict[str, Optional[str]]:
    return dict(_cache)


PDF_ENGINES = ("auto", "local", "ocr")


async def resolve_pdf_engine() -> str:
    """Which parser handles PDFs: 'auto', 'local' (PyMuPDF) or 'ocr' (the configured OCR service)."""
    value = (await get_setting("pdf_engine", "auto") or "auto").strip().lower()
    return value if value in PDF_ENGINES else "auto"


async def resolve_ocr_config() -> tuple[bool, str | None, str | None, str | None]:
    api_key = (await get_setting("ocr_api_key", "") or "").strip()
    base_url = (await get_setting("ocr_base_url", "") or "").strip().rstrip("/")
    model = (await get_setting("ocr_model", "") or "").strip()
    enabled = bool(api_key and base_url and model)
    return enabled, base_url or None, model or None, api_key or None


async def resolve_funasr_config() -> tuple[bool, str | None, str | None, str | None]:
    api_key = (await get_setting("funasr_api_key", "") or "").strip()
    base_url = (await get_setting("funasr_base_url", "") or "").strip().rstrip("/")
    model = (await get_setting("funasr_model", "") or "").strip()
    enabled = bool(api_key and base_url and model)
    return enabled, base_url or None, model or None, api_key or None


async def resolve_tts_config() -> tuple[bool, str | None, str | None, str | None, str]:
    api_key = (await get_setting("tts_api_key", "") or "").strip()
    base_url = (await get_setting("tts_base_url", "") or "").strip().rstrip("/")
    model = (await get_setting("tts_model", "") or "").strip()
    voice = (await get_setting("tts_voice", "deniz") or "deniz").strip() or "deniz"
    enabled = bool(api_key and base_url and model)
    return enabled, base_url or None, model or None, api_key or None, voice


DEFAULT_SEARXNG_URL = os.getenv("SEARXNG_URL") or f"http://127.0.0.1:{os.getenv('SEARXNG_PORT', '8888')}"


async def resolve_searxng_url() -> str:
    """Address of the local SearXNG instance used for all web search."""
    return (await get_setting("searxng_base_url", "") or "").strip().rstrip("/") or DEFAULT_SEARXNG_URL


async def resolve_web_search_config() -> tuple[bool, str]:
    """(enabled, base_url). Web search counts as enabled only while SearXNG answers."""
    from services.searxng_client import is_reachable

    base_url = await resolve_searxng_url()
    return await is_reachable(base_url), base_url


async def resolve_llm_config() -> tuple[str | None, str | None, str | None]:
    api_key = await get_setting("llm_api_key", "")
    base_url = await get_setting("llm_base_url", "")
    model = await get_setting("llm_model", "")
    return api_key or None, base_url or None, model or None


async def resolve_llm_provider_config() -> tuple[str | None, str | None, str | None, str]:
    api_key, base_url, model = await resolve_llm_config()
    api_format = await get_setting("llm_api_format", "openai")
    return api_key, base_url, model, api_format or "openai"


async def is_easy_task_llm_configured() -> bool:
    """Whether the user configured a separate "simple task model" (i.e. the saving plan is actually in effect).

    Empty means simple tasks share the main LLM's model.
    """
    easy_model = await get_setting("easy_task_llm", "")
    return bool(easy_model and easy_model.strip())


async def resolve_easy_task_llm_config() -> tuple[str | None, str | None, str | None]:
    """"Saving plan": the LLM configuration for simple tasks (summaries generated while parsing).

    Reuses the main LLM provider (key + base_url) and only swaps the model name when easy_task_llm is set;
    otherwise it matches the main LLM, so simple and complex tasks share one model.
    """
    api_key, base_url, model = await resolve_llm_config()
    if await is_easy_task_llm_configured():
        model = (await get_setting("easy_task_llm", "")).strip()
    return api_key, base_url, model


async def resolve_easy_task_llm_provider_config() -> tuple[str | None, str | None, str | None, str]:
    """Like resolve_easy_task_llm_config(), but includes the selected request format."""
    api_key, base_url, model, api_format = await resolve_llm_provider_config()
    if await is_easy_task_llm_configured():
        model = (await get_setting("easy_task_llm", "")).strip()
    return api_key, base_url, model, api_format


async def resolve_vlm_config() -> tuple[str | None, str | None, str | None]:
    api_key = await get_setting("vlm_api_key", "")
    base_url = await get_setting("vlm_base_url", "")
    model = await get_setting("vlm_model", "")
    return api_key or None, base_url or None, model or None


def default_local_embedding_url() -> str:
    return f"http://127.0.0.1:{os.getenv('EMBEDDING_PORT', '8001')}"


async def resolve_embedding_config() -> tuple[str, str, str, str]:
    source = await get_setting("embedding_source", "local")

    if source == "custom":
        base_url = await get_setting("embedding_base_url", "")
        model = await get_setting("embedding_model", "")
        api_key = await get_setting("embedding_api_key", "")
        return "api", base_url or "", model or "", api_key or ""

    local_url = (await get_setting("embedding_local_url", "")).strip() or default_local_embedding_url()
    return "local", local_url, "bge-m3", "local"
