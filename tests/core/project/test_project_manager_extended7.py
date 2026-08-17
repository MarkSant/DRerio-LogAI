"""Extended unit tests for core/project/project_manager.py (Part 7)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.project.project_manager import ProjectManager


class TestProjectManagerExtended7:
    """Test ProjectManager multi-aquarium helper edge cases and polygon updates."""

    def test_is_multi_aquarium_video_none(self):
        pm = ProjectManager()
        assert pm.is_multi_aquarium_video(None) is False

    def test_is_multi_aquarium_video_true(self):
        pm = ProjectManager()
        pm.zone_manager = MagicMock()
        pm.zone_manager.is_multi_aquarium_video.return_value = True
        assert pm.is_multi_aquarium_video("/videos/video1.mp4") is True

    def test_get_aquarium_count_none(self):
        pm = ProjectManager()
        assert pm.get_aquarium_count(None) == 1

    def test_get_aquarium_count_two(self):
        pm = ProjectManager()
        pm.zone_manager = MagicMock()
        pm.zone_manager.get_aquarium_count.return_value = 2
        assert pm.get_aquarium_count("/videos/video1.mp4") == 2

    def test_clear_multi_aquarium_zone_data_none(self):
        pm = ProjectManager()
        pm.clear_multi_aquarium_zone_data(None)

    def test_update_main_polygon_delegates_to_zone_manager(self):
        pm = ProjectManager()
        pm.zone_manager = MagicMock()
        pm.project_data = {"zones": {}}

        points = [(10, 10), (20, 20), (30, 10)]
        pm.update_main_polygon(points)
        pm.zone_manager.update_main_polygon.assert_called_once_with(
            pm.project_data, points, persist_callback=pm.save_project
        )
