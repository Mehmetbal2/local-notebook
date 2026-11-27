"""Size limits for PDF text extraction.

A PDF is compressed. A few kilobytes of Flate data can expand to gigabytes of
page content, one content stream can be shared by thousands of pages, and one
form XObject can be drawn thousands of times from a single page. MuPDF expands
all of that in memory when a page's text is extracted, so the expanded size of
each page is measured first, with bounded decompression, and pages over the
budget are skipped instead of being extracted.
"""
from __future__ import annotations

import base64
import binascii
import logging
import os
import re
import zlib
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

_MB = 1024 * 1024


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


# Pages a document may have; longer documents are rejected outright.
PDF_MAX_PAGES = _env_int("PDF_MAX_PAGES", 5000)
# Expanded content one page may make MuPDF interpret (content streams plus every
# form XObject drawing); a page over it is skipped.
PDF_MAX_PAGE_CONTENT_BYTES = _env_int("PDF_MAX_PAGE_CONTENT_MB", 32) * _MB
# Expanded content of the whole document, counting a shared stream once per page.
PDF_MAX_CONTENT_BYTES = _env_int("PDF_MAX_CONTENT_MB", 1024) * _MB
# Text a document may yield; parsing stops with an error past it.
PDF_MAX_TEXT_CHARS = _env_int("PDF_MAX_TEXT_MB", 64) * _MB

# Each form drawing costs at least this much, so a page full of `Do` operators
# that draw an empty form still runs out of budget quickly.
_MIN_DRAW_COST = 64
_MAX_FORM_DEPTH = 12
# Upper bound on how much one byte can expand through one filter: deflate stays
# under ~1032:1, LZW ~2731:1 and RunLength 128:1.
_ANY_FILTER_MAX_RATIO = 4096
_FLATE_NAMES = {"/FlateDecode", "/Fl"}
_FILTER_NAME_RE = re.compile(r"/[A-Za-z0-9]+")
_DELIMS = rb"\s/\[\]()<>{}%"
_DO_RE = re.compile(rb"/([^" + _DELIMS + rb"]+)\s*Do(?![^" + _DELIMS + rb"])")


_DEFAULT = object()


class PdfTooLarge(RuntimeError):
    """The PDF would expand beyond the configured limits; the message is user-facing."""


def text_flags(pymupdf) -> int:
    """Flags for get_text("dict") without TEXT_PRESERVE_IMAGES.

    With the default flags MuPDF decodes every image on the page into the
    result, so a tiny, highly compressed image can take gigabytes of memory.
    """
    return pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES


def _ascii85(data: bytes) -> bytes:
    data = data.strip()
    if data.startswith(b"<~"):
        data = data[2:]
    end = data.find(b"~>")
    if end != -1:
        data = data[:end]
    return base64.a85decode(data, adobe=False, ignorechars=b" \t\n\r\x0b\x0c\x00")


def _ascii_hex(data: bytes) -> bytes:
    data = bytes(c for c in data.split(b">", 1)[0] if c not in b" \t\n\r\x0b\x0c\x00")
    if len(data) % 2:
        data += b"0"
    return binascii.unhexlify(data)


def _inflate(data: bytes, limit: int) -> Optional[bytes]:
    for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
        try:
            return zlib.decompressobj(wbits).decompress(data, limit + 1)
        except zlib.error:
            continue
    return None


def _decoded_stream(doc, xref: int, limit: int) -> Optional[bytes]:
    """The decoded stream, or None when it is larger than `limit` or unreadable.

    Flate and the ASCII filters (ReportLab writes `[/ASCII85Decode
    /FlateDecode]`) are decoded here with the output bounded; any other filter
    is left to MuPDF only when even its worst-case expansion fits the budget.
    """
    try:
        kind, value = doc.xref_get_key(xref, "Filter")
        data = doc.xref_stream_raw(xref)
    except Exception:
        return None
    if data is None:
        return b""
    filters = _FILTER_NAME_RE.findall(value) if kind in ("name", "array") else []
    for position, name in enumerate(filters):
        decoded: Optional[bytes] = None
        try:
            if name in _FLATE_NAMES:
                decoded = _inflate(data, limit)
            elif name in ("/ASCII85Decode", "/A85"):
                decoded = _ascii85(data)
            elif name in ("/ASCIIHexDecode", "/AHx"):
                decoded = _ascii_hex(data)
        except (ValueError, binascii.Error):
            decoded = None
        if decoded is None:
            # A filter decoded only by MuPDF, or data that only MuPDF's lenient
            # decoders accept: let MuPDF decode the whole chain when even the
            # worst case of the filters left fits the budget.
            if len(data) * _ANY_FILTER_MAX_RATIO ** (len(filters) - position) > limit:
                return None
            try:
                data = doc.xref_stream(xref) or b""
            except Exception:
                return None
            break
        data = decoded
        if len(data) > limit:
            return None
    return data if len(data) <= limit else None


def page_content_size(doc, page, limit: int) -> Optional[int]:
    """Bytes of content MuPDF interprets to draw `page`, or None when over `limit`.

    Every `Do` of a form XObject adds the form's own expanded size, so a form
    drawn many times, or forms nested inside forms, are all counted.
    """
    try:
        contents = page.get_contents()
        forms = page.get_xobjects()
    except Exception:
        return None
    by_invoker: Dict[int, Dict[str, int]] = {}
    for xref, name, invoker, _bbox in forms:
        by_invoker.setdefault(invoker, {})[name] = xref
    memo: Dict[int, Optional[int]] = {}

    def expanded(data: bytes, names: Dict[str, int], depth: int, active: frozenset) -> Optional[int]:
        total = len(data)
        if not names:
            return total
        for match in _DO_RE.finditer(data):
            target = names.get(match.group(1).decode("latin-1"))
            if target is None:
                continue  # an image XObject: not decoded for text extraction
            size = form_size(target, depth + 1, active)
            if size is None:
                return None
            total += max(size, _MIN_DRAW_COST)
            if total > limit:
                return None
        return total

    def form_size(xref: int, depth: int, active: frozenset) -> Optional[int]:
        if xref in active or depth > _MAX_FORM_DEPTH:
            return None
        if xref not in memo:
            data = _decoded_stream(doc, xref, limit)
            memo[xref] = None if data is None else expanded(
                data, by_invoker.get(xref, {}), depth, active | {xref}
            )
        return memo[xref]

    total = 0
    for xref in contents:
        data = _decoded_stream(doc, xref, limit - total)
        if data is None:
            return None
        size = expanded(data, by_invoker.get(0, {}), 0, frozenset())
        if size is None:
            return None
        total += size
        if total > limit:
            return None
    return total


class PdfBudget:
    """Decides, once per page, whether its text may be extracted."""

    def __init__(
        self,
        doc,
        *,
        max_pages: Optional[int] | object = _DEFAULT,
        page_limit: Optional[int] = None,
        total_limit: Optional[int] = None,
    ):
        """Raises PdfTooLarge when the document has more than `max_pages` pages.

        Limits left out are read from the module settings at call time;
        `max_pages=None` disables the page count check.
        """
        from utils.i18n import msg as ui_msg

        if max_pages is _DEFAULT:
            max_pages = PDF_MAX_PAGES
        self.doc = doc
        self.page_limit = page_limit or PDF_MAX_PAGE_CONTENT_BYTES
        self.total_limit = total_limit or PDF_MAX_CONTENT_BYTES
        self.total = 0
        self.skipped: List[int] = []
        self._ok: Dict[int, bool] = {}
        if max_pages is not None and doc.page_count > max_pages:
            raise PdfTooLarge(ui_msg("pdf_too_many_pages", count=doc.page_count, limit=max_pages))

    def page_ok(self, index: int) -> bool:
        if index not in self._ok:
            size = page_content_size(self.doc, self.doc[index], self.page_limit)
            ok = size is not None and self.total + size <= self.total_limit
            if size is not None and not ok:
                from utils.i18n import msg as ui_msg

                raise PdfTooLarge(ui_msg("pdf_too_large", limit=self.total_limit // _MB))
            if ok:
                self.total += size
            else:
                self.skipped.append(index + 1)
                logger.warning("PDF page %d skipped: its content expands beyond %d MB", index + 1, self.page_limit // _MB)
            self._ok[index] = ok
        return self._ok[index]

    def pages(self, indexes: Iterable[int]):
        """The pages among `indexes` whose text may be extracted."""
        for index in indexes:
            if self.page_ok(index):
                yield index


def extract_plain_text(
    data: bytes,
    *,
    max_pages: int,
    max_chars: int,
    page_limit: int = 8 * _MB,
    total_limit: int = 64 * _MB,
) -> str:
    """Plain text of the first `max_pages` pages of PDF bytes fetched from the web.

    Pages that would expand too much are skipped, and extraction stops once
    `max_chars` of text have been collected. Any failure yields "".
    """
    try:
        import pymupdf
    except ImportError:
        return ""
    parts: List[str] = []
    collected = 0
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            budget = PdfBudget(doc, max_pages=None, page_limit=page_limit, total_limit=total_limit)
            for index in budget.pages(range(min(doc.page_count, max_pages))):
                blocks = doc[index].get_text("blocks", flags=pymupdf.TEXTFLAGS_BLOCKS & ~pymupdf.TEXT_PRESERVE_IMAGES)
                text = "\n\n".join(b[4].replace("\n", " ").strip() for b in blocks if b[6] == 0)
                if text.strip():
                    parts.append(text[: max_chars - collected])
                    collected += len(parts[-1])
                if collected >= max_chars:
                    break
    except PdfTooLarge:
        pass  # keep what was collected before the document budget ran out
    except Exception:
        return ""
    return "\n\n".join(p.strip() for p in parts if p.strip())
