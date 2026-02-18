"""Tests for TrajectoryDataService (Phase 5.6b)."""

from __future__ import annotations

import pandas as pd
import pyarrow as pa
import pytest

from zebtrack.core.services.trajectory_data_service import TrajectoryDataService


@pytest.fixture()
def sample_parquet(tmp_path):
    """Create a minimal trajectory Parquet file."""
    df = pd.DataFrame(
        {
            "timestamp": [0.0, 0.1, 0.2],
            "frame": [0, 1, 2],
            "track_id": [0, 0, 0],
            "x1": [10.0, 11.0, 12.0],
            "y1": [20.0, 21.0, 22.0],
            "x2": [30.0, 31.0, 32.0],
            "y2": [40.0, 41.0, 42.0],
            "confidence": [0.9, 0.95, 0.88],
        }
    )
    path = tmp_path / "3_CoordMovimento_test.parquet"
    df.to_parquet(str(path))
    return str(path)


class TestLoadTrajectory:
    """Tests for TrajectoryDataService.load_trajectory."""

    def test_load_success(self, sample_parquet: str) -> None:
        """Loads a valid Parquet file successfully."""
        svc = TrajectoryDataService()
        df = svc.load_trajectory(sample_parquet)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert "track_id" in df.columns

    def test_load_file_not_found(self, tmp_path) -> None:
        """Raises FileNotFoundError for missing file."""
        svc = TrajectoryDataService()
        with pytest.raises(FileNotFoundError, match="not found"):
            svc.load_trajectory(str(tmp_path / "nonexistent.parquet"))

    def test_load_corrupted_file(self, tmp_path) -> None:
        """Raises exception for corrupted Parquet file."""
        bad_path = tmp_path / "bad.parquet"
        bad_path.write_text("this is not parquet data")
        svc = TrajectoryDataService()
        with pytest.raises((pa.lib.ArrowInvalid, pd.errors.ParserError, Exception)):
            svc.load_trajectory(str(bad_path))


class TestLoadTrajectorySafe:
    """Tests for TrajectoryDataService.load_trajectory_safe."""

    def test_safe_load_success(self, sample_parquet: str) -> None:
        """Returns DataFrame on success."""
        svc = TrajectoryDataService()
        df = svc.load_trajectory_safe(sample_parquet)
        assert df is not None
        assert len(df) == 3

    def test_safe_load_missing_returns_none(self, tmp_path) -> None:
        """Returns None (not raises) for missing file."""
        svc = TrajectoryDataService()
        result = svc.load_trajectory_safe(str(tmp_path / "missing.parquet"))
        assert result is None

    def test_safe_load_corrupted_returns_none(self, tmp_path) -> None:
        """Returns None (not raises) for corrupted file."""
        bad_path = tmp_path / "bad.parquet"
        bad_path.write_bytes(b"\x00\x01\x02\x03")
        svc = TrajectoryDataService()
        result = svc.load_trajectory_safe(str(bad_path))
        assert result is None
