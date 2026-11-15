"""Make right-to-left text (Arabic, Persian, Hebrew…) render correctly in exported DOCX files.

Pandoc and python-docx write Arabic as ordinary runs. Word then draws those characters
with the Latin font (Calibri), which has no Arabic glyphs, so they show up as empty
boxes. Here every right-to-left stretch becomes its own run marked as right-to-left,
complex-script text with a font that has Arabic glyphs; paragraphs that are mostly
right-to-left also get right-to-left paragraph direction.
"""

from __future__ import annotations

import copy
import re
import zipfile
from io import BytesIO

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

RTL_FONT = "Times New Roman"  # ships with Word on Windows and macOS and covers Arabic and Hebrew

_RTL_CHARS = "֐-ࣿיִ-﷿ﹰ-﻿"
_RTL_CHAR_RE = re.compile(f"[{_RTL_CHARS}]")
# A right-to-left stretch: starts and ends with an RTL letter and may contain spaces,
# punctuation and diacritics in between, but no Latin letters or digits.
_RTL_SPAN_RE = re.compile(
    f"[{_RTL_CHARS}](?:[{_RTL_CHARS}\\s.,:;!?()\\[\\]«»\"'“”‘’\\-–—/…]*[{_RTL_CHARS}])?"
    # Sentence punctuation right after the Arabic belongs to it, so it shows at the Arabic end.
    "(?:[.,:;!?؟…]+)?"
)
_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)
_PARTS = ("word/document.xml", "word/footnotes.xml", "word/endnotes.xml")


def _ensure_rpr(run):
    rpr = run.find(f"{W}rPr")
    if rpr is None:
        rpr = etree.SubElement(run, f"{W}rPr")
        run.remove(rpr)
        run.insert(0, rpr)
    return rpr


# Child order inside <w:rPr> required by the OOXML schema; Word may reject files that break it.
_RPR_ORDER = [
    "rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike",
    "outline", "shadow", "emboss", "imprint", "noProof", "snapToGrid", "vanish", "webHidden",
    "color", "spacing", "w", "kern", "position", "sz", "szCs", "highlight", "u", "effect",
    "bdr", "shd", "fitText", "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout",
    "specVanish", "oMath",
]


_PPR_ORDER = [
    "pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl", "numPr",
    "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens", "kinsoku", "wordWrap",
    "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd",
    "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc",
    "textDirection", "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle",
    "rPr", "sectPr", "pPrChange",
]


def _insert_ordered(parent, element, order: list[str]) -> None:
    rank = order.index(etree.QName(element).localname)
    for index, child in enumerate(parent):
        local = etree.QName(child).localname
        if local in order and order.index(local) > rank:
            parent.insert(index, element)
            return
    parent.append(element)


def _rpr_child(rpr, name: str):
    """Return rPr's <w:name>, creating it at its schema position when missing."""
    existing = rpr.find(f"{W}{name}")
    if existing is not None:
        return existing
    element = etree.Element(f"{W}{name}")
    rank = _RPR_ORDER.index(name)
    for index, child in enumerate(rpr):
        local = etree.QName(child).localname
        if local in _RPR_ORDER and _RPR_ORDER.index(local) > rank:
            rpr.insert(index, element)
            return element
    rpr.append(element)
    return element


def _mark_rtl(run) -> None:
    rpr = _ensure_rpr(run)
    fonts = _rpr_child(rpr, "rFonts")
    fonts.set(f"{W}cs", RTL_FONT)
    fonts.attrib.pop(f"{W}cstheme", None)
    # Bold and italic of a right-to-left run are read from bCs/iCs: mirror b/i.
    for latin, complex_script in (("b", "bCs"), ("i", "iCs")):
        source = rpr.find(f"{W}{latin}")
        if source is not None and rpr.find(f"{W}{complex_script}") is None:
            target = _rpr_child(rpr, complex_script)
            for key, value in source.attrib.items():
                target.set(key, value)
    _rpr_child(rpr, "rtl")
    _rpr_child(rpr, "lang").set(f"{W}bidi", "ar-SA")


def _split_run(run) -> None:
    """Split one run into runs that are entirely RTL or entirely not, marking the RTL ones."""
    texts = run.findall(f"{W}t")
    if len(texts) != 1 or len(run) > (2 if run.find(f"{W}rPr") is not None else 1):
        # Runs with tabs, breaks or several texts: mark them whole if they are mostly RTL.
        joined = "".join(t.text or "" for t in texts)
        if _RTL_CHAR_RE.search(joined) and _is_mostly_rtl(joined):
            _mark_rtl(run)
        return
    text = texts[0].text or ""
    if not _RTL_CHAR_RE.search(text):
        return
    pieces: list[tuple[str, bool]] = []
    position = 0
    for match in _RTL_SPAN_RE.finditer(text):
        if match.start() > position:
            pieces.append((text[position:match.start()], False))
        pieces.append((match.group(0), True))
        position = match.end()
    if position < len(text):
        pieces.append((text[position:], False))
    if len(pieces) == 1:
        _mark_rtl(run)
        return
    parent = run.getparent()
    index = parent.index(run)
    for offset, (piece, is_rtl) in enumerate(pieces):
        new_run = copy.deepcopy(run)
        new_text = new_run.find(f"{W}t")
        new_text.text = piece
        new_text.set(XML_SPACE, "preserve")
        if is_rtl:
            _mark_rtl(new_run)
        parent.insert(index + offset, new_run)
    parent.remove(run)


def _starts_rtl(text: str) -> bool:
    """Paragraph direction by its first letter (Unicode's first-strong rule, like dir="auto").

    A reference line or a Turkish sentence that quotes Arabic stays left-to-right; a paragraph
    that is itself Arabic becomes right-to-left. Deciding by the share of Arabic letters
    instead flipped reference lines with long Arabic quotes.
    """
    for ch in text:
        if _LETTER_RE.match(ch):
            return bool(_RTL_CHAR_RE.match(ch))
    return False


def _is_mostly_rtl(text: str) -> bool:
    letters = _LETTER_RE.findall(text)
    if not letters:
        return False
    rtl = sum(1 for ch in letters if _RTL_CHAR_RE.match(ch))
    return rtl / len(letters) >= 0.6


def _fix_part(xml: bytes) -> bytes:
    root = etree.fromstring(xml)
    changed = False
    for paragraph in root.iter(f"{W}p"):
        paragraph_text = "".join(t.text or "" for t in paragraph.iter(f"{W}t"))
        if not _RTL_CHAR_RE.search(paragraph_text):
            continue
        changed = True
        for run in list(paragraph.iter(f"{W}r")):
            _split_run(run)
        if _starts_rtl(paragraph_text):
            ppr = paragraph.find(f"{W}pPr")
            if ppr is None:
                ppr = etree.Element(f"{W}pPr")
                paragraph.insert(0, ppr)
            if ppr.find(f"{W}bidi") is None:
                _insert_ordered(ppr, etree.Element(f"{W}bidi"), _PPR_ORDER)
    if not changed:
        return xml
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def fix_rtl_text(docx_bytes: bytes) -> bytes:
    """Return the DOCX with right-to-left text marked so Word renders it."""
    source = zipfile.ZipFile(BytesIO(docx_bytes))
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename in _PARTS:
                try:
                    data = _fix_part(data)
                except etree.XMLSyntaxError:
                    pass
            target.writestr(item, data)
    return output.getvalue()
