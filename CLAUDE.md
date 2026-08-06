# EventForge — Cursor Agent Context

> **Cursor IDE:** Context loads automatically from `.cursor/rules/`. See [AGENTS.md](./AGENTS.md) for the full agent guide.

## What Is EventForge?

**Dataset intelligence platform** — upload files + annotation schema → EventBridge pipeline → labeled JSONL out.

**Read first:** [`docs/DATASET_PLATFORM.md`](./docs/DATASET_PLATFORM.md) · [`docs/PIVOT_PLAN.md`](./docs/PIVOT_PLAN.md)

## Current phase

**Pivot Phases 0–9 complete.** **Phase 10 next** — polish & portfolio. See [`docs/PIVOT_PLAN.md`](./docs/PIVOT_PLAN.md).

**Infra scope:** LocalStack + workers locally. No AWS deploy (ADR-015).

## Commands

```bash
./scripts/setup-local.sh && make dev
make down / make logs
```

## User shortcuts

- _"What's next in the pivot?"_ → `docs/PIVOT_PLAN.md` progress table
- _"Implement pivot Phase N"_ → `docs/PIVOT_PLAN.md` Phase N checklist
- _"Implement KRE-xxx"_ → Linear MCP `get_issue`
