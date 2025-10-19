import os
import shutil

import pytest

from zebtrack.core.detector import ZoneData
from zebtrack.io.recorder import Recorder


@pytest.fixture
def recorder_setup():
    """Set up a temporary directory and a Recorder instance for testing."""
    test_dir = "temp_recorder_test_dir"
    os.makedirs(test_dir, exist_ok=True)
    recorder = Recorder()
    output_folder = os.path.join(test_dir, "test_run_1")
    frame_width = 100
    frame_height = 100

    yield recorder, output_folder, frame_width, frame_height

    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)


def test_schema_change_after_start_raises_error_and_cleans_up(recorder_setup):
    """
    Tests that changing calibration after recording starts raises a ValueError
    and that the recorder cleans up its state.
    """
    recorder, output_folder, frame_width, frame_height = recorder_setup

    recorder.start_recording(output_folder, frame_width, frame_height, zones=ZoneData())
    assert recorder.is_recording

    recorder.write_detection_data(0.1, 1, [(10, 10, 20, 20, 0.9, 1)])
    recorder.pixel_per_cm_ratio = (1.0, 1.0)
    recorder._flush_row_threshold = 1

    with pytest.raises(ValueError, match="Parquet schema cannot change during recording"):
        recorder.write_detection_data(0.2, 2, [(10, 10, 20, 20, 0.9, 1)])

    assert not recorder.is_recording, "Recorder should stop on critical error."


def test_schema_change_from_calibrated_to_uncalibrated_cleans_up(recorder_setup):
    """
    Tests that removing calibration after recording starts raises a ValueError
    and that the recorder cleans up its state.
    """
    recorder, output_folder, frame_width, frame_height = recorder_setup

    recorder.start_recording(
        output_folder,
        frame_width,
        frame_height,
        zones=ZoneData(),
        pixel_per_cm_ratio=(1.0, 1.0),
    )
    assert recorder.is_recording

    recorder.write_detection_data(0.1, 1, [(10, 10, 20, 20, 0.9, 1)])
    recorder.pixel_per_cm_ratio = None
    recorder._flush_row_threshold = 1

    with pytest.raises(ValueError, match="Parquet schema cannot change during recording"):
        recorder.write_detection_data(0.2, 2, [(10, 10, 20, 20, 0.9, 1)])

    assert not recorder.is_recording, "Recorder should stop on critical error."


def test_can_start_new_recording_after_error(recorder_setup):
    """
    Tests that a new recording can be started successfully after a schema
    validation error has occurred, ensuring the recorder is reset.
    """
    recorder, output_folder, frame_width, frame_height = recorder_setup

    # First recording fails
    recorder.start_recording(output_folder, frame_width, frame_height, zones=ZoneData())
    recorder.write_detection_data(0.1, 1, [(10, 10, 20, 20, 0.9, 1)])  # Add data to trigger flush
    recorder.pixel_per_cm_ratio = (1.0, 1.0)
    with pytest.raises(ValueError):
        recorder._flush_detection_data(force=True)

    assert not recorder.is_recording

    # Second recording should succeed
    new_output_folder = os.path.join(os.path.dirname(output_folder), "test_run_2")
    success = recorder.start_recording(
        new_output_folder,
        frame_width,
        frame_height,
        zones=ZoneData(),
        pixel_per_cm_ratio=(1.0, 1.0),
    )
    assert success
    assert recorder.is_recording
    recorder.stop_recording()


def test_sequential_recordings_work_correctly(recorder_setup):
    """
    Tests that the schema is correctly reset and used across multiple
    independent recording sessions.
    """
    recorder, output_folder, frame_width, frame_height = recorder_setup

    # First recording (no calibration)
    recorder.start_recording(output_folder, frame_width, frame_height, zones=ZoneData())
    recorder.write_detection_data(0.1, 1, [(10, 10, 20, 20, 0.9, 1)])
    recorder.stop_recording()
    assert not recorder.is_recording

    # Second recording (with calibration)
    new_output_folder = os.path.join(os.path.dirname(output_folder), "test_run_2")
    success = recorder.start_recording(
        new_output_folder,
        frame_width,
        frame_height,
        zones=ZoneData(),
        pixel_per_cm_ratio=(2.0, 2.0),
    )
    assert success
    assert recorder.is_recording
    recorder.write_detection_data(0.2, 2, [(10, 10, 20, 20, 0.9, 1)])
    recorder.stop_recording()
    assert not recorder.is_recording


def test_schema_change_before_first_flush_raises_error(recorder_setup):
    """
    Tests that a schema change raises an error on the first flush, even if
    the flush happens late (e.g., at stop_recording).
    """
    recorder, output_folder, frame_width, frame_height = recorder_setup

    recorder.start_recording(output_folder, frame_width, frame_height, zones=ZoneData())
    recorder._flush_row_threshold = 1000  # Ensure no flush happens automatically

    recorder.write_detection_data(0.1, 1, [(10, 10, 20, 20, 0.9, 1)])

    # Change schema before any flush has occurred
    recorder.pixel_per_cm_ratio = (1.0, 1.0)

    with pytest.raises(ValueError, match="Parquet schema cannot change during recording"):
        # The error should be raised when stop_recording forces the first flush
        recorder.stop_recording()

    assert not recorder.is_recording
