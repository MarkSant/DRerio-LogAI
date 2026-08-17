"""Extended unit tests for core/project/project_manager.py (Part 9)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.project.project_manager import ProjectManager


class TestProjectManagerExtended9:
    """Test ProjectManager polygon updating and metadata manager access."""

    def test_update_main_polygon_delegates_to_zone_manager(self):
        pm = ProjectManager()
        pm.zone_manager = MagicMock()
        pm.project_data = {}

        points = [(0, 0), (10, 0), (10, 10), (0, 10)]
        pm.update_main_polygon(points)

        pm.zone_manager.update_main_polygon.assert_called_once_with(
            pm.project_data, points, persist_callback=pm.save_project
        )

    def test_metadata_manager_initialized(self):
        pm = ProjectManager()
        assert pm.metadata_manager is not None
        assert pm.lifecycle_manager is not None

    def test_get_aquarium_count_none_safe(self):
        pm = ProjectManager()
        assert pm.get_aquarium_count(None) == 1
