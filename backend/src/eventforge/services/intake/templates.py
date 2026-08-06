"""Built-in annotation schema templates for v1 projects."""

from typing import Any

SUPPORT_CALL_TEMPLATE = "support_call"
SUPPORT_CALL_AUDIO_TEMPLATE = "support_call_audio"
DOCUMENT_CLASSIFICATION_TEMPLATE = "document_classification"

SUPPORT_CALL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "emotion": {"type": "string"},
        "intent": {"type": "string"},
        "topic": {"type": "string"},
        "resolution_status": {"type": "string"},
    },
    "required": ["emotion", "intent", "topic", "resolution_status"],
}

TEMPLATE_ALLOWED_EXTENSIONS: dict[str, frozenset[str]] = {
    SUPPORT_CALL_TEMPLATE: frozenset({".txt", ".md"}),
    SUPPORT_CALL_AUDIO_TEMPLATE: frozenset({".wav"}),
    DOCUMENT_CLASSIFICATION_TEMPLATE: frozenset({".txt", ".md", ".pdf"}),
}

SCHEMA_TEMPLATES: dict[str, dict[str, Any]] = {
    SUPPORT_CALL_TEMPLATE: SUPPORT_CALL_SCHEMA,
    SUPPORT_CALL_AUDIO_TEMPLATE: SUPPORT_CALL_SCHEMA,
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


def domain_for_template(schema_template: str | None) -> str:
    """Map a schema template to the job domain used by preprocessing and export."""
    if schema_template == SUPPORT_CALL_AUDIO_TEMPLATE:
        return "audio"
    if schema_template == SUPPORT_CALL_TEMPLATE:
        return "support_calls"
    return "documents"


def allowed_extensions_for_template(schema_template: str | None) -> frozenset[str]:
    """Return permitted upload extensions for a schema template."""
    if schema_template and schema_template in TEMPLATE_ALLOWED_EXTENSIONS:
        return TEMPLATE_ALLOWED_EXTENSIONS[schema_template]
    merged: set[str] = set()
    for extensions in TEMPLATE_ALLOWED_EXTENSIONS.values():
        merged.update(extensions)
    return frozenset(merged)
