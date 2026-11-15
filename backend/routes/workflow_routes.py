import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dependencies.auth import get_current_user
from dependencies.database import get_db
from dependencies.permissions import require_project, require_workflow
from models.feature import Feature
from models.file import File
from models.project import Project
from models.user import User
from models.workflow import Workflow
from services.workflow_titles import ensure_unique_workflow_title
from utils.i18n import msg as ui_msg

logger = logging.getLogger("routes.workflow")

router = APIRouter(prefix="/workflows", tags=["workflows"])


# ---------- request bodies ----------

class WorkflowCustomConfig(BaseModel):
    prompt: Optional[str] = None
    file_ids: list[str] = []
    preset_key: Optional[str] = None
    output_language: Optional[str] = None


class GenerateWorkflowRequest(BaseModel):
    project_id: str
    title: str = ""
    custom_config: Optional[WorkflowCustomConfig] = None


class StatusBatchRequest(BaseModel):
    workflow_ids: list[str] = []


class TitleUpdateRequest(BaseModel):
    title: str


class WorkflowExportRequest(BaseModel):
    include_citations: bool = True
    citation_style: str = "endnote"
    output_language: Optional[str] = None


WORKFLOW_TERMINAL_STATUSES = {"completed", "failed", "partial", "cancelled"}


# ---------- routes (literal paths first) ----------

@router.post("/generate")
async def generate_workflow(
    body: GenerateWorkflowRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    await require_project(db, body.project_id, current_user)

    cfg = body.custom_config or WorkflowCustomConfig()
    if not cfg.file_ids:
        raise HTTPException(status_code=400, detail=ui_msg("select_at_least_one_file"))
    custom_prompt = (cfg.prompt or "").strip()
    if not custom_prompt:
        raise HTTPException(status_code=400, detail=ui_msg("workflow_prompt_missing"))
    workflow_type = (cfg.preset_key or "").strip()
    if not workflow_type:
        raise HTTPException(status_code=400, detail=ui_msg("workflow_type_missing"))
    output_language = (cfg.output_language or "").strip()
    if not output_language:
        raise HTTPException(status_code=400, detail=ui_msg("output_language_missing"))
    result = await db.execute(
        select(File.id).where(
            File.project_id == body.project_id,
            File.id.in_(cfg.file_ids),
        )
    )
    accessible_file_ids = set(result.scalars().all())
    if accessible_file_ids != set(cfg.file_ids):
        raise HTTPException(status_code=404, detail="File not found")

    requested_title = (body.title or "").strip()
    workflow_title = (
        await ensure_unique_workflow_title(db, body.project_id, requested_title)
        if requested_title
        else None
    )

    wf = Workflow(
        project_id=body.project_id,
        workflow_type=workflow_type,
        title=workflow_title,
        status="pending",
        custom_prompt=custom_prompt,
        file_ids_json=json.dumps(cfg.file_ids, ensure_ascii=False),
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)

    redis = request.app.state.redis
    if redis is None:
        wf.status = "failed"
        wf.error_message = ui_msg("queue_unavailable_report")
        await db.commit()
        raise HTTPException(status_code=503, detail=ui_msg("queue_unavailable_report"))

    await redis.enqueue_job("generate_workflow_task", wf.id, output_language)

    return {
        "workflow_id": wf.id,
        "workflow_type": wf.workflow_type,
        "display_name": wf.title or wf.workflow_type or ui_msg("workflow_default_name"),
        "status": wf.status,
        "steps_count": 0,
        "is_finalized": wf.is_finalized,
    }


@router.post("/status/batch")
async def get_workflows_status_batch(
    body: StatusBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not body.workflow_ids:
        return {"workflows": {}}
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.features))
        .join(Project, Workflow.project_id == Project.id)
        .where(Workflow.id.in_(body.workflow_ids), Project.owner_user_id == current_user.id)
    )
    workflows = {wf.id: wf.to_status_dict() for wf in result.scalars().all()}
    return {"workflows": workflows}


@router.get("/project/{project_id}")
async def list_project_workflows(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    await require_project(db, project_id, current_user)
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.features))
        .where(Workflow.project_id == project_id)
        .order_by(Workflow.created_at.desc())
    )
    return {"workflows": [wf.to_list_dict() for wf in result.scalars().all()]}


@router.get("/{workflow_id}/status")
async def get_workflow_status(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    wf = await require_workflow(db, workflow_id, current_user, with_features=True)
    return wf.to_status_dict()


@router.post("/{workflow_id}/cancel")
async def cancel_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    wf = await require_workflow(db, workflow_id, current_user, with_features=True)

    if wf.status in WORKFLOW_TERMINAL_STATUSES:
        return wf.to_status_dict()

    if wf.status == "pending":
        wf.status = "cancelled"
        wf.error_message = ui_msg("workflow_cancelled")
        wf.finished_at = datetime.now(timezone.utc)
        for feature in wf.features or []:
            if feature.status in {"pending", "processing"}:
                feature.status = "cancelled"
                feature.error_message = ui_msg("workflow_cancelled")
                feature.finished_at = datetime.now(timezone.utc)
    else:
        wf.status = "cancelling"
        wf.error_message = ui_msg("workflow_cancelled")
        for feature in wf.features or []:
            if feature.status == "pending":
                feature.status = "cancelled"
                feature.error_message = ui_msg("workflow_cancelled")
                feature.finished_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(wf)
    logger.info("[workflow] cancel requested workflow_id=%s status=%s", workflow_id, wf.status)
    return wf.to_status_dict()


@router.get("/{workflow_id}/content")
async def get_workflow_content(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    wf = await require_workflow(db, workflow_id, current_user, with_features=True)
    return {
        "workflow_id": wf.id,
        "citations": wf.get_citations(),
        "features": [f.to_content_dict() for f in wf.features],
    }


@router.post("/{workflow_id}/export")
async def export_workflow(
    workflow_id: str,
    body: WorkflowExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from services.export_service import export_service

    wf = await require_workflow(db, workflow_id, current_user, with_features=True)

    features = [
        feature.to_content_dict()
        for feature in sorted(wf.features or [], key=lambda item: item.step_index)
    ]
    workflow_citations = wf.get_citations()

    try:
        from services.references import attach_reference_data

        await attach_reference_data(db, [workflow_citations, *(f.get("citations") or {} for f in features)])
        docx_stream, filename = export_service.export_workflow_to_docx(
            workflow_title=wf.title or "",
            features=features,
            citations=workflow_citations,
            include_citations=body.include_citations,
            citation_style=body.citation_style,
            output_language=body.output_language,
        )

        encoded_filename = quote(filename)

        return StreamingResponse(
            docx_stream,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("[workflow] export failed workflow_id=%s", workflow_id)
        raise HTTPException(status_code=500, detail="Export failed. Please try again.")


@router.get("/{workflow_id}")
async def get_workflow_detail(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    wf = await require_workflow(db, workflow_id, current_user, with_features=True)
    return wf.to_detail_dict()


@router.put("/{workflow_id}/title")
async def rename_workflow(
    workflow_id: str,
    body: TitleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    wf = await require_workflow(db, workflow_id, current_user, with_features=True)
    new_title = body.title.strip()
    if new_title:
        wf.title = await ensure_unique_workflow_title(
            db,
            wf.project_id,
            new_title,
            exclude_workflow_id=workflow_id,
        )
    await db.commit()
    return wf.to_list_dict()


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    wf = await require_workflow(db, workflow_id, current_user)
    # SQLite does not cascade foreign keys by default; delete child features explicitly to avoid orphan rows
    await db.execute(sa_delete(Feature).where(Feature.workflow_id == workflow_id))
    await db.delete(wf)
    await db.commit()
