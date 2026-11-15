"""Find web sources for a project ("Add source → Search the web").

Quick research: the LLM turns the user's topic into a few search queries,
SearXNG runs them in parallel, duplicates are merged, and the LLM ranks the
candidates with a one-line reason. Nothing is imported here.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from urllib.parse import urlparse

import time

import config

from services import open_access as oa
from services import searxng_client as sx
from services.llm_provider import complete_text

logger = logging.getLogger(__name__)

MAX_QUERIES = 3
MAX_CANDIDATES = 30
MAX_RESULTS = 12
# Results shown right after the search; the model then orders and explains them.
SHOWN_RESULTS = 18

SCOPE_CATEGORIES = {"web": "general", "academic": "science"}

_SYSTEM_PROMPT = (
    "You help a researcher find good sources on the web. "
    "You answer with JSON only and never invent URLs."
)


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


# Query writing blocks the result list, so it runs without reasoning.
QUERY_LLM_TIMEOUT = 60.0
# Ordering runs after the results are shown, so it can afford the model's reasoning.
RANK_LLM_TIMEOUT = 240.0
RANK_MAX_TOKENS = 8000  # reasoning and the answer share this budget


async def _llm_text(
    prompt: str, user_id: str, max_tokens: int, timeout: float = 60.0, thinking: bool = False
) -> str:
    started = time.monotonic()
    text = await complete_text(
        prompt,
        system_prompt=_SYSTEM_PROMPT,
        user_id=user_id,
        max_tokens=max_tokens,
        timeout=timeout,
        thinking=thinking,
    )
    logger.info(f"web discovery model call: {len(text)} chars in {time.monotonic() - started:.1f}s")
    return text


async def _llm_json(prompt: str, user_id: str, max_tokens: int) -> dict:
    return _parse_json(await _llm_text(prompt, user_id, max_tokens))


# Complete {"i": n, "reason": "..."} objects, so a truncated reply still yields its items.
_RANK_ITEM_RE = re.compile(r'\{\s*"i"\s*:\s*(\d+)\s*,\s*"reason"\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}')


def _parse_rank_items(text: str) -> list[tuple[int, str]]:
    items = []
    for m in _RANK_ITEM_RE.finditer(text or ""):
        try:
            reason = json.loads(f'"{m.group(2)}"')
        except ValueError:
            reason = m.group(2)
        items.append((int(m.group(1)), reason))
    return items


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"\w{4,}", text.casefold())}


def _lexical_filter(candidates: list[dict], queries: list[str]) -> list[dict]:
    """Drop results sharing no word stem with any query (engines such as arXiv
    return unrelated papers for non-English queries)."""
    stems = {w[:6] for q in queries for w in _terms(q)}
    if not stems:
        return candidates
    kept = []
    for c in candidates:
        words = _terms(f"{c['title']} {c['snippet']}")
        if any(w[:6] in stems for w in words):
            kept.append(c)
    return kept if len(kept) >= 5 else candidates


async def expand_queries(topic: str, scope: str, output_language: str, user_id: str) -> list[str]:
    scope_note = (
        "Target scholarly literature (articles, books, theses): use the field's technical terms."
        if scope == "academic"
        else "Target reliable web pages: encyclopedias, institutions, reputable publications."
    )
    prompt = (
        f"Research topic (written by the user):\n{topic}\n\n"
        f"Write up to {MAX_QUERIES} short search-engine queries (2-8 words each) that together find "
        f"the best sources on this topic. {scope_note}\n"
        "- The first query keeps the user's language.\n"
        "- Add an English query when the topic is not in English, since much of the literature is.\n"
        "- Vary the angle (key concept, main author or theory, specific aspect); no near-duplicates.\n"
        "- No search operators or quotes.\n\n"
        "Reply with JSON only: {\"queries\": [\"...\"]}"
    )
    text = await _llm_text(prompt, user_id, 2000, QUERY_LLM_TIMEOUT)
    data = _parse_json(text)
    if text and not data.get("queries"):
        logger.warning(f"web discovery query reply not understood: {text[:300]!r}")
    queries: list[str] = []
    for q in data.get("queries") or []:
        q = re.sub(r"\s+", " ", str(q)).strip().strip('"')
        if q and q.lower() not in {x.lower() for x in queries}:
            queries.append(q[:200])
    if topic.strip().lower() not in {q.lower() for q in queries}:
        # The user's own wording is always searched too.
        queries.insert(0, topic.strip()[:200])
    return queries[: MAX_QUERIES + 1]


def _kind(url: str) -> str:
    try:
        path = urlparse(url).path.lower()
    except ValueError:
        return "page"
    return "pdf" if path.endswith(".pdf") else "page"


async def gather_candidates(base_url: str, queries: list[str], scope: str, language: str | None) -> list[dict]:
    category = SCOPE_CATEGORIES.get(scope, "general")

    async def run(q: str):
        try:
            return await sx.search(base_url, q, categories=category, language=language)
        except sx.SearxngError as exc:
            logger.info(f"SearXNG query failed ({q}): {exc.code}")
            if exc.code in ("unreachable", "json_disabled"):
                raise
            return []

    lists = await asyncio.gather(*(run(q) for q in queries))
    # Reciprocal-rank fusion across the queries.
    merged: dict[str, dict] = {}
    for results in lists:
        for rank, hit in enumerate(results[:20]):
            doi = oa.normalize_doi(hit.doi) or oa.normalize_doi(hit.url)
            if oa.is_review_record(doi, hit.title):
                continue
            # The same work found by several engines merges on its DOI.
            key = f"doi:{doi}" if doi else sx._normalize_url(hit.url)
            entry = merged.get(key)
            score = 1.0 / (rank + 3)
            if entry is None:
                merged[key] = {
                    "url": hit.url,
                    "title": hit.title,
                    "snippet": hit.content[:400],
                    "domain": hit.domain,
                    "published_date": hit.published_date,
                    "engines": list(hit.engines),
                    "kind": _kind(hit.url),
                    "doi": doi,
                    "pdf_url": hit.pdf_url,
                    "authors": list(hit.authors),
                    "venue": hit.journal,
                    "_score": score + 0.02 * len(hit.engines),
                }
            else:
                entry["_score"] += score
                if len(hit.content) > len(entry["snippet"]):
                    entry["snippet"] = hit.content[:400]
                for e in hit.engines:
                    if e not in entry["engines"]:
                        entry["engines"].append(e)
                if not entry["pdf_url"] and hit.pdf_url:
                    entry["pdf_url"] = hit.pdf_url
                if not entry["authors"] and hit.authors:
                    entry["authors"] = list(hit.authors)
                if not entry["venue"] and hit.journal:
                    entry["venue"] = hit.journal
    ranked = sorted(merged.values(), key=lambda e: e["_score"], reverse=True)
    return _lexical_filter(ranked, queries)[:MAX_CANDIDATES]


async def rank_sources(
    topic: str, scope: str, items: list[dict], output_language: str, user_id: str
) -> list[dict] | None:
    """Order the shown results by usefulness with a one-line reason each.

    Returns [{"url", "reason"}] best first (results judged off-topic are left out),
    or None when the model gave no usable answer."""
    if not items:
        return []
    lines = []
    for i, c in enumerate(items):
        date = f" ({str(c.get('published_date') or '')[:4]})" if c.get("published_date") else ""
        where = c.get("venue") or c.get("domain") or ""
        lines.append(f"[{i}] {c.get('title', '')}{date} — {where}\n    {str(c.get('snippet') or '')[:220]}")
    scope_note = "scholarly sources" if scope == "academic" else "reliable, substantive sources"
    prompt = (
        f"Research topic:\n{topic}\n\n"
        f"Search results:\n" + "\n".join(lines) + "\n\n"
        f"Pick the results that are useful {scope_note} for this topic, best first, at most {MAX_RESULTS}. "
        "Leave out off-topic pages, shops, ads, login walls, thin listicles and duplicates of the same work. "
        f"For each, write a reason in {output_language}: one short sentence (max 12 words) saying what the "
        "source offers for this topic. Base it only on the title and snippet.\n\n"
        "Reply with JSON only, no other text: {\"results\": [{\"i\": 0, \"reason\": \"...\"}]}"
    )
    started = time.monotonic()
    text = await _llm_text(prompt, user_id, RANK_MAX_TOKENS, RANK_LLM_TIMEOUT, thinking=True)
    parsed = _parse_rank_items(text)
    logger.info(f"web discovery ranking: {len(parsed)} picked of {len(items)} in {time.monotonic() - started:.1f}s")
    if not parsed:
        if text:
            logger.warning(f"web discovery ranking reply not understood: {text[:300]!r}")
        return None
    order: list[dict] = []
    seen: set[int] = set()
    for idx, reason in parsed:
        if idx in seen or not 0 <= idx < len(items):
            continue
        seen.add(idx)
        order.append({"url": items[idx].get("url", ""), "reason": re.sub(r"\s+", " ", str(reason or "")).strip()[:300]})
        if len(order) >= MAX_RESULTS:
            break
    return order


async def annotate_access(results: list[dict]) -> None:
    """Mark each result with how much of it can be imported:
    full (a PDF is available), oa_page (a free page, PDF unknown),
    abstract (a scholarly work with no known free copy) or page (an ordinary web page)."""
    for r in results:
        if not r.get("pdf_url"):
            r["pdf_url"] = oa.arxiv_pdf_url(r["url"]) or (r["url"] if r.get("kind") == "pdf" else "")
        r.setdefault("landing_url", "")
    need = [r["doi"] for r in results if r.get("doi") and not r.get("pdf_url")]
    found: dict = {}
    if need:
        started = time.monotonic()
        found = await oa.openalex_lookup(need)
        logger.info(f"open access lookup: {len(found)}/{len(need)} DOIs known in {time.monotonic() - started:.1f}s")
    for r in results:
        info = found.get(r.get("doi") or "")
        if info is not None:
            if info.pdf_urls:
                r["pdf_url"] = info.pdf_urls[0]
            elif info.landing_url:
                r["landing_url"] = info.landing_url
            if not r.get("authors"):
                r["authors"] = info.authors
            if not r.get("venue"):
                r["venue"] = info.venue
            if not r.get("published_date") and info.year:
                r["published_date"] = info.year
        if r.get("pdf_url"):
            r["access"] = "full"
        elif r.get("landing_url"):
            r["access"] = "oa_page"
        elif r.get("doi"):
            r["access"] = "abstract"
        else:
            r["access"] = "page"
        r["authors"] = (r.get("authors") or [])[:10]


async def discover_sources(
    *, topic: str, scope: str, output_language: str, language: str | None, user_id: str
) -> dict:
    base_url = await config.resolve_searxng_url()
    t0 = time.monotonic()
    queries = await expand_queries(topic, scope, output_language, user_id)
    t1 = time.monotonic()
    candidates = await gather_candidates(base_url, queries, scope, language)
    t2 = time.monotonic()
    logger.info(f"web discovery: {len(queries)} queries in {t1 - t0:.1f}s, {len(candidates)} candidates in {t2 - t1:.1f}s")
    results = [dict(c, reason="") for c in candidates[:SHOWN_RESULTS]]
    for entry in results:
        entry.pop("_score", None)
    await annotate_access(results)
    return {"queries": queries, "results": results}
