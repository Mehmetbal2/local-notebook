import asyncio
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.text_decoding import read_text_file

from .base import BaseParser, Block, ParseResult
from .text_split import split_long_text

_TANZIL_AYAH_RE = re.compile(r"^(\d{1,3})\|(\d{1,3})\|(.+)$")

_SURAH_NAMES = [
    "الفاتحة", "البقرة", "آل عمران", "النساء", "المائدة", "الأنعام", "الأعراف",
    "الأنفال", "التوبة", "يونس", "هود", "يوسف", "الرعد", "إبراهيم", "الحجر",
    "النحل", "الإسراء", "الكهف", "مريم", "طه", "الأنبياء", "الحج", "المؤمنون",
    "النور", "الفرقان", "الشعراء", "النمل", "القصص", "العنكبوت", "الروم",
    "لقمان", "السجدة", "الأحزاب", "سبأ", "فاطر", "يس", "الصافات", "ص",
    "الزمر", "غافر", "فصلت", "الشورى", "الزخرف", "الدخان", "الجاثية",
    "الأحقاف", "محمد", "الفتح", "الحجرات", "ق", "الذاريات", "الطور", "النجم",
    "القمر", "الرحمن", "الواقعة", "الحديد", "المجادلة", "الحشر", "الممتحنة",
    "الصف", "الجمعة", "المنافقون", "التغابن", "الطلاق", "التحريم", "الملك",
    "القلم", "الحاقة", "المعارج", "نوح", "الجن", "المزمل", "المدثر", "القيامة",
    "الإنسان", "المرسلات", "النبأ", "النازعات", "عبس", "التكوير", "الانفطار",
    "المطففين", "الانشقاق", "البروج", "الطارق", "الأعلى", "الغاشية", "الفجر",
    "البلد", "الشمس", "الليل", "الضحى", "الشرح", "التين", "العلق", "القدر",
    "البينة", "الزلزلة", "العاديات", "القارعة", "التكاثر", "العصر", "الهمزة",
    "الفيل", "قريش", "الماعون", "الكوثر", "الكافرون", "النصر", "المسد",
    "الإخلاص", "الفلق", "الناس",
]

_HEADING_PATTERNS = [
    (r'^#{1,6}\s+', 'heading'),
    (r'^\[[^\]]{2,160}\]$', 'heading'),
    (r'^(?:الباب|الفصل|المبحث|المطلب|سورة|الجزء|القسم)\s+\S+', 'heading'),
    (r'^第[一二三四五六七八九十百千万零\d]+[章卷部篇]', 'heading'),
    (r'^第[一二三四五六七八九十百千万零\d]+[节]', 'heading'),
    (r'^[一二三四五六七八九十]+[、．.]', 'heading'),
    (r'^[（(][一二三四五六七八九十]+[）)]', 'heading'),
    (r'^\d+[、．.]\s*\S', 'heading'),
    (r'^[（(]\d+[）)]', 'heading'),
]

_LIST_PATTERNS = [
    (r'^[\-\*\+]\s', 'list'),
    (r'^\d+[\.\)]\s', 'list'),
]

_SPLIT_PUNCTUATION = "。！？!?؛;؟۔.:"


def _clean_text(text: str) -> str:
    if not text:
        return ""
    cleaned = text.replace("\xa0", " ").replace("\ufeff", "")
    return re.sub(r"[ \t]+", " ", cleaned).strip()


def _split_long_paragraph(text: str, max_chars: int = 600) -> List[str]:
    """Split prose without losing the suffix when no punctuation exists."""
    text = _clean_text(text)
    if len(text) <= max_chars:
        return [text] if text else []
    return split_long_text(text, max_chars, _SPLIT_PUNCTUATION)


def _looks_like_tanzil(lines: List[str], file_path: Optional[str]) -> bool:
    """Conservative detection of Tanzil ``surah|ayah|text`` exports.

    A handful of pipe-delimited rows must never turn an arbitrary TXT/log file
    into a Quran and silently drop its other lines.
    """
    non_empty = [
        line.strip() for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]
    if len(non_empty) < 20:
        return False

    matches = [
        match for line in non_empty
        if (match := _TANZIL_AYAH_RE.match(line))
    ]
    if len(matches) < 20 or len(matches) / len(non_empty) < 0.8:
        return False

    pairs: List[Tuple[int, int]] = []
    for match in matches:
        surah = int(match.group(1))
        ayah = int(match.group(2))
        if not (1 <= surah <= 114 and 1 <= ayah <= 300):
            return False
        pairs.append((surah, ayah))

    if pairs[0] != (1, 1):
        return False
    if any(pairs[index] > pairs[index + 1] for index in range(len(pairs) - 1)):
        return False

    filename = (Path(file_path).name.lower() if file_path else "")
    filename_hint = any(
        hint in filename for hint in ("quran", "tanzil", "uthmani", "قرآن", "قران")
    )
    if filename_hint:
        return True

    # For generically named files, require both strong structure and actual
    # Arabic script so pipe-delimited logs/CSV exports are never hijacked.
    arabic_chars = 0
    total_chars = 0
    for match in matches:
        text = match.group(3)
        total_chars += len(text)
        arabic_chars += sum(
            1 for char in text if "\u0600" <= char <= "\u06ff"
        )
    return len(matches) >= 30 and total_chars > 0 and arabic_chars / total_chars >= 0.5


class TxtParser(BaseParser):

    HEADING_PATTERNS = _HEADING_PATTERNS
    LIST_PATTERNS = _LIST_PATTERNS

    def get_supported_extensions(self) -> List[str]:
        return [".txt", ".md", ".markdown"]

    async def parse(self, file_path: str) -> ParseResult:
        from .isolation import run_isolated

        # In a child process with a memory and time limit (see isolation.py); this
        # also keeps block building off the event loop.
        return await asyncio.to_thread(run_isolated, parse_file, file_path)

    def _parse_sync(self, file_path: str) -> ParseResult:
        text = read_text_file(file_path)
        blocks, normalized_text, page_count = self._create_blocks_with_text(
            text, file_path=file_path
        )

        return ParseResult(
            text=normalized_text,
            blocks=blocks,
            page_count=page_count,
            images=[]
        )

    def _create_blocks(self, text: str) -> List[Block]:
        blocks, _, _ = self._create_blocks_with_text(text)
        return blocks

    def _create_blocks_with_text(
        self, text: str, file_path: Optional[str] = None
    ) -> Tuple[List[Block], str, int]:
        if not text:
            return [], "", 0

        lines = text.splitlines()
        if _looks_like_tanzil(lines, file_path):
            return self._create_tanzil_blocks(lines)

        raw_paragraphs = re.split(r'\n\s*\n', text)
        expanded_paragraphs: List[str] = []
        for para in raw_paragraphs:
            para = para.strip()
            if not para:
                continue
            if para.startswith(("```", "|", "<table")):
                expanded_paragraphs.append(para)
                continue
            if len(para) > 800:
                if "\n" in para:
                    expanded_paragraphs.extend(
                        self._split_multiline_paragraph(para, max_chars=600)
                    )
                else:
                    expanded_paragraphs.extend(
                        _split_long_paragraph(para, max_chars=600)
                    )
            else:
                expanded_paragraphs.append(para)

        blocks: List[Block] = []
        contents: List[str] = []
        position_offset = 0

        for para_text in expanded_paragraphs:
            para_text = para_text.strip()
            if not para_text:
                continue

            block_type = self._detect_block_type(para_text)
            clean_content = self._clean_content(para_text, block_type)
            if not clean_content:
                continue

            start_pos = position_offset
            end_pos = start_pos + len(clean_content)
            position_offset = end_pos + 1

            extra: Dict[str, Any] = {}
            if block_type == "heading":
                level = self._get_heading_level(para_text)
                if level:
                    extra["level"] = level

            blocks.append(Block(
                id=f"b_{len(blocks)}",
                type=block_type,
                content=clean_content,
                position={"start": start_pos, "end": end_pos},
                page=0,
                extra=extra if extra else None
            ))
            contents.append(clean_content)

        return blocks, "\n".join(contents), 0

    def _create_tanzil_blocks(
        self, lines: List[str]
    ) -> Tuple[List[Block], str, int]:
        blocks: List[Block] = []
        contents: List[str] = []
        position_offset = 0
        current_surah = 0
        current_group: List[str] = []
        current_len = 0
        group_start_ayah = 0
        group_end_ayah = 0

        def flush_group() -> None:
            nonlocal position_offset, current_group, current_len
            nonlocal group_start_ayah, group_end_ayah
            if not current_group:
                return
            content = "\n".join(current_group)
            start_pos = position_offset
            end_pos = start_pos + len(content)
            position_offset = end_pos + 1
            blocks.append(Block(
                id=f"b_{len(blocks)}",
                type="paragraph",
                content=content,
                position={"start": start_pos, "end": end_pos},
                page=0,
                extra={
                    "surah": current_surah,
                    "ayah_start": group_start_ayah,
                    "ayah_end": group_end_ayah,
                },
            ))
            contents.append(content)
            current_group = []
            current_len = 0
            group_start_ayah = 0
            group_end_ayah = 0

        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            match = _TANZIL_AYAH_RE.match(line)
            if not match:
                continue

            surah_num = int(match.group(1))
            ayah_num = int(match.group(2))
            ayah_text = match.group(3).strip()

            if surah_num != current_surah:
                flush_group()
                current_surah = surah_num
                surah_name = (
                    _SURAH_NAMES[surah_num - 1]
                    if 1 <= surah_num <= len(_SURAH_NAMES)
                    else ""
                )
                heading_content = (
                    f"سورة {surah_name} ({surah_num})"
                    if surah_name else f"سورة {surah_num}"
                )
                start_pos = position_offset
                end_pos = start_pos + len(heading_content)
                position_offset = end_pos + 1
                blocks.append(Block(
                    id=f"b_{len(blocks)}",
                    type="heading",
                    content=heading_content,
                    position={"start": start_pos, "end": end_pos},
                    page=0,
                    extra={
                        "level": 2,
                        "surah": surah_num,
                        "surah_name": surah_name,
                    },
                ))
                contents.append(heading_content)

            formatted_ayah = f"({surah_num}:{ayah_num}) {ayah_text}"
            if current_group and current_len + 1 + len(formatted_ayah) > 360:
                flush_group()
            if not current_group:
                group_start_ayah = ayah_num
            group_end_ayah = ayah_num
            current_group.append(formatted_ayah)
            current_len += len(formatted_ayah) + 1

        flush_group()
        return blocks, "\n".join(contents), 0

    @staticmethod
    def _split_multiline_paragraph(para: str, max_chars: int = 600) -> List[str]:
        chunks: List[str] = []
        current: List[str] = []
        current_len = 0

        def flush() -> None:
            nonlocal current, current_len
            if not current:
                return
            text = "\n".join(current).strip()
            if text:
                chunks.extend(_split_long_paragraph(text, max_chars=max_chars))
            current = []
            current_len = 0

        for raw_line in para.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if re.match(r"^(?:#{1,6}\s+|\[[^\]]{2,160}\]$)", line):
                flush()
                chunks.append(line)
                continue
            if current and current_len + 1 + len(line) > max_chars:
                flush()
            current.append(line)
            current_len += len(line) + 1
        flush()
        return chunks

    def _detect_block_type(self, text: str) -> str:
        text_stripped = text.strip()

        if not text_stripped:
            return "paragraph"

        if (text_stripped.startswith('|') and '|' in text_stripped) or \
           (text_stripped.startswith('<table')):
            return "table"

        if text_stripped.startswith('```') or text_stripped.startswith('>'):
            return "code"

        if text_stripped.startswith('$$'):
            return "equation"

        if "\n" not in text_stripped and len(text_stripped) <= 160:
            for pattern, block_type in self.HEADING_PATTERNS:
                if re.match(pattern, text_stripped):
                    return block_type
        elif re.match(r'^#{1,6}\s+', text_stripped):
            return "heading"

        for pattern, block_type in self.LIST_PATTERNS:
            if re.match(pattern, text_stripped):
                return block_type

        return "paragraph"

    def _clean_content(self, text: str, block_type: str) -> str:
        if block_type == "heading":
            text = re.sub(r'^#+\s*', '', text)
            if text.startswith("[") and text.endswith("]"):
                text = text[1:-1].strip() or text

        return text.strip()

    def _get_heading_level(self, text: str) -> int:
        text = text.strip()

        match = re.match(r'^(#{1,6})\s', text)
        if match:
            return len(match.group(1))

        return 2


def parse_file(file_path: str) -> ParseResult:
    """TxtParser()._parse_sync as a module-level function, so it can run in a child process."""
    return TxtParser()._parse_sync(file_path)
