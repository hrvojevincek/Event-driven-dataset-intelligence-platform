from eventforge.db.models import JobStageName
from eventforge.events.schemas.constants import (
    DETAIL_TYPE_ANNOTATION_TASK_COMPLETED,
    DETAIL_TYPE_ANNOTATION_TASK_DISPATCHED,
    DETAIL_TYPE_EMBEDDING_COMPLETED,
    DETAIL_TYPE_INTAKE_COMPLETED,
    DETAIL_TYPE_KNOWLEDGE_MINED,
    DETAIL_TYPE_PLANNING_COMPLETED,
    DETAIL_TYPE_PREPROCESSING_COMPLETED,
    DETAIL_TYPE_PROJECT_SUBMITTED,
    DETAIL_TYPE_RESEARCH_TASK_COMPLETED,
    DETAIL_TYPE_RESEARCH_TASK_DISPATCHED,
)

DETAIL_TYPE_TO_FAILED_STAGE: dict[str, str] = {
    DETAIL_TYPE_PROJECT_SUBMITTED: JobStageName.INTAKE.value,
    DETAIL_TYPE_INTAKE_COMPLETED: JobStageName.PREPROCESSING.value,
    DETAIL_TYPE_PREPROCESSING_COMPLETED: JobStageName.PLANNING.value,
    DETAIL_TYPE_PLANNING_COMPLETED: JobStageName.ANNOTATION.value,
    DETAIL_TYPE_ANNOTATION_TASK_DISPATCHED: JobStageName.ANNOTATION.value,
    DETAIL_TYPE_ANNOTATION_TASK_COMPLETED: JobStageName.EXPORT.value,
    # Legacy detail types until remaining research schemas are removed
    DETAIL_TYPE_EMBEDDING_COMPLETED: JobStageName.PLANNING.value,
    DETAIL_TYPE_KNOWLEDGE_MINED: JobStageName.ANNOTATION.value,
    DETAIL_TYPE_RESEARCH_TASK_DISPATCHED: JobStageName.ANNOTATION.value,
    DETAIL_TYPE_RESEARCH_TASK_COMPLETED: JobStageName.EXPORT.value,
}

DETAIL_TYPE_TO_QUEUE_SUFFIX: dict[str, str] = {
    DETAIL_TYPE_PROJECT_SUBMITTED: "intake",
    DETAIL_TYPE_INTAKE_COMPLETED: "preprocessing",
    DETAIL_TYPE_PREPROCESSING_COMPLETED: "planning",
    DETAIL_TYPE_PLANNING_COMPLETED: "annotation",
    DETAIL_TYPE_ANNOTATION_TASK_DISPATCHED: "annotation",
    DETAIL_TYPE_ANNOTATION_TASK_COMPLETED: "export",
    # Legacy detail types until remaining research schemas are removed
    DETAIL_TYPE_EMBEDDING_COMPLETED: "planning",
    DETAIL_TYPE_KNOWLEDGE_MINED: "annotation",
    DETAIL_TYPE_RESEARCH_TASK_DISPATCHED: "annotation",
    DETAIL_TYPE_RESEARCH_TASK_COMPLETED: "export",
}


def stage_for_failed_detail_type(detail_type: str) -> str | None:
    """Map an inbound event detail_type to the worker stage that failed to process it."""
    return DETAIL_TYPE_TO_FAILED_STAGE.get(detail_type)


def source_queue_for_detail_type(detail_type: str) -> str | None:
    """Infer the worker queue an inbound event was consumed from."""
    suffix = DETAIL_TYPE_TO_QUEUE_SUFFIX.get(detail_type)
    if suffix is None:
        return None
    from eventforge.core.config import get_settings

    return f"{get_settings().sqs_queue_prefix}-{suffix}"
