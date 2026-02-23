"""Tests for multi-aquarium ProjectManager functionality (Phase 8).

These tests cover:
- Resolving results directories for multiple aquariums
- Registering multi-aquarium outputs
- Getting multi-aquarium outputs
- Checking if video is in multi-aquarium mode
"""

import pytest

from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.core.state_manager import StateManager


@pytest.fixture
def project_setup(tmp_path):
    """Create a ProjectManager with a temporary project and return both.

    Returns:
        tuple: (ProjectManager, tmp_path, video1_path, video2_path)
    """
    state_manager = StateManager()
    pm = ProjectManager(state_manager=state_manager)

    # Create a minimal project
    project_path = tmp_path / "test_project"
    project_path.mkdir()

    # Create video files (needed for path matching)
    video1_path = tmp_path / "video1.mp4"
    video2_path = tmp_path / "video2.mp4"
    video1_path.touch()
    video2_path.touch()

    pm.project_path = project_path
    # Use proper batches structure that iter_project_videos expects
    pm.project_data = {
        "project_name": "Test Project",
        "project_type": "batch",
        "batches": [
            {
                "batch_name": "batch1",
                "videos": [
                    {
                        "path": str(video1_path),
                        "status": "pending",
                    },
                    {
                        "path": str(video2_path),
                        "status": "pending",
                    },
                ],
            }
        ],
    }

    return pm, tmp_path, str(video1_path), str(video2_path)


@pytest.fixture
def project_manager(project_setup):
    """Get just the ProjectManager from project_setup."""
    return project_setup[0]


class TestResolveMultiAquariumResultsDirectories:
    """Tests for resolve_multi_aquarium_results_directories method."""

    def test_creates_directory_structure(self, project_manager):
        """Test that correct directory structure is created for each aquarium."""
        configs = [
            {"aquarium_id": 0, "group": "Control", "subject_id": "S01", "day": 1},
            {"aquarium_id": 1, "group": "Treatment", "subject_id": "S02", "day": 1},
        ]

        result = project_manager.resolve_multi_aquarium_results_directories(
            experiment_id="video1",
            aquarium_configs=configs,
        )

        assert len(result) == 2
        assert 0 in result
        assert 1 in result

        # Verify paths exist
        assert result[0].exists()
        assert result[1].exists()

        # Verify path structure includes group/day/subject
        assert "Grupo_Control" in str(result[0])
        assert "Grupo_Treatment" in str(result[1])
        assert "Dia_01" in str(result[0])
        assert "Sujeito_S01" in str(result[0])
        assert "Sujeito_S02" in str(result[1])

    def test_different_groups_different_paths(self, project_manager):
        """Test that different groups generate different paths."""
        configs = [
            {"aquarium_id": 0, "group": "GroupA", "subject_id": "01", "day": 1},
            {"aquarium_id": 1, "group": "GroupB", "subject_id": "02", "day": 1},
        ]

        result = project_manager.resolve_multi_aquarium_results_directories(
            experiment_id="video1",
            aquarium_configs=configs,
        )

        # Paths should be different
        assert result[0] != result[1]
        assert "GroupA" in str(result[0])
        assert "GroupB" in str(result[1])

    def test_different_days_different_paths(self, project_manager):
        """Test that different days generate different paths."""
        configs = [
            {"aquarium_id": 0, "group": "Control", "subject_id": "01", "day": 1},
            {"aquarium_id": 1, "group": "Control", "subject_id": "01", "day": 2},
        ]

        result = project_manager.resolve_multi_aquarium_results_directories(
            experiment_id="video1",
            aquarium_configs=configs,
        )

        assert "Dia_01" in str(result[0])
        assert "Dia_02" in str(result[1])

    def test_single_aquarium_config(self, project_manager):
        """Test with single aquarium configuration."""
        configs = [
            {"aquarium_id": 0, "group": "Control", "subject_id": "S01", "day": 1},
        ]

        result = project_manager.resolve_multi_aquarium_results_directories(
            experiment_id="video1",
            aquarium_configs=configs,
        )

        assert len(result) == 1
        assert 0 in result
        assert result[0].exists()

    def test_missing_fields_use_defaults(self, project_manager):
        """Test that missing fields use sensible defaults."""
        configs = [
            {"aquarium_id": 0},  # Minimal config
        ]

        result = project_manager.resolve_multi_aquarium_results_directories(
            experiment_id="video1",
            aquarium_configs=configs,
        )

        assert len(result) == 1
        path_str = str(result[0])
        # Should have default values
        assert "Grupo_Sem_Grupo" in path_str
        assert "Dia_01" in path_str

    def test_returns_empty_when_no_project_path(self, project_manager):
        """Test returns empty dict when no project path is set."""
        project_manager.project_path = None

        configs = [
            {"aquarium_id": 0, "group": "Control", "subject_id": "S01", "day": 1},
        ]

        result = project_manager.resolve_multi_aquarium_results_directories(
            experiment_id="video1",
            aquarium_configs=configs,
        )

        assert result == {}

    def test_path_sanitization(self, project_manager):
        """Test that special characters in group names are sanitized."""
        configs = [
            {"aquarium_id": 0, "group": "Group/With\\Special:Chars", "subject_id": "S01", "day": 1},
        ]

        result = project_manager.resolve_multi_aquarium_results_directories(
            experiment_id="video1",
            aquarium_configs=configs,
        )

        assert len(result) == 1
        path_str = str(result[0])
        sanitized_part = path_str.split("Grupo_")[1] if "Grupo_" in path_str else path_str
        components = sanitized_part.replace("\\", "/").split("/")
        group_name_part = components[0]
        assert ":" not in group_name_part
        assert "/" not in group_name_part
        assert "\\" not in group_name_part


class TestRegisterMultiAquariumOutputs:
    """Tests for register_multi_aquarium_outputs method."""

    def test_register_outputs_success(self, project_setup):
        """Test successful registration of multi-aquarium outputs."""
        project_manager, tmp_path, video_path, _ = project_setup

        outputs = {
            0: {
                "results_dir": str(tmp_path / "aquarium_0"),
                "parquet_files": {"trajectory": str(tmp_path / "traj_0.parquet")},
                "group": "Control",
                "subject_id": "S01",
                "day": 1,
            },
            1: {
                "results_dir": str(tmp_path / "aquarium_1"),
                "parquet_files": {"trajectory": str(tmp_path / "traj_1.parquet")},
                "group": "Treatment",
                "subject_id": "S02",
                "day": 1,
            },
        }

        result = project_manager.register_multi_aquarium_outputs(
            video_path=video_path,
            outputs_by_aquarium=outputs,
        )

        assert result is True

        # Verify video entry was updated
        video_entry = project_manager.find_video_entry(path=video_path)
        assert video_entry["multi_aquarium_mode"] is True
        assert "multi_aquarium_outputs" in video_entry
        # Keys are strings for JSON compatibility
        assert "0" in video_entry["multi_aquarium_outputs"]
        assert "1" in video_entry["multi_aquarium_outputs"]

    def test_register_outputs_updates_status(self, project_setup):
        """Test that status is updated when all aquariums have trajectory."""
        project_manager, tmp_path, video_path, _ = project_setup

        outputs = {
            0: {
                "results_dir": str(tmp_path / "aq0"),
                "parquet_files": {"trajectory": str(tmp_path / "t0.parquet")},
            },
            1: {
                "results_dir": str(tmp_path / "aq1"),
                "parquet_files": {"trajectory": str(tmp_path / "t1.parquet")},
            },
        }

        project_manager.register_multi_aquarium_outputs(video_path, outputs)

        video_entry = project_manager.find_video_entry(path=video_path)
        assert video_entry["status"] == "processed"
        assert video_entry["has_trajectory"] is True

    def test_register_outputs_video_not_found(self, project_setup):
        """Test registration fails for non-existent video."""
        project_manager, tmp_path, _, _ = project_setup
        result = project_manager.register_multi_aquarium_outputs(
            video_path=str(tmp_path / "nonexistent.mp4"),
            outputs_by_aquarium={},
        )

        assert result is False

    def test_register_partial_outputs(self, project_setup):
        """Test registration with partial trajectory data."""
        project_manager, tmp_path, video_path, _ = project_setup

        outputs = {
            0: {
                "results_dir": str(tmp_path / "aq0"),
                "parquet_files": {"trajectory": str(tmp_path / "t0.parquet")},
            },
            1: {
                "results_dir": str(tmp_path / "aq1"),
                "parquet_files": {},  # No trajectory
            },
        }

        project_manager.register_multi_aquarium_outputs(video_path, outputs)

        video_entry = project_manager.find_video_entry(path=video_path)
        # Status should NOT be processed if not all have trajectory
        assert video_entry.get("has_trajectory") is not True

    def test_register_outputs_sets_has_summary(self, project_setup):
        """Test that has_summary is set when any aquarium has summary outputs."""
        project_manager, tmp_path, video_path, _ = project_setup

        outputs = {
            0: {
                "results_dir": str(tmp_path / "aq0"),
                "parquet_files": {
                    "trajectory": str(tmp_path / "t0.parquet"),
                    "summary_excel": str(tmp_path / "summary0.xlsx"),
                },
            },
            1: {
                "results_dir": str(tmp_path / "aq1"),
                "parquet_files": {"trajectory": str(tmp_path / "t1.parquet")},
            },
        }

        project_manager.register_multi_aquarium_outputs(video_path, outputs)

        video_entry = project_manager.find_video_entry(path=video_path)
        assert video_entry.get("has_summary") is True

    def test_register_outputs_preserves_frame_crop_box(self, project_setup):
        """Test that optional frame_crop_box is preserved for each aquarium."""
        project_manager, tmp_path, video_path, _ = project_setup

        outputs = {
            0: {
                "results_dir": str(tmp_path / "aq0"),
                "parquet_files": {"trajectory": str(tmp_path / "t0.parquet")},
                "frame_crop_box": (10, 20, 300, 400),
            },
            1: {
                "results_dir": str(tmp_path / "aq1"),
                "parquet_files": {"trajectory": str(tmp_path / "t1.parquet")},
                "frame_crop_box": None,
            },
        }

        project_manager.register_multi_aquarium_outputs(video_path, outputs)

        video_entry = project_manager.find_video_entry(path=video_path)
        # Keys are strings for JSON compatibility
        assert video_entry["multi_aquarium_outputs"]["0"].get("frame_crop_box") == (
            10,
            20,
            300,
            400,
        )
        assert video_entry["multi_aquarium_outputs"]["1"].get("frame_crop_box") is None


class TestGetMultiAquariumOutputs:
    """Tests for get_multi_aquarium_outputs method."""

    def test_get_outputs_returns_data(self, project_setup):
        """Test getting multi-aquarium outputs."""
        project_manager, _, video_path, _ = project_setup

        # First register outputs
        outputs = {
            0: {"results_dir": "/path/aq0", "group": "Control"},
            1: {"results_dir": "/path/aq1", "group": "Treatment"},
        }
        project_manager.register_multi_aquarium_outputs(video_path, outputs)

        # Then get them
        result = project_manager.get_multi_aquarium_outputs(video_path)

        assert result is not None
        # Keys are strings for JSON compatibility
        assert "0" in result or 0 in result  # Accept both for flexibility
        assert "1" in result or 1 in result
        # get_multi_aquarium_outputs returns integer keys after conversion
        key0 = 0 if 0 in result else "0"
        key1 = 1 if 1 in result else "1"
        assert result[key0]["group"] == "Control"
        assert result[key1]["group"] == "Treatment"

    def test_get_outputs_returns_none_for_non_multi_video(self, project_setup):
        """Test returns None for non-multi-aquarium video."""
        project_manager, _, video_path, _ = project_setup

        result = project_manager.get_multi_aquarium_outputs(video_path)

        assert result is None

    def test_get_outputs_returns_none_for_nonexistent_video(self, project_setup):
        """Test returns None for non-existent video."""
        project_manager, tmp_path, _, _ = project_setup
        result = project_manager.get_multi_aquarium_outputs(str(tmp_path / "nonexistent.mp4"))

        assert result is None


class TestIsMultiAquariumVideo:
    """Tests for is_multi_aquarium_video method."""

    def test_returns_true_for_multi_aquarium(self, project_setup):
        """Test returns True for multi-aquarium video."""
        project_manager, _, video_path, _ = project_setup

        # Register as multi-aquarium
        project_manager.register_multi_aquarium_outputs(
            video_path,
            {0: {"results_dir": "/path"}, 1: {"results_dir": "/path2"}},
        )

        result = project_manager.is_multi_aquarium_video(video_path)

        assert result is True

    def test_returns_false_for_regular_video(self, project_setup):
        """Test returns False for regular video."""
        project_manager, _, video_path, _ = project_setup

        result = project_manager.is_multi_aquarium_video(video_path)

        assert result is False

    def test_returns_false_for_nonexistent_video(self, project_setup):
        """Test returns False for non-existent video."""
        project_manager, tmp_path, _, _ = project_setup
        result = project_manager.is_multi_aquarium_video(str(tmp_path / "nonexistent.mp4"))

        assert result is False


class TestIntegrationMultiAquariumWorkflow:
    """Integration tests for complete multi-aquarium workflow."""

    def test_full_workflow(self, project_setup):
        """Test complete multi-aquarium workflow."""
        project_manager, _, video_path, _ = project_setup

        # Step 1: Resolve directories
        configs = [
            {"aquarium_id": 0, "group": "Control", "subject_id": "S01", "day": 1},
            {"aquarium_id": 1, "group": "Treatment", "subject_id": "S02", "day": 1},
        ]

        dirs = project_manager.resolve_multi_aquarium_results_directories(
            experiment_id="video1",
            aquarium_configs=configs,
        )

        assert len(dirs) == 2

        # Step 2: Register outputs
        outputs = {
            0: {
                "results_dir": str(dirs[0]),
                "parquet_files": {"trajectory": str(dirs[0] / "trajectory.parquet")},
                "group": "Control",
                "subject_id": "S01",
                "day": 1,
            },
            1: {
                "results_dir": str(dirs[1]),
                "parquet_files": {"trajectory": str(dirs[1] / "trajectory.parquet")},
                "group": "Treatment",
                "subject_id": "S02",
                "day": 1,
            },
        }

        success = project_manager.register_multi_aquarium_outputs(video_path, outputs)
        assert success

        # Step 3: Verify video is multi-aquarium
        assert project_manager.is_multi_aquarium_video(video_path)

        # Step 4: Get outputs
        retrieved = project_manager.get_multi_aquarium_outputs(video_path)
        assert retrieved is not None
        assert len(retrieved) == 2
        # Keys may be strings or integers depending on storage format
        key0 = 0 if 0 in retrieved else "0"
        key1 = 1 if 1 in retrieved else "1"
        assert retrieved[key0]["group"] == "Control"
        assert retrieved[key1]["group"] == "Treatment"

        # Step 5: Verify video status
        video_entry = project_manager.find_video_entry(path=video_path)
        assert video_entry["status"] == "processed"
        assert video_entry["has_trajectory"] is True
