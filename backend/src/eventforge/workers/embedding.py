"""Backward-compatible entrypoint — use eventforge.workers.preprocessing."""

from eventforge.workers.preprocessing import EmbeddingWorker, PreprocessingWorker

__all__ = ["EmbeddingWorker", "PreprocessingWorker"]
