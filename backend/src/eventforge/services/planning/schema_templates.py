"""Built-in label schemas and validation for the planning stage."""

import json
from typing import Any

from eventforge.services.intake.templates import (
    DOCUMENT_CLASSIFICATION_TEMPLATE,
    SCHEMA_TEMPLATES,
    SUPPORT_CALL_AUDIO_TEMPLATE,
    SUPPORT_CALL_TEMPLATE,
)

DEFAULT_SEGMENTS_PER_TASK = 3

TEMPLATE_SEGMENTS_PER_TASK: dict[str, int] = {
    SUPPORT_CALL_TEMPLATE: 1,
    SUPPORT_CALL_AUDIO_TEMPLATE: 5,
    DOCUMENT_CLASSIFICATION_TEMPLATE: 5,
}


def load_label_schema(schema_json: dict[str, Any] | str, template_id: str | None) -> dict[str, Any]:
    """Parse and validate the project's label schema before task planning."""
    if isinstance(schema_json, str):
        try:
            parsed = json.loads(schema_json)
        except json.JSONDecodeError as exc:
            msg = "schema_json must be valid JSON"
            raise ValueError(msg) from exc
    else:
        parsed = schema_json
    if not isinstance(parsed, dict):
        msg = "schema_json must be a JSON object"
        raise ValueError(msg)
    validate_label_schema(parsed, template_id)
    return parsed


def validate_label_schema(schema: dict[str, Any], template_id: str | None) -> None:
    """Ensure the label schema satisfies template constraints for v1."""
    if template_id and template_id not in SCHEMA_TEMPLATES:
        known = ", ".join(sorted(SCHEMA_TEMPLATES))
        msg = f"Unknown schema_template '{template_id}'. Expected one of: {known}"
        raise ValueError(msg)

    if schema.get("type") != "object":
        msg = "Label schema must have type 'object'"
        raise ValueError(msg)

    properties = schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        msg = "Label schema must define at least one property"
        raise ValueError(msg)

    for field_name, field_schema in properties.items():
        if not isinstance(field_schema, dict):
            msg = f"Property '{field_name}' must be an object"
            raise ValueError(msg)
        field_type = field_schema.get("type")
        if field_type != "string":
            msg = f"Property '{field_name}' must have type 'string' in v1"
            raise ValueError(msg)

    required = schema.get("required", [])
    if not isinstance(required, list):
        msg = "Label schema 'required' must be a list when present"
        raise ValueError(msg)

    property_names = set(properties)
    for field_name in required:
        if field_name not in property_names:
            msg = f"Required field '{field_name}' is missing from properties"
            raise ValueError(msg)

    if template_id:
        template_required = SCHEMA_TEMPLATES[template_id].get("required", [])
        for field_name in template_required:
            if field_name not in property_names:
                msg = f"Label schema missing template field '{field_name}'"
                raise ValueError(msg)


def segments_per_task_for_template(template_id: str | None) -> int:
    """Return the default batch size for a schema template."""
    if template_id is None:
        return DEFAULT_SEGMENTS_PER_TASK
    return TEMPLATE_SEGMENTS_PER_TASK.get(template_id, DEFAULT_SEGMENTS_PER_TASK)
