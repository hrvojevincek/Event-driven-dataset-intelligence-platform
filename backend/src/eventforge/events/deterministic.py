from uuid import NAMESPACE_URL, UUID, uuid5


def deterministic_event_id(job_id: UUID, detail_type: str) -> UUID:
    """Stable event_id for stage output events so retries publish the same envelope."""
    return uuid5(NAMESPACE_URL, f"{job_id}:{detail_type}")


def deterministic_pipeline_failed_event_id(job_id: UUID, failed_event_id: UUID) -> UUID:
    """Stable event_id for pipeline.failed so DLQ replays publish once."""
    return uuid5(NAMESPACE_URL, f"{job_id}:pipeline.failed:{failed_event_id}")


def deterministic_annotation_task_id(job_id: UUID, task_index: int) -> UUID:
    """Stable task_id for an annotation sub-task within a job."""
    return uuid5(NAMESPACE_URL, f"{job_id}:annotation-task:{task_index}")


def deterministic_research_task_id(job_id: UUID, task_index: int) -> UUID:
    """Stable task_id for a research sub-task within a job (legacy alias)."""
    return deterministic_annotation_task_id(job_id, task_index)
