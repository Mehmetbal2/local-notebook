import os
import sys
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")
os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packages"))

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from arq.connections import RedisSettings
from arq.worker import func

from utils.i18n import msg as ui_msg, set_language as set_ui_language

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
WORKFLOW_STEP_CONCURRENCY = int(os.getenv("WORKFLOW_STEP_CONCURRENCY", "3"))
WORKFLOW_FEATURE_TIMEOUT = int(os.getenv("WORKFLOW_FEATURE_TIMEOUT", "900"))
WORKFLOW_CANCEL_REQUESTED_STATUSES = {"cancelling", "cancelled"}
WORKFLOW_CANCELLED_STEP_MESSAGE = "__workflow_cancelled__"


class WorkflowCancelled(RuntimeError):
    """Raised when a workflow has been cancelled by the user."""


class FileProcessingCancelled(BaseException):
    """Raised inside parse_file_task when the user stopped or deleted the file.

    It derives from BaseException so the broad `except Exception` blocks around optional
    steps (summaries, image descriptions) cannot swallow it.
    """


FILE_CANCELLED_STATUS = "cancelled"


async def _raise_if_file_cancelled(file_id: str) -> None:
    """Stop processing when the file was stopped (status 'cancelled') or deleted meanwhile."""
    from sqlalchemy import select
    from database import AsyncSessionLocal
    from models.file import File

    async with AsyncSessionLocal() as check_db:
        status = (
            await check_db.execute(select(File.status).where(File.id == file_id))
        ).scalar_one_or_none()
    if status is None or status == FILE_CANCELLED_STATUS:
        raise FileProcessingCancelled()


from contextlib import asynccontextmanager


async def _shielded_commit(db) -> None:
    commit_task = asyncio.ensure_future(db.commit())
    try:
        await asyncio.shield(commit_task)
    except asyncio.CancelledError:
        try:
            await commit_task
        except Exception:
            pass
        raise


async def _safe_close(db) -> None:
    last_exc: Exception | None = None
    for attempt in range(20):
        close_task = asyncio.ensure_future(db.close())
        try:
            await asyncio.shield(close_task)
            return
        except asyncio.CancelledError:
            try:
                await close_task
            except Exception:
                pass
            return
        except Exception as exc:
            last_exc = exc
            if attempt < 19:
                await asyncio.sleep(0.05)
    if last_exc is not None:
        logger.debug("close skipped after retries: %s", last_exc)


@asynccontextmanager
async def _safe_session(session_factory):
    db = session_factory()
    try:
        yield db
    finally:
        await _safe_close(db)


async def _discard_cancelled_file(session_factory, file_id: str, project_id: str) -> None:
    """Remove whatever a stopped run already stored and leave the file marked 'cancelled'."""
    from sqlalchemy import delete as sa_delete
    from models.block import Block
    from models.file import File
    from models.image import Image
    from models.segment import Segment
    from services.vector_service import delete_by_file

    async with _safe_session(session_factory) as cleanup_db:
        await cleanup_db.execute(sa_delete(Segment).where(Segment.file_id == file_id))
        await cleanup_db.execute(sa_delete(Block).where(Block.file_id == file_id))
        await cleanup_db.execute(sa_delete(Image).where(Image.file_id == file_id))
        db_file = await cleanup_db.get(File, file_id)
        if db_file is not None:
            db_file.status = FILE_CANCELLED_STATUS
            db_file.error_message = None
            db_file.processing_message = None
            db_file.updated_at = datetime.now(timezone.utc)
        await _shielded_commit(cleanup_db)
    try:
        await asyncio.to_thread(delete_by_file, project_id, file_id)
    except Exception as exc:
        logger.warning(f"could not remove vectors of stopped file {file_id}: {exc}")


def _exception_message(exc: BaseException) -> str:
    message = str(exc).strip()
    if message:
        return message
    return exc.__class__.__name__


async def _safe_rollback(db) -> None:
    last_exc: Exception | None = None
    for attempt in range(20):
        rb_task = asyncio.ensure_future(db.rollback())
        try:
            await asyncio.shield(rb_task)
            return
        except asyncio.CancelledError:
            try:
                await rb_task
            except Exception:
                pass
            raise
        except Exception as exc:
            last_exc = exc
            if attempt < 19:
                await asyncio.sleep(0.05)
    if last_exc is not None:
        logger.debug("rollback skipped after retries: %s", last_exc)


async def _commit_file_progress(
    db,
    db_file,
    current: int | None = None,
    total: int | None = None,
    message: str | None = None,
) -> None:
    if current is not None:
        db_file.processing_current = max(0, int(current))
    if total is not None:
        db_file.processing_total = max(1, int(total))
        if db_file.processing_current is not None:
            db_file.processing_current = min(db_file.processing_current, db_file.processing_total)
    if message is not None:
        db_file.processing_message = message or None
    db_file.updated_at = datetime.now(timezone.utc)
    await _shielded_commit(db)
    if db_file.status != "ready":
        await _raise_if_file_cancelled(db_file.id)


class FileProgressTracker:
    def __init__(self, db, db_file, total: int, min_interval: float = 0.5):
        self.db = db
        self.db_file = db_file
        self.total = max(1, int(total))
        self.current = 0
        self.min_interval = min_interval
        self.last_flush = 0.0
        self.lock = asyncio.Lock()

    async def start(self) -> None:
        async with self.lock:
            self.current = 0
            await self._flush(force=True, message="")

    async def advance(self, amount: int = 1, force: bool = False) -> None:
        async with self.lock:
            self.current = min(self.total, self.current + max(0, int(amount)))
            await self._flush(force=force)

    async def finish(self) -> None:
        async with self.lock:
            self.current = self.total
            await self._flush(force=True, message="")

    async def _flush(self, force: bool = False, message: str | None = None) -> None:
        now = time.monotonic()
        if not force and self.current < self.total and now - self.last_flush < self.min_interval:
            return
        await _commit_file_progress(
            self.db,
            self.db_file,
            current=self.current,
            total=self.total,
            message=message,
        )
        self.last_flush = now


def _file_processing_message(file_type: str | None) -> str:
    if file_type == "pdf":
        return ui_msg("processing_pdf")
    if file_type in {"wav", "mp3", "m4a"}:
        return ui_msg("processing_audio")
    if file_type in {"jpg", "jpeg", "png"}:
        return ui_msg("processing_image")
    return ui_msg("processing_text")


async def _get_workflow_status(session_factory, workflow_id: str) -> str | None:
    from sqlalchemy import select
    from models.workflow import Workflow

    async with session_factory() as db:
        result = await db.execute(
            select(Workflow.status).where(Workflow.id == workflow_id)
        )
        return result.scalar_one_or_none()


async def _is_workflow_cancel_requested(session_factory, workflow_id: str) -> bool:
    status = await _get_workflow_status(session_factory, workflow_id)
    # A deleted workflow has no row left; stop it like a cancelled one instead of
    # letting it run to the end in the background.
    return status is None or status in WORKFLOW_CANCEL_REQUESTED_STATUSES


async def _raise_if_workflow_cancelled(session_factory, workflow_id: str) -> None:
    if await _is_workflow_cancel_requested(session_factory, workflow_id):
        raise WorkflowCancelled(ui_msg("workflow_cancelled"))


async def _mark_workflow_cancelled(
    session_factory,
    workflow_id: str,
    message: str | None = None,
) -> None:
    from sqlalchemy import select

    message = message or ui_msg("workflow_cancelled")
    from models.feature import Feature
    from models.workflow import Workflow

    async with session_factory() as db:
        wf = await db.get(Workflow, workflow_id)
        if not wf:
            return

        if wf.status not in {"completed", "partial"}:
            wf.status = "cancelled"
            wf.error_message = message
            wf.finished_at = datetime.now(timezone.utc)

        result = await db.execute(
            select(Feature).where(
                Feature.workflow_id == workflow_id,
                Feature.status.in_(["pending", "processing"]),
            )
        )
        for feat in result.scalars().all():
            feat.status = "cancelled"
            feat.error_message = message
            feat.finished_at = datetime.now(timezone.utc)

        await _shielded_commit(db)


async def on_startup(ctx: dict) -> None:
    from database import AsyncSessionLocal, engine, Base, ensure_runtime_schema
    import models

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await ensure_runtime_schema(conn, logger)

    ctx["session_factory"] = AsyncSessionLocal

    await _recover_stuck_files(AsyncSessionLocal)
    try:
        from workers.deep_research import recover_deep_research

        await recover_deep_research(AsyncSessionLocal, await _get_arq_pool())
    except Exception:
        logger.exception("Could not restart interrupted deep research jobs")
    from services.feature_agent_trace_service import cleanup_expired_feature_agent_traces
    await cleanup_expired_feature_agent_traces()

    logger.info("ARQ worker started")


async def _recover_stuck_files(session_factory) -> None:
    from sqlalchemy import select, func, delete as sa_delete
    from models.file import File
    from models.segment import Segment
    from models.block import Block
    from models.image import Image
    from services.local_queue import get_active_local_queue
    from services.vector_service import delete_by_file

    async with _safe_session(session_factory) as db:
        result = await db.execute(
            select(File).where(File.status.in_(["processing", "pending"]))
        )
        stuck = result.scalars().all()
        if not stuck:
            return

        logger.warning(f"Found {len(stuck)} file(s) stuck in 'processing'/'pending', recovering...")
        arq_pool = await _get_arq_pool()

        from uuid import uuid4
        to_enqueue: list[tuple[str, str, str, str, str | None]] = []
        for f in stuck:
            seg_count_res = await db.execute(
                select(func.count()).select_from(Segment).where(Segment.file_id == f.id)
            )
            has_segments = (seg_count_res.scalar() or 0) > 0
            task_name = "reembed_file_task" if has_segments else "parse_file_task"
            logger.info(f"Recovering file {f.id} ({f.file_name}) via {task_name}")
            if not has_segments:
                await db.execute(sa_delete(Segment).where(Segment.file_id == f.id))
                await db.execute(sa_delete(Block).where(Block.file_id == f.id))
                await db.execute(sa_delete(Image).where(Image.file_id == f.id))
            new_job_id = uuid4().hex
            f.status = "pending"
            f.job_id = new_job_id
            f.error_message = None
            f.processing_current = 0
            f.processing_total = None
            f.processing_message = None
            to_enqueue.append((f.id, f.project_id, new_job_id, task_name, f.output_language))

        await _shielded_commit(db)

    for fid, pid, new_job_id, task_name, language in to_enqueue:
        try:
            await asyncio.to_thread(delete_by_file, pid, fid)
        except Exception as exc:
            logger.warning(f"Could not delete old vectors for recovered file {fid}: {exc}")
        if arq_pool is not None:
            try:
                # Without the stored language a recovered file would be summarized in English.
                await arq_pool.enqueue_job(task_name, fid, language, _job_id=new_job_id)
                logger.info(f"Re-enqueued file {fid} ({task_name}, job_id={new_job_id})")
            except Exception as exc:
                logger.warning(f"Could not enqueue recovered file {fid} ({task_name}): {exc}")

    if arq_pool is not None and arq_pool is not get_active_local_queue():
        await arq_pool.aclose()


async def _get_arq_pool():
    from services.local_queue import get_active_local_queue
    local_q = get_active_local_queue()
    if local_q is not None:
        return local_q

    from arq import create_pool
    try:
        return await create_pool(RedisSettings.from_dsn(REDIS_URL))
    except Exception as e:
        logger.error(f"Cannot connect to Redis for re-enqueue: {e}")
        return None


async def on_shutdown(ctx: dict) -> None:
    from database import engine
    await engine.dispose()
    logger.info("ARQ worker stopped")


async def parse_file_task(
    ctx: dict,
    file_id: str,
    output_language: str | None = None,
) -> dict:
    set_ui_language(output_language)
    from models.file import File
    from models.project import Project

    session_factory = ctx["session_factory"]
    stop_reason: str | None = None
    project_id = ""
    # Set once blocks, segments and their (paid) summaries are committed. A failure after
    # that point must not send the whole file back through the queue's retry, which would
    # delete them and pay for every summary again.
    content_saved = False

    async with _safe_session(session_factory) as db:
        db_file = await db.get(File, file_id)
        if not db_file:
            logger.error(f"parse_file_task: file {file_id} not found")
            return {"status": "error", "reason": "file not found"}

        if db_file.status == FILE_CANCELLED_STATUS:
            logger.info(f"parse_file_task: file {file_id} was stopped before it started")
            return {"status": "cancelled", "file_id": file_id}

        file_name = db_file.file_name
        file_type = db_file.file_type
        from paths import resolve_stored_path
        file_path = resolve_stored_path(
            db_file.file_path,
            project_id=db_file.project_id,
            file_name=file_name,
        )
        project_id = db_file.project_id
        project = await db.get(Project, project_id)
        user_id = project.owner_user_id if project else None
        if output_language:
            # Remember the chosen language so a later reprocess without an explicit
            # language keeps it instead of falling back to English.
            db_file.output_language = output_language

        try:
            logger.info(f"Parsing file {file_id} ({file_name}, type={file_type})")

            from models.segment import Segment
            from models.block import Block
            from models.image import Image
            from sqlalchemy import delete as sa_delete
            from services.vector_service import delete_by_file
            await asyncio.to_thread(delete_by_file, project_id, file_id)

            await db.execute(sa_delete(Segment).where(Segment.file_id == file_id))
            await db.execute(sa_delete(Block).where(Block.file_id == file_id))
            await db.execute(sa_delete(Image).where(Image.file_id == file_id))

            db_file.status = "processing"
            db_file.error_message = None
            db_file.processing_current = 0
            db_file.processing_total = None
            db_file.processing_message = _file_processing_message(file_type)
            await _shielded_commit(db)

            import config
            _, emb_base_url, _, emb_api_key = await config.resolve_embedding_config()
            if not emb_base_url:
                raise RuntimeError(ui_msg("embedding_url_missing"))
            emb_source = await config.get_setting("embedding_source", "local")
            if emb_source != "local" and not emb_api_key:
                raise RuntimeError(ui_msg("embedding_key_missing"))

            logger.info(f"[{file_name}] step 1/5: extracting text & creating blocks")
            text, blocks, raw_images = await _extract_text_and_blocks(
                file_type,
                file_path,
                file_id=file_id,
                db=db,
                output_language=output_language,
            )
            logger.info(f"[{file_name}] extracted {len(text)} chars, {len(blocks)} blocks, {len(raw_images)} raw images")

            await _raise_if_file_cancelled(file_id)
            images_meta = await _describe_images(file_name, raw_images, output_language=output_language)
            await _raise_if_file_cancelled(file_id)

            if not blocks:
                logger.warning(f"[{file_name}] no blocks produced, marking ready")
                await _raise_if_file_cancelled(file_id)
                db_file.status = "ready"
                await _commit_file_progress(db, db_file, current=1, total=1, message="")
                return {"status": "ok", "file_id": file_id, "segments": 0}

            logger.info(f"[{file_name}] step 2/5: segmenting from {len(blocks)} blocks")
            from services.segment_service import segment_service
            split_result = segment_service.split_text_with_warnings(text, blocks)
            segments = split_result.segments
            for w in split_result.warnings:
                logger.warning(f"[{file_name}] segment warning: {w}")

            if not segments:
                logger.warning(f"[{file_name}] no segments produced, marking ready")
                await _raise_if_file_cancelled(file_id)
                db_file.status = "ready"
                await _commit_file_progress(db, db_file, current=1, total=1, message="")
                return {"status": "ok", "file_id": file_id, "segments": 0}

            logger.info(f"[{file_name}] {len(segments)} segments")

            segment_summaries: dict[int, str] = {}
            llm_summary_indices: set[int] = set()
            llm_cfg = None
            generate_segment_summaries = None
            ak = bu = md = fmt = ""
            progress_units_per_pass = max(1, len(segments))
            summary_language = output_language
            try:
                from services.summary_service import (
                    _resolve_llm,
                    generate_segment_summaries,
                    normalize_output_language,
                )
                import config as _config
                llm_cfg = await _resolve_llm()
                if llm_cfg:
                    ak, bu, md, fmt = llm_cfg
                    summary_language = normalize_output_language(output_language)
                    economy = await _config.is_easy_task_llm_configured()
                    logger.info(
                        f"[{file_name}] step 2.5: generating summaries for {len(segments)} "
                        f"segments (model={md}, format={fmt}, economy={economy}, "
                        f"language={summary_language})"
                    )
                else:
                    logger.info(f"[{file_name}] LLM not configured, skipping segment summaries")
            except Exception as e:
                llm_cfg = None
                logger.warning(f"[{file_name}] segment summary setup failed, continuing: {e}")
            standard_total = progress_units_per_pass + 1
            if llm_cfg:
                standard_total += progress_units_per_pass + 1
            if images_meta:
                standard_total += len(images_meta)
            progress = FileProgressTracker(db, db_file, standard_total)
            await progress.start()

            if llm_cfg and generate_segment_summaries is not None:
                try:
                    seg_inputs = [{"segment_index": s.segment_index, "content": s.content} for s in segments]
                    summary_batch = await generate_segment_summaries(
                        seg_inputs,
                        ak,
                        bu,
                        md,
                        api_format=fmt,
                        output_language=summary_language,
                        user_id=user_id,
                        progress_callback=progress.advance,
                    )
                    segment_summaries = summary_batch.summaries
                    llm_summary_indices = summary_batch.llm_indices
                    logger.info(
                        f"[{file_name}] summaries generated: "
                        f"{len(segment_summaries)}/{len(segments)} "
                        f"(llm={len(llm_summary_indices)})"
                    )
                except Exception as e:
                    remaining_summary_units = max(0, progress_units_per_pass - progress.current)
                    if remaining_summary_units:
                        await progress.advance(remaining_summary_units, force=True)
                    logger.warning(f"[{file_name}] segment summary step failed, continuing: {e}")

            await _raise_if_file_cancelled(file_id)
            logger.info(f"[{file_name}] step 3/5: storing blocks, segments & images")
            from services.vector_service import (
                ensure_collection, upsert_chunks,
                ensure_image_collection, upsert_image_chunks
            )
            from models.block import Block
            from models.image import Image
            import json as _json

            # Persist the parsed content and the (paid) LLM summaries BEFORE embedding.
            # If the embedding service is briefly unreachable, these rows survive on the
            # failed file and a later reprocess routes to reembed_file_task, which rebuilds
            # only the vectors instead of re-running OCR/LLM from scratch.
            await db.execute(sa_delete(Block).where(Block.file_id == file_id))
            await db.execute(sa_delete(Segment).where(Segment.file_id == file_id))
            await db.execute(sa_delete(Image).where(Image.file_id == file_id))

            db_blocks = [
                Block(
                    id=f"{file_id}_{b['id']}",
                    file_id=file_id,
                    block_id=b['id'],
                    block_index=i,
                    block_type=b['type'],
                    content=b['content'],
                    pos_start=b['position']['start'],
                    pos_end=b['position']['end'],
                    page=b.get('page', 0),
                    extra=_json.dumps(b.get('extra')) if b.get('extra') else None,
                )
                for i, b in enumerate(blocks)
            ]
            db.add_all(db_blocks)
            await db.flush()
            logger.info(f"[{file_name}] stored {len(db_blocks)} blocks")

            db_segments = [
                Segment(
                    id=f"{file_id}_s_{s.segment_index}",
                    file_id=file_id,
                    project_id=project_id,
                    segment_index=s.segment_index,
                    content=s.content,
                    summary=segment_summaries.get(s.segment_index),
                    pos_start=s.pos_start,
                    pos_end=s.pos_end,
                    block_ids=_json.dumps(s.block_ids) if s.block_ids else None,
                )
                for s in segments
            ]
            db.add_all(db_segments)
            await db.flush()

            db_image_count = 0
            if images_meta:
                db_images = [
                    Image(
                        id=f"{file_id}_img_{img['image_index']}",
                        file_id=file_id,
                        image_index=img["image_index"],
                        description=img["description"],
                        vlm_model=img.get("vlm_model"),
                    )
                    for img in images_meta
                ]
                db.add_all(db_images)
                db_image_count = len(db_images)
                await db.flush()

            await _shielded_commit(db)
            logger.info(
                f"[{file_name}] committed {len(db_blocks)} blocks, "
                f"{len(db_segments)} segments, {db_image_count} images "
                f"(summaries preserved before embedding)"
            )
            content_saved = True

            await _raise_if_file_cancelled(file_id)
            logger.info(f"[{file_name}] step 4/5: embedding {len(segments)} segments")
            from services.embedding_service import embed_texts
            contents = [s.content for s in segments]
            vectors = await embed_texts(contents, progress_callback=progress.advance)
            dim = len(vectors[0])
            logger.info(f"[{file_name}] embedding done, dim={dim}")
            await asyncio.to_thread(ensure_collection, project_id, dim)

            chunks = [
                {
                    "id":            f"{file_id}_s_{s.segment_index}",
                    "file_id":       file_id,
                    "file_name":     file_name,
                    "segment_index": s.segment_index,
                    "content":       s.content,
                    "summary":       segment_summaries.get(s.segment_index) or "",
                    "embedding":     vectors[i],
                }
                for i, s in enumerate(segments)
            ]
            await asyncio.to_thread(upsert_chunks, project_id, chunks)

            if images_meta:
                logger.info(f"[{file_name}] storing {len(images_meta)} images")
                await asyncio.to_thread(ensure_image_collection, project_id, dim)

                image_descriptions = [img["description"] for img in images_meta]
                image_vectors = await embed_texts(image_descriptions, progress_callback=progress.advance)

                image_chunks = [
                    {
                        "id":            f"{file_id}_img_{img['image_index']}",
                        "file_id":       file_id,
                        "file_name":     file_name,
                        "image_index":   img["image_index"],
                        "description":   img["description"],
                        "embedding":     image_vectors[i],
                    }
                    for i, img in enumerate(images_meta)
                ]
                await asyncio.to_thread(upsert_image_chunks, project_id, image_chunks)
                logger.info(f"[{file_name}] stored {len(images_meta)} images to vector db")
            await progress.advance(1, force=True)

            try:
                if llm_cfg and segment_summaries:
                    from services.summary_service import generate_file_summary
                    ak, bu, md, fmt = llm_cfg

                    logger.info(f"[{file_name}] step 5.1: generating file summary")
                    ordered = [segment_summaries[s.segment_index]
                               for s in segments if s.segment_index in segment_summaries]
                    preferred = [
                        segment_summaries[s.segment_index]
                        for s in segments
                        if s.segment_index in llm_summary_indices
                        and segment_summaries.get(s.segment_index)
                    ]
                    file_result = await generate_file_summary(
                        file_name,
                        ordered,
                        ak,
                        bu,
                        md,
                        api_format=fmt,
                        output_language=output_language,
                        user_id=user_id,
                        preferred_summaries=preferred,
                    )
                    if file_result["summary"]:
                        db_file.summary = file_result["summary"]
                    if file_result["keywords"]:
                        db_file.keywords = _json.dumps(file_result["keywords"], ensure_ascii=False)
                    logger.info(f"[{file_name}] file summary done")
                else:
                    logger.info(f"[{file_name}] skipping file/project summaries (LLM not configured or no segment summaries)")
            except Exception as e:
                logger.warning(f"[{file_name}] file/project summary failed, continuing: {e}")
            if llm_cfg:
                await progress.advance(1, force=True)

            await _raise_if_file_cancelled(file_id)
            db_file.status = "ready"
            await progress.finish()

            try:
                if llm_cfg and segment_summaries:
                    ak, bu, md, fmt = llm_cfg
                    logger.info(f"[{file_name}] step 5.2: generating project summary")
                    await _update_project_summary(
                        db,
                        project_id,
                        ak,
                        bu,
                        md,
                        fmt,
                        output_language=output_language,
                        user_id=user_id,
                    )
            except Exception as e:
                logger.warning(f"[{file_name}] project summary failed, continuing: {e}")

            logger.info(f"[{file_name}] done: {len(blocks)} blocks, {len(segments)} segments, {len(images_meta)} images stored")
            return {"status": "ok", "file_id": file_id, "blocks": len(blocks), "segments": len(segments), "images": len(images_meta)}

        except FileProcessingCancelled:
            logger.info(f"[{file_name}] processing stopped by the user")
            await _safe_rollback(db)
            stop_reason = "stopped"

        except asyncio.CancelledError:
            logger.info(f"[{file_name}] processing task cancelled")
            await _safe_rollback(db)
            stop_reason = "task_cancelled"

        except Exception as exc:
            logger.exception(f"Failed to parse file {file_id}: {exc}")
            await _safe_rollback(db)
            db_file = await db.get(File, file_id)
            if not db_file:
                # Deleted while it was being processed: nothing left to mark or retry.
                return {"status": "error", "reason": "file deleted"}
            db_file.status = "failed"
            db_file.error_message = str(exc)
            db_file.updated_at = datetime.now(timezone.utc)
            await _shielded_commit(db)
            if not content_saved:
                raise
            # The content and summaries are stored; only the vector stage failed. Rebuild the
            # vectors from them instead of letting the queue re-run the whole parse.
            await _queue_vector_rebuild(file_id, output_language)
            return {"status": "failed", "file_id": file_id, "content_saved": True}

    # Clean up only after the session above is closed: its transaction may still hold the
    # SQLite write lock until then, and a second session would wait on it.
    if stop_reason is not None:
        try:
            await asyncio.shield(_discard_cancelled_file(session_factory, file_id, project_id))
        except Exception as exc:
            logger.warning(f"could not clean up stopped file {file_id}: {exc}")
        if stop_reason == "task_cancelled":
            raise asyncio.CancelledError()
    return {"status": "cancelled", "file_id": file_id}


async def _queue_vector_rebuild(file_id: str, output_language: str | None) -> None:
    """Queue reembed_file_task for a file whose content is stored but whose vectors failed."""
    try:
        queue = await _get_arq_pool()
        if queue is None:
            return
        try:
            await queue.enqueue_job("reembed_file_task", file_id, output_language)
            logger.info(f"Queued a vector rebuild for {file_id} after the embedding step failed")
        finally:
            from services.local_queue import get_active_local_queue

            if queue is not get_active_local_queue():
                await queue.aclose()
    except Exception as exc:
        logger.warning(f"Could not queue a vector rebuild for {file_id}: {exc}")


async def _generate_missing_file_summary(db, db_file, segments, output_language: str | None) -> None:
    """Regenerate the file-level overview for a file that never reached that step.

    A parse that fails while embedding leaves stored segments (and their summaries) but
    no file summary, because the overview is produced after embedding. Recovery through
    reembed_file_task would then mark the file ready without an overview, so fill it in
    there when it is missing. Failures stay non-fatal: the vectors are already rebuilt.
    """
    import json as _json
    from models.project import Project
    from services.summary_service import (
        _resolve_llm,
        generate_file_summary,
        normalize_output_language,
    )

    stored = [s.summary for s in segments if (s.summary or "").strip()]
    if not stored:
        return
    try:
        llm_cfg = await _resolve_llm()
        if not llm_cfg:
            return
        ak, bu, md, fmt = llm_cfg
        project = await db.get(Project, db_file.project_id)
        user_id = project.owner_user_id if project else None
        result = await generate_file_summary(
            db_file.file_name,
            stored,
            ak,
            bu,
            md,
            api_format=fmt,
            output_language=normalize_output_language(output_language),
            user_id=user_id,
        )
        if result.get("summary"):
            db_file.summary = result["summary"]
        if result.get("keywords"):
            db_file.keywords = _json.dumps(result["keywords"], ensure_ascii=False)
        if result.get("summary") or result.get("keywords"):
            await _shielded_commit(db)
            logger.info(f"[{db_file.file_name}] missing file summary regenerated after re-embed")
    except Exception as exc:
        logger.warning(
            f"[{db_file.file_name}] could not regenerate file summary after re-embed: {exc}"
        )


async def reembed_file_task(
    ctx: dict,
    file_id: str,
    output_language: str | None = None,
) -> dict:
    """Re-vectorize an already parsed file from its stored SQLite segments & image descriptions without re-running OCR/LLM/VLM."""
    set_ui_language(output_language)
    from sqlalchemy import select, asc
    from models.file import File
    from models.segment import Segment
    from models.image import Image
    from services.embedding_service import embed_texts
    from services.vector_service import (
        delete_by_file,
        ensure_collection,
        ensure_image_collection,
        upsert_chunks,
        upsert_image_chunks,
    )

    session_factory = ctx["session_factory"]
    async with _safe_session(session_factory) as db:
        db_file = await db.get(File, file_id)
        if not db_file:
            return {"status": "error", "reason": "file not found"}
        if db_file.status == FILE_CANCELLED_STATUS:
            return {"status": "cancelled", "file_id": file_id}

        seg_res = await db.execute(
            select(Segment).where(Segment.file_id == file_id).order_by(asc(Segment.segment_index))
        )
        segments = list(seg_res.scalars().all())
        if not segments:
            # No stored segments in SQLite; fall back to full parse.
            pass
        else:
            img_res = await db.execute(
                select(Image).where(Image.file_id == file_id).order_by(asc(Image.image_index))
            )
            images = [img for img in img_res.scalars().all() if (img.description or "").strip()]

            file_name = db_file.file_name
            project_id = db_file.project_id
            total_units = len(segments) + len(images) + 1

            db_file.status = "processing"
            db_file.error_message = None
            db_file.processing_current = 0
            db_file.processing_total = total_units
            db_file.processing_message = ui_msg("reembedding_vectors")
            await _shielded_commit(db)

            progress = FileProgressTracker(db, db_file, total_units)
            await progress.start()

            try:
                try:
                    await asyncio.to_thread(delete_by_file, project_id, file_id)
                except Exception as exc:
                    logger.debug(f"[{file_name}] delete_by_file before re-embed skipped: {exc}")

                await _raise_if_file_cancelled(file_id)
                contents = [s.content for s in segments]
                vectors = await embed_texts(contents, progress_callback=progress.advance)
                dim = len(vectors[0])
                await asyncio.to_thread(ensure_collection, project_id, dim)

                chunks = [
                    {
                        "id":            s.id,
                        "file_id":       file_id,
                        "file_name":     file_name,
                        "segment_index": s.segment_index,
                        "content":       s.content,
                        "summary":       s.summary or "",
                        "embedding":     vectors[i],
                    }
                    for i, s in enumerate(segments)
                ]
                await asyncio.to_thread(upsert_chunks, project_id, chunks)

                if images:
                    await _raise_if_file_cancelled(file_id)
                    await asyncio.to_thread(ensure_image_collection, project_id, dim)
                    image_descriptions = [img.description for img in images]
                    image_vectors = await embed_texts(image_descriptions, progress_callback=progress.advance)
                    image_chunks = [
                        {
                            "id":          img.id,
                            "file_id":     file_id,
                            "file_name":   file_name,
                            "image_index": img.image_index,
                            "description": img.description,
                            "embedding":   image_vectors[i],
                        }
                        for i, img in enumerate(images)
                    ]
                    await asyncio.to_thread(upsert_image_chunks, project_id, image_chunks)

                if not (db_file.summary or "").strip():
                    await _generate_missing_file_summary(db, db_file, segments, output_language)

                db_file.status = "ready"
                db_file.error_message = None
                db_file.processing_message = None
                await progress.finish()
                logger.info(f"[{file_name}] re-embedded {len(segments)} segments and {len(images)} images (dim={dim})")
                return {"status": "ok", "file_id": file_id, "segments": len(segments), "images": len(images)}

            except (FileProcessingCancelled, asyncio.CancelledError) as exc:
                await _safe_rollback(db)
                try:
                    db_file = await db.get(File, file_id)
                    if db_file is not None:
                        db_file.status = FILE_CANCELLED_STATUS
                        db_file.processing_message = None
                        await _shielded_commit(db)
                except Exception:
                    pass
                if isinstance(exc, asyncio.CancelledError):
                    raise
                return {"status": "cancelled", "file_id": file_id}
            except Exception as exc:
                logger.exception(f"Failed to re-embed file {file_id}: {exc}")
                await _safe_rollback(db)
                try:
                    db_file = await db.get(File, file_id)
                    if db_file is not None:
                        db_file.status = "failed"
                        db_file.error_message = str(exc)
                        db_file.processing_message = None
                        await _shielded_commit(db)
                except Exception:
                    pass
                raise

    return await parse_file_task(ctx, file_id, output_language=output_language)


async def _update_project_summary(
    db,
    project_id: str,
    api_key: str,
    base_url: str | None,
    model: str,
    api_format: str,
    output_language: str | None = None,
    user_id: str | None = None,
) -> None:
    from sqlalchemy import select
    from models.file import File
    from models.project import Project
    from services.summary_service import generate_project_overview

    result = await db.execute(
        select(File).where(File.project_id == project_id, File.status == "ready", File.summary.isnot(None))
    )
    ready_files = result.scalars().all()

    project = await db.get(Project, project_id)
    if not project:
        await _shielded_commit(db)
        return
    project_name = project.name
    project_description = project.description

    file_summaries = [
        {"file_name": f.file_name, "summary": f.summary}
        for f in ready_files if f.summary
    ]

    await _shielded_commit(db)

    if not file_summaries:
        return

    overview = await generate_project_overview(
        project_name,
        file_summaries,
        api_key,
        base_url,
        model,
        api_format=api_format,
        project_description=project_description,
        output_language=output_language,
        user_id=user_id,
    )
    summary = overview.get("summary")
    color = overview.get("color")
    if summary or color:
        # Update with an explicit rowcount instead of a cached ORM object: the project can
        # be deleted while the model is writing, and a stale UPDATE would raise
        # "expected to update 1 row(s); 0 were matched".
        from sqlalchemy import update

        values: dict[str, str] = {}
        if summary:
            values["summary"] = summary
        if color:
            values["color"] = color
        result = await db.execute(
            update(Project).where(Project.id == project_id).values(**values)
        )
        if not result.rowcount:
            await db.rollback()
            logger.info(
                "Project %s was deleted while its overview was generated; update dropped",
                project_id,
            )
            return
        await _shielded_commit(db)
        logger.info(
            f"Project {project_id} overview updated "
            f"({len(summary or '')} chars, color={color or 'unchanged'})"
        )


async def refresh_project_summary_task(
    ctx: dict,
    project_id: str,
    output_language: str | None = None,
) -> dict:
    """Rebuild a project's overview after its set of sources changed (e.g. a file was deleted)."""
    from models.project import Project
    from services.summary_service import _resolve_llm

    set_ui_language(output_language)
    session_factory = ctx["session_factory"]
    async with _safe_session(session_factory) as db:
        project = await db.get(Project, project_id)
        if not project:
            return {"status": "skipped", "reason": "project not found"}
        llm_cfg = await _resolve_llm()
        if not llm_cfg:
            return {"status": "skipped", "reason": "llm not configured"}
        ak, bu, md, fmt = llm_cfg
        await _update_project_summary(
            db,
            project_id,
            ak,
            bu,
            md,
            fmt,
            output_language=output_language,
            user_id=project.owner_user_id,
        )
        return {"status": "ok", "project_id": project_id}


async def _describe_images(
    file_name: str,
    raw_images: list,
    output_language: str | None = None,
) -> list:
    if not raw_images:
        return []

    described_images = [img for img in raw_images if img.get("description")]
    pending_images = [img for img in raw_images if not img.get("description")]
    if not pending_images:
        logger.info(
            f"[{file_name}] step 1.5/5: reusing {len(described_images)} "
            "already described images"
        )
        return described_images

    from services.vlm_client import describe_image, resolve_vlm_config

    try:
        api_key, base_url, model = await resolve_vlm_config()
        if not api_key or not model:
            logger.warning(
                f"[{file_name}] VLM not configured, skipping descriptions of {len(pending_images)} images"
            )
            return described_images
    except Exception:
        logger.warning(f"[{file_name}] could not read the VLM configuration, skipping image descriptions")
        return described_images

    logger.info(
        f"[{file_name}] step 1.5/5: VLM describing {len(pending_images)} "
        f"images (model={model}, concurrency=2)"
    )

    from services.summary_service import normalize_output_language
    summary_language = normalize_output_language(output_language)

    PROMPT = (
        "Briefly describe this image. Focus on:\n"
        "1. The image's main subject and content.\n"
        "2. Key visual elements such as chart data, visible text, objects, or scenes.\n"
        "Use 50-100 words.\n\n"
        f"Output language: {summary_language}"
    )

    semaphore = asyncio.Semaphore(5)

    async def _describe_one(img: dict):
        async with semaphore:
            image_path = img.get("file_path")
            if not image_path:
                logger.warning(
                    f"[{file_name}] image {img.get('image_index', '?')} has no file_path, skipping"
                )
                return None
            try:
                description, vlm_model = await describe_image(image_path, prompt=PROMPT)
                logger.info(
                    f"[{file_name}] image {img['image_index']} "
                    f"described ({len(description)} chars)"
                )
                return {**img, "description": description, "vlm_model": vlm_model}
            except Exception as exc:
                logger.warning(
                    f"[{file_name}] image {img['image_index']} VLM description failed, skipping: {exc}"
                )
                return None

    results = await asyncio.gather(*[_describe_one(img) for img in pending_images])
    return described_images + [r for r in results if r is not None]


async def _extract_text_and_blocks(
    file_type: str | None, file_path: str,
    file_id: str | None = None, db=None,
    output_language: str | None = None,
) -> tuple[str, list, list]:
    from workers.parsers import get_parser_for_file

    if file_type in ("txt", "md", "markdown", "htm", "html", "pdf", "docx", "doc", "epub", "wav", "mp3", "m4a"):
        parser = get_parser_for_file(file_path)
        if file_type in ("pdf", "htm", "html"):
            result = await parser.parse(file_path, file_id=file_id, db=db)
        else:
            result = await parser.parse(file_path)

        blocks = [
            {
                "id": b.id,
                "type": b.type,
                "content": b.content,
                "position": b.position,
                "page": b.page,
                "extra": b.extra,
            }
            for b in result.blocks
        ]

        return result.text, blocks, result.images

    elif file_type in {"jpg", "jpeg", "png"}:
        parser = get_parser_for_file(file_path)
        result = await parser.parse(file_path, output_language=output_language)

        blocks = [
            {
                "id": b.id,
                "type": b.type,
                "content": b.content,
                "position": b.position,
                "page": b.page,
                "extra": b.extra,
            }
            for b in result.blocks
        ]

        return result.text, blocks, result.images

    logger.info(f"No text extractor for file_type={file_type!r}, skipping")
    return "", [], []


def _build_workflow_execution_layers(feature_items: list[dict]) -> list[list[dict]]:
    """Build DAG execution layers from feature custom_config step_id/depends_on."""
    by_step_id: dict[str, dict] = {}
    errors: list[str] = []
    for item in feature_items:
        step_id = item.get("step_id")
        if not step_id:
            errors.append(f"feature {item.get('id')} is missing step_id")
            continue
        if step_id in by_step_id:
            errors.append(f"duplicate step_id: {step_id}")
            continue
        by_step_id[step_id] = item

    for item in feature_items:
        step_id = item.get("step_id")
        if not step_id:
            continue
        for dep_id in item.get("depends_on") or []:
            dep = by_step_id.get(dep_id)
            if not dep:
                errors.append(f"step {step_id!r} depends on unknown step_id {dep_id!r}")

    if errors:
        raise RuntimeError("; ".join(errors))

    layers: dict[str, int] = {}
    visiting: set[str] = set()

    def layer_of(step_id: str) -> int:
        if step_id in layers:
            return layers[step_id]
        if step_id in visiting:
            raise RuntimeError(f"dependency cycle detected at step_id {step_id!r}")
        visiting.add(step_id)
        item = by_step_id[step_id]
        deps = item.get("depends_on") or []
        layer = 0 if not deps else max(layer_of(dep_id) for dep_id in deps) + 1
        visiting.remove(step_id)
        layers[step_id] = layer
        return layer

    for step_id in by_step_id:
        layer_of(step_id)

    grouped: dict[int, list[dict]] = {}
    for item in feature_items:
        grouped.setdefault(layers[item["step_id"]], []).append(item)

    return [
        sorted(grouped[layer], key=lambda item: item["order_index"])
        for layer in sorted(grouped.keys())
    ]


def _build_workflow_dependency_ancestors(feature_items: list[dict]) -> dict[str, list[str]]:
    """Return all transitive upstream dependency step_ids for each step, in display order."""
    by_step_id = {
        item["step_id"]: item
        for item in feature_items
        if item.get("step_id")
    }
    order_index = {
        step_id: item["order_index"]
        for step_id, item in by_step_id.items()
    }
    ancestors: dict[str, set[str]] = {}
    visiting: set[str] = set()

    def collect(step_id: str) -> set[str]:
        if step_id in ancestors:
            return ancestors[step_id]
        if step_id in visiting:
            raise RuntimeError(f"dependency cycle detected at step_id {step_id!r}")
        visiting.add(step_id)
        item = by_step_id[step_id]
        result: set[str] = set()
        for dep_id in item.get("depends_on") or []:
            if dep_id not in by_step_id:
                raise RuntimeError(f"step {step_id!r} depends on unknown step_id {dep_id!r}")
            result.add(dep_id)
            result.update(collect(dep_id))
        visiting.remove(step_id)
        ancestors[step_id] = result
        return result

    return {
        step_id: sorted(collect(step_id), key=lambda dep_id: order_index.get(dep_id, 0))
        for step_id in by_step_id
    }


def _build_workflow_dependency_graph(
    feature_items: list[dict],
) -> tuple[dict[str, dict], dict[str, set[str]], dict[str, list[str]]]:
    """Validate a workflow DAG and return step lookup, remaining deps, and dependents."""
    by_step_id: dict[str, dict] = {}
    errors: list[str] = []

    for item in feature_items:
        step_id = item.get("step_id")
        if not step_id:
            errors.append(f"feature {item.get('id')} is missing step_id")
            continue
        if step_id in by_step_id:
            errors.append(f"duplicate step_id: {step_id}")
            continue
        by_step_id[step_id] = item

    remaining_deps: dict[str, set[str]] = {
        step_id: set()
        for step_id in by_step_id
    }
    dependents: dict[str, list[str]] = {
        step_id: []
        for step_id in by_step_id
    }

    for item in feature_items:
        step_id = item.get("step_id")
        if not step_id or step_id not in by_step_id:
            continue
        for dep_id in item.get("depends_on") or []:
            if dep_id not in by_step_id:
                errors.append(f"step {step_id!r} depends on unknown step_id {dep_id!r}")
                continue
            remaining_deps[step_id].add(dep_id)
            dependents[dep_id].append(step_id)

    if errors:
        raise RuntimeError("; ".join(errors))

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visited:
            return
        if step_id in visiting:
            raise RuntimeError(f"dependency cycle detected at step_id {step_id!r}")
        visiting.add(step_id)
        for dep_id in remaining_deps[step_id]:
            visit(dep_id)
        visiting.remove(step_id)
        visited.add(step_id)

    for step_id in by_step_id:
        visit(step_id)

    for step_id, child_ids in dependents.items():
        child_ids.sort(key=lambda child_id: by_step_id[child_id]["order_index"])

    return by_step_id, remaining_deps, dependents


async def generate_workflow_task(
    ctx: dict,
    workflow_id: str,
    output_language: str | None = None,
) -> dict:
    """Plan a report, then generate it section by section."""
    set_ui_language(output_language)
    from datetime import datetime, timezone

    from agent.feature_agent import FeatureAgent
    from agent.capabilities import DEFAULT_FEATURE_TYPE
    from agent.tools.query_knowledge_base import CitationState
    from models.feature import Feature
    from models.project import Project
    from models.workflow import Workflow
    from services.workflow_citations import (
        convert_local_feature_to_workflow,
        finalize_workflow_citations,
    )
    from services.workflow_planner import generate_workflow_title, plan_workflow
    from services.workflow_titles import ensure_unique_workflow_title

    session_factory = ctx["session_factory"]
    workflow_started_at = time.perf_counter()
    output_language = (output_language or "").strip()

    # 1) Load the workflow and mark it processing
    async with session_factory() as db:
        from sqlalchemy import update as sa_update

        wf = await db.get(Workflow, workflow_id)
        if not wf:
            logger.error(f"generate_workflow_task: workflow {workflow_id} not found")
            return {"status": "error", "reason": "workflow not found"}
        if wf.status in WORKFLOW_CANCEL_REQUESTED_STATUSES:
            wf.status = "cancelled"
            wf.error_message = wf.error_message or ui_msg("workflow_cancelled")
            wf.finished_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("[workflow] cancelled before start workflow_id=%s", workflow_id)
            return {"status": "cancelled", "workflow_id": workflow_id}
        project_id = wf.project_id
        project = await db.get(Project, project_id)
        user_id = project.owner_user_id if project else None
        workflow_type = wf.workflow_type
        custom_prompt = wf.custom_prompt or ""
        file_ids = wf.get_file_ids()
        user_title = wf.title
        started_at = datetime.now(timezone.utc)
        result = await db.execute(
            sa_update(Workflow)
            .where(
                Workflow.id == workflow_id,
                Workflow.status.notin_(WORKFLOW_CANCEL_REQUESTED_STATUSES),
            )
            .values(status="processing", started_at=started_at)
        )
        await db.commit()
        if result.rowcount == 0:
            logger.info("[workflow] cancelled before processing claim workflow_id=%s", workflow_id)
            await _mark_workflow_cancelled(session_factory, workflow_id)
            return {"status": "cancelled", "workflow_id": workflow_id}

    logger.info(
        "[workflow] start workflow_id=%s project_id=%s type=%s title=%r "
        "file_ids=%s custom_prompt_chars=%d custom_prompt_preview=%r",
        workflow_id,
        project_id,
        workflow_type,
        user_title,
        file_ids,
        len(custom_prompt),
        custom_prompt[:200],
    )

    try:
        if not output_language:
            raise ValueError(ui_msg("output_language_missing"))

        await _raise_if_workflow_cancelled(session_factory, workflow_id)

        # 2) Without a title, generate one from the user's requirements before planning
        if not user_title:
            await _raise_if_workflow_cancelled(session_factory, workflow_id)
            user_title = await generate_workflow_title(
                custom_prompt,
                project_id=project_id,
                file_ids=file_ids,
                output_language=output_language,
                user_id=user_id,
                cancellation_check=lambda: _raise_if_workflow_cancelled(
                    session_factory,
                    workflow_id,
                ),
            )
            await _raise_if_workflow_cancelled(session_factory, workflow_id)
            async with session_factory() as db:
                wf = await db.get(Workflow, workflow_id)
                if wf:
                    if wf.status in WORKFLOW_CANCEL_REQUESTED_STATUSES:
                        raise WorkflowCancelled(ui_msg("workflow_cancelled"))
                    if wf.title:
                        user_title = wf.title
                    else:
                        user_title = await ensure_unique_workflow_title(
                            db,
                            project_id,
                            user_title,
                            exclude_workflow_id=workflow_id,
                        )
                        wf.title = user_title
                        await db.commit()
            logger.info(
                "[workflow] generated title workflow_id=%s title=%r",
                workflow_id,
                user_title,
            )

        # 3) Plan the sections
        await _raise_if_workflow_cancelled(session_factory, workflow_id)
        plan = await plan_workflow(
            project_id=project_id,
            custom_prompt=custom_prompt,
            file_ids=file_ids,
            report_title=user_title or "",
            output_language=output_language,
            user_id=user_id,
            cancellation_check=lambda: _raise_if_workflow_cancelled(
                session_factory,
                workflow_id,
            ),
        )
        await _raise_if_workflow_cancelled(session_factory, workflow_id)
        steps = plan["steps"]
        plan_title = user_title or ""
        logger.info(
            "[workflow] plan workflow_id=%s:\n%s",
            workflow_id,
            json.dumps(plan, ensure_ascii=False, indent=2),
        )

        # 4) Store the plan and create the feature rows
        async with session_factory() as db:
            wf = await db.get(Workflow, workflow_id)
            if wf and wf.status in WORKFLOW_CANCEL_REQUESTED_STATUSES:
                raise WorkflowCancelled(ui_msg("workflow_cancelled"))
            wf.plan_json = json.dumps(plan, ensure_ascii=False)
            if not wf.title:
                plan_title = await ensure_unique_workflow_title(
                    db,
                    project_id,
                    plan_title,
                    exclude_workflow_id=workflow_id,
                )
                wf.title = plan_title
            for idx, step in enumerate(steps):
                feat = Feature(
                    project_id=project_id,
                    workflow_id=workflow_id,
                    feature_type=DEFAULT_FEATURE_TYPE,
                    step_index=idx,
                    step_name=step["step_name"],
                    title=step["step_name"],
                    status="pending",
                )
                feat.set_custom_config({
                    "prompt": custom_prompt,
                    "file_ids": file_ids,
                    "step_id": step.get("step_id"),
                    "depends_on": step.get("depends_on", []),
                    "instruction": step.get("instruction", ""),
                })
                db.add(feat)
            await db.commit()
    except WorkflowCancelled:
        logger.info("[workflow] cancelled during planning workflow_id=%s", workflow_id)
        await _mark_workflow_cancelled(session_factory, workflow_id)
        return {"status": "cancelled", "workflow_id": workflow_id}
    except Exception as exc:
        logger.exception(f"workflow {workflow_id} planning failed: {exc}")
        async with session_factory() as db:
            wf = await db.get(Workflow, workflow_id)
            if wf:
                wf.status = "failed"
                wf.error_message = ui_msg("planning_failed", error=exc)
                wf.finished_at = datetime.now(timezone.utc)
                await db.commit()
        raise

    # 4) Schedule generation along the planner's dependency graph; each section gets its own CitationState.
    from sqlalchemy import select

    if await _is_workflow_cancel_requested(session_factory, workflow_id):
        logger.info("[workflow] cancelled before generation workflow_id=%s", workflow_id)
        await _mark_workflow_cancelled(session_factory, workflow_id)
        return {"status": "cancelled", "workflow_id": workflow_id}

    async with session_factory() as db:
        wf = await db.get(Workflow, workflow_id)
        result = await db.execute(
            select(Feature).where(Feature.workflow_id == workflow_id).order_by(Feature.step_index)
        )
        features = list(result.scalars().all())
        feature_items = []
        for feature in features:
            cfg = feature.get_custom_config()
            depends_on = cfg.get("depends_on") or []
            if isinstance(depends_on, str):
                depends_on = [depends_on]
            feature_items.append({
                "id": feature.id,
                "order_index": feature.step_index,
                "step_id": cfg.get("step_id"),
                "depends_on": depends_on,
                "step_name": feature.step_name,
                "feature_type": feature.feature_type,
            })
        dependency_ancestors = _build_workflow_dependency_ancestors(feature_items)
        by_step_id, remaining_deps, dependents = _build_workflow_dependency_graph(feature_items)
        report_title = wf.title or plan_title
    total_steps = len(feature_items)
    initial_ready = [
        step_id
        for step_id, deps in remaining_deps.items()
        if not deps
    ]
    initial_ready.sort(key=lambda step_id: by_step_id[step_id]["order_index"])
    concurrency_limit = max(1, WORKFLOW_STEP_CONCURRENCY)
    logger.info(
        "[workflow] generation begin workflow_id=%s report_title=%r total_steps=%d initial_ready=%s concurrency=%d",
        workflow_id,
        report_title,
        total_steps,
        initial_ready,
        concurrency_limit,
    )

    agent = FeatureAgent()
    completed = 0
    failed = 0
    failed_step_ids: dict[str, str] = {}

    async def mark_feature_failed(item: dict, message: str) -> None:
        async with session_factory() as db:
            feat = await db.get(Feature, item["id"])
            if feat:
                feat.status = "failed"
                feat.error_message = message
                feat.finished_at = datetime.now(timezone.utc)
                await db.commit()

    async def mark_feature_cancelled(item: dict, message: str | None = None) -> None:
        message = message or ui_msg("workflow_cancelled")
        async with session_factory() as db:
            feat = await db.get(Feature, item["id"])
            if feat and feat.status in {"pending", "processing"}:
                feat.status = "cancelled"
                feat.error_message = message
                feat.finished_at = datetime.now(timezone.utc)
                await db.commit()

    async def run_feature(item: dict) -> tuple[str, bool, str]:
        step_started_at = time.perf_counter()
        feat_id = item["id"]
        step_id = item["step_id"]
        step_index = item["order_index"]
        step_name = item["step_name"]
        feature_type = item["feature_type"] or DEFAULT_FEATURE_TYPE

        await _raise_if_workflow_cancelled(session_factory, workflow_id)

        async with session_factory() as db:
            feat = await db.get(Feature, feat_id)
            if not feat:
                return step_id, False, "feature not found"
            if feat.status == "cancelled":
                raise WorkflowCancelled(ui_msg("workflow_cancelled"))
            feat.status = "processing"
            feat.started_at = datetime.now(timezone.utc)
            feat.error_message = None
            await db.commit()
            custom_config = feat.get_custom_config()
            instruction = custom_config.get("instruction", "")
            depends_on = custom_config.get("depends_on") or []
            accessible_dependencies = dependency_ancestors.get(step_id, [])

        logger.info(
            "[workflow] step start workflow_id=%s step=%d/%d step_id=%s feature_id=%s type=%s "
            "name=%r depends_on=%s accessible_dependencies=%s instruction_chars=%d instruction_preview=%r",
            workflow_id,
            step_index + 1,
            total_steps,
            step_id,
            feat_id,
            feature_type,
            step_name,
            depends_on,
            accessible_dependencies,
            len(instruction),
            instruction[:240],
        )

        try:
            citation_state = CitationState()
            citation_state.project_id = project_id
            citation_state.file_ids = file_ids or None
            citation_state.workflow_id = workflow_id
            citation_state.current_step_id = step_id
            citation_state.current_feature_id = feat_id
            citation_state.depends_on = list(accessible_dependencies or [])

            feature_generation = agent.generate(
                report_title=report_title,
                step_name=step_name,
                instruction=instruction,
                feature_type=feature_type,
                custom_prompt=custom_prompt,
                citation_state=citation_state,
                start_display_num=1,
                user_id=user_id,
                cancellation_check=lambda: _raise_if_workflow_cancelled(
                    session_factory,
                    workflow_id,
                ),
            )
            if WORKFLOW_FEATURE_TIMEOUT > 0:
                blocks, local_citations, _ = await asyncio.wait_for(
                    feature_generation,
                    timeout=WORKFLOW_FEATURE_TIMEOUT,
                )
            else:
                blocks, local_citations, _ = await feature_generation
            await _raise_if_workflow_cancelled(session_factory, workflow_id)
            workflow_blocks, workflow_citations = convert_local_feature_to_workflow(
                blocks,
                local_citations,
                step_id,
            )
            async with session_factory() as db:
                feat = await db.get(Feature, feat_id)
                feat.set_blocks(workflow_blocks)
                feat.set_citations(workflow_citations)
                feat.status = "completed"
                feat.finished_at = datetime.now(timezone.utc)
                await db.commit()
            logger.info(
                "[workflow] step done workflow_id=%s step=%d/%d step_id=%s feature_id=%s name=%r "
                "blocks=%d local_citations=%d workflow_citations=%d elapsed=%.2fs",
                workflow_id,
                step_index + 1,
                total_steps,
                step_id,
                feat_id,
                step_name,
                len(workflow_blocks),
                len(local_citations or {}),
                len(workflow_citations or {}),
                time.perf_counter() - step_started_at,
            )
            return step_id, True, ""
        except WorkflowCancelled:
            logger.info(
                "[workflow] step cancelled workflow_id=%s step=%d/%d step_id=%s feature_id=%s name=%r "
                "elapsed=%.2fs",
                workflow_id,
                step_index + 1,
                total_steps,
                step_id,
                feat_id,
                step_name,
                time.perf_counter() - step_started_at,
            )
            await mark_feature_cancelled(item)
            return step_id, False, WORKFLOW_CANCELLED_STEP_MESSAGE
        except asyncio.TimeoutError as exc:
            message = ui_msg("section_timeout", seconds=WORKFLOW_FEATURE_TIMEOUT)
            logger.exception(
                "[workflow] step timeout workflow_id=%s step=%d/%d step_id=%s feature_id=%s name=%r "
                "elapsed=%.2fs timeout=%ds",
                workflow_id,
                step_index + 1,
                total_steps,
                step_id,
                feat_id,
                step_name,
                time.perf_counter() - step_started_at,
                WORKFLOW_FEATURE_TIMEOUT,
            )
            await mark_feature_failed(item, message)
            return step_id, False, message
        except Exception as exc:
            message = _exception_message(exc)
            logger.exception(
                "[workflow] step failed workflow_id=%s step=%d/%d step_id=%s feature_id=%s name=%r "
                "elapsed=%.2fs error=%s",
                workflow_id,
                step_index + 1,
                total_steps,
                step_id,
                feat_id,
                step_name,
                time.perf_counter() - step_started_at,
                message,
            )
            await mark_feature_failed(item, message)
            return step_id, False, message

    ready_queue = list(initial_ready)
    ready_set = set(ready_queue)
    pending_step_ids = set(by_step_id.keys())
    completed_step_ids: set[str] = set()
    running_tasks: dict[asyncio.Task, dict] = {}

    def enqueue_if_ready(step_id: str) -> None:
        if step_id not in pending_step_ids:
            return
        if step_id in ready_set or step_id in failed_step_ids:
            return
        if remaining_deps.get(step_id):
            return
        ready_queue.append(step_id)
        ready_set.add(step_id)
        ready_queue.sort(key=lambda queued_id: by_step_id[queued_id]["order_index"])

    def remove_from_ready(step_id: str) -> None:
        nonlocal ready_queue
        if step_id not in ready_set:
            return
        ready_set.discard(step_id)
        ready_queue = [queued_id for queued_id in ready_queue if queued_id != step_id]

    def launch_ready_tasks() -> None:
        while ready_queue and len(running_tasks) < concurrency_limit:
            step_id = ready_queue.pop(0)
            ready_set.discard(step_id)
            if step_id not in pending_step_ids or step_id in failed_step_ids:
                continue
            item = by_step_id[step_id]
            pending_step_ids.remove(step_id)
            task = asyncio.create_task(run_feature(item))
            running_tasks[task] = item
            logger.info(
                "[workflow] step scheduled workflow_id=%s step_id=%s running=%d queued=%d pending=%d",
                workflow_id,
                step_id,
                len(running_tasks),
                len(ready_queue),
                len(pending_step_ids),
            )

    async def mark_blocked_descendants(root_step_id: str) -> list[str]:
        nonlocal failed
        skipped: list[str] = []
        stack = list(dependents.get(root_step_id, []))
        seen: set[str] = set()

        while stack:
            step_id = stack.pop(0)
            if step_id in seen:
                continue
            seen.add(step_id)
            stack.extend(dependents.get(step_id, []))

            if step_id in completed_step_ids or step_id in failed_step_ids:
                continue
            if any(item["step_id"] == step_id for item in running_tasks.values()):
                logger.warning(
                    "[workflow] dependency failed while descendant is already running "
                    "workflow_id=%s failed_step_id=%s descendant_step_id=%s",
                    workflow_id,
                    root_step_id,
                    step_id,
                )
                continue

            failed_deps = [
                dep_id for dep_id in (by_step_id[step_id].get("depends_on") or [])
                if dep_id in failed_step_ids or dep_id == root_step_id
            ]
            message = f"dependency failed: {', '.join(failed_deps or [root_step_id])}"
            await mark_feature_failed(by_step_id[step_id], message)
            failed_step_ids[step_id] = message
            failed += 1
            pending_step_ids.discard(step_id)
            remove_from_ready(step_id)
            skipped.append(step_id)

        return skipped

    try:
        while pending_step_ids or running_tasks:
            if await _is_workflow_cancel_requested(session_factory, workflow_id):
                raise WorkflowCancelled(ui_msg("workflow_cancelled"))

            launch_ready_tasks()

            if not running_tasks:
                if pending_step_ids:
                    stalled = sorted(
                        pending_step_ids,
                        key=lambda step_id: by_step_id[step_id]["order_index"],
                    )
                    logger.error(
                        "[workflow] scheduler stalled workflow_id=%s pending=%s",
                        workflow_id,
                        stalled,
                    )
                    for step_id in stalled:
                        message = "dependency graph stalled"
                        await mark_feature_failed(by_step_id[step_id], message)
                        failed_step_ids[step_id] = message
                        failed += 1
                    pending_step_ids.clear()
                break

            done, _ = await asyncio.wait(
                list(running_tasks.keys()),
                return_when=asyncio.FIRST_COMPLETED,
                timeout=2.0,
            )
            if not done:
                continue

            succeeded_step_ids: list[str] = []
            for task in done:
                item = running_tasks.pop(task)
                step_id = item["step_id"]
                try:
                    result = task.result()
                except WorkflowCancelled:
                    await mark_feature_cancelled(item)
                    raise
                except Exception as exc:
                    message = _exception_message(exc)
                    await mark_feature_failed(item, message)
                    result = (step_id, False, message)

                result_step_id, ok, message = result
                if ok:
                    completed += 1
                    completed_step_ids.add(result_step_id)
                    succeeded_step_ids.append(result_step_id)
                    continue

                if message == WORKFLOW_CANCELLED_STEP_MESSAGE:
                    raise WorkflowCancelled(ui_msg("workflow_cancelled"))

                failed_step_ids[result_step_id] = message
                failed += 1
                skipped = await mark_blocked_descendants(result_step_id)
                logger.info(
                    "[workflow] step failed propagated workflow_id=%s step_id=%s skipped=%s completed=%d failed=%d",
                    workflow_id,
                    result_step_id,
                    skipped,
                    completed,
                    failed,
                )

            if succeeded_step_ids:
                if await _is_workflow_cancel_requested(session_factory, workflow_id):
                    raise WorkflowCancelled(ui_msg("workflow_cancelled"))

                async with session_factory() as db:
                    await finalize_workflow_citations(db, workflow_id)
                    await db.commit()

                for step_id in succeeded_step_ids:
                    for child_id in dependents.get(step_id, []):
                        if child_id in failed_step_ids:
                            continue
                        remaining_deps[child_id].discard(step_id)
                        enqueue_if_ready(child_id)

                logger.info(
                    "[workflow] scheduler progress workflow_id=%s completed=%d failed=%d newly_ready=%s running=%d pending=%d",
                    workflow_id,
                    completed,
                    failed,
                    list(ready_queue),
                    len(running_tasks),
                    len(pending_step_ids),
                )
    except WorkflowCancelled:
        logger.info("[workflow] cancelled during generation workflow_id=%s", workflow_id)
        for task in running_tasks:
            task.cancel()
        if running_tasks:
            await asyncio.gather(*running_tasks.keys(), return_exceptions=True)
        await _mark_workflow_cancelled(session_factory, workflow_id)
        return {"status": "cancelled", "workflow_id": workflow_id}

    # 5) Summarize the workflow status
    if await _is_workflow_cancel_requested(session_factory, workflow_id):
        logger.info("[workflow] cancelled before finalizing workflow_id=%s", workflow_id)
        await _mark_workflow_cancelled(session_factory, workflow_id)
        return {"status": "cancelled", "workflow_id": workflow_id}

    if completed == 0:
        final_status = "failed"
    elif failed > 0:
        final_status = "partial"
    else:
        final_status = "completed"

    async with session_factory() as db:
        wf = await db.get(Workflow, workflow_id)
        wf.status = final_status
        wf.finished_at = datetime.now(timezone.utc)
        await db.commit()

    logger.info(
        "[workflow] finished workflow_id=%s status=%s completed=%d failed=%d elapsed=%.2fs",
        workflow_id,
        final_status,
        completed,
        failed,
        time.perf_counter() - workflow_started_at,
    )
    return {"status": final_status, "workflow_id": workflow_id, "completed": completed, "failed": failed}


FEATURE_INSTRUCTION_TEMPLATES = {
    "objective_positioning": (
        "Analyze the selected source materials and produce a focused positioning analysis. "
        "Identify the core objective, audience-facing value, differentiation points, and practical recommendations."
    ),
    "audience_profile": (
        "Analyze the selected source materials and produce an audience profile. "
        "Identify core audience groups, their needs, motivations, concerns, and messaging implications."
    ),
    "comparative_analysis": (
        "Analyze the selected source materials and produce a comparable analysis. "
        "Compare relevant entities, claims, options, or approaches from the sources and explain the key differences."
    ),
    "content_summary": (
        "Summarize the selected source materials with a clear structure. "
        "Highlight the core thesis, main sections/themes, key arguments and supporting evidence, and essential takeaways."
    ),
    "timeline": (
        "Analyze the selected source materials and construct a timeline or ordered progression: chronological events, "
        "historical periods, biographical milestones, or the stages of a process or argument.\n"
        "Output format (strict — the result is rendered as an interactive timeline):\n"
        "1. Start with one short overview paragraph.\n"
        "2. Optionally group entries under `## <era or phase>` headings.\n"
        "3. Every entry is a `### <date, period or stage label> | <short title>` heading (the ` | ` separator is required), "
        "followed by one paragraph of 1-3 sentences saying what happened and why it matters, ending with its [citation_X] markers.\n"
        "4. Keep entries in order, 8-20 entries, and do not use tables or bullet lists for the entries."
    ),
    "mind_map": (
        "Analyze the selected source materials and build a hierarchical mind map of their concepts.\n"
        "Output format (strict — the result is rendered as an interactive tree):\n"
        "1. Exactly one `# <central theme>` heading at the top.\n"
        "2. 4-7 main branches as `## <branch>` headings; sub-branches as `### <sub-branch>` headings where useful.\n"
        "3. Under each branch or sub-branch, list the leaf concepts as bullet items (`- `); nest related details with two-space "
        "indented bullets. Each bullet is a short phrase of at most 14 words followed by its [citation_X] marker.\n"
        "4. No prose paragraphs, tables or numbered lists; the hierarchy itself carries the structure."
    ),
    "flashcards": (
        "Analyze the selected source materials and create study flashcards covering the key concepts, definitions, "
        "principles, arguments and important facts.\n"
        "Output format (strict — the result is rendered as flippable cards):\n"
        "1. Group the cards under `## <theme>` headings.\n"
        "2. Every card is a `### <front>` heading containing only the question, term or concept (no 'Front:' label, no numbering), "
        "followed by exactly one paragraph with the back: a concise answer or explanation of 1-3 sentences ending with its "
        "[citation_X] markers (no 'Back:' label).\n"
        "3. Write 14-24 cards; one idea per card; no introduction, conclusion or any other text between cards."
    ),
    "quiz": (
        "Analyze the selected source materials and create a quiz that tests real comprehension rather than recall of trivia.\n"
        "Output format (strict — the result is rendered as an interactive quiz):\n"
        "1. Group questions under `## <section>` headings (for example multiple choice, then short answer).\n"
        "2. Every question is a `### <question text>` heading (no numbering).\n"
        "3. A multiple-choice question is followed by exactly four bullet items `- A) ...`, `- B) ...`, `- C) ...`, `- D) ...` "
        "with one correct option and plausible distractors, then one blockquote line `> ✓ B — <one-sentence explanation> [citation_X]` "
        "where the letter after ✓ is the correct option.\n"
        "4. A short-answer question has no bullet items and is followed by one blockquote line `> ✓ <model answer> [citation_X]`.\n"
        "5. Write 8-12 multiple-choice and 2-4 short-answer questions. Vary which letter is correct. Do not add a separate answer key."
    ),
    "podcast": (
        "Task: Write the full script of a two-voice podcast conversation about the source materials, in the style of a "
        "well-produced deep-dive show: one HOST who guides, asks and challenges, and one GUEST who knows the sources "
        "inside out.\n"
        "Format (strict — every line is read aloud by a text-to-speech system, one voice per speaker):\n"
        "1. Every turn is ONE paragraph that starts with `HOST:` or `GUEST:` (exactly these two English tags, uppercase, "
        "followed by a colon). No headings, bullet lists, tables, stage directions, sound effects or speaker names.\n"
        "2. Keep inline [citation_X] markers at the end of the sentences they support; they are shown in the transcript "
        "and removed from the audio.\n"
        "3. Write what people actually say: short sentences, contractions, spoken numbers, no markdown emphasis.\n"
        "Conversation design:\n"
        "- Open with the HOST welcoming listeners in two or three sentences, naming the sources and the question the "
        "episode will answer; the GUEST replies with why the material matters.\n"
        "- Then move through 4-6 themes. For each theme the GUEST explains with concrete details and examples from the "
        "sources; the HOST interrupts with clarifying questions, asks for an example, pushes back on a weak point or "
        "raises a counter-argument, and relates the point to everyday experience; the GUEST adds nuance, corrects "
        "misreadings and approaches the point from a second angle.\n"
        "- Include at least one moment where the two disagree or weigh a tension in the sources, and one short recap by "
        "the HOST in the middle (\"so far we have...\").\n"
        "- Close with the GUEST's three key takeaways and the HOST signing off with one open question for listeners.\n"
        "- Length: 1800-2600 words in total, turns of 1-5 sentences, alternating speakers; never two turns in a row by "
        "the same speaker."
    ),
    "study_guide": (
        "Analyze the selected source materials and write a study guide that someone could learn the material from.\n"
        "Structure it with these `## ` sections, in this order, with titles translated into the output language: "
        "Overview (one paragraph on what the sources cover and why it matters); Key concepts (a bullet list of terms, each with a "
        "one-sentence definition); Main arguments and ideas (`### ` sub-sections with short paragraphs); Common misunderstandings "
        "(bullets); Review questions (6-10 open questions, as a bullet list, without answers); Suggested study order (a short "
        "numbered list). Cite every factual statement with [citation_X]."
    ),
    "faq": (
        "Analyze the selected source materials and write the frequently asked questions a newcomer to this material would have.\n"
        "Output format (strict — the result is rendered as an expandable list):\n"
        "1. Group questions under `## <topic>` headings.\n"
        "2. Every question is a `### <question>` heading phrased as a real reader would ask it, followed by exactly one paragraph "
        "that answers it directly in 2-4 sentences and ends with its [citation_X] markers.\n"
        "3. Write 10-16 questions, ordered from basic to advanced; no introduction or conclusion."
    ),
    "briefing_doc": (
        "Analyze the selected source materials and write a briefing document for a busy decision-maker.\n"
        "Structure it with these `## ` sections, in this order, with titles translated into the output language: "
        "Bottom line (2-3 sentences with the single most important conclusion); Key findings (5-8 bullets, each one finding with "
        "its evidence); Background and context (short paragraphs); Notable quotes (2-4 blockquotes taken verbatim from the sources); "
        "Open questions and risks (bullets); Recommended next steps (a short numbered list). Be specific and cite every claim with [citation_X]."
    ),
    "title_suggestion": (
        "Generate title suggestions based on the selected source materials. "
        "Explain why each title fits the source content and intended positioning."
    ),
    "communication_copy": (
        "Generate communication copy from the selected source materials. "
        "Focus on clear messaging, audience value, and concise reusable copy."
    ),
    "audio_overview": (
        "Task: Write a natural, engaging, and well-structured spoken narration script (audio overview) based on the source evidence.\n"
        "Requirements:\n"
        "1. Write in a fluent, broadcast-ready narrative style suitable for being read aloud from start to finish by a text-to-speech (TTS) model;\n"
        "2. Begin with a clear introduction of the work/sources and their central theme, then walk through the key arguments, findings, and practical takeaways in cohesive paragraphs, and end with a concise synthesis;\n"
        "3. Avoid markdown tables, raw code blocks, or visual-only formatting that cannot be read aloud naturally; use clear headings and flowing prose;\n"
        "4. Keep inline [citation_X] evidence markers in the written script so the user can inspect the sources alongside the audio player."
    ),
}


def _standalone_feature_instruction(
    feature_type: str,
    custom_prompt: str,
    output_language: str,
) -> str:
    base = FEATURE_INSTRUCTION_TEMPLATES.get(
        feature_type,
        "Use the selected source materials to generate one focused, reusable right-panel result.",
    )
    if custom_prompt:
        base = f"{base}\n\nAdditional user requirements: {custom_prompt}"
    return f"{base}\n\nImportant: The final answer must be written in {output_language}."


async def generate_feature_task(
    ctx: dict,
    feature_id: str,
    output_language: str | None = None,
) -> dict:
    """Generate a standalone quick-tool feature in the right panel."""
    set_ui_language(output_language)
    from agent.capabilities import DEFAULT_FEATURE_TYPE
    from agent.feature_agent import FeatureAgent
    from agent.tools.query_knowledge_base import CitationState
    from models.feature import Feature
    from models.project import Project

    session_factory = ctx["session_factory"]
    started = datetime.now(timezone.utc)
    output_language = (output_language or "Chinese").strip()

    async with session_factory() as db:
        feature = await db.get(Feature, feature_id)
        if not feature:
            logger.error("generate_feature_task: feature %s not found", feature_id)
            return {"status": "error", "reason": "feature not found"}

        project = await db.get(Project, feature.project_id)
        user_id = project.owner_user_id if project else None
        cfg = feature.get_custom_config()
        file_ids = cfg.get("file_ids") or []
        custom_prompt = (cfg.get("prompt") or "").strip()
        feature_type = feature.feature_type or DEFAULT_FEATURE_TYPE
        report_title = feature.title or feature.step_name or "Quick tool"
        feature.status = "processing"
        feature.error_message = None
        feature.started_at = started
        await db.commit()

    try:
        import config as app_config

        tts_config = None
        if feature_type in ("audio_overview", "podcast"):
            tts_enabled, tts_base_url, tts_model, tts_api_key, tts_voice = await app_config.resolve_tts_config()
            if not tts_enabled:
                raise RuntimeError(ui_msg("tts_not_configured"))
            tts_config = (tts_base_url or "", tts_api_key or "", tts_model or "", tts_voice or "deniz")

        citation_state = CitationState()
        citation_state.project_id = feature.project_id
        citation_state.file_ids = file_ids or None
        citation_state.current_feature_id = feature_id

        instruction = _standalone_feature_instruction(
            feature_type,
            custom_prompt,
            output_language,
        )
        blocks, citations, _ = await FeatureAgent().generate(
            report_title=report_title,
            step_name=report_title,
            instruction=instruction,
            feature_type=feature_type,
            custom_prompt=custom_prompt,
            citation_state=citation_state,
            start_display_num=1,
            user_id=user_id,
            trace_phase="standalone",
        )

        if feature_type in ("audio_overview", "podcast") and tts_config is not None:
            from paths import get_upload_dir
            from services.tts_client import (
                TTSClient,
                blocks_to_speech_text,
                parse_voices,
                split_dialogue,
            )

            tts_base_url, tts_api_key, tts_model, tts_voice = tts_config
            voices = parse_voices(tts_voice)
            tts_client = TTSClient(
                base_url=tts_base_url,
                api_key=tts_api_key,
                model=tts_model,
                voice=voices[0],
            )
            output_dir = get_upload_dir() / "feature_audio"

            if feature_type == "podcast":
                # Two speakers: first configured voice hosts, second is the guest.
                script_text = "\n".join(
                    "".join(
                        str(part.get("content", "")) for part in block.get("content_parts", [])
                        if isinstance(part, dict) and part.get("type") == "text"
                    )
                    for block in blocks
                    if isinstance(block, dict) and block.get("block_type") != "audio"
                )
                turns = split_dialogue(script_text)
                if len(turns) < 4:
                    raise RuntimeError(ui_msg("podcast_not_dialogue"))
                speaker_voices = {"HOST": voices[0], "GUEST": voices[1] if len(voices) > 1 else voices[0]}
                _, mime_type = await tts_client.synthesize_dialogue_to_file(
                    turns=turns,
                    voices=speaker_voices,
                    output_dir=output_dir,
                    stem=feature_id,
                )
                caption = f"{tts_model} · {speaker_voices['HOST']} & {speaker_voices['GUEST']}"
            else:
                narration_text = blocks_to_speech_text(blocks)
                if not narration_text:
                    raise RuntimeError(ui_msg("tts_no_narration"))
                _, mime_type = await tts_client.synthesize_to_file(
                    text=narration_text,
                    output_dir=output_dir,
                    stem=feature_id,
                )
                caption = f"{tts_model} · {voices[0]}"

            audio_block = {
                "block_type": "audio",
                "asset": {
                    "url": f"/api/features/{feature_id}/audio",
                    "mime_type": mime_type,
                },
                "caption": caption,
            }
            blocks = [audio_block] + list(blocks)

        async with session_factory() as db:
            feature = await db.get(Feature, feature_id)
            if feature:
                feature.set_blocks(blocks)
                feature.set_citations(citations)
                feature.status = "completed"
                feature.finished_at = datetime.now(timezone.utc)
                await db.commit()
        logger.info(
            "[feature] done feature_id=%s type=%s blocks=%d citations=%d",
            feature_id,
            feature_type,
            len(blocks),
            len(citations or {}),
        )
        return {"status": "completed", "feature_id": feature_id}
    except Exception as exc:
        logger.exception("feature %s generation failed: %s", feature_id, exc)
        async with session_factory() as db:
            feature = await db.get(Feature, feature_id)
            if feature:
                feature.status = "failed"
                feature.error_message = _exception_message(exc)
                feature.finished_at = datetime.now(timezone.utc)
                await db.commit()
        raise


from workers.deep_research import deep_research_task  # noqa: E402


class WorkerSettings:
    functions = [
        parse_file_task,
        # embed_texts already retries each batch on transient errors (EMBED_MAX_ATTEMPTS), so
        # a queue-level retry is only for a short Milvus or database hiccup: one more try,
        # not three full re-embeds of the file.
        func(reembed_file_task, max_tries=2),
        # Each attempt is an LLM call; one retry covers a transient provider error.
        func(refresh_project_summary_task, max_tries=2),
        func(generate_feature_task, max_tries=1),
        func(deep_research_task, max_tries=1),
        # Workflow generation is not idempotent yet; avoid ARQ replay appending duplicate steps.
        func(generate_workflow_task, max_tries=1),
    ]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = (
        RedisSettings.from_dsn(REDIS_URL)
        if REDIS_URL.startswith(("redis://", "rediss://", "unix://"))
        else RedisSettings()
    )
    max_jobs = int(os.getenv("WORKER_MAX_JOBS", "4"))
    job_timeout = int(os.getenv("WORKER_JOB_TIMEOUT", "3600"))
    max_tries = 3
    retry_jobs = True
    retry_delay = 1.0
    retry_backoff = True
