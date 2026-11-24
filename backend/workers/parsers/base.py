import os
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class Block:
    id: str
    type: str
    content: str
    position: Dict[str, int]
    page: int = 0
    extra: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "position": self.position,
            "page": self.page,
            "extra": self.extra
        }


@dataclass
class ParseResult:
    text: str
    blocks: List[Block]
    page_count: int = 0
    images: List[Dict[str, Any]] = field(default_factory=list)


class BaseParser(ABC):

    @abstractmethod
    async def parse(self, file_path: str) -> ParseResult:
        pass

    @abstractmethod
    def get_supported_extensions(self) -> List[str]:
        pass


# EPUB and DOCX files are zip archives. A small upload can expand to gigabytes
# ("zip bomb"), and the parsing libraries load members into memory, so the
# declared uncompressed size is checked before a parser opens the file.
ARCHIVE_MAX_UNCOMPRESSED_BYTES = max(1, int(os.getenv("ARCHIVE_MAX_UNCOMPRESSED_MB", "512"))) * 1024 * 1024
ARCHIVE_MAX_MEMBERS = 20000


def check_zip_archive(file_path: str) -> None:
    """Raise RuntimeError when a zip-based document would expand beyond the limits.

    zipfile never yields more than a member's declared size, so the sum of the
    declared sizes is a true upper bound on what the parser can unpack.
    """
    from utils.i18n import msg as ui_msg

    if not zipfile.is_zipfile(file_path):
        return
    with zipfile.ZipFile(file_path) as archive:
        members = archive.infolist()
        total = sum(member.file_size for member in members)
    limit_mb = ARCHIVE_MAX_UNCOMPRESSED_BYTES // (1024 * 1024)
    if len(members) > ARCHIVE_MAX_MEMBERS or total > ARCHIVE_MAX_UNCOMPRESSED_BYTES:
        raise RuntimeError(
            ui_msg("archive_too_large", size=max(1, total // (1024 * 1024)), limit=limit_mb, count=len(members))
        )
