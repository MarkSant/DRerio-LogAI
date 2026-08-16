"""
Extended unit tests for TrajectoryDataService.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from zebtrack.core.services.trajectory_data_service import TrajectoryDataService


class TestTrajectoryDataServiceExtended:
    """Test TrajectoryDataService load and safe load operations."""

    def test_load_trajectory_file_not_found(self, tmp_path: Path):
        nonexistent = str(tmp_path / "nonexistent.parquet")
        with pytest.raises(FileNotFoundError, match="Trajectory file not found"):
            TrajectoryDataService.load_trajectory(nonexistent)

    def test_load_trajectory_success(self, tmp_path: Path):
        parquet_file = tmp_path / "3_CoordMovimento_sample.parquet"
        df = pd.DataFrame({"frame": [1, 2], "x_cm": [10.0, 11.0], "y_cm": [5.0, 6.0]})
        df.to_parquet(parquet_file, index=False)

        loaded = TrajectoryDataService.load_trajectory(str(parquet_file))
        assert isinstance(loaded, pd.DataFrame)
        assert len(loaded) == 2
        pd.testing.assert_frame_equal(loaded, df)

    def test_load_trajectory_safe_missing_returns_none(self, tmp_path: Path):
        nonexistent = str(tmp_path / "missing.parquet")
        assert TrajectoryDataService.load_trajectory_safe(nonexistent) is None

    def test_load_trajectory_safe_corrupt_returns_none(self, tmp_path: Path):
        corrupt_file = tmp_path / "corrupt.parquet"
        corrupt_file.write_bytes(b"not a valid parquet file")
        assert TrajectoryDataService.load_trajectory_safe(str(corrupt_file)) is None
