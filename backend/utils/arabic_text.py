"""Arabic text normalization used only for embedding/search.

Displayed and exported text keeps its original diacritics; embeddings use a
light normalization so queries written without tashkeel still match fully
vocalized Arabic sources (Quran, Shamela exports, ...).
"""

import re

_ARABIC_DIACRITICS_RE = re.compile(
    r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]"
)
_ARABIC_RANGE_RE = re.compile(r"[\u0600-\u06ff]")
_ALEF_VARIANTS_RE = re.compile(r"[أإآٱ]")
_TATWEEL_RE = re.compile(r"\u0640")


def contains_arabic(text: str) -> bool:
    return bool(text) and bool(_ARABIC_RANGE_RE.search(text))


def normalize_arabic_for_embedding(text: str) -> str:
    """Normalize Arabic orthography without changing non-Arabic content."""
    if not text or not contains_arabic(text):
        return text

    normalized = _ARABIC_DIACRITICS_RE.sub("", text)
    normalized = _TATWEEL_RE.sub("", normalized)
    normalized = _ALEF_VARIANTS_RE.sub("ا", normalized)
    normalized = normalized.replace("ى", "ي")
    return normalized
