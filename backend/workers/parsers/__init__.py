from .base import BaseParser
from .pdf_parser import PDFParser
from .txt_parser import TxtParser
from .html_parser import HtmlParser
from .docx_parser import DocxParser
from .epub_parser import EpubParser
from .image_parser import ImageParser
from .audio_parser import AudioParser
from utils.i18n import msg as ui_msg


PARSERS = {
    ".pdf": PDFParser,
    ".txt": TxtParser,
    ".md": TxtParser,
    ".markdown": TxtParser,
    ".htm": HtmlParser,
    ".html": HtmlParser,
    ".docx": DocxParser,
    ".doc": DocxParser,
    ".epub": EpubParser,
    ".jpg": ImageParser,
    ".jpeg": ImageParser,
    ".png": ImageParser,
    ".wav": AudioParser,
    ".mp3": AudioParser,
    ".m4a": AudioParser,
}


def get_parser_for_file(file_path: str) -> "BaseParser":
    from pathlib import Path

    ext = Path(file_path).suffix.lower()
    parser_class = PARSERS.get(ext)

    if not parser_class:
        raise ValueError(ui_msg("unsupported_file_type", ext=ext))

    return parser_class()


__all__ = [
    "PDFParser",
    "TxtParser",
    "HtmlParser",
    "DocxParser",
    "EpubParser",
    "AudioParser",
    "get_parser_for_file",
    "PARSERS",
]
