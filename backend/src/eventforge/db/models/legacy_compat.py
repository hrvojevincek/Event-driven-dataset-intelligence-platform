"""Map legacy research-model kwargs/attrs onto the dataset platform schema."""

import json
import uuid
from typing import Any


def normalize_job_kwargs(kwargs: dict[str, Any]) -> None:
    if "topic" in kwargs:
        kwargs["name"] = kwargs.pop("topic")

    depth = kwargs.pop("depth", None)
    max_sources = kwargs.pop("max_sources", None)
    if depth is not None or max_sources is not None:
        payload: dict[str, Any] = {}
        raw = kwargs.get("schema_json", "{}")
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = {}
        legacy = payload.get("_legacy", {})
        if depth is not None:
            legacy["depth"] = depth.value if hasattr(depth, "value") else depth
        if max_sources is not None:
            legacy["max_sources"] = max_sources
        payload["_legacy"] = legacy
        kwargs["schema_json"] = json.dumps(payload)

    kwargs.setdefault("schema_json", "{}")


def job_legacy_meta(schema_json: str) -> dict[str, Any]:
    try:
        parsed = json.loads(schema_json)
    except json.JSONDecodeError:
        return {}
    legacy = parsed.get("_legacy", {})
    return legacy if isinstance(legacy, dict) else {}


def normalize_asset_kwargs(kwargs: dict[str, Any]) -> None:
    if "url" in kwargs:
        kwargs["storage_uri"] = kwargs.pop("url")
    if "title" in kwargs:
        kwargs["filename"] = kwargs.pop("title")
    if "snippet" in kwargs:
        kwargs["provenance"] = kwargs.pop("snippet")
    kwargs.setdefault("mime_type", "text/plain")
    kwargs.setdefault("fetch_status", "ok")


def normalize_segment_kwargs(kwargs: dict[str, Any]) -> None:
    kwargs.pop("embedding", None)
    if "source_id" in kwargs:
        kwargs["asset_id"] = kwargs.pop("source_id")
    if "chunk_index" in kwargs:
        kwargs["segment_index"] = kwargs.pop("chunk_index")


def normalize_annotation_task_kwargs(kwargs: dict[str, Any]) -> None:
    name = kwargs.pop("name", None)
    entity_type = kwargs.pop("entity_type", None)
    chunk_id = kwargs.pop("chunk_id", None)
    if name is not None:
        kwargs.setdefault("instructions", name)
    kwargs.setdefault("instructions", name or "")
    meta: dict[str, Any] = {"_legacy_entity_type": entity_type or "concept", "segment_ids": []}
    if chunk_id is not None:
        meta["_legacy_chunk_id"] = str(chunk_id)
    if "segment_ids_json" not in kwargs:
        kwargs["segment_ids_json"] = json.dumps(meta)
    if "task_index" not in kwargs:
        kwargs["task_index"] = 0


def annotation_task_entity_type(segment_ids_json: str) -> str:
    try:
        parsed = json.loads(segment_ids_json)
    except json.JSONDecodeError:
        return "concept"
    if isinstance(parsed, dict):
        value = parsed.get("_legacy_entity_type")
        if isinstance(value, str):
            return value
    return "concept"


def annotation_task_chunk_id(segment_ids_json: str) -> uuid.UUID | None:
    try:
        parsed = json.loads(segment_ids_json)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        raw = parsed.get("_legacy_chunk_id")
        if raw:
            return uuid.UUID(str(raw))
    return None


def set_annotation_task_chunk_id(segment_ids_json: str, chunk_id: uuid.UUID | None) -> str:
    try:
        parsed = json.loads(segment_ids_json)
        if not isinstance(parsed, dict):
            parsed = {"segment_ids": []}
    except json.JSONDecodeError:
        parsed = {"segment_ids": []}
    if chunk_id is None:
        parsed.pop("_legacy_chunk_id", None)
    else:
        parsed["_legacy_chunk_id"] = str(chunk_id)
    return json.dumps(parsed)


def normalize_annotation_batch_kwargs(kwargs: dict[str, Any]) -> None:
    content = kwargs.pop("content", None)
    sub_query = kwargs.pop("sub_query", None)
    if content is not None or sub_query is not None:
        labels: dict[str, str] = {}
        if content is not None:
            labels["content"] = content
        if sub_query is not None:
            labels["sub_query"] = sub_query
        kwargs["labels_json"] = json.dumps(labels)
    kwargs.setdefault("labels_json", kwargs.get("labels_json", "{}"))
    kwargs.setdefault("segment_count", 1)


def annotation_batch_field(labels_json: str, field: str) -> str:
    try:
        parsed = json.loads(labels_json)
    except json.JSONDecodeError:
        return labels_json if field == "content" else ""
    if isinstance(parsed, dict):
        value = parsed.get(field)
        if isinstance(value, str):
            return value
    return ""


def normalize_dataset_export_kwargs(kwargs: dict[str, Any]) -> None:
    if "content" in kwargs:
        kwargs["export_content"] = kwargs.pop("content")
    kwargs.setdefault("qc_report_json", "{}")
