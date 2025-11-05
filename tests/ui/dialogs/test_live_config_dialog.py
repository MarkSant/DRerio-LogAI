"""
Tests for LiveConfigDialog component.

Covers dialog initialization, device detection, validation, and error handling
as required by CLAUDE.md (minimum 70% coverage).

IMPORTANT: All tests mock wait_window() to prevent blocking dialog windows
from appearing during automated testing.
"""

from unittest.mock import MagicMock, patch

import pytest

from zebtrack.ui.dialogs.live_config_dialog import LiveConfigDialog


@pytest.mark.gui
class TestLiveConfigDialog:
    """Test suite for LiveConfigDialog component."""

    @pytest.fixture(autouse=True)
    def mock_wait_window(self):
        """Auto-mock wait_window to prevent dialogs from blocking tests."""
        with patch.object(LiveConfigDialog, "wait_window"):
            yield

    # --- Initialization Tests ---

    @patch("zebtrack.ui.dialogs.live_config_dialog.WizardService.detect_available_cameras")
    @patch("zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports")
    @patch("zebtrack.ui.dialogs.live_config_dialog.serial.tools.list_ports.comports")
    def test_dialog_initialization(
        self, mock_comports, mock_scan_ports, mock_detect_cameras, tkinter_root
    ):
        """Test dialog initializes and detects devices."""
        # Mock camera detection via WizardService
        mock_detect_cameras.return_value = [
            {"index": 0, "width": 1920, "height": 1080, "fps": 30.0, "description": "Camera 0"}
        ]

        # Mock port detection
        mock_port = MagicMock()
        mock_port.device = "COM3"
        mock_port.description = "Arduino Uno"
        mock_scan_ports.return_value = ([mock_port], [])

        # Create dialog (will automatically call body())
        dialog = LiveConfigDialog(tkinter_root)
        tkinter_root.update_idletasks()

        # Verify dialog created successfully
        assert dialog is not None
        assert hasattr(dialog, "available_cameras")
        assert hasattr(dialog, "available_ports")

    @patch("zebtrack.ui.dialogs.live_config_dialog.WizardService.detect_available_cameras")
    @patch("zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports")
    def test_camera_detection(self, mock_scan_ports, mock_videocapture, tkinter_root):
        """Test camera detection finds available cameras."""

        # Mock multiple cameras
        def mock_cap_factory(index, *args):
            cap = MagicMock()
            cap.isOpened.return_value = index < 2  # Cameras 0 and 1 available
            cap.release = MagicMock()
            return cap

        mock_videocapture.side_effect = mock_cap_factory
        mock_scan_ports.return_value = ([], [])

        dialog = LiveConfigDialog(tkinter_root)
        tkinter_root.update_idletasks()

        # Should detect cameras 0 and 1
        assert "Câmera 0" in dialog.available_cameras
        assert "Câmera 1" in dialog.available_cameras
        assert len(dialog.available_cameras) == 2

    @patch("zebtrack.ui.dialogs.live_config_dialog.WizardService.detect_available_cameras")
    @patch("zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports")
    def test_no_cameras_detected(self, mock_scan_ports, mock_videocapture, tkinter_root):
        """Test dialog handles no cameras detected."""
        # Mock no cameras available
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_cap.release = MagicMock()
        mock_videocapture.return_value = mock_cap

        mock_scan_ports.return_value = ([], [])

        dialog = LiveConfigDialog(tkinter_root)
        tkinter_root.update_idletasks()

        # Should have empty cameras dict
        assert len(dialog.available_cameras) == 0

    @patch("zebtrack.ui.dialogs.live_config_dialog.WizardService.detect_available_cameras")
    @patch("zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports")
    def test_port_detection_with_handshake(self, mock_scan_ports, mock_videocapture, tkinter_root):
        """Test port detection finds Arduino ports with handshake."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_videocapture.return_value = mock_cap

        # Mock Arduino ports with handshake
        mock_port1 = MagicMock()
        mock_port1.device = "COM3"
        mock_port1.description = "Arduino Uno"

        mock_port2 = MagicMock()
        mock_port2.device = "COM5"
        mock_port2.description = "Arduino Mega"

        mock_scan_ports.return_value = ([mock_port1, mock_port2], [])

        dialog = LiveConfigDialog(tkinter_root)
        tkinter_root.update_idletasks()

        # Should detect both Arduino ports with [Arduino] tag
        assert len(dialog.available_ports) == 2
        # Check that ports are in the dict
        port_values = list(dialog.available_ports.values())
        assert "COM3" in port_values
        assert "COM5" in port_values

    @patch("zebtrack.ui.dialogs.live_config_dialog.WizardService.detect_available_cameras")
    @patch("zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports")
    @patch("zebtrack.ui.dialogs.live_config_dialog.serial.tools.list_ports.comports")
    def test_port_detection_fallback(
        self, mock_comports, mock_scan_ports, mock_videocapture, tkinter_root
    ):
        """Test port detection falls back to raw ports when no handshake."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_videocapture.return_value = mock_cap

        # No handshake ports, but fallback ports available
        mock_port = MagicMock()
        mock_port.device = "COM7"
        mock_port.description = "USB Serial Port"

        mock_scan_ports.return_value = ([], [mock_port])

        dialog = LiveConfigDialog(tkinter_root)
        tkinter_root.update_idletasks()

        # Should include fallback port with [sem handshake] tag
        assert len(dialog.available_ports) >= 1
        port_values = list(dialog.available_ports.values())
        assert "COM7" in port_values

    @patch("zebtrack.ui.dialogs.live_config_dialog.WizardService.detect_available_cameras")
    @patch("zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports")
    @patch("zebtrack.ui.dialogs.live_config_dialog.serial.tools.list_ports.comports")
    def test_no_ports_detected(
        self, mock_comports, mock_scan_ports, mock_videocapture, tkinter_root
    ):
        """Test dialog handles no serial ports detected."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_videocapture.return_value = mock_cap

        mock_scan_ports.return_value = ([], [])
        mock_comports.return_value = []  # No raw ports either

        dialog = LiveConfigDialog(tkinter_root)
        tkinter_root.update_idletasks()

        # Should have empty ports dict
        assert len(dialog.available_ports) == 0

    # --- Validation Tests ---

    @patch("zebtrack.ui.dialogs.live_config_dialog.WizardService.detect_available_cameras")
    @patch("zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports")
    @patch("zebtrack.ui.dialogs.live_config_dialog.messagebox.showerror")
    def test_validate_no_cameras(
        self, mock_showerror, mock_scan_ports, mock_videocapture, tkinter_root
    ):
        """Test validation fails when no cameras detected."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_videocapture.return_value = mock_cap

        mock_scan_ports.return_value = ([], [])

        dialog = LiveConfigDialog(tkinter_root)
        tkinter_root.update_idletasks()

        # Validation should fail
        result = dialog.validate()
        assert result == 0

        # Should show error message
        mock_showerror.assert_called_once()
        assert "Nenhuma câmera" in mock_showerror.call_args[0][1]

    @patch("zebtrack.ui.dialogs.live_config_dialog.WizardService.detect_available_cameras")
    @patch("zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports")
    @patch("zebtrack.ui.dialogs.live_config_dialog.serial.tools.list_ports.comports")
    @patch("zebtrack.ui.dialogs.live_config_dialog.messagebox.showerror")
    def test_validate_arduino_enabled_no_ports(
        self, mock_showerror, mock_scan_ports, mock_comports, mock_videocapture, tkinter_root
    ):
        """Test validation fails when Arduino enabled but no ports."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_videocapture.return_value = mock_cap

        mock_scan_ports.return_value = ([], [])
        mock_comports.return_value = []  # No raw ports either

        dialog = LiveConfigDialog(tkinter_root)
        dialog.use_arduino_var.set(True)
        tkinter_root.update_idletasks()

        # Validation should fail
        result = dialog.validate()
        assert result == 0

        # Should show error about no ports
        mock_showerror.assert_called_once()
        assert "nenhuma porta serial" in mock_showerror.call_args[0][1].lower()

    @patch("zebtrack.ui.dialogs.live_config_dialog.WizardService.detect_available_cameras")
    @patch("zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports")
    def test_validate_success(self, mock_scan_ports, mock_videocapture, tkinter_root):
        """Test validation succeeds with valid configuration."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_videocapture.return_value = mock_cap

        mock_port = MagicMock()
        mock_port.device = "COM3"
        mock_port.description = "Arduino"
        mock_scan_ports.return_value = ([mock_port], [])

        dialog = LiveConfigDialog(tkinter_root)
        tkinter_root.update_idletasks()

        # Validation should succeed
        result = dialog.validate()
        assert result == 1

    # --- Apply Tests ---

    @patch("zebtrack.ui.dialogs.live_config_dialog.WizardService.detect_available_cameras")
    @patch("zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports")
    def test_apply_with_arduino(self, mock_scan_ports, mock_videocapture, tkinter_root):
        """Test apply() creates correct result with Arduino enabled."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_videocapture.return_value = mock_cap

        mock_port = MagicMock()
        mock_port.device = "COM5"
        mock_port.description = "Arduino Mega"
        mock_scan_ports.return_value = ([mock_port], [])

        dialog = LiveConfigDialog(tkinter_root)
        dialog.camera_var.set("Câmera 0")
        dialog.use_arduino_var.set(True)
        tkinter_root.update_idletasks()

        # Apply configuration
        dialog.apply()

        # Verify result
        assert dialog.result is not None
        assert dialog.result["camera_index"] == 0
        assert dialog.result["use_arduino"] is True
        assert dialog.result["arduino_port"] == "COM5"

    @patch("zebtrack.ui.dialogs.live_config_dialog.WizardService.detect_available_cameras")
    @patch("zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports")
    def test_apply_without_arduino(self, mock_scan_ports, mock_videocapture, tkinter_root):
        """Test apply() creates correct result with Arduino disabled."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_videocapture.return_value = mock_cap

        mock_scan_ports.return_value = ([], [])

        dialog = LiveConfigDialog(tkinter_root)
        dialog.camera_var.set("Câmera 1")
        dialog.use_arduino_var.set(False)
        tkinter_root.update_idletasks()

        # Apply configuration
        dialog.apply()

        # Verify result
        assert dialog.result is not None
        assert dialog.result["camera_index"] == 1
        assert dialog.result["use_arduino"] is False
        assert dialog.result["arduino_port"] is None

    # --- UI Interaction Tests ---

    @patch("zebtrack.ui.dialogs.live_config_dialog.WizardService.detect_available_cameras")
    @patch("zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports")
    def test_toggle_arduino_menu(self, mock_scan_ports, mock_videocapture, tkinter_root):
        """Test Arduino menu is enabled/disabled based on checkbox."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_videocapture.return_value = mock_cap

        mock_port = MagicMock()
        mock_port.device = "COM3"
        mock_port.description = "Arduino"
        mock_scan_ports.return_value = ([mock_port], [])

        dialog = LiveConfigDialog(tkinter_root)
        tkinter_root.update_idletasks()

        # Initially enabled if ports available
        initial_state = dialog.arduino_menu.cget("state")
        assert initial_state == "normal"

        # Disable Arduino
        dialog.use_arduino_var.set(False)
        dialog._toggle_arduino_menu()
        tkinter_root.update_idletasks()

        assert dialog.arduino_menu.cget("state") == "disabled"

        # Re-enable Arduino
        dialog.use_arduino_var.set(True)
        dialog._toggle_arduino_menu()
        tkinter_root.update_idletasks()

        assert dialog.arduino_menu.cget("state") == "normal"

    @patch("zebtrack.ui.dialogs.live_config_dialog.WizardService.detect_available_cameras")
    @patch("zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports")
    @patch("zebtrack.ui.dialogs.live_config_dialog.serial.tools.list_ports.comports")
    def test_toggle_arduino_menu_no_ports(
        self, mock_comports, mock_scan_ports, mock_videocapture, tkinter_root
    ):
        """Test Arduino checkbox is disabled when no ports available."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_videocapture.return_value = mock_cap

        mock_scan_ports.return_value = ([], [])
        mock_comports.return_value = []  # No raw ports

        dialog = LiveConfigDialog(tkinter_root)
        tkinter_root.update_idletasks()

        # Menu should already be disabled (no ports available)
        initial_state = dialog.arduino_menu.cget("state")
        assert initial_state == "disabled"

        # Try to enable Arduino (should fail due to no ports)
        dialog.use_arduino_var.set(True)
        dialog._toggle_arduino_menu()
        tkinter_root.update_idletasks()

        # Should remain disabled and checkbox should be unchecked
        assert dialog.arduino_menu.cget("state") == "disabled"
        assert dialog.use_arduino_var.get() is False

    # --- Error Handling Tests ---

    @patch("zebtrack.ui.dialogs.live_config_dialog.WizardService.detect_available_cameras")
    @patch("zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports")
    def test_camera_detection_with_exception(
        self, mock_scan_ports, mock_videocapture, tkinter_root
    ):
        """Test camera detection handles exceptions gracefully."""
        # Mock VideoCapture to raise exception
        mock_videocapture.side_effect = Exception("Camera error")
        mock_scan_ports.return_value = ([], [])

        # Should not crash
        dialog = LiveConfigDialog(tkinter_root)
        tkinter_root.update_idletasks()

        # Should have no cameras
        assert len(dialog.available_cameras) == 0

    @patch("zebtrack.ui.dialogs.live_config_dialog.WizardService.detect_available_cameras")
    @patch("zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports")
    def test_port_detection_with_exception(self, mock_scan_ports, mock_videocapture, tkinter_root):
        """Test port detection handles exceptions gracefully."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_videocapture.return_value = mock_cap

        # Mock scan_available_ports to raise exception
        mock_scan_ports.side_effect = Exception("Serial port error")

        # Should not crash
        dialog = LiveConfigDialog(tkinter_root)
        tkinter_root.update_idletasks()

        # Should have no ports
        assert len(dialog.available_ports) == 0

    @patch("zebtrack.ui.dialogs.live_config_dialog.WizardService.detect_available_cameras")
    @patch("zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports")
    def test_port_without_device_attribute(self, mock_scan_ports, mock_videocapture, tkinter_root):
        """Test port detection handles ports without device attribute."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_videocapture.return_value = mock_cap

        # Mock port without device attribute
        mock_port = MagicMock(spec=[])  # No attributes
        mock_scan_ports.return_value = ([mock_port], [])

        # Should not crash
        dialog = LiveConfigDialog(tkinter_root)
        tkinter_root.update_idletasks()

        # Port without device should be skipped
        assert len(dialog.available_ports) == 0

    # --- Performance Tests ---

    @patch("zebtrack.ui.dialogs.live_config_dialog.WizardService.detect_available_cameras")
    @patch("zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports")
    def test_camera_detection_early_stopping(
        self, mock_scan_ports, mock_videocapture, tkinter_root
    ):
        """Test camera detection checks up to 10 indices (performance issue)."""
        call_count = 0

        def mock_cap_factory(index, *args):
            nonlocal call_count
            call_count += 1
            cap = MagicMock()
            cap.isOpened.return_value = False  # No cameras
            cap.release = MagicMock()
            return cap

        mock_videocapture.side_effect = mock_cap_factory
        mock_scan_ports.return_value = ([], [])

        LiveConfigDialog(tkinter_root)
        tkinter_root.update_idletasks()

        # Should check exactly 10 indices
        assert call_count == 10

    @patch("zebtrack.ui.dialogs.live_config_dialog.WizardService.detect_available_cameras")
    @patch("zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports")
    def test_camera_detection_performance_with_cameras(
        self, mock_scan_ports, mock_videocapture, tkinter_root
    ):
        """Test camera detection with early stopping optimization."""
        call_count = 0

        def mock_cap_factory(index, *args):
            nonlocal call_count
            call_count += 1
            cap = MagicMock()
            # Cameras 0, 1, 2 available, then 3 consecutive failures
            cap.isOpened.return_value = index < 3
            cap.release = MagicMock()
            return cap

        mock_videocapture.side_effect = mock_cap_factory
        mock_scan_ports.return_value = ([], [])

        dialog = LiveConfigDialog(tkinter_root)
        tkinter_root.update_idletasks()

        # Should stop early after 3 consecutive failures (indices 3, 4, 5)
        # Total calls: 0, 1, 2 (success), 3, 4, 5 (3 failures) = 6 calls
        assert call_count == 6
        assert len(dialog.available_cameras) == 3
        assert len(dialog.available_cameras) == 3

    # --- Integration Tests ---

    @patch("zebtrack.ui.dialogs.live_config_dialog.WizardService.detect_available_cameras")
    @patch("zebtrack.ui.dialogs.live_config_dialog.Arduino.scan_available_ports")
    def test_complete_dialog_workflow(self, mock_scan_ports, mock_videocapture, tkinter_root):
        """Test complete dialog workflow from creation to apply."""
        # Setup mocks
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_videocapture.return_value = mock_cap

        mock_port = MagicMock()
        mock_port.device = "COM3"
        mock_port.description = "Arduino Uno"
        mock_scan_ports.return_value = ([mock_port], [])

        # Create dialog
        dialog = LiveConfigDialog(tkinter_root)
        tkinter_root.update_idletasks()

        # Verify devices detected
        assert len(dialog.available_cameras) > 0
        assert len(dialog.available_ports) > 0

        # Configure settings
        dialog.camera_var.set("Câmera 0")
        dialog.use_arduino_var.set(True)

        # Validate
        assert dialog.validate() == 1

        # Apply
        dialog.apply()

        # Verify result
        assert dialog.result["camera_index"] == 0
        assert dialog.result["use_arduino"] is True
        assert dialog.result["arduino_port"] == "COM3"
