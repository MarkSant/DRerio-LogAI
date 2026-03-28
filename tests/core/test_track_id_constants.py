"""Tests for AQUARIUM_TRACK_ID_MULTIPLIER constant and _offset_track_ids.

Validates:
- Constant values
- Offset arithmetic uses constant instead of magic 1000
- Overflow detection works with MAX_LOCAL_TRACK_ID
"""

from zebtrack.core.detection.multi_aquarium_detector import (
    AQUARIUM_TRACK_ID_MULTIPLIER,
    MAX_LOCAL_TRACK_ID,
    MultiAquariumDetector,
)


class TestTrackIdConstants:
    """Verify constant values and relationships."""

    def test_multiplier_value(self):
        assert AQUARIUM_TRACK_ID_MULTIPLIER == 1000

    def test_max_local_track_id(self):
        assert MAX_LOCAL_TRACK_ID == 999

    def test_relationship(self):
        assert MAX_LOCAL_TRACK_ID == AQUARIUM_TRACK_ID_MULTIPLIER - 1


class TestOffsetTrackIds:
    """Test _offset_track_ids static method."""

    def test_aquarium_0_no_offset(self):
        tracked = [(10, 20, 30, 40, 0.9, 5, 0)]
        result = MultiAquariumDetector._offset_track_ids(tracked, 0)
        assert result[0][5] == 5  # 0 * 1000 + 5

    def test_aquarium_1_offset(self):
        tracked = [(10, 20, 30, 40, 0.9, 5, 0)]
        result = MultiAquariumDetector._offset_track_ids(tracked, 1)
        assert result[0][5] == 1005  # 1 * 1000 + 5

    def test_aquarium_2_offset(self):
        tracked = [(10, 20, 30, 40, 0.9, 3, 0)]
        result = MultiAquariumDetector._offset_track_ids(tracked, 2)
        assert result[0][5] == 2003  # 2 * 1000 + 3

    def test_none_track_id_stays_none(self):
        tracked = [(10, 20, 30, 40, 0.9, None, 0)]
        result = MultiAquariumDetector._offset_track_ids(tracked, 1)
        assert result[0][5] is None

    def test_overflow_track_id_wraps(self):
        """Track ID > MAX_LOCAL_TRACK_ID should be wrapped with modulo."""
        tracked = [(10, 20, 30, 40, 0.9, 1500, 0)]
        result = MultiAquariumDetector._offset_track_ids(tracked, 1)
        # 1500 > 999 → overflow path: 1 * 1000 + (1500 % 1000) = 1500
        assert result[0][5] == 1500

    def test_boundary_track_id_at_max(self):
        """Track ID exactly at MAX_LOCAL_TRACK_ID should NOT trigger overflow."""
        tracked = [(10, 20, 30, 40, 0.9, MAX_LOCAL_TRACK_ID, 0)]
        result = MultiAquariumDetector._offset_track_ids(tracked, 1)
        assert result[0][5] == 1000 + MAX_LOCAL_TRACK_ID  # 1999

    def test_boundary_track_id_above_max(self):
        """Track ID one above MAX_LOCAL_TRACK_ID SHOULD trigger overflow."""
        tracked = [(10, 20, 30, 40, 0.9, MAX_LOCAL_TRACK_ID + 1, 0)]
        result = MultiAquariumDetector._offset_track_ids(tracked, 1)
        # 1000 > 999 → overflow: 1 * 1000 + (1000 % 1000) = 1000
        assert result[0][5] == 1000

    def test_empty_list(self):
        assert MultiAquariumDetector._offset_track_ids([], 0) == []

    def test_multiple_detections(self):
        tracked = [
            (0, 0, 10, 10, 0.9, 1, 0),
            (20, 20, 30, 30, 0.8, 2, 0),
            (40, 40, 50, 50, 0.7, None, 0),
        ]
        result = MultiAquariumDetector._offset_track_ids(tracked, 1)
        assert result[0][5] == 1001
        assert result[1][5] == 1002
        assert result[2][5] is None
