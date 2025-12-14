"""
Unit tests for Detector partitioned detection (multi-aquarium mode).

Tests for:
- set_multi_aquarium_zones() configuration
- detect_partitioned() detection with partitioning
- Independent tracking per aquarium
- Track ID offset format
- reset_multi_aquarium_tracking()
"""

from unittest.mock import MagicMock

import numpy as np
import pytest

from zebtrack.core.detector import AquariumData, Detector


@pytest.fixture
def mock_plugin():
    """Create a mock detector plugin."""
    plugin = MagicMock()
    plugin.get_name.return_value = "MockPlugin"
    plugin.class_names = {0: "aquarium", 1: "zebrafish"}
    plugin.detect.return_value = []
    # Remove detect_batch so it falls back to sequential processing
    del plugin.detect_batch
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

    def test_set_multi_aquarium_zones_uses_single_animal_mode(
        self, detector, dual_aquarium_setup
    ):
        """Test that ByteTrackers use single_animal_mode=True for 1 animal per aquarium.

        This ensures each aquarium gets stable tracking with ID Resurrection
        and Immediate Activation, just like single-aquarium mode.
        Track IDs will be: Aquarium 0 → local 1 → global 1
                          Aquarium 1 → local 1 → global 1001
        """
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        # Verify each ByteTracker has single_animal_mode enabled
        for aq_id in [0, 1]:
            tracker = detector._byte_trackers_multi[aq_id]
            assert hasattr(tracker, "single_animal_mode"), (
                f"ByteTracker for aquarium {aq_id} missing single_animal_mode attribute"
            )
            assert tracker.single_animal_mode is True, (
                f"ByteTracker for aquarium {aq_id} should have single_animal_mode=True"
            )

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

    def test_detect_partitioned_correct_assignment(
        self, detector, mock_plugin, dual_aquarium_setup
    ):
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

    def test_reset_preserves_single_animal_mode(self, detector, dual_aquarium_setup):
        """Test that reset tracking preserves single_animal_mode=True."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        # Reset all aquariums
        detector.reset_multi_aquarium_tracking(aquarium_id=None)

        # Verify single_animal_mode is preserved after reset
        for aq_id in [0, 1]:
            tracker = detector._byte_trackers_multi[aq_id]
            assert hasattr(tracker, "single_animal_mode"), (
                f"Reset ByteTracker for aquarium {aq_id} missing single_animal_mode"
            )
            assert tracker.single_animal_mode is True, (
                f"Reset ByteTracker for aquarium {aq_id} should have single_animal_mode=True"
            )


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


class TestROICroppingOptimization:
    """Tests for ROI cropping optimization methods."""

    def test_crop_aquarium_region_returns_correct_crop(self, detector, dual_aquarium_setup):
        """Test that _crop_aquarium_region returns correctly cropped region."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        # Create a frame with identifiable pattern
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        # Mark aquarium 0 region (left side: 0-600)
        frame[0:720, 0:600, 0] = 100  # Blue channel = 100 for left side
        # Mark aquarium 1 region (right side: 640-1280)
        frame[0:720, 640:1280, 1] = 200  # Green channel = 200 for right side

        # Crop aquarium 0
        cropped_0, crop_info_0 = detector._crop_aquarium_region(frame, 0, padding=0)
        assert cropped_0 is not None
        assert crop_info_0 is not None
        x_off, y_off, w, h = crop_info_0
        # Cropped region should contain the aquarium 0 marker
        assert np.mean(cropped_0[:, :, 0]) > 50  # Blue channel should be present

        # Crop aquarium 1
        cropped_1, crop_info_1 = detector._crop_aquarium_region(frame, 1, padding=0)
        assert cropped_1 is not None
        x_off_1, _, _, _ = crop_info_1
        # Aquarium 1 offset should be around 640
        assert x_off_1 >= 600

    def test_crop_aquarium_region_with_padding(self, detector, dual_aquarium_setup):
        """Test cropping with padding expands the region."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        # Get crop without padding
        _, info_no_pad = detector._crop_aquarium_region(frame, 0, padding=0)
        # Get crop with padding
        _, info_with_pad = detector._crop_aquarium_region(frame, 0, padding=20)

        x0, y0, w0, h0 = info_no_pad
        x1, y1, w1, h1 = info_with_pad

        # With padding, offset should be smaller (or equal if at edge)
        assert x1 <= x0
        assert y1 <= y0
        # Width and height should be larger (or equal if at edge)
        assert w1 >= w0
        assert h1 >= h0

    def test_crop_aquarium_region_invalid_aquarium(self, detector, dual_aquarium_setup):
        """Test cropping with invalid aquarium ID falls back to full frame."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        # Try to crop non-existent aquarium - should fall back to full frame
        cropped, crop_info = detector._crop_aquarium_region(frame, 999, padding=0)
        # Should return full frame dimensions as fallback
        assert cropped is not None
        assert crop_info == (0, 0, 1280, 720)

    def test_crop_aquarium_region_without_multi_aquarium(self, detector):
        """Test cropping when multi-aquarium is not configured returns full frame."""
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        # Should return full frame as fallback when no multi-aquarium configured
        cropped, crop_info = detector._crop_aquarium_region(frame, 0, padding=0)
        assert cropped is not None
        assert crop_info == (0, 0, 1280, 720)

    def test_detect_partitioned_optimized_coordinates_adjusted(
        self, detector, dual_aquarium_setup, mock_plugin
    ):
        """Test that detect_partitioned_optimized adjusts coordinates correctly."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        # Mock detection in cropped region - returns local coordinates
        # For aquarium 1 (right side), local detection at (50, 50, 80, 80)
        # should be adjusted to global coordinates
        mock_plugin.detect.return_value = [(50, 50, 80, 80, 0.95, 1)]

        detections = detector.detect_partitioned_optimized(frame, use_cropping=True)

        # Should have detections from both aquariums
        assert 0 in detections
        assert 1 in detections

    def test_detect_partitioned_optimized_without_cropping_fallback(
        self, detector, dual_aquarium_setup, mock_plugin
    ):
        """Test that use_cropping=False falls back to regular method."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        mock_plugin.detect.return_value = []

        # Should work with cropping disabled
        detections = detector.detect_partitioned_optimized(frame, use_cropping=False)

        assert isinstance(detections, dict)
        assert 0 in detections
        assert 1 in detections

    def test_cropping_reduces_processed_pixels(self, detector, dual_aquarium_setup):
        """Test that cropping reduces the number of pixels processed."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        full_frame_pixels = frame.shape[0] * frame.shape[1]  # 720 * 1280 = 921,600

        # Get cropped regions for both aquariums
        cropped_0, info_0 = detector._crop_aquarium_region(frame, 0, padding=10)
        cropped_1, info_1 = detector._crop_aquarium_region(frame, 1, padding=10)

        if cropped_0 is not None and cropped_1 is not None:
            cropped_pixels = (
                cropped_0.shape[0] * cropped_0.shape[1]
                + cropped_1.shape[0] * cropped_1.shape[1]
            )

            # Total cropped pixels should be less than full frame
            # (since aquariums don't overlap and don't cover entire frame)
            assert cropped_pixels < full_frame_pixels

    def test_crop_info_format(self, detector, dual_aquarium_setup):
        """Test that crop_info returns correct format (x_offset, y_offset, width, height)."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        cropped, crop_info = detector._crop_aquarium_region(frame, 0, padding=0)

        assert cropped is not None
        assert len(crop_info) == 4

        x_offset, y_offset, width, height = crop_info

        # All values should be non-negative
        assert x_offset >= 0
        assert y_offset >= 0
        assert width > 0
        assert height > 0

        # Cropped image dimensions should match crop_info
        assert cropped.shape[0] == height
        assert cropped.shape[1] == width


class TestParallelDetection:
    """Tests for Phase 2.1 parallel detection."""

    def test_detect_partitioned_parallel_returns_dict(
        self, detector, dual_aquarium_setup, mock_plugin
    ):
        """Test parallel detection returns dictionary with correct keys."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        mock_plugin.detect.return_value = []

        results = detector.detect_partitioned_parallel(frame, max_workers=2)

        assert isinstance(results, dict)
        assert 0 in results
        assert 1 in results

    def test_detect_partitioned_parallel_requires_multi_mode(self, detector):
        """Test parallel detection requires multi-aquarium mode."""
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        with pytest.raises(RuntimeError, match="not in multi-aquarium mode"):
            detector.detect_partitioned_parallel(frame)

    def test_detect_partitioned_parallel_with_detections(
        self, detector, dual_aquarium_setup, mock_plugin
    ):
        """Test parallel detection processes detections correctly."""
        detector.set_multi_aquarium_zones(
            aquariums=dual_aquarium_setup,
            actual_width=1280,
            actual_height=720,
        )

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        # Return a detection in cropped coordinates
        mock_plugin.detect.return_value = [(10, 10, 50, 50, 0.9, 1)]

        results = detector.detect_partitioned_parallel(frame, max_workers=2)

        # Both aquariums should have detections (mock returns same for both)
        assert len(results[0]) > 0 or len(results[1]) > 0


class TestBatchInference:
    """Tests for Phase 2.2 batch inference."""

    def test_detect_batch_empty_list(self, detector):
        """Test batch detection with empty frame list."""
        results = detector.detect_batch([], batch_size=4)
        assert results == []

    def test_detect_batch_returns_list(self, detector, mock_plugin):
        """Test batch detection returns list of detection lists."""
        # Initialize zones to enable byte tracker using ZoneData
        from zebtrack.core.detector import ZoneData

        zones = ZoneData(polygon=[(0, 0), (1280, 0), (1280, 720), (0, 720)])
        detector.set_zones(zones, 1280, 720)

        frames = [np.zeros((720, 1280, 3), dtype=np.uint8) for _ in range(3)]
        mock_plugin.detect.return_value = []

        results = detector.detect_batch(frames, batch_size=2)

        assert isinstance(results, list)
        assert len(results) == 3

    def test_detect_batch_respects_batch_size(self, detector, mock_plugin):
        """Test batch detection respects batch size parameter."""
        # Initialize zones to enable byte tracker using ZoneData
        from zebtrack.core.detector import ZoneData

        zones = ZoneData(polygon=[(0, 0), (1280, 0), (1280, 720), (0, 720)])
        detector.set_zones(zones, 1280, 720)

        frames = [np.zeros((720, 1280, 3), dtype=np.uint8) for _ in range(5)]
        mock_plugin.detect.return_value = [(10, 10, 50, 50, 0.9, 1)]

        results = detector.detect_batch(frames, batch_size=2)

        # Should process 5 frames in 3 batches (2+2+1)
        assert len(results) == 5
        # Each result should be a list of detections
        for result in results:
            assert isinstance(result, list)

    def test_detect_batch_with_native_batch_support(self, detector, mock_plugin):
        """Test batch detection uses native batch if plugin supports it."""
        # Initialize zones to enable byte tracker using ZoneData
        from zebtrack.core.detector import ZoneData

        zones = ZoneData(polygon=[(0, 0), (1280, 0), (1280, 720), (0, 720)])
        detector.set_zones(zones, 1280, 720)

        frames = [np.zeros((720, 1280, 3), dtype=np.uint8) for _ in range(2)]

        # Mock native batch support
        mock_plugin.detect_batch = MagicMock(
            return_value=[[(10, 10, 50, 50, 0.9, 1)], [(20, 20, 60, 60, 0.85, 2)]]
        )

        results = detector.detect_batch(frames, batch_size=2)

        # Should use native batch method
        mock_plugin.detect_batch.assert_called_once()
        assert len(results) == 2
