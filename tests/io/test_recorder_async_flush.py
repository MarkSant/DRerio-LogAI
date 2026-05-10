"""Phase 4 / M4 tests for the async Parquet flush thread.

Verifies that the recorder's dedicated flush thread:

1. Starts on ``start_recording`` and stops cleanly on ``stop_recording``.
2. Drains pending data on a normal stop (not on force-stop).
3. Frees the calling thread immediately when ``write_detection_data``
   crosses the row threshold (the work happens off-thread).
4. Falls back to a synchronous flush when no thread is running
   (legacy callers that bypass ``start_recording``).
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.io.recorder import Recorder


@pytest.fixture
def recorder_setup(tmp_path: Path):
    output = tmp_path / "session"
    output.mkdir()
    recorder = Recorder()
    recorder._flush_row_threshold = 1
    recorder._flush_interval_seconds = 0.05
    yield recorder, str(output)
    if recorder.is_recording:
        recorder.stop_recording(force_stop=True)


def _wait(predicate, timeout: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_flush_thread_started_and_named(recorder_setup) -> None:
    recorder, output = recorder_setup
    recorder.start_recording(output, 640, 480, zones=ZoneData(), is_video_file=True)

    assert recorder._flush_thread is not None
    assert recorder._flush_thread.is_alive()
    assert recorder._flush_thread.daemon
    assert "recorder-flush" in (recorder._flush_thread.name or "")

    recorder.stop_recording()


def test_flush_thread_joined_on_normal_stop_and_data_drained(recorder_setup) -> None:
    recorder, output = recorder_setup
    recorder.start_recording(output, 640, 480, zones=ZoneData(), is_video_file=True)
    recorder.write_detection_data(0.0, 1, [(0, 0, 10, 10, 0.9, 1)])

    recorder.stop_recording()

    # Thread reference cleared
    assert recorder._flush_thread is None
    # Buffer drained
    assert recorder.detection_data == []
    # Parquet file written (drain ran on stop)
    base = os.path.basename(output)
    parquet_path = Path(output) / f"3_CoordMovimento_{base}.parquet"
    assert parquet_path.exists()


def test_force_stop_skips_final_drain(recorder_setup) -> None:
    """force_stop=True must NOT flush remaining data to disk — the
    Parquet file is closed without an extra write."""
    recorder, output = recorder_setup
    recorder._flush_row_threshold = 10_000  # never auto-flush during the test
    recorder._flush_interval_seconds = 9999.0

    recorder.start_recording(output, 640, 480, zones=ZoneData(), is_video_file=True)
    recorder.write_detection_data(0.0, 1, [(0, 0, 10, 10, 0.9, 1)])

    # No periodic flush has run (interval too long); buffer holds the row.
    assert len(recorder.detection_data) == 1

    recorder.stop_recording(force_stop=True)

    assert recorder._flush_thread is None
    assert recorder.detection_data == []  # cleared by force_stop branch
    base = os.path.basename(output)
    parquet_path = Path(output) / f"3_CoordMovimento_{base}.parquet"
    assert not parquet_path.exists(), "force_stop must not produce a Parquet file"


def test_threshold_cross_signals_flush_thread_off_caller_thread(
    recorder_setup,
) -> None:
    """Crossing the row threshold must signal the flush thread, not
    block the caller. The flush itself happens on the dedicated thread.
    """
    recorder, output = recorder_setup
    recorder._flush_row_threshold = 1
    recorder._flush_interval_seconds = 9999.0  # disable timeout-driven flush

    recorder.start_recording(output, 640, 480, zones=ZoneData(), is_video_file=True)
    caller_thread = threading.get_ident()

    recorder.write_detection_data(0.0, 1, [(0, 0, 10, 10, 0.9, 1)])

    # Buffer drains on the dedicated thread, not the caller's.
    assert _wait(lambda: recorder.detection_data == [], timeout=2.0)
    assert recorder._flush_thread is not None
    assert recorder._flush_thread.ident != caller_thread

    recorder.stop_recording()


def test_synchronous_fallback_when_no_flush_thread() -> None:
    """When ``_flush_thread`` is missing (e.g. tests that bypass
    start_recording or external callers), ``write_detection_data``
    must keep working with the legacy synchronous flush."""
    recorder = Recorder()
    recorder._flush_row_threshold = 1
    recorder._flush_interval_seconds = 0.0
    recorder.is_recording = True
    recorder._parquet_filename = ""  # synchronous path is exercised; no real I/O assertion needed
    recorder._initial_schema_columns = None

    # No thread spawned → fallback path appends and tries to flush.
    # We patch _flush_detection_data to verify it IS called.
    called = {"sync": 0}
    real = recorder._flush_detection_data

    def spy(*args, **kwargs):
        called["sync"] += 1
        # Don't actually flush to disk for this unit test.
        with recorder._data_lock:
            recorder.detection_data.clear()

    recorder._flush_detection_data = spy  # type: ignore[method-assign]
    try:
        recorder.write_detection_data(0.0, 1, [(0, 0, 10, 10, 0.9, 1)])
    finally:
        recorder._flush_detection_data = real  # type: ignore[method-assign]

    assert called["sync"] == 1
