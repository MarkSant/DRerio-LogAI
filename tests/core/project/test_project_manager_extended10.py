"""Extended unit tests for core/project/project_manager.py (Part 10)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.project.project_manager import CONFIG_FILE_NAME, ProjectManager


class TestProjectManagerExtended10:
    """Test ProjectManager calibration and zone data accessors."""

    def test_project_manager_get_zone_data_delegation(self):
        pm = ProjectManager()
        pm.zone_manager = MagicMock()
        pm.project_data = {"test": True}

        pm.get_zone_data(video_path="/path/vid.mp4", fallback_to_global=False)
        pm.zone_manager.get_zone_data.assert_called_once_with(
            pm.project_data, video_path="/path/vid.mp4", fallback_to_global=False
        )

    def test_project_manager_get_multi_aquarium_zone_data_delegation(self):
        pm = ProjectManager()
        pm.zone_manager = MagicMock()
        pm.project_data = {"test": True}

        pm.get_multi_aquarium_zone_data(video_path="/path/vid.mp4")
        pm.zone_manager.get_multi_aquarium_zone_data.assert_called_once_with(
            pm.project_data, "/path/vid.mp4"
        )

    def test_project_manager_config_file_name_constant(self):
        assert CONFIG_FILE_NAME == "project_config.json"

    def test_project_manager_default_project_data(self):
        pm = ProjectManager()
        assert isinstance(pm.project_data, dict)
        assert pm.asset_manager is not None
        assert pm.zone_manager is not None
