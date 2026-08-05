# EventForge Backend

FastAPI application, SQS workers, and dataset pipeline stages.

## Setup

```bash
cd backend
cp .env.example .env   # or use repo-root .env
uv sync
```

Install git hooks (runs `ruff check` on commit):

```bash
make hooks   # from repo root
```

## Run

```bash
uv run uvicorn eventforge.main:app --reload --port 8000
```

Via Docker Compose (from repo root, with infra + backend):

```bash
make dev
curl http://localhost:8000/health
curl http://localhost:8000/health/ready
```

Logging uses pretty text in `ENVIRONMENT=local` and JSON elsewhere.

## Migrations

```bash
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "description"
```

See `docs/LOCAL_DEV.md` for full stack development.

## Projects API

| Method   | Path                               | Notes                                              |
| -------- | ---------------------------------- | -------------------------------------------------- |
| `POST`   | `/api/v1/projects`                 | Multipart upload + schema template; queues intake  |
| `GET`    | `/api/v1/projects`                 | List projects for current user                     |
| `GET`    | `/api/v1/projects/{id}`            | Stages, assets, export summary, `llm_usage`        |
| `GET`    | `/api/v1/projects/{id}/stream`     | SSE pipeline updates                             |
| `GET`    | `/api/v1/projects/{id}/export`     | Download JSONL (`?format=jsonl`) or QC (`?format=qc`) |
| `DELETE` | `/api/v1/projects/{id}`            | Remove project                                   |

Local dev uses an implicit mock user (no auth headers). Regenerate OpenAPI after schema changes: `make openapi` from repo root.

## Pipeline smoke test

With Postgres, LocalStack, API, and workers running:

```bash
make verify-e2e
```
