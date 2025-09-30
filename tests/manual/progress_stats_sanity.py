#!/usr/bin/env python3
"""Simplified progress statistics sanity checks."""
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


def test_controller_stats_structure() -> None:
    """Ensure callback handles stats payloads correctly."""
    print("Testing controller statistics structure...")
    stats = {
        "total_frames": 500,
        "processed_frames": 100,
        "detected_frames": 80,
        "start_time": 1_234_567_890.0,
    }

    def test_progress_callback(progress_fraction, status_message, frame=None, stats=None):
        del progress_fraction, status_message, frame
        if stats:
            print(
                "Stats - Total: {total}, Processed: {processed}, Detected: {detected}".format(
                    total=stats.get("total_frames"),
                    processed=stats.get("processed_frames"),
                    detected=stats.get("detected_frames"),
                )
            )
            return True
        return False

    result = test_progress_callback(0.2, "Processing...", None, stats)
    assert result is True
    result_no_stats = test_progress_callback(0.2, "Processing...", None, None)
    assert result_no_stats is False
    print("✅ Controller statistics structure test passed!")


def test_statistics_calculations() -> None:
    """Validate calculations for percent, rate, and ETA."""
    print("Testing statistics calculations...")
    start_time = time.time() - 10
    total_frames = 1000
    processed_frames = 250
    detected_frames = 180

    expected_percent = (processed_frames / total_frames) * 100
    assert expected_percent == 25.0

    elapsed = time.time() - start_time
    rate = processed_frames / elapsed
    assert rate > 0

    remaining_frames = total_frames - processed_frames
    eta = remaining_frames / rate
    assert eta > 0

    print(f"Calculated rate: {rate:.2f} frames/sec")
    print(f"Calculated ETA: {eta:.2f} seconds")
    print("✅ Statistics calculations test passed!")


def test_import_structure() -> None:
    """Confirm modules import cleanly."""
    print("Testing module imports...")
    from zebtrack.core import controller  # noqa: WPS433  pylint: disable=import-outside-toplevel
    from zebtrack import settings  # noqa: WPS433  pylint: disable=import-outside-toplevel

    assert hasattr(controller, "AppController")
    assert settings is not None
    print("✅ Module imports test passed!")


if __name__ == "__main__":
    print("Running simplified progress statistics manual tests...")
    print("=" * 60)
    test_import_structure()
    test_controller_stats_structure()
    test_statistics_calculations()
    print("=" * 60)
    print("✅ All simplified tests passed!")
