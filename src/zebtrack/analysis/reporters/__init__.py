"""Reporter sub-package — decomposed from the monolithic ``reporter.py``.

Public API
----------
ReporterContext          – Shared state container (legacy + modern construction)
WordReporter             – Individual Word (.docx) reports
ExcelReporter            – Summary Excel / CSV export
ParquetSummaryReporter   – Summary Parquet export
HtmlReporter             – Interactive Plotly HTML reports
ScriptExporter           – R / Python / Feather export
export_project_report    – Aggregated project-level Word report (standalone fn)
export_multi_aquarium_reports – Per-aquarium report generation (standalone fn)
"""

from zebtrack.analysis.reporters.excel_reporter import ExcelReporter
from zebtrack.analysis.reporters.html_reporter import HtmlReporter
from zebtrack.analysis.reporters.parquet_reporter import ParquetSummaryReporter
from zebtrack.analysis.reporters.project_reporter import (
    export_multi_aquarium_reports,
    export_project_report,
)
from zebtrack.analysis.reporters.reporter_context import ReporterContext
from zebtrack.analysis.reporters.script_exporter import ScriptExporter
from zebtrack.analysis.reporters.word_reporter import WordReporter

__all__ = [
    "ExcelReporter",
    "HtmlReporter",
    "ParquetSummaryReporter",
    "ReporterContext",
    "ScriptExporter",
    "WordReporter",
    "export_multi_aquarium_reports",
    "export_project_report",
]
