# SQS workers — start all: make workers (Honcho) or make workers-overmind (Overmind)
ingestion: uv run --project backend python -m eventforge.workers.intake
embedding: uv run --project backend python -m eventforge.workers.preprocessing
knowledge: uv run --project backend python -m eventforge.workers.planning
research: uv run --project backend python -m eventforge.workers.research
synthesis: uv run --project backend python -m eventforge.workers.synthesis
dlq: uv run --project backend python -m eventforge.workers.dlq
