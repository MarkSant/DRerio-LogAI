"""Tests for analysis and display interval configuration behavior."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from zebtrack.core.project_manager import ProjectManager

CONFIG_FILENAME = "project_config.json"
SINGLE_VIDEO_DIALOG_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "zebtrack"
    / "ui"
    / "dialogs"
    / "single_video_config_dialog.py"
)
SINGLE_VIDEO_DIALOG_SOURCE = SINGLE_VIDEO_DIALOG_PATH.read_text(encoding="utf-8")

CREATE_PROJECT_DIALOG_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "zebtrack"
    / "ui"
    / "dialogs"
    / "create_project_dialog.py"
)
CREATE_PROJECT_DIALOG_SOURCE = CREATE_PROJECT_DIALOG_PATH.read_text(encoding="utf-8")


def test_single_video_config_dialog_has_interval_methods() -> None:
    """Ensure the single-video dialog declares interval variables."""

    assert "class SingleVideoConfigDialog" in SINGLE_VIDEO_DIALOG_SOURCE
    assert 'self.analysis_interval_var = StringVar(value="10")' in SINGLE_VIDEO_DIALOG_SOURCE
    assert 'self.display_interval_var = StringVar(value="10")' in SINGLE_VIDEO_DIALOG_SOURCE


def test_create_project_dialog_has_interval_methods() -> None:
    """Ensure the project dialog declares interval variables."""

    assert "class CreateProjectDialog" in CREATE_PROJECT_DIALOG_SOURCE
    assert 'self.analysis_interval_var = StringVar(value="10")' in CREATE_PROJECT_DIALOG_SOURCE
    assert 'self.display_interval_var = StringVar(value="10")' in CREATE_PROJECT_DIALOG_SOURCE


def _generate_dummy_video(path: Path, *, frames: int = 8) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),  # type: ignore[attr-defined]
        10,
        (320, 240),
    )
    for idx in range(frames):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.rectangle(
            frame,
            (10 + idx * 5, 100),
            (60 + idx * 5, 150),
            (255, 255, 255),
            thickness=-1,
        )
        writer.write(frame)
    writer.release()
    return path


@pytest.mark.parametrize(
    ("analysis_interval", "display_interval"),
    [(14, 8), (5, 7)],
)
def test_project_manager_persists_interval_settings(
    tmp_path,
    analysis_interval,
    display_interval,
) -> None:
    project_dir = tmp_path / "interval_project"
    video_path = tmp_path / "inputs" / "sample.mp4"
    _generate_dummy_video(video_path)

    video_entries = ProjectManager.scan_input_paths([str(video_path)])
    assert video_entries, "scan_input_paths should detect the generated video"

    pm = ProjectManager()

    pm.create_new_project(
        project_path=str(project_dir),
        project_type="pre-recorded",
        video_files=video_entries,
        num_aquariums=2,
        animals_per_aquarium=3,
        aquarium_width_cm=25.0,
        aquarium_height_cm=18.5,
        analysis_interval_frames=analysis_interval,
        display_interval_frames=display_interval,
    )

    assert pm.project_data["analysis_interval_frames"] == analysis_interval
    assert pm.project_data["display_interval_frames"] == display_interval

    config_path = project_dir / CONFIG_FILENAME
    saved_data = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved_data["analysis_interval_frames"] == analysis_interval
    assert saved_data["display_interval_frames"] == display_interval
    assert saved_data["batches"], "Video batch should be persisted"
    assert saved_data["batches"][0]["videos"][0]["path"] == str(video_path)


def test_controller_workflow_roundtrip_persists_intervals(
    tmp_path,
) -> None:
    """Test that ProjectWorkflowService correctly persists interval settings.

    Phase 3E: Refactored to test ProjectWorkflowService directly.
    The ProjectManager persistence is already tested in test_project_manager_persists_interval_settings.
    """
    from zebtrack.core.project_workflow_service import ProjectWorkflowService
    from zebtrack.core.state_manager import StateManager

    # Create REAL ProjectManager for this test
    real_pm = ProjectManager()
    mock_model_service = MagicMock()
    mock_model_service.get_default_weight.return_value = ("best_seg.pt", "/fake/path")
    state_manager = StateManager()
    mock_ui_coordinator = MagicMock()
    mock_settings = MagicMock()
    mock_settings.model_selection.animal_method = "seg"

    service = ProjectWorkflowService(
        project_manager=real_pm,
        model_service=mock_model_service,
        state_manager=state_manager,
        ui_coordinator=mock_ui_coordinator,
        settings_obj=mock_settings,
    )

    project_dir = tmp_path / "controller_project"
    video_path = tmp_path / "inputs" / "controller_sample.mp4"
    _generate_dummy_video(video_path)
    video_entries = ProjectManager.scan_input_paths([str(video_path)])
    assert video_entries

    # Mock detector setup
    mock_setup_detector = MagicMock(return_value=True)
    mock_weight_setter = MagicMock()
    mock_openvino_setter = MagicMock()

    # Create project via service
    result = service.create_project(
        setup_detector_callback=mock_setup_detector,
        active_weight_setter=mock_weight_setter,
        use_openvino_setter=mock_openvino_setter,
        project_path=str(project_dir),
        project_type="pre-recorded",
        video_files=video_entries,
        num_aquariums=1,
        animals_per_aquarium=1,
        aquarium_width_cm=12.0,
        aquarium_height_cm=8.0,
        analysis_interval_frames=6,
        display_interval_frames=9,
    )

    assert result["success"], f"Project creation failed: {result.get('error_message')}"

    config_path = project_dir / CONFIG_FILENAME
    assert config_path.exists()

    saved_data = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved_data["analysis_interval_frames"] == 6
    assert saved_data["display_interval_frames"] == 9

    reloaded = ProjectManager()
    reloaded.load_project(str(project_dir))

    assert reloaded.project_data["analysis_interval_frames"] == 6
    assert reloaded.project_data["display_interval_frames"] == 9
    assert real_pm.project_data["analysis_interval_frames"] == 6
    assert real_pm.project_data["display_interval_frames"] == 9
