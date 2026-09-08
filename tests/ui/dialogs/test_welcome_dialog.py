"""Tests for the getting-started window.

The window is informational, which is exactly why the interesting assertions
are about what it must NOT do: it must not persist anything unless asked, must
not write the whole settings tree when it does, and must not take the
application down when hardware detection or Tk misbehaves.
"""

from unittest.mock import MagicMock, patch

import pytest

from zebtrack.ui.dialogs.welcome_dialog import (
    WelcomeDialog,
    _hardware_advice,
    should_show_welcome,
)

pytestmark = pytest.mark.gui


class TestShouldShowWelcome:
    """The gate that decides whether the window appears at startup."""

    def test_true_when_the_setting_is_enabled(self):
        settings = MagicMock()
        settings.ui.show_welcome = True

        assert should_show_welcome(settings) is True

    def test_false_when_the_setting_is_disabled(self):
        settings = MagicMock()
        settings.ui.show_welcome = False

        assert should_show_welcome(settings) is False

    def test_false_when_settings_have_no_ui_section(self):
        settings = MagicMock()
        settings.ui = None

        assert should_show_welcome(settings) is False

    def test_a_bare_mock_does_not_count_as_enabled(self):
        """A MagicMock answers every attribute truthily.

        Trusting ``getattr`` here would pop a modal window over the main window
        in any test or embedding that passes a stub settings object.
        """
        assert should_show_welcome(MagicMock()) is False

    def test_a_truthy_non_boolean_does_not_count_as_enabled(self):
        settings = MagicMock()
        settings.ui.show_welcome = "yes"

        assert should_show_welcome(settings) is False


class TestHardwareAdvice:
    """The OpenVINO guidance is read off the machine, not written in general."""

    def test_nvidia_machine_is_told_to_leave_openvino_off(self):
        summary = {"cuda_available": True, "openvino_available": True, "openvino_devices": ["CPU"]}
        with patch("zebtrack.utils.hardware_detection.get_hardware_summary", return_value=summary):
            headline, detail = _hardware_advice()

        assert "NVIDIA" in headline
        assert "CUDA" in detail

    def test_intel_machine_is_told_openvino_is_the_fast_path(self):
        summary = {
            "cuda_available": False,
            "openvino_available": True,
            "openvino_devices": ["CPU", "GPU", "NPU"],
        }
        with patch("zebtrack.utils.hardware_detection.get_hardware_summary", return_value=summary):
            headline, detail = _hardware_advice()

        assert "OpenVINO" in headline
        assert "NPU" in detail, "the detected devices should be named, not described abstractly"

    def test_machine_with_no_acceleration_is_told_so(self):
        summary = {"cuda_available": False, "openvino_available": False, "openvino_devices": []}
        with patch("zebtrack.utils.hardware_detection.get_hardware_summary", return_value=summary):
            headline, _detail = _hardware_advice()

        assert "acceleration" in headline.lower()

    def test_detection_failure_degrades_to_generic_advice(self):
        """Hardware probing touches optional native libraries; it can throw."""
        with patch(
            "zebtrack.utils.hardware_detection.get_hardware_summary",
            side_effect=RuntimeError("openvino exploded"),
        ):
            headline, detail = _hardware_advice()

        assert headline
        assert "OpenVINO" in detail


class TestWelcomeDialogBehaviour:
    """Driving the real widget, on a real Toplevel."""

    def test_closing_without_the_checkbox_persists_nothing(self, tkinter_root):
        dialog = WelcomeDialog(tkinter_root)

        with patch("zebtrack.settings.write_local_override") as write:
            dialog._close()

        write.assert_not_called()

    def test_checking_the_box_writes_only_that_one_key(self, tkinter_root):
        """Never ``save_settings``.

        ``save_settings`` dumps the whole resolved tree into config.local.yaml,
        which freezes every current default and permanently defeats the layered
        config.yaml -> config.local.yaml merge for that installation.
        """
        dialog = WelcomeDialog(tkinter_root)
        dialog.dont_show_again.set(True)

        with patch("zebtrack.settings.write_local_override") as write:
            dialog._close()

        write.assert_called_once_with({"ui": {"show_welcome": False}})

    def test_a_failed_write_does_not_propagate(self, tkinter_root):
        """Showing the window again next launch beats taking the app down."""
        dialog = WelcomeDialog(tkinter_root)
        dialog.dont_show_again.set(True)

        with patch(
            "zebtrack.settings.write_local_override",
            side_effect=OSError("read-only filesystem"),
        ):
            dialog._close()  # must not raise

    def test_opening_model_settings_invokes_the_callback(self, tkinter_root):
        callback = MagicMock()
        dialog = WelcomeDialog(tkinter_root, on_open_model_settings=callback)

        dialog._open_model_settings()

        callback.assert_called_once_with()
        assert dialog.opened_model_settings is True

    def test_the_callback_runs_after_the_window_is_gone(self, tkinter_root):
        """The panel must not open while this window still holds the grab."""
        seen: dict[str, bool] = {}

        def callback():
            seen["window_exists"] = bool(dialog.window.winfo_exists())

        dialog = WelcomeDialog(tkinter_root, on_open_model_settings=callback)
        dialog._open_model_settings()

        assert seen["window_exists"] is False

    def test_dismissing_with_the_box_ticked_still_persists(self, tkinter_root):
        """Escape and the window's X go through the same path as "Not now"."""
        dialog = WelcomeDialog(tkinter_root)
        dialog.dont_show_again.set(True)

        with patch("zebtrack.settings.write_local_override") as write:
            dialog._close()

        assert write.call_count == 1
