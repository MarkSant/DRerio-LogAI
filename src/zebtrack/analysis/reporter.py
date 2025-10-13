import gettext
import io
import locale
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, cast

import cv2
import matplotlib

matplotlib.use('Agg')  # Use non-interactive backend to avoid GUI thread warnings
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import structlog
from docx import Document
from docx.shared import Inches
from docxtpl import DocxTemplate
from matplotlib import patches
from matplotlib.axes import Axes
from matplotlib.colorbar import Colorbar
from matplotlib.figure import Figure
from scipy.ndimage import gaussian_filter

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.analysis.roi import ROI

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


def _(message: str) -> str:  # noqa: N802 - conventional gettext alias
    return _translator(message)

COLUMN_MAPPING = {
    "distancia_total_cm": "total_distance_cm",
    "velocidade_media_cm_s": "mean_speed_cm_s",
    "velocidade_mediana_cm_s": "median_speed_cm_s",
    "desvio_padrao_velocidade_cm_s": "speed_std_dev_cm_s",
    "contagem_curvas_acentuadas": "sharp_turns_count",
    "curvas_acentuadas_por_minuto": "sharp_turns_per_minute",
    "total_entradas_roi": "total_roi_entries",
    "data_hora_analise": "analysis_timestamp",
    "rajadas_velocidade_contagem": "speed_burst_count",
    "rajadas_velocidade_duracao_total_s": "speed_burst_total_duration_s",
    "rajadas_velocidade_limiar_cm_s": "speed_burst_threshold_cm_s",
    "periodos_inatividade_contagem": "inactivity_count",
    "periodos_inatividade_duracao_total_s": "inactivity_total_duration_s",
    "periodos_inatividade_percentual_registro": "inactivity_percentage_of_recording",
    "periodos_inatividade_limiar_cm_s": "inactivity_threshold_cm_s",
}

DYNAMIC_PREFIX_MAPPINGS = (
    ("tempo_no_", "time_in_"),
    ("percentual_tempo_no_", "time_percentage_in_"),
    ("entradas_no_", "entries_in_"),
    ("saidas_do_", "exits_from_"),
    ("latencia_para_", "latency_to_"),
    ("distancia_no_", "distance_in_"),
    ("velocidade_media_no_", "mean_speed_in_"),
    ("episodios_congelamento_no_", "freezing_events_in_"),
    ("duracao_total_congelamento_no_", "freezing_duration_in_"),
    ("cor_roi_", "roi_color_"),
)

GROUP_ID_FALLBACK_KEYS = ("group", "grupo", "grupo_id", "group_name")

REQUIRED_COLUMNS = (
    "experiment_id",
    "group_id",
    "analysis_timestamp",
    "total_distance_cm",
    "mean_speed_cm_s",
)


def _rgb_to_color_name(rgb_tuple):
    """
    Convert RGB tuple to closest color name.
    Returns a descriptive name for the color.
    """
    if not isinstance(rgb_tuple, (tuple, list)) or len(rgb_tuple) != 3:
        return str(rgb_tuple)

    # Common color names mapping
    color_map = {
        (255, 0, 0): "Red",
        (0, 255, 0): "Green",
        (0, 0, 255): "Blue",
        (255, 255, 0): "Yellow",
        (255, 0, 255): "Magenta",
        (0, 255, 255): "Cyan",
        (255, 165, 0): "Orange",
        (128, 0, 128): "Purple",
        (255, 192, 203): "Pink",
        (165, 42, 42): "Brown",
        (128, 128, 128): "Gray",
        (0, 0, 0): "Black",
        (255, 255, 255): "White",
    }

    # Find closest color
    r, g, b = rgb_tuple
    min_distance = float('inf')
    closest_name = f"RGB({r},{g},{b})"

    for rgb, name in color_map.items():
        distance = sum((a - b) ** 2 for a, b in zip(rgb_tuple, rgb))
        if distance < min_distance:
            min_distance = distance
            closest_name = name

    # If very close match (within 30 units squared), use the name
    return closest_name if min_distance < 900 else f"RGB({r},{g},{b})"


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


def _normalize_color_for_matplotlib(color):
    """
    Normalize color to matplotlib format (0-1 range).

    Handles different input formats:
    - RGB tuple (0-255): convert to (0-1)
    - String/named color: return as-is
    - Already normalized (0-1): return as-is
    """
    if isinstance(color, (tuple, list)) and len(color) == 3:
        # Check if values are in 0-255 range (need normalization)
        # If any value is > 1, assume it's in 0-255 range
        if any(isinstance(c, (int, float)) and c > 1 for c in color):
            return tuple(c / 255.0 for c in color)
        else:
            # Already normalized or mixed values
            return color
    # String colors or other formats - return as-is
    return color


class Reporter:
    def __init__(
        self,
        trajectory_df: pd.DataFrame,
        metadata: dict,
        # Calibration and setup
        pixelcm_x: float,
        pixelcm_y: float,
        video_height_px: int,
        arena_polygon_px: list[tuple[float, float]],
        rois: list[ROI],
        fps: float,
        # Optional params
        roi_colors: dict | None = None,
        video_path: str | None = None,
        calibration = None,
        # Analysis params
        sharp_turn_threshold: float = 90.0,
        freezing_threshold: float = 1.5,
        freezing_duration: float = 1.0,
        smoothing_window_length: int | None = None,
        smoothing_polyorder: int | None = None,
    ):
        self.metadata = metadata
        self.roi_colors = roi_colors if roi_colors else {}
        self.video_path = video_path
        self.calibration = calibration

        # Ensure trajectory coordinates stay aligned with calibration space
        # before running any calculations.
        if calibration is not None:
            trajectory_df = self._warp_trajectory_if_needed(
                trajectory_df, calibration
            )

        if "track_id" in trajectory_df.columns:
            track_ids = pd.to_numeric(trajectory_df["track_id"], errors="coerce")
            trajectory_df = trajectory_df.copy()
            trajectory_df["track_id"] = track_ids.astype("Int64")

        # Run the unified analysis via the service
        service = AnalysisService()
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

        # Generate the tidy dataframe from the report
        tidy_df = self._create_tidy_dataframe()
        self.tidy_data = self._standardize_tidy_dataframe(tidy_df)

    @staticmethod
    def _warp_trajectory_if_needed(
        trajectory_df: pd.DataFrame, calibration
    ) -> pd.DataFrame:
        """Warp bounding boxes into the calibrated space when raw points slip through.

    Some runs saved detections using the original video reference instead of the
    warped view. Metrics then break because coordinates no longer align with the
    arena and ROI polygons.

    We detect the mismatch when any bbox coordinate exceeds the expected warped
    dimensions. In that case we transform every bbox with the calibration
    homography so downstream analysis always operates in the calibrated frame.
        """

        homography = getattr(calibration, "homography_matrix", None)
        if calibration is None or homography is None:
            return trajectory_df

        expected_width, expected_height = calibration.target_dims_px
        if not expected_width or not expected_height:
            return trajectory_df

        required_columns = {"x1", "y1", "x2", "y2"}
        if not required_columns.issubset(trajectory_df.columns):
            return trajectory_df

        tolerance = 2.0

        def _max_safe(series_name: str) -> float:
            if series_name not in trajectory_df.columns:
                return float("-inf")
            series = trajectory_df[series_name]
            if series.empty:
                return float("-inf")
            return float(series.max(skipna=True))

        max_x = max(
            _max_safe(col)
            for col in ("x1", "x2", "x_center_px")
        )
        max_y = max(
            _max_safe(col)
            for col in ("y1", "y2", "y_center_px")
        )

        if max_x <= expected_width + tolerance and max_y <= expected_height + tolerance:
            return trajectory_df

        warped_df = trajectory_df.copy()

        x1_values = warped_df["x1"].to_numpy(copy=True)
        y1_values = warped_df["y1"].to_numpy(copy=True)
        x2_values = warped_df["x2"].to_numpy(copy=True)
        y2_values = warped_df["y2"].to_numpy(copy=True)

        for i, (x1, y1, x2, y2) in enumerate(
            zip(x1_values, y1_values, x2_values, y2_values)
        ):
            if any(pd.isna(v) for v in (x1, y1, x2, y2)):
                continue

            x1_w, y1_w, x2_w, y2_w = calibration.transform_bbox(x1, y1, x2, y2)
            x1_values[i] = x1_w
            y1_values[i] = y1_w
            x2_values[i] = x2_w
            y2_values[i] = y2_w

        warped_df["x1"] = x1_values
        warped_df["y1"] = y1_values
        warped_df["x2"] = x2_values
        warped_df["y2"] = y2_values

        # Recompute derived centers after the warp
        warped_df["x_center_px"] = (
            warped_df[["x1", "x2"]].mean(axis=1)
        )
        warped_df["y_center_px"] = (
            warped_df[["y1", "y2"]].mean(axis=1)
        )

        # Drop any stale cm columns – they will be recomputed by the analyzer
        for col in ("x_cm", "y_cm"):
            if col in warped_df.columns:
                warped_df.drop(columns=col, inplace=True)

        return warped_df

    def _create_tidy_dataframe(self) -> pd.DataFrame:
        """Creates a flat, tidy DataFrame from the structured report dictionary."""
        # Start with metadata
        combined_data = {**self.metadata}

        # --- General Behavioral Metrics ---
        general_behavior = self.report.get("comportamento_geral", {})
        combined_data["distancia_total_cm"] = general_behavior.get("distancia_total_cm")
        velocity_stats = general_behavior.get("estatisticas_velocidade", {})
        combined_data["velocidade_media_cm_s"] = velocity_stats.get("mean")
        combined_data["velocidade_mediana_cm_s"] = velocity_stats.get("median")
        combined_data["desvio_padrao_velocidade_cm_s"] = velocity_stats.get("std_dev")

        sharp_turns = general_behavior.get("curvas_acentuadas", {})
        combined_data["contagem_curvas_acentuadas"] = sharp_turns.get(
            "sharp_turns_count"
        )
        combined_data["curvas_acentuadas_por_minuto"] = sharp_turns.get(
            "sharp_turns_per_minute"
        )
        speed_bursts = general_behavior.get("rajadas_velocidade", {})
        combined_data["rajadas_velocidade_contagem"] = speed_bursts.get("count")
        combined_data["rajadas_velocidade_duracao_total_s"] = speed_bursts.get(
            "total_duration_s"
        )
        combined_data["rajadas_velocidade_limiar_cm_s"] = speed_bursts.get(
            "threshold_cm_s"
        )

        inactivity = general_behavior.get("periodos_inatividade", {})
        combined_data["periodos_inatividade_contagem"] = inactivity.get("count")
        combined_data["periodos_inatividade_duracao_total_s"] = inactivity.get(
            "total_duration_s"
        )
        combined_data["periodos_inatividade_percentual_registro"] = inactivity.get(
            "percentage_of_recording"
        )
        combined_data["periodos_inatividade_limiar_cm_s"] = inactivity.get(
            "threshold_cm_s"
        )

        # --- ROI-Specific Metrics (only if ROI analysis was performed) ---
        if self.r_analyzer:
            roi_analysis = self.report.get("analise_roi", {})
            time_spent = roi_analysis.get("tempo_gasto_por_roi", {})
            entry_counts = roi_analysis.get("contagem_entradas", {})
            exit_counts = roi_analysis.get("contagem_saidas", {})
            latencies = roi_analysis.get("latencia_primeira_entrada", {})
            distances = roi_analysis.get("distancia_por_roi", {})
            velocities = roi_analysis.get("estatisticas_velocidade_por_roi", {})
            freezing = roi_analysis.get("congelamento_por_roi", {})

            total_roi_entries = 0
            for roi_name in self.r_analyzer.rois:
                # Time spent
                combined_data[f"tempo_no_{roi_name}_s"] = time_spent.get(
                    roi_name, {}
                ).get("seconds")
                combined_data[f"percentual_tempo_no_{roi_name}"] = time_spent.get(
                    roi_name, {}
                ).get("percentage")
                # Entry and Exit counts
                entries = entry_counts.get(roi_name, 0)
                combined_data[f"entradas_no_{roi_name}"] = entries
                total_roi_entries += entries
                combined_data[f"saidas_do_{roi_name}"] = exit_counts.get(roi_name, 0)
                # Latency
                combined_data[f"latencia_para_{roi_name}_s"] = latencies.get(roi_name)
                # Intra-ROI Distance
                combined_data[f"distancia_no_{roi_name}_cm"] = distances.get(roi_name)
                # Intra-ROI Velocity
                roi_vel = velocities.get(roi_name)
                if roi_vel:
                    combined_data[f"velocidade_media_no_{roi_name}_cm_s"] = roi_vel.get(
                        "mean"
                    )
                # Intra-ROI Freezing
                roi_freeze = freezing.get(roi_name)
                if roi_freeze:
                    combined_data[f"episodios_congelamento_no_{roi_name}"] = (
                        roi_freeze.get("count")
                    )
                    combined_data[f"duracao_total_congelamento_no_{roi_name}_s"] = (
                        roi_freeze.get("total_duration")
                    )
                # ROI Color - convert to color name
                if roi_name in self.roi_colors:
                    combined_data[f"cor_roi_{roi_name}"] = _rgb_to_color_name(
                        self.roi_colors[roi_name]
                    )

            combined_data["total_entradas_roi"] = total_roi_entries
        combined_data["data_hora_analise"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        combined_data["group_id"] = self._resolve_group_id(combined_data)
        return pd.DataFrame([combined_data])

    def _resolve_group_id(self, combined_data: dict) -> str:
        """Ensures the summary dataframe includes a populated group_id column."""
        group_id = combined_data.get("group_id") or self.metadata.get("group_id")
        if group_id:
            return str(group_id)

        for key in GROUP_ID_FALLBACK_KEYS:
            candidate = combined_data.get(key) or self.metadata.get(key)
            if candidate:
                return str(candidate)

        return "unassigned"

    @staticmethod
    def _translate_column_name(column_name: str) -> str:
        if column_name in COLUMN_MAPPING:
            return COLUMN_MAPPING[column_name]

        for prefix, replacement in DYNAMIC_PREFIX_MAPPINGS:
            if column_name.startswith(prefix):
                suffix = column_name[len(prefix) :]
                return f"{replacement}{suffix}"

        return column_name

    def _standardize_tidy_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        standardized_df = df.copy()

        rename_map = {}
        for column in standardized_df.columns:
            translated = self._translate_column_name(column)
            if translated != column:
                rename_map[column] = translated

        if rename_map:
            standardized_df = standardized_df.rename(columns=rename_map)

        if "experiment_id" not in standardized_df.columns:
            experiment_id = (
                self.metadata.get("experiment_id")
                or self.metadata.get("video_name")
                or self.metadata.get("experiment_name")
                or self.metadata.get("name")
            )
            standardized_df["experiment_id"] = experiment_id or "unknown"

        standardized_df["experiment_id"] = (
            standardized_df["experiment_id"].fillna("unknown").astype(str)
        )

        if "group_id" not in standardized_df.columns:
            standardized_df["group_id"] = self._resolve_group_id(
                standardized_df.iloc[0].to_dict()
            )

        standardized_df["group_id"] = (
            standardized_df["group_id"].fillna("unassigned").astype(str)
        )

        self._validate_schema(standardized_df)
        return standardized_df

    def _validate_schema(self, df: pd.DataFrame):
        missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_columns:
            raise ValueError(
                "Reporter summary is missing required columns: "
                + ", ".join(sorted(missing_columns))
            )

    def export_summary_data(self, output_path: str, format: str = "excel"):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._validate_schema(self.tidy_data)
        if format == "excel":
            self.tidy_data.to_excel(output_path, index=False, engine="openpyxl")
        elif format == "csv":
            self.tidy_data.to_csv(output_path, index=False)
        elif format == "parquet":
            self.tidy_data.to_parquet(output_path, index=False)
        else:
            raise ValueError(f"Unsupported file format: {format}")

    def generate_trajectory_plot(
        self, ax: Axes | None = None, video_path: str | None = None
    ) -> Figure:
        fig_obj = ax.get_figure() if ax else plt.figure(figsize=(6, 6))
        fig = cast(Figure, fig_obj)
        ax = ax or fig.add_subplot(111)
        ax.clear()

        traj_data = self.b_analyzer.trajectory_data
        x = traj_data["x_cm_smoothed"]
        y = traj_data["y_cm_smoothed"]
        arena_poly_cm = self.b_analyzer.arena_polygon_cm
        min_x, min_y, max_x, max_y = arena_poly_cm.bounds

        # Get video dimensions if available
        if video_path and Path(video_path).exists():
            cap = cv2.VideoCapture(video_path)
            ret, frame = cap.read()
            if ret:
                # Apply perspective warp if calibration is available
                if self.calibration:
                    frame = self.calibration.warp_frame(frame)

                frame_height_px = frame.shape[0]
                frame_width_px = frame.shape[1]
                # Calculate proper extent based on pixel-to-cm conversion
                pixelcm_x = self.b_analyzer._pixelcm_x
                pixelcm_y = self.b_analyzer._pixelcm_y

                # Frame coordinates in cm
                # Per COORDINATE_SYSTEMS.md:
                # - Frame warped: y_px=0 at top, y_px=height at bottom
                #   (image convention)
                # - Trajectory y_cm: y_cm=0 at bottom, y_cm=max at top
                #   (cartesian)
                # - Conversion: y_cm = (video_height_px - y_center_px) / pixelcm_y
                #
                # To align frame with trajectories:
                # 1. Flip frame vertically so frame[0] = bottom
                # 2. Use origin='lower' so matplotlib maps frame[0] to y=0 (bottom)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame_rgb_flipped = cv2.flip(frame_rgb, 0)  # Flip vertically

                frame_extent: tuple[float, float, float, float] = (
                    0.0,  # left (x=0)
                    frame_width_px / pixelcm_x,  # right (x=max)
                    0.0,  # bottom (y=0)
                    frame_height_px / pixelcm_y,  # top (y=max)
                )
                ax.imshow(
                    frame_rgb_flipped,
                    extent=frame_extent,
                    origin='lower',
                    aspect="auto",
                    alpha=0.5,
                )
            cap.release()

        ax.set_facecolor("lightgray")
        # Draw arena boundary
        ax.add_patch(
            patches.Polygon(
                arena_poly_cm.exterior.coords, fill=False, edgecolor="black", lw=2
            )
        )

        # Draw ROIs if available
        if self.r_analyzer:
            for roi_name, roi in self.r_analyzer.rois.items():
                roi_color = self.roi_colors.get(roi_name, "blue")
                normalized_color = _normalize_color_for_matplotlib(roi_color)
                ax.add_patch(
                    patches.Polygon(
                        roi.geometry.exterior.coords,
                        fill=True,
                        color=normalized_color,
                        alpha=0.3,
                        edgecolor=normalized_color,
                        linewidth=2,
                    )
                )

        # Draw trajectory - use single color for single animal
        ax.plot(x, y, color="blue", linewidth=1.5, alpha=0.7, label="Trajectory")

        ax.set_title(f"Trajectory - {self.metadata.get('experiment_id', 'Unknown')}")
        ax.set_xlabel("Position (cm)")
        ax.set_ylabel("Position (cm)")
        ax.set_xlim(min_x - 1, max_x + 1)
        ax.set_ylim(min_y - 1, max_y + 1)
        ax.set_aspect("equal", adjustable="box")
        return fig

    def generate_heatmap(self, ax: Axes | None = None) -> Figure:
        fig_obj = ax.get_figure() if ax else plt.figure(figsize=(6, 6))
        fig = cast(Figure, fig_obj)
        ax = ax or fig.add_subplot(111)
        ax.clear()

        traj_data = self.b_analyzer.trajectory_data
        x = traj_data["x_cm_smoothed"]
        y = traj_data["y_cm_smoothed"]
        arena_poly_cm = self.b_analyzer.arena_polygon_cm
        min_x, min_y, max_x, max_y = arena_poly_cm.bounds

        heatmap, xedges, yedges = np.histogram2d(
            x, y, bins=50, range=[[min_x, max_x], [min_y, max_y]]
        )
        heatmap = gaussian_filter(heatmap.T, sigma=2)
        extent: tuple[float, float, float, float] = (
            float(xedges[0]),
            float(xedges[-1]),
            float(yedges[0]),
            float(yedges[-1]),
        )
        im = ax.imshow(
            heatmap,
            cmap="hot",
            origin="lower",
            extent=extent,
        )
        ax.set_title(f"Heatmap - {self.metadata.get('experiment_id', 'Unknown')}")
        ax.set_xlabel("Position (cm)")
        ax.set_ylabel("Position (cm)")
        ax.set_xlim(min_x - 1, max_x + 1)
        ax.set_ylim(min_y - 1, max_y + 1)
        ax.set_aspect("equal", adjustable="box")
        existing_artists = getattr(fig, "artists", [])
        if not any(isinstance(artist, Colorbar) for artist in existing_artists):
            fig.colorbar(im, ax=ax, label="Occupancy Density")
        return fig

    def generate_roi_reference_plot(self, ax: Axes | None = None) -> Figure:
        fig_obj = ax.get_figure() if ax else plt.figure(figsize=(6, 6))
        fig = cast(Figure, fig_obj)
        ax = ax or fig.add_subplot(111)
        ax.clear()

        arena_poly_cm = self.b_analyzer.arena_polygon_cm
        min_x, min_y, max_x, max_y = arena_poly_cm.bounds

        ax.set_facecolor("lightgray")
        ax.add_patch(
            patches.Polygon(
                arena_poly_cm.exterior.coords, fill=False, edgecolor="black", lw=2
            )
        )

        if self.r_analyzer:
            for i, (roi_name, roi) in enumerate(self.r_analyzer.rois.items()):
                roi_color = self.roi_colors.get(roi_name, "blue")
                # Normalize color for matplotlib (0-255 RGB tuples -> 0-1 range)
                normalized_color = _normalize_color_for_matplotlib(roi_color)
                ax.add_patch(
                    patches.Polygon(
                        roi.geometry.exterior.coords,
                        fill=True,
                        color=normalized_color,
                        alpha=0.4,
                    )
                )
                centroid = roi.geometry.centroid
                ax.text(
                    centroid.x,
                    centroid.y,
                    str(i + 1),
                    color="white",
                    ha="center",
                    va="center",
                    fontweight="bold",
                    fontsize=12,
                    bbox=dict(
                        facecolor=normalized_color,
                        alpha=0.7,
                        boxstyle="circle,pad=0.2",
                        ec="none",
                    ),
                )
        else:
            ax.text(
                0.5,
                0.5,
                "No ROIs defined for this analysis.",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )

        title = (
            f"ROI Reference Map - {self.metadata.get('experiment_id', 'Unknown')}"
        )
        ax.set_title(title)
        ax.set_xlabel("Position (cm)")
        ax.set_ylabel("Position (cm)")
        ax.set_xlim(min_x - 1, max_x + 1)
        ax.set_ylim(min_y - 1, max_y + 1)
        ax.set_aspect("equal", adjustable="box")
        return fig

    def generate_angular_velocity_plot(self, ax: Axes | None = None) -> Figure:
        fig_obj = ax.get_figure() if ax else plt.figure(figsize=(12, 6))
        fig = cast(Figure, fig_obj)
        ax = ax or fig.add_subplot(111)
        ax.clear()

        angular_velocity = self.b_analyzer.get_angular_velocity()
        if angular_velocity.empty or angular_velocity.isna().all():
            ax.text(
                0.5,
                0.5,
                "Not enough data for angular velocity.",
                ha="center",
                va="center",
            )
            ax.set_title("Angular Velocity")
            return fig

        sharp_turn_results = self.b_analyzer.calculate_sharp_turns(
            self.sharp_turn_threshold
        )
        sharp_turn_times = cast(
            pd.Series, sharp_turn_results["sharp_turns_timestamps"]
        )

        time_seconds = (
            angular_velocity.index - angular_velocity.index[0]
        ).total_seconds()

        ax.plot(time_seconds, angular_velocity, label="Angular Velocity")

        if not sharp_turn_times.empty:
            sharp_turn_values = angular_velocity.loc[sharp_turn_times]
            sharp_turn_time_seconds = (
                sharp_turn_times - angular_velocity.index[0]
            ).total_seconds()
            ax.plot(
                sharp_turn_time_seconds,
                sharp_turn_values,
                "ro",
                markersize=5,
                label="Sharp Turns",
            )

        title = f"Angular Velocity - {self.metadata.get('experiment_id', 'Unknown')}"
        ax.set_title(title)
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Angular Velocity (deg/s)")
        ax.legend()
        ax.grid(True)
        return fig

    def generate_position_vs_time_plot(self, ax: Axes | None = None) -> Figure:
        fig_obj = ax.get_figure() if ax else plt.figure(figsize=(12, 6))
        fig = cast(Figure, fig_obj)
        ax = ax or fig.add_subplot(111)
        ax.clear()

        traj_data = self.b_analyzer.trajectory_data
        if traj_data.empty:
            ax.text(0.5, 0.5, "No trajectory data.", ha="center", va="center")
            ax.set_title("Position vs. Time")
            return fig

        time_seconds = (traj_data.index - traj_data.index[0]).total_seconds()

        ax.plot(time_seconds, traj_data["x_cm_smoothed"], label="X coordinate (cm)")
        ax.plot(time_seconds, traj_data["y_cm_smoothed"], label="Y coordinate (cm)")

        title = (
            f"Position vs. Time - {self.metadata.get('experiment_id', 'Unknown')}"
        )
        ax.set_title(title)
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Position (cm)")
        ax.legend()
        ax.grid(True)
        return fig

    def generate_cumulative_distance_plot(self, ax: Axes | None = None) -> Figure:
        fig_obj = ax.get_figure() if ax else plt.figure(figsize=(12, 6))
        fig = cast(Figure, fig_obj)
        ax = ax or fig.add_subplot(111)
        ax.clear()

        traj_data = self.b_analyzer.trajectory_data
        if len(traj_data) < 2:
            ax.text(
                0.5,
                0.5,
                "Not enough data for distance calculation.",
                ha="center",
                va="center",
            )
            ax.set_title("Cumulative Distance")
            return fig

        x_smoothed = pd.to_numeric(
            cast(pd.Series, traj_data["x_cm_smoothed"]), errors="coerce"
        ).diff()
        y_smoothed = pd.to_numeric(
            cast(pd.Series, traj_data["y_cm_smoothed"]), errors="coerce"
        ).diff()
        distance_array = np.sqrt(
            np.square(x_smoothed.to_numpy()) + np.square(y_smoothed.to_numpy())
        )
        distances = pd.Series(distance_array, index=x_smoothed.index)
        cumulative_distance = distances.cumsum().fillna(0)
        time_seconds = (traj_data.index - traj_data.index[0]).total_seconds()

        ax.plot(time_seconds, cumulative_distance)
        title = _(
            "Cumulative Distance vs. Time - {experiment_id}"
        ).format(experiment_id=self.metadata.get("experiment_id", "Unknown"))
        ax.set_title(title)
        ax.set_xlabel(_("Time (s)"))
        ax.set_ylabel(_("Cumulative Distance (cm)"))
        ax.grid(True)
        return fig

    def export_individual_report(self, output_path: str):
        """
        Exports a complete individual report. This is a convenience wrapper
        around the step-by-step method for consumers who don't need progress updates.
        """
        self.export_individual_report_step_by_step(output_path, lambda p, s: None)

    def export_individual_report_step_by_step(
        self, output_path: str, progress_callback
    ):
        total_steps = 10
        template_path = INDIVIDUAL_REPORT_TEMPLATE
        heading_text = _(
            "Analysis Report - {experiment_id}"
        ).format(experiment_id=self.metadata.get("experiment_id", "Unknown"))

        doc_template: DocxTemplate | None = None
        document: Document

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

        if doc_template is None:
            document.add_heading(heading_text, level=1)

        # Step 1: Metadata section
        document.add_heading(_("Experiment Metadata"), level=2)
        for key, value in self.metadata.items():
            document.add_paragraph(
                f"{key.replace('_', ' ').title()}: {value}"
            )
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

        # Step 3: ROI Reference Map (optional)
        if self.r_analyzer:
            document.add_heading(_("ROI Reference Map"), level=2)
            fig = self.generate_roi_reference_plot()
            memfile = io.BytesIO()
            fig.savefig(memfile, format="png", dpi=300, bbox_inches="tight")
            plt.close(fig)
            memfile.seek(0)
            document.add_picture(memfile, width=Inches(6.5))
        progress_callback(3 / total_steps, _("ROI map added"))

        # Step 4-8: Visualization plots
        document.add_heading(_("Visualizations"), level=2)
        plot_configs = [
            (
                lambda ax: self.generate_trajectory_plot(ax, self.video_path),
                _("Trajectory"),
            ),
            (self.generate_heatmap, _("Heatmap")),
            (self.generate_position_vs_time_plot, _("Position vs. Time")),
            (self.generate_cumulative_distance_plot, _("Cumulative Distance")),
            (self.generate_angular_velocity_plot, _("Angular Velocity")),
        ]

        for i, (plot_func, name) in enumerate(plot_configs):
            fig, ax = plt.subplots(figsize=(10, 6))
            plot_func(ax)
            memfile = io.BytesIO()
            fig.savefig(memfile, format="png", dpi=300, bbox_inches="tight")
            plt.close(fig)
            memfile.seek(0)
            document.add_paragraph(_("Chart: {name}:").format(name=name))
            document.add_picture(memfile, width=Inches(6.0))
            progress_callback(
                (4 + i) / total_steps,
                _("Visualization added: {name}").format(name=name),
            )

        # Step 9: ROI Event Log
        if self.r_analyzer:
            document.add_page_break()
            document.add_heading(_("Appendix: ROI Event Log"), level=2)
            event_log_df = self.r_analyzer.get_event_log()
            if not event_log_df.empty:
                document.add_paragraph(
                    _(
                        "Chronological log of all entries and exits from defined ROIs."
                    )
                )

                event_log_df = event_log_df.rename(
                    columns={"roi_name": "ROI", "event": _("Event")}
                )

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
                document.add_paragraph(
                    _("No ROI entry or exit events were recorded.")
                )
        progress_callback(9 / total_steps, _("Event log added"))

        # Step 10: Save the document
        file_path = str(output_path)
        if doc_template is not None:
            doc_template.save(file_path)
        else:
            document.save(file_path)
        progress_callback(10 / total_steps, _("Report saved"))
        log.info("analysis.reporter.individual_saved", path=file_path)

    @staticmethod
    def _generate_comparative_boxplot(
        df: pd.DataFrame, metric: str, title: str
    ) -> Figure:
        fig, ax = plt.subplots(figsize=(8, 6))
        sns.boxplot(x="group_id", y=metric, data=df, ax=ax)
        sns.stripplot(x="group_id", y=metric, data=df, ax=ax, color=".25", size=6)
        ax.set_title(title, fontsize=16)
        ax.set_xlabel("Experimental Group", fontsize=12)
        ax.set_ylabel(metric.replace("_", " ").title(), fontsize=12)
        plt.tight_layout()
        return fig

    @staticmethod
    def export_project_report(aggregated_df: pd.DataFrame, output_path: str):
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
                boxplot_fig = Reporter._generate_comparative_boxplot(
                    aggregated_df,
                    metric,
                    title,
                )
                memfile = io.BytesIO()
                boxplot_fig.savefig(memfile, format="png", dpi=300, bbox_inches="tight")
                plt.close(boxplot_fig)
                memfile.seek(0)
                document.add_paragraph(title, style="Heading 3")
                document.add_picture(memfile, width=Inches(6.0))

        file_path = f"{output_path}.docx"
        document.save(file_path)
        print(f"Project report saved to: {file_path}")
