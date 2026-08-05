from eventforge.db.models.base import (
    PIPELINE_STAGE_NAMES,
    AnnotationBatch,
    AnnotationTask,
    Asset,
    AssetFetchStatus,
    Base,
    DatasetExport,
    Job,
    JobStage,
    JobStageName,
    JobStatus,
    LLMUsage,
    ProcessedEvent,
    Segment,
    StageStatus,
    User,
)

# Deprecated aliases — removed when legacy agent code is deleted (Phase 3+).
Project = Job
Source = Asset
DocumentChunk = Segment
KnowledgeEntity = AnnotationTask
ResearchNote = AnnotationBatch
SynthesisReport = DatasetExport

__all__ = [
    "AnnotationBatch",
    "AnnotationTask",
    "Asset",
    "AssetFetchStatus",
    "Base",
    "DatasetExport",
    "DocumentChunk",
    "Job",
    "JobStage",
    "JobStageName",
    "JobStatus",
    "KnowledgeEntity",
    "LLMUsage",
    "PIPELINE_STAGE_NAMES",
    "ProcessedEvent",
    "Project",
    "ResearchNote",
    "Segment",
    "Source",
    "StageStatus",
    "SynthesisReport",
    "User",
]
