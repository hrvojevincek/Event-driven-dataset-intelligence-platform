# EventForge — Technology Decisions (ADRs)

> **Cursor agents:** Consult before changing stack. Summary in `.cursor/rules/eventforge-core.mdc`. Update this file when making new architectural decisions.

Architecture Decision Records documenting key choices, trade-offs, and rationale.

**Format:** Status · Date · Decision

---

## ADR-001: Hybrid Stack — Next.js Frontend + FastAPI Backend

**Status:** Accepted  
**Date:** 2025-06-20

### Context

Need a portfolio project demonstrating both polished UX and robust backend/agent engineering.

### Decision

- **Frontend:** Next.js 15 (App Router, TypeScript)
- **Backend:** Python FastAPI

### Rationale

| Factor                 | Next.js                           | FastAPI                                   |
| ---------------------- | --------------------------------- | ----------------------------------------- |
| React Flow integration | Native                            | N/A                                       |
| shadcn/ui ecosystem    | Excellent                         | N/A                                       |
| LLM / ML libraries     | Limited                           | Rich (LangChain, LlamaIndex, native SDKs) |
| Async workers          | Node can, but Python dominates AI | First-class                               |
| Type safety            | TypeScript                        | Pydantic v2                               |
| Hiring signal          | Full-stack UX                     | Backend / ML engineering                  |

### Trade-offs

- Two runtimes to deploy and maintain
- Shared types require OpenAPI codegen pipeline
- Slightly more complex local dev (mitigated by Docker Compose)

### Alternatives Considered

- **Full Next.js** — API routes + BullMQ workers. Rejected: weaker Python AI ecosystem.
- **Full Python (Django + HTMX)** — Rejected: weaker portfolio UX impact, no React Flow.
- **T3 stack** — Rejected: doesn't showcase Python backend skills.

---

## ADR-002: AWS EventBridge + SQS + Step Functions

**Status:** Accepted  
**Date:** 2025-06-20

### Context

Pipeline has 5+ stages with parallel research fan-out. Need decoupling, retries, and observability.

### Decision

- **EventBridge** — event routing and audit log
- **SQS** — per-stage worker queues with DLQ
- **Step Functions** — research fan-out orchestration (Map state)

### Rationale

- Industry-standard serverless event patterns
- Independent scaling per queue
- DLQ built into SQS
- Step Functions Map state handles parallel research cleanly
- Strong portfolio signal for cloud-native architecture

### Trade-offs

- LocalStack emulation is imperfect (especially Step Functions)
- More IaC complexity than a monolithic job queue
- Eventual consistency between stages

### Alternatives Considered

| Option                | Pros                                       | Cons                                         | Verdict                          |
| --------------------- | ------------------------------------------ | -------------------------------------------- | -------------------------------- |
| **Temporal**          | Excellent durability, code-first workflows | Extra infrastructure, steeper learning curve | Future migration path (ADR-008)  |
| **Celery + Redis**    | Simple local dev                           | Not cloud-native, weaker portfolio signal    | Rejected for prod                |
| **Pure SQS chaining** | Simpler                                    | No native fan-out/wait                       | Rejected; SF needed for research |
| **Kafka**             | High throughput                            | Overkill for MVP, ops burden                 | Rejected                         |

---

## ADR-003: Postgres + pgvector (Single Store)

**Status:** Accepted (revised 2026-06-21)  
**Date:** 2025-06-20

### Context

Need relational metadata (users, jobs, costs) and vector similarity search for RAG.

### Decision

- **Postgres 16 with pgvector** — primary OLTP store and vector similarity search (RDS in prod)

### Rationale

- Single database simplifies local dev and operations
- pgvector provides sufficient ANN search for MVP scale with filtering by `job_id`
- ACID transactions across metadata and vectors in one store
- One fewer service in Docker Compose

### Trade-offs

- ANN performance below dedicated vector DBs at very large scale
- HNSW index tuning may be needed as corpus grows

### Alternatives Considered

| Option                           | Pros                        | Cons                          | Verdict                            |
| -------------------------------- | --------------------------- | ----------------------------- | ---------------------------------- |
| **Qdrant**                       | Fast ANN, payload filtering | Extra service, dual-store ops | Rejected for MVP; revisit at scale |
| **Pinecone / managed vector DB** | Zero ops, fast search       | Vendor lock-in, cost          | Deferred                           |

### Implementation

- Enable `vector` extension via Alembic migration
- Store document chunks + embeddings in Postgres (e.g. `document_chunks` table)
- Abstract vector access behind `VectorStoreProtocol` in backend for future migration if needed

---

## ADR-004: AWS Cognito for Authentication

**Status:** Superseded by [ADR-013](#adr-013-no-authentication-mvp)  
**Date:** 2025-06-20 · **Revised:** 2026-06-29 · **Superseded:** 2026-07-01

### Context

Need auth without building identity from scratch. FastAPI validates JWTs. Production deploys to AWS (EventBridge, SQS, ECS, RDS) — Cognito keeps identity in the same cloud footprint as the rest of the stack.

### Decision (historical)

Use **AWS Cognito User Pools** for authentication; FastAPI validates Cognito JWT (ID token) via JWKS. Next.js uses Cognito Hosted UI or Amplify Auth in Phase 4; Terraform `modules/cognito` in Phase 5.

### Superseded

Removed in favor of an open API with a single mock user to unblock cloud E2E and keep portfolio focus on the event pipeline. See ADR-013.

---

## ADR-005: OpenTelemetry for Observability

**Status:** Accepted  
**Date:** 2025-06-20

### Decision

Instrument all services with **OpenTelemetry** SDK; export via OTLP to collector.

### Rationale

- Vendor-neutral; works locally and on AWS (ADOT)
- Distributed tracing across agents is a core portfolio feature
- Correlate traces with `correlation_id` and `job_id` attributes

### Implementation Notes

- Python: `opentelemetry-instrumentation-fastapi`, custom spans in agents
- Next.js: `@opentelemetry/sdk` (Phase 4)
- Collector → Grafana Cloud free tier or AWS X-Ray

---

## ADR-006: Terraform for Infrastructure as Code

**Status:** Accepted  
**Date:** 2025-06-20

### Decision

Use **Terraform** with modular structure (`infra/terraform/modules/`). Default AWS region: **`eu-west-2` (London)** for dev and prod environments.

### Rationale

- Industry standard, portable skill
- Clear module boundaries: networking, RDS, SQS, EventBridge, ECS, IAM
- Works well in portfolio README

### Alternatives

- **AWS CDK** — great for TypeScript teams; we're Python-primary on backend
- **Pulumi** — viable; smaller community for AWS examples
- **Serverless Framework** — too narrow for ECS + RDS

### Structure

```
infra/terraform/
├── environments/dev/
├── environments/prod/
└── modules/{networking,rds,eventbridge,sqs,step-functions,ecs,observability}
```

---

## ADR-007: Docker Compose for Local Development

**Status:** Accepted  
**Date:** 2025-06-20

### Decision

Docker Compose orchestrates Postgres (with pgvector), LocalStack locally. Backend and frontend can run natively or in Compose.

### Rationale

- One command (`make dev`) for infrastructure dependencies
- LocalStack approximates AWS events locally
- Matches production service topology

### Limitations

- LocalStack Step Functions support is limited — may use simplified fan-out locally
- Document workarounds in `docs/LOCAL_DEV.md`

---

## ADR-008: Temporal as Future Migration Path

**Status:** Proposed (not implemented)  
**Date:** 2025-06-20

### Context

If Step Functions + EventBridge complexity grows (human-in-the-loop, long-running sagas, complex compensation).

### Proposal

Migrate orchestration to **Temporal** on AWS (Temporal Cloud or self-hosted ECS).

### Trigger Conditions

- Need durable timers > 1 year
- Complex saga compensation logic
- Step Functions cost or expressiveness limits hit
- Want code-first workflows with full testability

### Migration Strategy

- Keep event schemas in `shared/events/`
- Replace Step Functions with Temporal workflows
- Workers become Temporal activities
- EventBridge remains for external integrations

---

## ADR-009: Tavily for Web Search Ingestion

**Status:** Accepted (MVP)  
**Date:** 2025-06-20

### Decision

Use **Tavily API** for research-focused web search during ingestion.

### Rationale

- Built for AI/RAG pipelines
- Simple API, good relevance
- Alternative: SerpAPI (broader but more expensive)

---

## ADR-010: SSE for Real-Time UI Updates

**Status:** Accepted (MVP)  
**Date:** 2025-06-20

### Decision

Use **Server-Sent Events** from FastAPI for pipeline status streaming.

### Rationale

- Unidirectional (server → client) is sufficient
- Simpler than WebSocket; works through most proxies
- FastAPI `EventSourceResponse` is well-supported

### Revisit If

- Bidirectional client → server signaling needed during pipeline
- Multiple event types with binary payloads required

---

## ADR-011: LLM Cost Tracking

**Status:** Accepted  
**Date:** 2025-06-20

### Decision

Log every LLM call to `llm_usage` table: `job_id`, `agent_name`, `model`, `input_tokens`, `output_tokens`, `cost_usd`.

### Rationale

- Cost awareness is a production differentiator
- Enables per-user budgets and portfolio demo of FinOps thinking
- Calculate cost from published model pricing in config (not hardcoded in agents)

---

## ADR-012: All-in-AWS Deployment on ECS Fargate

**Status:** Accepted  
**Date:** 2026-06-30

### Context

Phase 5 deploys EventForge from a **monorepo** (`backend/`, `frontend/`, `infra/`) to AWS. Frontend hosting options were Vercel (split cloud) vs all-in-AWS. The stack targets EventBridge, SQS, and RDS in **`eu-west-2`**.

### Decision

Deploy **all runtime services on AWS ECS Fargate** in a single VPC:

| Monorepo path      | Artifact                              | ECS services                                      |
| ------------------ | ------------------------------------- | ------------------------------------------------- |
| `backend/`         | One ECR image (`eventforge-backend`)  | API + 6 workers (same image, different `command`) |
| `frontend/`        | One ECR image (`eventforge-frontend`) | Next.js standalone                                |
| `shared/events/`   | Bundled in backend image              | —                                                 |
| `infra/terraform/` | Terraform apply                       | VPC, ALB, RDS, queues, etc.                       |

**Routing:** One ALB — `/api/*` and `/health*` → API target group; default → frontend.

**Networking:** Public subnets (ALB only); private subnets (ECS tasks, RDS); NAT gateway for worker egress (Tavily, OpenAI).

**Secrets:** AWS Secrets Manager for DB password and API keys; injected into ECS task definitions (not in tfvars).

**Migrations:** Alembic runs in API container entrypoint on deploy (same as local `docker-entrypoint.sh`). Workers override entrypoint to skip migrations.

**CI/CD:** Path-filtered GitHub Actions — `backend/**` → ECR → ECS rolling update; `frontend/**` → ECR → ECS; `infra/terraform/**` → plan/apply.

### Rationale

- Single cloud footprint aligns with EventBridge and portfolio “AWS-native” story
- Reuses existing Dockerfiles; local Compose topology maps 1:1 to ECS services
- One backend image keeps worker deploys simple (shared code, per-service IAM still scoped by queue)
- ALB idle timeout configurable for SSE (≥ 300s)

### Trade-offs

- More ops than Vercel for frontend (ALB, TLS, scaling)
- NAT gateway cost in dev (~$32/mo per AZ; mitigated with `single_nat_gateway = true`)
- Build-time `NEXT_PUBLIC_*` vars require CI to pass API URL at image build

### Alternatives Considered

| Option                   | Pros                   | Cons                               | Verdict                       |
| ------------------------ | ---------------------- | ---------------------------------- | ----------------------------- |
| **Vercel + AWS backend** | Fastest Next.js deploy | Split hosting                      | Rejected — user chose all-AWS |
| **Lambda for workers**   | Pay per invoke         | Long-poll SQS awkward; cold starts | Rejected for MVP              |
| **EKS**                  | Full Kubernetes        | Overkill for portfolio MVP         | Rejected                      |

### Terraform module order

1. `networking` — VPC, subnets, NAT, security groups
2. `ecs` — cluster, ECR, ALB, task definitions, services
3. `rds`, `sqs`, `eventbridge`, `step-functions`, `observability` — subsequent PRs
4. `environments/dev` — composes modules in `eu-west-2`

### Environment matrix (local → AWS)

| Variable                      | Local                    | AWS dev                                               |
| ----------------------------- | ------------------------ | ----------------------------------------------------- |
| `AWS_ENDPOINT_URL`            | `http://localstack:4566` | unset                                                 |
| `POSTGRES_HOST`               | `localhost` / `postgres` | RDS endpoint (from `modules/rds`)                     |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | local collector          | ADOT sidecar / Grafana (Phase 5 observability module) |
| `CORS_ORIGINS`                | `http://localhost:3000`  | `https://app.<domain>`                                |

See `infra/terraform/environments/dev/terraform.tfvars.example` for full ECS env wiring.

---

## ADR-013: No Authentication (MVP)

**Status:** Accepted (supersedes ADR-004)  
**Date:** 2026-07-01

### Context

Cognito (ADR-004) added Hosted UI, Amplify, JWT validation, and Terraform complexity. Cloud E2E verification was blocked on auth wiring while local dev already ran with a mock user. The portfolio goal is the event-driven research pipeline, not identity.

### Decision

**No authentication** for MVP/local and AWS dev:

- FastAPI `get_current_user` always resolves a single mock user (`mock-local-user`).
- Jobs remain scoped by `user_id` in Postgres (schema unchanged).
- Frontend calls the API with no `Authorization` header.
- Terraform `modules/cognito` removed; no Cognito env vars in ECS or CI.

### Rationale

- Unblocks cloud E2E with the same code path as local Docker.
- Removes Amplify, JWKS, OAuth redirect, and dual `AUTH_DISABLED` modes.
- Keeps a hook for future auth via `users.auth_subject_id` without shipping identity now.

### Security (explicit non-goal)

The dev ALB exposes an **open API** — anyone with the URL can submit queries and read jobs for the mock user. Acceptable for portfolio/demo only; production would require auth (Cognito or alternative) before multi-tenant or public exposure.

### Alternatives considered

- **Keep Cognito** — rejected; cost/complexity outweighed benefit for current milestone.
- **Lightweight ALB secret header** — rejected; still another auth layer to operate.
- **Drop `users` table** — rejected; larger migration for little gain while single-user anyway.

---

## ADR-014: Pivot to Dataset Intelligence Platform

**Status:** Accepted  
**Date:** 2026-08-04

### Context

The research/RAG pipeline (Tavily ingestion → pgvector embedding → entity extraction → parallel web research → markdown synthesis) delivered weak AI value relative to infrastructure complexity. Embeddings were computed over Tavily snippets, not full documents; RAG retrieval duplicated what Tavily follow-up already did.

The event-driven architecture (EventBridge, SQS, Step Functions, idempotency, OTEL, SSE) remains a strong portfolio asset. The **workload** should change to match a real industry pattern: **dataset intelligence extraction** (cf. BeatPulse Labs — custom annotation pipelines for enterprise AI training data).

### Decision

Pivot EventForge from a **research Q&A platform** to a **dataset intelligence platform**:

- **Input:** Uploaded assets (documents v1) + user-defined annotation schema
- **Output:** Model-ready JSONL + QC report
- **Pipeline:** Intake → Preprocessing → Planning → Parallel Annotation → Export
- **Keep:** EventBridge + SQS + Step Functions, workers, React Flow, cost tracking, Terraform ECS stack
- **Remove:** Tavily, pgvector/RAG, research synthesis, query/topic model

v1 domain: **documents** (txt, md, pdf). LLM pre-labeling for MVP; HITL review deferred to v2.

### Rationale

| Factor | Research (old) | Dataset (new) |
| ------ | -------------- | ------------- |
| Distributed infra justification | Weak — RAG is synchronous-friendly | Strong — parallel annotation at scale |
| AI value | Redundant web search + thin RAG | Structured labeling with provenance |
| Portfolio story | "Multi-agent research" (oversold) | Event-driven data pipeline (accurate) |
| Industry alignment | Generic chatbot pattern | BeatPulse / Scale / Snorkel pattern |
| Complexity | pgvector + Tavily + 5 LLM stages | Postgres OLTP + 3 LLM stages |

### Trade-offs

- Breaking change — legacy research flow removed in place (not parallel product)
- `docs/ARCHITECTURE.md` and `docs/PRD.md` lag until Phase 10
- Physical SQS queue names may stay legacy until Phase 9 (cosmetic)

### Alternatives considered

- **Keep research, simplify to single RAG call** — rejected; still wrong product, keeps pgvector
- **Full rewrite (new repo)** — rejected; reuse infra, frontend, worker patterns
- **DataForge rebrand** — deferred; keep EventForge name (events still core)

### References

- `docs/DATASET_PLATFORM.md` — target product
- `docs/PIVOT_PLAN.md` — phased implementation checklist
- `.cursor/rules/dataset-pivot.mdc` — agent conventions during pivot

### Supersedes / revises

- **ADR-003** (Postgres + pgvector) — pgvector dropped; Postgres OLTP only
- **ADR-009** (Tavily) — superseded for ingestion; web search removed from pipeline

---

## ADR-015: Local-Only Scope (No AWS Deploy)

**Status:** Accepted  
**Date:** 2026-08-05

### Context

Phase 5 built Terraform modules for ECS, RDS, EventBridge, etc. During the dataset pivot grilling session, the decision was made to **keep the event-driven worker pattern locally** (LocalStack) but **not deploy or maintain AWS infrastructure** for the pivot target.

### Decision

- **Active:** Docker Compose — Postgres + LocalStack + backend + frontend + OTEL
- **Active:** SQS workers + EventBridge + Step Functions via LocalStack init scripts
- **Inactive:** Terraform apply, ECS deploy, cloud E2E, Secrets Manager ops
- **Storage:** Local disk only (`./data/uploads/`); no S3 for pivot MVP
- **Terraform:** Keep `infra/terraform/` in repo; add README note that it is archived reference from Phase 5

### Rationale

- Portfolio demo reliability — LocalStack is enough to show event-driven patterns without AWS cost/ops
- Pivot velocity — no deploy blockers while replacing research pipeline
- Interview option — can still reference Terraform work without maintaining it

### Trade-offs

- No production deployment story for pivot MVP
- Step Functions Map state remains imperfect in LocalStack (sequential fallback)
- S3 storage backend deferred to v2

---

## ADR-016: WAV Audio Pipeline (v1)

**Status:** Accepted  
**Date:** 2026-08-06

### Decision

- **Formats:** `.wav` only for audio projects
- **Domain:** project domain `"audio"` (`Job.domain`) with `schema_template = "support_call_audio"` (shared label schema with text support calls)
- **ASR:** `faster-whisper` local default; `ASR_PROVIDER=openai` opt-in (Phase 2)
- **Offsets:** `Segment.start_offset` / `end_offset` store **milliseconds** for audio; character offsets for documents
- **Segments:** Merge/split Whisper utterances into ~15–45s windows before planning
- **Export:** Keep `content`; add `audio_uri`, `start_ms`, `end_ms` for audio domain only
- **Limits:** 5-minute max duration at intake; no diarization; LLM sees transcript text only

---

## Decision Log

| ADR | Title                              | Status               |
| --- | ---------------------------------- | -------------------- |
| 001 | Hybrid Next.js + FastAPI           | Accepted             |
| 002 | EventBridge + SQS + Step Functions | Accepted             |
| 003 | Postgres + pgvector                | Superseded (ADR-014) |
| 004 | AWS Cognito Auth                   | Superseded (ADR-013) |
| 005 | OpenTelemetry                      | Accepted             |
| 006 | Terraform IaC                      | Accepted             |
| 007 | Docker Compose Local Dev           | Accepted             |
| 008 | Temporal Migration Path            | Proposed             |
| 009 | Tavily Web Search                  | Accepted             |
| 010 | SSE Real-Time                      | Accepted             |
| 011 | LLM Cost Tracking                  | Accepted             |
| 012 | All-in-AWS ECS Fargate             | Accepted             |
| 013 | No Authentication (MVP)            | Accepted             |
| 014 | Dataset Intelligence Pivot         | Accepted             |
| 015 | Local-Only Scope (No AWS Deploy)   | Accepted             |
| 016 | WAV Audio Pipeline (v1)            | Accepted             |
