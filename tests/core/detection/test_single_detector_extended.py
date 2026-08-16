"""
Extended unit tests for SingleDetector in core/detection/single_detector.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.core.detection.detection_types import AquariumData, MultiAquariumZoneData, ZoneData
from zebtrack.core.detection.single_detector import SingleDetector
from zebtrack.core.detection.zone_scaler import ZoneScaler
from zebtrack.plugins.base import DetectorPlugin
from zebtrack.settings import load_settings


class TestSingleDetectorExtended:
    """Test SingleDetector initialization, zones, modes, and tracking."""

    @pytest.fixture
    def mock_plugin(self) -> MagicMock:
        plugin = MagicMock(spec=DetectorPlugin)
        plugin.get_name.return_value = "MockDetector"
        plugin.detect.return_value = []
        return plugin

    def test_init_none_plugin_raises_value_error(self):
        with pytest.raises(ValueError, match="must be initialized with a valid plugin"):
            SingleDetector(plugin=None)  # type: ignore[arg-type]

    def test_init_custom_dimensions_and_dependencies(self, mock_plugin: MagicMock):
        settings_obj = load_settings()
        scaler = ZoneScaler(base_width=1920, base_height=1080)

        detector = SingleDetector(
            plugin=mock_plugin,
            zone_scaler=scaler,
            base_width=1920,
            base_height=1080,
            settings_obj=settings_obj,
        )

        assert detector.plugin is mock_plugin
        assert detector.zone_scaler is scaler
        assert detector.base_width == 1920
        assert detector.base_height == 1080
        assert detector.settings is settings_obj
        assert detector._zones_configured is False

    def test_set_zones_invalid_dimensions_raises(self, mock_plugin: MagicMock):
        detector = SingleDetector(plugin=mock_plugin)
        zone_data = ZoneData()
        with pytest.raises(ValueError, match="Actual dimensions must be positive"):
            detector.set_zones(zone_data, actual_width=0, actual_height=720)

    def test_set_zones_with_zone_data(self, mock_plugin: MagicMock):
        detector = SingleDetector(plugin=mock_plugin)
        zone_data = ZoneData(
            polygon=[[10, 10], [100, 10], [100, 100], [10, 100]],
            roi_polygons=[[[20, 20], [50, 20], [50, 50], [20, 50]]],
            roi_names=["Center"],
            roi_colors=[(255, 0, 0)],
        )

        detector.set_zones(zone_data, actual_width=1280, actual_height=720)

        assert detector.zones == zone_data
        assert detector._zones_configured is True
        assert detector._last_width == 1280
        assert detector._last_height == 720

    def test_set_zones_with_multi_aquarium_zone_data(self, mock_plugin: MagicMock):
        detector = SingleDetector(plugin=mock_plugin)
        aq0 = AquariumData(id=0, polygon=[[0, 0], [50, 50]])
        multi_data = MultiAquariumZoneData(aquariums=[aq0])

        detector.set_zones(multi_data, actual_width=1280, actual_height=720)

        assert detector.zones == multi_data
        assert detector._zones_configured is True

    def test_set_context_and_aquarium_region(self, mock_plugin: MagicMock):
        detector = SingleDetector(plugin=mock_plugin)
        detector.set_context("diagnostic")
        assert detector._context == "diagnostic"

        detector.set_aquarium_region_defined(True)
        assert detector._aquarium_region_defined is True

    def test_set_single_subject_mode(self, mock_plugin: MagicMock):
        detector = SingleDetector(plugin=mock_plugin)
        assert detector._single_subject_mode is False

        detector.set_single_subject_mode(True)
        assert detector._single_subject_mode is True

        detector.set_single_subject_mode(False)
        assert detector._single_subject_mode is False
