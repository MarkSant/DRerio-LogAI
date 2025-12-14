"""Tests for TrajectoryQualityValidator multi-aquarium features.

Phase 4: Robustness - 4.1 Tracking Validation, 4.2 Gap Detection
"""

import numpy as np
import pandas as pd
import pytest

from zebtrack.analysis.trajectory_validator import TrajectoryQualityValidator


class TestMultiAquariumIdValidation:
    """Test 4.1: Multi-aquarium track ID validation."""

    @pytest.fixture
    def validator(self):
        """Create validator with typical settings."""
        return TrajectoryQualityValidator(
            fps=30.0,
            max_plausible_speed_cm_s=50.0,
            min_trajectory_frames=10,
        )

    def test_valid_track_ids_within_bounds(self, validator):
        """Track IDs within expected aquarium ranges pass validation."""
        # Aquarium 0: IDs 0-999, Aquarium 1: IDs 1000-1999
        # Use a single aquarium to avoid cross-aquarium speed issues
        df = pd.DataFrame({
            "frame": list(range(1, 20)),
            "track_id": [1] * 19,
            "aquarium_id": [0] * 19,
            "x_cm": [1.0 + i * 0.01 for i in range(19)],  # Very slow movement
            "y_cm": [1.0] * 19,
        })

        result = validator.validate(df)

        # Should pass without ID-related warnings
        assert result["is_valid"]
        id_warnings = [w for w in result["warnings"] if "outside expected range" in w]
        assert len(id_warnings) == 0
        # Validate multi-aquarium stats exist
        assert "multi_aquarium_validation" in result["stats"]
        assert result["stats"]["multi_aquarium_validation"]["id_violations_count"] == 0

    def test_track_ids_outside_aquarium_bounds_warns(self, validator):
        """Track IDs outside aquarium bounds generate warnings."""
        # Aquarium 0 with ID 1500 (should be 0-999)
        df = pd.DataFrame({
            "frame": [1, 2, 3],
            "track_id": [1500, 1500, 1500],  # Wrong range for aquarium 0
            "aquarium_id": [0, 0, 0],
            "x_cm": [1.0, 1.1, 1.2],
            "y_cm": [1.0, 1.0, 1.0],
        })

        result = validator.validate(df)

        # Should warn about ID outside range
        id_warnings = [w for w in result["warnings"] if "outside expected range" in w]
        assert len(id_warnings) > 0
        assert "1500" in id_warnings[0]

    def test_large_track_id_jumps_detected(self, validator):
        """Large track ID jumps within aquarium are detected."""
        df = pd.DataFrame({
            "frame": [1, 2, 3, 4, 5],
            "track_id": [1, 1, 200, 200, 200],  # Jump of 199
            "aquarium_id": [0, 0, 0, 0, 0],
            "x_cm": [1.0, 1.1, 1.2, 1.3, 1.4],
            "y_cm": [1.0, 1.0, 1.0, 1.0, 1.0],
        })

        result = validator.validate(df)

        # Should warn about large ID jumps
        jump_warnings = [w for w in result["warnings"] if "track ID jumps" in w]
        assert len(jump_warnings) > 0

    def test_multiple_aquariums_validated_independently(self, validator):
        """Each aquarium is validated independently."""
        df = pd.DataFrame({
            "frame": [1, 2, 3, 1, 2, 3],
            "track_id": [1, 1, 1, 2000, 2000, 2000],  # Aquarium 1 has wrong ID
            "aquarium_id": [0, 0, 0, 1, 1, 1],
            "x_cm": [1.0, 1.1, 1.2, 5.0, 5.1, 5.2],
            "y_cm": [1.0, 1.0, 1.0, 5.0, 5.0, 5.0],
        })

        result = validator.validate(df)

        # Should warn about aquarium 1 having ID 2000 (expected 1000-1999)
        assert "multi_aquarium_validation" in result["stats"]
        stats = result["stats"]["multi_aquarium_validation"]
        assert stats["id_violations_count"] > 0

    def test_stats_contain_aquarium_details(self, validator):
        """Validation stats include per-aquarium track ID details."""
        df = pd.DataFrame({
            "frame": [1, 2, 1, 2],
            "track_id": [5, 5, 1005, 1005],
            "aquarium_id": [0, 0, 1, 1],
            "x_cm": [1.0, 1.1, 5.0, 5.1],
            "y_cm": [1.0, 1.0, 5.0, 5.0],
        })

        result = validator.validate(df)

        assert "multi_aquarium_validation" in result["stats"]
        stats = result["stats"]["multi_aquarium_validation"]
        assert "aquariums" in stats
        assert "aquarium_0" in stats["aquariums"]
        assert "aquarium_1" in stats["aquariums"]


class TestPerAquariumGapDetection:
    """Test 4.2: Per-aquarium gap detection."""

    @pytest.fixture
    def validator(self):
        """Create validator with typical settings."""
        return TrajectoryQualityValidator(
            fps=30.0,
            max_plausible_speed_cm_s=50.0,
            min_trajectory_frames=5,
        )

    def test_no_gaps_full_coverage(self, validator):
        """Perfect coverage reports 100% for each aquarium."""
        df = pd.DataFrame({
            "frame": [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
            "track_id": [1, 1, 1, 1, 1, 1001, 1001, 1001, 1001, 1001],
            "aquarium_id": [0, 0, 0, 0, 0, 1, 1, 1, 1, 1],
            "x_cm": [1.0] * 10,
            "y_cm": [1.0] * 10,
        })

        result = validator.validate(df)

        assert "per_aquarium_gaps" in result["stats"]
        for aq_stats in result["stats"]["per_aquarium_gaps"]["per_aquarium"].values():
            assert aq_stats["coverage_percent"] == 100.0
            assert aq_stats["gap_count"] == 0

    def test_gaps_detected_per_aquarium(self, validator):
        """Missing frames in one aquarium are detected independently."""
        # Aquarium 0 has frames 1,2,3,4,5, Aquarium 1 missing frame 3
        df = pd.DataFrame({
            "frame": [1, 2, 3, 4, 5, 1, 2, 4, 5],  # Missing frame 3 for aq 1
            "track_id": [1, 1, 1, 1, 1, 1001, 1001, 1001, 1001],
            "aquarium_id": [0, 0, 0, 0, 0, 1, 1, 1, 1],
            "x_cm": [1.0] * 9,
            "y_cm": [1.0] * 9,
        })

        result = validator.validate(df)

        assert "per_aquarium_gaps" in result["stats"]
        gaps = result["stats"]["per_aquarium_gaps"]["per_aquarium"]

        # Aquarium 0 should have full coverage
        assert gaps["aquarium_0"]["coverage_percent"] == 100.0

        # Aquarium 1 should have missing frame
        assert gaps["aquarium_1"]["total_missing_frames"] == 1
        assert gaps["aquarium_1"]["coverage_percent"] < 100.0

    def test_large_gap_generates_warning(self, validator):
        """Low coverage triggers warning."""
        # Only 4 out of 10 frames detected
        df = pd.DataFrame({
            "frame": [1, 2, 9, 10, 1, 2, 9, 10],
            "track_id": [1, 1, 1, 1, 1001, 1001, 1001, 1001],
            "aquarium_id": [0, 0, 0, 0, 1, 1, 1, 1],
            "x_cm": [1.0] * 8,
            "y_cm": [1.0] * 8,
        })

        result = validator.validate(df)

        # Should warn about low coverage
        coverage_warnings = [w for w in result["warnings"] if "Low detection coverage" in w]
        assert len(coverage_warnings) > 0

    def test_longest_gap_tracked(self, validator):
        """Longest gap is recorded in stats."""
        # Gap of 3 frames (4, 5, 6 missing)
        df = pd.DataFrame({
            "frame": [1, 2, 3, 7, 8, 9, 10],
            "track_id": [1] * 7,
            "aquarium_id": [0] * 7,
            "x_cm": [1.0] * 7,
            "y_cm": [1.0] * 7,
        })

        result = validator.validate(df)

        gaps = result["stats"]["per_aquarium_gaps"]["per_aquarium"]["aquarium_0"]
        assert gaps["longest_gap_frames"] == 3
        assert gaps["longest_gap_range"] == [4, 6]


class TestErrorRecoveryIntegration:
    """Test that validation continues even with partial data."""

    @pytest.fixture
    def validator(self):
        return TrajectoryQualityValidator(fps=30.0)

    def test_empty_aquarium_handled(self, validator):
        """Empty aquarium data doesn't crash validation."""
        df = pd.DataFrame({
            "frame": [],
            "track_id": [],
            "aquarium_id": [],
            "x_cm": [],
            "y_cm": [],
        })

        # Should not crash
        result = validator.validate(df)
        assert "is_valid" in result

    def test_missing_aquarium_columns_graceful(self, validator):
        """Missing aquarium_id column doesn't use multi-aquarium validation."""
        df = pd.DataFrame({
            "frame": [1, 2, 3],
            "track_id": [1, 1, 1],
            "x_cm": [1.0, 1.1, 1.2],
            "y_cm": [1.0, 1.0, 1.0],
        })

        result = validator.validate(df)

        # Should skip multi-aquarium validation
        assert "multi_aquarium_validation" not in result["stats"]
        assert "per_aquarium_gaps" not in result["stats"]

    def test_nan_track_ids_handled(self, validator):
        """NaN track IDs don't break multi-aquarium validation."""
        df = pd.DataFrame({
            "frame": [1, 2, 3, 4],
            "track_id": [1, np.nan, 1, 1],
            "aquarium_id": [0, 0, 0, 0],
            "x_cm": [1.0, 1.1, 1.2, 1.3],
            "y_cm": [1.0, 1.0, 1.0, 1.0],
        })

        # Should not crash
        result = validator.validate(df)
        assert "is_valid" in result
