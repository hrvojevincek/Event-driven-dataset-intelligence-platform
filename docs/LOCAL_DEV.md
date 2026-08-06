# EventForge — Local Development Guide

> **Cursor agents:** Quick commands in `.cursor/rules/eventforge-core.mdc`. Infra details in `.cursor/rules/infra-aws.mdc`. This doc is full troubleshooting reference.

How to run EventForge locally using Docker Compose, LocalStack, and native dev servers.

---

## Prerequisites

| Tool             | Version | Purpose                                        |
| ---------------- | ------- | ---------------------------------------------- |
| Docker Desktop   | 4.x+    | Containers for Postgres (pgvector), LocalStack |
| Node.js          | 20 LTS  | Frontend dev server                            |
| Python           | 3.12+   | Backend dev server                             |
| uv (recommended) | latest  | Python package management                      |
| AWS CLI          | 2.x     | Optional: inspect LocalStack resources         |
| Make             | any     | Convenience commands                           |

---

## Quick Start (Infrastructure Only — Phase 0)

```bash
# 1. Clone and enter repo
cd event-driven

# 2. One-time setup
./scripts/setup-local.sh

# 3. Start infrastructure services
make dev
```

This starts:

- **Postgres** (with pgvector) on `localhost:5432`
- **LocalStack** on `localhost:4566` (EventBridge, SQS, Step Functions, S3)

### Verify Services

```bash
# Postgres (includes pgvector extension)
docker compose exec postgres pg_isready -U eventforge

# LocalStack
curl http://localhost:4566/_localstack/health

# EventBridge bus (after init)
aws --endpoint-url=http://localhost:4566 events list-event-buses --region eu-west-2

# SQS queues
aws --endpoint-url=http://localhost:4566 sqs list-queues --region eu-west-2
```

Stop with `make down` or `docker compose down`.

---

## Environment Variables

```bash
cp .env.example .env
```

Key local values (defaults work for Docker Compose):

| Variable                | Local Value                                       |
| ----------------------- | ------------------------------------------------- |
| `POSTGRES_HOST`         | `localhost` (or `postgres` inside Docker network) |
| `AWS_ENDPOINT_URL`      | `http://localhost:4566`                           |
| `AWS_REGION`            | `eu-west-2` (London — prod default)               |
| `AWS_ACCESS_KEY_ID`     | `test`                                            |
| `AWS_SECRET_ACCESS_KEY` | `test`                                            |
| `NEXT_PUBLIC_API_URL`   | `http://localhost:8000`                           |
| `ASR_PROVIDER`          | `local` (default) or `openai`                     |
| `ASR_LOCAL_MODEL`       | `small` (faster-whisper; install `[asr]` extra) |
| `ASR_DEVICE`            | `cpu`                                             |
| `OPENAI_API_KEY`        | Required only when `ASR_PROVIDER=openai`          |

When running backend **inside** docker-compose, use service names (`postgres`, `localstack`) as hosts. When running **natively** on your machine, use `localhost`.

**Local ASR:** `cd backend && uv sync --extra asr` installs faster-whisper. CI and text-only dev skip this extra.

---

## Authentication

There is **no login** (ADR-013). All API requests use a shared mock user (`mock-local-user`). No Bearer token required.

```bash
./scripts/verify-pipeline-e2e.sh      # text pipeline
./scripts/verify-audio-pipeline.sh    # WAV + ASR (needs uv sync --extra asr)
# or: make verify-e2e / make verify-audio
```

**AWS dev:** the public ALB exposes an open API — portfolio/demo only; do not treat as production-ready.

---

## Full Stack (Phase 1+)

Once backend and frontend are scaffolded:

### Option A: Docker Compose (all services)

```bash
make dev
```

| Service     | URL                        |
| ----------- | -------------------------- |
| Frontend    | http://localhost:3000      |
| Backend API | http://localhost:8000      |
| API docs    | http://localhost:8000/docs |
| Postgres    | localhost:5432             |
| LocalStack  | localhost:4566             |

**Verify full stack (KRE-128):**

```bash
make dev   # separate terminal, or: docker compose up -d --build
make verify-fullstack
```

Checks `/health`, `/health/ready`, frontend HTML, and the same API URL the browser `api-client` uses.

### Option B: Hybrid (recommended for active development)

Run infrastructure in Docker; run app code natively for hot-reload.

```bash
# Terminal 1: infrastructure only
docker compose up postgres localstack

# Terminal 2: backend
cd backend
uv sync
uv run uvicorn eventforge.main:app --reload --port 8000

# Terminal 3: frontend
cd frontend
npm install
npm run dev
```

---

## LocalStack — AWS Resource Emulation

Init script `infra/docker/localstack/init/01-eventforge.sh` runs on LocalStack startup and creates:

- EventBridge bus: `eventforge-bus`
- SQS queues: `eventforge-ingestion`, `eventforge-embedding`, `eventforge-knowledge-mining`, `eventforge-research`, `eventforge-synthesis`, `eventforge-dlq`
- **Redrive policies:** each worker queue → `eventforge-dlq` with `maxReceiveCount: 3` (override via `SQS_MAX_RECEIVE_COUNT` in init env)

Verify redrive policies after `make dev`:

```bash
./scripts/verify-dlq-redrive.sh
```

If queues existed before redrive was added, restart LocalStack so init re-applies attributes:

```bash
docker compose restart localstack
```

### Manual AWS CLI (with awslocal)

If you have `awscli-local` installed:

```bash
pip install awscli-local

awslocal sqs send-message \
  --queue-url http://localhost:4566/000000000000/eventforge-ingestion \
  --message-body '{"event_id":"test-1","correlation_id":"corr-1","job_id":"job-1"}'
```

### LocalStack Limitations

| Feature                  | Local Support | Workaround                                |
| ------------------------ | ------------- | ----------------------------------------- |
| EventBridge → SQS rules  | Good          | Use init scripts                          |
| SQS long-polling         | Good          | —                                         |
| Step Functions Map state | Limited       | Simplified fan-out in local (see Phase 2) |
| ECS / Fargate            | Not emulated  | Run workers as local Python processes     |

---

## Database

### Connection String

```
postgresql+asyncpg://eventforge:changeme@localhost:5432/eventforge
```

### Migrations (Phase 1+)

```bash
cd backend
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "description"
```

### Reset Database

```bash
docker compose down -v   # WARNING: destroys volumes
docker compose up postgres
cd backend && uv run alembic upgrade head
```

---

## pgvector

The Postgres image includes the `vector` extension. It is enabled via Alembic migration in Phase 1 (`CREATE EXTENSION IF NOT EXISTS vector`).

Document chunks and embeddings are stored in Postgres (not a separate vector DB). Similarity search uses pgvector HNSW or IVFFlat indexes.

### Verify extension (Phase 1+)

```bash
docker compose exec postgres psql -U eventforge -d eventforge -c "SELECT extname FROM pg_extension WHERE extname = 'vector';"
```

---

## Observability (Phase 4+)

When OTEL collector is added to docker-compose:

```bash
make dev   # starts postgres, localstack, otel-collector, jaeger, backend, frontend

# Jaeger UI
open http://localhost:16686
```

Submit a query (UI or API), then search Jaeger by `correlation_id` or service name
(`eventforge-api`, `eventforge-worker-ingestion`, etc.).

Set in `.env`:

```
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=eventforge-api
```

Disable locally with `OTEL_ENABLED=false`.

---

## Running Workers Locally (Phase 2+)

Workers run as separate processes consuming SQS. Use the root `Procfile` to start all six at once.

**Recommended — Honcho** (included in backend dev deps, no extra install):

```bash
# Requires postgres + localstack (make dev or docker compose up postgres localstack)
make workers
```

**Optional — Overmind** (macOS/Linux, tmux panes + per-process attach):

```bash
brew install overmind
make workers-overmind
# overmind connect ingestion   # attach to one worker
# overmind restart research    # restart after code change
```

Run a single worker manually:

```bash
uv run --project backend python -m eventforge.workers.ingestion
```

**Tavily (Phase 3 ingestion):** set `TAVILY_API_KEY` in `.env` before running the ingestion worker or E2E smoke test. Without it, ingestion fails with a clear config error.

**Audio (WAV preprocessing):** install the optional ASR extra and run workers with `ASR_PROVIDER=local` (default). Preprocessing queue visibility is 900s in LocalStack init for slow CPU transcription. Smoke test: `make verify-audio` with API + workers running.

### Hybrid dev loop (API + workers)

```bash
# Terminal 1: infrastructure
docker compose up postgres localstack

# Terminal 2: API
cd backend && uv run uvicorn eventforge.main:app --reload --port 8000

# Terminal 3: all workers
make workers
```

Future: `docker compose --profile workers up` for CI / full-container stack.

---

## Common Issues

### Port already in use

```bash
# Find process on port 5432
lsof -i :5432
```

Change ports in `.env` if needed.

### LocalStack init didn't run

```bash
docker compose restart localstack
docker compose logs localstack | tail -50
```

Ensure init script is executable:

```bash
chmod +x infra/docker/localstack/init/01-eventforge.sh
```

### Backend can't connect to Postgres

- Native backend → use `POSTGRES_HOST=localhost`
- Docker backend → use `POSTGRES_HOST=postgres`

### CORS errors in frontend

Ensure FastAPI CORS middleware allows `http://localhost:3000` (configured in Phase 1).

---

## Development Workflow

```mermaid
flowchart LR
    A[Edit code] --> B[Hot reload]
    B --> C[Test via API/UI]
    C --> D{Pass?}
    D -->|No| A
    D -->|Yes| E[Update TASKS.md checkbox]
    E --> F[Commit when ready]
```

1. Pick task from `docs/TASKS.md`
2. Implement with local hybrid setup
3. Test end-to-end flow
4. Mark task complete in `docs/TASKS.md`
5. Commit when explicitly requested

---

## Useful Commands

```bash
make dev          # Start all services
make down         # Stop all services
make logs         # Tail logs
make test         # Run tests (Phase 1+)
make lint         # Run linters (Phase 1+)
./scripts/seed.sh # Seed sample data (Phase 1+)
```

---

## Next Steps

After infrastructure is verified:

1. **Phase 1–3:** Backend API + real AI pipeline ✅
2. **Phase 4.1:** SSE live updates on `/queries/[id]` ✅ ([KRE-151](https://linear.app/kreativbiro/issue/KRE-151))
3. **Phase 4.2:** React Flow pipeline visualization ✅ ([KRE-152](https://linear.app/kreativbiro/issue/KRE-152))
4. **Phase 4.3:** Dashboard UI — submit, history, synthesis, sources, cost ✅ ([KRE-153](https://linear.app/kreativbiro/issue/KRE-153))
5. **Phase 4.4:** Sign-in UI removed — open API with mock user (ADR-013)
6. **Phase 4.5:** Local OTEL — next
