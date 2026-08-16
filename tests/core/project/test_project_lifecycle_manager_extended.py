"""
Extended unit tests for ProjectLifecycleManager in core/project/project_lifecycle_manager.py.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zebtrack.core.exceptions import ProjectInvalidError
from zebtrack.core.project.project_lifecycle_manager import ProjectLifecycleManager


class TestProjectLifecycleManagerExtended:
    """Test ProjectLifecycleManager validation, load, and save operations."""

    def test_validate_project_parameters_valid(self):
        # Should not raise
        ProjectLifecycleManager.validate_project_parameters(
            num_aquariums=2,
            animals_per_aquarium=1,
            aquarium_width_cm=30.0,
            aquarium_height_cm=20.0,
            analysis_interval_frames=2,
            display_interval_frames=5,
            camera_index=0,
            project_type="Pre-recorded",
            video_files=["video.mp4"],
        )

    def test_validate_project_parameters_invalid_aquariums_raises(self):
        with pytest.raises(ValueError, match="num_aquariums must be >= 1"):
            ProjectLifecycleManager.validate_project_parameters(
                num_aquariums=0,
                animals_per_aquarium=1,
                aquarium_width_cm=30.0,
                aquarium_height_cm=20.0,
                analysis_interval_frames=1,
                display_interval_frames=1,
                camera_index=0,
                project_type="Live",
                video_files=None,
            )

        with pytest.raises(ValueError, match="num_aquariums must be <= 100"):
            ProjectLifecycleManager.validate_project_parameters(
                num_aquariums=101,
                animals_per_aquarium=1,
                aquarium_width_cm=30.0,
                aquarium_height_cm=20.0,
                analysis_interval_frames=1,
                display_interval_frames=1,
                camera_index=0,
                project_type="Live",
                video_files=None,
            )

    def test_validate_project_parameters_invalid_dimensions_raises(self):
        with pytest.raises(ValueError, match="aquarium_width_cm must be >= 0"):
            ProjectLifecycleManager.validate_project_parameters(
                num_aquariums=1,
                animals_per_aquarium=1,
                aquarium_width_cm=-5.0,
                aquarium_height_cm=20.0,
                analysis_interval_frames=1,
                display_interval_frames=1,
                camera_index=0,
                project_type="Live",
                video_files=None,
            )

        with pytest.raises(ValueError, match="aquarium_width_cm must be <= 500"):
            ProjectLifecycleManager.validate_project_parameters(
                num_aquariums=1,
                animals_per_aquarium=1,
                aquarium_width_cm=600.0,
                aquarium_height_cm=20.0,
                analysis_interval_frames=1,
                display_interval_frames=1,
                camera_index=0,
                project_type="Live",
                video_files=None,
            )

    def test_validate_project_parameters_invalid_intervals_and_types(self):
        with pytest.raises(ValueError, match="analysis_interval_frames must be >= 1"):
            ProjectLifecycleManager.validate_project_parameters(
                num_aquariums=1,
                animals_per_aquarium=1,
                aquarium_width_cm=30.0,
                aquarium_height_cm=20.0,
                analysis_interval_frames=0,
                display_interval_frames=1,
                camera_index=0,
                project_type="Live",
                video_files=None,
            )

        with pytest.raises(ValueError, match="project_type must be one of"):
            ProjectLifecycleManager.validate_project_parameters(
                num_aquariums=1,
                animals_per_aquarium=1,
                aquarium_width_cm=30.0,
                aquarium_height_cm=20.0,
                analysis_interval_frames=1,
                display_interval_frames=1,
                camera_index=0,
                project_type="CustomNonExistent",
                video_files=None,
            )

    def test_save_project_data_no_path_raises(self):
        with pytest.raises(ProjectInvalidError, match="the project path is not set"):
            ProjectLifecycleManager.save_project_data(
                project_path=None,
                project_data={},
                save_config_fn=MagicMock(),
            )

    def test_save_project_data_success(self, tmp_path: Path):
        mock_save = MagicMock()
        data = {"project_name": "TestProj"}
        ProjectLifecycleManager.save_project_data(
            project_path=tmp_path,
            project_data=data,
            save_config_fn=mock_save,
        )
        mock_save.assert_called_once_with(tmp_path, data)

    def test_load_project_data_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(ProjectInvalidError, match="not found in the selected directory"):
            ProjectLifecycleManager.load_project_data(
                project_path=tmp_path,
                load_config_fn=MagicMock(),
                apply_migrations_fn=MagicMock(),
            )

    def test_load_project_data_success(self, tmp_path: Path):
        # Create empty config file
        (tmp_path / "project_config.json").write_text("{}")

        mock_load = MagicMock(return_value={"version": "3.3", "project_name": "MyProj"})
        migrated_ret = ({"version": "3.3", "project_name": "MyProj"}, False, [])
        mock_migrate = MagicMock(return_value=migrated_ret)

        data, migrated, fields = ProjectLifecycleManager.load_project_data(
            project_path=tmp_path,
            load_config_fn=mock_load,
            apply_migrations_fn=mock_migrate,
        )

        assert data["project_name"] == "MyProj"
        assert migrated is False
        assert fields == []
