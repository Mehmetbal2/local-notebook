import asyncio
import logging
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from dependencies.auth import get_current_admin, hash_password
from dependencies.database import get_db
from models.user import User
from models.usage import UserModelUsageDaily
from schemas.admin import (
    AdminPasswordReset,
    AdminUsageResponse,
    AdminUsageRow,
    AdminUsageTotals,
    AdminUserCreate,
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserStatsResponse,
    AdminUserStatsRow,
    AdminUserStatsTotals,
)
from services.usage_service import current_usage_date

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger("admin_routes")


# Log lines that look like errors but are expected. Milvus Lite does not implement
# AllocTimestamp; pymilvus calls it after creating an index and falls back on its own.
_BENIGN_LOG_MARKERS = ("grpc._server  Exception calling application: Method not implemented!",)


def _is_benign_log_line(line: str) -> bool:
    return any(marker in line for marker in _BENIGN_LOG_MARKERS)


def _serialize_user(user: User) -> AdminUserResponse:
    return AdminUserResponse(
        user_id=user.id,
        username=user.username,
        role=user.role,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


async def _get_user_or_404(db: AsyncSession, user_id: str) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> AdminUserListResponse:
    result = await db.execute(
        select(User)
        .order_by(User.role.desc(), User.created_at.asc())
    )
    users = result.scalars().all()
    return AdminUserListResponse(
        users=[_serialize_user(user) for user in users],
        total=len(users),
    )


@router.get("/users/stats", response_model=AdminUserStatsResponse)
async def user_stats(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> AdminUserStatsResponse:
    """Per-user content and activity: projects, sources, chats, outputs and LLM usage.

    Content counts are all-time; LLM calls and tokens cover the last ``days`` days.
    Projects created before accounts existed have no owner and are reported as one row.
    """
    from sqlalchemy import case, func

    from models.feature import Feature
    from models.file import File
    from models.message import Message
    from models.project import Project
    from models.session import Session

    days = max(1, min(days, 366))
    stats: dict[str | None, dict] = {}

    def bucket(owner: str | None) -> dict:
        return stats.setdefault(owner, {"last": []})

    def newest(*values):
        found = [v for v in values if v is not None]
        if not found:
            return None
        # SQLite returns naive datetimes; compare them as UTC.
        return max(v if v.tzinfo else v.replace(tzinfo=timezone.utc) for v in found)

    owner = Project.owner_user_id
    for owner_id, count, updated in (
        await db.execute(select(owner, func.count(Project.id), func.max(Project.updated_at)).group_by(owner))
    ).all():
        entry = bucket(owner_id)
        entry["projects"] = int(count)
        entry["last"].append(updated)

    for owner_id, count, ready, size, created in (
        await db.execute(
            select(
                owner,
                func.count(File.id),
                func.sum(case((File.status == "ready", 1), else_=0)),
                func.sum(func.coalesce(File.file_size, 0)),
                func.max(File.created_at),
            )
            .join(Project, File.project_id == Project.id)
            .group_by(owner)
        )
    ).all():
        entry = bucket(owner_id)
        entry.update(files=int(count), ready_files=int(ready or 0), storage_bytes=int(size or 0))
        entry["last"].append(created)

    for owner_id, count in (
        await db.execute(
            select(owner, func.count(Session.id))
            .join(Project, Session.project_id == Project.id)
            .group_by(owner)
        )
    ).all():
        bucket(owner_id)["sessions"] = int(count)

    for owner_id, count, created in (
        await db.execute(
            select(owner, func.count(Message.id), func.max(Message.created_at))
            .join(Session, Message.session_id == Session.id)
            .join(Project, Session.project_id == Project.id)
            .where(Message.role == "user", Message.deleted_at.is_(None))
            .group_by(owner)
        )
    ).all():
        entry = bucket(owner_id)
        entry["messages"] = int(count)
        entry["last"].append(created)

    for owner_id, count, created in (
        await db.execute(
            select(owner, func.count(Feature.id), func.max(Feature.created_at))
            .join(Project, Feature.project_id == Project.id)
            .group_by(owner)
        )
    ).all():
        entry = bucket(owner_id)
        entry["outputs"] = int(count)
        entry["last"].append(created)

    since = current_usage_date() - timedelta(days=days - 1)
    token_sum = (
        UserModelUsageDaily.input_uncached_tokens
        + UserModelUsageDaily.input_cache_read_tokens
        + UserModelUsageDaily.input_cache_write_tokens
        + UserModelUsageDaily.output_tokens
    )
    for user_id, calls, tokens in (
        await db.execute(
            select(
                UserModelUsageDaily.user_id,
                func.sum(UserModelUsageDaily.call_count),
                func.sum(token_sum),
            )
            .where(UserModelUsageDaily.usage_date >= since)
            .group_by(UserModelUsageDaily.user_id)
        )
    ).all():
        entry = bucket(user_id)
        entry.update(llm_calls=int(calls or 0), tokens=int(tokens or 0))

    users = (await db.execute(select(User).order_by(User.role.desc(), User.created_at.asc()))).scalars().all()
    known = {user.id for user in users}
    rows: list[AdminUserStatsRow] = []
    for user in users:
        entry = stats.get(user.id, {"last": []})
        rows.append(
            AdminUserStatsRow(
                user_id=user.id,
                username=user.username,
                role=user.role,
                last_active_at=newest(*entry.pop("last", [])),
                **entry,
            )
        )
    # Content whose owner is missing (legacy projects or a deleted account) as one row.
    orphan: dict = {"last": []}
    for key, entry in stats.items():
        if key in known:
            continue
        for field, value in entry.items():
            if field == "last":
                orphan["last"].extend(value)
            else:
                orphan[field] = orphan.get(field, 0) + value
    if len(orphan) > 1:
        rows.append(
            AdminUserStatsRow(
                user_id=None,
                username="",
                role="unassigned",
                last_active_at=newest(*orphan.pop("last")),
                **orphan,
            )
        )

    totals = AdminUserStatsTotals()
    for row in rows:
        for field in ("projects", "files", "ready_files", "storage_bytes", "sessions", "messages", "outputs", "llm_calls", "tokens"):
            setattr(totals, field, getattr(totals, field) + getattr(row, field))
    totals.active_users = sum(1 for row in rows if row.user_id and row.llm_calls > 0)
    return AdminUserStatsResponse(period_days=days, rows=rows, totals=totals)


@router.post("/users", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: AdminUserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> AdminUserResponse:
    username = body.username.strip()
    if len(username) < 2:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Username must be at least 2 characters")

    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    user = User(
        username=username,
        password_hash=hash_password(body.password),
        role="user",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _serialize_user(user)


@router.get("/usage", response_model=AdminUsageResponse)
async def list_usage(
    start_date: date | None = None,
    end_date: date | None = None,
    user_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> AdminUsageResponse:
    today = current_usage_date()
    start = start_date or (today - timedelta(days=29))
    end = end_date or today
    if start > end:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="start_date must be before end_date")

    query = (
        select(UserModelUsageDaily, User.username)
        .join(User, UserModelUsageDaily.user_id == User.id)
        .where(
            UserModelUsageDaily.usage_date >= start,
            UserModelUsageDaily.usage_date <= end,
        )
        .order_by(
            UserModelUsageDaily.usage_date.desc(),
            User.username.asc(),
            UserModelUsageDaily.model.asc(),
        )
    )
    if user_id:
        query = query.where(UserModelUsageDaily.user_id == user_id)

    result = await db.execute(query)
    rows: list[AdminUsageRow] = []
    totals = {
        "call_count": 0,
        "input_uncached_tokens": 0,
        "input_cache_read_tokens": 0,
        "input_cache_write_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }

    for usage, username in result.all():
        total_tokens = (
            usage.input_uncached_tokens
            + usage.input_cache_read_tokens
            + usage.input_cache_write_tokens
            + usage.output_tokens
        )
        row = AdminUsageRow(
            usage_date=usage.usage_date,
            user_id=usage.user_id,
            username=username,
            model=usage.model,
            call_count=usage.call_count,
            input_uncached_tokens=usage.input_uncached_tokens,
            input_cache_read_tokens=usage.input_cache_read_tokens,
            input_cache_write_tokens=usage.input_cache_write_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=total_tokens,
        )
        rows.append(row)
        totals["call_count"] += usage.call_count
        totals["input_uncached_tokens"] += usage.input_uncached_tokens
        totals["input_cache_read_tokens"] += usage.input_cache_read_tokens
        totals["input_cache_write_tokens"] += usage.input_cache_write_tokens
        totals["output_tokens"] += usage.output_tokens
        totals["total_tokens"] += total_tokens

    return AdminUsageResponse(
        rows=rows,
        totals=AdminUsageTotals(**totals),
    )


@router.post("/users/{user_id}/password")
async def reset_user_password(
    user_id: str,
    body: AdminPasswordReset,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> dict:
    user = await _get_user_or_404(db, user_id)
    user.password_hash = hash_password(body.new_password)
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"success": True, "message": "Password reset"}


@router.get("/backup")
async def download_backup(
    include_uploads: bool = False,
    include_vectors: bool = True,
    _: User = Depends(get_current_admin),
) -> FileResponse:
    """Create and stream a portable backup zip (database, local vectors, optional uploads)."""
    from services.backup_service import create_backup_archive

    try:
        archive_path = await asyncio.to_thread(
            create_backup_archive, include_uploads, include_vectors
        )
    except Exception as exc:
        logger.exception("Backup creation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backup failed: {exc}",
        ) from exc
    return FileResponse(
        path=str(archive_path),
        media_type="application/zip",
        filename=archive_path.name,
        background=BackgroundTask(archive_path.unlink, missing_ok=True),
    )


@router.post("/backup/prepare")
async def prepare_backup(
    include_uploads: bool = False,
    include_vectors: bool = True,
    _: User = Depends(get_current_admin),
) -> dict:
    """Build a backup archive and return a one-time link for the browser to download it.

    The browser follows the link like any download, so a multi-gigabyte archive streams
    to disk instead of being collected in page memory first.
    """
    from services.backup_service import DOWNLOAD_TTL_SECONDS, create_backup_archive, register_download

    try:
        archive_path = await asyncio.to_thread(
            create_backup_archive, include_uploads, include_vectors
        )
    except Exception as exc:
        logger.exception("Backup creation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backup failed: {exc}",
        ) from exc
    token = register_download(archive_path)
    return {
        "download_path": f"/api/admin/backup/download/{token}",
        "filename": archive_path.name,
        "size_bytes": archive_path.stat().st_size,
        "expires_in": DOWNLOAD_TTL_SECONDS,
    }


@router.get("/backup/download/{token}")
async def download_prepared_backup(token: str) -> FileResponse:
    """Serve a prepared archive once. The unguessable one-time token is the authorization:
    a plain browser download cannot send the Authorization header."""
    from services.backup_service import claim_download

    archive_path = claim_download(token)
    if archive_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This download link has expired or was already used",
        )
    return FileResponse(
        path=str(archive_path),
        media_type="application/zip",
        filename=archive_path.name,
        headers={"Cache-Control": "no-store"},
        background=BackgroundTask(archive_path.unlink, missing_ok=True),
    )


@router.post("/restore")
async def restore_backup(
    file: UploadFile = File(...),
    _: User = Depends(get_current_admin),
) -> dict:
    """Validate an uploaded backup and stage it for the next application start."""
    from services.backup_service import MAX_RESTORE_BYTES, stage_restore_archive

    suffix = Path(file.filename or "backup.zip").suffix or ".zip"
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_path = Path(handle.name)
    written = 0
    try:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_RESTORE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Backup archive is too large",
                )
            handle.write(chunk)
        handle.close()
        result = await asyncio.to_thread(stage_restore_archive, temp_path)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Restore staging failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Restore failed: {exc}",
        ) from exc
    finally:
        try:
            handle.close()
        finally:
            temp_path.unlink(missing_ok=True)

    return {
        "ok": True,
        "message": "Restore staged. Restart the application to apply it.",
        "manifest": result.get("manifest", {}),
    }


@router.get("/diagnostics")
async def get_diagnostics(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> dict:
    """Read-only health snapshot: counts, vector store, storage, services and recent errors."""
    import platform
    import shutil
    import time as _time

    import httpx
    from sqlalchemy import func

    import config
    from models.file import File
    from models.message import Message
    from models.project import Project
    from models.segment import Segment
    from paths import get_data_dir, get_upload_dir
    from services import vector_service as vs
    from services.backup_service import database_file, milvus_file

    counts: dict[str, int] = {}
    for key, model in (
        ("projects", Project),
        ("files", File),
        ("segments", Segment),
        ("messages", Message),
        ("users", User),
    ):
        counts[key] = int((await db.scalar(select(func.count()).select_from(model))) or 0)
    counts["ready_files"] = int(
        (
            await db.scalar(
                select(func.count()).select_from(File).where(File.status == "ready")
            )
        )
        or 0
    )

    def _dir_size(path: Path) -> int:
        total = 0
        try:
            for entry in path.rglob("*"):
                try:
                    if entry.is_file():
                        total += entry.stat().st_size
                except OSError:
                    continue
        except OSError:
            pass
        return total

    def _vector_stats() -> dict:
        try:
            client = vs._get_client()
            mode = "remote" if vs.MILVUS_URI.startswith(("http://", "https://")) else "local"
            collections: dict[str, dict] = {}
            for name in (vs.TEXT_COLLECTION, vs.IMAGE_COLLECTION):
                if not client.has_collection(name):
                    collections[name] = {"exists": False, "rows": 0, "dim": None}
                    continue
                stats = client.get_collection_stats(collection_name=name) or {}
                description = client.describe_collection(collection_name=name) or {}
                dim = None
                for field in description.get("fields", []):
                    if field.get("name") == "embedding":
                        dim = (field.get("params") or {}).get("dim")
                collections[name] = {
                    "exists": True,
                    "rows": int(stats.get("row_count") or 0),
                    "dim": dim,
                }
            return {"mode": mode, "collections": collections}
        except Exception as exc:
            return {"error": str(exc)[:300], "collections": {}}

    def _recent_log_lines(limit: int = 20) -> list[str]:
        log_path = get_data_dir() / "logs" / "backend.log"
        if not log_path.exists():
            return []
        try:
            size = log_path.stat().st_size
            with log_path.open("rb") as handle:
                handle.seek(max(0, size - 200_000))
                text = handle.read().decode("utf-8", errors="replace")
            lines = [
                line
                for line in text.splitlines()
                if (" ERROR " in line or " WARNING " in line) and not _is_benign_log_line(line)
            ]
            return lines[-limit:]
        except OSError:
            return []

    async def _searxng_status() -> dict:
        try:
            base = await config.resolve_searxng_url()
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{base.rstrip('/')}/healthz")
            return {"url": base, "reachable": response.status_code == 200}
        except Exception as exc:
            return {"reachable": False, "error": str(exc)[:200]}

    async def _embedding_status() -> dict:
        from services.embedding_service import _running_port

        source = await config.get_setting("embedding_source", "local")
        if source != "local":
            return {
                "source": source,
                "model": await config.get_setting("embedding_model", ""),
                "local_running": False,
            }

        url = (
            await config.get_setting("embedding_local_url", "")
        ) or config.default_local_embedding_url()
        status_info: dict = {
            "source": source,
            "url": url,
            "local_port": _running_port(),
            "local_running": False,
        }
        # A port file only says the service was started; ask it whether it actually answers.
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{url.rstrip('/')}/health")
            if response.status_code == 200:
                payload = response.json() if response.content else {}
                status_info.update(
                    local_running=True,
                    model=str(payload.get("model") or ""),
                    dim=payload.get("dim"),
                    device=str(payload.get("device") or ""),
                )
            else:
                status_info["error"] = f"HTTP {response.status_code}"
        except Exception as exc:
            status_info["error"] = str(exc)[:200] or exc.__class__.__name__
        return status_info

    async def _llm_status() -> dict:
        key, _base_url, model, api_format = await config.resolve_easy_task_llm_provider_config()
        return {
            "configured": bool(key and model),
            "model": model or "",
            "api_format": api_format or "",
        }

    data_dir = get_data_dir()
    uploads_dir = get_upload_dir()
    data_size, uploads_size = await asyncio.gather(
        asyncio.to_thread(_dir_size, data_dir),
        asyncio.to_thread(_dir_size, uploads_dir),
    )
    disk = shutil.disk_usage(data_dir)

    db_path = database_file()
    vectors_path = milvus_file()
    if db_path and db_path.exists():
        # In WAL mode recent writes live in the -wal file until a checkpoint; count both.
        db_size = sum(
            part.stat().st_size
            for part in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm"))
            if part.exists()
        )
    else:
        db_size = None
    if vectors_path and vectors_path.exists():
        # The Milvus Lite store is a directory; stat() alone would report a few hundred bytes.
        vectors_size = (
            await asyncio.to_thread(_dir_size, vectors_path)
            if vectors_path.is_dir()
            else vectors_path.stat().st_size
        )
    else:
        vectors_size = None

    searxng, embedding, llm = await asyncio.gather(
        _searxng_status(), _embedding_status(), _llm_status()
    )
    vectors = await asyncio.to_thread(_vector_stats)
    recent_logs = await asyncio.to_thread(_recent_log_lines)

    started_at = getattr(request.app.state, "started_at", None)
    return {
        "app": {
            "version": request.app.version,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "uptime_seconds": int(_time.time() - started_at) if started_at else None,
        },
        "database": {
            "path": str(db_path) if db_path else None,
            "size_bytes": db_size,
            "counts": counts,
        },
        "vectors": {
            **vectors,
            "file_size_bytes": vectors_size,
        },
        "storage": {
            "data_dir": str(data_dir),
            "data_bytes": data_size,
            "uploads_bytes": uploads_size,
            "disk_free_bytes": disk.free,
            "disk_total_bytes": disk.total,
        },
        "services": {
            "searxng": searxng,
            "embedding": embedding,
            "llm": llm,
        },
        "logs": {"recent": recent_logs},
    }
