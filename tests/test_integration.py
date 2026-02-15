from typing import Any, cast
from unittest.mock import MagicMock

import cv2
import numpy as np
import pandas as pd
import pytest

# Import the actual classes we want to integrate
from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.analysis.reporter import Reporter
from zebtrack.core.detector import Detector, ZoneData
from zebtrack.io.recorder import Recorder
from zebtrack.plugins.base import DetectorPlugin

# -- Mocks and Test Data Generators --


def generate_mock_video(filepath: str, duration_s: int = 5, fps: int = 10):
    """
    Generates a simple dummy video file with a moving square.
    This avoids needing a real video file for testing the pipeline.
    """
    width, height = 640, 480
    fourcc = cast(Any, cv2).VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(filepath, fourcc, fps, (width, height))

    if not writer.isOpened():
        raise RuntimeError(
            f"Failed to create video writer for {filepath}. "
            "This may be due to missing video codecs (e.g., ffmpeg, libavcodec)."
        )

    for i in range(duration_s * fps):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        # Draw a white square that moves across the screen
        x = int((i / (duration_s * fps)) * (width - 50))
        cv2.rectangle(frame, (x, 100), (x + 50, 150), (255, 255, 255), -1)
        writer.write(frame)

    writer.release()

    # Verify the video was created and is readable
    test_cap = cv2.VideoCapture(str(filepath))
    if not test_cap.isOpened():
        raise RuntimeError(
            f"Video file {filepath} was created but cannot be opened. "
            "This may indicate codec issues."
        )
    test_cap.release()


class MockPluginForIntegration(DetectorPlugin):
    """
    A mock plugin that simulates the output of a real tracking model by
    finding a white square in the mock video.
    """

    def __init__(self, model_path: str):
        pass  # Ignored

    def detect(
        self, frame: np.ndarray, conf_threshold: float | None = None
    ) -> list[tuple[int, int, int, int, float, int | None, int]]:
        # Accept conf_threshold but ignore it for this simple mock
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        contours, _ = cv2.findContours(gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return []
        x, y, w, h = cv2.boundingRect(contours[0])
        return [(x, y, x + w, y + h, 0.99, 1, 1)]  # x1, y1, x2, y2, conf, track_id, class_id

    @staticmethod
    def get_name() -> str:
        return "MockIntegrationPlugin"

    @property
    def model_input_shape(self) -> tuple[int, int]:
        return (640, 480)


@pytest.fixture
def integration_test_setup(tmp_path):
    """
    Sets up a temporary directory, a mock video, and other resources
    for the integration test.
    """
    video_path = tmp_path / "mock_video.mp4"

    try:
        generate_mock_video(video_path, duration_s=20)
    except RuntimeError as e:
        pytest.skip(f"Cannot generate mock video: {e}")

    # Directory to save the intermediate tracking results
    tracking_output_dir = tmp_path / "tracking_results"
    tracking_output_dir.mkdir()

    yield video_path, tracking_output_dir

    # Teardown is handled by tmp_path fixture


# -- New, More Complete Integration Test --


def test_full_pipeline_from_video_to_report(integration_test_setup):
    """
    Tests the full data processing pipeline from video to a final report.
    1. Tracks a mock video using the real Detector with a mock Plugin.
    2. Saves the results using the Recorder.
    3. Loads the tracked data and generates a summary report using Reporter.
    4. Asserts that the final report file is created.
    """
    video_path, tracking_output_dir = integration_test_setup

    # -- Phase 1: Tracking and Recording --
    mock_plugin = MockPluginForIntegration(model_path="dummy")
    detector = Detector(plugin=mock_plugin, base_width=640, base_height=480)
    recorder = Recorder()

    cap = cv2.VideoCapture(str(video_path))
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))

    # Define a simple, full-frame arena for detection
    arena_polygon = [
        [0, 0],
        [frame_width, 0],
        [frame_width, frame_height],
        [0, frame_height],
    ]
    zones = ZoneData(polygon=arena_polygon)
    detector.set_zones(zones, frame_width, frame_height)

    experiment_id = video_path.stem
    recorder.start_recording(
        output_folder=str(tracking_output_dir),
        frame_width=frame_width,
        frame_height=frame_height,
        zones=zones,
        pixel_per_cm_ratio=(10.0, 10.0),  # Mock calibration
        is_video_file=True,  # Don't create a new video, we're analyzing one
        base_name=experiment_id,
    )

    frame_num = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        # Use the real detector's detect method
        detections, _ = detector.detect(frame, project_type="pre-recorded")
        timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        recorder.write_detection_data(timestamp, frame_num, detections)
        frame_num += 1

    recorder.stop_recording()
    cap.release()

    # -- Phase 2: Analysis and Reporting --
    # Check that the intermediate results file was created
    experiment_id = video_path.stem
    results_file = tracking_output_dir / f"3_CoordMovimento_{experiment_id}.parquet"
    assert results_file.exists()

    # Create mock settings for AnalysisService
    mock_settings = MagicMock()
    mock_settings.trajectory_smoothing = MagicMock()
    mock_settings.trajectory_smoothing.window_length = 5
    mock_settings.trajectory_smoothing.polyorder = 2
    mock_settings.angular_velocity = MagicMock()
    mock_settings.angular_velocity.min_displacement_threshold_cm = 0.5
    mock_settings.angular_velocity.angle_calculation_window = 3
    mock_settings.angular_velocity.angular_velocity_smoothing_window = 5
    mock_settings.roi_inclusion_rule = "centroid_in"
    mock_settings.roi_buffer_radius_value = 0.0
    mock_settings.roi_min_bbox_overlap_ratio = 0.5

    # MIGRADO PARA v3.0: Usar AnalysisService + Reporter.from_analysis()
    service = AnalysisService(settings_obj=mock_settings)

    # Load the tracked data
    trajectory_df = pd.read_parquet(results_file)

    # The reporter needs the bbox columns, add dummy ones.
    trajectory_df["x1"] = trajectory_df["x_center_px"] - 1
    trajectory_df["y1"] = trajectory_df["y_center_px"] - 1
    trajectory_df["x2"] = trajectory_df["x_center_px"] + 1
    trajectory_df["y2"] = trajectory_df["y_center_px"] + 1

    analysis = service.run_full_analysis_as_dto(
        arena_polygon_px=arena_polygon,
        fps=fps,
        metadata={"experiment_id": "integration_test"},
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        rois=[],
        roi_colors={},
        trajectory_df=trajectory_df,
        video_height_px=frame_height,
        freezing_vel_threshold=1.0,
        freezing_min_duration=2.0,
        max_plausible_speed_cm_s=100.0,  # Higher threshold for integration test
    )
    reporter = Reporter.from_analysis(analysis)

    # Generate a final summary report
    report_output_path = tracking_output_dir / "final_summary.xlsx"
    reporter.export_summary_data(str(report_output_path), format="excel")

    # -- Phase 3: Final Assertion --
    assert report_output_path.exists()

    # Optional: A light check on the content of the created report
    report_df = pd.read_excel(report_output_path)
    assert "Experiment ID" in report_df.columns
    assert report_df["Experiment ID"].iloc[0] == "integration_test"
