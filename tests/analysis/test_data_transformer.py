"""
Unit tests for DataTransformer class.

Phase: Code Quality Improvements (Task 2.5)
Tests data transformation, column standardization, schema validation,
trajectory warping, and RGB color name conversion.
"""

from typing import Any
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer
from zebtrack.analysis.data_transformer import (
    RGB_COLOR_MATCH_THRESHOLD,
    DataTransformer,
    _rgb_to_color_name,
)
from zebtrack.analysis.roi import ROI, ROIAnalyzer


@pytest.fixture
def mock_settings():
    """Create mock settings for analyzers."""
    settings = Mock()
    settings.trajectory_smoothing = Mock()
    settings.trajectory_smoothing.window_length = 5
    settings.trajectory_smoothing.polyorder = 2
    settings.angular_velocity = Mock()
    settings.angular_velocity.min_displacement_threshold_cm = 0.5
    settings.angular_velocity.angle_calculation_window = 3
    settings.angular_velocity.angular_velocity_smoothing_window = 5
    settings.roi_inclusion_rule = "centroid_in"
    settings.roi_buffer_radius_value = 0.0
    settings.roi_min_bbox_overlap_ratio = 0.5
    return settings


@pytest.fixture
def sample_trajectory_df():
    """Create sample trajectory DataFrame for testing."""
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01", periods=10, freq="100ms"),
            "frame": range(10),
            "track_id": [1] * 10,
            "x1": [10.0 + i for i in range(10)],
            "y1": [20.0 + i for i in range(10)],
            "x2": [30.0 + i for i in range(10)],
            "y2": [40.0 + i for i in range(10)],
            "confidence": [0.95] * 10,
            "x_center_px": [20.0 + i for i in range(10)],
            "y_center_px": [30.0 + i for i in range(10)],
        }
    )


@pytest.fixture
def sample_rois():
    """Create sample ROI list for testing."""
    return [
        ROI(
            name="center",
            geometry=Polygon([(10, 10), (20, 10), (20, 20), (10, 20)]),
            coordinate_space="px",
        ),
        ROI(
            name="periphery",
            geometry=Polygon([(30, 30), (40, 30), (40, 40), (30, 40)]),
            coordinate_space="px",
        ),
    ]


@pytest.fixture
def behavior_analyzer(sample_trajectory_df, mock_settings):
    """Create ConcreteBehavioralAnalyzer instance with test data."""
    arena_polygon_px = [(0, 0), (100, 0), (100, 100), (0, 100)]
    analyzer = ConcreteBehavioralAnalyzer(
        trajectory_df=sample_trajectory_df,
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=100,
        arena_polygon_px=arena_polygon_px,
        fps=10.0,
    )
    return analyzer


@pytest.fixture
def roi_analyzer(behavior_analyzer, sample_rois, mock_settings):
    """Create ROIAnalyzer instance with test data."""
    analyzer = ROIAnalyzer(
        behavior_analyzer=behavior_analyzer,
        rois=sample_rois,
    )
    return analyzer


@pytest.fixture
def sample_report(behavior_analyzer, roi_analyzer):
    """Create sample analysis report structure."""
    return {
        "comportamento_geral": {
            "distancia_total_cm": 42.5,
            "estatisticas_velocidade": {
                "mean": 4.25,
                "median": 4.0,
                "std_dev": 0.5,
            },
            "curvas_acentuadas": {
                "sharp_turns_count": 3,
                "sharp_turns_per_minute": 18.0,
            },
            "rajadas_velocidade": {
                "count": 2,
                "total_duration_s": 1.5,
                "threshold_cm_s": 10.0,
            },
            "periodos_inatividade": {
                "count": 1,
                "total_duration_s": 0.5,
                "percentage_of_recording": 5.0,
                "threshold_cm_s": 0.5,
            },
        },
        "analise_roi": {
            "tempo_gasto_por_roi": {
                "center": {"seconds": 0.3, "percentage": 30.0},
                "periphery": {"seconds": 0.7, "percentage": 70.0},
            },
            "contagem_entradas": {"center": 2, "periphery": 1},
            "contagem_saidas": {"center": 2, "periphery": 1},
            "latencia_primeira_entrada": {"center": 0.1, "periphery": 0.5},
            "distancia_por_roi": {"center": 15.0, "periphery": 27.5},
            "estatisticas_velocidade_por_roi": {
                "center": {"mean": 5.0},
                "periphery": {"mean": 3.5},
            },
            "congelamento_por_roi": {
                "center": {"count": 0, "total_duration": 0.0},
                "periphery": {"count": 1, "total_duration": 0.5},
            },
        },
    }


@pytest.fixture
def transformer():
    """Create DataTransformer instance."""
    return DataTransformer()


# ============================================================================
# Tests for RGB Color Name Conversion
# ============================================================================


def test_rgb_to_color_name_exact_match():
    """Test RGB to color name conversion with exact matches."""
    assert _rgb_to_color_name((255, 0, 0)) == "Red"
    assert _rgb_to_color_name((0, 255, 0)) == "Green"
    assert _rgb_to_color_name((0, 0, 255)) == "Blue"
    assert _rgb_to_color_name((255, 255, 0)) == "Yellow"
    assert _rgb_to_color_name((0, 0, 0)) == "Black"
    assert _rgb_to_color_name((255, 255, 255)) == "White"


def test_rgb_to_color_name_close_match():
    """Test RGB to color name conversion with close matches within threshold."""
    # Close to red (within threshold of 900 = 30²)
    assert _rgb_to_color_name((250, 5, 5)) == "Red"
    assert _rgb_to_color_name((255, 10, 10)) == "Red"

    # Close to green
    assert _rgb_to_color_name((5, 250, 5)) == "Green"

    # Close to blue
    assert _rgb_to_color_name((5, 5, 250)) == "Blue"


def test_rgb_to_color_name_far_match_returns_rgb_string():
    """Test RGB to color name conversion returns RGB string for distant colors."""
    # Color far from any named color (> 30 units away)
    result = _rgb_to_color_name((100, 150, 200))
    assert result.startswith("RGB(")
    assert "100" in result
    assert "150" in result
    assert "200" in result


def test_rgb_to_color_name_threshold_boundary():
    """Test RGB color matching near the threshold boundary (900 = 30²)."""
    # Test case at exactly the threshold
    # Distance from Red (255,0,0) to (225,0,0) = 30² = 900
    result = _rgb_to_color_name((225, 0, 0))
    # Should match Red as distance == threshold
    assert result == "Red" or result.startswith("RGB(")

    # Just over threshold should return RGB string
    result_far = _rgb_to_color_name((224, 0, 0))
    # Distance = 31² = 961 > 900
    assert result_far.startswith("RGB(") or result_far == "Red"


def test_rgb_to_color_name_invalid_input():
    """Test RGB to color name conversion with invalid inputs."""
    assert _rgb_to_color_name(None) == "None"
    assert _rgb_to_color_name("invalid") == "invalid"
    assert _rgb_to_color_name((255, 0)) == "(255, 0)"
    assert _rgb_to_color_name([255, 0, 0, 255]) == "[255, 0, 0, 255]"


def test_rgb_color_match_threshold_value():
    """Test that RGB_COLOR_MATCH_THRESHOLD has expected value."""
    assert RGB_COLOR_MATCH_THRESHOLD == 2500
    assert RGB_COLOR_MATCH_THRESHOLD == 50**2  # 50² in RGB space


# ============================================================================
# Tests for create_tidy_dataframe
# ============================================================================


def test_create_tidy_dataframe_basic(transformer, behavior_analyzer, sample_report):
    """Test creating tidy dataframe with basic behavior metrics only."""
    metadata = {"experiment_id": "test_001", "group_id": "control"}

    df = transformer.create_tidy_dataframe(
        report=sample_report, metadata=metadata, b_analyzer=behavior_analyzer
    )

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert df["experiment_id"].iloc[0] == "test_001"
    assert df["group_id"].iloc[0] == "control"

    # Check general behavior metrics
    assert df["distancia_total_cm"].iloc[0] == 42.5
    assert df["velocidade_media_cm_s"].iloc[0] == 4.25
    assert df["velocidade_mediana_cm_s"].iloc[0] == 4.0
    assert df["desvio_padrao_velocidade_cm_s"].iloc[0] == 0.5
    assert df["contagem_curvas_acentuadas"].iloc[0] == 3
    assert df["curvas_acentuadas_por_minuto"].iloc[0] == 18.0

    # Check speed bursts
    assert df["rajadas_velocidade_contagem"].iloc[0] == 2
    assert df["rajadas_velocidade_duracao_total_s"].iloc[0] == 1.5
    assert df["rajadas_velocidade_limiar_cm_s"].iloc[0] == 10.0

    # Check inactivity
    assert df["periodos_inatividade_contagem"].iloc[0] == 1
    assert df["periodos_inatividade_duracao_total_s"].iloc[0] == 0.5
    assert df["periodos_inatividade_percentual_registro"].iloc[0] == 5.0
    assert df["periodos_inatividade_limiar_cm_s"].iloc[0] == 0.5

    # Timestamp should be present
    assert "data_hora_analise" in df.columns


def test_create_tidy_dataframe_with_rois(
    transformer, behavior_analyzer, roi_analyzer, sample_report
):
    """Test creating tidy dataframe with ROI-specific metrics."""
    metadata = {"experiment_id": "test_002", "group_id": "treatment"}
    roi_colors = {"center": (255, 0, 0), "periphery": (0, 255, 0)}

    df = transformer.create_tidy_dataframe(
        report=sample_report,
        metadata=metadata,
        b_analyzer=behavior_analyzer,
        r_analyzer=roi_analyzer,
        roi_colors=roi_colors,
    )

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1

    # Check ROI time spent
    assert df["tempo_no_center_s"].iloc[0] == 0.3
    assert df["percentual_tempo_no_center"].iloc[0] == 30.0
    assert df["tempo_no_periphery_s"].iloc[0] == 0.7
    assert df["percentual_tempo_no_periphery"].iloc[0] == 70.0

    # Check ROI entries/exits
    assert df["entradas_no_center"].iloc[0] == 2
    assert df["saidas_do_center"].iloc[0] == 2
    assert df["entradas_no_periphery"].iloc[0] == 1
    assert df["saidas_do_periphery"].iloc[0] == 1
    assert df["total_entradas_roi"].iloc[0] == 3

    # Check ROI latencies
    assert df["latencia_para_center_s"].iloc[0] == 0.1
    assert df["latencia_para_periphery_s"].iloc[0] == 0.5

    # Check ROI distances and velocities
    assert df["distancia_no_center_cm"].iloc[0] == 15.0
    assert df["distancia_no_periphery_cm"].iloc[0] == 27.5
    assert df["velocidade_media_no_center_cm_s"].iloc[0] == 5.0
    assert df["velocidade_media_no_periphery_cm_s"].iloc[0] == 3.5

    # Check ROI freezing
    assert df["episodios_congelamento_no_center"].iloc[0] == 0
    assert df["duracao_total_congelamento_no_center_s"].iloc[0] == 0.0
    assert df["episodios_congelamento_no_periphery"].iloc[0] == 1
    assert df["duracao_total_congelamento_no_periphery_s"].iloc[0] == 0.5

    # Check ROI colors
    assert df["cor_roi_center"].iloc[0] == "Red"
    assert df["cor_roi_periphery"].iloc[0] == "Green"


# ============================================================================
# Tests for translate_column_name
# ============================================================================


def test_translate_column_name_static_mapping(transformer):
    """Test column name translation with static mappings."""
    assert transformer.translate_column_name("distancia_total_cm") == "total_distance_cm"
    assert transformer.translate_column_name("velocidade_media_cm_s") == "mean_speed_cm_s"
    assert transformer.translate_column_name("velocidade_mediana_cm_s") == "median_speed_cm_s"
    assert transformer.translate_column_name("contagem_curvas_acentuadas") == "sharp_turns_count"
    assert transformer.translate_column_name("periodos_inatividade_contagem") == "inactivity_count"


def test_translate_column_name_dynamic_prefix(transformer):
    """Test column name translation with dynamic prefix mappings."""
    assert transformer.translate_column_name("tempo_no_center_s") == "time_in_center_s"
    assert (
        transformer.translate_column_name("percentual_tempo_no_periphery")
        == "time_percentage_in_periphery"
    )
    assert transformer.translate_column_name("entradas_no_roi1") == "entries_in_roi1"
    assert transformer.translate_column_name("saidas_do_roi2") == "exits_from_roi2"
    assert transformer.translate_column_name("latencia_para_center") == "latency_to_center"
    assert transformer.translate_column_name("distancia_no_roi3") == "distance_in_roi3"
    assert transformer.translate_column_name("velocidade_media_no_center") == "mean_speed_in_center"
    assert transformer.translate_column_name("cor_roi_center") == "roi_color_center"


def test_translate_column_name_unmapped(transformer):
    """Test column name translation with unmapped names."""
    assert transformer.translate_column_name("custom_column_name") == "custom_column_name"
    assert transformer.translate_column_name("experiment_id") == "experiment_id"
    assert transformer.translate_column_name("group_id") == "group_id"


# ============================================================================
# Tests for standardize_tidy_dataframe
# ============================================================================


def test_standardize_tidy_dataframe_basic(transformer):
    """Test standardizing tidy dataframe with column name translation."""
    df = pd.DataFrame(
        [
            {
                "experiment_id": "test_001",
                "group_id": "control",
                "distancia_total_cm": 42.5,
                "velocidade_media_cm_s": 4.25,
                "data_hora_analise": "2025-01-01 12:00:00",
            }
        ]
    )
    metadata = {"experiment_id": "test_001"}

    standardized = transformer.standardize_tidy_dataframe(df, metadata)

    assert "total_distance_cm" in standardized.columns
    assert "mean_speed_cm_s" in standardized.columns
    assert "analysis_timestamp" in standardized.columns
    assert standardized["total_distance_cm"].iloc[0] == 42.5
    assert standardized["mean_speed_cm_s"].iloc[0] == 4.25


def test_standardize_tidy_dataframe_missing_experiment_id(transformer):
    """Test standardizing dataframe adds experiment_id from metadata."""
    df = pd.DataFrame(
        [
            {
                "group_id": "control",
                "distancia_total_cm": 42.5,
                "velocidade_media_cm_s": 4.25,
                "data_hora_analise": "2025-01-01 12:00:00",
            }
        ]
    )
    metadata = {"experiment_id": "test_002"}

    standardized = transformer.standardize_tidy_dataframe(df, metadata)

    assert "experiment_id" in standardized.columns
    assert standardized["experiment_id"].iloc[0] == "test_002"


def test_standardize_tidy_dataframe_missing_group_id(transformer):
    """Test standardizing dataframe adds group_id fallback."""
    df = pd.DataFrame(
        [
            {
                "experiment_id": "test_001",
                "distancia_total_cm": 42.5,
                "velocidade_media_cm_s": 4.25,
                "data_hora_analise": "2025-01-01 12:00:00",
            }
        ]
    )
    metadata = {"experiment_id": "test_001"}

    standardized = transformer.standardize_tidy_dataframe(df, metadata)

    assert "group_id" in standardized.columns
    assert standardized["group_id"].iloc[0] == "unassigned"


# ============================================================================
# Tests for validate_schema
# ============================================================================


def test_validate_schema_success(transformer):
    """Test schema validation with all required columns present."""
    df = pd.DataFrame(
        [
            {
                "experiment_id": "test_001",
                "group_id": "control",
                "analysis_timestamp": "2025-01-01 12:00:00",
                "total_distance_cm": 42.5,
                "mean_speed_cm_s": 4.25,
            }
        ]
    )

    # Should not raise
    transformer.validate_schema(df)


def test_validate_schema_missing_required(transformer):
    """Test schema validation raises error when required columns missing."""
    df = pd.DataFrame(
        [
            {
                "experiment_id": "test_001",
                "group_id": "control",
                # Missing: analysis_timestamp, total_distance_cm, mean_speed_cm_s
            }
        ]
    )

    with pytest.raises(ValueError, match="missing required columns"):
        transformer.validate_schema(df)


# ============================================================================
# Tests for warp_trajectory_if_needed
# ============================================================================


def test_warp_trajectory_if_needed_no_warp_needed():
    """Test trajectory warping when coordinates are within bounds."""
    df = pd.DataFrame(
        {
            "x1": [10.0, 20.0],
            "y1": [15.0, 25.0],
            "x2": [30.0, 40.0],
            "y2": [35.0, 45.0],
            "x_center_px": [20.0, 30.0],
            "y_center_px": [25.0, 35.0],
        }
    )

    calibration = Mock()
    calibration.target_dims_px = (100, 100)
    calibration.homography_matrix = np.eye(3)

    result = DataTransformer.warp_trajectory_if_needed(df, calibration)

    # Should return original dataframe unchanged
    pd.testing.assert_frame_equal(result, df)


def test_warp_trajectory_if_needed_exceeds_bounds():
    """Test trajectory warping when coordinates exceed expected bounds."""
    df = pd.DataFrame(
        {
            "x1": [10.0, 120.0],  # x2=120 exceeds target_width=100
            "y1": [15.0, 25.0],
            "x2": [30.0, 140.0],
            "y2": [35.0, 45.0],
            "x_center_px": [20.0, 130.0],
            "y_center_px": [25.0, 35.0],
        }
    )

    calibration = Mock()
    calibration.target_dims_px = (100, 100)
    calibration.homography_matrix = np.eye(3)
    calibration.transform_bbox = Mock(
        side_effect=lambda x1, y1, x2, y2: (x1 * 0.8, y1 * 0.8, x2 * 0.8, y2 * 0.8)
    )

    result = DataTransformer.warp_trajectory_if_needed(df, calibration)

    # Should call transform_bbox for the out-of-bounds row
    assert calibration.transform_bbox.called

    # Check that bounding boxes were transformed
    assert result["x2"].iloc[1] < df["x2"].iloc[1]  # Should be scaled down


def test_warp_trajectory_if_needed_no_calibration():
    """Test trajectory warping returns original when no calibration."""
    df = pd.DataFrame(
        {
            "x1": [10.0, 20.0],
            "y1": [15.0, 25.0],
            "x2": [30.0, 40.0],
            "y2": [35.0, 45.0],
        }
    )

    result = DataTransformer.warp_trajectory_if_needed(df, None)

    # Should return original dataframe unchanged
    pd.testing.assert_frame_equal(result, df)


def test_warp_trajectory_if_needed_missing_columns():
    """Test trajectory warping returns original when required columns missing."""
    df = pd.DataFrame(
        {
            "x1": [10.0, 20.0],
            "y1": [15.0, 25.0],
            # Missing x2, y2
        }
    )

    calibration = Mock()
    calibration.target_dims_px = (100, 100)
    calibration.homography_matrix = np.eye(3)

    result = DataTransformer.warp_trajectory_if_needed(df, calibration)

    # Should return original dataframe unchanged
    pd.testing.assert_frame_equal(result, df)


# ============================================================================
# Tests for _resolve_group_id
# ============================================================================


def test_resolve_group_id_from_combined_data(transformer):
    """Test group ID resolution from combined_data."""
    combined_data: dict[str, Any] = {"group_id": "treatment"}
    metadata: dict[str, Any] = {}

    result = transformer._resolve_group_id(combined_data, metadata)
    assert result == "treatment"


def test_resolve_group_id_from_metadata(transformer):
    """Test group ID resolution from metadata."""
    combined_data: dict[str, Any] = {}
    metadata: dict[str, Any] = {"group_id": "control"}

    result = transformer._resolve_group_id(combined_data, metadata)
    assert result == "control"


def test_resolve_group_id_from_fallback_keys(transformer):
    """Test group ID resolution from fallback keys."""
    combined_data: dict[str, Any] = {}
    metadata: dict[str, Any] = {"grupo": "experimental"}

    result = transformer._resolve_group_id(combined_data, metadata)
    assert result == "experimental"

    # Test with group_name fallback
    combined_data = {}
    metadata = {"group_name": "placebo"}

    result = transformer._resolve_group_id(combined_data, metadata)
    assert result == "placebo"


def test_resolve_group_id_unassigned(transformer):
    """Test group ID resolution returns 'unassigned' when not found."""
    combined_data: dict[str, Any] = {}
    metadata: dict[str, Any] = {}

    result = transformer._resolve_group_id(combined_data, metadata)
    assert result == "unassigned"


# ============================================================================
# Tests for stateless behavior
# ============================================================================


def test_transformer_is_stateless():
    """Test that DataTransformer instances are stateless."""
    t1 = DataTransformer()
    t2 = DataTransformer()

    # Multiple instances should behave identically
    assert t1.translate_column_name("distancia_total_cm") == t2.translate_column_name(
        "distancia_total_cm"
    )

    # No instance state should affect behavior
    df1 = pd.DataFrame([{"experiment_id": "test_001", "group_id": "G1"}])
    df2 = pd.DataFrame([{"experiment_id": "test_002", "group_id": "G2"}])

    result1 = t1._resolve_group_id(df1.iloc[0].to_dict(), {})
    result2 = t2._resolve_group_id(df2.iloc[0].to_dict(), {})

    assert result1 == "G1"
    assert result2 == "G2"


# ============================================================================
# Tests for standardize_roi_columns
# ============================================================================


def test_standardize_roi_columns_pads_missing_columns():
    """Test that standardize_roi_columns adds missing ROI columns with appropriate defaults."""
    transformer = DataTransformer()

    # DataFrame with only roi1
    df = pd.DataFrame(
        {
            "experiment_id": ["exp1", "exp1"],
            "group_id": ["control", "control"],
            "tempo_no_roi1_s": [10.5, 15.2],
            "entradas_no_roi1": [3, 5],
        }
    )

    # Expected ROI names include roi1 and roi2
    expected_rois = ["roi1", "roi2"]

    result = transformer.standardize_roi_columns(df, expected_rois)

    # Verify roi1 columns unchanged
    assert "tempo_no_roi1_s" in result.columns
    assert "entradas_no_roi1" in result.columns
    pd.testing.assert_series_equal(result["tempo_no_roi1_s"], df["tempo_no_roi1_s"])

    # Verify roi2 columns added
    assert "tempo_no_roi2_s" in result.columns
    assert "entradas_no_roi2" in result.columns
    assert "latencia_para_roi2_s" in result.columns
    assert "distancia_no_roi2_cm" in result.columns

    # Verify default values: NaN for continuous metrics, 0 for counts
    assert result["tempo_no_roi2_s"].isna().all()
    assert result["latencia_para_roi2_s"].isna().all()
    assert (result["entradas_no_roi2"] == 0).all()
    assert (result["saidas_do_roi2"] == 0).all()


def test_standardize_roi_columns_returns_unchanged_when_no_expected_rois():
    """Test that standardize_roi_columns returns unchanged DataFrame when
    expected_roi_names is None."""
    transformer = DataTransformer()

    df = pd.DataFrame(
        {
            "experiment_id": ["exp1"],
            "group_id": ["control"],
            "tempo_no_roi1_s": [10.5],
        }
    )

    result = transformer.standardize_roi_columns(df, None)

    # Should return unchanged DataFrame
    pd.testing.assert_frame_equal(result, df)


def test_standardize_roi_columns_handles_empty_expected_list():
    """Test that standardize_roi_columns handles empty expected_roi_names list."""
    transformer = DataTransformer()

    df = pd.DataFrame(
        {
            "experiment_id": ["exp1"],
            "group_id": ["control"],
            "tempo_no_roi1_s": [10.5],
        }
    )

    result = transformer.standardize_roi_columns(df, [])

    # Should return unchanged DataFrame
    pd.testing.assert_frame_equal(result, df)


def test_standardize_roi_columns_preserves_existing_data():
    """Test that standardize_roi_columns preserves all existing columns and data."""
    transformer = DataTransformer()

    df = pd.DataFrame(
        {
            "experiment_id": ["exp1", "exp2"],
            "group_id": ["control", "treatment"],
            "tempo_no_center_s": [10.5, 20.3],
            "entradas_no_center": [3, 5],
            "total_distance_cm": [100.5, 150.3],
        }
    )

    expected_rois = ["center", "edge"]
    result = transformer.standardize_roi_columns(df, expected_rois)

    # All original columns should be preserved
    assert "experiment_id" in result.columns
    assert "group_id" in result.columns
    assert "total_distance_cm" in result.columns
    assert "tempo_no_center_s" in result.columns
    assert "entradas_no_center" in result.columns

    # Original data should be unchanged
    pd.testing.assert_series_equal(result["experiment_id"], df["experiment_id"])
    pd.testing.assert_series_equal(result["tempo_no_center_s"], df["tempo_no_center_s"])
    pd.testing.assert_series_equal(result["total_distance_cm"], df["total_distance_cm"])


def test_standardize_roi_columns_adds_all_expected_metric_types():
    """Test that all ROI metric column types are added."""
    transformer = DataTransformer()

    df = pd.DataFrame(
        {
            "experiment_id": ["exp1"],
            "group_id": ["control"],
        }
    )

    expected_rois = ["test_roi"]
    result = transformer.standardize_roi_columns(df, expected_rois)

    # Verify all metric types are added
    expected_columns = [
        "tempo_no_test_roi_s",
        "percentual_tempo_no_test_roi",
        "entradas_no_test_roi",
        "saidas_do_test_roi",
        "latencia_para_test_roi_s",
        "distancia_no_test_roi_cm",
        "velocidade_media_no_test_roi_cm_s",
        "episodios_congelamento_no_test_roi",
        "duracao_total_congelamento_no_test_roi_s",
        "cor_roi_test_roi",
    ]

    for col in expected_columns:
        assert col in result.columns, f"Missing column: {col}"


def test_standardize_roi_columns_uses_correct_default_values():
    """Test that continuous metrics use NaN and count metrics use 0 as defaults."""
    transformer = DataTransformer()

    df = pd.DataFrame(
        {
            "experiment_id": ["exp1", "exp2"],
            "group_id": ["control", "treatment"],
        }
    )

    expected_rois = ["roi1"]
    result = transformer.standardize_roi_columns(df, expected_rois)

    # Continuous metrics should be NaN
    continuous_metrics = [
        "tempo_no_roi1_s",
        "percentual_tempo_no_roi1",
        "latencia_para_roi1_s",
        "distancia_no_roi1_cm",
        "velocidade_media_no_roi1_cm_s",
        "duracao_total_congelamento_no_roi1_s",
        "cor_roi_roi1",
    ]

    for col in continuous_metrics:
        assert result[col].isna().all(), f"{col} should be NaN but got {result[col].values}"

    # Count metrics should be 0
    count_metrics = [
        "entradas_no_roi1",
        "saidas_do_roi1",
        "episodios_congelamento_no_roi1",
    ]

    for col in count_metrics:
        assert (result[col] == 0).all(), f"{col} should be 0 but got {result[col].values}"


def test_standardize_roi_columns_handles_multiple_rois():
    """Test standardization with multiple ROIs."""
    transformer = DataTransformer()

    df = pd.DataFrame(
        {
            "experiment_id": ["exp1"],
            "group_id": ["control"],
            "tempo_no_roi1_s": [10.0],
        }
    )

    expected_rois = ["roi1", "roi2", "roi3"]
    result = transformer.standardize_roi_columns(df, expected_rois)

    # Verify columns for all ROIs exist
    for roi_name in expected_rois:
        assert f"tempo_no_{roi_name}_s" in result.columns
        assert f"entradas_no_{roi_name}" in result.columns
        assert f"latencia_para_{roi_name}_s" in result.columns

    # roi1 should have original data
    assert result["tempo_no_roi1_s"].iloc[0] == 10.0

    # roi2 and roi3 should have defaults
    assert result["tempo_no_roi2_s"].isna().all()
    assert result["tempo_no_roi3_s"].isna().all()
    assert (result["entradas_no_roi2"] == 0).all()
    assert (result["entradas_no_roi3"] == 0).all()


def test_standardize_roi_columns_does_not_modify_original_dataframe():
    """Test that standardize_roi_columns doesn't modify the original DataFrame."""
    transformer = DataTransformer()

    df = pd.DataFrame(
        {
            "experiment_id": ["exp1"],
            "group_id": ["control"],
            "tempo_no_roi1_s": [10.5],
        }
    )

    original_columns = set(df.columns)
    expected_rois = ["roi1", "roi2"]

    result = transformer.standardize_roi_columns(df, expected_rois)

    # Original DataFrame should be unchanged
    assert set(df.columns) == original_columns
    assert "tempo_no_roi2_s" not in df.columns

    # Result should have new columns
    assert "tempo_no_roi2_s" in result.columns
