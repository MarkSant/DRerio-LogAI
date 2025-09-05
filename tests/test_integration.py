import os
import shutil
import uuid

import cv2
import numpy as np
import pandas as pd
import pytest

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer
from zebtrack.core.detector import ZoneData
from zebtrack.io.recorder import Recorder


# -- Mocks and Test Data Generators --

def generate_mock_video(filepath: str, duration_s: int = 5, fps: int = 10):
    """
    Generates a simple dummy video file with a moving square.
    This avoids needing a real video file for testing the pipeline.
    """
    width, height = 640, 480
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(filepath, fourcc, fps, (width, height))

    for i in range(duration_s * fps):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        # Draw a white square that moves across the screen
        x = int((i / (duration_s * fps)) * (width - 50))
        cv2.rectangle(frame, (x, 100), (x + 50, 150), (255, 255, 255), -1)
        writer.write(frame)

    writer.release()


class MockDetector:
    """
    A mock detector that simulates the output of a real tracking model.
    It returns a predictable, moving bounding box with a consistent track_id.
    """

    def __init__(self, model_path: str):
        # The model_path is ignored, it's just to match the plugin interface.
        pass

    def detect(self, frame: np.ndarray) -> list:
        """
        Finds the white square in the mock video and returns its bbox.
        This is a very simple, non-ML form of "detection".
        """
        # Convert frame to grayscale and find non-zero pixels
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        contours, _ = cv2.findContours(
            gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            return []

        # Assume the largest contour is our square
        x, y, w, h = cv2.boundingRect(contours[0])
        x1, y1, x2, y2 = x, y, x + w, y + h
        confidence = 0.99
        track_id = 1  # Always track "animal 1"
        return [(x1, y1, x2, y2, confidence, track_id)]


@pytest.fixture
def integration_test_setup():
    """
    Sets up a temporary directory, a mock video, and other resources
    for the integration test.
    """
    test_dir = f"temp_integration_test_{uuid.uuid4()}"
    os.makedirs(test_dir, exist_ok=True)

    video_path = os.path.join(test_dir, "mock_video.mp4")
    generate_mock_video(video_path)

    output_folder = os.path.join(test_dir, "results")

    yield video_path, output_folder

    # Teardown
    shutil.rmtree(test_dir)


# -- Integration Test --

def test_full_pipeline_integration(integration_test_setup):
    """
    Tests the full data processing pipeline from video to analysis.
    1. "Tracks" a mock video using a MockDetector.
    2. Saves the results using the Recorder.
    3. Loads the saved data using the ConcreteBehavioralAnalyzer.
    4. Asserts that the final analysis produces a non-zero distance.
    """
    video_path, output_folder = integration_test_setup

    # -- 1. Tracking Phase --
    detector = MockDetector(model_path="dummy_path")
    cap = cv2.VideoCapture(video_path)
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # -- 2. Recording Phase --
    recorder = Recorder()
    # Mock calibration ratio for the recorder
    mock_pixel_ratio = (10.0, 10.0)
    mock_zones = ZoneData(polygon=[[0, 0], [frame_width, frame_height]])
    recorder.start_recording(
        output_folder,
        frame_width,
        frame_height,
        zones=mock_zones,
        pixel_per_cm_ratio=mock_pixel_ratio,
    )

    frame_num = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        detections = detector.detect(frame)
        timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        recorder.write_detection_data(timestamp, frame_num, detections)
        frame_num += 1

    recorder.stop_recording()
    cap.release()

    # -- Verification and Analysis Phase --
    # Check that the results file was created
    results_file = os.path.join(
        output_folder, f"3_CoordMovimento_{os.path.basename(output_folder)}.parquet"
    )
    assert os.path.exists(results_file)

    # -- 3. Analysis Phase --
    trajectory_df = pd.read_parquet(results_file)
    # The analyzer's __init__ expects bbox columns, which are not the focus
    # of this test but are required for instantiation. We can add dummy ones.
    trajectory_df["x1"] = trajectory_df["x_center_px"] - 1
    trajectory_df["y1"] = trajectory_df["y_center_px"] - 1
    trajectory_df["x2"] = trajectory_df["x_center_px"] + 1
    trajectory_df["y2"] = trajectory_df["y_center_px"] + 1


    analyzer = ConcreteBehavioralAnalyzer(
        trajectory_df=trajectory_df,
        pixelcm_x=mock_pixel_ratio[0],
        pixelcm_y=mock_pixel_ratio[1],
        video_height_px=frame_height,
        arena_polygon_px=[(0, 0), (frame_width, 0), (frame_width, frame_height), (0, frame_height)],
    )

    # -- 4. Final Assertion --
    total_distance = analyzer.calculate_total_distance()
    assert total_distance > 0
    # The mock video moves the box from left to right, so distance should be significant
    assert total_distance > 50.0  # (640px wide / 10px/cm = 64cm)
