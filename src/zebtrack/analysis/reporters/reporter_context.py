"""Shared context for all reporter sub-classes.

ReporterContext holds the common state (tidy_data, metadata, analyzers,
viz_generator, data_transformer, calibration params) that every export
format needs.  Instantiate it once via the legacy constructor or
``ReporterContext.from_analysis()`` and pass it to the format-specific
reporter classes.
"""

from __future__ import annotations

import gettext
import locale
import os
import warnings
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.analysis.data_transformer import DataTransformer
from zebtrack.analysis.models import AnalysisResult
from zebtrack.analysis.roi import ROI
from zebtrack.analysis.visualization_generator import VisualizationGenerator

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Paths – templates and locales live under ``src/zebtrack/``
# ---------------------------------------------------------------------------
_ZEBTRACK_PKG = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = _ZEBTRACK_PKG / "templates"
LOCALES_DIR = _ZEBTRACK_PKG / "locales"
REPORTER_DOMAIN = "reporter"
INDIVIDUAL_REPORT_TEMPLATE = TEMPLATES_DIR / "individual_report_template.docx"
PROJECT_REPORT_TEMPLATE = TEMPLATES_DIR / "project_report_template.docx"


# ---------------------------------------------------------------------------
# i18n helpers  (shared with word_reporter and html_reporter)
# ---------------------------------------------------------------------------
def _load_translator() -> Callable[[str], str]:
    """Build a gettext translator for the reporter domain."""
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
    """Translate *message* using the reporter domain catalogue."""
    return _translator(message)


# ---------------------------------------------------------------------------
# ReporterContext
# ---------------------------------------------------------------------------
class ReporterContext:
    """Shared state for all report exporters.

    Construction Paths:
        1. **Modern (RECOMMENDED)**: ``ReporterContext.from_analysis(dto)``
        2. **Legacy (DEPRECATED)**: ``ReporterContext(trajectory_df=..., ...)``

    The context is immutable after construction – pass it to
    ``WordReporter``, ``ExcelReporter``, etc.

    Example:
        >>> ctx = ReporterContext.from_analysis(analysis_result)
        >>> WordReporter(ctx).export_individual_report("report.docx")
        >>> ExcelReporter(ctx).export_summary("summary.xlsx")
    """

    def __init__(
        self,
        trajectory_df: pd.DataFrame | None = None,
        metadata: dict | None = None,
        # Calibration and setup
        pixelcm_x: float | None = None,
        pixelcm_y: float | None = None,
        video_height_px: int | None = None,
        arena_polygon_px: Sequence[Sequence[float]] | None = None,
        rois: list[ROI] | None = None,
        fps: float | None = None,
        # Optional params
        roi_colors: dict | None = None,
        video_path: str | None = None,
        calibration: Any = None,
        frame_crop_box: tuple[int, int, int, int] | None = None,
        # Analysis params
        sharp_turn_threshold: float = 90.0,
        freezing_threshold: float = 1.5,
        freezing_duration: float = 1.0,
        smoothing_window_length: int | None = None,
        smoothing_polyorder: int | None = None,
        settings_obj: Any = None,
        behavioral_config: dict | None = None,
        # Modern path: DTO-based construction
        analysis: AnalysisResult | None = None,
    ):
        """Create ReporterContext.

        **RECOMMENDED**: Use ``ReporterContext.from_analysis(analysis_result)``
        instead of calling this constructor directly.

        Args:
            trajectory_df: Raw trajectory DataFrame (DEPRECATED)
            metadata: Experiment metadata (DEPRECATED)
            pixelcm_x: Pixels-to-cm X conversion (DEPRECATED)
            pixelcm_y: Pixels-to-cm Y conversion (DEPRECATED)
            video_height_px: Video height (DEPRECATED)
            arena_polygon_px: Arena polygon (DEPRECATED)
            rois: ROI list (DEPRECATED)
            fps: Frame rate (DEPRECATED)
            roi_colors: ROI colours dict (optional)
            video_path: Video file path (optional)
            calibration: Calibration object (optional)
            frame_crop_box: Crop box tuple (optional)
            sharp_turn_threshold: Sharp turn threshold (deg/s)
            freezing_threshold: Freezing velocity threshold (cm/s)
            freezing_duration: Minimum freezing duration (s)
            smoothing_window_length: Smoothing window (optional)
            smoothing_polyorder: Smoothing polynomial order (optional)
            settings_obj: Settings instance (optional)
            behavioral_config: Behavioural config dict (optional)
            analysis: AnalysisResult DTO (RECOMMENDED)
        """
        # Modern path: delegate to from_analysis
        if analysis is not None:
            temp = ReporterContext.from_analysis(analysis)
            self.__dict__.update(temp.__dict__)
            return

        # Legacy path validation
        if trajectory_df is None:
            raise ValueError(
                "ReporterContext: Either 'analysis' or 'trajectory_df' must be provided. "
                "RECOMMENDED: Use ReporterContext.from_analysis(analysis_result) instead."
            )

        # Deprecation warning
        warnings.warn(
            "ReporterContext: Direct instantiation with trajectory_df is DEPRECATED and "
            "will be removed in v3.0. "
            "\n"
            "Migration Guide:\n"
            "  Instead of: ReporterContext(trajectory_df=df, ...)\n"
            "  Use:        service = AnalysisService(settings_obj=settings)\n"
            "              analysis = service.run_full_analysis_as_dto(...)\n"
            "              ctx = ReporterContext.from_analysis(analysis)\n"
            "\n"
            "Benefits: Better performance (no re-analysis), improved testability, type safety.\n"
            "Timeline: Deprecation in v2.1 (2025-11), removal in v3.0 (2026-02).\n"
            "See docs/migration/reporter-v3.md for details.",
            DeprecationWarning,
            stacklevel=2,
        )

        # --- store raw params ---
        self.settings = settings_obj
        self.metadata = metadata
        self.roi_colors = roi_colors if roi_colors else {}
        self.video_path = video_path
        self.calibration = calibration
        self.frame_crop_box = frame_crop_box
        self._pixelcm_x = pixelcm_x
        self._pixelcm_y = pixelcm_y
        self._video_height_px = video_height_px

        # Ensure trajectory coordinates stay aligned with calibration space
        if calibration is not None:
            trajectory_df = DataTransformer.warp_trajectory_if_needed(
                trajectory_df, calibration, force=True
            )

        if "track_id" in trajectory_df.columns:
            track_ids = pd.to_numeric(trajectory_df["track_id"], errors="coerce")
            trajectory_df = trajectory_df.copy()
            trajectory_df["track_id"] = track_ids.astype("Int64")

        # Run unified analysis via service
        service = AnalysisService(settings_obj=settings_obj)
        (
            self.report,
            self.b_analyzer,
            self.r_analyzer,
            self.validation_warnings,
            self.validation_stats,
        ) = service.run_full_analysis(
            trajectory_df=trajectory_df,
            pixelcm_x=pixelcm_x or 1.0,
            pixelcm_y=pixelcm_y or 1.0,
            video_height_px=video_height_px or 0,
            arena_polygon_px=arena_polygon_px or [],
            rois=rois or [],
            fps=fps or 30.0,
            freezing_vel_threshold=freezing_threshold,
            freezing_min_duration=freezing_duration,
            smoothing_window_length=smoothing_window_length,
            smoothing_polyorder=smoothing_polyorder,
            behavioral_config=behavioral_config,
        )

        # Analysis parameters
        self.sharp_turn_threshold = sharp_turn_threshold
        self.freezing_threshold = freezing_threshold
        self.freezing_duration = freezing_duration
        self.validation_warnings = self.report.get("validacao", {}).get("avisos", [])
        self.validation_stats = self.report.get("validacao", {}).get("estatisticas", {})

        # Behavioural config (MUST be set before tidy DF creation)
        self.behavioral_config = behavioral_config if behavioral_config else {}

        # Shared components
        self._init_shared_components()

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------
    @classmethod
    def from_analysis(cls, analysis: AnalysisResult) -> ReporterContext:
        """Create ReporterContext from a pre-computed AnalysisResult DTO.

        This is the **recommended** construction path.
        """
        instance = cls.__new__(cls)

        instance.settings = None
        instance.metadata = analysis.metadata
        instance.roi_colors = analysis.roi_colors
        instance.video_path = analysis.video_path
        instance.calibration = analysis.calibration_params.calibration
        instance.frame_crop_box = getattr(analysis, "frame_crop_box", None)
        instance._pixelcm_x = analysis.calibration_params.pixelcm_x
        instance._pixelcm_y = analysis.calibration_params.pixelcm_y
        instance._video_height_px = analysis.calibration_params.video_height_px

        instance.report = analysis.report
        instance.b_analyzer = analysis.behavioral_analyzer
        instance.r_analyzer = analysis.roi_analyzer
        instance.behavioral_config = analysis.behavioral_config or {}

        instance.sharp_turn_threshold = analysis.sharp_turn_threshold
        instance.freezing_threshold = analysis.freezing_threshold
        instance.freezing_duration = analysis.freezing_duration
        instance.validation_warnings = getattr(analysis, "validation_warnings", [])
        instance.validation_stats = getattr(analysis, "validation_stats", {})

        instance._init_shared_components()
        return instance

    # ------------------------------------------------------------------
    # Shared initialisation (used by both construction paths)
    # ------------------------------------------------------------------
    def _init_shared_components(self) -> None:
        """Create ``DataTransformer``, ``VisualizationGenerator`` and tidy DF."""
        self.data_transformer = DataTransformer()
        self.viz_generator = VisualizationGenerator(
            b_analyzer=self.b_analyzer,
            r_analyzer=self.r_analyzer,
            metadata=self.metadata or {},
            roi_colors=self.roi_colors,
            calibration=self.calibration,
            pixelcm_x=self._pixelcm_x,
            pixelcm_y=self._pixelcm_y,
            video_height_px=self._video_height_px,
            sharp_turn_threshold=self.sharp_turn_threshold,
            settings_obj=self.settings,
            frame_crop_box=self.frame_crop_box,
            behavioral_config=self.behavioral_config,
        )

        tidy_df = self.data_transformer.create_tidy_dataframe(
            report=self.report,
            metadata=self.metadata or {},
            b_analyzer=self.b_analyzer,
            r_analyzer=self.r_analyzer,
            roi_colors=self.roi_colors,
            validation_stats=self.validation_stats,
            behavioral_config=self.behavioral_config,
        )
        self.tidy_data = self.data_transformer.standardize_tidy_dataframe(
            tidy_df, self.metadata or {}
        )

    # ------------------------------------------------------------------
    # Utilities shared across reporters
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_aquarium_perspective(perspective: str | None) -> str:
        """Normalize perspective aliases to canonical names.

        Delegates to :func:`zebtrack.analysis.perspective_utils.normalize_aquarium_perspective`.
        """
        from zebtrack.analysis.perspective_utils import normalize_aquarium_perspective

        return normalize_aquarium_perspective(perspective)
