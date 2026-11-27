"""Local, offline PDF parsing with PyMuPDF.

Produces the same Block layout as the OCR-service path (headings, paragraphs, lists,
tables, images, 0-1000 normalised bounding boxes) so the rest of the pipeline and
the PDF viewer do not care which engine ran. Works only for PDFs with a text
layer; scanned pages are detected so the caller can route them to OCR.
"""

from __future__ import annotations

import logging
import re
import statistics
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import Block, ParseResult
from .pdf_limits import PDF_MAX_TEXT_CHARS, PdfBudget, PdfTooLarge, text_flags
from utils.i18n import msg as ui_msg
from utils.errors import UserFacingError

logger = logging.getLogger("parsers.pymupdf")

_BULLET_RE = re.compile(r"^\s*(?:[•◦▪■●○\-–—*·]|\(?\d{1,3}[.)]|[a-zA-Z][.)]|[ivxIVX]{1,5}[.)])\s+")
_NUMBERED_HEADING_RE = re.compile(r"^\s*(?:\d{1,2}(?:\.\d{1,2}){0,3}\.?|[IVX]{1,5}\.|[A-ZÇĞİÖŞÜ]\.)\s+\S")
_PAGE_NUMBER_RE = re.compile(r"^\s*(?:[-–—]?\s*\d{1,4}\s*[-–—]?|[ivxlcIVXLC]{1,6}|(?:sayfa|page|s\.)\s*\d{1,4}(?:\s*/\s*\d{1,4})?)\s*$", re.IGNORECASE)
_HYPHEN_END_RE = re.compile(r"(\w)[-‐‑]$")
_MIN_IMAGE_SIDE = 48
_MIN_IMAGE_AREA_RATIO = 0.004  # of the page area; filters bullets, rules, logos in headers
# Document-wide limits: a small PDF can place one large image on thousands of pages.
# Each distinct image is written once, and the total is capped so a single upload
# cannot fill the disk.
_MAX_IMAGES_PER_DOCUMENT = 1000
_MAX_IMAGE_BYTES_PER_DOCUMENT = 500 * 1024 * 1024
# Decoded size is checked from the image's declared width and height before PyMuPDF
# decodes it: a few kilobytes of compressed data can declare gigabytes of pixels.
_MAX_IMAGE_PIXELS = 40_000_000  # e.g. 8000 x 5000
_MIN_TEXT_CHARS_PER_PAGE = 40  # below this on average the PDF is treated as scanned


@dataclass
class _Line:
    text: str
    bbox: Tuple[float, float, float, float]
    size: float
    bold: bool
    dir_rtl: bool


@dataclass
class _Para:
    lines: List[_Line] = field(default_factory=list)

    @property
    def text(self) -> str:
        out = ""
        for line in self.lines:
            piece = line.text.strip()
            if not piece:
                continue
            if not out:
                out = piece
            elif _HYPHEN_END_RE.search(out):
                out = _HYPHEN_END_RE.sub(r"\1", out) + piece
            else:
                out = f"{out} {piece}"
        return out

    @property
    def bbox(self) -> Tuple[float, float, float, float]:
        xs0 = [l.bbox[0] for l in self.lines]
        ys0 = [l.bbox[1] for l in self.lines]
        xs1 = [l.bbox[2] for l in self.lines]
        ys1 = [l.bbox[3] for l in self.lines]
        return (min(xs0), min(ys0), max(xs1), max(ys1))

    @property
    def size(self) -> float:
        return statistics.median(l.size for l in self.lines) if self.lines else 0.0

    @property
    def bold(self) -> bool:
        return bool(self.lines) and sum(1 for l in self.lines if l.bold) * 2 >= len(self.lines)


def _import_pymupdf():
    try:
        import pymupdf  # type: ignore
        return pymupdf
    except ImportError:
        try:
            import fitz  # type: ignore
            return fitz
        except ImportError as exc:
            raise UserFacingError(ui_msg("pymupdf_missing")) from exc


def _norm_bbox(bbox, width: float, height: float) -> List[int]:
    x0, y0, x1, y1 = bbox
    if width <= 0 or height <= 0:
        return [0, 0, 0, 0]
    clamp = lambda v: max(0, min(1000, int(round(v))))
    return [clamp(x0 / width * 1000), clamp(y0 / height * 1000), clamp(x1 / width * 1000), clamp(y1 / height * 1000)]


def parse_file(file_path: str, image_dir: Optional[Path] = None) -> ParseResult:
    """PyMuPDFParser().parse as a module-level function, so it can run in a child process."""
    return PyMuPDFParser(image_dir=image_dir).parse(file_path)


def has_text_layer(file_path: str, sample_pages: int = 8) -> Tuple[bool, int]:
    """(True, page_count) when the PDF carries enough extractable text to skip OCR."""
    pymupdf = _import_pymupdf()
    with pymupdf.open(file_path) as doc:
        page_count = doc.page_count
        if page_count == 0:
            return False, 0
        budget = PdfBudget(doc)
        step = max(1, page_count // sample_pages)
        sampled = 0
        chars = 0
        for index in budget.pages(range(0, page_count, step)):
            if sampled >= sample_pages:
                break
            chars += len(doc[index].get_text("text", flags=text_flags(pymupdf)).strip())
            sampled += 1
        return (chars / max(sampled, 1)) >= _MIN_TEXT_CHARS_PER_PAGE, page_count


class PyMuPDFParser:
    """Layout-aware text extraction from born-digital PDFs, no network needed."""

    def __init__(self, image_dir: Optional[Path] = None):
        self.image_dir = image_dir

    def parse(self, file_path: str) -> ParseResult:
        pymupdf = _import_pymupdf()
        blocks: List[Block] = []
        images: List[Dict[str, Any]] = []
        self._saved_xrefs: Dict[int, Tuple[str, str]] = {}
        self._saved_image_bytes = 0
        position = 0

        with pymupdf.open(file_path) as doc:
            page_count = doc.page_count
            budget = PdfBudget(doc)
            flags = text_flags(pymupdf)
            body_size = self._body_font_size(doc, budget, flags)
            repeated = self._repeated_edge_lines(doc, budget, flags)

            for page_index in budget.pages(range(page_count)):
                page = doc[page_index]
                width, height = page.rect.width, page.rect.height
                page_no = page_index + 1

                table_regions, table_blocks = self._extract_tables(page, page_no, width, height)
                paragraphs = self._page_paragraphs(page, table_regions, repeated, flags)
                image_blocks = self._extract_images(doc, page, page_no, width, height, images)

                # Merge text, tables and images in top-to-bottom order.
                items: List[Tuple[float, Block]] = []
                for para in paragraphs:
                    block = self._para_to_block(para, body_size, page_no, width, height)
                    if block is not None:
                        items.append((para.bbox[1], block))
                items.extend(table_blocks)
                items.extend(image_blocks)
                items.sort(key=lambda item: item[0])

                for _, block in items:
                    block.position = {"start": position, "end": position + len(block.content)}
                    position += len(block.content) + 1
                    blocks.append(block)
                if position > PDF_MAX_TEXT_CHARS:
                    raise PdfTooLarge(ui_msg("pdf_too_large", limit=PDF_MAX_TEXT_CHARS // (1024 * 1024)))

            if budget.skipped and not blocks:
                raise PdfTooLarge(ui_msg("pdf_too_large", limit=budget.page_limit // (1024 * 1024)))

        for index, block in enumerate(blocks):
            block.id = f"b_{index}"

        text = "\n".join(block.content for block in blocks)
        logger.info("pymupdf parsed %s: pages=%d blocks=%d images=%d", Path(file_path).name, page_count, len(blocks), len(images))
        return ParseResult(text=text, blocks=blocks, page_count=page_count, images=images)

    # ---------- document-level statistics ----------

    @staticmethod
    def _body_font_size(doc, budget: PdfBudget, flags: int) -> float:
        sizes: List[float] = []
        step = max(1, doc.page_count // 12)
        for index in budget.pages(range(0, doc.page_count, step)):
            for block in doc[index].get_text("dict", flags=flags).get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if text:
                            sizes.extend([round(span.get("size", 0), 1)] * len(text))
            if len(sizes) > 20000:
                break
        return statistics.median(sizes) if sizes else 11.0

    @staticmethod
    def _repeated_edge_lines(doc, budget: PdfBudget, flags: int) -> set:
        """Running headers/footers: short lines at the page edge that recur on many pages."""
        if doc.page_count < 4:
            return set()
        counts: Dict[str, int] = {}
        step = max(1, doc.page_count // 20)
        sampled = 0
        for index in budget.pages(range(0, doc.page_count, step)):
            page = doc[index]
            height = page.rect.height
            seen = set()
            for block in page.get_text("dict", flags=flags).get("blocks", []):
                y0, y1 = block.get("bbox", (0, 0, 0, 0))[1], block.get("bbox", (0, 0, 0, 0))[3]
                if y1 > height * 0.12 and y0 < height * 0.88:
                    continue
                for line in block.get("lines", []):
                    text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
                    normalised = re.sub(r"\d+", "#", text)
                    if 0 < len(normalised) <= 80:
                        seen.add(normalised)
            for key in seen:
                counts[key] = counts.get(key, 0) + 1
            sampled += 1
        return {key for key, count in counts.items() if count >= max(3, sampled * 0.4)}

    # ---------- text ----------

    def _page_paragraphs(self, page, table_regions, repeated: set, flags: int) -> List[_Para]:
        width, height = page.rect.width, page.rect.height
        paragraphs: List[_Para] = []
        pymupdf = _import_pymupdf()

        text_blocks = [b for b in page.get_text("dict", flags=flags).get("blocks", []) if b.get("type") == 0]
        for block in self._reading_order(text_blocks, width):
            rect = pymupdf.Rect(block["bbox"])
            if any(self._overlaps(rect, region) for region in table_regions):
                continue

            current = _Para()
            prev: Optional[_Line] = None
            for raw_line in block.get("lines", []):
                spans = [s for s in raw_line.get("spans", []) if s.get("text", "").strip()]
                if not spans:
                    continue
                text = "".join(s["text"] for s in raw_line["spans"]).strip()
                if not text:
                    continue
                y0, y1 = raw_line["bbox"][1], raw_line["bbox"][3]
                at_edge = y1 <= height * 0.12 or y0 >= height * 0.88
                if at_edge and (re.sub(r"\d+", "#", text) in repeated or _PAGE_NUMBER_RE.match(text)):
                    continue

                total = sum(len(s["text"]) for s in spans) or 1
                size = sum(s.get("size", 0) * len(s["text"]) for s in spans) / total
                bold = sum(len(s["text"]) for s in spans if self._span_bold(s)) * 2 >= total
                line = _Line(text=text, bbox=tuple(raw_line["bbox"]), size=size, bold=bold, dir_rtl=raw_line.get("dir", (1, 0))[0] < 0)

                if prev is not None and self._starts_new_paragraph(prev, line):
                    if current.lines:
                        paragraphs.append(current)
                    current = _Para()
                current.lines.append(line)
                prev = line
            if current.lines:
                paragraphs.append(current)

        return self._merge_split_paragraphs(paragraphs, width)

    @staticmethod
    def _reading_order(blocks: List[Dict[str, Any]], width: float) -> List[Dict[str, Any]]:
        """Top-to-bottom, but a block in the left column is read before the right column.

        Full-width blocks (titles, wide paragraphs) split the page into bands; inside a
        band narrow blocks are grouped by the half of the page they sit in.
        """
        ordered: List[Dict[str, Any]] = []
        band: List[Dict[str, Any]] = []

        def flush():
            if band:
                band.sort(key=lambda blk: (0 if (blk["bbox"][0] + blk["bbox"][2]) / 2 < width / 2 else 1, blk["bbox"][1]))
                ordered.extend(band)
                band.clear()

        for block in sorted(blocks, key=lambda blk: (round(blk["bbox"][1]), blk["bbox"][0])):
            x0, _, x1, _ = block["bbox"]
            if (x1 - x0) >= width * 0.6:
                flush()
                ordered.append(block)
            else:
                band.append(block)
        flush()
        return ordered

    @staticmethod
    def _span_bold(span: Dict[str, Any]) -> bool:
        if span.get("flags", 0) & 16:
            return True
        font = str(span.get("font", "")).lower()
        return "bold" in font or "black" in font or "heavy" in font or "semibold" in font

    @staticmethod
    def _starts_new_paragraph(prev: _Line, line: _Line) -> bool:
        gap = line.bbox[1] - prev.bbox[3]
        line_height = max(prev.bbox[3] - prev.bbox[1], 1.0)
        if gap > line_height * 0.9:
            return True
        if abs(line.size - prev.size) > max(1.5, prev.size * 0.15):
            return True
        if prev.bold != line.bold and (len(prev.text) < 80 or len(line.text) < 80):
            return True
        if _BULLET_RE.match(line.text) and not _BULLET_RE.match(prev.text):
            return True
        if _BULLET_RE.match(line.text) and _BULLET_RE.match(prev.text):
            return True
        return False

    @staticmethod
    def _merge_split_paragraphs(paragraphs: List[_Para], width: float) -> List[_Para]:
        """PyMuPDF splits a paragraph into several blocks when spacing is uneven; glue them back."""
        merged: List[_Para] = []
        for para in paragraphs:
            if merged:
                last = merged[-1]
                last_text = last.text
                gap = para.bbox[1] - last.bbox[3]
                same_column = abs(para.bbox[0] - last.bbox[0]) < width * 0.08
                continues = (
                    same_column
                    and gap < max(last.size, 1.0) * 0.8
                    and abs(para.size - last.size) < 1.0
                    and last_text
                    and not last_text.rstrip().endswith((".", "!", "?", ":", "؟", "۔", "。", "！", "？"))
                    and not _BULLET_RE.match(para.text)
                    and last.bold == para.bold
                )
                if continues:
                    last.lines.extend(para.lines)
                    continue
            merged.append(para)
        return merged

    @staticmethod
    def _overlaps(rect, region) -> bool:
        inter = rect & region
        if inter.is_empty:
            return False
        return inter.get_area() > rect.get_area() * 0.5

    def _para_to_block(self, para: _Para, body_size: float, page_no: int, width: float, height: float) -> Optional[Block]:
        text = para.text.strip()
        if not text:
            return None

        extra: Dict[str, Any] = {"bbox": _norm_bbox(para.bbox, width, height)}
        heading_level = self._heading_level(para, body_size, text)
        if heading_level:
            extra["level"] = heading_level
            return Block(id="", type="heading", content=text, position={"start": 0, "end": 0}, page=page_no, extra=extra)

        if len(para.lines) > 1 and sum(1 for l in para.lines if _BULLET_RE.match(l.text)) >= max(2, len(para.lines) // 2):
            items = self._list_items(para)
            extra["list_items"] = items
            return Block(id="", type="list", content="\n".join(items), position={"start": 0, "end": 0}, page=page_no, extra=extra)
        if _BULLET_RE.match(text) and len(text) < 400:
            extra["list_items"] = [text]
            return Block(id="", type="list", content=text, position={"start": 0, "end": 0}, page=page_no, extra=extra)

        return Block(id="", type="paragraph", content=text, position={"start": 0, "end": 0}, page=page_no, extra=extra)

    @staticmethod
    def _heading_level(para: _Para, body_size: float, text: str) -> int:
        if len(text) > 160 or "\n" in text or len(para.lines) > 3:
            return 0
        if text.endswith((".", ",", ";", "،", "؛")) and not _NUMBERED_HEADING_RE.match(text):
            return 0
        ratio = para.size / body_size if body_size else 1.0
        if ratio >= 1.6:
            return 1
        if ratio >= 1.3:
            return 2
        if ratio >= 1.12:
            return 3
        if para.bold and len(text) <= 100 and (ratio >= 1.0 or _NUMBERED_HEADING_RE.match(text)):
            return 3 if ratio >= 1.0 else 4
        if _NUMBERED_HEADING_RE.match(text) and len(text) <= 80 and len(para.lines) == 1 and ratio >= 1.0:
            return 3
        return 0

    @staticmethod
    def _list_items(para: _Para) -> List[str]:
        items: List[str] = []
        for line in para.lines:
            piece = line.text.strip()
            if _BULLET_RE.match(piece) or not items:
                items.append(piece)
            else:
                items[-1] = f"{items[-1]} {piece}"
        return items

    # ---------- tables ----------

    def _extract_tables(self, page, page_no: int, width: float, height: float):
        regions = []
        blocks: List[Tuple[float, Block]] = []
        try:
            finder = page.find_tables()
        except Exception as exc:  # older PyMuPDF or malformed page
            logger.debug("find_tables failed on page %d: %s", page_no, exc)
            return regions, blocks

        for table in getattr(finder, "tables", []):
            try:
                rows = table.extract()
            except Exception:
                continue
            cleaned = [[(cell or "").replace("\n", " ").strip() for cell in row] for row in rows if row]
            cleaned = [row for row in cleaned if any(row)]
            if len(cleaned) < 2 or max(len(row) for row in cleaned) < 2:
                continue
            columns = max(len(row) for row in cleaned)
            cleaned = [row + [""] * (columns - len(row)) for row in cleaned]

            md = ["| " + " | ".join(cleaned[0]) + " |", "| " + " | ".join(["---"] * columns) + " |"]
            md += ["| " + " | ".join(row) + " |" for row in cleaned[1:]]
            html = "<table>" + "".join(
                "<tr>" + "".join(f"<{'th' if r == 0 else 'td'}>{escape(cell)}</{'th' if r == 0 else 'td'}>" for cell in row) + "</tr>"
                for r, row in enumerate(cleaned)
            ) + "</table>"

            rect = table.bbox if not hasattr(table, "bbox") or not callable(table.bbox) else table.bbox()
            pymupdf = _import_pymupdf()
            rect = pymupdf.Rect(rect)
            regions.append(rect)
            blocks.append((rect.y0, Block(
                id="",
                type="paragraph",
                content="\n".join(md),
                position={"start": 0, "end": 0},
                page=page_no,
                extra={"is_table": True, "table_html": html, "bbox": _norm_bbox(rect, width, height)},
            )))
        return regions, blocks

    # ---------- images ----------


    @staticmethod
    def _image_size_ok(doc, xref: int, info: Dict[str, Any]) -> bool:
        """True when the image's declared pixel count is within _MAX_IMAGE_PIXELS."""
        def as_int(value) -> int:
            try:
                return int(str(value).strip().split()[0])
            except (TypeError, ValueError, IndexError):
                return 0

        width = as_int(info.get("width"))
        height = as_int(info.get("height"))
        try:
            width = max(width, as_int(doc.xref_get_key(xref, "Width")[1]))
            height = max(height, as_int(doc.xref_get_key(xref, "Height")[1]))
        except Exception:
            pass
        return 0 < width * height <= _MAX_IMAGE_PIXELS
    def _extract_images(self, doc, page, page_no: int, width: float, height: float, images: List[Dict[str, Any]]):
        blocks: List[Tuple[float, Block]] = []
        if self.image_dir is None:
            return blocks
        page_area = width * height
        seen_xrefs = set()

        for info in page.get_image_info(xrefs=True):
            xref = info.get("xref")
            bbox = info.get("bbox")
            if not xref or xref in seen_xrefs or not bbox:
                continue
            x0, y0, x1, y1 = bbox
            if (x1 - x0) < _MIN_IMAGE_SIDE or (y1 - y0) < _MIN_IMAGE_SIDE:
                continue
            if (x1 - x0) * (y1 - y0) < page_area * _MIN_IMAGE_AREA_RATIO:
                continue
            seen_xrefs.add(xref)
            if len(images) >= _MAX_IMAGES_PER_DOCUMENT:
                break
            if not self._image_size_ok(doc, xref, info):
                logger.info("image %s on page %d skipped: too many pixels", xref, page_no)
                continue
            index = len(images)
            saved = getattr(self, "_saved_xrefs", {}).get(xref)
            if saved is not None:
                # The same image object on another page: point to the file already written.
                target_path, name = saved
            else:
                if getattr(self, "_saved_image_bytes", 0) >= _MAX_IMAGE_BYTES_PER_DOCUMENT:
                    break
                try:
                    pymupdf = _import_pymupdf()
                    pix = pymupdf.Pixmap(doc, xref)
                    if pix.n - pix.alpha >= 4:  # CMYK -> RGB
                        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                    if pix.width < _MIN_IMAGE_SIDE or pix.height < _MIN_IMAGE_SIDE:
                        continue
                    self.image_dir.mkdir(parents=True, exist_ok=True)
                    name = f"p{page_no}_{index}.png"
                    target = self.image_dir / name
                    pix.save(str(target))
                    target_path = str(target)
                    self._saved_image_bytes = getattr(self, "_saved_image_bytes", 0) + target.stat().st_size
                    if not hasattr(self, "_saved_xrefs"):
                        self._saved_xrefs = {}
                    self._saved_xrefs[xref] = (target_path, name)
                except Exception as exc:
                    logger.debug("image %s on page %d skipped: %s", xref, page_no, exc)
                    continue

            images.append({"image_index": index, "file_path": target_path, "page": page_no, "img_name": name})
            blocks.append((y0, Block(
                id="",
                type="paragraph",
                content="[Image]",
                position={"start": 0, "end": 0},
                page=page_no,
                extra={"is_image": True, "image_index": index, "image_name": name, "image_source_type": "image", "bbox": _norm_bbox(bbox, width, height)},
            )))
        return blocks
