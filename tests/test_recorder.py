import os
import shutil

import numpy as np
import pandas as pd
import pytest

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


def test_start_recording_creates_files(recorder_setup):
    """Test that start_recording creates metadata Parquet files and video file."""
    from zebtrack.core.detector import ZoneData

    recorder, output_folder, frame_width, frame_height = recorder_setup
    mock_zones = ZoneData()  # Pass empty zones for this test
    success = recorder.start_recording(output_folder, frame_width, frame_height, zones=mock_zones)
    assert success

    base_name = os.path.basename(output_folder)

    # Check if metadata files were created
    video_file = os.path.join(output_folder, f"{base_name}.mp4")
    processing_area_parquet = os.path.join(output_folder, f"1_ProcessingArea_{base_name}.parquet")
    areas_of_interest_parquet = os.path.join(
        output_folder, f"2_AreasOfInterest_{base_name}.parquet"
    )
    # The detection data file is only created on stop_recording
    coord_movimento_file = os.path.join(output_folder, f"3_CoordMovimento_{base_name}.parquet")

    assert os.path.exists(video_file)
    assert os.path.exists(processing_area_parquet)
    # The areas of interest file should NOT be created if no ROIs are provided
    assert not os.path.exists(areas_of_interest_parquet)
    assert not os.path.exists(coord_movimento_file)

    recorder.stop_recording()

    # Now test that it IS created when ROIs are present
    mock_zones_with_roi = ZoneData(roi_polygons=[[[0, 0], [1, 1], [0, 1]]])
    recorder.start_recording(output_folder, frame_width, frame_height, zones=mock_zones_with_roi)
    assert os.path.exists(areas_of_interest_parquet)
    recorder.stop_recording()


def test_metadata_parquet_content(recorder_setup):
    """Test that the metadata Parquet files have the correct content."""
    from zebtrack.core.detector import ZoneData

    recorder, output_folder, frame_width, frame_height = recorder_setup
    mock_zones = ZoneData(
        polygon=[[0, 0], [1, 1], [0, 1]],
        roi_polygons=[[[10, 10], [20, 10], [20, 20], [10, 20]]],
        roi_names=["TestROI"],
    )
    recorder.start_recording(output_folder, frame_width, frame_height, zones=mock_zones)
    base_name = os.path.basename(output_folder)

    # Test Processing Area Parquet
    processing_area_parquet = os.path.join(output_folder, f"1_ProcessingArea_{base_name}.parquet")
    assert os.path.exists(processing_area_parquet)
    df_proc = pd.read_parquet(processing_area_parquet)
    assert list(df_proc.columns) == ["x", "y"]
    assert len(df_proc) == len(mock_zones.polygon)

    # Test Areas of Interest Parquet
    areas_of_interest_parquet = os.path.join(
        output_folder, f"2_AreasOfInterest_{base_name}.parquet"
    )
    assert os.path.exists(areas_of_interest_parquet)
    df_areas = pd.read_parquet(areas_of_interest_parquet)
    assert list(df_areas.columns) == ["roi_name", "point_index", "x", "y"]
    assert len(df_areas) == 4  # 4 points in our test polygon
    assert df_areas.iloc[0]["roi_name"] == "TestROI"
    assert df_areas.iloc[1]["point_index"] == 1
    assert df_areas.iloc[2]["x"] == 20

    recorder.stop_recording()


def test_write_detection_data_saves_parquet(recorder_setup):
    """
    Test that writing multiple frames of detection data is saved correctly
    to a Parquet file, including calculated center points.
    """
    recorder, output_folder, frame_width, frame_height = recorder_setup
    from zebtrack.core.detector import ZoneData

    mock_zones = ZoneData()
    # Provide a mock pixel-to-cm ratio to enable center point calculation
    mock_pixel_ratio = (10.0, 10.0)  # 10 pixels per cm
    recorder.start_recording(
        output_folder,
        frame_width,
        frame_height,
        zones=mock_zones,
        pixel_per_cm_ratio=mock_pixel_ratio,
    )

    # Write a few frames of data
    detections_data = [
        (1.23, 101, [(10, 20, 30, 40, 0.98, 1)]),
        (1.26, 102, [(11, 21, 31, 41, 0.99, 1)]),
    ]
    for ts, fn, dets in detections_data:
        recorder.write_detection_data(ts, fn, dets)

    # Stop recording to trigger Parquet file save
    recorder.stop_recording()

    # Check that the Parquet file was created
    base_name = os.path.basename(output_folder)
    coord_movimento_parquet = os.path.join(output_folder, f"3_CoordMovimento_{base_name}.parquet")
    assert os.path.exists(coord_movimento_parquet)

    # Check the content of the Parquet file
    df = pd.read_parquet(coord_movimento_parquet)

    # 1. Check the number of records
    assert len(df) == 2

    # 2. Check the column names explicitly
    expected_columns = [
        "timestamp",
        "frame",
        "track_id",
        "x1",
        "y1",
        "x2",
        "y2",
        "confidence",
        "x_center_px",
        "y_center_px",
        "x_cm",
        "y_cm",
    ]
    assert list(df.columns) == expected_columns

    # 3. Check the data in the first row
    row1 = df.iloc[0]
    assert row1["timestamp"] == 1.23
    assert row1["frame"] == 101
    assert row1["track_id"] == 1
    assert row1["x1"] == 10
    assert row1["y1"] == 20
    assert row1["confidence"] == pytest.approx(0.98)
    assert row1["x_center_px"] == 20.0  # (10+30)/2
    assert row1["y_center_px"] == 30.0  # (20+40)/2
    assert row1["x_cm"] == pytest.approx(2.0)  # 20.0 / 10.0
    assert row1["y_cm"] == pytest.approx(3.0)  # 30.0 / 10.0


def test_periodic_flush_triggers_before_stop(recorder_setup):
    """Recorder should flush buffered data to disk automatically."""
    from zebtrack.core.detector import ZoneData

    recorder, output_folder, frame_width, frame_height = recorder_setup

    recorder._flush_row_threshold = 1
    recorder._flush_interval_seconds = 0.0

    recorder.start_recording(output_folder, frame_width, frame_height, zones=ZoneData())

    recorder.write_detection_data(0.5, 10, [(5, 5, 15, 15, 0.9, 42)])

    # Data should have been flushed immediately, leaving the in-memory buffer empty
    assert recorder.detection_data == []

    recorder.stop_recording()

    base_name = os.path.basename(output_folder)
    parquet_path = os.path.join(output_folder, f"3_CoordMovimento_{base_name}.parquet")
    assert os.path.exists(parquet_path)

    df = pd.read_parquet(parquet_path)
    assert len(df) == 1
    assert df.iloc[0]["track_id"] == 42


def test_write_detection_data_coerces_track_id_types(recorder_setup):
    from zebtrack.core.detector import ZoneData

    recorder, output_folder, frame_width, frame_height = recorder_setup
    recorder.start_recording(output_folder, frame_width, frame_height, zones=ZoneData())

    recorder.write_detection_data(0.0, 1, [(0, 0, 10, 10, 0.7, "7")])
    recorder.stop_recording()

    base_name = os.path.basename(output_folder)
    parquet_path = os.path.join(output_folder, f"3_CoordMovimento_{base_name}.parquet")
    df = pd.read_parquet(parquet_path)
    assert df.iloc[0]["track_id"] == 7


def test_write_detection_data_handles_multiple_tracks(recorder_setup):
    from zebtrack.core.detector import ZoneData

    recorder, output_folder, frame_width, frame_height = recorder_setup
    recorder.start_recording(output_folder, frame_width, frame_height, zones=ZoneData())

    recorder.write_detection_data(
        0.1,
        5,
        [
            (1, 1, 11, 11, 0.95, 1),
            (2, 2, 12, 12, 0.85, "8"),
        ],
    )
    recorder.stop_recording()

    base_name = os.path.basename(output_folder)
    parquet_path = os.path.join(output_folder, f"3_CoordMovimento_{base_name}.parquet")
    df = pd.read_parquet(parquet_path)
    assert set(df["track_id"].tolist()) == {1, 8}


def test_video_writing(recorder_setup):
    """Test that writing video frames increases file size."""
    from zebtrack.core.detector import ZoneData

    recorder, output_folder, frame_width, frame_height = recorder_setup
    mock_zones = ZoneData()
    recorder.start_recording(output_folder, frame_width, frame_height, zones=mock_zones)
    base_name = os.path.basename(output_folder)
    video_file = os.path.join(output_folder, f"{base_name}.mp4")

    initial_size = os.path.getsize(video_file)

    # Create a dummy frame and write it
    dummy_frame = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)
    recorder.write_video_frame(dummy_frame)
    recorder.write_video_frame(dummy_frame)

    # Stop recording to flush the writer
    recorder.stop_recording()

    final_size = os.path.getsize(video_file)
    assert final_size > initial_size
