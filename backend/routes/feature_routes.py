import copy
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import get_current_user, get_current_user_query_or_header
from dependencies.database import get_db
from dependencies.permissions import require_project
from agent.blocks_builder import markdown_to_blocks
from models.feature import Feature
from models.file import File
from models.message import Message
from models.session import Session
from models.project import Project
from models.user import User
from paths import get_upload_dir
from utils.i18n import msg as ui_msg
from utils.time import utc_isoformat

logger = logging.getLogger("routes.feature")

router = APIRouter(prefix="/features", tags=["features"])


class FeatureCustomConfig(BaseModel):
    prompt: Optional[str] = None
    title: Optional[str] = None
    file_ids: list[str] = Field(default_factory=list)
    output_language: Optional[str] = None


class GenerateFeatureRequest(BaseModel):
    project_id: str
    feature_type: str
    custom_config: Optional[FeatureCustomConfig] = None


class StatusBatchRequest(BaseModel):
    feature_ids: list[str] = Field(default_factory=list)


class ContentBatchRequest(BaseModel):
    feature_ids: list[str] = Field(default_factory=list)


class FeatureUpdateRequest(BaseModel):
    title: Optional[str] = None
    # Only manual notes can have their body edited.
    content: Optional[str] = None


class NoteCreateRequest(BaseModel):
    project_id: str
    title: Optional[str] = None
    # Save a chat answer: the assistant message to copy, with its citations.
    message_id: Optional[str] = None
    # Or a free-form note written by the user (markdown).
    content: Optional[str] = None


NOTE_FEATURE_TYPE = "note"
NOTE_MAX_CHARS = 200_000
NOTE_TITLE_MAX_CHARS = 120


FEATURE_TYPE_LABELS = {
    "objective_positioning": ("定位分析", "Positioning analysis", "Konumlandırma analizi"),
    "audience_profile": ("受众画像", "Audience profile", "Hedef kitle profili"),
    "comparative_analysis": ("同类分析", "Comparable analysis", "Karşılaştırmalı analiz"),
    "content_summary": ("内容摘要", "Content summary", "İçerik özeti"),
    "timeline": ("时间线", "Timeline", "Zaman çizelgesi"),
    "mind_map": ("思维导图", "Mind map", "Zihin haritası"),
    "flashcards": ("闪卡", "Flashcards", "Bilgi kartları"),
    "quiz": ("测验", "Quiz", "Sınav"),
    "title_suggestion": ("标题生成", "Title suggestions", "Başlık önerileri"),
    "communication_copy": ("传播文案", "Communication copy", "İletişim metni"),
    "audio_overview": ("音频概览", "Audio overview", "Sesli genel bakış"),
    "podcast": ("播客对谈", "Podcast conversation", "Podcast sohbeti"),
    "study_guide": ("学习指南", "Study guide", "Çalışma rehberi"),
    "faq": ("常见问题", "FAQ", "Sık sorulan sorular"),
    "briefing_doc": ("简报文档", "Briefing doc", "Brifing belgesi"),
    "note": ("笔记", "Note", "Not"),
    "deep_research": ("深度研究", "Deep research", "Derin araştırma"),
    "custom_feature": ("快捷工具", "Quick tool", "Özel hızlı araç"),
    "text_section": ("快捷工具", "Quick tool", "Hızlı araç"),
}

_AUDIO_EXT_MIMES = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
    "m4a": "audio/mp4",
}


def _find_feature_audio_path(feature_id: str):
    audio_dir = get_upload_dir() / "feature_audio"
    for ext, mime in _AUDIO_EXT_MIMES.items():
        candidate = audio_dir / f"{feature_id}.{ext}"
        if candidate.is_file():
            return candidate, mime
    return None, None


def _is_chinese_output(language: str | None) -> bool:
    return (language or "").strip().lower().startswith("chinese")


def _is_turkish_output(language: str | None) -> bool:
    return (language or "").strip().lower().startswith(("turkish", "tr", "türkçe"))


def feature_display_name(feature_type: str, output_language: str | None = None) -> str:
    zh, en, tr = FEATURE_TYPE_LABELS.get(
        feature_type,
        (feature_type, feature_type, feature_type),
    )
    if _is_chinese_output(output_language):
        return zh
    if _is_turkish_output(output_language):
        return tr
    return en


def _feature_to_list_dict(feature: Feature) -> dict:
    cfg = feature.get_custom_config()
    return {
        "id": feature.id,
        "feature_type": feature.feature_type,
        "display_name": feature.title or feature.step_name or feature.feature_type,
        "title": feature.title,
        "prompt": cfg.get("prompt"),
        "note_source": cfg.get("note_source") if feature.feature_type == NOTE_FEATURE_TYPE else None,
        "progress": cfg.get("progress") if feature.status in ("pending", "processing") else None,
        "status": feature.status,
        "error_message": feature.error_message,
        "created_at": utc_isoformat(feature.created_at),
        "started_at": utc_isoformat(feature.started_at),
        "finished_at": utc_isoformat(feature.finished_at),
    }


async def _require_feature(db: AsyncSession, feature_id: str, current_user: User) -> Feature:
    result = await db.execute(
        select(Feature)
        .join(Project, Feature.project_id == Project.id)
        .where(
            Feature.id == feature_id,
            Feature.workflow_id.is_(None),
            Project.owner_user_id == current_user.id,
        )
    )
    feature = result.scalar_one_or_none()
    if not feature:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature not found")
    return feature


@router.get("/project/{project_id}")
async def list_project_features(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    await require_project(db, project_id, current_user)
    result = await db.execute(
        select(Feature)
        .where(Feature.project_id == project_id, Feature.workflow_id.is_(None))
        .order_by(Feature.created_at.desc())
    )
    return {"features": [_feature_to_list_dict(feature) for feature in result.scalars().all()]}


@router.post("/generate")
async def generate_feature(
    body: GenerateFeatureRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    await require_project(db, body.project_id, current_user)

    feature_type = (body.feature_type or "").strip()
    if not feature_type:
        raise HTTPException(status_code=400, detail=ui_msg("feature_type_missing"))

    cfg = body.custom_config or FeatureCustomConfig()
    file_ids = [file_id for file_id in (cfg.file_ids or []) if file_id]
    if not file_ids:
        raise HTTPException(status_code=400, detail=ui_msg("select_at_least_one_file"))

    result = await db.execute(
        select(File.id).where(
            File.project_id == body.project_id,
            File.status == "ready",
            File.id.in_(file_ids),
        )
    )
    accessible_file_ids = set(result.scalars().all())
    if accessible_file_ids != set(file_ids):
        raise HTTPException(status_code=404, detail="File not found or not ready")

    output_language = (cfg.output_language or "").strip() or "Chinese"
    display_name = feature_display_name(feature_type, output_language)
    title = (cfg.title or "").strip() or display_name

    feature = Feature(
        project_id=body.project_id,
        workflow_id=None,
        feature_type=feature_type,
        step_index=0,
        step_name=title,
        title=title,
        status="pending",
    )
    feature.set_custom_config({
        "prompt": (cfg.prompt or "").strip(),
        "title": (cfg.title or "").strip(),
        "file_ids": file_ids,
        "output_language": output_language,
    })
    db.add(feature)
    await db.commit()
    await db.refresh(feature)

    redis = request.app.state.redis
    if redis is None:
        feature.status = "failed"
        feature.error_message = ui_msg("queue_unavailable_feature")
        feature.finished_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=503, detail=ui_msg("queue_unavailable_feature"))

    await redis.enqueue_job("generate_feature_task", feature.id, output_language)

    return {
        "feature_id": feature.id,
        "status": feature.status,
        "display_name": display_name,
    }


_THINK_BLOCK_RE = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)
_MD_DECORATION_RE = re.compile(r"[#*_`>\[\]|]+")
_CITATION_TOKEN_RE = re.compile(r"\[citation[_:][^\]]*\]")


def _derive_note_title(markdown: str) -> str:
    """First meaningful line of the note, stripped of markdown decoration."""
    for raw_line in markdown.splitlines():
        line = _CITATION_TOKEN_RE.sub("", raw_line)
        line = _MD_DECORATION_RE.sub("", line).strip(" -–—:\t")
        if len(line) >= 3:
            if len(line) > NOTE_TITLE_MAX_CHARS:
                line = line[: NOTE_TITLE_MAX_CHARS - 1].rstrip() + "…"
            return line
    return ""


def _safe_json_dict(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


async def _load_answer_markdown(
    db: AsyncSession,
    project_id: str,
    message_id: str,
) -> tuple[str, dict, str]:
    """Return (markdown, citation_map, question) for the chat answer containing `message_id`.

    One answer shown in the chat can span several stored assistant messages (one per
    tool-calling round), so the whole run between two user messages is collected.
    Citation metadata lives on the session's tool messages.
    """
    result = await db.execute(
        select(Message)
        .join(Session, Message.session_id == Session.id)
        .where(Message.id == message_id, Session.project_id == project_id)
    )
    target = result.scalar_one_or_none()
    if not target or target.role != "assistant" or target.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    result = await db.execute(
        select(Message)
        .where(Message.session_id == target.session_id, Message.deleted_at.is_(None))
        .order_by(Message.created_at.asc())
    )
    messages = list(result.scalars().all())
    index = next((i for i, m in enumerate(messages) if m.id == target.id), None)
    if index is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    start = index
    while start > 0 and messages[start - 1].role != "user":
        start -= 1
    end = index
    while end + 1 < len(messages) and messages[end + 1].role != "user":
        end += 1

    texts = []
    for message in messages[start : end + 1]:
        if message.role != "assistant" or not message.content:
            continue
        text = _THINK_BLOCK_RE.sub("", message.content).strip()
        if text:
            texts.append(text)

    # Resolve against the map as it stood at the end of this answer's turn; later turns may
    # have reused the same citation keys for other passages (see services/citation_history).
    citation_map: dict = {}
    for message in messages[: end + 1]:
        if message.role == "tool" and message.citations:
            citation_map.update(_safe_json_dict(message.citations))

    question = ""
    if start > 0 and messages[start - 1].role == "user":
        question = (messages[start - 1].content or "").strip()

    return "\n\n".join(texts), citation_map, question


def _build_note_blocks(markdown: str, citation_map: dict) -> tuple[list, dict]:
    """Blocks plus the citations they use, numbered from 1 inside the note."""
    working_map = copy.deepcopy(citation_map)
    for meta in working_map.values():
        if isinstance(meta, dict):
            meta.pop("display_num", None)
    blocks, _ = markdown_to_blocks(markdown, working_map, 1)
    used = {
        cid: meta
        for cid, meta in working_map.items()
        if isinstance(meta, dict) and meta.get("display_num") is not None
    }
    return blocks, used


CHAT_NOTE_REPAIR_SETTING = "chat_note_citations_repaired_v1"


async def repair_chat_note_citations(db: AsyncSession) -> int:
    """Rebuild the citations of notes saved from chat answers, once.

    Notes saved before the per-turn fix resolved their citation keys against the whole
    session, so some point at passages from later turns (or other works). Each note keeps
    the id of the answer it came from, so its blocks can be rebuilt from that answer.
    Returns the number of notes that changed.
    """
    result = await db.execute(select(Feature).where(Feature.feature_type == NOTE_FEATURE_TYPE))
    changed = 0
    for note in result.scalars().all():
        cfg = note.get_custom_config()
        message_id = cfg.get("message_id")
        if cfg.get("note_source") != "chat" or not message_id:
            continue
        try:
            markdown, citation_map, _ = await _load_answer_markdown(db, note.project_id, message_id)
        except HTTPException:
            continue  # the answer was deleted; keep the note as it is
        if not markdown:
            continue
        blocks, citations = _build_note_blocks(markdown, citation_map)
        if citations != note.get_citations() or blocks != note.get_blocks():
            note.set_blocks(blocks)
            note.set_citations(citations)
            changed += 1
    await db.commit()
    return changed


@router.post("/notes", status_code=status.HTTP_201_CREATED)
async def create_note(
    body: NoteCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Save a chat answer (with its citations) or a hand-written text as a note."""
    await require_project(db, body.project_id, current_user)

    citation_map: dict = {}
    question = ""
    if body.message_id:
        markdown, citation_map, question = await _load_answer_markdown(db, body.project_id, body.message_id)
        note_source = "chat"
    else:
        markdown = (body.content or "").strip()
        note_source = "manual"

    if not markdown:
        raise HTTPException(status_code=400, detail="Note content is empty")
    if len(markdown) > NOTE_MAX_CHARS:
        raise HTTPException(status_code=413, detail="Note content is too long")

    blocks, citations = _build_note_blocks(markdown, citation_map)
    # A saved answer is named after the question that produced it.
    title = (
        (body.title or "").strip()[:NOTE_TITLE_MAX_CHARS]
        or _derive_note_title(question)
        or _derive_note_title(markdown)
    )
    if not title:
        title = feature_display_name(NOTE_FEATURE_TYPE, None)

    now = datetime.now(timezone.utc)
    feature = Feature(
        project_id=body.project_id,
        workflow_id=None,
        feature_type=NOTE_FEATURE_TYPE,
        step_index=0,
        step_name=title,
        title=title,
        status="completed",
        started_at=now,
        finished_at=now,
    )
    config = {"note_source": note_source}
    if note_source == "chat":
        config["message_id"] = body.message_id
    else:
        config["markdown"] = markdown
    feature.set_custom_config(config)
    feature.set_blocks(blocks)
    feature.set_citations(citations)
    db.add(feature)
    await db.commit()
    await db.refresh(feature)
    return _feature_to_list_dict(feature)


@router.post("/{feature_id}/regenerate")
async def regenerate_feature(
    feature_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Run a quick tool again in place, with the sources and prompt it was created with."""
    feature = await _require_feature(db, feature_id, current_user)
    if feature.feature_type == NOTE_FEATURE_TYPE:
        raise HTTPException(status_code=400, detail="Notes cannot be regenerated")
    if feature.status in ("pending", "processing"):
        raise HTTPException(status_code=409, detail="Feature is already being generated")
    if feature.feature_type == "deep_research":
        return await _restart_deep_research(feature, request, db)

    cfg = feature.get_custom_config()
    file_ids = [file_id for file_id in (cfg.get("file_ids") or []) if file_id]
    result = await db.execute(
        select(File.id).where(
            File.project_id == feature.project_id,
            File.status == "ready",
            File.id.in_(file_ids),
        )
    )
    available_file_ids = [file_id for file_id in file_ids if file_id in set(result.scalars().all())]
    if not available_file_ids:
        raise HTTPException(status_code=400, detail="The sources used for this result are no longer available")

    redis = request.app.state.redis
    if redis is None:
        raise HTTPException(status_code=503, detail=ui_msg("queue_unavailable_feature"))

    cfg["file_ids"] = available_file_ids
    feature.set_custom_config(cfg)
    feature.status = "pending"
    feature.error_message = None
    feature.started_at = None
    feature.finished_at = None
    feature.set_blocks([])
    feature.set_citations({})
    await db.commit()

    audio_path, _ = _find_feature_audio_path(feature.id)
    if audio_path:
        audio_path.unlink(missing_ok=True)

    output_language = (cfg.get("output_language") or "").strip() or "Chinese"
    await redis.enqueue_job("generate_feature_task", feature.id, output_language)
    return _feature_to_list_dict(feature)


async def _restart_deep_research(feature: Feature, request: Request, db: AsyncSession) -> dict:
    """Run a deep research again from the start, with its original topic and scope."""
    redis = request.app.state.redis
    if redis is None:
        raise HTTPException(status_code=503, detail=ui_msg("queue_unavailable_feature"))
    cfg = feature.get_custom_config()
    # "collected" (sources read before a failed report) is kept: the job then only rewrites the report.
    for key in ("sources", "subquestions", "markdown"):
        cfg.pop(key, None)
    cfg["progress"] = ui_msg("research_queued")
    feature.set_custom_config(cfg)
    feature.status = "pending"
    feature.error_message = None
    feature.started_at = None
    feature.finished_at = None
    feature.set_blocks([])
    feature.set_citations({})
    await db.commit()
    await redis.enqueue_job("deep_research_task", feature.id, cfg.get("output_language"))
    return _feature_to_list_dict(feature)


@router.post("/status/batch")
async def get_features_status_batch(
    body: StatusBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not body.feature_ids:
        return {"features": {}}
    result = await db.execute(
        select(Feature)
        .join(Project, Feature.project_id == Project.id)
        .where(
            Feature.id.in_(body.feature_ids),
            Feature.workflow_id.is_(None),
            Project.owner_user_id == current_user.id,
        )
    )
    return {
        "features": {
            feature.id: _feature_to_list_dict(feature)
            for feature in result.scalars().all()
        }
    }


@router.post("/content/batch")
async def get_features_content_batch(
    body: ContentBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not body.feature_ids:
        return {"features": {}}
    result = await db.execute(
        select(Feature)
        .join(Project, Feature.project_id == Project.id)
        .where(
            Feature.id.in_(body.feature_ids),
            Feature.workflow_id.is_(None),
            Project.owner_user_id == current_user.id,
        )
    )
    return {
        "features": {
            feature.id: feature.to_content_dict()
            for feature in result.scalars().all()
        }
    }


@router.get("/{feature_id}")
async def get_feature(
    feature_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    feature = await _require_feature(db, feature_id, current_user)
    return feature.to_content_dict()


@router.get("/{feature_id}/references")
async def get_feature_references(
    feature_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """For downloads: each cited work's current name, page and one sentence to search for."""
    from services.references import build_references

    feature = await _require_feature(db, feature_id, current_user)
    citations = feature.get_citations()
    references = await build_references(db, citations.values())
    return {
        "references": {
            citation_id: references[id(meta)]
            for citation_id, meta in citations.items()
            if isinstance(meta, dict) and id(meta) in references
        }
    }


@router.get("/{feature_id}/audio")
async def get_feature_audio(
    feature_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_query_or_header),
):
    feature = await _require_feature(db, feature_id, current_user)
    audio_path, mime_type = _find_feature_audio_path(feature.id)
    if not audio_path:
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(
        path=str(audio_path),
        media_type=mime_type or "audio/mpeg",
        filename=audio_path.name,
        content_disposition_type="inline",
    )


@router.put("/{feature_id}")
async def update_feature(
    feature_id: str,
    body: FeatureUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    feature = await _require_feature(db, feature_id, current_user)
    title = (body.title or "").strip()
    if title:
        feature.title = title
        feature.step_name = title

    if body.content is not None:
        cfg = feature.get_custom_config()
        if feature.feature_type != NOTE_FEATURE_TYPE or cfg.get("note_source") != "manual":
            raise HTTPException(status_code=400, detail="Only hand-written notes can be edited")
        markdown = body.content.strip()
        if not markdown:
            raise HTTPException(status_code=400, detail="Note content is empty")
        if len(markdown) > NOTE_MAX_CHARS:
            raise HTTPException(status_code=413, detail="Note content is too long")
        blocks, citations = _build_note_blocks(markdown, {})
        cfg["markdown"] = markdown
        feature.set_custom_config(cfg)
        feature.set_blocks(blocks)
        feature.set_citations(citations)

    await db.commit()
    await db.refresh(feature)
    return {
        "id": feature.id,
        "title": feature.title,
        "updated_at": utc_isoformat(datetime.now(timezone.utc)),
    }


@router.delete("/{feature_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feature(
    feature_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    feature = await _require_feature(db, feature_id, current_user)
    audio_path, _ = _find_feature_audio_path(feature.id)
    if audio_path:
        audio_path.unlink(missing_ok=True)
    await db.execute(sa_delete(Feature).where(Feature.id == feature.id))
    await db.commit()
