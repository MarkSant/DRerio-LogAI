"""
Tests for LiveAnalysisDialog and LivePreviewWindow.

These tests cover the UI components for live camera analysis (v2.0 feature):
- LiveAnalysisDialog: Configuration dialog for live analysis sessions
- LivePreviewWindow: Real-time preview window with detection overlays
"""

import time
from unittest.mock import Mock, patch

import numpy as np
import pytest

from tests.utils.wait_helpers import wait_for_condition
from zebtrack.ui.dialogs.live_analysis_dialog import LiveAnalysisDialog
from zebtrack.ui.dialogs.live_preview_window import LivePreviewWindow


@pytest.fixture(autouse=True)
def prevent_dialog_blocking():
    """Prevent dialogs from blocking by patching wait_window and withdraw."""
    with (
        patch("tkinter.simpledialog.Dialog.wait_window"),
        patch("tkinter.Toplevel.withdraw"),
        patch("tkinter.Toplevel.deiconify"),
        patch("tkinter.Toplevel.wait_window"),
        patch("tkinter.messagebox.showinfo"),
        patch("tkinter.messagebox.showwarning"),
        patch("tkinter.messagebox.showerror"),
        patch("tkinter.messagebox.askyesno", return_value=True),
        patch("tkinter.messagebox.askokcancel", return_value=True),
    ):
        yield


def process_tk_events(root, iterations=10):
    """Helper to process Tkinter events including after() callbacks."""
    for _ in range(iterations):
        root.update()
        root.update_idletasks()


# ==============================================================================
# Tests for LiveAnalysisDialog
# ==============================================================================


@pytest.mark.gui
class TestLiveAnalysisDialog:
    """Tests for LiveAnalysisDialog configuration interface."""

    def test_init_default_values(self, tkinter_root, test_settings):
        """Test initialization with default values from settings."""
        with patch.object(LiveAnalysisDialog, "wait_window"):
            with patch(
                "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras"
            ) as mock_detect:
                mock_detect.return_value = []

                dialog = LiveAnalysisDialog(tkinter_root, settings_obj=test_settings)
                tkinter_root.update_idletasks()

                # Verify default values from settings
                expected_duration = test_settings.live_analysis.default_duration_s
                assert dialog.duration_var.get() == expected_duration
                assert dialog.analysis_interval_var.get() == 5
                assert dialog.display_interval_var.get() == 5
                assert dialog.record_video_var.get() is True
                assert dialog.experiment_id_var.get() == ""

    def test_init_without_settings(self, tkinter_root):
        """Test initialization without settings object (fallback defaults)."""
        with patch.object(LiveAnalysisDialog, "wait_window"):
            with patch(
                "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras"
            ) as mock_detect:
                mock_detect.return_value = []

                dialog = LiveAnalysisDialog(tkinter_root, settings_obj=None)
                tkinter_root.update_idletasks()

                # Verify fallback defaults
                assert dialog.duration_var.get() == 300.0
                assert dialog.analysis_interval_var.get() == 5

    def test_camera_detection_success(self, tkinter_root, test_settings):
        """Test successful camera detection."""
        mock_cameras = [
            {
                "index": 0,
                "name": "720p HD Camera",
                "resolution": "1920x1080",
            },
            {
                "index": 1,
                "name": "Logi C270",
                "resolution": "640x480",
            },
        ]

        with patch(
            "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras"
        ) as mock_detect:
            mock_detect.return_value = mock_cameras

            dialog = LiveAnalysisDialog(tkinter_root, settings_obj=test_settings)

            # Process the after() callback that calls _detect_cameras
            # Need to process Tk events first to trigger the scheduled callback
            tkinter_root.update_idletasks()
            tkinter_root.update()
            wait_for_condition(lambda: len(dialog.camera_index_map) >= 2, timeout=1.0)

            # Verify camera index map populated
            assert len(dialog.camera_index_map) == 2

            # Verify combobox values
            values = dialog.camera_combo["values"]
            assert len(values) == 2
            assert "[0]" in values[0]
            assert "720p HD Camera" in values[0]

            # Verify first camera auto-selected
            assert dialog.camera_selection_var.get() != ""
            assert dialog.camera_status_label.cget("text") == "✓ 2 câmera(s) detectada(s)"
            assert dialog.camera_status_label.cget("fg") == "green"

    def test_camera_detection_no_cameras(self, tkinter_root, test_settings):
        """Test camera detection when no cameras found."""
        with patch(
            "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras"
        ) as mock_detect:
            mock_detect.return_value = []

            dialog = LiveAnalysisDialog(tkinter_root, settings_obj=test_settings)
            process_tk_events(tkinter_root)

            # Verify empty state
            assert len(dialog.camera_index_map) == 0
            assert len(dialog.camera_combo["values"]) == 0  # Empty tuple or list
            assert dialog.camera_status_label.cget("text") == "✗ Nenhuma câmera detectada"
            assert dialog.camera_status_label.cget("fg") == "red"

    def test_camera_detection_exception(self, tkinter_root, test_settings):
        """Test camera detection error handling."""
        with patch.object(LiveAnalysisDialog, "wait_window"):
            with patch(
                "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras"
            ) as mock_detect:
                mock_detect.side_effect = RuntimeError("Camera access failed")

                # Mock messagebox to prevent blocking
                with patch("zebtrack.ui.dialogs.live_analysis_dialog.messagebox.showerror"):
                    dialog = LiveAnalysisDialog(tkinter_root, settings_obj=test_settings)
                    process_tk_events(tkinter_root)

                    # Verify error state
                    assert dialog.camera_status_label.cget("text") == "✗ Erro ao detectar câmeras"
                    assert dialog.camera_status_label.cget("fg") == "red"

    def test_manual_camera_detection_refresh(self, tkinter_root, test_settings):
        """Test manual camera detection refresh via detect button."""
        initial_cameras = [{"index": 0, "name": "Camera 0", "resolution": "640x480"}]
        refreshed_cameras = [
            {"index": 0, "name": "Camera 0", "resolution": "640x480"},
            {"index": 1, "name": "Camera 1", "resolution": "1920x1080"},
        ]

        with patch.object(LiveAnalysisDialog, "wait_window"):
            with patch(
                "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras"
            ) as mock_detect:
                mock_detect.return_value = initial_cameras

                dialog = LiveAnalysisDialog(tkinter_root, settings_obj=test_settings)
                process_tk_events(tkinter_root)

                # Initial state
                assert len(dialog.camera_index_map) == 1

                # Mock refresh
                mock_detect.return_value = refreshed_cameras
                dialog._detect_cameras()
                process_tk_events(tkinter_root)

                # Verify updated state
                assert len(dialog.camera_index_map) == 2

    def test_validate_no_camera_selected(self, tkinter_root, test_settings):
        """Test validation fails when no camera selected."""
        with patch.object(LiveAnalysisDialog, "wait_window"):
            with patch(
                "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras"
            ) as mock_detect:
                mock_detect.return_value = []

                dialog = LiveAnalysisDialog(tkinter_root, settings_obj=test_settings)
                tkinter_root.update_idletasks()

                # Clear camera selection
                dialog.camera_selection_var.set("")

                # Mock messagebox to prevent blocking
                with patch(
                    "zebtrack.ui.dialogs.live_analysis_dialog.messagebox.showwarning"
                ) as mock_warning:
                    result = dialog.validate()

                    assert result is False
                    mock_warning.assert_called_once()

    def test_validate_invalid_camera_index(self, tkinter_root, test_settings):
        """Test validation fails for invalid camera index."""
        with patch.object(LiveAnalysisDialog, "wait_window"):
            with patch(
                "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras"
            ) as mock_detect:
                mock_detect.return_value = []

                dialog = LiveAnalysisDialog(tkinter_root, settings_obj=test_settings)
                tkinter_root.update_idletasks()

                # Set invalid camera selection
                dialog.camera_selection_var.set("Invalid Camera")

                with patch(
                    "zebtrack.ui.dialogs.live_analysis_dialog.messagebox.showerror"
                ) as mock_error:
                    result = dialog.validate()

                    assert result is False
                    mock_error.assert_called_once()

    def test_duration_validation_positive(self, tkinter_root, test_settings):
        """Test duration validation with valid positive value."""
        mock_cameras = [{"index": 0, "name": "Camera 0", "resolution": "640x480"}]

        with patch.object(LiveAnalysisDialog, "wait_window"):
            with patch(
                "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras"
            ) as mock_detect:
                mock_detect.return_value = mock_cameras

                dialog = LiveAnalysisDialog(tkinter_root, settings_obj=test_settings)
                process_tk_events(tkinter_root)

                # Select camera
                dialog.camera_combo.current(0)

                # Set valid duration
                dialog.duration_var.set(600.0)

                # Should validate successfully
                result = dialog.validate()
                assert result is True

    def test_duration_validation_invalid_zero(self, tkinter_root, test_settings):
        """Test duration validation fails for zero/negative values."""
        mock_cameras = [{"index": 0, "name": "Camera 0", "resolution": "640x480"}]

        with patch.object(LiveAnalysisDialog, "wait_window"):
            with patch(
                "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras"
            ) as mock_detect:
                mock_detect.return_value = mock_cameras

                dialog = LiveAnalysisDialog(tkinter_root, settings_obj=test_settings)
                process_tk_events(tkinter_root)

                # Select camera
                dialog.camera_combo.current(0)

                # Set invalid duration
                dialog.duration_var.set(0)

                # Should fail validation (showerror already mocked globally)
                result = dialog.validate()
                assert result is False

    def test_duration_validation_max_exceeded(self, tkinter_root, test_settings):
        """Test duration validation with value exceeding max."""
        mock_cameras = [{"index": 0, "name": "Camera 0", "resolution": "640x480"}]

        with patch.object(LiveAnalysisDialog, "wait_window"):
            with patch(
                "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras"
            ) as mock_detect:
                mock_detect.return_value = mock_cameras

                dialog = LiveAnalysisDialog(tkinter_root, settings_obj=test_settings)
                process_tk_events(tkinter_root)

                # Select camera
                dialog.camera_combo.current(0)

                # Set duration exceeding max
                max_duration = test_settings.live_analysis.max_duration_s
                dialog.duration_var.set(max_duration + 1000)

                # Should still validate but adjust to max (showwarning already mocked)
                result = dialog.validate()
                assert result is True
                assert dialog.duration_var.get() == max_duration

    def test_analysis_interval_validation_invalid(self, tkinter_root, test_settings):
        """Test analysis interval validation with invalid value."""
        mock_cameras = [{"index": 0, "name": "Camera 0", "resolution": "640x480"}]

        with patch.object(LiveAnalysisDialog, "wait_window"):
            with patch(
                "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras"
            ) as mock_detect:
                mock_detect.return_value = mock_cameras

                dialog = LiveAnalysisDialog(tkinter_root, settings_obj=test_settings)
                process_tk_events(tkinter_root)

                # Select camera
                dialog.camera_combo.current(0)

                # Set invalid interval
                dialog.analysis_interval_var.set(0)

                # Should fail validation (showerror already mocked)
                result = dialog.validate()
                assert result is False

    def test_display_interval_validation_invalid(self, tkinter_root, test_settings):
        """Test display interval validation with invalid value."""
        mock_cameras = [{"index": 0, "name": "Camera 0", "resolution": "640x480"}]

        with patch.object(LiveAnalysisDialog, "wait_window"):
            with patch(
                "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras"
            ) as mock_detect:
                mock_detect.return_value = mock_cameras

                dialog = LiveAnalysisDialog(tkinter_root, settings_obj=test_settings)
                process_tk_events(tkinter_root)

                # Select camera
                dialog.camera_combo.current(0)

                # Set invalid interval
                dialog.display_interval_var.set(-5)

                # Should fail validation (showerror already mocked)
                result = dialog.validate()
                assert result is False

    def test_record_video_checkbox_state(self, tkinter_root, test_settings):
        """Test record video checkbox state changes."""
        with patch.object(LiveAnalysisDialog, "wait_window"):
            with patch(
                "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras"
            ) as mock_detect:
                mock_detect.return_value = []

                dialog = LiveAnalysisDialog(tkinter_root, settings_obj=test_settings)
                tkinter_root.update_idletasks()

                # Initial state
                assert dialog.record_video_var.get() is True

                # Toggle
                dialog.record_video_var.set(False)
                assert dialog.record_video_var.get() is False

    def test_experiment_id_auto_generation(self, tkinter_root, test_settings):
        """Test automatic experiment ID generation when not provided."""
        mock_cameras = [{"index": 0, "name": "Camera 0", "resolution": "640x480"}]

        with patch.object(LiveAnalysisDialog, "wait_window"):
            with patch(
                "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras"
            ) as mock_detect:
                mock_detect.return_value = mock_cameras

                dialog = LiveAnalysisDialog(tkinter_root, settings_obj=test_settings)
                process_tk_events(tkinter_root)

                # Select camera
                dialog.camera_combo.current(0)

                # Leave experiment ID empty
                dialog.experiment_id_var.set("")

                # Call apply to generate ID
                dialog.apply()

                # Verify auto-generated ID
                assert dialog.result is not None
                assert dialog.result["experiment_id"].startswith("camera_")
                assert len(dialog.result["experiment_id"]) > len("camera_")

    def test_experiment_id_custom(self, tkinter_root, test_settings):
        """Test custom experiment ID is preserved."""
        mock_cameras = [{"index": 0, "name": "Camera 0", "resolution": "640x480"}]

        with patch.object(LiveAnalysisDialog, "wait_window"):
            with patch(
                "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras"
            ) as mock_detect:
                mock_detect.return_value = mock_cameras

                dialog = LiveAnalysisDialog(tkinter_root, settings_obj=test_settings)
                process_tk_events(tkinter_root)

                # Select camera
                dialog.camera_combo.current(0)

                # Set custom ID
                custom_id = "my_experiment_001"
                dialog.experiment_id_var.set(custom_id)

                # Call apply
                dialog.apply()

                # Verify custom ID preserved
                assert dialog.result is not None
                assert dialog.result["experiment_id"] == custom_id

    def test_ok_button_result_assembly(self, tkinter_root, test_settings):
        """Test OK button assembles result dictionary correctly."""
        mock_cameras = [{"index": 1, "name": "Test Camera", "resolution": "1920x1080"}]

        with patch.object(LiveAnalysisDialog, "wait_window"):
            with patch(
                "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras"
            ) as mock_detect:
                mock_detect.return_value = mock_cameras

                dialog = LiveAnalysisDialog(tkinter_root, settings_obj=test_settings)

                # Process events to trigger camera detection callback
                tkinter_root.update_idletasks()
                tkinter_root.update()
                wait_for_condition(lambda: len(dialog.camera_index_map) >= 1, timeout=1.0)

                # Select camera
                dialog.camera_combo.current(0)

                # Set values
                dialog.duration_var.set(600.0)
                dialog.analysis_interval_var.set(5)
                dialog.display_interval_var.set(10)
                dialog.record_video_var.set(False)
                dialog.experiment_id_var.set("test_exp")

                # Call apply
                dialog.apply()

                # Verify result structure
                assert dialog.result is not None
                assert dialog.result["camera_index"] == 1
                assert dialog.result["duration_s"] == 600.0
                assert dialog.result["analysis_interval_frames"] == 5
                assert dialog.result["display_interval_frames"] == 10
                assert dialog.result["record_video"] is False
                assert dialog.result["experiment_id"] == "test_exp"

    def test_quick_duration_buttons(self, tkinter_root, test_settings):
        """Test quick duration preset buttons."""
        with patch.object(LiveAnalysisDialog, "wait_window"):
            with patch(
                "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras"
            ) as mock_detect:
                mock_detect.return_value = []

                dialog = LiveAnalysisDialog(tkinter_root, settings_obj=test_settings)
                tkinter_root.update_idletasks()

                # Test 1 min button
                dialog.duration_var.set(60)
                assert dialog.duration_var.get() == 60

                # Test 5 min button
                dialog.duration_var.set(300)
                assert dialog.duration_var.get() == 300

                # Test 10 min button
                dialog.duration_var.set(600)
                assert dialog.duration_var.get() == 600

                # Test 30 min button
                dialog.duration_var.set(1800)
                assert dialog.duration_var.get() == 1800


# ==============================================================================
# Tests for LivePreviewWindow
# ==============================================================================


@pytest.mark.gui
class TestLivePreviewWindow:
    """Tests for LivePreviewWindow real-time display."""

    def test_window_creation(self, tkinter_root):
        """Test window creation and basic layout."""
        callback = Mock()

        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=300.0,
            on_stop_callback=callback,
        )
        tkinter_root.update_idletasks()

        # Verify window created
        assert window.window is not None
        assert window.camera_index == 0
        assert window.duration_s == 300.0
        assert window.on_stop_callback == callback
        assert window.is_stopped is False

        # Verify UI components exist
        assert window.canvas is not None
        assert window.timer_label is not None
        assert window.status_label is not None
        assert window.stop_button is not None

        window.destroy()

    def test_frame_update_no_detections(self, tkinter_root):
        """Test frame update without detections."""
        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=300.0,
        )
        tkinter_root.update_idletasks()

        # Create dummy frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Update frame
        window.update_frame(frame, detections=None)
        tkinter_root.update_idletasks()

        # Verify stats updated
        assert window.frame_count == 1
        assert window.detection_count == 0

        window.destroy()

    def test_frame_update_with_detections(self, tkinter_root):
        """Test frame update with detections."""
        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=300.0,
        )
        tkinter_root.update_idletasks()

        # Create dummy frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Create dummy detections [x1, y1, x2, y2, conf]
        detections = [
            [100, 100, 200, 200, 0.95],
            [300, 150, 400, 250, 0.87],
        ]

        # Update frame
        window.update_frame(frame, detections=detections)
        tkinter_root.update_idletasks()

        # Verify stats updated
        assert window.frame_count == 1
        assert window.detection_count == 2

        window.destroy()

    def test_fps_calculation(self, tkinter_root):
        """Test FPS calculation on frame updates."""
        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=300.0,
        )
        tkinter_root.update_idletasks()

        # Create dummy frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Update multiple frames
        window.update_frame(frame)
        tkinter_root.update_idletasks()
        window.update_frame(frame)
        tkinter_root.update_idletasks()

        # FPS should be calculated (non-zero) after multiple updates
        wait_for_condition(lambda: window.current_fps > 0, timeout=1.0)
        assert window.current_fps > 0

        window.destroy()

    def test_stats_update(self, tkinter_root):
        """Test stats labels update correctly."""
        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=300.0,
        )
        tkinter_root.update_idletasks()

        # Create dummy frame and detections
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        detections = [[100, 100, 200, 200, 0.95]]

        # Update multiple times
        for _ in range(5):
            window.update_frame(frame, detections=detections)
            tkinter_root.update_idletasks()

        # Verify stats
        assert window.frames_label.cget("text") == "5"
        assert window.detections_label.cget("text") == "5"

        window.destroy()

    def test_manual_stop_button(self, tkinter_root):
        """Test manual stop button callback."""
        callback = Mock()

        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=300.0,
            on_stop_callback=callback,
        )
        tkinter_root.update_idletasks()

        # Click stop button
        window._on_stop_clicked()
        tkinter_root.update_idletasks()

        # Verify stopped state
        assert window.is_stopped is True
        assert callback.called is True

        # Verify status updated
        assert "Parado" in window.status_label.cget("text")

        window.destroy()

    def test_auto_stop_on_duration_complete(self, tkinter_root):
        """Test automatic stop when duration expires."""
        callback = Mock()

        # Use very short duration
        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=0.1,  # 100ms
            on_stop_callback=callback,
        )
        tkinter_root.update_idletasks()

        # Start the timer
        window.start_timer()

        # Wait for auto-stop to trigger (process events while waiting)
        def check_stopped_with_events():
            for _ in range(20):  # 20 iterations x ~10ms = ~200ms
                tkinter_root.update()
                tkinter_root.update_idletasks()
                if window.is_stopped:
                    return True
                time.sleep(0.01)  # intentional Tk event loop delay
            return window.is_stopped

        assert check_stopped_with_events() is True

        # Verify auto-stopped
        assert window.is_stopped is True
        assert callback.called is True

        window.destroy()

    def test_stop_callback_invocation(self, tkinter_root):
        """Test stop callback is invoked exactly once."""
        callback = Mock()

        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=300.0,
            on_stop_callback=callback,
        )
        tkinter_root.update_idletasks()

        # Stop multiple times
        window._on_stop_clicked()
        window._on_stop_clicked()
        window._on_stop_clicked()
        tkinter_root.update_idletasks()

        # Callback should only be called once
        assert callback.call_count == 1

        window.destroy()

    def test_window_close_event_triggers_stop(self, tkinter_root):
        """Test window close event triggers stop callback."""
        callback = Mock()

        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=300.0,
            on_stop_callback=callback,
        )
        tkinter_root.update_idletasks()

        # Trigger close
        window._on_window_close()
        tkinter_root.update_idletasks()

        # Verify callback invoked
        assert callback.called is True
        assert window.is_stopped is True

    def test_frame_update_after_stop(self, tkinter_root):
        """Test frame updates are ignored after stop."""
        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=300.0,
        )
        tkinter_root.update_idletasks()

        # Stop window
        window._on_stop_clicked()

        # Try to update frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        initial_count = window.frame_count

        window.update_frame(frame)
        tkinter_root.update_idletasks()

        # Frame count should not increase
        assert window.frame_count == initial_count

        window.destroy()

    def test_timer_updates(self, tkinter_root):
        """Test timer label updates correctly."""
        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=10.0,
        )
        tkinter_root.update_idletasks()

        # Start the timer
        window.start_timer()

        # Manually trigger timer update
        window._update_timer()
        tkinter_root.update_idletasks()

        # Wait for timer label to update
        wait_for_condition(lambda: "Restante:" in window.timer_label.cget("text"), timeout=1.0)

        # Verify timer label contains expected text
        timer_text = window.timer_label.cget("text")
        assert "Tempo:" in timer_text
        assert "Restante:" in timer_text

        window.destroy()

    def test_show_hide_methods(self, tkinter_root):
        """Test show and hide window methods."""
        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=300.0,
        )

        # Show window
        window.show()
        tkinter_root.update_idletasks()

        # Hide window
        window.hide()
        tkinter_root.update_idletasks()

        # Cleanup
        window.destroy()

    def test_destroy_method(self, tkinter_root):
        """Test destroy method stops and cleans up."""
        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=300.0,
        )
        tkinter_root.update_idletasks()

        # Destroy
        window.destroy()

        # Verify stopped
        assert window.is_stopped is True

    # ------------------------------------------------------------------
    # Recording progress widgets (Etapa 5)
    # ------------------------------------------------------------------

    def test_start_timer_renders_clock_in_HHMMSS(self, tkinter_root):
        """Calling start_timer() should populate start_time_label with HH:MM:SS."""
        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=300.0,
        )
        tkinter_root.update_idletasks()

        assert window.start_time_label.cget("text") == "--:--:--"

        window.start_timer()
        tkinter_root.update_idletasks()

        text = window.start_time_label.cget("text")
        assert text.startswith("Início:")
        # The clock part is the suffix after "Início: " — should match HH:MM:SS
        clock = text.replace("Início:", "").strip()
        assert len(clock.split(":")) == 3
        h, m, s = clock.split(":")
        assert h.isdigit() and m.isdigit() and s.isdigit()

        window.destroy()

    def test_update_frame_with_recorded_count_writes_recorded_label(self, tkinter_root):
        """recorded_count kwarg flows into the 'Frames gravados' label."""
        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=300.0,
        )
        tkinter_root.update_idletasks()

        assert window.recorded_frames_label.cget("text") == "0"

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        window.update_frame(frame, detections=None, recorded_count=42)
        tkinter_root.update_idletasks()

        assert window.recorded_frames_label.cget("text") == "42"

        window.update_frame(frame, detections=None, recorded_count=137)
        tkinter_root.update_idletasks()
        assert window.recorded_frames_label.cget("text") == "137"

        window.destroy()

    def test_update_frame_without_recorded_count_leaves_label_untouched(self, tkinter_root):
        """Backward compatibility: legacy callers that omit recorded_count don't reset it."""
        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=300.0,
        )
        tkinter_root.update_idletasks()

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        window.update_frame(frame, detections=None, recorded_count=99)
        tkinter_root.update_idletasks()
        assert window.recorded_frames_label.cget("text") == "99"

        # Subsequent call without the kwarg must not reset to 0.
        window.update_frame(frame, detections=None)
        tkinter_root.update_idletasks()
        assert window.recorded_frames_label.cget("text") == "99"

        window.destroy()

    def test_progress_bar_set_to_indeterminate_when_no_duration_configured(self, tkinter_root):
        """duration_s <= 0 should configure the progress bar in indeterminate mode."""
        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=0.0,
        )
        tkinter_root.update_idletasks()

        assert str(window.progress_bar.cget("mode")) == "indeterminate"
        # ETA should remain "--" because we cannot compute it.
        window.start_timer()
        window._update_timer()
        tkinter_root.update_idletasks()
        assert window.eta_label.cget("text") == "--"

        window.destroy()

    def test_progress_bar_percent_matches_elapsed_over_duration(self, tkinter_root):
        """_update_progress writes (elapsed / duration) * 100 to the bar."""
        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=10.0,
        )
        tkinter_root.update_idletasks()

        assert str(window.progress_bar.cget("mode")) == "determinate"

        window._update_progress(elapsed=2.5, remaining=7.5)
        tkinter_root.update_idletasks()
        assert window.progress_bar.cget("value") == pytest.approx(25.0)

        window._update_progress(elapsed=9.0, remaining=1.0)
        tkinter_root.update_idletasks()
        assert window.progress_bar.cget("value") == pytest.approx(90.0)

        window.destroy()

    def test_eta_label_shows_remaining_in_humanised_format(self, tkinter_root):
        """ETA label uses 'Xs', 'Xm Ys', or 'Xh Ym Zs' depending on magnitude."""
        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=3700.0,
        )
        tkinter_root.update_idletasks()

        window._update_progress(elapsed=0.0, remaining=45.0)
        assert window.eta_label.cget("text") == "45s"

        window._update_progress(elapsed=0.0, remaining=125.0)
        assert window.eta_label.cget("text") == "2m 05s"

        window._update_progress(elapsed=0.0, remaining=3661.0)
        assert window.eta_label.cget("text") == "1h 01m 01s"

        window.destroy()

    def test_stop_clicked_freezes_stop_time_label(self, tkinter_root):
        """Manual stop should record the wall-clock time into stop_time_label."""
        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=300.0,
        )
        tkinter_root.update_idletasks()

        assert window.stop_time_label.cget("text") == "--:--:--"

        window._on_stop_clicked()
        tkinter_root.update_idletasks()

        text = window.stop_time_label.cget("text")
        # After stop, the label should hold an HH:MM:SS clock (no prefix here).
        assert text != "--:--:--"
        assert len(text.split(":")) == 3

        # Subsequent updates while stopped must not mutate the frozen value.
        frozen = text
        window._on_stop_clicked()  # idempotent
        tkinter_root.update_idletasks()
        assert window.stop_time_label.cget("text") == frozen

        window.destroy()

    def test_auto_stop_also_freezes_stop_time_label(self, tkinter_root):
        """Expiry-driven stop should write stop_time_label exactly like the manual path."""
        window = LivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            duration_s=300.0,
        )
        tkinter_root.update_idletasks()

        window.start_time = time.time() - 1000.0  # force "expired"
        window._update_timer()  # triggers _auto_stop branch
        tkinter_root.update_idletasks()

        assert window.is_stopped is True
        assert window.stop_time_label.cget("text") != "--:--:--"

        window.destroy()

    def test_format_eta_helper_handles_negative_and_zero(self):
        """_format_eta clamps negatives to 0 and renders 0 → '0s'."""
        assert LivePreviewWindow._format_eta(0) == "0s"
        assert LivePreviewWindow._format_eta(-5) == "0s"
        assert LivePreviewWindow._format_eta(59) == "59s"
        assert LivePreviewWindow._format_eta(60) == "1m 00s"
