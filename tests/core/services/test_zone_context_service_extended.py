"""
Extended unit tests for ZoneContextService.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.detection import MultiAquariumZoneData, ZoneData
from zebtrack.core.services.zone_context_service import ZoneContextService


class TestZoneContextServiceExtended:
    """Test ZoneContextService resolution matrix."""

    def test_project_manager_none_returns_empty_zone_data(self):
        svc = ZoneContextService(project_manager=None)
        assert svc.project_manager is None
        data = svc.get_zone_data_for_active_context()
        assert isinstance(data, ZoneData)
        assert data.polygon == []

    def test_project_manager_getter_setter(self):
        svc = ZoneContextService()
        mock_pm = MagicMock()
        svc.project_manager = mock_pm
        assert svc.project_manager is mock_pm

    def test_multi_aquarium_active_video_resolution(self):
        mock_pm = MagicMock()
        mock_pm.get_active_zone_video.return_value = "/path/to/active.mp4"
        mock_pm.get_project_type.return_value = "video"
        mock_pm.is_multi_aquarium_video.return_value = True

        expected_multi = MultiAquariumZoneData(aquariums=[])
        mock_pm.get_multi_aquarium_zone_data.return_value = expected_multi

        svc = ZoneContextService(project_manager=mock_pm)
        res = svc.get_zone_data_for_active_context()

        assert res is expected_multi
        mock_pm.get_multi_aquarium_zone_data.assert_called_once_with("/path/to/active.mp4")

    def test_single_aquarium_active_video_resolution(self):
        mock_pm = MagicMock()
        mock_pm.get_active_zone_video.return_value = "/path/to/active.mp4"
        mock_pm.get_project_type.return_value = "video"
        mock_pm.is_multi_aquarium_video.return_value = False

        expected_zone = ZoneData(polygon=[[0, 0], [10, 10]])
        mock_pm.get_zone_data.return_value = expected_zone

        svc = ZoneContextService(project_manager=mock_pm)
        res = svc.get_zone_data_for_active_context()

        assert res is expected_zone
        mock_pm.get_zone_data.assert_called_once_with(
            video_path="/path/to/active.mp4",
            fallback_to_global=False,
        )

    def test_pending_single_video_path_used_when_no_active_video(self):
        mock_pm = MagicMock()
        mock_pm.get_active_zone_video.return_value = None
        mock_pm.get_project_type.return_value = "video"
        mock_pm.is_multi_aquarium_video.return_value = False

        expected_zone = ZoneData(polygon=[[5, 5], [15, 15]])
        mock_pm.get_zone_data.return_value = expected_zone

        svc = ZoneContextService(project_manager=mock_pm)
        res = svc.get_zone_data_for_active_context(pending_single_video_path="/path/to/pending.mp4")

        assert res is expected_zone
        mock_pm.get_zone_data.assert_called_once_with(
            video_path="/path/to/pending.mp4",
            fallback_to_global=False,
        )

    def test_live_project_uses_global_fallback(self):
        mock_pm = MagicMock()
        mock_pm.get_active_zone_video.return_value = "/path/to/live.mp4"
        mock_pm.get_project_type.return_value = "live"
        mock_pm.is_multi_aquarium_video.return_value = False

        expected_zone = ZoneData(polygon=[[1, 1]])
        mock_pm.get_zone_data.return_value = expected_zone

        svc = ZoneContextService(project_manager=mock_pm)
        res = svc.get_zone_data_for_active_context()

        assert res is expected_zone
        mock_pm.get_zone_data.assert_called_once_with(
            video_path="/path/to/live.mp4",
            fallback_to_global=True,
        )

    def test_exception_in_video_lookup_falls_back_to_global(self):
        mock_pm = MagicMock()
        mock_pm.get_active_zone_video.return_value = "/path/to/err.mp4"
        mock_pm.get_project_type.return_value = "video"
        mock_pm.is_multi_aquarium_video.return_value = False
        mock_pm.get_zone_data.side_effect = [
            KeyError("Video not found"),  # per-video call raises KeyError
            ZoneData(polygon=[[99, 99]]),  # fallback global call succeeds
        ]

        svc = ZoneContextService(project_manager=mock_pm)
        res = svc.get_zone_data_for_active_context()

        assert isinstance(res, ZoneData)
        assert res.polygon == [[99, 99]]
        mock_pm.get_zone_data.assert_called_with()
