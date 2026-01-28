import pandas as pd
import pytest

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.settings import load_settings


@pytest.fixture
def service():
    settings = load_settings()
    return AnalysisService(settings_obj=settings)


def test_aggregate_session_summaries(service, tmp_path):
    """Test aggregation of multiple session summary files."""
    # Create dummy session summaries
    data1 = {
        "total_distance_cm": [100.0],
        "average_speed_cm_s": [10.0],
        "time_in_center_s": [5.0],
        "entries_to_center": [2],
        "other_col": ["a"],
    }
    df1 = pd.DataFrame(data1)
    path1 = tmp_path / "session1.xlsx"
    df1.to_excel(path1, index=False)

    data2 = {
        "total_distance_cm": [200.0],
        "average_speed_cm_s": [20.0],
        "time_in_center_s": [10.0],
        "entries_to_center": [4],
        "other_col": ["b"],
    }
    df2 = pd.DataFrame(data2)
    path2 = tmp_path / "session2.xlsx"
    df2.to_excel(path2, index=False)

    output_path = tmp_path / "unified.xlsx"

    service.aggregate_session_summaries([path1, path2], output_path)

    assert output_path.exists()

    # Verify All Sessions
    unified_df = pd.read_excel(output_path, sheet_name="All Sessions")
    assert len(unified_df) == 2
    assert "session_number" in unified_df.columns
    assert "session_file" in unified_df.columns
    assert unified_df.iloc[0]["total_distance_cm"] == 100.0
    assert unified_df.iloc[1]["total_distance_cm"] == 200.0
    assert unified_df.iloc[0]["session_file"] == "session1"

    # Verify Session Summary
    summary_df = pd.read_excel(output_path, sheet_name="Session Summary")
    assert len(summary_df) == 2
    assert "session_number" in summary_df.columns

    row1 = summary_df[summary_df["session_number"] == 1].iloc[0]
    assert row1["total_distance_cm"] == 100.0
    assert row1["entries_to_center"] == 2

    row2 = summary_df[summary_df["session_number"] == 2].iloc[0]
    assert row2["total_distance_cm"] == 200.0
    assert row2["entries_to_center"] == 4


def test_aggregate_session_summaries_multi_row_mean(service, tmp_path):
    """Test that aggregation uses mean (not sum) for entries when multiple rows
    exist per session."""
    # Session 1: Two animals
    data1 = {
        "total_distance_cm": [100.0, 100.0],
        "entries_to_center": [2, 4],  # Mean should be 3
    }
    df1 = pd.DataFrame(data1)
    path1 = tmp_path / "session1.xlsx"
    df1.to_excel(path1, index=False)

    # Session 2: One animal
    data2 = {"total_distance_cm": [200.0], "entries_to_center": [10]}
    df2 = pd.DataFrame(data2)
    path2 = tmp_path / "session2.xlsx"
    df2.to_excel(path2, index=False)

    output_path = tmp_path / "unified_multi.xlsx"
    service.aggregate_session_summaries([path1, path2], output_path)

    summary_df = pd.read_excel(output_path, sheet_name="Session Summary")

    # Check Session 1
    row1 = summary_df[summary_df["session_number"] == 1].iloc[0]
    # Verify entries_to_center is averaged (3) not summed (6)
    assert row1["entries_to_center"] == 3.0


def test_aggregate_session_summaries_missing_columns(service, tmp_path):
    """Test that aggregation handles missing columns gracefully."""
    # File without entries_to_center
    data1 = {"total_distance_cm": [100.0], "average_speed_cm_s": [10.0]}
    df1 = pd.DataFrame(data1)
    path1 = tmp_path / "session1.xlsx"
    df1.to_excel(path1, index=False)

    data2 = {"total_distance_cm": [200.0], "average_speed_cm_s": [20.0]}
    df2 = pd.DataFrame(data2)
    path2 = tmp_path / "session2.xlsx"
    df2.to_excel(path2, index=False)

    output_path = tmp_path / "unified_missing.xlsx"
    service.aggregate_session_summaries([path1, path2], output_path)

    summary_df = pd.read_excel(output_path, sheet_name="Session Summary")
    assert "total_distance_cm" in summary_df.columns
    assert "entries_to_center" not in summary_df.columns
    assert len(summary_df) == 2


def test_aggregate_session_summaries_empty_list(service, tmp_path):
    """Test that aggregation raises ValueError for empty list."""
    with pytest.raises(ValueError, match="No valid summary data"):
        service.aggregate_session_summaries([], tmp_path / "out.xlsx")


def test_aggregate_session_summaries_invalid_file(service, tmp_path):
    """Test that invalid files are skipped/logged but don't crash if others are valid."""
    # Create one valid file
    data1 = {"total_distance_cm": [100.0]}
    df1 = pd.DataFrame(data1)
    path1 = tmp_path / "valid.xlsx"
    df1.to_excel(path1, index=False)

    # Path to non-existent file
    path2 = tmp_path / "non_existent.xlsx"

    output_path = tmp_path / "unified_partial.xlsx"

    # Should warn but proceed with valid data
    service.aggregate_session_summaries([path1, path2], output_path)

    assert output_path.exists()
    unified_df = pd.read_excel(output_path, sheet_name="All Sessions")
    assert len(unified_df) == 1
    assert unified_df.iloc[0]["session_file"] == "valid"
