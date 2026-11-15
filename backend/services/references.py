"""Reference entries for downloads: the work's current name, its page and one sentence to search for.

A citation stores the passage it points to. For a reader writing a paper the most useful
thing is a sentence copied verbatim from that passage: searched in the work, it leads to
the exact page and paragraph. The page is added when the source has one (PDF page index,
or the printed page carried by Shamela HTML exports).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Sentence ends in Latin, Arabic and CJK text; also paragraph breaks.
_SENTENCE_END_RE = re.compile(r"(?<=[.!?؟۔。！？])\s+|\n+")
_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)
_WS_RE = re.compile(r"\s+")
MIN_SENTENCE_CHARS = 25
MAX_SENTENCE_CHARS = 220


def source_display_name(file_name: str) -> str:
    """The work's name as shown in references: the file name without its extension."""
    base, ext = os.path.splitext(file_name or "")
    return base if ext and len(ext) <= 6 else (file_name or "")


def _clip(sentence: str) -> str:
    if len(sentence) <= MAX_SENTENCE_CHARS:
        return sentence
    cut = sentence[:MAX_SENTENCE_CHARS].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{cut}…"


def pick_search_sentence(text: str, starts_mid_sentence: bool) -> tuple[str, int]:
    """Choose one verbatim sentence of `text` that is long enough to search for.

    Returns (sentence, offset in `text`). The first piece is skipped when the passage begins
    in the middle of a sentence, since a fragment is hard to find and may mislead.
    """
    if not text:
        return "", 0
    pieces: list[tuple[str, int]] = []
    position = 0
    for match in _SENTENCE_END_RE.finditer(text):
        pieces.append((text[position:match.start()], position))
        position = match.end()
    pieces.append((text[position:], position))

    candidates = []
    for index, (piece, offset) in enumerate(pieces):
        stripped = piece.strip()
        if not stripped:
            continue
        if index == 0 and starts_mid_sentence and len(pieces) > 1:
            continue
        letters = len(_LETTER_RE.findall(stripped))
        if letters < 12 or len(stripped) < MIN_SENTENCE_CHARS:
            continue
        candidates.append((stripped, offset + piece.index(stripped)))
    if candidates:
        # Prefer a real sentence over a heading or list label (those rarely end in punctuation).
        complete = [c for c in candidates if c[0][-1:] in ".!?؟۔。！？…\"”»'"]
        sentence, offset = (complete or candidates)[0]
        return _clip(_WS_RE.sub(" ", sentence)), offset
    # No complete sentence: take the start of the passage.
    stripped = text.strip()
    return _clip(_WS_RE.sub(" ", stripped)), text.index(stripped[:1]) if stripped else 0


def _block_page(block: Any) -> tuple[Optional[int], Optional[int]]:
    page = block.page if isinstance(block.page, int) and block.page > 0 else None
    volume = None
    if block.extra:
        try:
            extra = json.loads(block.extra) if isinstance(block.extra, str) else block.extra
            if isinstance(extra, dict) and isinstance(extra.get("volume"), int):
                volume = extra["volume"]
        except (TypeError, ValueError):
            pass
    return page, volume


async def build_references(db: AsyncSession, citations: Iterable[dict]) -> dict[int, dict]:
    """Reference data for each text citation, keyed by id() of the citation dict.

    Each value: name, file_type, page, volume, page_kind ('pdf' | 'printed' | None), sentence.
    Web, image and audio citations are left out (they keep their own formatting).
    """
    from models.block import Block
    from models.file import File
    from models.segment import Segment

    metas = [m for m in citations if isinstance(m, dict) and m.get("segment_id") and m.get("type", "segment") == "segment"]
    if not metas:
        return {}

    file_ids = {m.get("file_id") for m in metas if m.get("file_id")}
    segment_ids = {m.get("segment_id") for m in metas}

    files = {
        f.id: f
        for f in (await db.execute(select(File).where(File.id.in_(file_ids)))).scalars().all()
    }
    segments = {
        s.id: s
        for s in (await db.execute(select(Segment).where(Segment.id.in_(segment_ids)))).scalars().all()
    }

    wanted_blocks: dict[str, set[str]] = {}
    for segment in segments.values():
        try:
            block_ids = json.loads(segment.block_ids or "[]")
        except ValueError:
            block_ids = []
        wanted_blocks.setdefault(segment.file_id, set()).update(b for b in block_ids if isinstance(b, str))
    # Non-PDF sources only have meaningful pages when the parser found page markers
    # (e.g. Shamela HTML); a single page value everywhere means "no pages".
    from sqlalchemy import func

    paged_files: set[str] = set()
    for file_id in file_ids:
        file = files.get(file_id)
        if file is not None and (file.file_type or "") == "pdf":
            paged_files.add(file_id)
            continue
        distinct_pages = (
            await db.execute(select(func.count(func.distinct(Block.page))).where(Block.file_id == file_id))
        ).scalar() or 0
        if distinct_pages > 1:
            paged_files.add(file_id)

    blocks_by_file: dict[str, list[Any]] = {}
    for file_id, block_ids in wanted_blocks.items():
        if not block_ids:
            continue
        rows = (
            await db.execute(select(Block).where(Block.file_id == file_id, Block.block_id.in_(block_ids)))
        ).scalars().all()
        blocks_by_file[file_id] = sorted(rows, key=lambda b: b.pos_start or 0)

    result: dict[int, dict] = {}
    for meta in metas:
        file = files.get(meta.get("file_id"))
        segment = segments.get(meta.get("segment_id"))
        name = source_display_name(file.file_name if file else meta.get("file_name", ""))
        file_type = (file.file_type if file else "") or ""
        text = (segment.content if segment else None) or meta.get("content") or ""
        if text.endswith("..."):
            text = text[:-3]

        blocks = blocks_by_file.get(segment.file_id, []) if segment else []
        starts_mid_sentence = True
        if segment and blocks and segment.pos_start is not None:
            starts_mid_sentence = not any(b.pos_start == segment.pos_start for b in blocks)
        sentence, offset = pick_search_sentence(text, starts_mid_sentence)

        page = volume = None
        if blocks and segment and segment.file_id in paged_files:
            absolute = (segment.pos_start or 0) + offset if segment and segment.pos_start is not None else None
            chosen = None
            if absolute is not None:
                chosen = next(
                    (b for b in blocks if (b.pos_start or 0) <= absolute <= (b.pos_end or 0)),
                    None,
                )
            page, volume = _block_page(chosen or blocks[0])

        result[id(meta)] = {
            "name": name,
            "file_type": file_type,
            "page": page,
            "volume": volume,
            "page_kind": ("pdf" if file_type == "pdf" else "printed") if page else None,
            "sentence": sentence,
        }
    return result


async def attach_reference_data(db, citation_maps) -> None:
    """Add `_ref` (work name, page, search sentence) to every text citation, in place."""
    from services.references import build_references

    metas = {}
    for citation_map in citation_maps:
        if isinstance(citation_map, dict):
            for meta in citation_map.values():
                if isinstance(meta, dict):
                    metas[id(meta)] = meta
    references = await build_references(db, metas.values())
    for key, ref in references.items():
        metas[key]["_ref"] = ref
