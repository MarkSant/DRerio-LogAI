"""
Tests for analysis_interval_frames and display_interval_frames configuration.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add src to path for test imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def test_single_video_config_dialog_has_interval_methods():
    """
    Test that SingleVideoConfigDialog creates interval-related variables.
    """
    # Read the source code to verify the dialog creates the interval variables
    import os
    gui_file = os.path.join(
        os.path.dirname(__file__), '..', 'src', 'zebtrack', 'ui', 'gui.py'
    )
    with open(gui_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the SingleVideoConfigDialog.body method
    assert 'class SingleVideoConfigDialog' in content
    assert 'self.analysis_interval_var = StringVar(value="10")' in content
    assert 'self.display_interval_var = StringVar(value="10")' in content


def test_create_project_dialog_has_interval_methods():
    """
    Test that CreateProjectDialog creates interval-related variables.
    """
    # Read the source code to verify the dialog creates the interval variables
    import os
    gui_file = os.path.join(
        os.path.dirname(__file__), '..', 'src', 'zebtrack', 'ui', 'gui.py'
    )
    with open(gui_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the CreateProjectDialog class and verify it has interval variables
    assert 'class CreateProjectDialog' in content
    # The dialog should initialize these variables in its __init__ or body
    # method
    parts = content.split('class CreateProjectDialog')[1].split('class ')
    """Integration-focused tests for interval frame configuration."""

    import json
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    import cv2
    import numpy as np
    import pytest

    from zebtrack.core.controller import AppController
    from zebtrack.core.project_manager import ProjectManager

    CONFIG_FILENAME = "project_config.json"


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
        "analysis_interval,display_interval",
        [(14, 8), (5, 7)],
    )
    def test_project_manager_persists_interval_settings(tmp_path, analysis_interval, display_interval):
        project_dir = tmp_path / "interval_project"
        video_path = tmp_path / "inputs" / "sample.mp4"
        _generate_dummy_video(video_path)

        video_entries = ProjectManager.scan_input_paths([str(video_path)])
        assert video_entries, "scan_input_paths should detect the generated video"

        pm = ProjectManager()

        with patch("zebtrack.core.project_manager.messagebox"):
            assert pm.create_new_project(
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


    @patch("zebtrack.core.controller.ApplicationGUI")
    def test_controller_workflow_roundtrip_persists_intervals(mock_gui, tmp_path):
        root = MagicMock()
        controller = AppController(root=root)
        controller.view = mock_gui.return_value

        project_dir = tmp_path / "controller_project"
        video_path = tmp_path / "inputs" / "controller_sample.mp4"
        _generate_dummy_video(video_path)
        video_entries = controller.project_manager.scan_input_paths([str(video_path)])
        assert video_entries

        with (
            patch.object(controller, "setup_detector", return_value=True),
            patch("zebtrack.core.project_manager.messagebox"),
        ):
            controller.create_project_workflow(
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

        config_path = project_dir / CONFIG_FILENAME
        assert config_path.exists()

        saved_data = json.loads(config_path.read_text(encoding="utf-8"))
        assert saved_data["analysis_interval_frames"] == 6
        assert saved_data["display_interval_frames"] == 9

        reloaded = ProjectManager()
        with patch("zebtrack.core.project_manager.messagebox"):
            assert reloaded.load_project(str(project_dir))

        assert reloaded.project_data["analysis_interval_frames"] == 6
        assert reloaded.project_data["display_interval_frames"] == 9
        assert controller.project_manager.project_data["analysis_interval_frames"] == 6
        assert controller.project_manager.project_data["display_interval_frames"] == 9
