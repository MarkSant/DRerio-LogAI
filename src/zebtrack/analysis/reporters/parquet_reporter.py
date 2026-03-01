"""Parquet summary export.

Exports the tidy analysis DataFrame to ``.parquet`` with internal
(non-display) column names and optional ROI schema standardisation.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from zebtrack.analysis.reporters.reporter_context import ReporterContext

log = structlog.get_logger(__name__)


class ParquetSummaryReporter:
    """Export summary data in Parquet format.

    Unlike ``ExcelReporter``, Parquet output preserves internal column
    names (no display renaming) so that downstream code can rely on a
    stable schema.

    Example:
        >>> ctx = ReporterContext.from_analysis(analysis_result)
        >>> ParquetSummaryReporter(ctx).export_summary("summary.parquet")
    """

    def __init__(self, ctx: ReporterContext) -> None:
        self._ctx = ctx

    def export_summary(
        self,
        output_path: Path | str,
        expected_roi_names: list[str] | None = None,
    ) -> None:
        """Export summary data to Parquet.

        Args:
            output_path: Output file path (``.parquet``).
            expected_roi_names: Optional list of ROI names for schema
                standardisation.
        """
        path = Path(output_path) if isinstance(output_path, str) else output_path
        path.parent.mkdir(parents=True, exist_ok=True)

        data_to_export = self._ctx.tidy_data
        if expected_roi_names:
            data_to_export = self._ctx.data_transformer.standardize_roi_columns(
                data_to_export, expected_roi_names
            )

        self._ctx.data_transformer.validate_schema(data_to_export)

        data_to_export.to_parquet(path, index=False)
        log.info("reporter.parquet.exported", path=str(path))
