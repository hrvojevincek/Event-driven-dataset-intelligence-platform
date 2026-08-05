# SQS workers — start all: make workers (Honcho) or make workers-overmind (Overmind)
intake: uv run --project backend python -m eventforge.workers.intake
preprocessing: uv run --project backend python -m eventforge.workers.preprocessing
planning: uv run --project backend python -m eventforge.workers.planning
annotation: uv run --project backend python -m eventforge.workers.annotation
export: uv run --project backend python -m eventforge.workers.export
dlq: uv run --project backend python -m eventforge.workers.dlq
