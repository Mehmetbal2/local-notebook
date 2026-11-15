"""Search inside a project's sources, notes and results.

Matching ignores case and diacritics, so "maverdi" finds "Mâverdî", "ibnu'l"
finds "İbnü’l" and an Arabic word matches with or without its vowel marks.
Every word of the query must occur in the same block (paragraph) or note.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

SNIPPET_CHARS = 180
MAX_SNIPPETS = 3
MAX_QUERY_WORDS = 8

# Apostrophes and transliteration marks (ʿayn, hamza) are dropped so "ibnul" ≈ "İbnü’l".
_DROP = {ord(c): None for c in "’'`´ʿʾʼ‘"}
_SPECIAL = {ord("ı"): "i", ord("ß"): "ss", ord("ـ"): None}  # dotless i, sharp s, Arabic tatweel


def _fold_char(ch: str) -> str:
    if ord(ch) in _DROP:
        return ""
    special = _SPECIAL.get(ord(ch), ch)
    if special is None:
        return ""
    if special != ch:
        return special
    decomposed = unicodedata.normalize("NFKD", ch)
    base = "".join(c for c in decomposed if not unicodedata.combining(c))
    return base.casefold()


def fold(text: str) -> str:
    """Lower-case text without diacritics or apostrophes (for matching only)."""
    text = (text or "").translate(_DROP).translate(_SPECIAL)
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def query_words(query: str) -> list[str]:
    words = [w for w in re.split(r"\s+", fold(query).strip()) if w]
    # Longest words first: they are the most selective.
    unique = sorted(set(words), key=len, reverse=True)
    return unique[:MAX_QUERY_WORDS]


def _folded_with_map(text: str) -> tuple[str, list[int]]:
    """Folded text plus, for each folded character, the index of its source character."""
    out: list[str] = []
    index: list[int] = []
    for i, ch in enumerate(text):
        folded = _fold_char(ch)
        out.append(folded)
        index.extend([i] * len(folded))
    return "".join(out), index


def make_snippet(text: str, words: list[str]) -> dict | None:
    """A passage around the first match, with the character ranges of every match in it."""
    folded, index = _folded_with_map(text)
    hits: list[tuple[int, int]] = []
    for word in words:
        start = 0
        while True:
            pos = folded.find(word, start)
            if pos < 0:
                break
            hits.append((index[pos], index[pos + len(word) - 1] + 1))
            start = pos + len(word)
    if not hits:
        return None
    hits.sort()
    first = hits[0][0]
    begin = max(0, first - SNIPPET_CHARS // 3)
    end = min(len(text), begin + SNIPPET_CHARS)
    # Start and end on word boundaries.
    if begin > 0:
        space = text.find(" ", begin, first)
        begin = space + 1 if space >= 0 else begin
    if end < len(text):
        space = text.rfind(" ", hits[0][1], end)
        end = space if space > 0 else end
    piece = re.sub(r"\s+", " ", text[begin:end])
    display = ("…" if begin > 0 else "") + piece + ("…" if end < len(text) else "")
    return {"text": display, "ranges": _ranges(display, words)}


def _ranges(display: str, words: list[str]) -> list[list[int]]:
    """Character ranges of the query words in the shown passage (for highlighting)."""
    folded, index = _folded_with_map(display)
    ranges = []
    for word in words:
        start = 0
        while (pos := folded.find(word, start)) >= 0:
            end = index[pos + len(word) - 1] + 1
            # Keep trailing vowel marks / accents with the highlighted word.
            while end < len(display) and unicodedata.combining(display[end]):
                end += 1
            ranges.append([index[pos], end])
            start = pos + len(word)
    return sorted(ranges)


# ── sources ─────────────────────────────────────────────────────────────────

@dataclass
class _FileIndex:
    stamp: str
    paged: bool
    blocks: list[tuple[str, str, int]] = field(default_factory=list)  # (content, folded, page)


_file_cache: dict[str, _FileIndex] = {}


async def _file_index(db: AsyncSession, file_id: str, stamp: str, file_type: str | None) -> _FileIndex:
    from models.block import Block

    cached = _file_cache.get(file_id)
    if cached is not None and cached.stamp == stamp:
        return cached
    rows = (
        await db.execute(
            select(Block.content, Block.page).where(Block.file_id == file_id).order_by(Block.block_index.asc())
        )
    ).all()
    pages = {page for _, page in rows if page}
    entry = _FileIndex(
        stamp=stamp,
        paged=file_type == "pdf" or len(pages) > 1,
        blocks=[(content or "", fold(content or ""), page or 0) for content, page in rows],
    )
    _file_cache[file_id] = entry
    return entry


async def search_files(db: AsyncSession, project_id: str, query: str) -> list[dict]:
    from models.file import File

    words = query_words(query)
    if not words:
        return []
    files = (
        await db.execute(
            select(File.id, File.file_name, File.file_type, File.updated_at).where(
                File.project_id == project_id, File.status == "ready"
            )
        )
    ).all()
    results = []
    for file_id, file_name, file_type, updated_at in files:
        index = await _file_index(db, file_id, str(updated_at), file_type)
        name_match = all(w in fold(file_name) for w in words)
        count = 0
        snippets: list[dict] = []
        for content, folded, page in index.blocks:
            if all(w in folded for w in words):
                count += 1
                if len(snippets) < MAX_SNIPPETS:
                    snippet = make_snippet(content, words)
                    if snippet:
                        if index.paged and page:
                            snippet["page"] = page
                        snippets.append(snippet)
        if count or name_match:
            results.append({
                "id": file_id,
                "name_match": name_match,
                "count": count,
                "snippets": snippets,
            })
    results.sort(key=lambda r: (not r["name_match"], -r["count"]))
    return results


# ── notes and results ───────────────────────────────────────────────────────

# Emphasis and code marks and heading hashes are not part of the text the reader sees.
_MARKDOWN_MARKS = re.compile(r"\*\*|__|~~|`|^#{1,6}\s+", re.MULTILINE)


def _feature_text(blocks: list) -> list[str]:
    """Readable text of a result's blocks (citation markers left out)."""
    texts: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if node.get("type") == "citation_ref" or node.get("block_type") in ("audio", "image"):
                return
            for key, value in node.items():
                if key in ("content", "text", "question", "answer", "front", "back", "label") and isinstance(value, str):
                    if value.strip():
                        texts.append(_MARKDOWN_MARKS.sub("", value))
                elif isinstance(value, (list, dict)):
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(blocks)
    return texts


async def search_features(db: AsyncSession, project_id: str, query: str) -> dict[str, list[dict]]:
    """Matches in notes/quick results ("features") and in report sections, grouped by report ("workflows")."""
    from models.feature import Feature
    from models.workflow import Workflow

    words = query_words(query)
    if not words:
        return {"features": [], "workflows": []}
    rows = (
        await db.execute(
            select(Feature.id, Feature.workflow_id, Feature.title, Feature.step_name, Feature.blocks_json).where(
                Feature.project_id == project_id,
                Feature.status == "completed",
            )
        )
    ).all()
    titles = dict(
        (await db.execute(select(Workflow.id, Workflow.title).where(Workflow.project_id == project_id))).all()
    )
    features: list[dict] = []
    reports: dict[str, dict] = {}
    for feature_id, workflow_id, title, step_name, blocks_json in rows:
        try:
            blocks = json.loads(blocks_json) if blocks_json else []
        except ValueError:
            blocks = []
        name = title or step_name or ""
        count = 0
        snippets: list[dict] = []
        for text in _feature_text(blocks):
            if all(w in fold(text) for w in words):
                count += 1
                if len(snippets) < MAX_SNIPPETS:
                    snippet = make_snippet(text, words)
                    if snippet:
                        snippets.append(snippet)
        if workflow_id:
            entry = reports.setdefault(
                workflow_id,
                {
                    "id": workflow_id,
                    "name_match": all(w in fold(titles.get(workflow_id) or "") for w in words),
                    "count": 0,
                    "snippets": [],
                },
            )
            entry["count"] += count
            for snippet in snippets:
                if len(entry["snippets"]) < MAX_SNIPPETS:
                    entry["snippets"].append(snippet | {"section": name})
            continue
        name_match = all(w in fold(name) for w in words)
        if count or name_match:
            features.append({"id": feature_id, "name_match": name_match, "count": count, "snippets": snippets})
    workflows = [r for r in reports.values() if r["count"] or r["name_match"]]
    features.sort(key=lambda r: (not r["name_match"], -r["count"]))
    workflows.sort(key=lambda r: (not r["name_match"], -r["count"]))
    return {"features": features, "workflows": workflows}
