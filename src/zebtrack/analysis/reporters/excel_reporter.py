"""Excel summary export.

Exports the tidy analysis DataFrame to ``.xlsx`` or ``.csv`` with
display-friendly column names and geotaxis renaming.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from zebtrack.analysis.reporters.reporter_context import ReporterContext

log = structlog.get_logger(__name__)


class ExcelReporter:
    """Export summary data in Excel or CSV format.

    Example:
        >>> ctx = ReporterContext.from_analysis(analysis_result)
        >>> ExcelReporter(ctx).export_summary("summary.xlsx")
    """

    def __init__(self, ctx: ReporterContext) -> None:
        self._ctx = ctx

    def export_summary(
        self,
        output_path: Path | str,
        expected_roi_names: list[str] | None = None,
    ) -> None:
        """Export summary data to Excel or CSV.

        The output applies display-friendly column names (via
        ``DISPLAY_COLUMN_MAPPING``) and geotaxis renaming when applicable.

        Args:
            output_path: Output file path (``.xlsx`` or ``.csv``).
            expected_roi_names: Optional list of ROI names for schema
                standardisation.  Missing ROI columns are added with
                ``NaN`` / ``0`` defaults.
        """
        path = Path(output_path) if isinstance(output_path, str) else output_path
        path.parent.mkdir(parents=True, exist_ok=True)

        data_to_export = self._ctx.tidy_data
        if expected_roi_names:
            data_to_export = self._ctx.data_transformer.standardize_roi_columns(
                data_to_export, expected_roi_names
            )

        self._ctx.data_transformer.validate_schema(data_to_export)

        # Geotaxis column renaming -----------------------------------------
        height_cm = float((self._ctx.metadata or {}).get("aquarium_height_cm", 0) or 0)
        num_zones = int((self._ctx.metadata or {}).get("geotaxis_num_zones", 0) or 0)
        if num_zones == 0 and hasattr(self._ctx, "behavioral_config"):
            num_zones = int(self._ctx.behavioral_config.get("geotaxis_num_zones", 0) or 0)

        # Apply display formatting
        data_to_export = self._ctx.data_transformer.prepare_for_display(
            data_to_export, height_cm, num_zones
        )

        fmt = "csv" if str(path).lower().endswith(".csv") else "excel"
        if fmt == "excel":
            data_to_export.to_excel(path, index=False, engine="openpyxl")
        else:
            data_to_export.to_csv(path, index=False)

        log.info("reporter.excel.exported", path=str(path), format=fmt)
