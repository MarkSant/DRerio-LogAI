import os
import shutil
import time

import numpy as np
import pandas as pd
import pytest

from tests.utils.wait_helpers import wait_for_condition
from zebtrack.io.recorder import Recorder


@pytest.fixture
def recorder_setup(tmp_path):
    """Set up a temporary directory and a Recorder instance for testing."""
    import gc

    # Use pytest's tmp_path for unique directory per test (thread-safe)
    test_dir = tmp_path / "recorder_test"
    test_dir.mkdir(exist_ok=True)
    recorder = Recorder()
    output_folder = str(test_dir / "test_run_1")
    frame_width = 100
    frame_height = 100

    # Yield the necessary objects to the tests
    yield recorder, output_folder, frame_width, frame_height

    # Teardown: ensure recorder is stopped and clean up
    try:
        # Stop recording if it's still active
        if hasattr(recorder, "is_recording") and recorder.is_recording:
            recorder.stop_recording(force_stop=True)
    except Exception:
        pass  # Ignore errors during cleanup

    # Force garbage collection to release file handles
    del recorder
    gc.collect()

    # Give Windows time to release file handles (short wait)
    time.sleep(0.1)

    # Clean up the temporary directory
    if test_dir.exists():
        max_retries = 3
        for attempt in range(max_retries):
            try:
                shutil.rmtree(test_dir)
                break
            except PermissionError:
                if attempt < max_retries - 1:
                    time.sleep(0.3 * (attempt + 1))  # Exponential backoff
                else:
                    # If still fails, pytest will clean up tmp_path automatically
                    pass  # Silently ignore - pytest tmp_path cleanup will handle it


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

    # Wait for file to be created
    base_name = os.path.basename(output_folder)
    coord_movimento_parquet = os.path.join(output_folder, f"3_CoordMovimento_{base_name}.parquet")
    wait_for_condition(lambda: os.path.exists(coord_movimento_parquet), timeout=2.0)

    # Check that the Parquet file was created
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


def test_pixel_ratio_change_during_recording_is_rejected(recorder_setup):
    """Changing calibration mid-recording should raise to avoid schema drift."""
    from zebtrack.core.detector import ZoneData

    recorder, output_folder, frame_width, frame_height = recorder_setup
    recorder.start_recording(
        output_folder,
        frame_width,
        frame_height,
        zones=ZoneData(),
        is_video_file=True,
    )

    with pytest.raises(ValueError):
        recorder.pixel_per_cm_ratio = (1.0, 1.0)

    assert recorder.is_recording
    recorder.stop_recording(force_stop=True)


def test_schema_mismatch_flush_forces_stop(recorder_setup):
    """Schema changes mid-run should force-stop and bubble the error."""
    from zebtrack.core.detector import ZoneData

    recorder, output_folder, frame_width, frame_height = recorder_setup
    recorder._flush_row_threshold = 10  # keep buffered until explicit flush
    recorder.start_recording(
        output_folder,
        frame_width,
        frame_height,
        zones=ZoneData(),
        is_video_file=True,
    )

    recorder.write_detection_data(0.1, 1, [(1, 2, 3, 4, 0.9, 7)])
    recorder._pixel_per_cm_ratio = (1.0, 1.0)  # bypass setter to simulate drift

    with pytest.raises(ValueError):
        recorder._flush_detection_data(force=True)

    assert recorder.is_recording is False
    assert recorder.detection_data == []

    # Wait for file to be created
    base_name = os.path.basename(output_folder)
    parquet_path = os.path.join(output_folder, f"3_CoordMovimento_{base_name}.parquet")
    wait_for_condition(lambda: os.path.exists(parquet_path), timeout=2.0)

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

    # Give Windows time to flush the file to disk

    time.sleep(0.1)

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

    # Give Windows time to flush the file to disk

    time.sleep(0.1)

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


def test_start_recording_with_invalid_calibration_raises_error(recorder_setup):
    """Test that invalid calibration raises a ValueError."""
    from zebtrack.core.detector import ZoneData

    recorder, output_folder, frame_width, frame_height = recorder_setup
    mock_zones = ZoneData()

    # Try with invalid calibration, expecting a ValueError
    with pytest.raises(ValueError, match="must be finite"):
        recorder.start_recording(
            output_folder,
            frame_width,
            frame_height,
            zones=mock_zones,
            pixel_per_cm_ratio=(float("nan"), 5.0),  # Invalid
        )

    # Ensure no recording files were created due to the failure
    assert not os.path.exists(os.path.join(output_folder, "3_CoordMovimento.parquet"))


# === Edge Cases and Boundary Conditions ===


class TestRecorderEdgeCases:
    """Test edge cases and boundary conditions for Recorder."""

    def test_empty_detection_list(self, recorder_setup):
        """Test recording with empty detection list for multiple frames."""
        from zebtrack.core.detector import ZoneData

        recorder, output_folder, frame_width, frame_height = recorder_setup
        recorder.start_recording(output_folder, frame_width, frame_height, zones=ZoneData())

        # Write multiple frames with no detections
        for frame_num in range(10):
            recorder.write_detection_data(frame_num * 0.033, frame_num, [])

        recorder.stop_recording()

        # Wait for file to be created
        base_name = os.path.basename(output_folder)
        parquet_path = os.path.join(output_folder, f"3_CoordMovimento_{base_name}.parquet")
        wait_for_condition(lambda: os.path.exists(parquet_path), timeout=2.0)

        # Verify parquet file was created
        assert os.path.exists(parquet_path)

        # Verify it's empty
        df = pd.read_parquet(parquet_path)
        assert len(df) == 0

    def test_single_frame_recording(self, recorder_setup):
        """Test recording with only a single frame."""
        from zebtrack.core.detector import ZoneData

        recorder, output_folder, frame_width, frame_height = recorder_setup
        recorder.start_recording(output_folder, frame_width, frame_height, zones=ZoneData())

        # Write exactly one frame with one detection
        recorder.write_detection_data(0.0, 0, [(10, 10, 20, 20, 0.95, 1)])

        recorder.stop_recording()

        # Wait for file to be created
        base_name = os.path.basename(output_folder)
        parquet_path = os.path.join(output_folder, f"3_CoordMovimento_{base_name}.parquet")
        wait_for_condition(lambda: os.path.exists(parquet_path), timeout=2.0)

        # Verify parquet file exists and has 1 row
        assert os.path.exists(parquet_path)

        df = pd.read_parquet(parquet_path)
        assert len(df) == 1
        assert df.iloc[0]["track_id"] == 1

    def test_very_large_detection_count(self, recorder_setup):
        """Test recording with very large number of detections per frame (1000+)."""
        from zebtrack.core.detector import ZoneData

        recorder, output_folder, frame_width, frame_height = recorder_setup
        recorder.start_recording(output_folder, frame_width, frame_height, zones=ZoneData())

        # Create 1200 detections in a single frame
        large_detection_list = []
        for i in range(1200):
            x1 = (i % 100) * 10
            y1 = (i // 100) * 10
            x2 = x1 + 5
            y2 = y1 + 5
            large_detection_list.append((x1, y1, x2, y2, 0.9, i))

        recorder.write_detection_data(0.0, 0, large_detection_list)

        recorder.stop_recording()

        # Wait for file to be created
        base_name = os.path.basename(output_folder)
        parquet_path = os.path.join(output_folder, f"3_CoordMovimento_{base_name}.parquet")
        wait_for_condition(lambda: os.path.exists(parquet_path), timeout=2.0)

        # Verify all detections were saved
        assert os.path.exists(parquet_path)

        df = pd.read_parquet(parquet_path)
        assert len(df) == 1200

    def test_calibration_columns_with_valid_data(self, recorder_setup):
        """Test that calibration columns are correctly calculated with valid pixel_per_cm_ratio."""
        from zebtrack.core.detector import ZoneData

        recorder, output_folder, frame_width, frame_height = recorder_setup
        pixel_ratio = (5.0, 5.0)  # 5 pixels per cm

        recorder.start_recording(
            output_folder,
            frame_width,
            frame_height,
            zones=ZoneData(),
            pixel_per_cm_ratio=pixel_ratio,
        )

        # Write detection at center of frame
        recorder.write_detection_data(0.0, 0, [(40, 40, 60, 60, 0.9, 1)])

        recorder.stop_recording()

        # Give Windows time to flush

        time.sleep(0.1)

        base_name = os.path.basename(output_folder)
        parquet_path = os.path.join(output_folder, f"3_CoordMovimento_{base_name}.parquet")
        df = pd.read_parquet(parquet_path)

        # Check calibration columns exist and are valid
        assert "x_cm" in df.columns
        assert "y_cm" in df.columns
        assert not pd.isna(df.iloc[0]["x_cm"])
        assert not pd.isna(df.iloc[0]["y_cm"])

        # Center should be (50, 50) in pixels -> (10, 10) in cm
        assert df.iloc[0]["x_cm"] == pytest.approx(10.0, abs=0.1)
        assert df.iloc[0]["y_cm"] == pytest.approx(10.0, abs=0.1)

    def test_timestamp_discontinuities(self, recorder_setup):
        """Test handling of timestamp discontinuities (out of order, duplicates, large gaps)."""
        from zebtrack.core.detector import ZoneData

        recorder, output_folder, frame_width, frame_height = recorder_setup
        recorder.start_recording(output_folder, frame_width, frame_height, zones=ZoneData())

        # Write timestamps with discontinuities
        # 1. Normal progression
        recorder.write_detection_data(0.0, 0, [(10, 10, 20, 20, 0.9, 1)])
        recorder.write_detection_data(0.033, 1, [(11, 11, 21, 21, 0.9, 1)])

        # 2. Large gap (5 seconds)
        recorder.write_detection_data(5.033, 152, [(12, 12, 22, 22, 0.9, 1)])

        # 3. Duplicate timestamp
        recorder.write_detection_data(5.033, 153, [(13, 13, 23, 23, 0.9, 2)])

        # 4. Out of order (earlier timestamp after later ones)
        recorder.write_detection_data(2.5, 75, [(14, 14, 24, 24, 0.9, 3)])

        recorder.stop_recording()

        # Wait for file to be created
        base_name = os.path.basename(output_folder)
        parquet_path = os.path.join(output_folder, f"3_CoordMovimento_{base_name}.parquet")
        wait_for_condition(lambda: os.path.exists(parquet_path), timeout=2.0)

        # Verify all frames were saved despite discontinuities
        df = pd.read_parquet(parquet_path)

        assert len(df) == 5  # All 5 detections should be present
        # Verify the data integrity
        assert set(df["track_id"].tolist()) == {1, 2, 3}

    def test_zero_dimension_frame(self, recorder_setup):
        """Test error handling with zero or negative frame dimensions."""
        from zebtrack.core.detector import ZoneData

        recorder, output_folder, _, _ = recorder_setup

        # Test with zero width
        with pytest.raises((ValueError, RuntimeError)):
            recorder.start_recording(output_folder, 0, 100, zones=ZoneData())

        # Test with zero height
        with pytest.raises((ValueError, RuntimeError)):
            recorder.start_recording(output_folder, 100, 0, zones=ZoneData())

    def test_extreme_confidence_values(self, recorder_setup):
        """Test handling of extreme confidence values (0.0, 1.0, >1.0)."""
        from zebtrack.core.detector import ZoneData

        recorder, output_folder, frame_width, frame_height = recorder_setup
        recorder.start_recording(output_folder, frame_width, frame_height, zones=ZoneData())

        # Write detections with extreme confidence values
        recorder.write_detection_data(
            0.0,
            0,
            [
                (10, 10, 20, 20, 0.0, 1),  # Zero confidence
                (20, 20, 30, 30, 1.0, 2),  # Perfect confidence
                (30, 30, 40, 40, 1.5, 3),  # Over 1.0 (should still save)
            ],
        )

        recorder.stop_recording()

        # Give Windows time to flush

        time.sleep(0.1)

        base_name = os.path.basename(output_folder)
        parquet_path = os.path.join(output_folder, f"3_CoordMovimento_{base_name}.parquet")
        df = pd.read_parquet(parquet_path)

        # All should be saved
        assert len(df) == 3
        assert df.iloc[0]["confidence"] == pytest.approx(0.0)
        assert df.iloc[1]["confidence"] == pytest.approx(1.0)
        assert df.iloc[2]["confidence"] == pytest.approx(1.5)

    def test_negative_coordinates(self, recorder_setup):
        """Test handling of negative bounding box coordinates."""
        from zebtrack.core.detector import ZoneData

        recorder, output_folder, frame_width, frame_height = recorder_setup
        recorder.start_recording(output_folder, frame_width, frame_height, zones=ZoneData())

        # Write detections with negative coordinates
        recorder.write_detection_data(
            0.0,
            0,
            [
                (-10, -10, 10, 10, 0.9, 1),  # Partially out of frame (top-left)
                (90, 90, 110, 110, 0.9, 2),  # Partially out of frame (bottom-right)
            ],
        )

        recorder.stop_recording()

        # Give Windows time to flush

        time.sleep(0.1)

        base_name = os.path.basename(output_folder)
        parquet_path = os.path.join(output_folder, f"3_CoordMovimento_{base_name}.parquet")
        df = pd.read_parquet(parquet_path)

        # Should still be saved
        assert len(df) == 2
        # Center calculation should still work
        assert df.iloc[0]["x_center_px"] == pytest.approx(0.0)
        assert df.iloc[0]["y_center_px"] == pytest.approx(0.0)
