"""Extended unit tests for core/services/zone_context_service.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.detection import AquariumData, MultiAquariumZoneData, ZoneData
from zebtrack.core.services.zone_context_service import ZoneContextService


class TestZoneContextServiceExtended:
    """Test ZoneContextService resolution for single, multi-aquarium, and live contexts."""

    def test_init_and_project_manager_getter_setter(self):
        svc = ZoneContextService(None)
        assert svc.project_manager is None

        mock_pm = MagicMock()
        svc.project_manager = mock_pm
        assert svc.project_manager is mock_pm

    def test_get_zone_data_none_project_manager_returns_empty_zonedata(self):
        svc = ZoneContextService(None)
        result = svc.get_zone_data_for_active_context()
        assert isinstance(result, ZoneData)
        assert result.polygon == []
        assert result.roi_polygons == []

    def test_get_zone_data_multi_aquarium_context(self):
        mock_pm = MagicMock()
        mock_pm.get_active_zone_video.return_value = "/path/multi_video.mp4"
        mock_pm.get_project_type.return_value = "video"
        mock_pm.is_multi_aquarium_video.return_value = True

        multi_data = MultiAquariumZoneData(
            aquariums=[AquariumData(id=0), AquariumData(id=1)],
            video_width=1920,
            video_height=1080,
        )
        mock_pm.get_multi_aquarium_zone_data.return_value = multi_data

        svc = ZoneContextService(mock_pm)
        result = svc.get_zone_data_for_active_context()
        assert result is multi_data

    def test_get_zone_data_single_video_with_polygon(self):
        mock_pm = MagicMock()
        mock_pm.get_active_zone_video.return_value = None
        mock_pm.get_project_type.return_value = "video"
        mock_pm.is_multi_aquarium_video.return_value = False

        expected_zone = ZoneData(polygon=[(0, 0), (100, 100)])
        mock_pm.get_zone_data.return_value = expected_zone

        svc = ZoneContextService(mock_pm)
        result = svc.get_zone_data_for_active_context(pending_single_video_path="/path/pending.mp4")
        assert result is expected_zone

    def test_get_zone_data_live_project_fallback_to_global(self):
        mock_pm = MagicMock()
        mock_pm.get_active_zone_video.return_value = "/path/live_feed.mp4"
        mock_pm.get_project_type.return_value = "live"
        mock_pm.is_multi_aquarium_video.return_value = False

        global_zone = ZoneData(polygon=[(10, 10), (50, 50)])
        mock_pm.get_zone_data.side_effect = [
            ZoneData(),  # per-video call returns empty
            global_zone,  # final fallback call
        ]

        svc = ZoneContextService(mock_pm)
        result = svc.get_zone_data_for_active_context()
        assert result is global_zone
