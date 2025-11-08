"""
Simplified test to verify LiveConfigDialog works with new camera dropdown.
"""

from unittest.mock import patch

import pytest

from zebtrack.ui.dialogs.live_config_dialog import LiveConfigDialog


@pytest.mark.gui
def test_live_config_dialog_with_camera_dropdown(tkinter_root):
    """Test that LiveConfigDialog works with the new combobox camera selection."""

    # Mock WizardService to return camera list
    with patch(
        "zebtrack.core.wizard_service.WizardService.detect_available_cameras"
    ) as mock_detect:
        mock_detect.return_value = [
            {
                "index": 0,
                "width": 1920,
                "height": 1080,
                "fps": 30.0,
                "description": "720p HD Camera",
            },
            {
                "index": 1,
                "width": 640,
                "height": 480,
                "fps": 30.0,
                "description": "Logi C270 HD WebCam",
            },
        ]

        # Mock Arduino detection
        with patch(
            "zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports"
        ) as mock_arduino:
            mock_arduino.return_value = ([], [])

            # Mock wait_window to prevent blocking
            with patch.object(LiveConfigDialog, "wait_window"):
                dialog = LiveConfigDialog(tkinter_root)
                tkinter_root.update_idletasks()

                # Verify cameras detected and added to dict
                assert len(dialog.available_cameras) == 2
                assert "720p HD Camera" in dialog.available_cameras
                assert "Logi C270 HD WebCam" in dialog.available_cameras

                # Verify combobox created and populated
                assert hasattr(dialog, "camera_combo")
                assert dialog.camera_combo["values"] == ("720p HD Camera", "Logi C270 HD WebCam")

                # Verify first camera selected by default
                assert dialog.camera_var.get() == "720p HD Camera"


@pytest.mark.gui
def test_live_config_dialog_refresh_cameras(tkinter_root):
    """Test that refresh cameras button works."""

    # Initial detection returns 1 camera
    initial_cameras = [
        {"index": 0, "width": 1920, "height": 1080, "fps": 30.0, "description": "Camera 0"},
    ]

    # After refresh, returns 2 cameras
    refreshed_cameras = [
        {"index": 0, "width": 1920, "height": 1080, "fps": 30.0, "description": "720p HD Camera"},
        {"index": 1, "width": 640, "height": 480, "fps": 30.0, "description": "Logi C270"},
    ]

    with patch(
        "zebtrack.core.wizard_service.WizardService.detect_available_cameras"
    ) as mock_detect:
        mock_detect.return_value = initial_cameras

        with patch(
            "zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports"
        ) as mock_arduino:
            mock_arduino.return_value = ([], [])

            with patch.object(LiveConfigDialog, "wait_window"):
                dialog = LiveConfigDialog(tkinter_root)
                tkinter_root.update_idletasks()

                # Initial state
                assert len(dialog.available_cameras) == 1

                # Mock refresh to return different cameras
                mock_detect.return_value = refreshed_cameras
                dialog._refresh_cameras()
                tkinter_root.update_idletasks()

                # Should have updated camera list
                assert len(dialog.available_cameras) == 2
                assert "720p HD Camera" in dialog.available_cameras
                assert "Logi C270" in dialog.available_cameras
