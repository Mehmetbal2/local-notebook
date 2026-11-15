"""Deep research: plan → search → read full texts → fill gaps → cited report.

Runs as a background job and writes its result into a Feature of type
"deep_research", so the report appears among the project's results with its
web citations, and the sources it read can be added to the project.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone

from utils.i18n import msg as ui_msg, set_language as set_ui_language

logger = logging.getLogger("workers.deep_research")

DEEP_RESEARCH_FEATURE_TYPE = "deep_research"

MAX_SUBQUESTIONS = 5
MAX_ROUNDS = 2              # first pass + one round of follow-up searches
SOURCES_PER_SUBQUESTION = 5
MAX_SOURCES = 28
MIN_SOURCE_TEXT = 300
EXCERPT_CHARS = 3200        # passage kept from each source for the report
PDF_MAX_PAGES = 60
FETCH_CONCURRENCY = 5

PLAN_TIMEOUT = 240.0
GAP_TIMEOUT = 120.0
REPORT_TIMEOUT = 1500.0

_SYSTEM_PROMPT = (
    "You are a careful research assistant. You plan searches, judge sources and write "
    "well-structured reports that rest only on the sources you are given."
)


class ResearchStopped(Exception):
    """The result was deleted or stopped while the job was running."""


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


async def _set_progress(session_factory, feature_id: str, message: str, **cfg_updates) -> None:
    from models.feature import Feature

    async with session_factory() as db:
        feature = await db.get(Feature, feature_id)
        if feature is None or feature.status in ("cancelled", "failed"):
            raise ResearchStopped()
        cfg = feature.get_custom_config()
        cfg["progress"] = message
        cfg.update(cfg_updates)
        feature.set_custom_config(cfg)
        await db.commit()
    logger.info(f"[deep research {feature_id[:8]}] {message}")


# ── steps ───────────────────────────────────────────────────────────────────

async def _plan(topic: str, scope: str, language: str, user_id: str | None) -> list[dict]:
    from services.llm_provider import complete_text

    scope_note = (
        "Favour scholarly literature (articles, books, theses); use the field's technical terms."
        if scope == "academic"
        else "Use reliable sources: encyclopedias, institutions, reputable publications and scholarship."
    )
    prompt = (
        f"Research topic (written by the user):\n{topic}\n\n"
        f"Break the topic into {MAX_SUBQUESTIONS - 1}-{MAX_SUBQUESTIONS} sub-questions that together cover it "
        "well (definitions and background, main positions or findings, key thinkers or works, debates, "
        "applications). For each, write 2 short search-engine queries (2-8 words): one in the user's "
        "language and, if that is not English, one in English. No search operators.\n"
        f"{scope_note}\n"
        f"Write the sub-questions in {language}.\n\n"
        "Reply with JSON only: {\"subquestions\": [{\"question\": \"...\", \"queries\": [\"...\", \"...\"]}]}"
    )
    text = await complete_text(
        prompt, system_prompt=_SYSTEM_PROMPT, user_id=user_id, max_tokens=8000,
        timeout=PLAN_TIMEOUT, thinking=True, stream=True,
    )
    subs: list[dict] = []
    for item in _parse_json(text).get("subquestions") or []:
        if not isinstance(item, dict):
            continue
        question = re.sub(r"\s+", " ", str(item.get("question") or "")).strip()
        queries = [re.sub(r"\s+", " ", str(q)).strip().strip('"') for q in item.get("queries") or []]
        queries = [q[:200] for q in queries if q][:3]
        if question and queries:
            subs.append({"question": question[:300], "queries": queries})
    if not subs:
        logger.warning(f"deep research plan not understood: {text[:300]!r}")
        subs = [{"question": topic, "queries": [topic]}]
    return subs[:MAX_SUBQUESTIONS]


async def _follow_up_queries(
    topic: str, subs: list[dict], sources: list[dict], language: str, user_id: str | None
) -> list[tuple[int, list[str]]]:
    from services.llm_provider import complete_text

    lines = []
    for i, sub in enumerate(subs):
        found = [s for s in sources if s["sub"] == i]
        titles = "; ".join(s["title"][:80] for s in found[:6]) or "(nothing usable found)"
        lines.append(f"[{i}] {sub['question']}\n    sources read: {len(found)} — {titles}")
    prompt = (
        f"Research topic:\n{topic}\n\n"
        "Sub-questions and the sources read so far:\n" + "\n".join(lines) + "\n\n"
        "Which sub-questions are still poorly covered (few or off-target sources)? For at most 3 of "
        "them, write 2 new, differently worded search queries (one in the user's language, one in "
        "English). If coverage is already good, return an empty list.\n\n"
        "Reply with JSON only: {\"followups\": [{\"i\": 0, \"queries\": [\"...\", \"...\"]}]}"
    )
    text = await complete_text(
        prompt, system_prompt=_SYSTEM_PROMPT, user_id=user_id, max_tokens=2000, timeout=GAP_TIMEOUT
    )
    result: list[tuple[int, list[str]]] = []
    for item in _parse_json(text).get("followups") or []:
        try:
            idx = int(item.get("i"))
        except (TypeError, ValueError, AttributeError):
            continue
        queries = [re.sub(r"\s+", " ", str(q)).strip().strip('"')[:200] for q in item.get("queries") or []]
        queries = [q for q in queries if q][:2]
        if 0 <= idx < len(subs) and queries:
            result.append((idx, queries))
    return result[:3]


def _pdf_text(data: bytes) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return ""
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            pages = []
            for i in range(min(len(doc), PDF_MAX_PAGES)):
                blocks = doc[i].get_text("blocks")
                pages.append("\n\n".join(b[4].replace("\n", " ").strip() for b in blocks if b[6] == 0))
    except Exception:
        return ""
    return "\n\n".join(p for p in pages if p.strip())


async def _gather_round(
    base_url: str,
    scope: str,
    topic: str,
    targets: list[tuple[int, list[str]]],
    subs: list[dict],
    sources: list[dict],
    seen: set[str],
) -> int:
    """Search, pick and read new sources for the given sub-questions. Returns how many were added."""
    from routes.web_source_routes import WebSourceItem, _fetch_source
    from services import open_access as oa
    from services import searxng_client as sx
    from services.web_discovery import annotate_access, gather_candidates

    picks: list[tuple[int, dict]] = []
    for sub_index, queries in targets:
        try:
            candidates = await gather_candidates(base_url, queries, scope, None)
        except sx.SearxngError:
            raise
        except Exception as exc:
            logger.info(f"deep research search failed ({queries}): {exc}")
            continue
        taken = 0
        for cand in candidates:
            key = f"doi:{cand['doi']}" if cand.get("doi") else sx._normalize_url(cand["url"])
            if key in seen:
                continue
            seen.add(key)
            picks.append((sub_index, cand))
            taken += 1
            if taken >= SOURCES_PER_SUBQUESTION:
                break
    room = MAX_SOURCES - len(sources)
    picks = picks[: max(room, 0)]
    if not picks:
        return 0
    await annotate_access([c for _, c in picks])

    sem = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def read(sub_index: int, cand: dict):
        item = WebSourceItem(
            url=cand["url"],
            title=cand.get("title"),
            pdf_url=cand.get("pdf_url") or None,
            landing_url=cand.get("landing_url") or None,
            doi=cand.get("doi") or None,
            authors=cand.get("authors") or [],
            published_date=cand.get("published_date") or None,
        )
        async with sem:
            try:
                page, info = await asyncio.wait_for(_fetch_source(item), 90)
            except Exception as exc:
                logger.info(f"deep research could not read {cand['url']}: {exc}")
                return None
        text = await asyncio.to_thread(_pdf_text, page.pdf_bytes or b"") if page.is_pdf else page.text
        if len(text or "") < (80 if info.get("abstract_only") else MIN_SOURCE_TEXT):
            return None
        focus = " ".join([subs[sub_index]["question"], *subs[sub_index]["queries"], topic])
        excerpt = sx.relevant_excerpt(text, focus, EXCERPT_CHARS)
        year = (re.search(r"\b(1[5-9]\d\d|20\d\d)\b", page.published or cand.get("published_date") or "") or [None])[0]
        return {
            "sub": sub_index,
            "url": cand["url"],
            "title": info.get("title") or page.title or cand.get("title") or cand["url"],
            "venue": cand.get("venue") or page.site_name or cand.get("domain") or "",
            "domain": cand.get("domain") or "",
            "authors": (page.authors or info.get("authors") or cand.get("authors") or [])[:10],
            "year": year or info.get("year") or "",
            "doi": info.get("doi") or cand.get("doi") or "",
            "pdf_url": cand.get("pdf_url") or "",
            "landing_url": cand.get("landing_url") or "",
            "full_text": bool(page.is_pdf) or not info.get("abstract_only"),
            "chars": len(text),
            "excerpt": excerpt,
        }

    results = await asyncio.gather(*(read(i, c) for i, c in picks))
    added = 0
    for res in results:
        if res and len(sources) < MAX_SOURCES:
            res["n"] = len(sources) + 1
            sources.append(res)
            added += 1
    return added


_SOURCE_REF_RE = re.compile(r"\[(S\s*\d+(?:\s*[,;]\s*S?\s*\d+)*)\]", re.IGNORECASE)


def _to_citation_markers(markdown: str, max_n: int) -> str:
    """[S3] / [S1, S4] → [citation_3][citation_1][citation_4]; unknown numbers are dropped."""
    def repl(match: re.Match) -> str:
        nums = [int(n) for n in re.findall(r"\d+", match.group(1))]
        return "".join(f"[citation_{n}]" for n in nums if 1 <= n <= max_n)

    return _SOURCE_REF_RE.sub(repl, markdown)


async def _write_report(
    topic: str, subs: list[dict], sources: list[dict], language: str, user_id: str | None
) -> str:
    from services.llm_provider import complete_text

    digest = []
    for s in sources:
        who = (s["authors"][0] + (" et al." if len(s["authors"]) > 1 else "")) if s["authors"] else ""
        meta = ", ".join(x for x in [who, s["venue"], s["year"]] if x)
        kind = "full text" if s["full_text"] else "abstract only"
        digest.append(f"[S{s['n']}] {s['title']} ({meta}; {kind})\n{s['excerpt']}")
    plan = "\n".join(f"{i + 1}. {sub['question']}" for i, sub in enumerate(subs))
    prompt = (
        f"Research topic:\n{topic}\n\n"
        f"Sub-questions:\n{plan}\n\n"
        f"Sources (passages taken from them):\n\n" + "\n\n".join(digest) + "\n\n"
        f"Write a thorough research report in {language}, in Markdown:\n"
        "- Start with one '# ' title line, then a short introduction.\n"
        "- One '## ' section per sub-question (you may merge or reorder them if that reads better), "
        "then a '## ' section with the conclusions and the open questions or gaps in the sources.\n"
        "- Every factual statement must rest on the sources above. Cite them right after the "
        "statement with their markers, e.g. [S3] or [S2, S5]. Do not invent sources, page numbers "
        "or quotations; do not add a bibliography (it is generated from the markers).\n"
        "- Where sources disagree, say so and cite both sides. Mark clearly what rests only on "
        "abstracts.\n"
        "- Prefer precise, substantive content (definitions, arguments, findings, names, dates) over "
        "general statements."
    )
    return await complete_text(
        prompt, system_prompt=_SYSTEM_PROMPT, user_id=user_id, max_tokens=16000,
        timeout=REPORT_TIMEOUT, thinking=True, easy_task=False, stream=True,
    )


# ── job ─────────────────────────────────────────────────────────────────────

async def deep_research_task(ctx: dict, feature_id: str, output_language: str | None = None) -> dict:
    set_ui_language(output_language)
    import config
    from models.feature import Feature
    from models.project import Project
    from routes.feature_routes import _build_note_blocks
    from services import searxng_client as sx

    session_factory = ctx["session_factory"]
    started = time.monotonic()
    language = (output_language or "Turkish").strip()

    async with session_factory() as db:
        feature = await db.get(Feature, feature_id)
        if feature is None:
            return {"status": "error", "reason": "feature not found"}
        project = await db.get(Project, feature.project_id)
        user_id = project.owner_user_id if project else None
        cfg = feature.get_custom_config()
        topic = (cfg.get("query") or feature.title or "").strip()
        scope = cfg.get("scope") if cfg.get("scope") in ("web", "academic") else "web"
        # Sources read by an earlier run whose report failed: write the report again from them.
        collected = cfg.get("collected") if isinstance(cfg.get("collected"), dict) else None
        feature.status = "processing"
        feature.started_at = datetime.now(timezone.utc)
        feature.error_message = None
        await db.commit()

    try:
        base_url = await config.resolve_searxng_url()
        if collected and collected.get("sources"):
            subs = collected.get("subs") or [{"question": topic, "queries": [topic]}]
            sources = collected["sources"]
            rounds = 0
        else:
            await _set_progress(session_factory, feature_id, ui_msg("research_planning"))
            subs = await _plan(topic, scope, language, user_id)
            await _set_progress(
                session_factory, feature_id, ui_msg("research_searching", count=len(subs)),
                subquestions=[s["question"] for s in subs],
            )
            sources = []
            rounds = MAX_ROUNDS

        seen: set[str] = set()
        targets = [(i, sub["queries"]) for i, sub in enumerate(subs)]
        for round_no in range(rounds):
            await _gather_round(base_url, scope, topic, targets, subs, sources, seen)
            await _set_progress(
                session_factory, feature_id, ui_msg("research_read", count=len(sources)),
            )
            if round_no + 1 >= MAX_ROUNDS or len(sources) >= MAX_SOURCES:
                break
            await _set_progress(session_factory, feature_id, ui_msg("research_gaps", count=len(sources)))
            targets = await _follow_up_queries(topic, subs, sources, language, user_id)
            if not targets:
                break
            for idx, queries in targets:
                subs[idx]["queries"] = subs[idx]["queries"] + queries

        if not sources:
            raise RuntimeError(ui_msg("research_no_sources"))

        # Keep what was read, so a failed report can be written again without searching.
        await _set_progress(
            session_factory, feature_id, ui_msg("research_writing", count=len(sources)),
            collected={"subs": subs, "sources": sources},
        )
        markdown = (await _write_report(topic, subs, sources, language, user_id)).strip()
        if not markdown:
            raise RuntimeError(ui_msg("research_report_failed"))

        title = topic[:120]
        lines = markdown.splitlines()
        if lines and lines[0].startswith("# "):
            title = re.sub(r"\s+", " ", lines[0][2:]).strip()[:200] or title
            markdown = "\n".join(lines[1:]).lstrip()
        markdown = _to_citation_markers(markdown, len(sources))

        citation_map = {
            f"citation_{s['n']}": {
                "type": "web",
                "title": s["title"],
                "url": s["url"],
                "snippet": s["excerpt"][:600],
                "source": s["venue"] or s["domain"],
                "published_date": s["year"],
                "favicon": "",
            }
            for s in sources
        }
        blocks, citations = _build_note_blocks(markdown, citation_map)
        used = {int(k.split("_")[1]) for k in citations}

        async with session_factory() as db:
            feature = await db.get(Feature, feature_id)
            if feature is None or feature.status == "cancelled":
                raise ResearchStopped()
            cfg = feature.get_custom_config()
            cfg.pop("progress", None)
            cfg.pop("collected", None)
            cfg["subquestions"] = [s["question"] for s in subs]
            cfg["sources"] = [
                {k: v for k, v in s.items() if k != "excerpt"} | {"cited": s["n"] in used}
                for s in sources
            ]
            cfg["markdown"] = markdown
            feature.set_custom_config(cfg)
            feature.title = title
            feature.step_name = title
            feature.set_blocks(blocks)
            feature.set_citations(citations)
            feature.status = "completed"
            feature.finished_at = datetime.now(timezone.utc)
            await db.commit()
        logger.info(
            f"[deep research {feature_id[:8]}] done: {len(sources)} sources, {len(used)} cited, "
            f"{time.monotonic() - started:.0f}s"
        )
        return {"status": "completed", "feature_id": feature_id}

    except ResearchStopped:
        logger.info(f"[deep research {feature_id[:8]}] stopped")
        return {"status": "cancelled", "feature_id": feature_id}
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if isinstance(exc, sx.SearxngError) and exc.code == "unreachable":
            message = ui_msg("searxng_cannot_connect", url=await config.resolve_searxng_url())
        else:
            message = str(exc) or ui_msg("unknown_error")
        logger.exception(f"[deep research {feature_id[:8]}] failed")
        async with session_factory() as db:
            feature = await db.get(Feature, feature_id)
            if feature is not None:
                cfg = feature.get_custom_config()
                cfg.pop("progress", None)
                feature.set_custom_config(cfg)
                feature.status = "failed"
                feature.error_message = message[:1000]
                feature.finished_at = datetime.now(timezone.utc)
                await db.commit()
        return {"status": "failed", "feature_id": feature_id}


async def recover_deep_research(session_factory, queue) -> None:
    """Restart research jobs that a restart of the app interrupted."""
    from sqlalchemy import select
    from models.feature import Feature

    if queue is None:
        return
    async with session_factory() as db:
        result = await db.execute(
            select(Feature).where(
                Feature.feature_type == DEEP_RESEARCH_FEATURE_TYPE,
                Feature.status.in_(["pending", "processing"]),
            )
        )
        stuck = result.scalars().all()
        for feature in stuck:
            cfg = feature.get_custom_config()
            cfg["progress"] = ui_msg("research_restarted")
            feature.set_custom_config(cfg)
            feature.status = "pending"
        await db.commit()
    for feature in stuck:
        await queue.enqueue_job(
            "deep_research_task", feature.id, feature.get_custom_config().get("output_language")
        )
        logger.info(f"Re-enqueued deep research {feature.id}")
