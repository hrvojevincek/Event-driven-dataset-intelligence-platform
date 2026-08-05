# EventForge — Cursor Agent Guide

> **You are working in Cursor IDE.** Project context is loaded automatically from `.cursor/rules/`. This file is the entry point for agent sessions.

## What to read

| Priority | Source                                      | When                                                            |
| -------- | ------------------------------------------- | --------------------------------------------------------------- |
| 1        | `.cursor/rules/eventforge-core.mdc`         | Always (auto-applied)                                           |
| 2        | **`docs/DATASET_PLATFORM.md`**              | **Active pivot — what we're building**                          |
| 3        | **`docs/PIVOT_PLAN.md`**                    | **Active pivot — phase checklist & progress**                   |
| 4        | `.cursor/rules/dataset-pivot.mdc`           | Backend, frontend, events during pivot                            |
| 5        | `.cursor/rules/*.mdc` matching open files   | File-specific context                                           |
| 6        | **Linear MCP** (`list_issues`, `get_issue`) | Issue tracking (when Linear issues exist for pivot)               |
| 7        | `docs/LINEAR.md`                            | Legacy issue index (Phases 0–5)                                 |
| 8        | `docs/TASKS.md`                             | Legacy phase progress (Phases 0–6)                              |
| 9        | `docs/ARCHITECTURE.md`                      | Legacy pipeline diagrams — update in pivot Phase 10               |
| 10       | `docs/TECH_DECISIONS.md`                    | ADR-014 pivot decision + stack choices                          |
| 11       | `docs/PRD.md`                               | Legacy product scope — update in pivot Phase 10                   |
| 12       | `docs/LOCAL_DEV.md`                         | Local setup and troubleshooting                                 |
| 13       | `docs/ISSUES.md`                            | Postmortems; append after hard infra/CI fixes (no secrets)      |

## Project summary

**EventForge** — pivoting to an **event-driven dataset intelligence platform** (BeatPulse-style).

- User uploads files + annotation schema → EventBridge pipeline (intake → preprocess → plan → parallel annotate → export) → JSONL + QC in dashboard with React Flow
- Hybrid: Next.js frontend + FastAPI backend + AWS events (EventBridge/SQS/Step Functions)
- Data: Postgres (OLTP; pgvector removed) | Auth: mock user | Observability: OpenTelemetry

## Current status

**Dataset pivot active (2026-08-05).** Decisions locked via grilling — see `docs/PIVOT_PLAN.md` § Locked decisions.

| Track | Status | Doc |
| ----- | ------ | --- |
| **Dataset pivot** | Phase 0 ✅ → Phase 1 next | `docs/PIVOT_PLAN.md` |
| Legacy AWS (archived) | Terraform in repo, not maintained | ADR-015 |

**Infra scope:** LocalStack + workers locally. No AWS deploy.

## Commands

```bash
./scripts/setup-local.sh && make dev   # start local infra
make down                              # stop
```

## Agent rules

1. Surgical diffs — don't over-engineer
2. Event schemas in `shared/events/` before backend code
3. Production patterns: idempotency, DLQ, OTEL spans, cost tracking
4. Update `docs/TASKS.md` checkboxes when done
5. Commit only when user explicitly requests
6. **Docstrings on classes** — new or touched Python classes get a one-line docstring (see `backend-python.mdc`)

## User shortcuts

| Say this                     | Agent does                                          |
| ---------------------------- | --------------------------------------------------- |
| "What's next in the pivot?" | Read `docs/PIVOT_PLAN.md` progress table → next phase |
| "Implement pivot Phase N"    | Follow `docs/PIVOT_PLAN.md` Phase N checklist       |
| "What's next in EventForge?" | Linear MCP or `docs/PIVOT_PLAN.md` if pivot active  |
| "Implement KRE-118"          | `get_issue` → implement acceptance criteria         |
| "Mark KRE-117 done"          | Close in Linear + update `docs/TASKS.md`            |

## Cursor rules map

```
.cursor/rules/
├── eventforge-core.mdc      alwaysApply — stack, architecture, behavior
├── dataset-pivot.mdc        pivot — target product, terminology, constraints
├── backend-python.mdc       backend/**
├── frontend-nextjs.mdc      frontend/**
├── event-pipeline.mdc       agents, workers, events (legacy + target flow)
├── infra-aws.mdc            infra, docker-compose
└── docs-workflow.mdc        docs, TASKS, workflow
```
