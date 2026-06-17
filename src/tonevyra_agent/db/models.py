"""SQLAlchemy ORM models for the existing Tonevyra PostgreSQL schema."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import CHAR, BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ImageTask(Base):
    __tablename__ = "image_tasks"
    __table_args__ = (
        CheckConstraint(
            "status = ANY (ARRAY['DETECTED'::text, 'STABILIZING'::text, 'QUEUED'::text, "
            "'ANALYZING'::text, 'ANALYSIS_DONE'::text, 'CORRECTION_PLANNED'::text, "
            "'LIGHTROOM_REQUESTED'::text, 'LIGHTROOM_PROCESSING'::text, 'EXPORT_DONE'::text, "
            "'QUALITY_CHECK'::text, 'PASS'::text, 'REVIEW_REQUIRED'::text, 'FAILED'::text, "
            "'SKIPPED'::text])",
            name="image_tasks_status_check",
        ),
        CheckConstraint("retry_count >= 0", name="image_tasks_retry_count_check"),
        {"schema": "public"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_hash: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_ext: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'DETECTED'::text"))
    current_stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    quality_decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    artifacts: Mapped[list[TaskArtifact]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    events: Mapped[list[TaskEvent]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    stage_results: Mapped[list[StageResult]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    quality_results: Mapped[list[QualityResult]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    feedback_records: Mapped[list[FeedbackRecord]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    learning_samples: Mapped[list[LearningSample]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class TaskArtifact(Base):
    __tablename__ = "task_artifacts"
    __table_args__ = (
        CheckConstraint(
            "artifact_type = ANY (ARRAY['EXIF_JSON'::text, 'PREVIEW_JPEG'::text, "
            "'VISION_PROMPT'::text, 'VISION_RAW_RESPONSE'::text, 'VISION_STRUCTURED'::text, "
            "'CORRECTION_PLAN'::text, 'LIGHTROOM_REQUEST'::text, 'LIGHTROOM_RESPONSE'::text, "
            "'QUALITY_DETAIL'::text, 'EXPORTED_IMAGE'::text, 'RECOVERY_DECISION'::text, "
            "'AI_SETTINGS'::text, 'FINAL_SETTINGS'::text, 'MANUAL_EDIT_DELTA'::text, "
            "'FEEDBACK_RECORD'::text, 'TRAINING_SAMPLE_MANIFEST'::text])",
            name="task_artifacts_artifact_type_check",
        ),
        CheckConstraint("version >= 1", name="task_artifacts_version_check"),
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="task_artifacts_size_bytes_check"),
        {"schema": "public"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("public.image_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_type: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("now()"))

    task: Mapped[ImageTask] = relationship(back_populates="artifacts")


class TaskEvent(Base):
    __tablename__ = "task_events"
    __table_args__ = ({"schema": "public"},)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("public.image_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("now()"))

    task: Mapped[ImageTask] = relationship(back_populates="events")


class StageResult(Base):
    __tablename__ = "stage_results"
    __table_args__ = (
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="stage_results_duration_ms_check"),
        {"schema": "public"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("public.image_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    stage_status: Mapped[str] = mapped_column(Text, nullable=False)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("now()"))

    task: Mapped[ImageTask] = relationship(back_populates="stage_results")


class QualityResult(Base):
    __tablename__ = "quality_results"
    __table_args__ = ({"schema": "public"},)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("public.image_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    exposure_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    color_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    sharpness_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    noise_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    saturation_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    underwater_cast_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    overall_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    reason_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("now()"))

    task: Mapped[ImageTask] = relationship(back_populates="quality_results")


class FeedbackRecord(Base):
    __tablename__ = "feedback_records"
    __table_args__ = ({"schema": "public"},)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("public.image_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_action: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("ARRAY[]::text[]"))
    ai_settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    final_settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    manual_edit_delta_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("now()"))

    task: Mapped[ImageTask] = relationship(back_populates="feedback_records")
    learning_samples: Mapped[list[LearningSample]] = relationship(back_populates="feedback")


class LearningSample(Base):
    __tablename__ = "learning_samples"
    __table_args__ = ({"schema": "public"},)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("public.image_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    feedback_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("public.feedback_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    sample_type: Mapped[str] = mapped_column(Text, nullable=False)
    sample_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'::text"))
    dataset_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("now()"))

    task: Mapped[ImageTask] = relationship(back_populates="learning_samples")
    feedback: Mapped[FeedbackRecord | None] = relationship(back_populates="learning_samples")


class VTaskSummary(Base):
    __tablename__ = "v_task_summary"
    __table_args__ = ({"schema": "public"},)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    file_name: Mapped[str | None] = mapped_column(Text)
    file_ext: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    current_stage: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int | None] = mapped_column(Integer)
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    quality_decision: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    failed_stage: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    artifact_count: Mapped[int | None] = mapped_column(BigInteger)
    event_count: Mapped[int | None] = mapped_column(BigInteger)
