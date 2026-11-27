"""Find sources on the web and import the chosen ones into a project."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import get_current_user
from dependencies.database import get_db
from dependencies.permissions import require_project
from models.file import File
from models.user import User
from paths import get_upload_dir, safe_join, to_portable_path
from schemas.file import FileResponse
from services import open_access as oa
from services import searxng_client as sx
from utils.i18n import msg as ui_msg

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/web-sources", tags=["web-sources"])

MIN_PAGE_TEXT = 300
MAX_IMPORT_ITEMS = 20
FETCH_CONCURRENCY = 4


class WebSourceSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    scope: str = "web"  # web | academic
    output_language: str | None = None


class WebSourceItem(BaseModel):
    url: str
    title: str | None = None
    # Filled from the search results when known
    pdf_url: str | None = None
    landing_url: str | None = None
    doi: str | None = None
    authors: list[str] = Field(default_factory=list)
    published_date: str | None = None


class WebSourceImportRequest(BaseModel):
    items: list[WebSourceItem]
    output_language: str | None = None


def _searxng_http_error(exc: sx.SearxngError, base_url: str) -> HTTPException:
    if exc.code == "unreachable":
        return HTTPException(status_code=503, detail=ui_msg("searxng_cannot_connect", url=base_url))
    if exc.code == "json_disabled":
        return HTTPException(status_code=503, detail=ui_msg("searxng_json_disabled"))
    if exc.code == "rate_limited":
        return HTTPException(status_code=429, detail=ui_msg("searxng_rate_limited"))
    return HTTPException(status_code=502, detail=ui_msg("service_returned", status=exc.status or exc.code))


async def _imported_urls(db: AsyncSession, project_id: str) -> set[str]:
    rows = (
        await db.execute(
            select(File.source_url).where(File.project_id == project_id, File.source_url.is_not(None))
        )
    ).scalars().all()
    return {sx._normalize_url(u) for u in rows if u}


@router.post("/search")
async def search_web_sources(
    project_id: str,
    body: WebSourceSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    import config
    from services.web_discovery import discover_sources_quick

    await require_project(db, project_id, current_user)
    scope = body.scope if body.scope in ("web", "academic") else "web"
    try:
        data = await discover_sources_quick(
            topic=body.query.strip(),
            scope=scope,
            language=None,
        )
    except sx.SearxngError as exc:
        raise _searxng_http_error(exc, await config.resolve_searxng_url())
    imported = await _imported_urls(db, project_id)
    for item in data["results"]:
        item["imported"] = sx._normalize_url(item["url"]) in imported
    return {"scope": scope, **data}


class WebSourceExpandRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    scope: str = "web"
    output_language: str | None = None
    exclude_urls: list[str] = Field(default_factory=list, max_length=80)


@router.post("/search/expand")
async def expand_web_sources(
    project_id: str,
    body: WebSourceExpandRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Phase 2 of a search: the model writes extra queries, which are searched for more sources."""
    import config
    from services.web_discovery import discover_sources_expanded

    await require_project(db, project_id, current_user)
    scope = body.scope if body.scope in ("web", "academic") else "web"
    try:
        data = await discover_sources_expanded(
            topic=body.query.strip(),
            scope=scope,
            output_language=body.output_language or "Turkish",
            language=None,
            user_id=current_user.id,
            exclude_urls=body.exclude_urls,
        )
    except sx.SearxngError as exc:
        raise _searxng_http_error(exc, await config.resolve_searxng_url())
    imported = await _imported_urls(db, project_id)
    for item in data["results"]:
        item["imported"] = sx._normalize_url(item["url"]) in imported
    return {"scope": scope, **data}


class WebSourceRankRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    scope: str = "web"
    output_language: str | None = None
    items: list[dict] = Field(default_factory=list, max_length=40)


@router.post("/rank")
async def rank_web_sources(
    project_id: str,
    body: WebSourceRankRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Second step of a search: the model orders the shown results and explains each."""
    from services.web_discovery import rank_sources

    await require_project(db, project_id, current_user)
    order = await rank_sources(
        body.query.strip(),
        body.scope if body.scope in ("web", "academic") else "web",
        body.items,
        body.output_language or "Turkish",
        current_user.id,
    )
    return {"ok": order is not None, "order": order or []}


class DeepResearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000)
    scope: str = "web"
    output_language: str | None = None


@router.post("/deep-research")
async def start_deep_research(
    project_id: str,
    body: DeepResearchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Start a background deep research; its report appears among the project's results."""
    from models.feature import Feature
    from routes.feature_routes import _feature_to_list_dict

    await require_project(db, project_id, current_user)
    redis = request.app.state.redis
    if redis is None:
        raise HTTPException(status_code=503, detail=ui_msg("queue_unavailable_feature"))
    topic = re.sub(r"\s+", " ", body.query).strip()
    language = body.output_language or "Turkish"
    feature = Feature(
        project_id=project_id,
        workflow_id=None,
        feature_type="deep_research",
        step_index=0,
        step_name=topic[:200],
        title=topic[:200],
        status="pending",
    )
    feature.set_custom_config({
        "query": topic,
        "scope": body.scope if body.scope in ("web", "academic") else "web",
        "output_language": language,
        "progress": ui_msg("research_queued"),
    })
    db.add(feature)
    await db.commit()
    await db.refresh(feature)
    await redis.enqueue_job("deep_research_task", feature.id, language)
    return _feature_to_list_dict(feature)


# ── import ──────────────────────────────────────────────────────────────────

def _safe_name(text: str, limit: int = 150) -> str:
    text = unicodedata.normalize("NFC", re.sub(r"\s+", " ", text or "")).strip()
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", text).strip(" .-–")
    return text[:limit].rstrip(" .-–") or "web-source"


def _surname(author: str) -> str:
    author = author.strip()
    if "," in author:
        return author.split(",", 1)[0].strip()
    parts = author.split()
    return parts[-1] if parts else author


def _year(text: str | None) -> str:
    match = re.search(r"\b(1[5-9]\d\d|20\d\d)\b", text or "")
    return match.group(1) if match else ""


def _base_name(page: sx.FetchedPage, fallback_title: str, meta: dict | None = None) -> str:
    """"Author - Year - Title" when citation data is known, else the title."""
    meta = meta or {}
    title = meta.get("title") or page.title or fallback_title or page.final_url
    authors = page.authors or meta.get("authors") or []
    year = _year(page.published) or meta.get("year") or ""
    if authors and year:
        author = _surname(authors[0]) + (" et al." if len(authors) > 1 else "")
        return _safe_name(f"{author} - {year} - {title}", 180)
    return _safe_name(title)


def _unique_path(project_dir: Path, base: str, ext: str, taken: set[str]) -> Path:
    name = f"{base}{ext}"
    n = 2
    while name.lower() in taken or safe_join(project_dir, name).exists():
        name = f"{base} ({n}){ext}"
        n += 1
    taken.add(name.lower())
    return safe_join(project_dir, name)


def _markdown_document(page: sx.FetchedPage, title: str, url: str, info: dict | None = None) -> str:
    info = info or {}
    meta = [f"- {ui_msg('websource_label_url')}: {url}"]
    authors = page.authors or info.get("authors") or []
    if authors:
        meta.append(f"- {ui_msg('websource_label_authors')}: {'; '.join(authors[:10])}")
    published = (page.published or "")[:10] or info.get("year") or ""
    if published:
        meta.append(f"- {ui_msg('websource_label_published')}: {published}")
    if page.site_name:
        meta.append(f"- {ui_msg('websource_label_site')}: {page.site_name}")
    if info.get("doi"):
        meta.append(f"- DOI: {info['doi']}")
    meta.append(f"- {ui_msg('websource_label_accessed')}: {datetime.now().strftime('%Y-%m-%d')}")
    note = f"\n\n> {ui_msg('websource_abstract_only_note')}" if info.get("abstract_only") else ""
    return f"# {title}\n\n" + "\n".join(meta) + note + "\n\n---\n\n" + page.text.strip() + "\n"


async def _fetch_source(item: WebSourceItem) -> tuple[sx.FetchedPage, dict]:
    """Download the fullest free version of a source.

    Order: known PDF links, then open-access copies found by DOI (OpenAlex /
    Semantic Scholar), then a free landing page, then the result page itself.
    A scholarly work that ends with only its publisher page is marked abstract_only."""
    doi = oa.normalize_doi(item.doi) or oa.normalize_doi(item.url)
    info: dict = {
        "doi": doi,
        "title": "",
        "authors": list(item.authors or []),
        "year": _year(item.published_date),
        "abstract_only": False,
    }
    pdf_urls: list[str] = [u for u in [item.pdf_url, oa.arxiv_pdf_url(item.url)] if u]
    pages: list[str] = [u for u in [item.landing_url] if u]
    if doi:
        found = await oa.resolve_open_access(doi)
        if found is not None:
            pdf_urls += [u for u in found.pdf_urls if u not in pdf_urls]
            if found.landing_url and found.landing_url not in pages:
                pages.append(found.landing_url)
            info["title"] = found.title
            info["authors"] = info["authors"] or found.authors
            info["year"] = info["year"] or found.year
    if item.url not in pages:
        pages.append(item.url)

    last_error: Exception | None = None
    for url in pdf_urls:
        try:
            page = await sx.fetch_page(url, timeout=30, follow_pdf=True)
            if page.is_pdf:
                return page, info
        except Exception as exc:
            last_error = exc
            logger.info(f"PDF candidate failed ({url}): {exc}")

    fallback: sx.FetchedPage | None = None
    for url in pages:
        try:
            page = await sx.fetch_page(url, timeout=25, follow_pdf=True)
        except Exception as exc:
            last_error = exc
            logger.info(f"page candidate failed ({url}): {exc}")
            continue
        if page.is_pdf:
            return page, info
        if fallback is None or len(page.text) > len(fallback.text):
            fallback = page
        if len(page.text) >= 3000:
            break
    if fallback is None:
        raise last_error or sx.SearxngError("http", "download failed")
    info["abstract_only"] = bool(doi)
    return fallback, info


def _fetch_error_reason(exc: Exception) -> str:
    text = str(exc)
    if isinstance(exc, sx.SearxngError):
        if exc.code == "blocked":
            return ui_msg("websource_blocked")
        if "too large" in text:
            return ui_msg("websource_too_large")
        if "unsupported content type" in text:
            return ui_msg("websource_unsupported")
        if exc.status:
            return ui_msg("websource_http_error", status=exc.status)
    if "timeout" in type(exc).__name__.lower() or "timed out" in text.lower():
        return ui_msg("websource_timeout")
    return ui_msg("websource_fetch_failed")


@router.post("/import")
async def import_web_sources(
    project_id: str,
    body: WebSourceImportRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    await require_project(db, project_id, current_user)
    items = [i for i in body.items if i.url.startswith(("http://", "https://"))][:MAX_IMPORT_ITEMS]
    if not items:
        raise HTTPException(status_code=422, detail=ui_msg("websource_nothing_selected"))

    already = await _imported_urls(db, project_id)
    skipped = [i for i in items if sx._normalize_url(i.url) in already]
    todo = [i for i in items if sx._normalize_url(i.url) not in already]

    sem = asyncio.Semaphore(FETCH_CONCURRENCY)
    project_dir = safe_join(get_upload_dir(), project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    spooled: dict[int, tuple[str, int]] = {}  # id(page) -> (temporary file, size)

    async def fetch(item: WebSourceItem):
        async with sem:
            try:
                page, info = await _fetch_source(item)
            except Exception as exc:
                logger.info(f"web source fetch failed ({item.url}): {exc}")
                return item, None, {}, exc
            if page.pdf_bytes:
                # A PDF goes to disk as soon as it arrives, so at most FETCH_CONCURRENCY
                # downloads are in memory at once instead of every PDF of the request.
                spooled[id(page)] = (await asyncio.to_thread(_spool_to_disk, project_dir, page.pdf_bytes), len(page.pdf_bytes))
                page.pdf_bytes = b""  # still a PDF (is_pdf), without holding the bytes
            return item, page, info, None

    try:
        fetched = await asyncio.gather(*(fetch(i) for i in todo))
        return await _store_fetched(db, request, body, project_id, project_dir, fetched, spooled, skipped)
    finally:
        for path, _size in spooled.values():
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass


def _spool_to_disk(project_dir, data: bytes) -> str:
    fd, path = tempfile.mkstemp(prefix=".import-", suffix=".part", dir=project_dir)
    with os.fdopen(fd, "wb") as out:
        out.write(data)
    return path


async def _store_fetched(db, request, body, project_id, project_dir, fetched, spooled, skipped) -> dict:
    taken = {
        n.lower()
        for n in (await db.execute(select(File.file_name).where(File.project_id == project_id))).scalars().all()
    }

    created: list[File] = []
    failed: list[dict] = []
    abstract_only: list[str] = []
    for item, page, info, error in fetched:
        title = (item.title or "").strip()
        if page is None:
            failed.append({"url": item.url, "title": title, "reason": _fetch_error_reason(error)})
            continue
        if page.is_pdf:
            dest = _unique_path(project_dir, _base_name(page, title, info), ".pdf", taken)
            data = None
        else:
            # An abstract is short, so it is kept even below the usual minimum.
            min_text = 80 if info.get("abstract_only") else MIN_PAGE_TEXT
            if len(page.text) < min_text:
                failed.append({"url": item.url, "title": title or page.title, "reason": ui_msg("websource_no_text")})
                continue
            doc_title = info.get("title") or page.title or title or item.url
            dest = _unique_path(project_dir, _base_name(page, title, info), ".md", taken)
            data = _markdown_document(page, doc_title, page.final_url or item.url, info).encode("utf-8")
            if info.get("abstract_only"):
                abstract_only.append(item.url)

        if data is None:
            spool_path, file_size = spooled.pop(id(page))
            await asyncio.to_thread(os.replace, spool_path, dest)
        else:
            async with aiofiles.open(dest, "wb") as f:
                await f.write(data)
            file_size = len(data)
        db_file = File(
            project_id=project_id,
            file_name=dest.name,
            file_path=to_portable_path(dest),
            file_type="pdf" if page.is_pdf else "md",
            file_size=file_size,
            status="pending",
            processing_current=0,
            processing_total=None,
            processing_message=None,
            source_url=item.url,
        )
        db.add(db_file)
        created.append(db_file)

    if created:
        await db.commit()
        redis = request.app.state.redis
        if redis is not None:
            for db_file in created:
                job = await redis.enqueue_job("parse_file_task", db_file.id, body.output_language)
                db_file.job_id = job.job_id
            await db.commit()
        for db_file in created:
            await db.refresh(db_file)

    return {
        "imported": [FileResponse.model_validate(f).model_dump(mode="json") for f in created],
        "failed": failed,
        "skipped": [{"url": i.url, "title": i.title or ""} for i in skipped],
        "abstract_only": abstract_only,
    }
