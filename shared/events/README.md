# Event Schemas

> **Cursor agents:** Pipeline rules in `.cursor/rules/event-pipeline.mdc`. Define schemas here before backend Pydantic models.

Canonical event contracts shared between backend publishers, workers, and Step Functions.

## Conventions

- EventBridge `detail-type`: `eventforge.<domain>.<action>` (e.g. `eventforge.project.submitted`)
- Envelope fields: `event_id`, `correlation_id`, `job_id`, `timestamp`, `schema_version`, `detail_type`, `payload`
- JSON Schema in this directory; mirrored as Pydantic in `backend/src/eventforge/events/schemas/`

## Dataset platform pipeline (current)

```
project.submitted → intake.completed → preprocessing.completed → planning.completed
  → annotation.task.dispatched (×N) → annotation.task.completed (×N)
  → annotation.all_completed → export.completed
```

Physical SQS queue names are unchanged (`eventforge-ingestion`, `eventforge-embedding`, etc.) until Phase 9.

## Schema index

| File                                       | Status        | Producer                | Consumer                |
| ------------------------------------------ | ------------- | ----------------------- | ----------------------- |
| `envelope.schema.json`                     | Done          | All                     | All                     |
| `project.submitted.schema.json`            | Done (pivot)  | API                     | Intake worker           |
| `intake.completed.schema.json`             | Done (pivot)  | Intake                  | Preprocessing worker    |
| `preprocessing.completed.schema.json`      | Done (pivot)  | Preprocessing           | Planning worker         |
| `planning.completed.schema.json`           | Done (pivot)  | Planning                | Annotation orchestrator |
| `annotation.task.dispatched.schema.json`   | Done (pivot)  | Annotation orchestrator | Annotation workers      |
| `annotation.task.completed.schema.json`    | Done (pivot)  | Annotation              | Export worker           |
| `annotation.all_completed.schema.json`     | Done (pivot)  | Annotation orchestrator | Export worker           |
| `export.completed.schema.json`             | Done (pivot)  | Export                  | API / SSE               |
| `pipeline.failed.schema.json`              | Done          | DLQ worker              | Alerting / SSE          |

### Legacy (removed in Phase 7)

| File                                   | Replaced by                              |
| -------------------------------------- | ---------------------------------------- |
| `query.submitted.schema.json`          | `project.submitted.schema.json`          |
| `ingestion.completed.schema.json`      | `intake.completed.schema.json`           |
| `embedding.completed.schema.json`      | `preprocessing.completed.schema.json`    |
| `knowledge.mined.schema.json`          | `planning.completed.schema.json`         |
| `research.task.dispatched.schema.json` | `annotation.task.dispatched.schema.json` |
| `research.task.completed.schema.json`  | `annotation.task.completed.schema.json`  |
| `research.all_completed.schema.json`   | `annotation.all_completed.schema.json`   |
| `synthesis.completed.schema.json`      | `export.completed.schema.json`           |

See `docs/DATASET_PLATFORM.md` and `docs/PIVOT_PLAN.md` for the full pivot plan.
