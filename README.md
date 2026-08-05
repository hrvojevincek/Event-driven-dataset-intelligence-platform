# EventForge

**Event-driven multi-agent research platform** — submit a topic, watch a pipeline of specialized agents investigate it in parallel, and get a structured synthesis with sources.

Portfolio project focused on production event-driven patterns on AWS — idempotency, DLQ, correlation IDs, cost controls, observability — with a multi-agent research pipeline as the workload.

## Architecture (at a glance)

```mermaid
flowchart LR
    API[FastAPI API] -->|query.submitted| EB[EventBridge]
    EB --> Q1[SQS ingestion]
    Q1 --> W1[Ingestion agent]
    W1 -->|ingestion.completed| EB
    EB --> Q2[SQS embedding]
    Q2 --> W2[Embedding agent]
    W2 --> EB
    EB --> Q3[SQS knowledge]
    Q3 --> W3[Knowledge agent]
    W3 --> EB
    EB --> Q4[SQS research]
    Q4 --> W4[Research agents ×N]
    W4 --> EB
    EB --> Q5[SQS synthesis]
    Q5 --> W5[Synthesis agent]
    W5 --> DB[(Postgres + pgvector)]
    API --> DB
```

Agents communicate via **events only** (no agent-to-agent HTTP). Every event carries `correlation_id` for tracing end-to-end.

Full diagrams: [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)

---

## Stack

| Layer                    | Tech                                                                                                  |
| ------------------------ | ----------------------------------------------------------------------------------------------------- |
| **API**                  | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.0, uv                                                |
| **Workers**              | Async SQS consumers, one module per pipeline stage                                                    |
| **Events**               | AWS EventBridge + SQS (+ Step Functions for research fan-out in prod)                                 |
| **Data**                 | Postgres 16 + pgvector                                                                                |
| **LLM**                  | OpenAI + Anthropic client; Tavily search; OpenAI embeddings; RAG; cited synthesis                     |
| **Resilience**           | Exponential backoff retries, per-provider circuit breakers, optional `JOB_MAX_COST_USD`               |
| **Frontend** _(Phase 4)_ | Next.js 16, shadcn/ui, TanStack Query, React Flow, SSE ✅                                             |
| **Auth**                 | Mock user only — open API (ADR-013); no login UI                                                      |
| **Observability**        | OpenTelemetry → OTLP collector → Jaeger ✅ ([KRE-155](https://linear.app/kreativbiro/issue/KRE-155))  |
| **IaC** _(Phase 5)_      | Terraform — networking, rds, sqs, eventbridge, ecs, github-oidc                                       |
| **CI/CD** _(Phase 5)_    | GitHub Actions — lint/test on PR; OIDC deploy to ECR/ECS on `main` ([`docs/CICD.md`](./docs/CICD.md)) |
| **Local**                | Docker Compose + LocalStack                                                                           |

---

## Local dev

**Prerequisites:** Docker, Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
cp .env.example .env
./scripts/setup-local.sh    # first time
make dev                    # Postgres + LocalStack + backend + frontend + OTEL + Jaeger

cd backend && uv run alembic upgrade head   # migrations
```

| Service  | URL                        |
| -------- | -------------------------- |
| Frontend | http://localhost:3000      |
| Backend  | http://localhost:8000      |
| API docs | http://localhost:8000/docs |
| Jaeger   | http://localhost:16686     |

**Phase 3 API keys** (in `.env` — required for real ingestion → synthesis path):

```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...   # optional second provider
TAVILY_API_KEY=tvly-...        # web search (ingestion)
LLM_DEFAULT_MODEL=gpt-4o-mini
KNOWLEDGE_RAG_TOP_K=10         # optional — RAG retrieval limit
KNOWLEDGE_MAX_ENTITIES=4       # optional — caps research fan-out
JOB_MAX_COST_USD=2.0           # optional — per-job LLM spend cap (omit to disable)
```

**Hybrid (hot reload):** run infra in Docker, API + frontend natively:

```bash
docker compose up postgres localstack
cd backend && uv sync && uv run uvicorn eventforge.main:app --reload --port 8000
cd frontend && cp .env.example .env.local && npm install && npm run dev   # http://localhost:3000
```

**Workers** (required for pipeline to complete):

```bash
make workers   # all 5 workers + DLQ handler via Honcho (Procfile)
```

**Observability** (OTEL + Jaeger — included in `make dev`):

```bash
# .env
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317   # host workers
OTEL_SERVICE_NAME=eventforge

# Jaeger UI — after submitting a query + running workers
open http://localhost:16686
```

Search by **Service** (`eventforge`, `eventforge-worker-ingestion`, …) or tag `correlation_id=<from query response>`. Disable with `OTEL_ENABLED=false`.

Detail: [`docs/LOCAL_DEV.md`](./docs/LOCAL_DEV.md#observability-phase-4)

Or one terminal each:

```bash
uv run --project backend python -m eventforge.workers.ingestion
uv run --project backend python -m eventforge.workers.embedding
uv run --project backend python -m eventforge.workers.knowledge
uv run --project backend python -m eventforge.workers.research
uv run --project backend python -m eventforge.workers.synthesis
```

**Local setup (3 terminals for hybrid):** `make dev` (full stack) · or infra + `make workers` · API calls below.

Header **API ok** badge on http://localhost:3000 confirms frontend → backend health via `lib/api-client.ts`.

**Regions:** `AWS_REGION=eu-west-2` (London — prod/dev default).

**Try the API:**

```bash
# Health
curl http://localhost:8000/health

# E2E pipeline script (mock user — no auth)
./scripts/verify-pipeline-e2e.sh

curl -X POST http://localhost:8000/api/v1/queries \
  -H "Content-Type: application/json" \
  -d '{"topic": "Event-driven architecture patterns", "depth": "standard"}'

# Poll job detail (use job_id from response)
curl http://localhost:8000/api/v1/queries/{job_id}
```

OpenAPI docs: http://localhost:8000/docs

Full guide: [`docs/LOCAL_DEV.md`](./docs/LOCAL_DEV.md)

---

## AWS dev deploy

EventForge runs on **ECS Fargate** in `eu-west-2` (ALB → API + frontend, RDS, EventBridge/SQS workers).

| Item          | Value                                                                                                                 |
| ------------- | --------------------------------------------------------------------------------------------------------------------- |
| App URL       | `http://<alb_dns_name>` (from `terraform output alb_dns_name`)                                                        |
| CI/CD         | [`docs/CICD.md`](./docs/CICD.md) — set repo variable `AWS_DEPLOY_ROLE_ARN`, push to `main` or run **Deploy** workflow |
| Manual deploy | `infra/terraform/README.md` — ECR build/push + `scripts/ci/ecs-deploy-*.sh`                                           |

```bash
cd infra/terraform/environments/dev
terraform output alb_dns_name
terraform output -raw github_actions_role_arn   # → GitHub variable AWS_DEPLOY_ROLE_ARN
```

---

## Project structure

```
event-driven/
├── backend/src/eventforge/   # API, agents, workers, events, db
│   ├── core/otel.py          # OTEL setup + agent span helpers
│   ├── services/llm/         # LLM client + OpenAI/Anthropic providers
│   ├── services/embedding/   # Chunking + OpenAI embeddings
│   ├── services/knowledge/   # RAG retrieval + entity extraction
│   ├── services/research/    # Sub-query generation + note synthesis
│   ├── services/synthesis/   # Cited report generation
│   ├── services/resilience/  # Retry, circuit breaker, cost cap
│   └── services/search/      # Tavily client
├── shared/events/            # JSON Schema contracts (source of truth)
├── infra/                    # Terraform (Phase 5), LocalStack init, Docker, OTEL
│   └── terraform/            # modules/networking, rds, ecs, github-oidc, environments/dev
├── docs/                     # PRD, architecture, ADRs, roadmap, CICD, ISSUES
├── scripts/                  # setup, E2E verify, CI deploy (scripts/ci/)
└── frontend/                 # Next.js app (Phase 4)
    └── src/
        ├── app/              # /, /login, /queries/new, /queries/[id]
        ├── components/       # layout, auth, dashboard, workflow (React Flow), shadcn/ui
        ├── hooks/            # useJobStream (SSE), use-queries (TanStack Query)
        ├── lib/              # api-client, sse-client
        └── types/api.ts      # generated from OpenAPI (npm run codegen)
```

---

## Documentation

| Doc                                                  | Purpose                              |
| ---------------------------------------------------- | ------------------------------------ |
| [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)     | System design, event flows, diagrams |
| [`docs/PRD.md`](./docs/PRD.md)                       | Product vision and user stories      |
| [`docs/TASKS.md`](./docs/TASKS.md)                   | Phase roadmap and checkboxes         |
| [`docs/TECH_DECISIONS.md`](./docs/TECH_DECISIONS.md) | ADRs (Tavily, pgvector, SSE, etc.)   |
| [`docs/LOCAL_DEV.md`](./docs/LOCAL_DEV.md)           | Troubleshooting and worker setup     |
| [`docs/CICD.md`](./docs/CICD.md)                     | GitHub Actions deploy setup          |
| [`docs/ISSUES.md`](./docs/ISSUES.md)                 | Problems solved (STAR postmortems)   |

For Cursor agents: [AGENTS.md](./AGENTS.md) · [`.cursor/rules/`](./.cursor/rules/)

---

## License

MIT — portfolio project.
