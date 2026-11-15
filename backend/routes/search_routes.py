"""Search inside a project: source texts, notes and results."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import get_current_user
from dependencies.database import get_db
from dependencies.permissions import require_project
from models.user import User

router = APIRouter(prefix="/projects/{project_id}/search", tags=["search"])


@router.get("")
async def search_project(
    project_id: str,
    q: str = Query(min_length=2, max_length=200),
    target: str = Query("all", pattern="^(all|files|features)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    from services.project_search import search_features, search_files

    await require_project(db, project_id, current_user)
    result: dict = {"query": q}
    if target in ("all", "files"):
        result["files"] = await search_files(db, project_id, q)
    if target in ("all", "features"):
        result.update(await search_features(db, project_id, q))
    return result
