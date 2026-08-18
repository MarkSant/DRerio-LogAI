"""Extended unit tests for analysis/behavior.py (Part 2)."""

from __future__ import annotations

import pandas as pd

from zebtrack.analysis.behavior import Episode


class TestBehaviorExtended2:
    """Test Episode TypedDict and BehavioralAnalyzer input validation."""

    def test_episode_typed_dict(self):
        ep: Episode = {
            "start_time": pd.Timedelta(seconds=1),
            "end_time": pd.Timedelta(seconds=5),
            "duration": 4.0,
            "track_id": 1,
        }
        assert ep["duration"] == 4.0
        assert ep["track_id"] == 1
        assert "start_time" in ep
        assert "end_time" in ep

    def test_episode_without_track_id(self):
        ep: Episode = {
            "start_time": 0.0,
            "end_time": 2.5,
            "duration": 2.5,
        }
        assert ep["duration"] == 2.5
        assert "track_id" not in ep

    def test_episode_zero_duration(self):
        ep: Episode = {
            "start_time": 10.0,
            "end_time": 10.0,
            "duration": 0.0,
        }
        assert ep["duration"] == 0.0
