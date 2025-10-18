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

    # Yield the necessary objects to the tests
    yield recorder, output_folder, frame_width, frame_height

    # Teardown: clean up the temporary directory
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)


def test_schema_change_after_start_raises_error(recorder_setup):
    """
    Tests that changing the calibration (and thus the schema) after recording
    has started raises a ValueError during flush.
    """
    recorder, output_folder, frame_width, frame_height = recorder_setup

    # 1. Start recording WITHOUT calibration
    recorder.start_recording(output_folder, frame_width, frame_height, zones=ZoneData())

    # 2. Add some data
    recorder.write_detection_data(0.1, 1, [(10, 10, 20, 20, 0.9, 1)])

    # 3. Now, add calibration mid-way through. This is the problematic scenario.
    recorder.pixel_per_cm_ratio = (1.0, 1.0)

    # 4. Trigger a flush (by writing more data with flush threshold set low)
    # The recorder is now in an error state. We expect the flush to fail.
    recorder._flush_row_threshold = 1
    with pytest.raises(ValueError, match="Parquet schema cannot change during recording"):
        recorder.write_detection_data(0.2, 2, [(10, 10, 20, 20, 0.9, 1)])

    # Do not call stop_recording, as the recorder is in a known error state.
    # The fixture's teardown will handle directory cleanup.


def test_schema_change_from_calibrated_to_uncalibrated_raises_error(recorder_setup):
    """
    Tests that removing calibration after recording has started with it
    raises a ValueError during flush.
    """
    recorder, output_folder, frame_width, frame_height = recorder_setup

    # 1. Start recording WITH calibration
    recorder.start_recording(
        output_folder,
        frame_width,
        frame_height,
        zones=ZoneData(),
        pixel_per_cm_ratio=(1.0, 1.0),
    )

    # 2. Add some data
    recorder.write_detection_data(0.1, 1, [(10, 10, 20, 20, 0.9, 1)])

    # 3. Now, REMOVE calibration mid-way through.
    recorder.pixel_per_cm_ratio = None

    # 4. Trigger a flush and expect an error
    recorder._flush_row_threshold = 1
    with pytest.raises(ValueError, match="Parquet schema cannot change during recording"):
        recorder.write_detection_data(0.2, 2, [(10, 10, 20, 20, 0.9, 1)])

    # Do not call stop_recording, as the recorder is in a known error state.
    # The fixture's teardown will handle directory cleanup.