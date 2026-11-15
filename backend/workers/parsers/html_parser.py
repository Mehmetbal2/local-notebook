import asyncio
import base64
import binascii
import html as html_lib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote

from utils.text_decoding import read_text_file

from .base import BaseParser, Block, ParseResult

try:  # BeautifulSoup is already a project dependency (EPUB parsing).
    from bs4 import BeautifulSoup, NavigableString, Tag
except Exception:  # pragma: no cover - surfaced as a clear parse error at runtime
    BeautifulSoup = None  # type: ignore[assignment]
    NavigableString = ()  # type: ignore[assignment]
    Tag = ()  # type: ignore[assignment]

_ARABIC_INDIC_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_DROP_TAGS = ("script", "style", "noscript", "svg", "iframe", "object", "embed")
_HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_BLOCK_CONTAINERS = {"div", "section", "article", "main", "aside", "header", "footer", "nav", "figure"}
_INLINE_TAGS = {
    "span", "a", "b", "strong", "i", "em", "u", "s", "small", "big", "font",
    "sup", "sub", "code", "abbr", "cite", "q", "mark", "time", "label",
}
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\ufeff]")
_BRACKET_HEADING_RE = re.compile(r"^\[([^\]]{2,160})\]")


def _clean_text(text: str) -> str:
    """Collapse layout whitespace while preserving zero-width joiners."""
    if not text:
        return ""
    cleaned = text.replace("\xa0", " ").replace("\ufeff", "")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()


def _plain_for_detection(text: str) -> str:
    return _ZERO_WIDTH_RE.sub("", text).strip()


def _split_long_paragraph(text: str, max_chars: int = 800) -> List[str]:
    """Split long prose at punctuation or word boundaries with a hard cap."""
    text = _clean_text(text)
    if len(text) <= max_chars:
        return [text] if text else []

    chunks: List[str] = []
    remaining = text
    punctuation = "。！？!?؛;؟۔.:"

    while len(remaining) > max_chars:
        window = remaining[:max_chars]
        cut = max(window.rfind(char) for char in punctuation)
        if cut < max_chars * 0.55:
            cut = window.rfind(" ")
        if cut < max_chars * 0.55:
            cut = max_chars
        else:
            cut += 1
        chunk = remaining[:cut].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut:].strip()

    if remaining:
        chunks.append(remaining)
    return chunks


def _parse_page_locator(text: str, default: int) -> Tuple[Optional[int], int]:
    """Parse Shamela page headers such as ``(ص: ١٣)`` or ``(ج1 ص: 13)``."""
    if not text:
        return None, default

    normalized = text.translate(_ARABIC_INDIC_MAP)
    volume: Optional[int] = None

    volume_match = re.search(r"(?:الجزء|(?<![\w])ج)\s*[:\s]*(\d+)", normalized)
    if volume_match:
        try:
            volume = int(volume_match.group(1))
        except ValueError:
            volume = None

    page_match = re.search(
        r"(?:ص|الصفحة|page)\s*[:.\s]*(\d+)", normalized, flags=re.IGNORECASE
    )
    if page_match:
        try:
            page = int(page_match.group(1))
            if page > 0:
                return volume, page
        except ValueError:
            pass

    numbers = re.findall(r"\d+", normalized)
    if numbers:
        try:
            page = int(numbers[-1])
            if page > 0:
                return volume, page
        except ValueError:
            pass

    return volume, default


class HtmlParser(BaseParser):
    """HTML parser with specialized support for Maktaba Shamela Arabic books.

    Shamela exports wrap each printed page in ``div.PageText`` and repeat a
    running header (``div.PageHead``) containing the book title and printed
    page number. The header is metadata, not content: it is consumed for page
    numbering and deliberately excluded from blocks, embeddings, and summaries.
    """

    def get_supported_extensions(self) -> List[str]:
        return [".htm", ".html"]

    async def parse(
        self,
        file_path: str,
        file_id: Optional[str] = None,
        db=None,
    ) -> ParseResult:
        return await asyncio.to_thread(self._parse_sync, file_path, file_id)

    # ---------- top-level parsing ----------

    def _parse_sync(self, file_path: str, file_id: Optional[str]) -> ParseResult:
        if BeautifulSoup is None:
            raise RuntimeError("beautifulsoup4 is required to parse HTML documents")

        raw_html = read_text_file(file_path, html=True)

        path = Path(file_path)
        self._source_dir = path.parent
        self._image_dir = path.parent / "images" / file_id if file_id else None
        self._images: List[Dict[str, Any]] = []

        # Shamela exports use orphan </p> tags as separators (thousands of
        # closers for a handful of openers). Valid HTML keeps its <p> structure.
        open_p = len(re.findall(r"<p\b", raw_html, flags=re.IGNORECASE))
        close_p = len(re.findall(r"</p\s*>", raw_html, flags=re.IGNORECASE))
        orphan_paragraphs = close_p > max(open_p * 3, open_p + 50)

        if orphan_paragraphs:
            normalized_html = re.sub(
                r"</?p\b[^>]*>|<br\b[^>]*/?>|<hr\b[^>]*/?>",
                "\n",
                raw_html,
                flags=re.IGNORECASE,
            )
        else:
            normalized_html = re.sub(
                r"<br\b[^>]*/?>|<hr\b[^>]*/?>",
                "\n",
                raw_html,
                flags=re.IGNORECASE,
            )

        soup = BeautifulSoup(normalized_html, "html.parser")
        for tag in soup(list(_DROP_TAGS)):
            tag.decompose()

        page_divs = soup.find_all("div", class_="PageText")
        if page_divs:
            collected, max_page = self._extract_shamela_pages(page_divs)
        else:
            body = soup.body or soup
            collected = self._extract_container(body, page_num=0, volume=None)
            max_page = 0

        blocks, full_text = self._build_blocks(collected)
        return ParseResult(
            text=full_text,
            blocks=blocks,
            page_count=max_page,
            images=self._images,
        )

    def _extract_shamela_pages(
        self, page_divs: list
    ) -> Tuple[List[Tuple[str, str, int, Dict[str, Any]]], int]:
        collected: List[Tuple[str, str, int, Dict[str, Any]]] = []
        max_page = 0

        for index, page_div in enumerate(page_divs):
            page_num = index + 1
            volume: Optional[int] = None

            head = page_div.find("div", class_="PageHead")
            if head is not None:
                page_number_el = head.find("span", class_="PageNumber")
                if page_number_el is not None:
                    volume, page_num = _parse_page_locator(
                        page_number_el.get_text(" ", strip=True), page_num
                    )
                # Running headers are metadata only.
                head.decompose()

            # Some exports keep these spans outside .PageHead.
            for stray in page_div.find_all(True, class_=["PageNumber", "PartName"]):
                stray.decompose()

            max_page = max(max_page, page_num)
            collected.extend(
                self._extract_container(page_div, page_num=page_num, volume=volume)
            )

        return collected, max_page

    def _extract_container(
        self,
        container,
        *,
        page_num: int,
        volume: Optional[int],
    ) -> List[Tuple[str, str, int, Dict[str, Any]]]:
        collected: List[Tuple[str, str, int, Dict[str, Any]]] = []
        buffer: List[str] = []

        def with_volume(extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
            payload = dict(extra or {})
            if volume is not None:
                payload["volume"] = volume
            return payload

        def add(content: str, block_type: str, extra: Optional[Dict[str, Any]] = None) -> None:
            content = _clean_text(content)
            if not content or not _plain_for_detection(content):
                return
            collected.append((content, block_type, page_num, with_volume(extra)))

        def flush() -> None:
            if not buffer:
                return
            text = _clean_text(" ".join(buffer))
            buffer.clear()
            if not text or not _plain_for_detection(text):
                return
            for chunk in _split_long_paragraph(text, max_chars=800):
                add(chunk, "paragraph")

        def walk(node) -> None:
            for child in getattr(node, "children", []):
                if isinstance(child, NavigableString):
                    parts = str(child).split("\n")
                    for part_index, part in enumerate(parts):
                        if part.strip():
                            buffer.append(part)
                        if part_index < len(parts) - 1:
                            flush()
                    continue

                if not isinstance(child, Tag):
                    continue

                name = (child.name or "").lower()
                if name in _DROP_TAGS:
                    continue

                classes = set(child.get("class") or [])
                if "PageHead" in classes or "PageNumber" in classes or "PartName" in classes:
                    continue

                if name == "table":
                    flush()
                    self._emit_table(child, add)
                    continue

                if name == "img":
                    flush()
                    self._emit_image(child, page_num, add)
                    continue

                if name in _HEADING_TAGS:
                    flush()
                    add(child.get_text(" ", strip=True), "heading", {"level": _HEADING_TAGS[name]})
                    continue

                if name == "span" and "title" in classes:
                    text = _clean_text(child.get_text(" ", strip=True))
                    heading = self._bracket_heading(text)
                    if heading:
                        flush()
                        add(heading, "heading", {"level": 2})
                    elif text:
                        buffer.append(text)
                    continue

                if name in ("p", "blockquote", "pre", "li"):
                    flush()
                    if child.find(["table", "img"], recursive=True) is not None:
                        walk(child)
                        flush()
                        continue
                    text = child.get_text(" ", strip=True)
                    if name == "blockquote":
                        add(text, "quote")
                    elif name == "pre":
                        add(text, "code")
                    elif name == "li":
                        add(text, "list")
                    else:
                        for chunk in _split_long_paragraph(text, max_chars=800):
                            add(chunk, "paragraph")
                    continue

                if name in ("ul", "ol"):
                    flush()
                    for item in child.find_all("li", recursive=False):
                        add(item.get_text(" ", strip=True), "list")
                    continue

                if name in ("br", "hr"):
                    flush()
                    continue

                if name in _BLOCK_CONTAINERS:
                    flush()
                    walk(child)
                    flush()
                    continue

                if name in _INLINE_TAGS:
                    text = child.get_text(" ", strip=True)
                    if text:
                        buffer.append(text)
                    continue

                # Unknown tags are treated as containers so inline content is not lost.
                walk(child)

        walk(container)
        flush()
        return collected

    # ---------- headings ----------

    @staticmethod
    def _bracket_heading(text: str) -> Optional[str]:
        cleaned = _plain_for_detection(text)
        if not cleaned.startswith("["):
            return None
        match = _BRACKET_HEADING_RE.match(cleaned)
        if not match:
            return None
        heading = _clean_text(match.group(1))
        return heading or None

    # ---------- tables ----------

    def _emit_table(self, table, add) -> None:
        table_html, plain_text, caption, footnote = self._table_payload(table)
        if not plain_text:
            return

        extra: Dict[str, Any] = {"is_table": True, "table_html": table_html}
        if caption:
            extra["table_caption"] = caption
        if footnote:
            extra["table_footnote"] = footnote
        add(plain_text, "paragraph", extra)

    def _table_payload(self, table) -> Tuple[str, str, str, str]:
        rows = [
            row for row in table.find_all("tr")
            if row.find_parent("table") is table
        ]
        if not rows:
            return "", "", "", ""

        caption_el = table.find("caption")
        caption = _clean_text(caption_el.get_text(" ", strip=True)) if caption_el else ""

        footnote_el = table.find("tfoot") or table.find(True, class_="footnote")
        footnote = _clean_text(footnote_el.get_text(" ", strip=True)) if footnote_el else ""

        html_rows: List[str] = []
        plain_rows: List[str] = []
        has_header = False

        for row_index, row in enumerate(rows):
            cells = row.find_all(["th", "td"], recursive=False)
            if not cells:
                cells = [
                    cell for cell in row.find_all(["th", "td"])
                    if cell.find_parent("tr") is row
                ]
            if not cells:
                continue

            is_header = any(cell.name == "th" for cell in cells) or row_index == 0
            has_header = has_header or is_header
            html_cells: List[str] = []
            plain_cells: List[str] = []

            for cell in cells:
                cell_text = _clean_text(cell.get_text(" ", strip=True))
                plain_cells.append(cell_text)
                attrs = ""
                for attr in ("colspan", "rowspan"):
                    value = str(cell.get(attr) or "").strip()
                    if value.isdigit() and int(value) > 1:
                        attrs += f' {attr}="{value}"'
                tag = "th" if is_header else "td"
                html_cells.append(f"<{tag}{attrs}>{html_lib.escape(cell_text)}</{tag}>")

            html_rows.append("<tr>" + "".join(html_cells) + "</tr>")
            plain_rows.append(" | ".join(plain_cells))

        if not html_rows:
            return "", "", "", ""

        if has_header and len(html_rows) > 1:
            table_html = (
                "<table><thead>" + html_rows[0] + "</thead>"
                "<tbody>" + "".join(html_rows[1:]) + "</tbody></table>"
            )
        else:
            table_html = "<table><tbody>" + "".join(html_rows) + "</tbody></table>"

        plain_text = "\n".join(plain_rows)
        if caption:
            plain_text = f"{caption}\n{plain_text}"
        if footnote:
            plain_text = f"{plain_text}\n{footnote}"
        return table_html, plain_text, caption, footnote

    # ---------- images ----------

    def _emit_image(self, image, page_num: int, add) -> None:
        src = str(image.get("src") or "").strip()
        alt = _clean_text(str(image.get("alt") or ""))
        title = _clean_text(str(image.get("title") or ""))

        local_path = self._save_image(src)
        if local_path is None:
            # Remote images are intentionally not fetched (no network/SSRF),
            # but their accessible text is preserved.
            fallback = alt or title
            if fallback:
                add(fallback, "paragraph")
            return

        image_index = len(self._images)
        self._images.append({
            "image_index": image_index,
            "file_path": str(local_path),
            "page": page_num,
            "img_name": local_path.name,
        })

        extra: Dict[str, Any] = {
            "is_image": True,
            "image_index": image_index,
            "image_name": local_path.name,
        }
        caption = title or alt
        if caption:
            extra["image_caption"] = caption
        add(caption or "[Image]", "paragraph", extra)

    def _save_image(self, src: str) -> Optional[Path]:
        if not src or self._image_dir is None:
            return None

        data_match = re.match(
            r"^data:image/([a-zA-Z0-9.+-]+);base64,(.+)$", src, flags=re.DOTALL
        )
        if data_match:
            ext = data_match.group(1).lower()
            if ext == "jpeg":
                ext = "jpg"
            if ext not in {"jpg", "png", "gif", "webp", "bmp"}:
                return None
            try:
                raw = base64.b64decode(data_match.group(2), validate=False)
            except (binascii.Error, ValueError):
                return None
            return self._write_image(raw, ext, prefix="embedded")

        if re.match(r"^(?:[a-z]+:)?//", src, flags=re.IGNORECASE):
            return None

        relative = unquote(src.split("?", 1)[0].split("#", 1)[0]).lstrip("/")
        candidate = (self._source_dir / relative).resolve()
        try:
            candidate.relative_to(self._source_dir.resolve())
        except ValueError:
            return None
        if not candidate.is_file():
            return None

        ext = candidate.suffix.lstrip(".").lower() or "jpg"
        if ext == "jpeg":
            ext = "jpg"
        if ext not in {"jpg", "png", "gif", "webp", "bmp"}:
            return None
        try:
            raw = candidate.read_bytes()
        except OSError:
            return None
        return self._write_image(raw, ext, prefix=candidate.stem)

    def _write_image(self, raw: bytes, ext: str, *, prefix: str) -> Optional[Path]:
        if not raw or self._image_dir is None:
            return None
        safe_ext = re.sub(r"[^a-zA-Z0-9]", "", ext.lower()) or "jpg"
        safe_prefix = re.sub(r"[^a-zA-Z0-9_-]", "_", prefix)[:40] or "image"
        self._image_dir.mkdir(parents=True, exist_ok=True)
        target = self._image_dir / f"{safe_prefix}_{len(self._images)}.{safe_ext}"
        try:
            target.write_bytes(raw)
        except OSError:
            return None
        return target

    # ---------- blocks ----------

    @staticmethod
    def _build_blocks(
        collected: List[Tuple[str, str, int, Dict[str, Any]]]
    ) -> Tuple[List[Block], str]:
        blocks: List[Block] = []
        contents: List[str] = []
        position_offset = 0

        for content, block_type, page_num, extra in collected:
            start_pos = position_offset
            end_pos = start_pos + len(content)
            position_offset = end_pos + 1

            blocks.append(
                Block(
                    id=f"b_{len(blocks)}",
                    type=block_type,
                    content=content,
                    position={"start": start_pos, "end": end_pos},
                    page=page_num,
                    extra=extra if extra else None,
                )
            )
            contents.append(content)

        return blocks, "\n".join(contents)
