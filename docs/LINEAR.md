# EventForge — Linear Integration

> **ARCHIVED (legacy Phases 0–5):** Frozen research/AWS issue index (2026-07-01). **Active pivot work:** [`docs/PIVOT_PLAN.md`](./PIVOT_PLAN.md). Use Linear MCP for current issues when they exist.

> **Mirror (legacy):** `docs/TASKS.md` checkboxes + `KRE-xxx` links

## Workspace

| Item    | Value                                                                        |
| ------- | ---------------------------------------------------------------------------- |
| Team    | `Kreativbiro` (key: `KRE`)                                                   |
| Project | [EventForge](https://linear.app/kreativbiro/project/eventforge-f35070f0931e) |
| Target  | Phase 5 AWS deployment                                                       |

## Latest progress (2026-07-01)

**Phase 5 nearly complete** — Step Functions + observability landed; cloud E2E verify next.

| Done (Phase 5)                                                                                                                                             | Next                 |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- |
| [KRE-156](https://linear.app/kreativbiro/issue/KRE-156) … [KRE-161](https://linear.app/kreativbiro/issue/KRE-161) Terraform modules (networking → cognito) | **Cloud E2E verify** |
| [KRE-162](https://linear.app/kreativbiro/issue/KRE-162) ECS runtime, Cognito OAuth, SSE keepalives                                                         | **Phase 6 polish**   |
| [KRE-163](https://linear.app/kreativbiro/issue/KRE-163) GitHub Actions CI/CD — OIDC, ECR, ECS                                                              |                      |
| [KRE-164](https://linear.app/kreativbiro/issue/KRE-164) Step Functions research fan-out                                                                    |                      |
| [KRE-165](https://linear.app/kreativbiro/issue/KRE-165) Observability — ADOT, X-Ray, alarms                                                                |                      |

**Phase 4 complete** — [KRE-155](https://linear.app/kreativbiro/issue/KRE-155) local OTEL (SDK, collector, Jaeger).

| Done (Phase 4)                                        |
| ----------------------------------------------------- |
| KRE-119 Next.js + Tailwind + shadcn                   |
| KRE-121 layout + placeholder pages                    |
| KRE-124 API client + Dockerfile + compose             |
| KRE-126 OpenAPI → TypeScript codegen                  |
| KRE-128 full-stack smoke test (`verify-fullstack.sh`) |
| KRE-151 SSE + `useJobStream`                          |
| KRE-152 React Flow pipeline visualization             |
| KRE-153 Dashboard UI + TanStack Query                 |
| KRE-154 Cognito UI (Amplify Auth)                     |
| KRE-155 OTEL local — SDK, collector, Jaeger           |

**Phase 3 complete** — real AI pipeline + Cognito JWT auth verified end-to-end.

Phases 0–3 complete. Full pipeline runs locally with real AI, cited synthesis, and authenticated API. Frontend at http://localhost:3000 with live API health badge.

## Agent workflow (Cursor + Linear MCP)

1. **Start session:** `list_issues` with `project: EventForge` (or `get_issue` for a specific `KRE-xxx`)
2. **Pick work:** Prefer unblocked issues in current milestone; respect `blockedBy`
3. **Implement:** Use acceptance criteria from issue description + `.cursor/rules/`
4. **On complete:** Mark issue Done in Linear + check box in `docs/TASKS.md`

### MCP commands

```
list_issues(project: "EventForge")
get_issue(id: "KRE-122")
save_issue(id: "KRE-122", state: "Done")
```

## Milestones

| Milestone               | Status                                                                                                            |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Phase 0 — Foundation    | Complete                                                                                                          |
| Phase 1 — Scaffolding   | Backend complete; frontend → Phase 4                                                                              |
| Phase 2 — Core Pipeline | Complete (stub agents + E2E)                                                                                      |
| Phase 3 — Real AI       | **Complete** — KRE-139–147 (real agents + Cognito auth + resilience)                                              |
| Phase 4 — Frontend      | **Complete** — KRE-151–155 ✅                                                                                     |
| Phase 5 — AWS Deploy    | **Nearly complete** — Terraform + CI/CD + Step Functions + observability (KRE-156–KRE-165); cloud E2E verify next |

## Issue index (Phase 0 + 1)

| ID     | Linear                                                  | Title                                               | Estimate | Blocked by                                  |
| ------ | ------------------------------------------------------- | --------------------------------------------------- | -------- | ------------------------------------------- |
| EF-001 | [KRE-117](https://linear.app/kreativbiro/issue/KRE-117) | Close Phase 0 — git init + docker verify            | 2        | —                                           |
| EF-002 | [KRE-118](https://linear.app/kreativbiro/issue/KRE-118) | Backend project init — uv + package layout          | 2        | KRE-117                                     |
| EF-003 | [KRE-120](https://linear.app/kreativbiro/issue/KRE-120) | FastAPI app + health endpoints                      | 2        | KRE-118                                     |
| EF-004 | [KRE-123](https://linear.app/kreativbiro/issue/KRE-123) | DB layer — SQLAlchemy, Alembic, core models         | 3        | KRE-120                                     |
| EF-005 | [KRE-125](https://linear.app/kreativbiro/issue/KRE-125) | Config, logging, Dockerfile, compose wiring         | 3        | KRE-123                                     |
| EF-006 | [KRE-119](https://linear.app/kreativbiro/issue/KRE-119) | Frontend init — Next.js 15, Tailwind, shadcn        | 3        | KRE-117                                     |
| EF-007 | [KRE-121](https://linear.app/kreativbiro/issue/KRE-121) | Frontend layout + placeholder pages                 | 3        | KRE-119                                     |
| EF-008 | [KRE-124](https://linear.app/kreativbiro/issue/KRE-124) | Frontend API client + Dockerfile + compose          | 2        | KRE-121                                     |
| EF-009 | [KRE-126](https://linear.app/kreativbiro/issue/KRE-126) | OpenAPI generation + TypeScript codegen             | 2        | KRE-120, KRE-124                            |
| EF-010 | [KRE-122](https://linear.app/kreativbiro/issue/KRE-122) | Event envelope + query.submitted schemas (mini-122) | 1        | KRE-118                                     |
| EF-011 | [KRE-127](https://linear.app/kreativbiro/issue/KRE-127) | CI stub — lint workflow                             | 1        | KRE-125 (backend); KRE-124 (eslint)         |
| EF-012 | [KRE-128](https://linear.app/kreativbiro/issue/KRE-128) | Phase 1 integration smoke test                      | 2        | KRE-125, KRE-124, KRE-126, KRE-122, KRE-127 |

## Issue index (Phase 2 — vertical slices)

| ID     | Linear                                                  | Title                                                 | Estimate | Blocked by |
| ------ | ------------------------------------------------------- | ----------------------------------------------------- | -------- | ---------- |
| EF-013 | [KRE-129](https://linear.app/kreativbiro/issue/KRE-129) | Query API + EventBridge publisher + idempotency       | 3        | KRE-122    |
| EF-014 | [KRE-130](https://linear.app/kreativbiro/issue/KRE-130) | SQS consumer base + ingestion stub worker             | 3        | KRE-129    |
| EF-015 | [KRE-131](https://linear.app/kreativbiro/issue/KRE-131) | Harden pipeline idempotency (atomic claim + API keys) | 2        | KRE-130    |
| EF-016 | [KRE-132](https://linear.app/kreativbiro/issue/KRE-132) | Re-verify deferred ingestion/worker review findings   | —        | KRE-131    |
| EF-017 | [KRE-133](https://linear.app/kreativbiro/issue/KRE-133) | Automated RAG eval (faithfulness, citations, RAGAS)   | 3        | Phase 3    |
| EF-018 | [KRE-134](https://linear.app/kreativbiro/issue/KRE-134) | SQS DLQ redrive policies (LocalStack)                 | 1        | E2E done   |
| EF-019 | [KRE-135](https://linear.app/kreativbiro/issue/KRE-135) | pipeline.failed schema + DLQ terminal failure         | 2        | KRE-134    |

## Issue index (Deferred — revisit after backend complete)

| ID     | Linear                                                  | Title                                      | Priority | When      |
| ------ | ------------------------------------------------------- | ------------------------------------------ | -------- | --------- |
| EF-020 | [KRE-136](https://linear.app/kreativbiro/issue/KRE-136) | Transactional outbox for event publishing  | Medium   | Phase 3/5 |
| EF-021 | [KRE-137](https://linear.app/kreativbiro/issue/KRE-137) | LocalStack full `SQS_QUEUE_PREFIX` support | Low      | Pre-AWS   |
| EF-022 | [KRE-138](https://linear.app/kreativbiro/issue/KRE-138) | DLQ poison-pill observability + archive    | Low      | Phase 4/6 |

> Remaining Phase 2 polish (`GET /queries` list) stays in `docs/TASKS.md`. **Stage event schemas are added incrementally with each worker** — not upfront in KRE-122.

## Issue index (Phase 3 — real AI & auth)

| ID     | Linear                                                  | Title                                             | Estimate | Blocked by |
| ------ | ------------------------------------------------------- | ------------------------------------------------- | -------- | ---------- |
| EF-023 | [KRE-139](https://linear.app/kreativbiro/issue/KRE-139) | LLM client + cost tracking foundation             | 3        | —          |
| EF-024 | [KRE-140](https://linear.app/kreativbiro/issue/KRE-140) | Tavily web search ingestion                       | 3        | KRE-139    |
| EF-025 | [KRE-141](https://linear.app/kreativbiro/issue/KRE-141) | Real embedding — chunking + OpenAI embeddings     | 3        | KRE-140    |
| EF-026 | [KRE-143](https://linear.app/kreativbiro/issue/KRE-143) | Knowledge mining — RAG + entity extraction        | 3        | KRE-141    |
| EF-027 | [KRE-142](https://linear.app/kreativbiro/issue/KRE-142) | Research — LLM parallel sub-queries               | 3        | KRE-143    |
| EF-028 | [KRE-144](https://linear.app/kreativbiro/issue/KRE-144) | Synthesis — cited report generation               | 3        | KRE-142    |
| EF-029 | [KRE-145](https://linear.app/kreativbiro/issue/KRE-145) | LLM cost tracking API endpoint                    | 2        | KRE-139    |
| EF-030 | [KRE-146](https://linear.app/kreativbiro/issue/KRE-146) | Backend Cognito JWT auth + user-scoped queries    | 3        | —          |
| EF-031 | [KRE-147](https://linear.app/kreativbiro/issue/KRE-147) | LLM resilience — retry, circuit breaker, cost cap | 3        | KRE-139    |

## Issue index (Post-Phase 3 — revisit after cited synthesis E2E)

> Pick up **after KRE-144** (real pipeline working). Umbrella: [KRE-150](https://linear.app/kreativbiro/issue/KRE-150).

| ID     | Linear                                                  | Title                                               | Priority | Blocked by |
| ------ | ------------------------------------------------------- | --------------------------------------------------- | -------- | ---------- |
| EF-032 | [KRE-148](https://linear.app/kreativbiro/issue/KRE-148) | Revisit chunking — semantic / structure-aware RAG   | Low      | KRE-144    |
| EF-033 | [KRE-149](https://linear.app/kreativbiro/issue/KRE-149) | Ingestion — Tavily raw content / Extract            | Low      | KRE-144    |
| EF-034 | [KRE-150](https://linear.app/kreativbiro/issue/KRE-150) | Post-Phase 3 quality pass (agents, API, resilience) | Medium   | KRE-144    |
| EF-017 | [KRE-133](https://linear.app/kreativbiro/issue/KRE-133) | Automated RAG eval (faithfulness, citations, RAGAS) | Low      | KRE-144    |

Also see deferred infra/reliability: KRE-136 (outbox), KRE-137, KRE-138.

## Issue index (Phase 4 — frontend & real-time)

| ID     | Linear                                                  | Title                                                 | Estimate | Blocked by |
| ------ | ------------------------------------------------------- | ----------------------------------------------------- | -------- | ---------- |
| EF-035 | [KRE-151](https://linear.app/kreativbiro/issue/KRE-151) | SSE pipeline stream + `useJobStream` hook (Phase 4.1) | 5        | KRE-128    |
| EF-036 | [KRE-152](https://linear.app/kreativbiro/issue/KRE-152) | React Flow pipeline visualization (Phase 4.2)         | 5        | KRE-151    |
| EF-037 | [KRE-153](https://linear.app/kreativbiro/issue/KRE-153) | Dashboard UI — submit, history, synthesis (Phase 4.3) | 5        | KRE-152    |
| EF-038 | [KRE-154](https://linear.app/kreativbiro/issue/KRE-154) | Cognito UI — Amplify Auth, Bearer token (Phase 4.4)   | 5        | KRE-153    |
| EF-039 | [KRE-155](https://linear.app/kreativbiro/issue/KRE-155) | Local OTEL — SDK, collector, Jaeger (Phase 4.5)       | 5        | KRE-154    |

## Issue index (Phase 5 — AWS deployment)

| ID     | Linear                                                  | Title                                                   | Estimate | Blocked by |
| ------ | ------------------------------------------------------- | ------------------------------------------------------- | -------- | ---------- |
| EF-040 | [KRE-156](https://linear.app/kreativbiro/issue/KRE-156) | Terraform `modules/networking` — VPC, NAT, SG           | —        | —          |
| EF-041 | [KRE-157](https://linear.app/kreativbiro/issue/KRE-157) | Terraform `modules/ecs` — ECR, ALB, Fargate services    | —        | KRE-156    |
| EF-042 | [KRE-158](https://linear.app/kreativbiro/issue/KRE-158) | Terraform `modules/rds` — Postgres 16, backups, SM pwd  | —        | KRE-156    |
| EF-043 | [KRE-159](https://linear.app/kreativbiro/issue/KRE-159) | Terraform `modules/sqs` — worker queues, DLQ, redrive   | —        | —          |
| EF-044 | [KRE-160](https://linear.app/kreativbiro/issue/KRE-160) | Terraform `modules/eventbridge` — bus + stage rules     | —        | KRE-159    |
| EF-045 | [KRE-161](https://linear.app/kreativbiro/issue/KRE-161) | Terraform `modules/cognito` — pool, client, Hosted UI   | —        | —          |
| EF-046 | [KRE-162](https://linear.app/kreativbiro/issue/KRE-162) | AWS deploy hardening — ECS runtime, Cognito OAuth, SSE  | —        | KRE-157    |
| EF-047 | [KRE-163](https://linear.app/kreativbiro/issue/KRE-163) | GitHub Actions CI/CD — OIDC, ECR deploy, Terraform      | —        | KRE-162    |
| EF-048 | [KRE-164](https://linear.app/kreativbiro/issue/KRE-164) | Terraform `modules/step-functions` — research fan-out   | —        | KRE-160    |
| EF-049 | [KRE-165](https://linear.app/kreativbiro/issue/KRE-165) | Terraform `modules/observability` — ADOT, X-Ray, alarms | —        | KRE-162    |

> **Next:** Cloud E2E verify on AWS dev, then Phase 6 polish.

## Backend-first track (recommended)

```
Done:   KRE-118 → KRE-120 → KRE-123 → KRE-125 → KRE-122 → KRE-129 → KRE-130 → KRE-131 → KRE-132
        + all stub workers + E2E smoke test + KRE-134 (DLQ redrive) + KRE-135 (pipeline.failed)

Done:   KRE-139 (LLM client + cost tracking foundation)
        KRE-140 (Tavily web search ingestion)
        KRE-141 (real embeddings — chunking + OpenAI)
        KRE-143 (knowledge mining — RAG + entity extraction)
        KRE-142 (research — LLM parallel sub-queries)
        KRE-144 (synthesis — cited report generation)
        KRE-145 (LLM cost tracking API)
        KRE-146 (Cognito JWT auth + user-scoped queries)
        KRE-147 (LLM resilience — retry, circuit breaker, cost cap)

Next:   Phase 5 AWS deployment (in progress)
        Done: KRE-156–163 ✅ Terraform, AWS dev, CI/CD
        Next: cloud E2E verify → Phase 6

Optional: KRE-150 umbrella → KRE-148 chunking, KRE-149 richer ingestion, KRE-133 RAG eval (+ KRE-136/137/138)

Parallel (optional): pytest in CI (commented in ci.yml)
```

## Parallel tracks (original Phase 1)

```
Track A (backend): KRE-118 → KRE-120 → KRE-123 → KRE-125 → KRE-127
Track B (frontend): KRE-119 → KRE-121 → KRE-124 → KRE-127
Parallel: KRE-122 (after KRE-118), KRE-126 (after KRE-120 + KRE-124)
Finish: KRE-128
```

## Labels

`phase-0`, `phase-1`, `phase-2`, `backend`, `frontend`, `infra`, `docs`, `workflows`, `agents`, `observability`, `Feature`

## User shortcuts

| Say this                     | Agent does                             |
| ---------------------------- | -------------------------------------- |
| "What's next in EventForge?" | `list_issues` → suggest unblocked work |
| "Implement KRE-122"          | Mini-122 schemas + Pydantic mirror     |
| "Implement KRE-129"          | Query API + EventBridge publisher      |
| "Mark KRE-117 done"          | Close in Linear + update TASKS.md      |

## Grill-me decisions (2025-06-20)

- Scope: Phase 0 + Phase 1 only (~12 grouped issues)
- Linear = active source; TASKS.md = mirror
- New EventForge project on Kreativbiro
- Backend: `uv`
- Phase 1 includes lint-only CI stub

## Plan revision (2026-06-21)

- **Mini-122:** KRE-122 scoped to envelope + `query.submitted` only (1 pt)
- **Backend-first:** Phase 2 vertical slices (KRE-129, KRE-130) may start before Phase 1 frontend exit
- **Incremental schemas:** remaining pipeline events defined when each worker is built
- Phase 1 exit (KRE-128) moved to Phase 4 — do not block pipeline work on frontend

## Plan revision (2026-06-23)

- **Phase 3 ↔ Phase 4 swap:** Real AI agents + backend auth now Phase 3; frontend + SSE/React Flow now Phase 4
- **Frontend deferred:** KRE-119 through KRE-128 move to Phase 4 milestone; test backend via Postman until then
