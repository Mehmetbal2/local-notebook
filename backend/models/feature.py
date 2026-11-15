import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from utils.time import utc_isoformat


class Feature(Base):
    """One section of a report (sub-report).

    Belongs to a Workflow (step); the while-loop agent generates its content as blocks.
    Quick tools and notes have no workflow_id; report sections always set it.
    """

    __tablename__ = "features"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=True, index=True
    )

    feature_type: Mapped[str] = mapped_column(String(50), nullable=False, default="text_section")
    step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # section name (also shown as the title)
    step_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # pending / processing / completed / failed / cancelled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    blocks_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    citations_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generation_report: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    custom_config_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    workflow: Mapped[Optional["Workflow"]] = relationship("Workflow", back_populates="features")

    # --- JSON helpers ---

    def get_blocks(self) -> List[Dict[str, Any]]:
        if not self.blocks_json:
            return []
        try:
            data = json.loads(self.blocks_json)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    def set_blocks(self, blocks: List[Dict[str, Any]]) -> None:
        self.blocks_json = json.dumps(blocks, ensure_ascii=False) if blocks else None

    def get_citations(self) -> Dict[str, Any]:
        if not self.citations_json:
            return {}
        try:
            data = json.loads(self.citations_json)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def set_citations(self, data: Dict[str, Any]) -> None:
        self.citations_json = json.dumps(data, ensure_ascii=False) if data else None

    def get_custom_config(self) -> Dict[str, Any]:
        if not self.custom_config_json:
            return {}
        try:
            data = json.loads(self.custom_config_json)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def set_custom_config(self, data: Dict[str, Any]) -> None:
        self.custom_config_json = json.dumps(data, ensure_ascii=False) if data else None

    # --- view helpers ---

    def get_step_id(self) -> Optional[str]:
        step_id = self.get_custom_config().get("step_id")
        return str(step_id) if step_id else None

    def get_depends_on(self) -> List[str]:
        depends_on = self.get_custom_config().get("depends_on") or []
        if isinstance(depends_on, str):
            depends_on = [depends_on]
        if not isinstance(depends_on, list):
            return []
        return [str(item) for item in depends_on if item]

    def to_content_dict(self) -> Dict[str, Any]:
        """Shape of the frontend WorkflowContentFeature / Feature."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "feature_type": self.feature_type,
            "step_index": self.step_index,
            "step_id": self.get_step_id(),
            "depends_on": self.get_depends_on(),
            "step_name": self.step_name,
            "title": self.title or self.step_name,
            "status": self.status,
            "error_message": self.error_message,
            "blocks": self.get_blocks(),
            "citations": self.get_citations(),
            "generation_report": self.generation_report or "",
            "created_at": utc_isoformat(self.created_at),
            "started_at": utc_isoformat(self.started_at),
            "finished_at": utc_isoformat(self.finished_at),
            "note_source": self.get_custom_config().get("note_source"),
            "note_markdown": self.get_custom_config().get("markdown"),
            "progress": self.get_custom_config().get("progress") if self.status in ("pending", "processing") else None,
            "research_sources": self.get_custom_config().get("sources") if self.feature_type == "deep_research" else None,
            "research_scope": self.get_custom_config().get("scope") if self.feature_type == "deep_research" else None,
        }
