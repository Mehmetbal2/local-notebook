"""Convert the markdown produced by the while-loop agent into frontend FeatureBlock lists.

Citation splitting reuses CitationParser so citation numbers stay continuous across a workflow:
the caller passes a shared citation_map and start_display_num; this function returns the updated
next_display_num and writes the assigned display_num back into citation_map (same behaviour as
chat_agent's _sync_display_nums).
"""

import re
from typing import Any, Dict, List, Tuple

from agent.citation_parser import CitationParser

# The patterns avoid two adjacent repeats that can match the same characters
# (e.g. `\s+(.*)`), so a long run of spaces cannot make them backtrack; the
# captured text is stripped afterwards.
_HEADING_RE = re.compile(r"^(#{1,6})\s(.*)$")
_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s(.*)$")
_QUOTE_RE = re.compile(r"^\s*>\s?(.*)$")


def _is_table_row(line: str) -> bool:
    """`| … |` with optional surrounding whitespace."""
    s = line.strip()
    return len(s) >= 2 and s[0] == "|" and s[-1] == "|"


def _is_table_separator(line: str) -> bool:
    """A markdown table separator row such as `|---|:--:|` or `--- | ---`."""
    s = line.lstrip()
    if s.startswith("|"):
        s = s[1:].lstrip()
    if s.startswith(":"):
        s = s[1:]
    return s.startswith("--")


def _text_to_parts(parser: CitationParser, text: str) -> List[Dict[str, Any]]:
    """Split a piece of text into content_parts by parsing its citations."""
    parts: List[Dict[str, Any]] = []
    events = list(parser.feed(text)) + list(parser.flush())
    for ev in events:
        if ev["type"] == "text":
            content = ev.get("content", "")
            if content:
                parts.append({"type": "text", "content": content})
        elif ev["type"] == "citation_ref":
            part = {k: v for k, v in ev.items()}
            parts.append(part)
    if not parts:
        parts.append({"type": "text", "content": text})
    return parts


def markdown_to_blocks(
    markdown: str,
    citation_map: Dict[str, Any],
    start_display_num: int = 1,
) -> Tuple[List[Dict[str, Any]], int]:
    """markdown -> (blocks, next_display_num)。"""
    parser = CitationParser(citation_map=citation_map, start_display_num=start_display_num)
    blocks: List[Dict[str, Any]] = []

    lines = (markdown or "").replace("\r\n", "\n").split("\n")
    i = 0
    n = len(lines)
    para_buf: List[str] = []

    def flush_para() -> None:
        if not para_buf:
            return
        text = " ".join(s.strip() for s in para_buf).strip()
        para_buf.clear()
        if text:
            blocks.append({
                "block_type": "paragraph",
                "content_parts": _text_to_parts(parser, text),
            })

    in_code = False
    code_buf: List[str] = []

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # code block: collected verbatim as one paragraph
        if stripped.startswith("```"):
            if in_code:
                in_code = False
                code_text = "\n".join(code_buf)
                code_buf.clear()
                if code_text.strip():
                    blocks.append({
                        "block_type": "paragraph",
                        "content_parts": [{"type": "text", "content": code_text}],
                    })
            else:
                flush_para()
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue

        # blank line: paragraph break
        if not stripped:
            flush_para()
            i += 1
            continue

        # heading
        m = _HEADING_RE.match(line)
        if m:
            flush_para()
            level = len(m.group(1))
            text = m.group(2).strip()
            blocks.append({
                "block_type": "heading",
                "level": level,
                "content_parts": _text_to_parts(parser, text),
            })
            i += 1
            continue

        # table: consecutive | … | rows (including the separator row); raw markdown is stored in content
        if _is_table_row(line) and i + 1 < n and _is_table_separator(lines[i + 1]):
            flush_para()
            table_lines = [line]
            i += 1
            while i < n and _is_table_row(lines[i]):
                table_lines.append(lines[i])
                i += 1
            raw_table = "\n".join(table_lines)
            blocks.append({
                "block_type": "paragraph",
                "content": raw_table,
                "content_parts": _text_to_parts(parser, raw_table),
                "extra": {"is_table": True},
            })
            continue

        # blockquote
        m = _QUOTE_RE.match(line)
        if m:
            flush_para()
            text = m.group(1).strip()
            blocks.append({
                "block_type": "quote",
                "content_parts": _text_to_parts(parser, text),
            })
            i += 1
            continue

        # list item: one list block per item (the frontend's processFeatureBlocks groups them)
        m = _LIST_RE.match(line)
        if m:
            flush_para()
            text = m.group(1).strip()
            list_block: Dict[str, Any] = {
                "block_type": "list",
                "content_parts": _text_to_parts(parser, text),
            }
            # Nested bullets: two spaces (or one tab) per level. Flat lists stay unchanged.
            leading = line[: len(line) - len(line.lstrip())].replace("\t", "  ")
            indent = min(len(leading) // 2, 6)
            if indent > 0:
                list_block["extra"] = {"indent": indent}
            blocks.append(list_block)
            i += 1
            continue

        # ordinary paragraph line
        para_buf.append(line)
        i += 1

    flush_para()
    if in_code and code_buf:
        code_text = "\n".join(code_buf)
        if code_text.strip():
            blocks.append({
                "block_type": "paragraph",
                "content_parts": [{"type": "text", "content": code_text}],
            })

    # write the assigned display_num back into citation_map so later sections reuse the same numbers
    for citation_id, display_num in parser.id_to_display.items():
        entry = citation_map.get(citation_id)
        if entry is not None and entry.get("display_num") is None:
            entry["display_num"] = display_num

    return blocks, parser.display_num
