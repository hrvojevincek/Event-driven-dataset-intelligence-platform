"""Legacy entry point — delegates to the dataset intake worker."""

from eventforge.workers.intake import IngestionWorker, IntakeWorker, main

__all__ = ["IngestionWorker", "IntakeWorker", "main"]

if __name__ == "__main__":
    main(IntakeWorker, service_suffix="ingestion")
