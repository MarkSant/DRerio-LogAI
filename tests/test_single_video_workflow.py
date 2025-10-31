import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pandas as pd
import pytest

from zebtrack.core.detector import Detector
from zebtrack.core.main_view_model import AppController
from zebtrack.plugins.base import DetectorPlugin

# --- Test Helpers (adapted from test_integration.py) ---


def generate_mock_video(filepath: str, duration_s: int = 2, fps: int = 10):
    """Generates a simple dummy video file with a moving square."""
    width, height = 640, 480
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(filepath, fourcc, fps, (width, height))

    for i in range(duration_s * fps):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        x = int((i / (duration_s * fps)) * (width - 50))
        cv2.rectangle(frame, (x, 100), (x + 50, 150), (255, 255, 255), -1)
        writer.write(frame)
    writer.release()


class MockPlugin(DetectorPlugin):
    """A mock plugin that 'detects' a white square in the mock video."""

    def __init__(self, model_path: str, expected_hash: str | None = None):
        pass  # No model to load

    def detect(self, frame: np.ndarray) -> list:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        contours, _ = cv2.findContours(gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return []
        x, y, w, h = cv2.boundingRect(contours[0])
        # Return format: [x1, y1, x2, y2, confidence, track_id]
        return [[x, y, x + w, y + h, 0.99, 1]]

    @staticmethod
    def get_name() -> str:
        return "MockPlugin"

    @property
    def model_input_shape(self):
        return (640, 480)


@pytest.fixture
def single_video_test_setup(tmp_path: Path):
    """
    Sets up a complete environment for testing the single video workflow.
    This includes a mock controller, a mock video, and mock configuration.
    """
    from tests.helpers import create_test_controller
    
    # 1. Create a temporary video file
    video_path = tmp_path / "test_video.mp4"
    generate_mock_video(str(video_path))

    # 2. Create controller with factory
    mock_root = MagicMock()
    controller = create_test_controller(root=mock_root)
    controller.ui_event_bus = MagicMock()

    # 3. Setup a mock detector on the controller
    mock_plugin_instance = MockPlugin(model_path="dummy")
    controller.detector = Detector(
        plugin=mock_plugin_instance,
        base_width=640,
        base_height=480,
    )
    # Mock project manager for this test
    controller.project_manager = MagicMock()
    controller.project_manager.project_path = None  # Crucial for single video mode
    controller.project_manager.get_zone_data.return_value = MagicMock(
        polygon=None, squares=[], colors=[]
    )
    # Mock calibration data
    controller.project_manager.get_calibration_data.return_value = {}

    # 4. Define the configuration that the dialog would produce
    test_config = {
        "aquarium_width_cm": 10.0,
        "aquarium_height_cm": 10.0,
        "sharp_turn_threshold_deg_s": 150.0,
        "freezing_velocity_threshold": 0.8,
        "freezing_min_duration_s": 1.2,
    }

    # 5. Define the video info structure
    video_info = {"path": str(video_path), "has_data": False}

    yield controller, video_info, test_config, tmp_path

    # Teardown: tmp_path is handled by pytest


# --- The Integration Test ---


def test_single_video_workflow_creates_output_files(single_video_test_setup):
    """
    Tests that the single video analysis workflow runs without crashing and
    creates the expected output files (_summary.xlsx and _report.docx).
    """
    controller, video_info, test_config, output_dir = single_video_test_setup

    # The video name is used to create the results folder
    video_name = os.path.splitext(os.path.basename(video_info["path"]))[0]
    results_folder = output_dir / f"{video_name}_results"

    # We call the internal processing method directly to bypass UI interactions
    # that are part of the public `start_single_video_workflow` method.
    controller._process_videos(
        videos_to_process=[video_info],
        output_base_dir=str(results_folder),
        single_video_config=test_config,
    )

    # Assertions
    summary_file = results_folder / f"{video_name}_summary.xlsx"
    report_file = results_folder / f"{video_name}_report.docx"

    assert results_folder.exists(), "The main results folder should be created."
    assert summary_file.exists(), "The Excel summary file should be created."
    assert report_file.exists(), "The Word report file should be created."

    # Optional: A light check on the Excel file content
    summary_df = pd.read_excel(summary_file)
    # Check that the config from the dialog was used for metadata
    assert "aquarium_width_cm" in summary_df.columns
    assert summary_df["aquarium_width_cm"].iloc[0] == 10.0
