# EventForge — Cursor Agent Context

> **Cursor IDE:** Context loads automatically from `.cursor/rules/`. See `AGENTS.md` for the full agent guide.

## What Is EventForge?

**Pivoting (2026-08-04)** to an event-driven **dataset intelligence platform** — upload files + annotation schema → pipeline → labeled JSONL out. Legacy research/RAG code remains until pivot phases land.

**Read first:** `docs/DATASET_PLATFORM.md` · `docs/PIVOT_PLAN.md`

**Portfolio goal:** production-grade patterns — scalability, resilience, observability, cloud integration, cost awareness.

## Cursor Rules (primary context)

| Rule                  | Scope                                          | Loads when                          |
| --------------------- | ---------------------------------------------- | ----------------------------------- |
| `eventforge-core.mdc` | Stack, architecture, commands, behavior        | **Always**                          |
| `backend-python.mdc`  | FastAPI, agents, workers, DB                   | `backend/**`                        |
| `frontend-nextjs.mdc` | Next.js, React Flow, SSE                       | `frontend/**`                       |
| `event-pipeline.mdc`  | Events, idempotency, stage contracts           | agents/workers/events               |
| `infra-aws.mdc`       | Docker, LocalStack, Terraform                  | `infra/**`                          |
| `dataset-pivot.mdc`   | Target product, terminology, pivot constraints | `backend/**`, `frontend/**`, events |
| `docs-workflow.mdc`   | TASKS, phases, Linear sync                     | `docs/**`                           |

Deep reference: `docs/DATASET_PLATFORM.md`, `docs/PIVOT_PLAN.md`, `docs/ARCHITECTURE.md`, `docs/TECH_DECISIONS.md`

## Stack

Next.js 15 + FastAPI + EventBridge/SQS/Step Functions + Postgres + OpenTelemetry + Terraform

## Commands

```bash
./scripts/setup-local.sh && make dev   # infra: Postgres (pgvector), LocalStack
make down / make logs
```

Phase 1+: `uv run uvicorn eventforge.main:app --reload` | `npm run dev`

## Architecture essentials

- Event-first (EventBridge, not agent-to-agent HTTP)
- Idempotency via `processed_events`
- DLQ: `eventforge-dlq`
- `correlation_id` for tracing + SSE + React Flow
- Cost tracking in `llm_usage`
- **Docstrings:** new Python classes get a one-line purpose docstring (see `backend-python.mdc`)

## Current phase

**Phases 0–4 complete.** **Phase 5 in progress** — AWS dev + CI/CD + Step Functions + observability ([KRE-156](https://linear.app/kreativbiro/issue/KRE-156)–[KRE-165](https://linear.app/kreativbiro/issue/KRE-165)). **Next:** cloud E2E verify, Phase 6. Index: `docs/LINEAR.md`

## User shortcuts

- _"What's next in EventForge?"_ → Linear MCP
- _"Implement KRE-xxx"_ → issue acceptance criteria
- _"Mark KRE-xxx done"_ → Linear + TASKS.md sync

## Linear

Project: [EventForge](https://linear.app/kreativbiro/project/eventforge-f35070f0931e)

## Naming

EventForge | bus: `eventforge-bus` | queues: `eventforge-{stage}` | package: `eventforge` | API: `/api/v1`
