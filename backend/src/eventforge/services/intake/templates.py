"""Built-in annotation schema templates for v1 projects."""

from typing import Any

SUPPORT_CALL_TEMPLATE = "support_call"
DOCUMENT_CLASSIFICATION_TEMPLATE = "document_classification"

SCHEMA_TEMPLATES: dict[str, dict[str, Any]] = {
    SUPPORT_CALL_TEMPLATE: {
        "type": "object",
        "properties": {
            "emotion": {"type": "string"},
            "intent": {"type": "string"},
            "topic": {"type": "string"},
            "resolution_status": {"type": "string"},
        },
        "required": ["emotion", "intent", "topic", "resolution_status"],
    },
    DOCUMENT_CLASSIFICATION_TEMPLATE: {
        "type": "object",
        "properties": {
            "category": {"type": "string"},
            "summary": {"type": "string"},
            "sensitivity_flag": {"type": "string"},
        },
        "required": ["category", "summary", "sensitivity_flag"],
    },
}


def resolve_schema(
    *,
    schema_template: str | None,
    schema_json: dict[str, Any] | None,
) -> tuple[dict[str, Any], str | None]:
    """Merge an optional template with an optional JSON override."""
    if schema_template and schema_template not in SCHEMA_TEMPLATES:
        known = ", ".join(sorted(SCHEMA_TEMPLATES))
        msg = f"Unknown schema_template '{schema_template}'. Expected one of: {known}"
        raise ValueError(msg)

    base: dict[str, Any] = {}
    if schema_template:
        base = dict(SCHEMA_TEMPLATES[schema_template])
    if schema_json:
        base = schema_json if not base else {**base, **schema_json}
    if not base:
        msg = "Provide schema_template or schema_json"
        raise ValueError(msg)
    return base, schema_template
