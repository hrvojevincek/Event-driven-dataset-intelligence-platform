from eventforge.db.repositories.annotation_batch import AnnotationBatchRepository
from eventforge.db.repositories.annotation_task import AnnotationTaskRepository
from eventforge.db.repositories.asset import AssetRepository
from eventforge.db.repositories.base import BaseRepository
from eventforge.db.repositories.dataset_export import DatasetExportRepository
from eventforge.db.repositories.job import JobRepository, JobStageRepository
from eventforge.db.repositories.llm_usage import LLMUsageRepository
from eventforge.db.repositories.processed_event import ProcessedEventRepository
from eventforge.db.repositories.segment import SegmentRepository
from eventforge.db.repositories.user import UserRepository

# Deprecated aliases — removed when legacy agent code is deleted (Phase 3+).
DocumentChunkRepository = SegmentRepository
KnowledgeEntityRepository = AnnotationTaskRepository
ResearchNoteRepository = AnnotationBatchRepository
SourceRepository = AssetRepository
SynthesisReportRepository = DatasetExportRepository

__all__ = [
    "AnnotationBatchRepository",
    "AnnotationTaskRepository",
    "AssetRepository",
    "BaseRepository",
    "DatasetExportRepository",
    "DocumentChunkRepository",
    "JobRepository",
    "JobStageRepository",
    "KnowledgeEntityRepository",
    "LLMUsageRepository",
    "ProcessedEventRepository",
    "ResearchNoteRepository",
    "SegmentRepository",
    "SourceRepository",
    "SynthesisReportRepository",
    "UserRepository",
]
