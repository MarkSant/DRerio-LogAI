"""Unit tests for LiveCameraModeSelectionDialog logic."""

from typing import Any, cast
from unittest.mock import Mock

from zebtrack.core.recording.live_camera_mode import LiveCameraMode
from zebtrack.ui.dialogs.live_camera_mode_selection_dialog import (
    LiveCameraModeSelectionDialog,
)


class _DummyVar:
    def __init__(self, value: str) -> None:
        self._value = value

    def get(self) -> str:
        return self._value

    def set(self, value: str) -> None:
        self._value = value


def _build_dialog_stub(selected_mode: LiveCameraMode) -> LiveCameraModeSelectionDialog:
    dialog = cast(Any, LiveCameraModeSelectionDialog.__new__(LiveCameraModeSelectionDialog))
    dialog.mode_var = _DummyVar(selected_mode.name)
    dialog.selected_mode = None
    dialog.on_mode_selected = Mock()
    dialog.destroy = Mock()
    return cast(LiveCameraModeSelectionDialog, dialog)


def test_mode_display_name_defaults_to_enum_name():
    dialog = LiveCameraModeSelectionDialog.__new__(LiveCameraModeSelectionDialog)

    display_name = dialog._mode_display_name(LiveCameraMode.RECORD_ONLY)

    assert display_name == "Apenas Gravação"


def test_on_confirm_sets_mode_and_invokes_callback():
    dialog = _build_dialog_stub(LiveCameraMode.SEQUENTIAL_AQUARIUM)

    dialog._on_confirm()

    assert dialog.selected_mode == LiveCameraMode.SEQUENTIAL_AQUARIUM
    cast(Mock, dialog.on_mode_selected).assert_called_once_with(LiveCameraMode.SEQUENTIAL_AQUARIUM)
    cast(Mock, dialog.destroy).assert_called_once()


def test_on_cancel_clears_selection_and_closes():
    dialog = _build_dialog_stub(LiveCameraMode.SINGLE_AQUARIUM_REALTIME)
    dialog.selected_mode = LiveCameraMode.SINGLE_AQUARIUM_REALTIME

    dialog._on_cancel()

    assert dialog.selected_mode is None
    cast(Mock, dialog.destroy).assert_called_once()


def test_on_mode_changed_reads_current_selection():
    dialog = _build_dialog_stub(LiveCameraMode.MULTI_AQUARIUM_REALTIME)

    dialog._on_mode_changed()

    assert dialog.mode_var.get() == LiveCameraMode.MULTI_AQUARIUM_REALTIME.name
