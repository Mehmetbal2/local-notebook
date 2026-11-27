import asyncio
import posixpath
import re
import zipfile
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote
from xml.etree import ElementTree

from .base import ARCHIVE_MAX_UNCOMPRESSED_BYTES, BaseParser, Block, ParseResult, check_zip_archive
from utils.i18n import msg as ui_msg
from utils.errors import UserFacingError


# Block-level tags extracted from chapter bodies in document order; tables are handled separately as markdown
_BLOCK_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "pre", "table")
# Used to find outermost blocks: an element with one of these tags among its ancestors is nested content and is skipped to avoid duplicates
_CONTAINER_TAGS = {"p", "li", "blockquote", "pre", "table"}
# Tags excluded from the body text index
_DROP_TAGS = ("script", "style", "nav", "header", "footer")


class EpubParser(BaseParser):
    """EPUB parser: extracts structured text in the reading order of the OPF spine.

    This version only extracts structured text; it does not reproduce the original layout:
    - Reading order comes from the spine, not from the order of file names in the zip.
    - page is always 0; chapter info (spine_index / href / chapter_title etc.) goes in extra,
      so PDF page-number logic is not misapplied.
    - Images are not extracted (images is empty).
    """

    def get_supported_extensions(self) -> List[str]:
        return [".epub"]

    async def parse(self, file_path: str) -> ParseResult:
        from .isolation import run_isolated

        # In a child process with a memory and time limit: see isolation.py.
        return await asyncio.to_thread(run_isolated, parse_file, file_path)

    def _parse_sync(self, file_path: str) -> ParseResult:
        import ebooklib
        from ebooklib import epub

        check_zip_archive(file_path)
        check_manifest_size(file_path)
        try:
            book = epub.read_epub(file_path)
        except Exception as exc:  # damaged file / invalid zip / missing OPF
            raise UserFacingError(ui_msg("epub_corrupt", error=exc)) from exc

        href_to_title = self._build_toc_title_map(book)

        # (content, block_type, extra) triples in the book's reading order
        collected: List[Tuple[str, str, Dict[str, Any]]] = []
        chapter_index = 0
        # A spine may list the same chapter many times, directly or through several
        # manifest ids that point at the same file; each file is read once, so a small
        # archive cannot multiply one large chapter into gigabytes of text.
        seen_items: set[str] = set()
        seen_files: set[str] = set()

        for spine_index, idref, linear in self._iter_spine(book):
            if idref in seen_items:
                continue
            seen_items.add(idref)
            item = book.get_item_with_id(idref)
            if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue
            if self._is_nav_document(item):
                continue

            href = item.get_name() or ""
            file_key = href.split("#", 1)[0].lower()
            if file_key in seen_files:
                continue
            seen_files.add(file_key)
            try:
                raw = item.get_content()
            except Exception:
                continue

            chapter_blocks = self._extract_chapter_blocks(raw)
            if not chapter_blocks:
                continue

            chapter_title = self._chapter_title(href, chapter_blocks, href_to_title)

            for content, block_type, extra in chapter_blocks:
                extra = dict(extra)
                extra.update(
                    {
                        "chapter_index": chapter_index,
                        "spine_index": spine_index,
                        "href": href,
                    }
                )
                if chapter_title:
                    extra["chapter_title"] = chapter_title
                if not linear:
                    extra["linear"] = False
                collected.append((content, block_type, extra))

            chapter_index += 1

        if not collected:
            raise UserFacingError(ui_msg("epub_no_text"))

        blocks, text = self._build_blocks(collected)

        return ParseResult(text=text, blocks=blocks, page_count=0, images=[])

    # ── spine ────────────────────────────────────────────────────────────────

    @staticmethod
    def _iter_spine(book) -> List[Tuple[int, str, bool]]:
        """Return a list of (spine_index, idref, linear) in reading order.

        ebooklib's book.spine items may be (idref, 'yes'/'no') tuples or bare idrefs.
        """
        result: List[Tuple[int, str, bool]] = []
        for index, entry in enumerate(book.spine or []):
            if isinstance(entry, (tuple, list)):
                idref = entry[0]
                linear_flag = entry[1] if len(entry) > 1 else "yes"
                linear = str(linear_flag).lower() != "no"
            else:
                idref = entry
                linear = True
            if idref:
                result.append((index, idref, linear))
        return result

    @staticmethod
    def _is_nav_document(item) -> bool:
        # The EPUB3 navigation document is XHTML with the nav property and must not be indexed as body text
        props = getattr(item, "properties", None) or []
        return "nav" in props

    # ── Table-of-contents title map ──────────────────────────────────────────────────────────

    def _build_toc_title_map(self, book) -> Dict[str, str]:
        """Build a flat href (without anchor) -> title map from the toc (NCX / EPUB3 nav)."""
        mapping: Dict[str, str] = {}

        def walk(nodes):
            for node in nodes:
                # either a Link or a (Section, [children]) tuple
                if isinstance(node, (tuple, list)):
                    for sub in node:
                        if isinstance(sub, (tuple, list)):
                            walk(sub)
                        else:
                            add(sub)
                else:
                    add(node)

        def add(link):
            href = getattr(link, "href", None)
            title = getattr(link, "title", None)
            if href and title:
                key = href.split("#", 1)[0]
                mapping.setdefault(key, title.strip())

        try:
            walk(book.toc or [])
        except Exception:
            pass
        return mapping

    def _chapter_title(
        self,
        href: str,
        chapter_blocks: List[Tuple[str, str, Dict[str, Any]]],
        href_to_title: Dict[str, str],
    ) -> Optional[str]:
        key = href.split("#", 1)[0]
        # also try the basename; toc hrefs may carry a relative path prefix
        title = href_to_title.get(key) or href_to_title.get(key.split("/")[-1])
        if title:
            return title
        # fallback: use the chapter's first heading block
        for content, block_type, _ in chapter_blocks:
            if block_type == "heading" and content:
                return content
        return None

    # ── HTML -> blocks ────────────────────────────────────────────────────────────

    def _extract_chapter_blocks(
        self, raw: bytes
    ) -> List[Tuple[str, str, Dict[str, Any]]]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw, "html.parser")

        for tag in soup(list(_DROP_TAGS)):
            tag.decompose()

        body = soup.body or soup
        blocks: List[Tuple[str, str, Dict[str, Any]]] = []

        for el in self._outermost_blocks(body):
            name = el.name.lower()

            if name == "table":
                md = self._table_to_markdown(el)
                if md:
                    blocks.append((md, "paragraph", {"is_table": True}))
                continue

            text = self._normalize_text(el.get_text(separator=" "))
            if not text:
                continue

            if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                blocks.append((text, "heading", {"level": int(name[1])}))
            elif name == "li":
                blocks.append((text, "list", {}))
            elif name == "pre":
                blocks.append((text, "paragraph", {"is_code": True}))
            else:  # p / blockquote
                blocks.append((text, "paragraph", {}))

        return blocks

    @staticmethod
    def _normalize_text(text: str) -> str:
        if not text:
            return ""
        text = text.replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\s*\n\s*", " ", text)
        return text.strip()

    @staticmethod
    def _outermost_blocks(body):
        """Block elements in document order, skipping those inside another block.

        A walk from the top that does not descend into container blocks; checking
        every element's ancestors instead took time proportional to the square of
        the nesting depth.
        """
        stack = [child for child in reversed(list(body.children)) if getattr(child, "name", None)]
        while stack:
            el = stack.pop()
            name = el.name.lower()
            if name in _BLOCK_TAGS:
                yield el
            if name not in _CONTAINER_TAGS:
                stack.extend(child for child in reversed(list(el.children)) if getattr(child, "name", None))

    @staticmethod
    def _own_rows(table_el) -> list:
        """Rows of this table only; rows of nested tables stay inside their cell's text.

        find_all("tr") also returned every nested row while each enclosing cell's
        text already held it, so text was copied once per nesting level.
        """
        rows = []
        for child in table_el.children:
            name = getattr(child, "name", None)
            if name == "tr":
                rows.append(child)
            elif name in ("thead", "tbody", "tfoot"):
                rows.extend(c for c in child.children if getattr(c, "name", None) == "tr")
        return rows

    def _table_to_markdown(self, table_el) -> str:
        rows = self._own_rows(table_el)
        if not rows:
            return ""

        md_rows: List[str] = []
        for i, row in enumerate(rows):
            cells = row.find_all(["td", "th"], recursive=False)
            clean = [self._normalize_text(c.get_text(separator=" ")) for c in cells]
            if not clean:
                continue
            md_rows.append("| " + " | ".join(clean) + " |")
            if i == 0:
                md_rows.append("| " + " | ".join(["---"] * len(clean)) + " |")

        return "\n".join(md_rows)

    # ── Assembly ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_blocks(
        collected: List[Tuple[str, str, Dict[str, Any]]]
    ) -> Tuple[List[Block], str]:
        blocks: List[Block] = []
        contents: List[str] = []
        position_offset = 0

        for content, block_type, extra in collected:
            start_pos = position_offset
            end_pos = start_pos + len(content)
            position_offset = end_pos + 1  # keep offsets consistent with the full text built by "\n".join

            blocks.append(
                Block(
                    id=f"b_{len(blocks)}",
                    type=block_type,
                    content=content,
                    position={"start": start_pos, "end": end_pos},
                    page=0,
                    extra=extra or None,
                )
            )
            contents.append(content)

        return blocks, "\n".join(contents)


def parse_file(file_path: str) -> ParseResult:
    """EpubParser()._parse_sync as a module-level function, so it can run in a child process."""
    return EpubParser()._parse_sync(file_path)


def check_manifest_size(file_path: str) -> None:
    """Raise RuntimeError when the manifest makes EbookLib load too much.

    EbookLib reads the file of every manifest entry into memory, one copy per
    entry, so one large chapter listed under many ids is loaded many times even
    though the archive's declared size counts it once.
    """
    try:
        with zipfile.ZipFile(file_path) as archive:
            sizes = {info.filename: info.file_size for info in archive.infolist()}
            container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
            rootfile = next((el.get("full-path") for el in container.iter() if el.tag.endswith("rootfile")), None)
            if not rootfile:
                return
            opf = ElementTree.fromstring(archive.read(rootfile))
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError, OSError):
        return  # read_epub reports the damaged file
    base = posixpath.dirname(rootfile)
    total = 0
    count = 0
    for el in opf.iter():
        if not el.tag.endswith("item") or not el.get("href"):
            continue
        href = posixpath.normpath(posixpath.join(base, unquote(el.get("href").split("#", 1)[0])))
        total += sizes.get(href, 0)
        count += 1
    if total > ARCHIVE_MAX_UNCOMPRESSED_BYTES:
        raise UserFacingError(
            ui_msg(
                "archive_too_large",
                size=max(1, total // (1024 * 1024)),
                limit=ARCHIVE_MAX_UNCOMPRESSED_BYTES // (1024 * 1024),
                count=count,
            )
        )
