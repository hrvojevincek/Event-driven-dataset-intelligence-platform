import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models."""


class JobStatus(StrEnum):
    """Lifecycle states for a dataset project."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStageName(StrEnum):
    """Named pipeline stages in execution order."""

    INTAKE = "intake"
    PREPROCESSING = "preprocessing"
    PLANNING = "planning"
    ANNOTATION = "annotation"
    EXPORT = "export"


# Ordered stages used when creating job_stages rows (excludes deprecated aliases).
PIPELINE_STAGE_NAMES: tuple[JobStageName, ...] = (
    JobStageName.INTAKE,
    JobStageName.PREPROCESSING,
    JobStageName.PLANNING,
    JobStageName.ANNOTATION,
    JobStageName.EXPORT,
)


class StageStatus(StrEnum):
    """Per-stage execution states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AssetFetchStatus(StrEnum):
    """Asset preprocessing lifecycle."""

    PENDING = "pending"
    OK = "ok"
    FAILED = "failed"


class User(Base):
    """Authenticated user keyed by external auth subject (mock user locally)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    auth_subject_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    jobs: Mapped[list["Job"]] = relationship(back_populates="user")


class Job(Base):
    """A dataset project and its overall pipeline state."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    correlation_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_json: Mapped[str] = mapped_column(Text, nullable=False)
    schema_template: Mapped[str | None] = mapped_column(String(64), nullable=True)
    domain: Mapped[str] = mapped_column(String(32), nullable=False, default="documents")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=JobStatus.PENDING.value)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="jobs")
    stages: Mapped[list["JobStage"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    assets: Mapped[list["Asset"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    segments: Mapped[list["Segment"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    annotation_tasks: Mapped[list["AnnotationTask"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    annotation_batches: Mapped[list["AnnotationBatch"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    dataset_export: Mapped["DatasetExport | None"] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )
    llm_usage_records: Mapped[list["LLMUsage"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class LLMUsage(Base):
    """Token usage and cost for one LLM call within a project."""

    __tablename__ = "llm_usage"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped["Job"] = relationship(back_populates="llm_usage_records")


class JobStage(Base):
    """Execution record for one pipeline stage on a project."""

    __tablename__ = "job_stages"
    __table_args__ = (UniqueConstraint("job_id", "stage", name="uq_job_stages_job_id_stage"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=StageStatus.PENDING.value
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    job: Mapped["Job"] = relationship(back_populates="stages")


class Asset(Base):
    """Uploaded file registered during intake."""

    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provenance: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetch_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AssetFetchStatus.PENDING.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped["Job"] = relationship(back_populates="assets")
    segments: Mapped[list["Segment"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )


class Segment(Base):
    """Preprocessed text slice from an asset."""

    __tablename__ = "segments"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "segment_index",
            name="uq_segments_asset_id_segment_index",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped["Job"] = relationship(back_populates="segments")
    asset: Mapped["Asset"] = relationship(back_populates="segments")


class AnnotationTask(Base):
    """Planned labeling work over a batch of segments."""

    __tablename__ = "annotation_tasks"
    __table_args__ = (
        UniqueConstraint("job_id", "task_index", name="uq_annotation_tasks_job_id_task_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_index: Mapped[int] = mapped_column(Integer, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    segment_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped["Job"] = relationship(back_populates="annotation_tasks")


class AnnotationBatch(Base):
    """Structured labels produced for one annotation task."""

    __tablename__ = "annotation_batches"
    __table_args__ = (
        UniqueConstraint("job_id", "task_index", name="uq_annotation_batches_job_id_task_index"),
        UniqueConstraint("task_id", name="uq_annotation_batches_task_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    task_index: Mapped[int] = mapped_column(Integer, nullable=False)
    labels_json: Mapped[str] = mapped_column(Text, nullable=False)
    segment_count: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped["Job"] = relationship(back_populates="annotation_batches")


class DatasetExport(Base):
    """Final JSONL export and QC report for a completed project."""

    __tablename__ = "dataset_exports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    export_content: Mapped[str] = mapped_column(Text, nullable=False)
    qc_report_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped["Job"] = relationship(back_populates="dataset_export")


class ProcessedEvent(Base):
    """Idempotency record — composite PK (event_id, worker_name)."""

    __tablename__ = "processed_events"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    worker_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
