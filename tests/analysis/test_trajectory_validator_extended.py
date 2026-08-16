"""
Extended unit tests for TrajectoryQualityValidator.
"""

from __future__ import annotations

import pandas as pd

from zebtrack.analysis.trajectory_validator import TrajectoryQualityValidator


class TestTrajectoryQualityValidatorExtended:
    """Test comprehensive validation checks in TrajectoryQualityValidator."""

    def test_empty_dataframe(self):
        val = TrajectoryQualityValidator(fps=30.0)
        res = val.validate(pd.DataFrame())
        assert res["is_valid"] is False
        assert "Trajectory dataframe is empty" in res["errors"]

    def test_missing_required_columns(self):
        val = TrajectoryQualityValidator(fps=30.0, min_trajectory_frames=5)
        df = pd.DataFrame({"x_cm": [1.0, 2.0]})
        res = val.validate(df)
        assert any("Missing required columns" in w for w in res["warnings"])

    def test_short_trajectory_warning(self):
        val = TrajectoryQualityValidator(fps=30.0, min_trajectory_frames=50)
        df = pd.DataFrame(
            {
                "frame": list(range(10)),
                "track_id": [1] * 10,
                "x_cm": [1.0] * 10,
                "y_cm": [1.0] * 10,
            }
        )
        res = val.validate(df)
        assert any("Trajectory is short" in w for w in res["warnings"])

    def test_speed_violations_detection_with_timestamps(self):
        val = TrajectoryQualityValidator(
            fps=30.0,
            max_plausible_speed_cm_s=20.0,
            min_trajectory_frames=5,
        )
        # Teleport: 0 to 100 cm in 0.1s = 1000 cm/s
        df = pd.DataFrame(
            {
                "frame": [1, 2, 3, 4, 5],
                "timestamp": [0.0, 0.1, 0.2, 0.3, 0.4],
                "track_id": [1, 1, 1, 1, 1],
                "x_cm": [0.0, 100.0, 100.1, 100.2, 100.3],
                "y_cm": [0.0, 0.0, 0.0, 0.0, 0.0],
            }
        )
        res = val.validate(df)
        assert any("implausible speed" in w for w in res["warnings"])
        assert "speed_violations" in res["stats"]
        assert res["stats"]["speed_violations"]["count"] >= 1

    def test_temporal_gaps_anomalous_detection(self):
        val = TrajectoryQualityValidator(fps=30.0, min_trajectory_frames=5)
        # Big jump in frame numbers from 2 to 100
        df = pd.DataFrame(
            {
                "frame": [1, 2, 100, 101, 102],
                "track_id": [1, 1, 1, 1, 1],
                "x_cm": [1.0, 1.1, 1.2, 1.3, 1.4],
                "y_cm": [1.0, 1.0, 1.0, 1.0, 1.0],
            }
        )
        res = val.validate(df)
        assert any("anomalous temporal gaps" in w for w in res["warnings"])
        assert "temporal_gaps" in res["stats"]

    def test_arena_violations_detection(self):
        val = TrajectoryQualityValidator(fps=30.0, min_trajectory_frames=3)
        # Arena bounded (0,0) to (10,10)
        arena = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]
        # Point (15, 15) is outside arena
        df = pd.DataFrame(
            {
                "frame": [1, 2, 3],
                "track_id": [1, 1, 1],
                "x_cm": [5.0, 15.0, 5.0],
                "y_cm": [5.0, 15.0, 5.0],
            }
        )
        res = val.validate(df, arena_polygon=arena)
        assert any("outside arena" in w for w in res["warnings"])
        assert "arena_violations" in res["stats"]

    def test_duplicate_frames_detected_as_error(self):
        val = TrajectoryQualityValidator(fps=30.0, min_trajectory_frames=3)
        df = pd.DataFrame(
            {
                "frame": [1, 1, 2],  # Duplicate frame 1 for same track
                "track_id": [1, 1, 1],
                "x_cm": [1.0, 1.0, 2.0],
                "y_cm": [1.0, 1.0, 2.0],
            }
        )
        res = val.validate(df)
        assert res["is_valid"] is False
        assert any("duplicate frame+track_id entries" in e for e in res["errors"])

    def test_track_id_instability_warning(self):
        val = TrajectoryQualityValidator(fps=30.0, min_trajectory_frames=5)
        # Frequent switches
        df = pd.DataFrame(
            {
                "frame": [1, 2, 3, 4, 5, 6],
                "track_id": [1, 2, 1, 2, 1, 2],
                "x_cm": [1.0] * 6,
                "y_cm": [1.0] * 6,
            }
        )
        res = val.validate(df)
        assert any("High frequency of track_id changes" in w for w in res["warnings"])
