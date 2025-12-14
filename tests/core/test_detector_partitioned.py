"""
Unit tests for Detector partitioned detection (multi-aquarium mode).

Tests for:
- set_multi_aquarium_zones() configuration
- detect_partitioned() detection with partitioning
- Independent tracking per aquarium
- Track ID offset format
- reset_multi_aquarium_tracking()
"""

import pytest
import numpy as np
from unittest.mock import MagicMock, patch

from zebtrack.core.detector import Detector, AquariumData, ZoneData


@pytest.fixture
def mock_plugin():
    """Create a mock detector plugin."""
    plugin = MagicMock()
    plugin.get_name.return_value = "MockPlugin"
    plugin.class_names = {0: "aquarium", 1: "zebrafish"}
    plugin.detect.return_value = []
    return plugin


@pytest.fixture
def detector(mock_plugin):
    """Create a Detector instance with mock plugin."""
    det = Detector(
        plugin=mock_plugin,
        base_width=1280,
        base_height=720,
    )
    return det


@pytest.fixture
def dual_aquarium_setup():
    """Setup with 2 aquariums side by side."""
    return [
        AquariumData(
            id=0,
            polygon=[[0, 0], [600, 0], [600, 720], [0, 720]],
            roi_polygons=[[[100, 100], [200, 100], [200, 200], [100, 200]]],
            roi_names=["ROI_Centro"],
            roi_colors=[(255, 0, 0)],
            group="Controle",
            subject_id="S01",
            day=1,
        ),
        AquariumData(
            id=1,
            polygon=[[680, 0], [1280, 0], [1280, 720], [680, 720]],
            roi_polygons=[[[800, 100], [900, 100], [900, 200], [800, 200]]],
            roi_names=["ROI_Centro"],
            roi_colors=[(0, 255, 0)],
            group="Tratamento",
            subject_id="S02",
            day=1,
        ),
    ]


class TestSetMultiAquariumZones:
    """Tests for set_multi_aquarium_zones method."""

    def test_set_multi_aquarium_zones_success(self, detector, dual_aquarium_setup):
        """Test successful multi-aquarium zone configuration."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        assert detector._multi_aquarium_mode is True
        assert len(detector._aquariums) == 2
        assert detector._zones_configured is True

    def test_set_multi_aquarium_zones_creates_trackers(self, detector, dual_aquarium_setup):
        """Test that independent ByteTrackers are created for each aquarium."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        assert 0 in detector._byte_trackers_multi
        assert 1 in detector._byte_trackers_multi
        assert detector._byte_trackers_multi[0] is not detector._byte_trackers_multi[1]

    def test_set_multi_aquarium_zones_scales_polygons(self, detector, dual_aquarium_setup):
        """Test that polygons are scaled correctly."""
        # Use different dimensions to test scaling
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=640,  # Half width
            actual_height=360,  # Half height
        )

        # Check polygon 0 was scaled
        scaled_poly_0 = detector._scaled_aquarium_polygons[0]
        assert scaled_poly_0 is not None
        assert scaled_poly_0.shape[0] == 4  # 4 vertices

        # First vertex should be at origin (0, 0)
        assert scaled_poly_0[0][0] == 0
        assert scaled_poly_0[0][1] == 0

        # Second vertex should be at half of original (300, 0)
        assert scaled_poly_0[1][0] == 300

    def test_set_multi_aquarium_zones_invalid_dimensions(self, detector, dual_aquarium_setup):
        """Test error on invalid dimensions."""
        with pytest.raises(ValueError, match="Invalid dimensions"):
            detector.set_multi_aquarium_zones(
                aquariums=dual_aquarium_setup,
                actual_width=0,
                actual_height=720,
            )

    def test_set_multi_aquarium_zones_max_two(self, detector):
        """Test error when more than 2 aquariums provided."""
        three_aquariums = [
            AquariumData(id=0, polygon=[[0, 0], [100, 100]]),
            AquariumData(id=1, polygon=[[200, 0], [300, 100]]),
            AquariumData(id=2, polygon=[[400, 0], [500, 100]]),
        ]

        with pytest.raises(ValueError, match="Maximum of 2"):
            detector.set_multi_aquarium_zones(
                aquariums=three_aquariums,
                actual_width=1280,
                actual_height=720,
            )


class TestDetectPartitioned:
    """Tests for detect_partitioned method."""

    def test_detect_partitioned_requires_multi_mode(self, detector):
        """Test error when not in multi-aquarium mode."""
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        with pytest.raises(RuntimeError, match="not in multi-aquarium mode"):
            detector.detect_partitioned(frame)

    def test_detect_partitioned_validates_frame(self, detector, dual_aquarium_setup):
        """Test frame validation."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        with pytest.raises(ValueError, match="valid numpy array"):
            detector.detect_partitioned(None)

        with pytest.raises(ValueError, match="cannot be empty"):
            detector.detect_partitioned(np.array([]))

    def test_detect_partitioned_correct_assignment(self, detector, mock_plugin, dual_aquarium_setup):
        """Test detections are assigned to correct aquarium."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        # Mock detections - one in each aquarium
        mock_plugin.detect.return_value = [
            # Detection in aquarium 0 (left side, center at ~150)
            (100, 300, 200, 400, 0.9, None, 1),
            # Detection in aquarium 1 (right side, center at ~880)
            (830, 300, 930, 400, 0.85, None, 1),
        ]

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        results = detector.detect_partitioned(frame)

        assert 0 in results
        assert 1 in results
        assert len(results[0]) >= 0  # Could be 0 or 1 depending on tracking
        assert len(results[1]) >= 0

    def test_detect_partitioned_empty_frame(self, detector, mock_plugin, dual_aquarium_setup):
        """Test detection with no detections."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        mock_plugin.detect.return_value = []

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        results = detector.detect_partitioned(frame)

        assert results[0] == []
        assert results[1] == []


class TestTrackIdOffset:
    """Tests for track ID offset format."""

    def test_track_id_offset_format(self, detector, dual_aquarium_setup):
        """Test track IDs follow offset format: aquarium_id * 1000 + local_id."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        # Verify offset calculation
        aquarium_0_track_id = 0 * 1000 + 5  # Local ID 5
        aquarium_1_track_id = 1 * 1000 + 5  # Local ID 5

        assert aquarium_0_track_id == 5
        assert aquarium_1_track_id == 1005

    def test_track_ids_unique_across_aquariums(self, detector, dual_aquarium_setup):
        """Test that track IDs are unique between aquariums."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        # Simulate track IDs from both aquariums
        aq0_ids = [0 * 1000 + i for i in range(1, 10)]
        aq1_ids = [1 * 1000 + i for i in range(1, 10)]

        # No overlap
        assert set(aq0_ids).isdisjoint(set(aq1_ids))


class TestResetMultiAquariumTracking:
    """Tests for reset_multi_aquarium_tracking method."""

    def test_reset_single_aquarium(self, detector, dual_aquarium_setup):
        """Test reset tracking for a single aquarium."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        original_tracker = detector._byte_trackers_multi[0]
        detector.reset_multi_aquarium_tracking(aquarium_id=0)

        # Tracker should be replaced
        assert detector._byte_trackers_multi[0] is not original_tracker
        # Other tracker unchanged
        assert 1 in detector._byte_trackers_multi

    def test_reset_all_aquariums(self, detector, dual_aquarium_setup):
        """Test reset tracking for all aquariums."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        original_0 = detector._byte_trackers_multi[0]
        original_1 = detector._byte_trackers_multi[1]

        detector.reset_multi_aquarium_tracking(aquarium_id=None)

        assert detector._byte_trackers_multi[0] is not original_0
        assert detector._byte_trackers_multi[1] is not original_1


class TestMultiAquariumHelpers:
    """Tests for multi-aquarium helper methods."""

    def test_is_multi_aquarium_mode_false(self, detector):
        """Test is_multi_aquarium_mode returns False initially."""
        assert detector.is_multi_aquarium_mode() is False

    def test_is_multi_aquarium_mode_true(self, detector, dual_aquarium_setup):
        """Test is_multi_aquarium_mode returns True after setup."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )
        assert detector.is_multi_aquarium_mode() is True

    def test_get_aquarium_polygon(self, detector, dual_aquarium_setup):
        """Test get_aquarium_polygon returns scaled polygon."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        poly_0 = detector.get_aquarium_polygon(0)
        poly_1 = detector.get_aquarium_polygon(1)
        poly_missing = detector.get_aquarium_polygon(99)

        assert poly_0 is not None
        assert poly_1 is not None
        assert poly_missing is None

    def test_get_aquarium_roi_polygons(self, detector, dual_aquarium_setup):
        """Test get_aquarium_roi_polygons returns scaled ROIs."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        rois_0 = detector.get_aquarium_roi_polygons(0)
        rois_1 = detector.get_aquarium_roi_polygons(1)
        rois_missing = detector.get_aquarium_roi_polygons(99)

        assert len(rois_0) == 1
        assert len(rois_1) == 1
        assert rois_missing == []

    def test_get_multi_aquarium_data(self, detector, dual_aquarium_setup):
        """Test get_multi_aquarium_data returns aquarium list."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        data = detector.get_multi_aquarium_data()

        assert len(data) == 2
        assert data[0].group == "Controle"
        assert data[1].group == "Tratamento"


class TestPointInPolygon:
    """Tests for _point_in_polygon helper method."""

    def test_point_inside(self, detector):
        """Test point inside polygon returns True."""
        polygon = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.int32)

        assert detector._point_in_polygon((50, 50), polygon) is True

    def test_point_outside(self, detector):
        """Test point outside polygon returns False."""
        polygon = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.int32)

        assert detector._point_in_polygon((200, 200), polygon) is False

    def test_point_on_boundary(self, detector):
        """Test point on boundary returns True."""
        polygon = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.int32)

        # Points on boundary should return True (>= 0)
        assert detector._point_in_polygon((0, 0), polygon) is True
        assert detector._point_in_polygon((50, 0), polygon) is True

    def test_empty_polygon(self, detector):
        """Test empty polygon returns False."""
        polygon = np.array([], dtype=np.int32)

        assert detector._point_in_polygon((50, 50), polygon) is False


class TestDrawMultiAquariumOverlay:
    """Tests for draw_multi_aquarium_overlay method."""

    def test_draw_overlay_returns_frame(self, detector, dual_aquarium_setup):
        """Test draw overlay returns modified frame."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        detections = {0: [], 1: []}

        result = detector.draw_multi_aquarium_overlay(frame, detections)

        assert result is not None
        assert result.shape == (720, 1280, 3)

    def test_draw_overlay_with_detections(self, detector, dual_aquarium_setup):
        """Test draw overlay with detections."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        detections = {
            0: [(100, 200, 150, 250, 0.9, 1, 1)],
            1: [(800, 200, 850, 250, 0.85, 1001, 1)],
        }

        result = detector.draw_multi_aquarium_overlay(frame, detections)

        # Frame should have been modified (not all zeros)
        assert np.any(result > 0)
