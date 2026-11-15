from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from paths import resolve_stored_path, to_portable_path


class File(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processing_current: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    processing_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    processing_message: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    job_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Address a web-imported source was downloaded from
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    project: Mapped["Project"] = relationship("Project", back_populates="files")


@event.listens_for(File, "before_insert")
@event.listens_for(File, "before_update")
def _normalize_file_path_for_storage(mapper, connection, target: File) -> None:
    if target.file_path:
        target.file_path = to_portable_path(target.file_path)


@event.listens_for(File, "load")
@event.listens_for(File, "refresh")
def _resolve_file_path_on_load(target: File, *args) -> None:
    if target.file_path:
        target.__dict__["file_path"] = resolve_stored_path(
            target.file_path,
            project_id=getattr(target, "project_id", None),
            file_name=getattr(target, "file_name", None),
        )
