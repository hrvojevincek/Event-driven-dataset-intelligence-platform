# EventForge Frontend

Next.js App Router dashboard for the dataset intelligence pipeline.

## Features

- Project upload + schema templates
- React Flow pipeline visualization
- SSE (`useJobStream`) — real-time stage updates
- QC panel + JSONL export preview
- shadcn/ui + Tailwind v4

## Routes

| Path               | Purpose                              |
| ------------------ | ------------------------------------ |
| `/`                | Landing + recent projects            |
| `/projects/new`    | Upload files + pick annotation schema |
| `/projects/[id]`   | Pipeline graph + QC + JSONL export   |

## Local dev

```bash
cp .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev
```

Open http://localhost:3000 — API calls use the backend mock user (no login). See [`docs/LOCAL_DEV.md`](../docs/LOCAL_DEV.md).

## Structure

```
frontend/src/
├── app/                    # App Router pages
├── components/
│   ├── ui/                 # shadcn/ui
│   ├── workflow/           # React Flow nodes/edges
│   └── dashboard/          # QC, export, cost panels
├── hooks/useJobStream.ts   # SSE subscription
├── lib/api-client.ts       # Typed fetch (openapi-typescript)
└── types/                  # Generated from OpenAPI
```

Regenerate API types after backend OpenAPI changes:

```bash
npm run codegen
```
