"""Robust text decoding for uploaded documents.

Handles BOM-marked UTF-8/UTF-16, HTML-declared charsets, Arabic Windows
(cp1256) exports, and generic Latin fallbacks. Content is returned without
Unicode normalization so source text (especially Quranic text) stays
byte-faithful at the code-point level; filenames are normalized separately.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

_HTML_CHARSET_RE = re.compile(
    rb"""<meta[^>]+charset\s*=\s*["']?\s*([a-zA-Z0-9_\-]+)""",
    re.IGNORECASE,
)
_HTML_CHARSET_HTTP_EQUIV_RE = re.compile(
    rb"""<meta[^>]+content\s*=\s*["'][^"']*charset\s*=\s*([a-zA-Z0-9_\-]+)""",
    re.IGNORECASE,
)
_CODEPAGE_RE = re.compile(r"^(?:cp|windows-)(\d+)$", re.IGNORECASE)

_CHARSET_ALIASES = {
    "utf8": "utf-8",
    "utf-8": "utf-8",
    "unicode": "utf-16",
    "utf16": "utf-16",
    "utf-16le": "utf-16-le",
    "utf-16be": "utf-16-be",
    "windows-1256": "cp1256",
    "cp-1256": "cp1256",
    "arabic": "cp1256",
    "iso-8859-6": "iso-8859-6",
    "iso8859-6": "iso-8859-6",
    "windows-1252": "cp1252",
    "cp-1252": "cp1252",
}


def _canonical_charset(value: str | None) -> Optional[str]:
    if not value:
        return None
    label = value.strip().strip("\"'").lower()
    if label in _CHARSET_ALIASES:
        return _CHARSET_ALIASES[label]
    match = _CODEPAGE_RE.match(label)
    if match:
        return f"cp{match.group(1)}"
    return label


def sniff_html_charset(raw: bytes) -> Optional[str]:
    """Return the charset declared in the first 8 KiB of an HTML document."""
    head = raw[:8192]
    for pattern in (_HTML_CHARSET_RE, _HTML_CHARSET_HTTP_EQUIV_RE):
        match = pattern.search(head)
        if match:
            return _canonical_charset(match.group(1).decode("ascii", errors="ignore"))
    return None


def _looks_utf16_without_bom(raw: bytes, *, allow_fallback: bool = True) -> Optional[str]:
    """Heuristic for BOM-less UTF-16 text.

    For Latin/Arabic UTF-16 one byte of each pair is a small high byte
    (0x00 for ASCII, 0x06 for Arabic); for CJK/BMP text both bytes are
    non-zero, so a short decoded-printability score is used as fallback.
    """
    if len(raw) < 4 or len(raw) % 2 != 0:
        return None
    sample = raw[:4096]
    pairs = len(sample) // 2
    if pairs == 0:
        return None

    even_high = sum(1 for byte in sample[0::2] if byte <= 0x08) / pairs
    odd_high = sum(1 for byte in sample[1::2] if byte <= 0x08) / pairs
    if odd_high > 0.8 and even_high < 0.3:
        return "utf-16-le"
    if even_high > 0.8 and odd_high < 0.3:
        return "utf-16-be"

    # CJK/BMP UTF-16: the high byte of each pair sits in 0x30..0x9F.
    even_cjk = sum(1 for byte in sample[0::2] if 0x30 <= byte <= 0x9F) / pairs
    odd_cjk = sum(1 for byte in sample[1::2] if 0x30 <= byte <= 0x9F) / pairs
    if odd_cjk > 0.8 and even_cjk < 0.3:
        return "utf-16-le"
    if even_cjk > 0.8 and odd_cjk < 0.3:
        return "utf-16-be"

    if not allow_fallback:
        return None
    # Plain ASCII/UTF-8 text is never BOM-less UTF-16; decoding it as UTF-16
    # produces plausible-looking CJK gibberish.
    if all(byte < 0x80 for byte in sample):
        return None

    # Fallback for CJK/BMP text where neither byte is a small high byte.
    best_encoding: Optional[str] = None
    best_score = 0.0
    for encoding in ("utf-16-le", "utf-16-be"):
        decoded = _try_decode(raw[:2048], encoding)
        if not decoded:
            continue
        text = decoded.replace("\ufffd", "")
        if len(text) < 8:
            continue
        controls = sum(
            1 for char in text
            if ord(char) < 32 and char not in "\n\r\t"
        )
        letters = sum(
            1 for char in text
            if char.isalpha() or char.isdigit() or char.isspace()
        )
        score = letters / len(text) - controls / len(text)
        if score > best_score:
            best_score = score
            best_encoding = encoding
    if best_encoding and best_score > 0.9:
        return best_encoding
    return None


def looks_like_binary(raw: bytes) -> bool:
    """Detect binary payloads that should not be ingested as text documents."""
    if not raw:
        return False
    if raw.startswith((b"\xff\xfe", b"\xfe\xff", b"\xef\xbb\xbf")):
        return False
    if _looks_utf16_without_bom(raw, allow_fallback=False):
        return False
    sample = raw[:8192]
    if b"\x00" in sample:
        return True
    control = sum(
        1
        for byte in sample
        if byte < 32 and byte not in (9, 10, 13, 12, 11)
    )
    return control / len(sample) > 0.05


def _try_decode(raw: bytes, encoding: str) -> Optional[str]:
    try:
        return raw.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return None


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def decode_bytes(raw: bytes, declared_charset: str | None = None) -> str:
    """Decode document bytes without mutating the underlying characters.

    Order is intentional: BOM and declared charset win, then strict UTF-8,
    then BOM-less UTF-16, then Arabic Windows-1256, then Latin fallbacks.
    ``cp1256`` must not be tried before UTF-16 because it accepts every byte
    and would silently turn UTF-16 files into mojibake.
    """
    if not raw:
        return ""

    # 1. Byte-order marks are authoritative.
    if raw.startswith(b"\xef\xbb\xbf"):
        return _normalize_newlines(raw.decode("utf-8-sig", errors="replace"))
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return _normalize_newlines(raw.decode("utf-16", errors="replace"))

    # 2. Charset declared by the document (HTML meta, etc.).
    charset = _canonical_charset(declared_charset)
    if charset:
        decoded = _try_decode(raw, charset)
        if decoded is not None:
            return _normalize_newlines(decoded)

    # 3. Strong BOM-less UTF-16 signals (ASCII/Arabic/CJK byte structure).
    utf16_encoding = _looks_utf16_without_bom(raw, allow_fallback=False)
    if utf16_encoding:
        decoded = _try_decode(raw, utf16_encoding)
        if decoded is not None:
            return _normalize_newlines(decoded)

    # 4. Strict UTF-8 is the default for modern exports.
    decoded = _try_decode(raw, "utf-8")
    if decoded is not None:
        return _normalize_newlines(decoded)

    # 5. Arabic Windows exports are common for Shamela/desktop tools.
    #    Only choose cp1256 when the payload actually looks Arabic; otherwise
    #    a Western Windows-1252 file would be decoded as Arabic letters.
    sample = raw[:8192]
    arabic_bytes = sum(1 for byte in sample if 0xC7 <= byte <= 0xFE)
    if sample and arabic_bytes / len(sample) > 0.10:
        decoded = _try_decode(raw, "cp1256")
        if decoded is not None:
            return _normalize_newlines(decoded)

    # 6. Weaker BOM-less UTF-16 fallback for uncommon scripts.
    utf16_encoding = _looks_utf16_without_bom(raw, allow_fallback=True)
    if utf16_encoding:
        decoded = _try_decode(raw, utf16_encoding)
        if decoded is not None:
            return _normalize_newlines(decoded)

    # 7. Latin Windows fallback, then Arabic, then lossy UTF-8.
    for encoding in ("cp1252", "cp1256", "iso-8859-6"):
        decoded = _try_decode(raw, encoding)
        if decoded is not None:
            return _normalize_newlines(decoded)

    return _normalize_newlines(raw.decode("utf-8", errors="replace"))


def read_text_file(path: str | Path, *, html: bool = False) -> str:
    raw = Path(path).read_bytes()
    declared = sniff_html_charset(raw) if html else None
    return decode_bytes(raw, declared_charset=declared)
