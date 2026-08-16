"""
Extended unit tests for MultiAquariumDetector in core/detection/multi_aquarium_detector.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.core.detection.detection_post_processor import DetectionPostProcessor
from zebtrack.core.detection.detection_types import AquariumData
from zebtrack.core.detection.multi_aquarium_detector import (
    AQUARIUM_TRACK_ID_MULTIPLIER,
    MAX_LOCAL_TRACK_ID,
    MultiAquariumDetector,
)
from zebtrack.core.detection.zone_scaler import ZoneScaler
from zebtrack.plugins.base import DetectorPlugin
from zebtrack.settings import load_settings


class TestMultiAquariumDetectorExtended:
    """Test MultiAquariumDetector initialization, track IDs, and scaling."""

    @pytest.fixture
    def mock_plugin(self) -> MagicMock:
        plugin = MagicMock(spec=DetectorPlugin)
        plugin.get_name.return_value = "MockDetectorPlugin"
        plugin.detect.return_value = []
        return plugin

    def test_constants(self):
        assert AQUARIUM_TRACK_ID_MULTIPLIER == 1000
        assert MAX_LOCAL_TRACK_ID == 999

    def test_init_none_plugin_raises(self):
        scaler = ZoneScaler(1280, 720)
        post_proc = DetectionPostProcessor()
        with pytest.raises(ValueError, match="must be initialized with a valid plugin"):
            MultiAquariumDetector(
                plugin=None,  # type: ignore[arg-type]
                zone_scaler=scaler,
                post_processor=post_proc,
            )

    def test_init_success(self, mock_plugin: MagicMock):
        settings_obj = load_settings()
        scaler = ZoneScaler(1920, 1080)
        post_proc = DetectionPostProcessor()

        detector = MultiAquariumDetector(
            plugin=mock_plugin,
            zone_scaler=scaler,
            post_processor=post_proc,
            base_width=1920,
            base_height=1080,
            settings_obj=settings_obj,
        )

        assert detector.plugin is mock_plugin
        assert detector.zone_scaler is scaler
        assert detector.post_processor is post_proc
        assert detector.base_width == 1920
        assert detector.base_height == 1080
        assert detector.settings is settings_obj
        assert detector._multi_aquarium_mode is False

    def test_set_multi_aquarium_zones_invalid_dimensions_raises(self, mock_plugin: MagicMock):
        scaler = ZoneScaler(1280, 720)
        post_proc = DetectionPostProcessor()
        detector = MultiAquariumDetector(
            plugin=mock_plugin,
            zone_scaler=scaler,
            post_processor=post_proc,
        )
        with pytest.raises(ValueError, match="Invalid dimensions"):
            detector.set_multi_aquarium_zones([], actual_width=0, actual_height=720)

    def test_set_multi_aquarium_zones_more_than_two_raises(self, mock_plugin: MagicMock):
        scaler = ZoneScaler(1280, 720)
        post_proc = DetectionPostProcessor()
        detector = MultiAquariumDetector(
            plugin=mock_plugin,
            zone_scaler=scaler,
            post_processor=post_proc,
        )
        aq = AquariumData(id=0, polygon=[[0, 0], [10, 0], [10, 10]])
        with pytest.raises(ValueError, match="Maximum of 2 aquariums supported"):
            detector.set_multi_aquarium_zones([aq, aq, aq], actual_width=1280, actual_height=720)

    def test_set_multi_aquarium_zones_success(self, mock_plugin: MagicMock):
        scaler = ZoneScaler(1280, 720)
        post_proc = DetectionPostProcessor()
        detector = MultiAquariumDetector(
            plugin=mock_plugin,
            zone_scaler=scaler,
            post_processor=post_proc,
        )

        aq0 = AquariumData(
            id=0,
            polygon=[[10, 10], [500, 10], [500, 500], [10, 500]],
            roi_polygons=[[[50, 50], [150, 50], [150, 150], [50, 150]]],
            roi_names=["TopLeft0"],
        )
        aq1 = AquariumData(
            id=1,
            polygon=[[600, 10], [1100, 10], [1100, 500], [600, 500]],
            roi_polygons=[[[650, 50], [750, 50], [750, 150], [650, 150]]],
            roi_names=["TopLeft1"],
        )

        detector.set_multi_aquarium_zones([aq0, aq1], actual_width=1280, actual_height=720)

        assert detector._multi_aquarium_mode is True
        assert detector._zones_configured is True
        assert len(detector._aquariums) == 2

        # Verify scaled polygon lookups
        assert 0 in detector._scaled_aquarium_polygons
        poly0 = detector._scaled_aquarium_polygons[0]
        assert poly0.shape == (4, 2)

        assert 0 in detector._scaled_aquarium_roi_polygons
        rois0 = detector._scaled_aquarium_roi_polygons[0]
        assert len(rois0) == 1
