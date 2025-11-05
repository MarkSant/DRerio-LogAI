import gettext
import io
import locale
import os
import warnings
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import structlog
from docx import Document
from docx.document import Document as DocxDocument
from docx.shared import Inches
from docxtpl import DocxTemplate

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.analysis.data_transformer import DataTransformer
from zebtrack.analysis.models import AnalysisResult
from zebtrack.analysis.visualization_generator import VisualizationGenerator

log = structlog.get_logger(__name__)

_BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = _BASE_DIR.parent / "templates"
LOCALES_DIR = _BASE_DIR.parent / "locales"
REPORTER_DOMAIN = "reporter"
INDIVIDUAL_REPORT_TEMPLATE = TEMPLATES_DIR / "individual_report_template.docx"
PROJECT_REPORT_TEMPLATE = TEMPLATES_DIR / "project_report_template.docx"


def _load_translator():
    languages: list[str] = []

    env_candidates: list[str] = []
    for env_var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(env_var)
        if value:
            env_candidates.extend(lang for lang in value.split(":") if lang)

    try:
        current_locale = locale.getlocale()[0]
    except (AttributeError, TypeError, ValueError):
        current_locale = None

    for candidate in [*env_candidates, current_locale]:
        if not candidate:
            continue
        if candidate not in languages:
            languages.append(candidate)
        if "_" in candidate:
            base = candidate.split("_", 1)[0]
            if base not in languages:
                languages.append(base)

    try:
        translator = gettext.translation(
            REPORTER_DOMAIN,
            localedir=str(LOCALES_DIR),
            languages=languages if languages else None,
            fallback=True,
        )
    except OSError:
        translator = gettext.NullTranslations()

    return translator.gettext


_translator: Callable[[str], str] = _load_translator()


def _(message: str) -> str:
    return _translator(message)


def _format_time_minutes_seconds(seconds):
    """
    Format time as MM:SS or HH:MM:SS if over an hour.
    """
    if pd.isna(seconds) or seconds is None:
        return "N/A"

    seconds = float(seconds)
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}:{secs:02d}"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"


class Reporter:
    """Generate analysis reports in various formats (Excel, Word).

    This class is responsible for the final assembly of reports, delegating
    data transformation to DataTransformer and visualization generation to
    VisualizationGenerator.

    Refactored in Phase 2 (Task 2.5) to separate concerns:
        - DataTransformer: Handles data transformation and tidying
        - VisualizationGenerator: Handles plot/visualization generation
        - Reporter: Handles final report assembly and export

    Example:
        >>> # Modern approach (RECOMMENDED)
        >>> service = AnalysisService(settings_obj=settings)
        >>> analysis = service.run_full_analysis_as_dto(...)
        >>> reporter = Reporter.from_analysis(analysis)
        >>> reporter.export_summary_data("output.xlsx")
        >>> reporter.export_individual_report("report.docx")
    """

    def __init__(
        self,
        trajectory_df: pd.DataFrame = None,
        metadata: dict | None = None,
        # Calibration and setup
        pixelcm_x: float | None = None,
        pixelcm_y: float | None = None,
        video_height_px: int | None = None,
        arena_polygon_px: list[tuple[float, float]] | None = None,
        rois: list | None = None,
        fps: float | None = None,
        # Optional params
        roi_colors: dict | None = None,
        video_path: str | None = None,
        calibration=None,
        # Analysis params
        sharp_turn_threshold: float = 90.0,
        freezing_threshold: float = 1.5,
        freezing_duration: float = 1.0,
        smoothing_window_length: int | None = None,
        smoothing_polyorder: int | None = None,
        settings_obj=None,
        # Modern path: DTO-based construction
        analysis: AnalysisResult | None = None,
    ):
        """Create Reporter instance for generating analysis reports.

        **RECOMMENDED**: Use Reporter.from_analysis(analysis_result) instead
        of calling this constructor directly.

        Construction Paths:
            1. Modern (RECOMMENDED): Pass pre-computed analysis via `analysis` parameter
            2. Legacy (DEPRECATED): Pass trajectory_df + all other parameters

        Args:
            trajectory_df: Raw trajectory DataFrame (DEPRECATED - use analysis parameter)
            metadata: Experiment metadata (DEPRECATED - included in analysis)
            pixelcm_x: Pixels-to-cm conversion (DEPRECATED - included in analysis)
            pixelcm_y: Pixels-to-cm conversion (DEPRECATED - included in analysis)
            video_height_px: Video height (DEPRECATED - included in analysis)
            arena_polygon_px: Arena polygon (DEPRECATED - included in analysis)
            rois: ROI list (DEPRECATED - included in analysis)
            fps: Frame rate (DEPRECATED - included in analysis)
            roi_colors: ROI colors (optional)
            video_path: Video file path (optional)
            calibration: Calibration object (optional)
            sharp_turn_threshold: Sharp turn threshold (deg/s)
            freezing_threshold: Freezing velocity threshold (cm/s)
            freezing_duration: Minimum freezing duration (s)
            smoothing_window_length: Smoothing window (optional)
            smoothing_polyorder: Smoothing polynomial order (optional)
            settings_obj: Settings instance (optional)
            analysis: AnalysisResult DTO (RECOMMENDED - modern path)

        Example (Modern - RECOMMENDED):
            >>> # Get pre-computed analysis
            >>> service = AnalysisService(settings_obj=settings)
            >>> analysis = service.run_full_analysis_as_dto(...)
            >>> reporter = Reporter.from_analysis(analysis)  # Use factory method!

        Example (Legacy - DEPRECATED):
            >>> reporter = Reporter(
            ...     trajectory_df=df,
            ...     metadata={"experiment_id": "exp_001"},
            ...     pixelcm_x=10.0,
            ...     # ... many more parameters ...
            ... )
            # DeprecationWarning: Use Reporter.from_analysis() instead
        """
        # Modern path: using AnalysisResult DTO
        if analysis is not None:
            # Delegate to from_analysis() and copy attributes
            temp_instance = Reporter.from_analysis(analysis)
            self.__dict__.update(temp_instance.__dict__)
            return

        # Legacy path validation
        if trajectory_df is None:
            raise ValueError(
                "Reporter: Either 'analysis' or 'trajectory_df' must be provided. "
                "RECOMMENDED: Use Reporter.from_analysis(analysis_result) instead."
            )

        # Emit deprecation warning for legacy constructor
        warnings.warn(
            "Reporter: Direct instantiation with trajectory_df is DEPRECATED and "
            "will be removed in v3.0. "
            "\n"
            "Migration Guide:\n"
            "  Instead of: Reporter(trajectory_df=df, metadata=meta, pixelcm_x=10.0, ...)\n"
            "  Use:        service = AnalysisService(settings_obj=settings)\n"
            "              analysis = service.run_full_analysis_as_dto(...)\n"
            "              reporter = Reporter.from_analysis(analysis)\n"
            "\n"
            "Benefits: Better performance (no re-analysis), improved testability, type safety.\n"
            "Timeline: Deprecation in v2.1 (2025-11), removal in v3.0 (2026-02).\n"
            "See docs/migration/reporter-v3.md for details.",
            DeprecationWarning,
            stacklevel=2,
        )

        # Legacy constructor logic
        self.settings = settings_obj
        self.metadata = metadata
        self.roi_colors = roi_colors if roi_colors else {}
        self.video_path = video_path
        self.calibration = calibration
        self._pixelcm_x = pixelcm_x
        self._pixelcm_y = pixelcm_y
        self._video_height_px = video_height_px

        # Ensure trajectory coordinates stay aligned with calibration space
        # before running any calculations.
        if calibration is not None:
            trajectory_df = DataTransformer.warp_trajectory_if_needed(trajectory_df, calibration)

        if "track_id" in trajectory_df.columns:
            track_ids = pd.to_numeric(trajectory_df["track_id"], errors="coerce")
            trajectory_df = trajectory_df.copy()
            trajectory_df["track_id"] = track_ids.astype("Int64")

        # Run the unified analysis via the service
        service = AnalysisService(settings_obj=settings_obj)
        self.report, self.b_analyzer, self.r_analyzer = service.run_full_analysis(
            trajectory_df=trajectory_df,
            pixelcm_x=pixelcm_x,
            pixelcm_y=pixelcm_y,
            video_height_px=video_height_px,
            arena_polygon_px=arena_polygon_px,
            rois=rois,
            fps=fps,
            freezing_vel_threshold=freezing_threshold,
            freezing_min_duration=freezing_duration,
            smoothing_window_length=smoothing_window_length,
            smoothing_polyorder=smoothing_polyorder,
        )

        # Store for plotting methods that still need them
        self.sharp_turn_threshold = sharp_turn_threshold
        self.freezing_threshold = freezing_threshold
        self.freezing_duration = freezing_duration

        # Initialize data transformer and visualization generator
        self.data_transformer = DataTransformer()
        self.viz_generator = VisualizationGenerator(
            b_analyzer=self.b_analyzer,
            r_analyzer=self.r_analyzer,
            metadata=self.metadata,
            roi_colors=self.roi_colors,
            calibration=self.calibration,
            pixelcm_x=self._pixelcm_x,
            pixelcm_y=self._pixelcm_y,
            video_height_px=self._video_height_px,
            sharp_turn_threshold=self.sharp_turn_threshold,
            settings_obj=self.settings,
        )

        # Generate the tidy dataframe from the report
        tidy_df = self.data_transformer.create_tidy_dataframe(
            report=self.report,
            metadata=self.metadata,
            b_analyzer=self.b_analyzer,
            r_analyzer=self.r_analyzer,
            roi_colors=self.roi_colors,
        )
        self.tidy_data = self.data_transformer.standardize_tidy_dataframe(tidy_df, self.metadata)

    @classmethod
    def from_analysis(cls, analysis: AnalysisResult) -> "Reporter":
        """Create Reporter from pre-computed analysis result (RECOMMENDED).

        This is the modern, performant way to create Reporter instances.
        Avoids re-running analysis and enables better testability.

        Args:
            analysis: AnalysisResult DTO with pre-computed analysis

        Returns:
            Reporter instance ready for report generation

        Example:
            >>> # In analysis workflow
            >>> service = AnalysisService(settings_obj=settings)
            >>> result = service.run_full_analysis_as_dto(...)
            >>> reporter = Reporter.from_analysis(result)
            >>> reporter.export_summary_data(output_path)
        """
        instance = cls.__new__(cls)

        # Store settings reference
        instance.settings = None  # Not needed when using pre-computed analysis

        # Store metadata and calibration
        instance.metadata = analysis.metadata
        instance.roi_colors = analysis.roi_colors
        instance.video_path = analysis.video_path
        instance.calibration = analysis.calibration_params.calibration
        instance._pixelcm_x = analysis.calibration_params.pixelcm_x
        instance._pixelcm_y = analysis.calibration_params.pixelcm_y
        instance._video_height_px = analysis.calibration_params.video_height_px

        # Store analysis results directly (no re-computation)
        instance.report = analysis.report
        instance.b_analyzer = analysis.behavioral_analyzer
        instance.r_analyzer = analysis.roi_analyzer

        # Store analysis parameters
        instance.sharp_turn_threshold = analysis.sharp_turn_threshold
        instance.freezing_threshold = analysis.freezing_threshold
        instance.freezing_duration = analysis.freezing_duration

        # Initialize data transformer and visualization generator
        instance.data_transformer = DataTransformer()
        instance.viz_generator = VisualizationGenerator(
            b_analyzer=instance.b_analyzer,
            r_analyzer=instance.r_analyzer,
            metadata=instance.metadata,
            roi_colors=instance.roi_colors,
            calibration=instance.calibration,
            pixelcm_x=instance._pixelcm_x,
            pixelcm_y=instance._pixelcm_y,
            video_height_px=instance._video_height_px,
            sharp_turn_threshold=instance.sharp_turn_threshold,
            settings_obj=instance.settings,
        )

        # Generate tidy dataframe
        tidy_df = instance.data_transformer.create_tidy_dataframe(
            report=instance.report,
            metadata=instance.metadata,
            b_analyzer=instance.b_analyzer,
            r_analyzer=instance.r_analyzer,
            roi_colors=instance.roi_colors,
        )
        instance.tidy_data = instance.data_transformer.standardize_tidy_dataframe(
            tidy_df, instance.metadata
        )

        return instance

    def export_summary_data(self, output_path: Path | str, format: str = "excel"):
        """Export summary data to file (Excel, CSV, or Parquet).

        Args:
            output_path: Output file path
            format: Output format ('excel', 'csv', or 'parquet')

        Raises:
            ValueError: If unsupported format is specified
        """
        path = Path(output_path) if isinstance(output_path, str) else output_path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.data_transformer.validate_schema(self.tidy_data)
        if format == "excel":
            self.tidy_data.to_excel(output_path, index=False, engine="openpyxl")
        elif format == "csv":
            self.tidy_data.to_csv(output_path, index=False)
        elif format == "parquet":
            self.tidy_data.to_parquet(output_path, index=False)
        else:
            raise ValueError(f"Unsupported file format: {format}")

    def export_individual_report(self, output_path: Path | str):
        """
        Exports a complete individual report. This is a convenience wrapper
        around the step-by-step method for consumers who don't need progress updates.

        Args:
            output_path: Output file path for the report
        """
        self.export_individual_report_step_by_step(output_path, lambda p, s: None)

    def export_individual_report_step_by_step(
        self, output_path: Path | str, progress_callback: Callable[[float, str], None]
    ):
        """Export individual report with step-by-step progress reporting.

        Args:
            output_path: Output file path for the report
            progress_callback: Callback function (progress: float, status: str) -> None
        """
        output_path = Path(output_path) if isinstance(output_path, str) else output_path
        total_steps = 10
        template_path = INDIVIDUAL_REPORT_TEMPLATE
        heading_text = _("Analysis Report - {experiment_id}").format(
            experiment_id=self.metadata.get("experiment_id", "Unknown")
        )

        doc_template, document = self._prepare_report_document(template_path, heading_text)

        # Step 1: Metadata section
        self._append_metadata_section(document, progress_callback, total_steps)
        # Final step: ensure document is written to disk. If a DocxTemplate
        # was used, save via its API to preserve any template context. Otherwise
        # save the Document object directly.
        try:
            file_path = (
                f"{output_path}.docx"
                if not str(output_path).lower().endswith(".docx")
                else str(output_path)
            )
            if doc_template is not None:
                # DocxTemplate saves via .save()
                doc_template.save(file_path)
            else:
                document.save(file_path)
            progress_callback(1.0, _("Report saved"))
            log.info("reporter.individual_report.saved", path=file_path)
        except Exception as e:
            log.error("reporter.individual_report.save_failed", error=str(e), exc_info=True)

    def _prepare_report_document(self, template_path: Path, heading_text: str):
        """Prepare a docx document using template if available, return (doc_template, document)."""
        doc_template: DocxTemplate | None = None
        document: DocxDocument | None = None

        if template_path.exists():
            try:
                doc_template = DocxTemplate(str(template_path))
                doc_template.render({"title": heading_text})
                document = doc_template.docx
            except Exception:
                log.warning(
                    "analysis.reporter.template_render_failed",
                    template=str(template_path),
                    exc_info=True,
                )
                document = Document()
        else:
            log.warning(
                "analysis.reporter.template_missing_fallback",
                template=str(template_path),
            )
            document = Document()

        if document is None:
            document = Document()

        if doc_template is None:
            document.add_heading(heading_text, level=1)

        return doc_template, document

    def _append_metadata_section(
        self,
        document: DocxDocument,
        progress_callback: Callable[[float, str], None],
        total_steps: int,
    ) -> None:
        """Append the metadata section to the provided document and call progress callback."""
        document.add_heading(_("Experiment Metadata"), level=2)
        for key, value in self.metadata.items():
            document.add_paragraph(f"{key.replace('_', ' ').title()}: {value}")
        progress_callback(1 / total_steps, _("Metadata added"))

        # Step 2: Summary table
        document.add_heading(_("Metrics Summary"), level=2)
        df = self.tidy_data.drop(
            columns=[k for k in self.metadata.keys() if k in self.tidy_data.columns]
        )

        table = document.add_table(rows=1, cols=2)
        table.style = "Table Grid"
        table.cell(0, 0).text = _("Metric")
        table.cell(0, 1).text = _("Value")

        for column_name in df.columns:
            row_cells = table.add_row().cells
            formatted_name = column_name.replace("_", " ").title()
            row_cells[0].text = formatted_name

            value = df[column_name].iloc[0]
            if pd.isna(value):
                row_cells[1].text = _("N/A")
            elif isinstance(value, (int, float)):
                if column_name.endswith("_s"):
                    row_cells[1].text = _format_time_minutes_seconds(value)
                else:
                    row_cells[1].text = f"{value:.2f}"
            else:
                row_cells[1].text = str(value)

        document.add_page_break()
        progress_callback(2 / total_steps, _("Summary table added"))

        # Step 3: ROI Reference Map (optional) + Visualizations + ROI Event Log
        # These are extracted into helpers to keep this method concise.
        self._append_roi_reference_map(document, progress_callback, total_steps)
        self._append_visualizations(document, progress_callback, total_steps)
        self._append_roi_event_log(document, progress_callback, total_steps)

    def _append_roi_reference_map(
        self,
        document: DocxDocument,
        progress_callback: Callable[[float, str], None],
        total_steps: int,
    ) -> None:
        """Append ROI reference map if available."""
        if not self.r_analyzer:
            return
        document.add_heading(_("ROI Reference Map"), level=2)
        fig = self.viz_generator.generate_roi_reference_plot()
        memfile = io.BytesIO()
        fig.savefig(memfile, format="png", dpi=300, bbox_inches="tight")
        import matplotlib.pyplot as plt

        plt.close(fig)
        memfile.seek(0)
        document.add_picture(memfile, width=Inches(6.5))
        progress_callback(3 / total_steps, _("ROI map added"))

    def _append_visualizations(
        self,
        document: DocxDocument,
        progress_callback: Callable[[float, str], None],
        total_steps: int,
    ) -> None:
        """Generate and append visualization plots in parallel."""
        document.add_heading(_("Visualizations"), level=2)
        plot_configs = [
            (
                lambda ax: self.viz_generator.generate_trajectory_plot(ax, self.video_path),
                _("Trajectory"),
            ),
            (self.viz_generator.generate_heatmap, _("Heatmap")),
            (self.viz_generator.generate_position_vs_time_plot, _("Position vs. Time")),
            (self.viz_generator.generate_cumulative_distance_plot, _("Cumulative Distance")),
            (self.viz_generator.generate_angular_velocity_plot, _("Angular Velocity")),
        ]

        log.info("reporter.plots.parallel_generation.start", count=len(plot_configs))
        plot_results = self.viz_generator.generate_plots_parallel(plot_configs)

        for i, (memfile, name) in enumerate(plot_results):
            if memfile.getbuffer().nbytes > 0:
                document.add_paragraph(_("Chart: {name}:").format(name=name))
                document.add_picture(memfile, width=Inches(6.0))
            progress_callback(
                (4 + i) / total_steps,
                _("Visualization added: {name}").format(name=name),
            )

    def _append_roi_event_log(
        self,
        document: DocxDocument,
        progress_callback: Callable[[float, str], None],
        total_steps: int,
    ) -> None:
        """Append ROI event log appendix if ROI analyzer produced events."""
        if not self.r_analyzer:
            return
        document.add_page_break()
        document.add_heading(_("Appendix: ROI Event Log"), level=2)
        event_log_df = self.r_analyzer.get_event_log()
        if not event_log_df.empty:
            document.add_paragraph(
                _("Chronological log of all entries and exits from defined ROIs.")
            )

            event_log_df = event_log_df.rename(columns={"roi_name": "ROI", "event": _("Event")})

            start_time = event_log_df["timestamp"].iloc[0]

            table = document.add_table(rows=1, cols=len(event_log_df.columns))
            table.style = "Table Grid"
            for i, col_name in enumerate(event_log_df.columns):
                if col_name == "timestamp":
                    table.cell(0, i).text = _("Time (mm:ss)")
                else:
                    table.cell(0, i).text = str(col_name)

            for _index, row in event_log_df.iterrows():
                cells = table.add_row().cells
                for i, (col_name, value) in enumerate(row.items()):
                    if col_name == "timestamp":
                        elapsed = (value - start_time).total_seconds()
                        minutes = int(elapsed // 60)
                        seconds = elapsed % 60
                        cells[i].text = f"{minutes:02d}:{seconds:06.3f}"
                    else:
                        cells[i].text = str(value)
        else:
            document.add_paragraph(_("No ROI entry or exit events were recorded."))
        progress_callback(9 / total_steps, _("Event log added"))

    @staticmethod
    def export_project_report(aggregated_df: pd.DataFrame, output_path: Path | str):
        """Export aggregated project report with comparative analysis.

        Args:
            aggregated_df: Aggregated DataFrame with multiple experiments
            output_path: Output file path for the report
        """
        output_path = Path(output_path) if isinstance(output_path, str) else output_path
        document = Document()
        document.add_heading("Aggregated Project Report", level=1)
        document.add_heading("Descriptive Statistics by Group", level=2)
        if "total_distance_cm" in aggregated_df.columns:
            desc_stats = aggregated_df.groupby("group_id")["total_distance_cm"].agg(
                ["mean", "std", "count"]
            )
            document.add_paragraph("Statistics for Total Distance Traveled (cm):")
            table = document.add_table(rows=1, cols=len(desc_stats.columns) + 1)
            table.style = "Table Grid"
            hdr_cells = table.rows[0].cells
            hdr_cells[0].text = "group_id"
            for i, col_name in enumerate(desc_stats.columns):
                hdr_cells[i + 1].text = col_name
            for index, row in desc_stats.iterrows():
                row_cells = table.add_row().cells
                row_cells[0].text = str(index)
                for i, value in enumerate(row):
                    row_cells[i + 1].text = f"{value:.2f}"
        else:
            document.add_paragraph(
                "Total distance metric not available for the aggregated dataset."
            )
        document.add_page_break()
        document.add_heading("Comparative Plots", level=2)

        metrics_for_boxplot = [
            "total_distance_cm",
            "mean_speed_cm_s",
            "sharp_turns_count",
            "sharp_turns_per_minute",
            "total_roi_entries",
        ]

        for metric in metrics_for_boxplot:
            if metric in aggregated_df.columns:
                title = f"Comparison of {metric.replace('_', ' ').title()}"
                boxplot_fig = VisualizationGenerator.generate_comparative_boxplot(
                    aggregated_df,
                    metric,
                    title,
                )
                memfile = io.BytesIO()
                boxplot_fig.savefig(memfile, format="png", dpi=300, bbox_inches="tight")
                import matplotlib.pyplot as plt

                plt.close(boxplot_fig)
                memfile.seek(0)
                document.add_paragraph(title, style="Heading 3")
                document.add_picture(memfile, width=Inches(6.0))

        file_path = f"{output_path}.docx"
        document.save(file_path)
