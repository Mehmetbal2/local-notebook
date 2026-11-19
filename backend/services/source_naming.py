"""Suggest a "Author - Year - Title" name for a source, for the user to review and confirm.

The suggestion is read from the file name and the opening pages (title page, imprint).
Nothing is renamed here: the user edits the suggestion and decides.
"""

from __future__ import annotations

import json
import logging
import re

import config
from services.llm_provider import complete_text

logger = logging.getLogger(__name__)

OPENING_TEXT_CHARS = 6000
# "Author - Year - Title", year may be a range (1408/1988) or "t.y." / "n.d." (no date).
BIBLIOGRAPHIC_NAME_RE = re.compile(
    # The author part must allow hyphens (Ebü'l-Hasan, Jean-Paul); only a spaced dash
    # separates the fields, so a hyphen inside a name is not mistaken for a separator.
    r"^\s*.+?\s+[-–]\s+(?:\d{3,4}(?:\s*/\s*\d{3,4})?|t\.\s?y\.|n\.\s?d\.)\s+[-–]\s+\S.*$",
    re.IGNORECASE,
)

_SYSTEM_PROMPT = (
    "You identify the bibliographic data of a document from its file name and opening pages. "
    "You never invent data: a field you cannot read from the material stays empty."
)


def is_bibliographic_name(name_without_extension: str) -> bool:
    return bool(BIBLIOGRAPHIC_NAME_RE.match(name_without_extension or ""))


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _clean(value: object, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip().strip("-–").strip()
    # Characters that cannot appear in file names on common systems.
    text = re.sub(r'[\\/:*?"<>|]', "", text)
    return text[:limit]


async def suggest_source_name(
    *,
    file_name: str,
    opening_text: str,
    output_language: str,
    user_id: str,
) -> dict:
    api_key, _base_url, model, _api_format = await config.resolve_easy_task_llm_provider_config()
    if not api_key or not model:
        raise RuntimeError("LLM is not configured")

    prompt = (
        "Identify this document's author, year and title so it can be named "
        "\"Author - Year - Title\".\n\n"
        "Rules:\n"
        "- Use only what the file name and the opening pages show (title page, imprint, cover).\n"
        "- author: the author's name as usually cited (surname-first is not required). For several "
        "authors, the first one followed by \"et al.\". For a translation, the original author.\n"
        "- year: the publication year of this edition as printed; keep a dual year such as "
        "\"1408/1988\" as printed. Leave it empty if no year is shown — do not use the author's "
        "dates or guess.\n"
        "- title: the work's title without subtitle, translator or publisher.\n"
        f"- For works in Arabic or another non-Latin script, give author and title in the "
        f"transliteration customary in {output_language}-language scholarship, unless the file "
        "name already uses a specific form; then keep that form.\n"
        "- confidence: \"high\" when all three come from the title page or imprint, "
        "\"medium\" when one is inferred from the file name, \"low\" otherwise.\n"
        "- note: one short sentence in "
        f"{output_language} saying where the data came from or what is missing.\n\n"
        "Reply with JSON only: "
        "{\"author\": \"\", \"year\": \"\", \"title\": \"\", \"confidence\": \"\", \"note\": \"\"}\n\n"
        f"File name: {file_name}\n\n"
        f"Opening pages:\n{opening_text[:OPENING_TEXT_CHARS]}"
    )
    # Reasoning on: transliteration, dual (Hijri/Gregorian) years and telling the author
    # from the translator or editor are judgement calls, and the user waits for few files.
    text = await complete_text(
        prompt,
        system_prompt=_SYSTEM_PROMPT,
        user_id=user_id,
        max_tokens=6000,
        timeout=150,
        thinking=True,
    )
    data = _parse_json(text)
    confidence = str(data.get("confidence") or "").lower()
    return {
        "author": _clean(data.get("author"), 120),
        "year": _clean(data.get("year"), 20),
        "title": _clean(data.get("title"), 200),
        "confidence": confidence if confidence in {"high", "medium", "low"} else "low",
        "note": _clean(data.get("note"), 300),
    }
