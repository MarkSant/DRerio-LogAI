"""Extended unit tests for core/project/project_manager.py (Part 8)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.project.project_manager import ProjectManager


class TestProjectManagerExtended8:
    """Test ProjectManager multi-aquarium output registration and initial project properties."""

    def test_register_multi_aquarium_outputs_empty(self):
        pm = ProjectManager()
        pm.project_data = {"outputs": {}}

        pm.register_multi_aquarium_outputs("/videos/video1.mp4", {})
        assert pm.project_data["outputs"] == {}

    def test_project_manager_initial_state(self):
        pm = ProjectManager()
        assert pm.project_path is None
        assert pm.project_data == {}
        assert pm.metadata is None
        assert pm._groups_cache is None
        assert pm._groups_cache_valid is False

    def test_list_roi_templates_delegates_to_asset_manager(self):
        pm = ProjectManager()
        pm.asset_manager = MagicMock()
        pm.asset_manager.list_roi_templates.return_value = [{"name": "Template1"}]

        res = pm.list_roi_templates(include_global=True)
        assert res == [{"name": "Template1"}]
        pm.asset_manager.list_roi_templates.assert_called_once_with(
            pm.project_data, include_global=True
        )

    def test_clear_multi_aquarium_zone_data_none_safe(self):
        pm = ProjectManager()
        # Passing None should return immediately without accessing zone_manager
        pm.clear_multi_aquarium_zone_data(None)
