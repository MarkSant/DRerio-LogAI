import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from zebtrack.analysis.reporter import Reporter
from zebtrack.analysis.roi import ROI
from shapely.geometry import box

@pytest.fixture
def reporter_setup(tmp_path):
    """Provides a fully initialized Reporter instance for testing."""
    # Create sample data
    trajectory_df = pd.DataFrame({
        'timestamp': pd.to_datetime(range(10), unit='s'),
        'x_center_px': range(10, 20),
        'y_center_px': range(20, 30),
        'x1': range(9, 19),
        'y1': range(19, 29),
        'x2': range(11, 21),
        'y2': range(21, 31),
    })
    metadata = {"experiment_id": "test_exp_01", "group_id": "control"}
    pixelcm_x = 10.0
    pixelcm_y = 10.0
    video_height_px = 100
    arena_polygon_px = [(0, 0), (50, 0), (50, 50), (0, 50)]
    rois = [ROI(name="zone1", geometry=box(1, 1, 2, 2))]
    fps = 10.0

    # The Reporter's __init__ calls the full analysis service.
    # We can patch the service to return predictable data, isolating the
    # Reporter's own logic (tidy data creation, plotting, exporting).
    with patch("zebtrack.analysis.reporter.AnalysisService") as mock_service:
        mock_analyzer = MagicMock()
        # Mock the ROI analyzer to have a _rois attribute
        mock_roi_analyzer = MagicMock()
        mock_roi_analyzer._rois = {"zone1": rois[0]}

        mock_report_dict = {
            "comportamento_geral": {
                "distancia_total_cm": 100.0,
                "estatisticas_velocidade": {"mean": 10.0, "median": 10.0, "std_dev": 1.0},
                "curvas_acentuadas": {"sharp_turns_count": 5, "sharp_turns_per_minute": 30.0},
            },
            "analise_roi": {
                "tempo_gasto_por_roi": {"zone1": {"seconds": 5.0, "percentage": 50.0}},
                "contagem_entradas": {"zone1": 1},
                "contagem_saidas": {"zone1": 1},
                "latencia_primeira_entrada": {"zone1": 1.0},
                "distancia_por_roi": {"zone1": 10.0},
                "estatisticas_velocidade_por_roi": {"zone1": {"mean": 12.0}},
                "congelamento_por_roi": {"zone1": {"count": 2, "total_duration": 2.0}},
            }
        }
        mock_service.return_value.run_full_analysis.return_value = (
            mock_report_dict, mock_analyzer, mock_roi_analyzer
        )

        reporter = Reporter(
            trajectory_df=trajectory_df, metadata=metadata, pixelcm_x=pixelcm_x,
            pixelcm_y=pixelcm_y, video_height_px=video_height_px,
            arena_polygon_px=arena_polygon_px, rois=rois, fps=fps
        )
        yield reporter, tmp_path

def test_reporter_create_tidy_dataframe(reporter_setup):
    """
    Tests if the _create_tidy_dataframe method correctly flattens the
    analysis report into a single-row DataFrame.
    """
    reporter, _ = reporter_setup
    tidy_df = reporter.tidy_data

    assert isinstance(tidy_df, pd.DataFrame)
    assert len(tidy_df) == 1

    # Check that metadata is included
    assert tidy_df["experiment_id"].iloc[0] == "test_exp_01"
    assert tidy_df["group_id"].iloc[0] == "control"

    # Check some flattened metrics from the mock report
    assert tidy_df["distancia_total_cm"].iloc[0] == 100.0
    assert tidy_df["velocidade_media_cm_s"].iloc[0] == 10.0
    assert tidy_df["contagem_curvas_acentuadas"].iloc[0] == 5
    assert tidy_df["tempo_no_zone1_s"].iloc[0] == 5.0
    assert tidy_df["entradas_no_zone1"].iloc[0] == 1
    assert "data_hora_analise" in tidy_df.columns

@patch("pandas.DataFrame.to_excel")
def test_reporter_export_summary_excel(mock_to_excel, reporter_setup):
    """Tests that export_summary_data calls the correct pandas method for Excel."""
    reporter, tmp_path = reporter_setup
    output_path = tmp_path / "summary.xlsx"
    reporter.export_summary_data(str(output_path), format="excel")
    mock_to_excel.assert_called_once_with(str(output_path), index=False, engine="openpyxl")

@patch("pandas.DataFrame.to_csv")
def test_reporter_export_summary_csv(mock_to_csv, reporter_setup):
    """Tests that export_summary_data calls the correct pandas method for CSV."""
    reporter, tmp_path = reporter_setup
    output_path = tmp_path / "summary.csv"
    reporter.export_summary_data(str(output_path), format="csv")
    mock_to_csv.assert_called_once_with(str(output_path), index=False)

@patch("pandas.DataFrame.to_parquet")
def test_reporter_export_summary_parquet(mock_to_parquet, reporter_setup):
    """Tests that export_summary_data calls the correct pandas method for Parquet."""
    reporter, tmp_path = reporter_setup
    output_path = tmp_path / "summary.parquet"
    reporter.export_summary_data(str(output_path), format="parquet")
    mock_to_parquet.assert_called_once_with(str(output_path), index=False)

def test_reporter_export_summary_invalid_format(reporter_setup):
    """Tests that a ValueError is raised for an unsupported format."""
    reporter, tmp_path = reporter_setup
    with pytest.raises(ValueError, match="Unsupported file format: json"):
        reporter.export_summary_data(str(tmp_path / "summary.json"), format="json")
