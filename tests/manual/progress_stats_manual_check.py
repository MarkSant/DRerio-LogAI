#!/usr/bin/env python3
"""Manual checks for progress statistics integration."""
from pathlib import Path
import sys
import time
import tkinter as tk
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from zebtrack.ui.gui import ApplicationGUI  # noqa: E402  pylint: disable=wrong-import-position


def test_update_processing_stats() -> None:
    """Ensure update_processing_stats populates GUI labels."""
    print("Testing update_processing_stats method...")
    root = tk.Tk()
    root.withdraw()
    mock_controller = MagicMock()
    gui = ApplicationGUI(root, mock_controller)
    gui._build_progress_frame()  # type: ignore[attr-defined]

    start_time = time.time() - 10
    gui.update_processing_stats(
        total_frames=1000,
        processed_frames=250,
        detected_frames=180,
        start_time=start_time,
    )

    assert gui.progress_labels["total"].get() == "1000"
    assert gui.progress_labels["processed"].get() == "250"
    assert gui.progress_labels["detected"].get() == "180"

    percent_val = gui.progress_labels["percent"].get()
    assert percent_val == "25.0%"

    elapsed_val = gui.progress_labels["elapsed"].get()
    assert elapsed_val != "-"
    eta_val = gui.progress_labels["eta"].get()
    assert eta_val != "-"

    print(f"Elapsed time: {elapsed_val}")
    print(f"ETA: {eta_val}")
    print("✅ update_processing_stats test passed!")
    root.destroy()


def test_progress_callback_signature() -> None:
    """Validate callback signature with statistics payload."""
    print("Testing progress callback with stats parameter...")
    mock_view = MagicMock()

    stats = {
        "total_frames": 500,
        "processed_frames": 100,
        "detected_frames": 80,
        "start_time": time.time() - 5,
    }

    def test_progress_callback(progress_fraction, status_message, frame=None, stats=None):
        del progress_fraction, status_message, frame
        if stats:
            mock_view.update_processing_stats(
                total_frames=stats.get("total_frames"),
                processed_frames=stats.get("processed_frames"),
                detected_frames=stats.get("detected_frames"),
                start_time=stats.get("start_time"),
            )
        return True

    result = test_progress_callback(0.2, "Processing...", None, stats)
    assert result is True
    mock_view.update_processing_stats.assert_called_once_with(
        total_frames=500,
        processed_frames=100,
        detected_frames=80,
        start_time=stats["start_time"],
    )
    print("✅ Progress callback signature test passed!")


if __name__ == "__main__":
    print("Running progress statistics manual checks...")
    print("=" * 50)
    test_update_processing_stats()
    test_progress_callback_signature()
    print("=" * 50)
    print("✅ All manual checks passed!")
