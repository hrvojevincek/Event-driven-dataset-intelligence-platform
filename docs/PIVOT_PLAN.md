# Dataset Pivot — Implementation Plan

> **Cursor agents:** Active work tracker for research → dataset intelligence pivot.  
> **Product vision:** `docs/DATASET_PLATFORM.md` · **ADRs:** ADR-014 (pivot), ADR-015 (local-only scope)

**Started:** 2026-08-04  
**Decisions locked:** 2026-08-05 (grilling session)  
**Estimated effort:** ~10–12 dev days  
**Strategy:** Big-bang rename in vertical slices — no parallel `/queries` route

---

## Locked decisions (do not re-litigate)

| #   | Decision         | Choice                                                                                                                                       |
| --- | ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Primary goal** | Portfolio-first + BeatPulse-flavored hooks (schema, provenance, QC)                                                                          |
| 2   | **Demo balance** | 60% live React Flow pipeline / 40% QC + JSONL export story                                                                                   |
| 3   | **v1 domain**    | `.txt`, `.md`, `.pdf` in; **support-call transcript fixture** + speech-style labels out                                                      |
| 4   | **Migration**    | Big-bang with vertical-slice milestones (delete research code as each stage lands)                                                           |
| 5   | **Schema UX**    | Template picker + JSON override; 2 v1 templates (see below)                                                                                  |
| 6   | **File storage** | Local disk only (`./data/uploads/`); S3 deferred (no deploy)                                                                                 |
| 7   | **Parallelism**  | Preprocessing sequential (single worker); annotation fan-out via Step Functions Map (local: simplified sequential where LocalStack is flaky) |
| 8   | **Infra scope**  | **LocalStack yes** (EventBridge + SQS + workers). **AWS deploy no.** Terraform kept in repo, not maintained — README note only               |
| 9   | **Project name** | **EventForge** (unchanged)                                                                                                                   |

### v1 schema templates

1. **Support call annotation** — `emotion`, `intent`, `topic`, `resolution_status` (speech-flavored demo)
2. **Document classification** — `category`, `summary`, `sensitivity_flag`

Users pick a template, optionally edit JSON. No form builder in v1.

### Demo fixture

`fixtures/support-calls/` — ~10 plain-text transcript snippets (`call_001.txt` …) submitted with the **Support call annotation** template.

---

## Progress summary

| Phase | Name                | Status         |
| ----- | ------------------- | -------------- |
| 0     | Decisions & docs    | ✅ Done        |
| 1     | Data model          | ✅ Done        |
| 2     | Event contracts     | ✅ Done        |
| 3     | Intake stage        | ✅ Done        |
| 4     | Preprocessing stage | ✅ Done        |
| 5     | Planning stage      | ⬜ Not started |
| 6     | Annotation stage    | ⬜ Not started |
| 7     | Export stage        | ⬜ Not started |
| 8     | Frontend pivot      | ⬜ Not started |
| 9     | Local infra cleanup | ⬜ Not started |
| 10    | Polish & portfolio  | ⬜ Not started |

**Legend:** ⬜ Not started · 🟡 In progress · ✅ Done

**Next:** Phase 5 — Planning stage

---

## Build order

```
Week 1: Phase 1–4  → upload files, get segments E2E (first green milestone)
Week 2: Phase 5–7  → full pipeline to JSONL (API/curl)
Week 3: Phase 8–10 → UI, local cleanup, README + demo fixture
```

---

## Phase 0 — Decisions & documentation ✅

- [x] Write `docs/DATASET_PLATFORM.md`
- [x] Write `docs/PIVOT_PLAN.md`
- [x] ADR-014 (dataset pivot) + ADR-015 (local-only scope)
- [x] `.cursor/rules/dataset-pivot.mdc`
- [x] Grilling session — all decisions locked (2026-08-05)
- [x] Project name: **EventForge**
- [x] v1 domain: documents + support-call demo fixture

---

## Phase 1 — Data model ✅

**Goal:** New DB shape. Drop pgvector.

### Models (`backend/src/eventforge/db/models/`)

- [x] Extend `Job` with project fields: `name`, `description`, `schema_json`, `schema_template`, `domain`
- [x] Add `Asset` model (replaces `Source`)
- [x] Add `Segment` model (replaces `DocumentChunk`, no embedding)
- [x] Add `AnnotationTask` model (replaces `KnowledgeEntity`)
- [x] Add `AnnotationBatch` model (replaces `ResearchNote`)
- [x] Add `DatasetExport` model (replaces `SynthesisReport`)

### Stage enum

- [x] Rename `JobStageName`: `intake`, `preprocessing`, `planning`, `annotation`, `export`
- [x] Add `PIPELINE_STAGE_NAMES` for stage row creation

### Migration

- [x] Single baseline migration `0001_initial_dataset_platform.py` (legacy chain removed)
- [x] Switch Postgres image to plain `postgres:16` (docker-compose + CI)
- [x] New repositories + deprecated aliases for legacy imports
- [x] Update `test_db.py` + add `test_dataset_models.py`
- [x] Remove `pgvector` from `pyproject.toml`

**Exit:** `alembic upgrade head` succeeds. No pgvector in models or Docker.

**Note:** Legacy agents/tests still use old field names — addressed in Phases 2–7.

---

## Phase 2 — Event contracts

**Goal:** New JSON schemas + Pydantic models. Update **LocalStack init** (not Terraform).

| Legacy                     | Target                       | Schema file                                            |
| -------------------------- | ---------------------------- | ------------------------------------------------------ |
| `query.submitted`          | `project.submitted`          | `shared/events/project.submitted.schema.json`          |
| `ingestion.completed`      | `intake.completed`           | `shared/events/intake.completed.schema.json`           |
| `embedding.completed`      | `preprocessing.completed`    | `shared/events/preprocessing.completed.schema.json`    |
| `knowledge.mined`          | `planning.completed`         | `shared/events/planning.completed.schema.json`         |
| `research.task.dispatched` | `annotation.task.dispatched` | `shared/events/annotation.task.dispatched.schema.json` |
| `research.task.completed`  | `annotation.task.completed`  | `shared/events/annotation.task.completed.schema.json`  |
| `research.all_completed`   | `annotation.all_completed`   | `shared/events/annotation.all_completed.schema.json`   |
| `synthesis.completed`      | `export.completed`           | `shared/events/export.completed.schema.json`           |

- [x] JSON schemas in `shared/events/`
- [x] Pydantic models in `backend/src/eventforge/events/schemas/`
- [x] Update `infra/docker/localstack/init/01-eventforge.sh` routing rules
- [ ] **Defer:** Terraform module updates (archived — no deploy)
- [ ] **Defer:** physical SQS queue renames (keep `eventforge-embedding` queue name)

**Exit:** New events validate. LocalStack routes target event types.

---

## Phase 3 — Intake stage

**Replaces:** `agents/ingestion.py`, Tavily, `POST /queries`

- [x] `services/storage/local.py` — save uploads to `./data/uploads/{project_id}/`
- [x] `services/intake/` — file validation, mime detection, provenance metadata
- [x] `agents/intake.py` + `workers/intake.py`
- [x] `api/routes/projects.py` — `POST /api/v1/projects` (multipart + `schema_template` or `schema_json`)
- [x] `services/project.py` (rename from `query.py`) — emit `project.submitted`
- [x] Delete Tavily from intake path

**Exit:** Upload 5 files → assets in DB → `intake.completed` on LocalStack.

---

## Phase 4 — Preprocessing stage

**Replaces:** `agents/embedding.py`, `services/embedding/`

**v1:** Single worker processes all assets sequentially (no per-asset Map state).

- [x] `services/preprocessing/extract.py` — plain text + PDF (`pypdf`)
- [x] `services/preprocessing/segmentation.py` — paragraph / token-window segments
- [x] `agents/preprocessing.py` + `workers/preprocessing.py`
- [x] Delete `services/embedding/` entirely
- [x] Remove embedding config + OpenAI embedding calls

**Exit:** PDFs/text → segments in DB. First **vertical-slice E2E**: upload → segments.

### Phase 4.1 — PDF segmentation tightening

- [x] Layout-aware PDF extraction via `pymupdf4llm` (Markdown output)
- [x] Document-type-aware segmentation (`plain` vs `markdown`)
- [x] PDF/Markdown: header-aware sections + paragraph reconstruction (no line-by-line fallback)
- [x] Plain `.txt`: keep paragraph → line fallback for transcripts

**Exit:** Simple PDFs produce coherent multi-sentence segments, not one line per chunk.

---

## Phase 5 — Planning stage

**Replaces:** `agents/knowledge.py`, entity extraction

- [ ] `services/planning/schema_templates.py` — Support call + Document classification templates
- [ ] `services/planning/task_builder.py` — merge template + override; batch segments into N tasks
- [ ] `agents/planning.py` + `workers/planning.py`
- [ ] Validate `schema_json` against template constraints

**Exit:** Segments → N `AnnotationTask` rows driven by chosen template.

---

## Phase 6 — Annotation stage

**Replaces:** `agents/research.py`, RAG, Tavily follow-up

**v1:** Step Functions Map for annotation fan-out; fallback to sequential in local dev per LocalStack limits.

- [ ] `services/annotation/labeler.py` — LLM labels segment batch; JSON schema validation; confidence flag
- [ ] `agents/annotation.py` + `workers/annotation.py`
- [ ] Update Step Functions ASL template (annotation naming) — local init script only
- [ ] Delete `services/research/`, Tavily research usage

**Exit:** Parallel annotation tasks → `AnnotationBatch` rows with valid `labels_json`.

---

## Phase 7 — Export stage

**Replaces:** `agents/synthesis.py`

- [ ] `services/export/merge.py` — combine batches → JSONL
- [ ] `services/export/qc.py` — coverage %, schema compliance, low-confidence flags, cost total
- [ ] `agents/export.py` + `workers/export.py`
- [ ] `GET /api/v1/projects/{id}/export` — download JSONL

**Exit:** Full pipeline → JSONL + QC report. **Full E2E milestone.**

---

## Phase 8 — Frontend pivot

**Demo UX:** 60% pipeline animation / 40% QC + export panel.

- [ ] New `PIPELINE_STAGES` + agent names in `job-stream.ts` / `stage-agents.ts`
- [ ] `/projects/new` — file upload + template picker + optional JSON editor
- [ ] `/projects/[id]` — React Flow + **QC panel** (coverage, flags) + JSONL preview + download
- [ ] Remove synthesis markdown viewer; remove query submit form
- [ ] Landing page copy — dataset intelligence platform

**Exit:** 5-minute demo path works in browser.

---

## Phase 9 — Local infra cleanup

**In scope (local only):**

- [ ] Postgres image: `postgres:16` (drop pgvector)
- [ ] Remove Tavily from `.env.example` and config
- [ ] Update LocalStack init for new event routes
- [ ] Update `scripts/verify-pipeline-e2e.sh` for project upload flow
- [ ] Add `data/uploads/` to `.gitignore`

**Out of scope (archived — do not maintain):**

- Terraform applies, ECS deploy, RDS, Secrets Manager
- S3 storage backend
- Physical SQS queue renames in Terraform

**Exit:** `make dev` + E2E script passes locally.

---

## Phase 10 — Polish & portfolio

- [ ] Update `README.md` — new pitch + note: _Terraform/ECS built previously; pivot target is local-only_
- [ ] Update `docs/ARCHITECTURE.md` — target pipeline diagram
- [ ] Add `fixtures/support-calls/` + `scripts/demo-support-calls.sh`
- [ ] Update `docs/PRD.md` vision (brief)
- [ ] Edge-case flags in QC (no HITL UI — v2)

**Exit:** Portfolio demo reproducible in 5 minutes.

---

## 5-minute demo script

1. Open http://localhost:3000
2. **New project** → upload `fixtures/support-calls/*.txt`
3. Select template **Support call annotation** ( tweak JSON if desired)
4. Watch React Flow: Intake → Preprocessing → Planning → Annotation (×N) → Export
5. Show **QC panel**: coverage, flagged segments
6. Download **JSONL** — point out provenance fields per line

---

## File touch map

| Area        | Key files                                                                            |
| ----------- | ------------------------------------------------------------------------------------ |
| Models      | `backend/src/eventforge/db/models/base.py`                                           |
| Events      | `shared/events/`, `backend/src/eventforge/events/schemas/`                           |
| Agents      | `backend/src/eventforge/agents/{intake,preprocessing,planning,annotation,export}.py` |
| Workers     | `backend/src/eventforge/workers/`                                                    |
| Services    | `services/{storage,intake,preprocessing,planning,annotation,export}/`                |
| API         | `api/routes/projects.py`                                                             |
| Frontend    | `types/job-stream.ts`, `components/workflow/`, `components/dashboard/`               |
| Local infra | `docker-compose.yml`, `infra/docker/localstack/init/`                                |
| Fixtures    | `fixtures/support-calls/`                                                            |
| Docs        | `docs/DATASET_PLATFORM.md`, `README.md`                                              |

---

## Agent instructions

1. Read locked decisions above before implementing
2. Event schemas in `shared/events/` **before** backend code
3. One pivot phase at a time; check boxes when done
4. Do **not** reintroduce pgvector, Tavily, or RAG
5. Do **not** scope AWS deploy or Terraform maintenance
6. LocalStack + workers stay; no in-process pipeline shortcut

---

## v2 backlog

- Real speech (Whisper + `.mp3`)
- HITL review queue UI
- Preprocessing Map state (one worker per asset)
- S3 storage + AWS deploy (revive Terraform)
- Schema form builder
- `annotation.review_requested` feedback loop event
