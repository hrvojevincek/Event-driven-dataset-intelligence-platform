"""Deprecated — use eventforge.db.repositories.dataset_export.DatasetExportRepository."""

from eventforge.db.repositories.dataset_export import DatasetExportRepository

SynthesisReportRepository = DatasetExportRepository

__all__ = ["SynthesisReportRepository"]
