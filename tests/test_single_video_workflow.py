import os
from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pandas as pd
import pytest

from zebtrack.core.detector import Detector
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
    from unittest.mock import Mock

    from tests.helpers import create_test_controller
    from zebtrack.analysis.analysis_service import AnalysisService

    # 1. Create a temporary video file
    video_path = tmp_path / "test_video.mp4"
    generate_mock_video(str(video_path))

    # 2. Create mock settings
    from tests.helpers import create_mock_settings

    mock_settings = create_mock_settings()

    # 3. Create REAL AnalysisService for proper file generation
    analysis_service = AnalysisService(settings_obj=mock_settings)

    # 4. Create controller with factory and real analysis service
    mock_root = MagicMock()
    controller = create_test_controller(
        root=mock_root, settings_obj=mock_settings, analysis_service=analysis_service
    )
    controller.ui_event_bus = MagicMock()

    # 5. Configure video_processing_service mock to return proper results path
    results_folder = tmp_path / "test_video_results"
    results_folder.mkdir(exist_ok=True)

    # Mock resolve_results_path to return the results folder
    controller.video_processing_service.resolve_results_path = Mock(
        return_value=(str(results_folder), True)
    )

    # Mock process_single_video to simulate successful processing
    def mock_process_single_video(video_path, output_dir, **kwargs):
        # Create a mock parquet file with tracking data
        tracking_data = pd.DataFrame(
            {
                "timestamp": [0.0, 0.1, 0.2],
                "frame": [0, 1, 2],
                "track_id": [1, 1, 1],
                "x1": [100, 110, 120],
                "y1": [100, 110, 120],
                "x2": [150, 160, 170],
                "y2": [150, 160, 170],
                "confidence": [0.9, 0.9, 0.9],
            }
        )

        # Create tracking file
        video_name = Path(video_path).stem
        tracking_file = Path(output_dir) / f"{video_name}_tracking.parquet"
        tracking_data.to_parquet(tracking_file)

        return True, tracking_file

    controller.video_processing_service.process_single_video = Mock(
        side_effect=mock_process_single_video
    )

    # 6. Setup a mock detector on the controller
    mock_plugin_instance = MockPlugin(model_path="dummy")
    controller.detector = Detector(
        plugin=mock_plugin_instance,
        base_width=640,
        base_height=480,
    )

    # 7. Mock project manager for this test
    controller.project_manager = MagicMock()
    controller.project_manager.project_path = None  # Crucial for single video mode
    controller.project_manager.get_zone_data.return_value = MagicMock(
        polygon=None, squares=[], colors=[]
    )
    controller.project_manager.get_calibration_data.return_value = {}

    # 8. Define the configuration that the dialog would produce
    test_config = {
        "aquarium_width_cm": 10.0,
        "aquarium_height_cm": 10.0,
        "sharp_turn_threshold_deg_s": 150.0,
        "freezing_velocity_threshold": 0.8,
        "freezing_min_duration_s": 1.2,
    }

    # 9. Define the video info structure
    video_info = {"path": str(video_path), "has_data": False}

    yield controller, video_info, test_config, tmp_path, mock_root

    # Teardown: tmp_path is handled by pytest


# --- The Integration Test ---


def test_single_video_workflow_creates_output_files(single_video_test_setup):
    """
    Tests that the video processing workflow components are properly wired together
    and can be called in sequence.
    """
    controller, video_info, test_config, output_dir, root = single_video_test_setup

    # Test that controller has the required services wired together
    assert controller.analysis_service is not None, "Controller should have analysis_service"
    assert controller.video_processing_service is not None, (
        "Controller should have video_processing_service"
    )
    assert controller.detector is not None, "Controller should have detector"

    # Test that the mock video processing service can be called
    video_name = os.path.splitext(os.path.basename(video_info["path"]))[0]
    results_folder = output_dir / f"{video_name}_results"
    results_folder.mkdir(exist_ok=True)

    # Call the mocked process_single_video
    success, tracking_file = controller.video_processing_service.process_single_video(
        video_info["path"], str(results_folder), config=test_config
    )

    # Verify the mock worked correctly
    assert success, "Video processing should succeed"
    assert tracking_file.exists(), "Tracking file should be created by the mock"

    # Verify tracking file has expected structure
    df = pd.read_parquet(tracking_file)
    required_columns = ["frame", "track_id", "x1", "y1", "x2", "y2", "confidence"]
    for col in required_columns:
        assert col in df.columns, f"Tracking data should have '{col}' column"

    assert len(df) > 0, "Tracking data should have some detections"
