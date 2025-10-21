"""
Centralized fixtures for integration tests.

Provides reusable components for testing multi-component workflows.
"""

import gc
import time
from pathlib import Path

import pytest

from zebtrack.core.detector import ZoneData
from zebtrack.core.state_manager import StateManager
from zebtrack.io.recorder import Recorder


@pytest.fixture
def integration_recorder(tmp_path):
    """
    Recorder with proper cleanup for integration tests.

    Ensures recorder is properly stopped and cleaned up even if test fails.
    Includes Windows-specific delays for file system sync.

    Yields:
        Recorder: Fresh recorder instance for the test
    """
    recorder = Recorder()
    yield recorder

    # Cleanup: ensure recording is stopped
    if recorder.is_recording:
        recorder.stop_recording(force_stop=True)

    # Force cleanup to prevent resource leaks
    del recorder
    gc.collect()
    time.sleep(0.1)  # Give Windows time to release file handles


@pytest.fixture
def integration_zones():
    """
    Standard zone configuration for integration tests.

    Returns:
        ZoneData: Two-zone configuration with:
            - Processing area: 1280x720
            - Zone A: 200x200 at (100, 100)
            - Zone B: 200x200 at (400, 100)
    """
    return ZoneData(
        polygon=[(0, 0), (1280, 0), (1280, 720), (0, 720)],
        roi_polygons=[
            [(100, 100), (300, 100), (300, 300), (100, 300)],  # Zone A
            [(400, 100), (600, 100), (600, 300), (400, 300)],  # Zone B
        ],
        roi_names=["Zone A", "Zone B"],
    )


@pytest.fixture
def integration_single_zone():
    """
    Single zone configuration for simpler integration tests.

    Returns:
        ZoneData: One-zone configuration with:
            - Processing area: 1280x720
            - Test Zone: 200x200 at (100, 100)
    """
    return ZoneData(
        polygon=[(0, 0), (1280, 0), (1280, 720), (0, 720)],
        roi_polygons=[
            [(100, 100), (300, 100), (300, 300), (100, 300)],
        ],
        roi_names=["Test Zone"],
    )


@pytest.fixture
def integration_state_manager():
    """
    StateManager for integration tests.

    Returns:
        StateManager: Fresh instance for tracking state changes
    """
    return StateManager()


@pytest.fixture
def integration_output_dir(tmp_path):
    """
    Create a temporary output directory for integration test results.

    Args:
        tmp_path: pytest's tmp_path fixture

    Returns:
        Path: Directory for test outputs (automatically cleaned up)
    """
    output_dir = tmp_path / "integration_results"
    output_dir.mkdir()
    return output_dir


# Helper functions for common test patterns

def setup_basic_recording(recorder, zones, output_dir, base_name="test_video", **kwargs):
    """
    Standard recording setup for integration tests.

    Args:
        recorder: Recorder instance
        zones: ZoneData configuration
        output_dir: Output directory path
        base_name: Base name for output files
        **kwargs: Additional arguments for start_recording()

    Returns:
        Recorder: The configured recorder (for chaining)
    """
    recorder.start_recording(
        output_folder=str(output_dir),
        frame_width=1280,
        frame_height=720,
        zones=zones,
        is_video_file=True,
        base_name=base_name,
        **kwargs,
    )
    return recorder


def verify_parquet_schema(file_path, expected_columns):
    """
    Verify Parquet file has expected schema.

    Args:
        file_path: Path to Parquet file
        expected_columns: Set of expected column names

    Raises:
        AssertionError: If schema doesn't match
    """
    import pyarrow.parquet as pq

    table = pq.read_table(str(file_path))
    actual_columns = set(table.schema.names)
    assert actual_columns == expected_columns, (
        f"Schema mismatch:\n"
        f"  Expected: {sorted(expected_columns)}\n"
        f"  Actual:   {sorted(actual_columns)}\n"
        f"  Missing:  {sorted(expected_columns - actual_columns)}\n"
        f"  Extra:    {sorted(actual_columns - expected_columns)}"
    )


def verify_parquet_row_count(file_path, expected_count):
    """
    Verify Parquet file has expected number of rows.

    Args:
        file_path: Path to Parquet file
        expected_count: Expected row count

    Raises:
        AssertionError: If row count doesn't match
    """
    import pyarrow.parquet as pq

    table = pq.read_table(str(file_path))
    actual_count = len(table)
    assert actual_count == expected_count, (
        f"Row count mismatch: expected {expected_count}, got {actual_count}"
    )


def create_sample_detections(num_detections=1, track_id=1):
    """
    Create sample detection data for testing.

    Args:
        num_detections: Number of detections to create
        track_id: Starting track ID

    Returns:
        list: List of detection tuples (x1, y1, x2, y2, confidence, track_id)
    """
    return [(100 + i * 50, 100, 150 + i * 50, 150, 0.9, track_id + i) for i in range(num_detections)]
