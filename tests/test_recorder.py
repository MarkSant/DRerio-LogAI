import os
import shutil
import time
import typing

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
    from zebtrack.core.detection import ZoneData

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
    from zebtrack.core.detection import ZoneData

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
    from zebtrack.core.detection import ZoneData

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
        "uncertainty",
        "bbox_iou",
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
    assert row1["uncertainty"] == pytest.approx(0.02)  # 1 - 0.98
    assert row1["bbox_iou"] == pytest.approx(1.0)  # First detection
    assert row1["x_center_px"] == 20.0  # (10+30)/2
    assert row1["y_center_px"] == 30.0  # (20+40)/2
    assert row1["x_cm"] == pytest.approx(2.0)  # 20.0 / 10.0
    assert row1["y_cm"] == pytest.approx(3.0)  # 30.0 / 10.0


def test_periodic_flush_triggers_before_stop(recorder_setup):
    """Recorder should flush buffered data to disk automatically."""
    import time

    from zebtrack.core.detection import ZoneData

    recorder, output_folder, frame_width, frame_height = recorder_setup

    recorder._flush_row_threshold = 1
    recorder._flush_interval_seconds = 0.0

    recorder.start_recording(output_folder, frame_width, frame_height, zones=ZoneData())

    recorder.write_detection_data(0.5, 10, [(5, 5, 15, 15, 0.9, 42)])

    # Phase 4 / M4: flush is now async; poll briefly for the dedicated
    # flush thread to drain the buffer instead of asserting synchronously.
    deadline = time.time() + 2.0
    while time.time() < deadline and recorder.detection_data:
        time.sleep(0.01)
    assert recorder.detection_data == []

    recorder.stop_recording()


def test_pixel_ratio_change_during_recording_is_rejected(recorder_setup):
    """Changing calibration mid-recording should raise to avoid schema drift."""
    from zebtrack.core.detection import ZoneData

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
    from zebtrack.core.detection import ZoneData

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

    # When force_stop=True is called (due to schema mismatch error),
    # data is NOT saved to prevent corrupted files.
    # So the parquet file should NOT exist.
    base_name = os.path.basename(output_folder)
    parquet_path = os.path.join(output_folder, f"3_CoordMovimento_{base_name}.parquet")
    assert not os.path.exists(parquet_path), "Parquet should NOT be created on force_stop"


def test_write_detection_data_coerces_track_id_types(recorder_setup):
    from zebtrack.core.detection import ZoneData

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
    from zebtrack.core.detection import ZoneData

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
    from zebtrack.core.detection import ZoneData

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
    from zebtrack.core.detection import ZoneData

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
        from zebtrack.core.detection import ZoneData

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
        from zebtrack.core.detection import ZoneData

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
        from zebtrack.core.detection import ZoneData

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
        from zebtrack.core.detection import ZoneData

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
        from zebtrack.core.detection import ZoneData

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
        from zebtrack.core.detection import ZoneData

        recorder, output_folder, _, _ = recorder_setup

        # Test with zero width
        with pytest.raises((ValueError, RuntimeError)):
            recorder.start_recording(output_folder, 0, 100, zones=ZoneData())

        # Test with zero height
        with pytest.raises((ValueError, RuntimeError)):
            recorder.start_recording(output_folder, 100, 0, zones=ZoneData())

    def test_extreme_confidence_values(self, recorder_setup):
        """Test handling of extreme confidence values (0.0, 1.0, >1.0)."""
        from zebtrack.core.detection import ZoneData

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
        from zebtrack.core.detection import ZoneData

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


def test_recorder_thread_safety_concurrent_writes(recorder_setup):
    """Test that concurrent write_detection_data calls don't lose or corrupt data.

    Phase 5.2: Validates that the threading.Lock in Recorder properly
    serializes concurrent appends to detection_data.
    """
    import threading

    from zebtrack.core.detection import ZoneData

    recorder, output_folder, frame_width, frame_height = recorder_setup

    recorder.start_recording(
        output_folder=output_folder,
        frame_width=frame_width,
        frame_height=frame_height,
        zones=ZoneData(),
        is_video_file=True,
    )

    # Force large flush thresholds to accumulate data in-memory
    recorder._flush_row_threshold = 100000
    recorder._flush_interval_seconds = 9999

    num_threads = 4
    detections_per_thread = 50
    barrier = threading.Barrier(num_threads)
    errors: list[Exception] = []

    def worker(thread_id: int) -> None:
        try:
            barrier.wait(timeout=5)  # Synchronize start
            for i in range(detections_per_thread):
                frame = thread_id * 1000 + i
                ts = f"2025-01-01 00:00:{frame:02d}"
                det = [(float(i), float(i), float(i + 10), float(i + 10), 0.9, thread_id)]
                recorder.write_detection_data(ts, frame, det)
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(tid,), daemon=True) for tid in range(num_threads)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"Worker threads raised errors: {errors}"

    # All detections should be present (no data lost)
    with recorder._data_lock:
        total = len(recorder.detection_data)
    expected = num_threads * detections_per_thread
    assert total == expected, f"Expected {expected} detections but got {total}"

    recorder.stop_recording()


def test_recorder_atomic_write_leaves_no_tmp_on_success(recorder_setup):
    """Test that atomic write produces final file and no .tmp artifact.

    Phase 5.3: Validates the temp-file + rename pattern.
    """
    from zebtrack.core.detection import ZoneData

    recorder, output_folder, frame_width, frame_height = recorder_setup

    recorder.start_recording(
        output_folder=output_folder,
        frame_width=frame_width,
        frame_height=frame_height,
        zones=ZoneData(),
        is_video_file=True,
    )

    ts = "2025-01-01 00:00:00"
    det = [(10.0, 10.0, 20.0, 20.0, 0.95, 1)]
    recorder.write_detection_data(ts, 1, det)
    recorder.stop_recording()

    time.sleep(0.1)

    base_name = os.path.basename(output_folder)
    parquet_path = os.path.join(output_folder, f"3_CoordMovimento_{base_name}.parquet")
    tmp_path = parquet_path + ".tmp"

    assert os.path.exists(parquet_path), "Final Parquet file should exist"
    assert not os.path.exists(tmp_path), "Temp file should be cleaned up"


def test_recorder_verify_parquet_integrity(tmp_path):
    """Test that _verify_parquet_integrity correctly validates files.

    Phase 5.3: Validates the integrity check utility.
    """
    import pyarrow as pa
    from pyarrow import parquet as pq

    # Valid file
    valid_path = str(tmp_path / "valid.parquet")
    table = pa.table({"a": [1, 2], "b": [3, 4]})
    pq.write_table(table, valid_path)
    assert Recorder._verify_parquet_integrity(valid_path) is True

    # Invalid file (random bytes)
    invalid_path = str(tmp_path / "invalid.parquet")
    with open(invalid_path, "wb") as f:
        f.write(b"this is not a parquet file")
    assert Recorder._verify_parquet_integrity(invalid_path) is False

    # Missing file
    assert Recorder._verify_parquet_integrity(str(tmp_path / "nonexistent.parquet")) is False


# =============================================================================
# Sidecar de máscaras — o schema IMUTÁVEL de 3_CoordMovimento não muda
# =============================================================================


def test_immutable_schema_unchanged_by_mask_feature(recorder_setup):
    """As colunas de ``3_CoordMovimento`` seguem exatamente as de sempre.

    O sidecar de máscaras existe justamente para NÃO tocar neste schema, que é
    imutável por contrato de projeto (CLAUDE.md). Este teste é a guarda: se
    alguém "só acrescentar uma coluninha" de geometria aqui, ele quebra.
    """
    recorder, output_folder, frame_width, frame_height = recorder_setup
    recorder._persist_masks = True

    from zebtrack.core.detection import ZoneData

    recorder.start_recording(
        output_folder, frame_width, frame_height, zones=ZoneData(), is_video_file=True
    )
    recorder.write_detection_data(0.0, 0, [(1, 1, 5, 5, 0.9, 1, 1)])
    recorder.write_mask_data(0, {1: np.array([[0.0, 0.0], [4.0, 0.0], [4.0, 4.0]])})
    recorder.stop_recording()

    base_name = os.path.basename(output_folder)
    trajectory = pd.read_parquet(
        os.path.join(output_folder, f"3_CoordMovimento_{base_name}.parquet")
    )

    assert list(trajectory.columns) == [
        "timestamp",
        "frame",
        "track_id",
        "x1",
        "y1",
        "x2",
        "y2",
        "confidence",
        "uncertainty",
        "bbox_iou",
        "x_center_px",
        "y_center_px",
    ]
    assert "mask_wkb" not in trajectory.columns
    # E a máscara foi para o arquivo separado.
    assert os.path.exists(os.path.join(output_folder, f"3b_Mascaras_{base_name}.parquet"))


def test_persist_masks_defaults_to_off(recorder_setup):
    """O padrão é NÃO gravar máscaras: custo zero para quem não usa seg_overlap."""
    recorder, _output_folder, _w, _h = recorder_setup
    assert recorder.persist_masks is False
    assert recorder.mask_parquet_filename == ""


# =============================================================================
# Object sidecar ``3c_Objetos_`` (ADR-010)
# =============================================================================

_OBJECT_COLUMNS_AND_TYPES = [
    ("frame", "int64"),
    ("timestamp", "double"),
    ("t_event_s", "double"),
    ("class_id", "int16"),
    ("class_name", "dictionary<values=string, indices=int32, ordered=0>"),
    ("role", "dictionary<values=string, indices=int32, ordered=0>"),
    ("x1", "float"),
    ("y1", "float"),
    ("x2", "float"),
    ("y2", "float"),
    ("confidence", "float"),
    ("track_id", "int64"),
    ("aquarium_id", "int16"),
]


def _objects_settings(enabled: bool = True):
    from tests.helpers.prerecorded_pipeline import load_pristine_settings

    settings = load_pristine_settings()
    settings.recorder.persist_object_sidecar = enabled
    return settings


def _context(bbox, class_id=2, name="experimenter", confidence=0.7, aquarium_id=None):
    return {
        "class_id": class_id,
        "class_name": name,
        "role": "context",
        "bbox": bbox,
        "confidence": confidence,
        "aquarium_id": aquarium_id,
    }


def _subject(bbox, aquarium_id=None, track_id=None):
    item = {
        "class_id": 1,
        "class_name": "rat",
        "role": "subject",
        "bbox": bbox,
        "confidence": 0.9,
        "aquarium_id": aquarium_id,
    }
    if track_id is not None:
        item["track_id"] = track_id
    return item


def _read_3c(path):
    """Read a ``3c_Objetos_`` sidecar the test expects to be valid."""
    from zebtrack.io.object_sidecar import read_object_sidecar

    df = read_object_sidecar(path)
    assert df is not None, f"unreadable object sidecar: {path}"
    return df


class _DoublingCalibration:
    """Calibration double: warps every coordinate by x2 (the trajectory's path)."""

    pixel_per_cm_ratio = (10.0, 10.0)

    def transform_bbox(self, x1, y1, x2, y2):
        return x1 * 2, y1 * 2, x2 * 2, y2 * 2

    def transform_points(self, points):
        return [[x * 2, y * 2] for x, y in points]


@pytest.fixture
def objects_recorder(tmp_path):
    from zebtrack.core.detection import ZoneData

    folder = tmp_path / "objects"
    recorder = Recorder(settings_obj=_objects_settings())
    yield recorder, folder, ZoneData()
    if recorder.is_recording:
        recorder.stop_recording(force_stop=True)


def _objects_path(folder, base="base"):
    return folder / f"3c_Objetos_{base}.parquet"


class TestObjectSidecar:
    def test_columns_order_and_types_follow_adr_010(self, objects_recorder):
        import pyarrow.parquet as pq

        recorder, folder, zones = objects_recorder
        recorder.start_recording(folder, 100, 100, zones, is_video_file=True, base_name="base")
        recorder.write_object_data(0.0, 0, 0.0, [_context((1, 2, 3, 4))])
        recorder.stop_recording()

        schema = pq.read_schema(_objects_path(folder))
        assert [(f.name, str(f.type)) for f in schema] == _OBJECT_COLUMNS_AND_TYPES

    def test_one_heartbeat_per_processed_frame_even_without_detections(self, objects_recorder):
        recorder, folder, zones = objects_recorder
        recorder.start_recording(folder, 100, 100, zones, is_video_file=True, base_name="base")
        recorder.write_object_data(0.0, 0, 0.0, [])
        recorder.write_object_data(0.5, 5, 0.5, [_context((1, 2, 3, 4))])
        recorder.write_object_data(1.0, 10, 1.0, [])
        recorder.stop_recording()

        df = _read_3c(_objects_path(folder))
        heartbeat = df[df["class_id"] == -1]
        assert heartbeat["frame"].tolist() == [0, 5, 10]
        assert heartbeat["role"].tolist() == ["frame"] * 3
        assert heartbeat[["x1", "y1", "x2", "y2", "confidence"]].isna().all().all()
        objects = df[df["class_id"] != -1]
        assert objects["frame"].tolist() == [5]
        assert objects["role"].tolist() == ["context"]
        assert objects["class_name"].tolist() == ["experimenter"]
        assert objects["t_event_s"].tolist() == [0.5]
        # Heartbeat first, then the frame's objects.
        assert df["class_id"].tolist() == [-1, -1, 2, -1]

    def test_coordinates_stay_raw_even_with_a_calibration(self, objects_recorder):
        recorder, folder, zones = objects_recorder
        recorder.start_recording(
            folder,
            100,
            100,
            zones,
            is_video_file=True,
            base_name="base",
            calibration=_DoublingCalibration(),
        )
        recorder.write_detection_data(0.0, 0, [(10, 20, 30, 40, 0.9, 1, 1)])
        recorder.write_object_data(0.0, 0, 0.0, [_subject((10.0, 20.0, 30.0, 40.0))])
        recorder.stop_recording()

        objects = _read_3c(_objects_path(folder))
        row = objects[objects["class_id"] == 1].iloc[0]
        assert [row["x1"], row["y1"], row["x2"], row["y2"]] == [10.0, 20.0, 30.0, 40.0]
        # The trajectory DID go through the calibration: the double is live.
        trajectory = pd.read_parquet(folder / "3_CoordMovimento_base.parquet")
        assert trajectory["x1"].tolist() == [20]

    def test_kill_switch_writes_nothing(self, tmp_path):
        from zebtrack.core.detection import ZoneData

        recorder = Recorder(settings_obj=_objects_settings(enabled=False))
        folder = tmp_path / "off"
        recorder.start_recording(folder, 100, 100, ZoneData(), is_video_file=True, base_name="b")
        recorder.write_object_data(0.0, 0, 0.0, [_context((1, 2, 3, 4))])
        recorder.stop_recording()

        assert recorder.persist_object_sidecar is False
        assert recorder.object_parquet_filename == ""
        assert not _objects_path(folder, "b").exists()

    def test_recorder_without_settings_writes_nothing(self, recorder_setup):
        recorder, output_folder, w, h = recorder_setup
        from zebtrack.core.detection import ZoneData

        recorder.start_recording(output_folder, w, h, ZoneData(), is_video_file=True)
        recorder.write_object_data(0.0, 0, 0.0, [])
        recorder.stop_recording()

        assert recorder.persist_object_sidecar is False
        assert not any(name.startswith("3c_") for name in os.listdir(output_folder))

    def test_not_recording_or_paused_writes_nothing(self, objects_recorder):
        recorder, folder, zones = objects_recorder
        recorder.write_object_data(0.0, 0, 0.0, [])  # before start: no-op, no crash
        recorder.start_recording(folder, 100, 100, zones, is_video_file=True, base_name="base")
        recorder.pause_recording()
        recorder.write_object_data(0.0, 0, 0.0, [])
        recorder.resume_recording()
        recorder.write_object_data(0.1, 1, 0.1, [])
        recorder.stop_recording()

        assert _read_3c(_objects_path(folder))["frame"].tolist() == [1]

    def test_invalid_observations_are_skipped_not_fatal(self, objects_recorder):
        recorder, folder, zones = objects_recorder
        recorder.start_recording(folder, 100, 100, zones, is_video_file=True, base_name="base")
        bad = [
            _context(None),
            _context((1, 2, 3)),
            _context((1, 2, float("nan"), 4)),
            {"bbox": (1, 2, 3, 4), "role": "context"},  # no class_id
        ]
        recorder.write_object_data(0.0, 0, 0.0, [*bad, _context((1, 2, 3, 4))])
        recorder.stop_recording()

        df = _read_3c(_objects_path(folder))
        assert df["class_id"].tolist() == [-1, 2]

    def test_track_id_is_kept_when_the_observation_has_one(self, objects_recorder):
        recorder, folder, zones = objects_recorder
        recorder.start_recording(folder, 100, 100, zones, is_video_file=True, base_name="base")
        recorder.write_object_data(0.0, 0, 0.0, [_subject((1, 2, 3, 4), track_id=7)])
        recorder.stop_recording()

        df = _read_3c(_objects_path(folder))
        assert df["track_id"].tolist()[1] == 7

    def test_trajectory_schema_is_unchanged_by_the_object_sidecar(self, objects_recorder):
        recorder, folder, zones = objects_recorder
        recorder.start_recording(folder, 100, 100, zones, is_video_file=True, base_name="base")
        recorder.write_detection_data(0.0, 0, [(1, 1, 5, 5, 0.9, 1, 1)])
        recorder.write_object_data(0.0, 0, 0.0, [_context((1, 2, 3, 4))])
        recorder.stop_recording()

        trajectory = pd.read_parquet(folder / "3_CoordMovimento_base.parquet")
        assert list(trajectory.columns) == [
            "timestamp",
            "frame",
            "track_id",
            "x1",
            "y1",
            "x2",
            "y2",
            "confidence",
            "uncertainty",
            "bbox_iou",
            "x_center_px",
            "y_center_px",
        ]
        assert _objects_path(folder).exists()

    def test_metadata_given_at_start_lands_in_the_parquet(self, objects_recorder):
        from zebtrack.io.object_sidecar import (
            CLOCK_PTS,
            ObjectSidecarMetadata,
            read_object_sidecar_metadata,
        )

        recorder, folder, zones = objects_recorder
        metadata = ObjectSidecarMetadata(
            class_names={0: "arena", 1: "rat", 2: "experimenter"},
            class_roles={"arena": "arena", "rat": "subject", "experimenter": "context"},
            weight_sha256="ab" * 32,
            clock=CLOCK_PTS,
            analysis_interval_frames=3,
            class_roles_source="weight",
        )
        recorder.start_recording(
            folder,
            100,
            100,
            zones,
            is_video_file=True,
            base_name="base",
            object_metadata=metadata,
        )
        recorder.write_object_data(0.0, 0, 0.0, [])
        recorder.stop_recording()

        assert read_object_sidecar_metadata(_objects_path(folder)) == metadata

    @pytest.mark.parametrize(("is_video_file", "clock"), [(True, "pts"), (False, "capture_perf")])
    def test_default_metadata_names_the_clock_of_the_pipeline(
        self, objects_recorder, is_video_file, clock
    ):
        from zebtrack.io.object_sidecar import read_object_sidecar_metadata

        recorder, folder, zones = objects_recorder
        recorder.start_recording(
            folder, 64, 64, zones, is_video_file=is_video_file, base_name="base"
        )
        recorder.write_object_data(0.0, 0, 0.0, [])
        recorder.stop_recording()

        metadata = read_object_sidecar_metadata(_objects_path(folder))
        assert metadata is not None
        assert metadata.clock == clock
        assert metadata.class_names == {}
        assert metadata.analysis_interval_frames is None

    def test_write_failure_degrades_and_removes_the_partial_file(self, objects_recorder):
        from unittest.mock import patch

        from structlog.testing import capture_logs

        from zebtrack.io import recorder as recorder_module

        recorder, folder, zones = objects_recorder
        recorder.start_recording(folder, 100, 100, zones, is_video_file=True, base_name="base")
        recorder.write_object_data(0.0, 0, 0.0, [])
        recorder._flush_object_data(force=True)
        assert _objects_path(folder).exists()

        with (
            capture_logs() as logs,
            patch.object(recorder_module, "build_object_table", side_effect=OSError("disk full")),
        ):
            recorder.write_object_data(0.1, 1, 0.1, [])
            recorder._flush_object_data(force=True)

        warnings = [e for e in logs if e["event"] == "recorder.object_sidecar.write_failed"]
        assert len(warnings) == 1
        assert warnings[0]["log_level"] == "warning"
        # A truncated sidecar would read as "frames not processed": it is gone.
        assert not _objects_path(folder).exists()

        # The session goes on, the sidecar stays off, the trajectory is intact.
        recorder.write_object_data(0.2, 2, 0.2, [])
        recorder.write_detection_data(0.2, 2, [(1, 1, 5, 5, 0.9, 1, 1)])
        recorder.stop_recording()
        assert not _objects_path(folder).exists()
        assert pd.read_parquet(folder / "3_CoordMovimento_base.parquet")["frame"].tolist() == [2]

    def test_force_stop_discards_the_buffer(self, objects_recorder):
        recorder, folder, zones = objects_recorder
        recorder.start_recording(folder, 100, 100, zones, is_video_file=True, base_name="base")
        recorder.write_object_data(0.0, 0, 0.0, [])
        recorder.stop_recording(force_stop=True, reason="cancel")

        assert not _objects_path(folder).exists()

    def test_buffer_crossing_the_threshold_is_flushed_before_stop(self, tmp_path):
        from zebtrack.core.detection import ZoneData

        settings = _objects_settings()
        settings.recorder.flush_row_threshold = 3
        recorder = Recorder(settings_obj=settings)
        folder = tmp_path / "flush"
        recorder.start_recording(folder, 100, 100, ZoneData(), is_video_file=True, base_name="b")
        try:
            for frame in range(4):
                recorder.write_object_data(frame / 10, frame, frame / 10, [])
            wait_for_condition(lambda: _objects_path(folder, "b").exists(), timeout=5.0)
        finally:
            recorder.stop_recording()

        assert _read_3c(_objects_path(folder, "b"))["frame"].tolist() == [0, 1, 2, 3]

    def test_without_flush_thread_the_threshold_flushes_synchronously(self, tmp_path):
        from zebtrack.core.detection import ZoneData

        settings = _objects_settings()
        settings.recorder.flush_row_threshold = 2
        recorder = Recorder(settings_obj=settings)
        folder = tmp_path / "sync"
        recorder.start_recording(folder, 100, 100, ZoneData(), is_video_file=True, base_name="b")
        recorder._stop_flush_thread(drain=False)
        try:
            recorder.write_object_data(0.0, 0, 0.0, [])
            recorder.write_object_data(0.1, 1, 0.1, [])

            assert _objects_path(folder, "b").exists()
        finally:
            recorder.stop_recording()


class TestStaleSidecarCleanup:
    def _plant(self, folder, names):
        folder.mkdir(parents=True, exist_ok=True)
        for name in names:
            (folder / name).write_bytes(b"stale")

    @pytest.mark.parametrize("enabled", [True, False])
    def test_start_recording_removes_stale_sidecars_of_the_same_base(self, tmp_path, enabled):
        from zebtrack.core.detection import ZoneData

        folder = tmp_path / "session"
        stale = [
            "3b_Mascaras_base.parquet",
            "3c_Objetos_base.parquet",
            "7_AnalysisWindow_base.json",
        ]
        kept = [
            "3b_Mascaras_other.parquet",
            "3c_Objetos_base_2.parquet",
            "7_AnalysisWindow_other.json",
            "6_FrameLedger_base.csv",
            "notes.txt",
        ]
        self._plant(folder, stale + kept)
        recorder = Recorder(settings_obj=_objects_settings(enabled=enabled))

        recorder.start_recording(folder, 100, 100, ZoneData(), is_video_file=True, base_name="base")
        try:
            for name in stale:
                assert not (folder / name).exists(), name
            for name in kept:
                assert (folder / name).exists(), name
        finally:
            recorder.stop_recording()

    def test_cleanup_runs_without_settings_too(self, tmp_path):
        """The stale-mask bug (AUDIT) hit sessions without any object sidecar."""
        from zebtrack.core.detection import ZoneData

        folder = tmp_path / "session"
        self._plant(folder, ["3b_Mascaras_base.parquet"])
        recorder = Recorder()

        recorder.start_recording(folder, 100, 100, ZoneData(), is_video_file=True, base_name="base")
        recorder.stop_recording()

        assert not (folder / "3b_Mascaras_base.parquet").exists()

    def test_an_unremovable_stale_file_only_warns(self, tmp_path, monkeypatch):
        from pathlib import Path

        from structlog.testing import capture_logs

        from zebtrack.core.detection import ZoneData

        folder = tmp_path / "session"
        self._plant(folder, ["3c_Objetos_base.parquet"])
        original_unlink = Path.unlink

        def locked(self, *args, **kwargs):
            if self.name == "3c_Objetos_base.parquet":
                raise PermissionError("locked by another process")
            return original_unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", locked)
        recorder = Recorder(settings_obj=_objects_settings(enabled=False))

        with capture_logs() as logs:
            started = recorder.start_recording(
                folder, 100, 100, ZoneData(), is_video_file=True, base_name="base"
            )
        recorder.stop_recording()

        assert started is True
        assert any(e["event"] == "recorder.start.stale_sidecar_remove_failed" for e in logs)


class TestObjectSidecarMultiAquarium:
    _POLYGONS: typing.ClassVar[dict[int, list[list[int]]]] = {
        0: [[0, 0], [100, 0], [100, 100], [0, 100]],
        1: [[200, 0], [300, 0], [300, 100], [200, 100]],
    }

    def _start(self, tmp_path, **kwargs):
        from zebtrack.core.detection import ZoneData

        recorder = Recorder(settings_obj=_objects_settings())
        zones = {
            aq: ZoneData(polygon=[tuple(p) for p in poly]) for aq, poly in self._POLYGONS.items()
        }
        assert recorder.start_recording_multi_aquarium(
            output_folder=str(tmp_path / "results"),
            width=320,
            height=120,
            zones_by_aquarium=zones,
            base_name="exp",
            write_video=False,
            **kwargs,
        )
        return recorder

    def _read(self, tmp_path, aquarium_number):
        folder = tmp_path / "results" / f"aquarium_{aquarium_number}"
        return _read_3c(folder / f"3c_Objetos_exp_aquarium_{aquarium_number}.parquet")

    def test_each_aquarium_gets_its_own_sidecar_with_its_heartbeat(self, tmp_path):
        recorder = self._start(tmp_path)
        recorder.write_partitioned_object_data(0.0, 0, 0.0, [], self._POLYGONS)
        recorder.stop_recording_multi_aquarium()

        for number, aq_id in ((1, 0), (2, 1)):
            df = self._read(tmp_path, number)
            assert df["class_id"].tolist() == [-1]
            assert df["aquarium_id"].tolist() == [aq_id]

    def test_rows_are_routed_by_role_and_position(self, tmp_path):
        recorder = self._start(tmp_path)
        observations = [
            _subject((10, 10, 20, 20), aquarium_id=0),
            _subject((210, 10, 220, 20), aquarium_id=1),
            _context((140, 50, 160, 70), class_id=3, name="hand", aquarium_id=0),
            _context((240, 40, 260, 60), class_id=4, name="box", aquarium_id=1),
        ]
        recorder.write_partitioned_object_data(0.5, 5, 0.5, observations, self._POLYGONS)
        recorder.stop_recording_multi_aquarium()

        first = self._read(tmp_path, 1)
        second = self._read(tmp_path, 2)
        # aquarium 0: its subject + the hand in no aquarium (null aquarium_id).
        assert first["class_id"].tolist() == [-1, 1, 3]
        assert first["aquarium_id"].tolist()[:2] == [0, 0]
        assert pd.isna(first["aquarium_id"].iloc[2])
        # aquarium 1: its subject, the shared hand and the box inside it.
        assert second["class_id"].tolist() == [-1, 1, 3, 4]
        assert second["aquarium_id"].tolist()[:2] == [1, 1]
        assert pd.isna(second["aquarium_id"].iloc[2])
        assert second["aquarium_id"].tolist()[3] == 1

    def test_metadata_reaches_every_sub_recorder(self, tmp_path):
        from zebtrack.io.object_sidecar import (
            CLOCK_PTS,
            ObjectSidecarMetadata,
            read_object_sidecar_metadata,
        )

        metadata = ObjectSidecarMetadata(
            class_names={1: "zebrafish"}, clock=CLOCK_PTS, analysis_interval_frames=10
        )
        recorder = self._start(tmp_path, object_metadata=metadata)
        recorder.write_partitioned_object_data(0.0, 0, 0.0, [], self._POLYGONS)
        recorder.stop_recording_multi_aquarium()

        for number in (1, 2):
            folder = tmp_path / "results" / f"aquarium_{number}"
            path = folder / f"3c_Objetos_exp_aquarium_{number}.parquet"
            assert read_object_sidecar_metadata(path) == metadata

    def test_partitioned_write_requires_multi_aquarium_mode(self):
        with pytest.raises(RuntimeError):
            Recorder().write_partitioned_object_data(0.0, 0, 0.0, [], self._POLYGONS)
