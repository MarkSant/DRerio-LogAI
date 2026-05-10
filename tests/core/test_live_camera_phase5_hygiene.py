"""Phase 5 hygiene tests for the live pipeline.

Covers:
* M3 — preview-window status updates from worker threads must be
  marshalled through ``root.after(0, ...)``.
* M5 — ``stop_session`` joins worker threads with a bounded total
  budget instead of paying the per-thread timeout sequentially.
* B2 — accumulated video drops surface to the UI as a status event.
"""

from __future__ import annotations

import time
from threading import Event, Thread
from unittest.mock import Mock

import pytest

from zebtrack.core.recording.live_camera_service import LiveCameraService


@pytest.fixture
def live_camera_service() -> LiveCameraService:
    return LiveCameraService(
        controller=None,
        state_manager=Mock(),
        project_manager=Mock(),
        recording_service=Mock(),
        detector_service=Mock(),
        settings_obj=Mock(),
        recorder=Mock(),
        event_bus=Mock(),
        root=None,
    )


# ---------------------------------------------------------------------------
# M3 — preview status bounce through root.after
# ---------------------------------------------------------------------------


def test_post_preview_status_uses_root_after_when_available(
    live_camera_service: LiveCameraService,
) -> None:
    preview = Mock()
    root = Mock()
    live_camera_service.preview_window = preview
    live_camera_service.root = root

    live_camera_service._post_preview_status("hello", color="red")

    root.after.assert_called_once_with(0, preview.update_status_text, "hello", "red")
    # Update happens via root.after, NOT directly on the worker thread.
    preview.update_status_text.assert_not_called()


def test_post_preview_status_falls_back_when_no_root(
    live_camera_service: LiveCameraService,
) -> None:
    preview = Mock()
    live_camera_service.preview_window = preview
    live_camera_service.root = None

    live_camera_service._post_preview_status("hello", color="red")

    preview.update_status_text.assert_called_once_with("hello", "red")


def test_post_preview_status_noop_without_preview(
    live_camera_service: LiveCameraService,
) -> None:
    live_camera_service.preview_window = None
    live_camera_service.root = Mock()

    # Must not raise even though there is nothing to update.
    live_camera_service._post_preview_status("hi")

    live_camera_service.root.after.assert_not_called()


# ---------------------------------------------------------------------------
# B2 — video-drop status surfaces via UI event
# ---------------------------------------------------------------------------


def test_publish_video_drop_status_emits_status_event(
    live_camera_service: LiveCameraService,
) -> None:
    bus = Mock()
    live_camera_service.event_bus = bus
    live_camera_service._dropped_frames_video = 7

    live_camera_service._publish_video_drop_status()

    assert bus.publish.call_count == 1
    event = bus.publish.call_args.args[0]
    # The payload is a StatusPayload — we just sanity-check the message
    # carries the drop count and a hint about the disk.
    payload = event.data
    assert "7" in payload.message
    assert "verifique" in payload.message.lower()


def test_publish_video_drop_status_silent_without_event_bus(
    live_camera_service: LiveCameraService,
) -> None:
    live_camera_service.event_bus = None
    live_camera_service._dropped_frames_video = 3

    # Must not raise.
    live_camera_service._publish_video_drop_status()


# ---------------------------------------------------------------------------
# M5 — stop_session joins with bounded total timeout
# ---------------------------------------------------------------------------


def _stuck_thread() -> Thread:
    """Spawn a daemon thread that never exits within the test window."""
    halt = Event()
    t = Thread(target=halt.wait, daemon=True)
    t.start()
    return t


def test_stop_session_bounded_total_join_budget(
    live_camera_service: LiveCameraService,
) -> None:
    """Even when every worker thread blocks, ``stop_session`` must
    return well within the per-thread timeout x N upper bound. The new
    parallel-friendly join caps the *total* wait, not the sum.
    """
    live_camera_service.capture_thread = _stuck_thread()
    live_camera_service.processing_thread = _stuck_thread()
    live_camera_service.video_recording_thread = _stuck_thread()
    # Avoid touching real IO during stop:
    live_camera_service.recorder = None
    live_camera_service.camera = None
    live_camera_service.preview_window = None
    live_camera_service.event_bus = None
    live_camera_service.root = None
    live_camera_service.timer_id = None

    started = time.monotonic()
    live_camera_service.stop_session()
    elapsed = time.monotonic() - started

    # Sequential 5 s/thread would have cost ~15 s. The bounded budget
    # is 5 s; we leave generous headroom for slow CI hosts.
    assert elapsed < 8.0, f"stop_session exceeded total join budget: {elapsed:.1f}s"
