"""Tests for ``StartRecordingDialog`` (live session start: day/group/subject + camera).

A6-04: the "Trocar..." button asks the injected ``camera_provider`` for the
current camera list. The provider enumerates hardware (up to 3 s per index), so
the dialog calls it on a background worker and opens the chooser on Tk.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

from tests.utils.deferring_tk import bind_deferring_tk

from zebtrack.ui.dialogs.start_recording_dialog import StartRecordingDialog


def _dialog(provider):
    dialog = cast(Any, StartRecordingDialog.__new__(StartRecordingDialog))
    dialog.camera_provider = provider
    dialog.pm = SimpleNamespace(project_data={"camera_index": 2, "camera_friendly_name": "Rig"})
    dialog._camera_detection_pending = False
    dialog._camera_index_override = None
    dialog._camera_friendly_name_override = None
    dialog._camera_label = MagicMock()
    opened: list = []
    dialog._show_camera_chooser = lambda cams: opened.append((cams, threading.current_thread()))
    return dialog, bind_deferring_tk(dialog), opened


def test_camera_provider_runs_off_tk_and_the_chooser_opens_on_tk():
    provider_threads: list = []
    cameras = [{"index": 0, "description": "Webcam"}]

    def provider():
        provider_threads.append(threading.current_thread())
        return cameras

    dialog, tk_loop, opened = _dialog(provider)
    dialog._open_camera_chooser()

    assert opened == []
    dialog._camera_label.config.assert_called_once_with(text="Detecting...")

    tk_loop.run_until_idle()

    assert len(provider_threads) == 1
    assert provider_threads[0] is not threading.main_thread()
    assert opened == [(cameras, threading.main_thread())]
    # The label goes back to the project camera once detection settles.
    dialog._camera_label.config.assert_called_with(text="Rig (index 2)")


def test_second_click_while_detecting_does_not_start_another_scan():
    release = threading.Event()
    calls: list = []

    def provider():
        calls.append(1)
        release.wait(5)
        return []

    dialog, tk_loop, opened = _dialog(provider)
    dialog._open_camera_chooser()
    dialog._open_camera_chooser()
    release.set()
    with patch("zebtrack.ui.dialogs.start_recording_dialog.messagebox.showwarning"):
        tk_loop.run_until_idle()

    assert calls == [1]
    assert opened == [([], threading.main_thread())]
    assert dialog._camera_detection_pending is False


def test_provider_failure_shows_the_error_on_tk():
    errors: list = []

    def provider():
        raise OSError("no dshow")

    dialog, tk_loop, opened = _dialog(provider)
    with patch(
        "zebtrack.ui.dialogs.start_recording_dialog.messagebox.showerror",
        side_effect=lambda *a, **k: errors.append((a, threading.current_thread())),
    ):
        dialog._open_camera_chooser()
        tk_loop.run_until_idle()

    assert opened == []
    assert len(errors) == 1
    (title, message), thread = errors[0]
    assert title == "Detection failed"
    assert "no dshow" in message
    assert thread is threading.main_thread()


def test_no_provider_means_no_detection():
    dialog, tk_loop, opened = _dialog(None)
    dialog._open_camera_chooser()

    assert tk_loop.pending == []
    assert opened == []
    dialog._camera_label.config.assert_not_called()
