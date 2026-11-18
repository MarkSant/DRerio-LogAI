"""
Extended unit tests for TrajectoryDataService.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from zebtrack.core.services.trajectory_data_service import TrajectoryDataService


class TestTrajectoryDataServiceExtended:
    """Test TrajectoryDataService load operations."""

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
