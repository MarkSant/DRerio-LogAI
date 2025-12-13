"""Data transformation service for analysis results.

This module handles the transformation of analysis results into standardized
tidy dataframes suitable for export and reporting.

Extracted from reporter.py as part of Phase 2 refactoring (Task 2.5).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import structlog

from zebtrack.analysis.behavior import BehavioralAnalyzer
from zebtrack.analysis.roi import ROIAnalyzer

__all__ = ["DataTransformer"]

log = structlog.get_logger(__name__)

# Color matching threshold for RGB space (30² in RGB space, 0-255 range)
# Note: Using Euclidean distance in RGB space is not perceptually uniform.
# Small changes in blue are more noticeable than similar changes in green.
# For better color matching, consider LAB or HSV color spaces in the future.
RGB_COLOR_MATCH_THRESHOLD = 900

# Column name mappings for Portuguese → English translation
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

# Dynamic prefix mappings for Portuguese → English translation of ROI-specific columns
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

# Fallback keys to search for group ID in metadata when not explicitly provided
GROUP_ID_FALLBACK_KEYS = ("group", "grupo", "grupo_id", "group_name")

# Required columns that must be present in standardized tidy dataframes
REQUIRED_COLUMNS = (
    "experiment_id",
    "group_id",
    "analysis_timestamp",
    "total_distance_cm",
    "mean_speed_cm_s",
)


def _rgb_to_color_name(rgb_tuple):
    """Convert RGB tuple to closest color name.

    Uses Euclidean distance in RGB space to find the closest named color.

    Note: This method uses RGB color space which is not perceptually uniform.
    Small changes in blue are more noticeable than similar changes in green.
    For more accurate color matching, consider LAB or HSV color spaces.

    Args:
        rgb_tuple: RGB color as tuple/list of 3 values (0-255 range)

    Returns:
        str: Closest color name or RGB string if no close match found
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
    min_distance = float("inf")
    closest_name = f"RGB({r},{g},{b})"

    for rgb, name in color_map.items():
        distance = sum((a - b) ** 2 for a, b in zip(rgb_tuple, rgb, strict=False))
        if distance < min_distance:
            min_distance = distance
            closest_name = name

    # If close match (within threshold), use the name; otherwise return RGB string
    return closest_name if min_distance < RGB_COLOR_MATCH_THRESHOLD else f"RGB({r},{g},{b})"


class DataTransformer:
    """Transforms analysis results into standardized tidy dataframes.

    This class handles all data transformation logic for converting structured
    analysis reports into flat, tidy dataframes suitable for export and
    statistical analysis.

    Responsibilities:
        - Create tidy dataframes from structured reports
        - Collect and organize ROI-specific metrics
        - Standardize column names (Portuguese → English)
        - Validate dataframe schemas
        - Resolve group IDs from various sources

    Example:
        >>> transformer = DataTransformer()
        >>> tidy_df = transformer.create_tidy_dataframe(
        ...     report=analysis_report,
        ...     metadata={"experiment_id": "exp_001"},
        ...     b_analyzer=behavior_analyzer,
        ...     r_analyzer=roi_analyzer,
        ...     roi_colors={"roi1": (255, 0, 0)}
        ... )
        >>> standardized_df = transformer.standardize_tidy_dataframe(tidy_df, metadata)

    Note:
        This class is stateless and does not require initialization.
        All methods can be called on a fresh instance.
    """

    def create_tidy_dataframe(
        self,
        report: dict[str, Any],
        metadata: dict[str, Any],
        b_analyzer: BehavioralAnalyzer,
        r_analyzer: ROIAnalyzer | None = None,
        roi_colors: dict[str, tuple[int, int, int]] | None = None,
    ) -> pd.DataFrame:
        """Create a flat, tidy DataFrame from the structured report dictionary.

        Args:
            report: Structured analysis report dictionary
            metadata: Experiment metadata
            b_analyzer: BehavioralAnalyzer instance with trajectory data
            r_analyzer: ROIAnalyzer instance (optional)
            roi_colors: Dictionary mapping ROI names to RGB tuples (optional)

        Returns:
            pd.DataFrame: Tidy dataframe with one row per experiment
        """
        # Start with metadata
        combined_data = {**metadata}

        # --- General Behavioral Metrics ---
        general_behavior = report.get("comportamento_geral", {})
        combined_data["distancia_total_cm"] = general_behavior.get("distancia_total_cm")
        velocity_stats = general_behavior.get("estatisticas_velocidade", {})
        combined_data["velocidade_media_cm_s"] = velocity_stats.get("mean")
        combined_data["velocidade_mediana_cm_s"] = velocity_stats.get("median")
        combined_data["desvio_padrao_velocidade_cm_s"] = velocity_stats.get("std_dev")

        sharp_turns = general_behavior.get("curvas_acentuadas", {})
        combined_data["contagem_curvas_acentuadas"] = sharp_turns.get("sharp_turns_count")
        combined_data["curvas_acentuadas_por_minuto"] = sharp_turns.get("sharp_turns_per_minute")
        speed_bursts = general_behavior.get("rajadas_velocidade", {})
        combined_data["rajadas_velocidade_contagem"] = speed_bursts.get("count")
        combined_data["rajadas_velocidade_duracao_total_s"] = speed_bursts.get("total_duration_s")
        combined_data["rajadas_velocidade_limiar_cm_s"] = speed_bursts.get("threshold_cm_s")

        inactivity = general_behavior.get("periodos_inatividade", {})
        combined_data["periodos_inatividade_contagem"] = inactivity.get("count")
        combined_data["periodos_inatividade_duracao_total_s"] = inactivity.get("total_duration_s")
        combined_data["periodos_inatividade_percentual_registro"] = inactivity.get(
            "percentage_of_recording"
        )
        combined_data["periodos_inatividade_limiar_cm_s"] = inactivity.get("threshold_cm_s")

        # --- ROI-Specific Metrics (only if ROI analysis was performed) ---
        if r_analyzer:
            roi_colors_dict = roi_colors if roi_colors else {}
            combined_data = self._collect_roi_metrics(
                combined_data, report, r_analyzer, roi_colors_dict
            )

        combined_data["data_hora_analise"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        combined_data["group_id"] = self._resolve_group_id(combined_data, metadata)
        return pd.DataFrame([combined_data])

    def _collect_roi_metrics(
        self,
        combined_data: dict[str, Any],
        report: dict[str, Any],
        r_analyzer: ROIAnalyzer,
        roi_colors: dict[str, tuple[int, int, int]],
    ) -> dict[str, Any]:
        """Collect ROI-specific metrics and append them to combined_data.

        This helper centralizes extraction from the report's ROI analysis
        structure and reduces the complexity of the main tidy-dataframe builder.

        Args:
            combined_data: Dictionary to append metrics to
            report: Structured analysis report
            r_analyzer: ROIAnalyzer instance
            roi_colors: Dictionary mapping ROI names to RGB tuples

        Returns:
            dict: Updated combined_data with ROI metrics
        """
        roi_analysis = report.get("analise_roi", {})
        time_spent = roi_analysis.get("tempo_gasto_por_roi", {})
        entry_counts = roi_analysis.get("contagem_entradas", {})
        exit_counts = roi_analysis.get("contagem_saidas", {})
        latencies = roi_analysis.get("latencia_primeira_entrada", {})
        distances = roi_analysis.get("distancia_por_roi", {})
        velocities = roi_analysis.get("estatisticas_velocidade_por_roi", {})
        freezing = roi_analysis.get("congelamento_por_roi", {})

        total_roi_entries = 0
        for roi_name in r_analyzer.rois:
            # Time spent
            combined_data[f"tempo_no_{roi_name}_s"] = time_spent.get(roi_name, {}).get("seconds")
            combined_data[f"percentual_tempo_no_{roi_name}"] = time_spent.get(roi_name, {}).get(
                "percentage"
            )

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
                combined_data[f"velocidade_media_no_{roi_name}_cm_s"] = roi_vel.get("mean")

            # Intra-ROI Freezing
            roi_freeze = freezing.get(roi_name)
            if roi_freeze:
                combined_data[f"episodios_congelamento_no_{roi_name}"] = roi_freeze.get("count")
                combined_data[f"duracao_total_congelamento_no_{roi_name}_s"] = roi_freeze.get(
                    "total_duration"
                )

            # ROI Color - convert to color name
            if roi_name in roi_colors:
                combined_data[f"cor_roi_{roi_name}"] = _rgb_to_color_name(roi_colors[roi_name])

        combined_data["total_entradas_roi"] = total_roi_entries
        return combined_data

    def standardize_roi_columns(
        self,
        df: pd.DataFrame,
        expected_roi_names: list[str] | None = None
    ) -> pd.DataFrame:
        """Ensure DataFrame has columns for all expected ROIs, padding with NaN/0 if missing.

        This method standardizes ROI column schemas across different videos to enable
        proper concatenation in unified reports.

        Args:
            df: Tidy dataframe to standardize
            expected_roi_names: List of all ROI names that should have columns

        Returns:
            pd.DataFrame: Dataframe with standardized ROI columns
        """
        if not expected_roi_names:
            return df

        standardized_df = df.copy()

        # ROI metric templates - maps column pattern to default value
        # Use NaN for continuous metrics, 0 for count metrics
        roi_column_templates = [
            ("tempo_no_{}_s", pd.NA),
            ("percentual_tempo_no_{}", pd.NA),
            ("entradas_no_{}", 0),  # Count: use 0 instead of NaN
            ("saidas_do_{}", 0),    # Count: use 0 instead of NaN
            ("latencia_para_{}_s", pd.NA),
            ("distancia_no_{}_cm", pd.NA),
            ("velocidade_media_no_{}_cm_s", pd.NA),
            ("episodios_congelamento_no_{}", 0),  # Count: use 0
            ("duracao_total_congelamento_no_{}_s", pd.NA),
            ("cor_roi_{}", pd.NA),
        ]

        # Add missing columns for each expected ROI
        for roi_name in expected_roi_names:
            for template, default_value in roi_column_templates:
                col_name = template.format(roi_name)
                if col_name not in standardized_df.columns:
                    standardized_df[col_name] = default_value

        return standardized_df

    def _resolve_group_id(self, combined_data: dict[str, Any], metadata: dict[str, Any]) -> str:
        """Ensure the summary dataframe includes a populated group_id column.

        Args:
            combined_data: Combined data dictionary
            metadata: Experiment metadata

        Returns:
            str: Resolved group ID
        """
        group_id = combined_data.get("group_id") or metadata.get("group_id")
        if group_id:
            return str(group_id)

        for key in GROUP_ID_FALLBACK_KEYS:
            candidate = combined_data.get(key) or metadata.get(key)
            if candidate:
                return str(candidate)

        return "unassigned"

    @staticmethod
    def translate_column_name(column_name: str) -> str:
        """Translate Portuguese column name to English.

        Args:
            column_name: Column name in Portuguese

        Returns:
            str: Column name in English
        """
        if column_name in COLUMN_MAPPING:
            return COLUMN_MAPPING[column_name]

        for prefix, replacement in DYNAMIC_PREFIX_MAPPINGS:
            if column_name.startswith(prefix):
                suffix = column_name[len(prefix) :]
                return f"{replacement}{suffix}"

        return column_name

    def standardize_tidy_dataframe(
        self, df: pd.DataFrame, metadata: dict[str, Any]
    ) -> pd.DataFrame:
        """Standardize tidy dataframe with English column names and validated schema.

        Args:
            df: Tidy dataframe to standardize
            metadata: Experiment metadata for fallback values

        Returns:
            pd.DataFrame: Standardized dataframe with validated schema

        Raises:
            ValueError: If required columns are missing after standardization
        """
        standardized_df = df.copy()

        # Translate column names
        rename_map = {}
        for column in standardized_df.columns:
            translated = self.translate_column_name(column)
            if translated != column:
                rename_map[column] = translated

        if rename_map:
            standardized_df = standardized_df.rename(columns=rename_map)

        # Ensure experiment_id exists
        if "experiment_id" not in standardized_df.columns:
            experiment_id = (
                metadata.get("experiment_id")
                or metadata.get("video_name")
                or metadata.get("experiment_name")
                or metadata.get("name")
            )
            standardized_df["experiment_id"] = experiment_id or "unknown"

        standardized_df["experiment_id"] = (
            standardized_df["experiment_id"].fillna("unknown").astype(str)
        )

        # Ensure group_id exists
        if "group_id" not in standardized_df.columns:
            standardized_df["group_id"] = self._resolve_group_id(
                standardized_df.iloc[0].to_dict(), metadata
            )

        standardized_df["group_id"] = standardized_df["group_id"].fillna("unassigned").astype(str)

        # Validate schema
        self.validate_schema(standardized_df)
        return standardized_df

    @staticmethod
    def validate_schema(df: pd.DataFrame):
        """Validate that dataframe has all required columns.

        Args:
            df: DataFrame to validate

        Raises:
            ValueError: If required columns are missing
        """
        missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_columns:
            raise ValueError(
                "Reporter summary is missing required columns: "
                + ", ".join(sorted(missing_columns))
            )

    @staticmethod
    def warp_trajectory_if_needed(trajectory_df: pd.DataFrame, calibration) -> pd.DataFrame:
        """Warp bounding boxes into the calibrated space when raw points slip through.

        Some runs saved detections using the original video reference instead of the
        warped view. Metrics then break because coordinates no longer align with the
        arena and ROI polygons.

        We detect the mismatch when any bbox coordinate exceeds the expected warped
        dimensions. In that case we transform every bbox with the calibration
        homography so downstream analysis always operates in the calibrated frame.

        Args:
            trajectory_df: Trajectory DataFrame with bbox coordinates
            calibration: Calibration object with homography_matrix

        Returns:
            pd.DataFrame: Warped trajectory DataFrame if needed, otherwise original
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

        max_x = max(_max_safe(col) for col in ("x1", "x2", "x_center_px"))
        max_y = max(_max_safe(col) for col in ("y1", "y2", "y_center_px"))

        if max_x <= expected_width + tolerance and max_y <= expected_height + tolerance:
            return trajectory_df

        warped_df = trajectory_df.copy()

        # Extract bbox coordinates to NumPy arrays for efficient iteration
        x1_values = warped_df["x1"].to_numpy(copy=True)
        y1_values = warped_df["y1"].to_numpy(copy=True)
        x2_values = warped_df["x2"].to_numpy(copy=True)
        y2_values = warped_df["y2"].to_numpy(copy=True)

        # Performance Note: Row-by-row iteration with calibration.transform_bbox()
        # This is necessary because calibration.transform_bbox() applies homography
        # transformations that cannot be easily vectorized without modifying the
        # calibration interface. Typical trajectory sizes (100-10000 detections)
        # complete in <1 second even with row-by-row processing.
        #
        # Future optimization: If calibration.transform_bbox() is refactored to
        # accept NumPy arrays, this could be vectorized for significant speedup.
        for i, (x1, y1, x2, y2) in enumerate(
            zip(x1_values, y1_values, x2_values, y2_values, strict=False)
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
        warped_df["x_center_px"] = warped_df[["x1", "x2"]].mean(axis=1)
        warped_df["y_center_px"] = warped_df[["y1", "y2"]].mean(axis=1)

        # Drop any stale cm columns – they will be recomputed by the analyzer
        for col in ("x_cm", "y_cm"):
            if col in warped_df.columns:
                warped_df.drop(columns=col, inplace=True)

        return warped_df
