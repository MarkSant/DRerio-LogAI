"""Unit tests for ``zebtrack.core.services.ZoneContextService``.

Covers the active-context resolution logic that decides which ``ZoneData`` (or
``MultiAquariumZoneData``) applies to the current project/video. This is part of
the multi-aquarium domain (CRITICAL per project docs), so the resolution order
and the fallbacks are pinned explicitly.

The ``ProjectManager`` is duck-typed and stood in with ``Mock``.
"""

from unittest.mock import Mock

from zebtrack.core.detection import AquariumData, MultiAquariumZoneData, ZoneData
from zebtrack.core.services.zone_context_service import ZoneContextService


def _pm(**overrides):
    """Build a ProjectManager mock with sensible non-multi defaults."""
    pm = Mock()
    pm.get_active_zone_video.return_value = "video.mp4"
    pm.get_project_type.return_value = "pre_recorded"
    pm.is_multi_aquarium_video.return_value = False
    pm.get_multi_aquarium_zone_data.return_value = None
    pm.get_zone_data.return_value = ZoneData()
    for key, value in overrides.items():
        getattr(pm, key).return_value = value
    return pm


class TestNoProjectManager:
    def test_none_pm_returns_empty_zone_data(self):
        service = ZoneContextService(project_manager=None)
        result = service.get_zone_data_for_active_context()
        assert isinstance(result, ZoneData)
        assert not result.polygon and not result.roi_polygons


class TestMultiAquariumResolution:
    def test_multi_aquarium_takes_precedence(self):
        multi = MultiAquariumZoneData(aquariums=[AquariumData(id=0), AquariumData(id=1)])
        pm = _pm()
        pm.is_multi_aquarium_video.return_value = True
        pm.get_multi_aquarium_zone_data.return_value = multi

        result = ZoneContextService(pm).get_zone_data_for_active_context()
        assert result is multi

    def test_empty_multi_data_falls_through_to_zone_data(self):
        # is_multi flag set but no multi data → resolution continues to per-video.
        per_video = ZoneData(polygon=[[0, 0], [10, 0], [10, 10], [0, 10]])
        pm = _pm()
        pm.is_multi_aquarium_video.return_value = True
        pm.get_multi_aquarium_zone_data.return_value = None
        pm.get_zone_data.return_value = per_video

        result = ZoneContextService(pm).get_zone_data_for_active_context()
        assert result is per_video


class TestPerVideoResolution:
    def test_returns_per_video_zone_with_polygon(self):
        per_video = ZoneData(polygon=[[0, 0], [10, 0], [10, 10], [0, 10]])
        pm = _pm(get_zone_data=per_video)
        result = ZoneContextService(pm).get_zone_data_for_active_context()
        assert result is per_video

    def test_pending_video_used_when_no_active_video(self):
        pm = _pm(get_active_zone_video=None)
        # Non-empty zone so resolution returns at the per-video step (its call is last).
        pm.get_zone_data.return_value = ZoneData(polygon=[[0, 0], [1, 0], [1, 1]])
        ZoneContextService(pm).get_zone_data_for_active_context(
            pending_single_video_path="pending.mp4"
        )
        # The pending path must drive the per-video lookup.
        _, kwargs = pm.get_zone_data.call_args
        assert kwargs.get("video_path") == "pending.mp4"

    def test_live_project_requests_global_fallback(self):
        pm = _pm(get_project_type="live")
        pm.get_zone_data.return_value = ZoneData(polygon=[[0, 0], [1, 0], [1, 1]])
        ZoneContextService(pm).get_zone_data_for_active_context()
        _, kwargs = pm.get_zone_data.call_args
        assert kwargs.get("fallback_to_global") is True


class TestFallbacks:
    def test_empty_zone_data_falls_back_to_global(self):
        sentinel_global = ZoneData(polygon=[[9, 9], [8, 8], [7, 7]])

        def zone_data_side_effect(*args, **kwargs):
            # Per-video lookup returns empty; the final bare call returns global.
            if "video_path" in kwargs:
                return ZoneData()
            return sentinel_global

        pm = _pm()
        pm.get_zone_data.side_effect = zone_data_side_effect

        result = ZoneContextService(pm).get_zone_data_for_active_context()
        assert result is sentinel_global

    def test_exception_during_lookup_falls_back_to_global(self):
        sentinel_global = ZoneData(polygon=[[1, 1], [2, 2], [3, 3]])

        def zone_data_side_effect(*args, **kwargs):
            if "video_path" in kwargs:
                raise KeyError("boom")
            return sentinel_global

        pm = _pm()
        pm.get_zone_data.side_effect = zone_data_side_effect

        result = ZoneContextService(pm).get_zone_data_for_active_context()
        assert result is sentinel_global


class TestProjectManagerProperty:
    def test_setter_updates_reference(self):
        service = ZoneContextService(project_manager=None)
        assert service.project_manager is None
        pm = _pm()
        service.project_manager = pm
        assert service.project_manager is pm
