"""AI research records.

Everything Claude is asked and everything it answers is persisted with the
prompt version, model, token usage and estimated cost. AI output is research
material: it is stored, labelled and shown as such, and it is never an input to
order placement.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AIPromptVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ai_prompt_versions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_ai_prompt_name_version"),)

    name: Mapped[str] = mapped_column(String(100), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    task: Mapped[str] = mapped_column(String(60))
    system_prompt: Mapped[str] = mapped_column(Text)
    user_template: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)


class AIAnalysis(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ai_analysis"
    __table_args__ = (Index("ix_ai_analysis_task_time", "task", "created_at"),)

    task: Mapped[str] = mapped_column(String(60), index=True)
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_prompt_versions.id")
    )
    model: Mapped[str] = mapped_column(String(80))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    # What the model was shown (already-redacted, bounded context).
    input_context: Mapped[dict] = mapped_column(JSONB, default=dict)
    output_text: Mapped[str | None] = mapped_column(Text)
    output_structured: Mapped[dict] = mapped_column(JSONB, default=dict)

    related_signal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trading_signals.id", ondelete="SET NULL")
    )
    related_strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL")
    )
    related_backtest_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("backtest_jobs.id", ondelete="SET NULL")
    )

    # Always true in this build - rendered as a banner in the UI.
    is_research_only: Mapped[bool] = mapped_column(Boolean, default=True)
    validated_by_rules: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_notes: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)


class AIUsageLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ai_usage_logs"
    __table_args__ = (Index("ix_ai_usage_time", "called_at"),)

    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_analysis.id", ondelete="CASCADE")
    )
    model: Mapped[str] = mapped_column(String(80))
    called_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text)


class AIRecommendation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Explicitly labelled as a hypothesis for research, never an instruction."""

    __tablename__ = "ai_recommendations"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_analysis.id", ondelete="CASCADE")
    )
    category: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(250))
    body: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Numeric(6, 3))
    status: Mapped[str] = mapped_column(String(30), default="PROPOSED")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    review_notes: Mapped[str | None] = mapped_column(Text)
