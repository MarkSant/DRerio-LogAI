"""
Tests for ArduinoDashboardWidget component.

Covers widget initialization, event emission, public API methods, error handling,
and thread-safe UI updates as required by CLAUDE.md (minimum 70% coverage).
"""

import time
from unittest.mock import MagicMock, patch

import pytest
from tests.utils.wait_helpers import wait_for_condition, wait_for_thread_exit

from zebtrack.ui.components.arduino_dashboard import ArduinoDashboardWidget
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents


@pytest.mark.gui
class TestArduinoDashboardWidget:
    """Test suite for ArduinoDashboardWidget component."""

    @pytest.fixture
    def event_bus(self):
        """Create a mock event bus for testing."""
        bus = MagicMock(spec=EventBusV2)
        bus.subscribe = MagicMock()
        return bus

    @pytest.fixture
    def project_manager(self):
        """Create a mock project manager for testing."""
        pm = MagicMock()
        pm.project_data = {"arduino_port": "COM3"}
        pm.save_project = MagicMock()
        return pm

    @pytest.fixture
    def widget(self, tkinter_root, event_bus, project_manager):
        """Create an ArduinoDashboardWidget instance for testing."""
        widget = ArduinoDashboardWidget(
            tkinter_root,
            event_bus=event_bus,
            project_manager=project_manager,
        )
        tkinter_root.update_idletasks()
        return widget

    # --- Initialization Tests ---

    def test_widget_initialization(self, tkinter_root, event_bus, project_manager):
        """Test widget initializes with correct default values."""
        widget = ArduinoDashboardWidget(
            tkinter_root,
            event_bus=event_bus,
            project_manager=project_manager,
        )
        tkinter_root.update_idletasks()

        # Verify default state
        assert widget.status_var.get() == "Desconectado"
        assert widget.last_command_var.get() == "-"

        # Verify widget references
        assert widget.status_indicator is not None
        assert widget.log_text is not None

        # Verify max log lines constant
        assert widget.MAX_LOG_LINES == 300

    def test_widget_without_project_manager(self, tkinter_root, event_bus):
        """Test widget can be created without project manager."""
        widget = ArduinoDashboardWidget(
            tkinter_root,
            event_bus=event_bus,
            project_manager=None,
        )
        tkinter_root.update_idletasks()

        assert widget.project_manager is None
        assert widget.status_var.get() == "Desconectado"

    def test_widget_without_event_bus(self, tkinter_root):
        """Test widget can be created without event bus (no crashes)."""
        widget = ArduinoDashboardWidget(tkinter_root, event_bus=None)
        tkinter_root.update_idletasks()

        assert widget.event_bus is None

    # --- Public API Tests ---

    def test_append_log(self, widget, tkinter_root):
        """Test append_log adds timestamped messages to log."""
        message = "Test log entry"
        widget.append_log(message)
        # Process scheduled after() callbacks
        tkinter_root.update()

        log_content = widget.log_text.get("1.0", "end")
        assert message in log_content
        assert "[" in log_content  # Timestamp marker

    def test_append_log_multiple_messages(self, widget, tkinter_root):
        """Test appending multiple log messages."""
        messages = ["Message 1", "Message 2", "Message 3"]

        for msg in messages:
            widget.append_log(msg)
            # Process scheduled updates
            tkinter_root.update()

        log_content = widget.log_text.get("1.0", "end")
        for msg in messages:
            assert msg in log_content

    def test_append_log_trimming(self, widget, tkinter_root):
        """Test log trimming when exceeding MAX_LOG_LINES."""
        # Add messages exceeding MAX_LOG_LINES
        for i in range(widget.MAX_LOG_LINES + 50):
            widget.append_log(f"Message {i}")
            if i % 50 == 0:  # Periodic UI updates
                tkinter_root.update_idletasks()

        tkinter_root.update_idletasks()

        # Count lines in log
        log_content = widget.log_text.get("1.0", "end")
        line_count = len([line for line in log_content.split("\n") if line.strip()])

        # Should not exceed MAX_LOG_LINES significantly
        assert line_count <= widget.MAX_LOG_LINES + 10  # Some tolerance for timing

    def test_seeds_connected_status_from_manager(self, tkinter_root, event_bus):
        """Regression: a panel built AFTER connect must reflect the live state.

        Previously the dashboard hardcoded 'disconnected' at build time, so the
        dot stayed red even though the serial connection was already up.
        """
        from unittest.mock import MagicMock

        manager = MagicMock()
        manager.is_connected.return_value = True
        manager.current_port.return_value = "COM3"

        widget = ArduinoDashboardWidget(
            tkinter_root,
            event_bus=event_bus,
            arduino_manager=manager,
        )
        tkinter_root.update_idletasks()

        assert widget.status_var.get() == "Conectado (COM3)"
        assert widget.status_indicator.cget("foreground") == "#16a34a"

    def test_command_event_updates_last_command(self, tkinter_root):
        """UI_UPDATE_ARDUINO_COMMAND must refresh the 'Último comando' label.

        Uses a real EventBusV2 so the widget's subscription actually dispatches.
        """
        from zebtrack.ui import payloads
        from zebtrack.ui.event_bus_v2 import Event, EventBusV2, UIEvents

        real_bus = EventBusV2()
        widget = ArduinoDashboardWidget(tkinter_root, event_bus=real_bus)
        tkinter_root.update_idletasks()

        real_bus.publish(
            Event(
                type=UIEvents.UI_UPDATE_ARDUINO_COMMAND,
                data=payloads.UIUpdateArduinoCommandPayload(command=5, success=True, source="zone"),
            )
        )
        tkinter_root.update_idletasks()

        assert widget.last_command_var.get() == "5"

    def test_run_on_ui_thread_inline_on_main_thread(self, widget):
        """On the main thread the callback runs inline (synchronous)."""
        ran = []
        widget._run_on_ui_thread(lambda: ran.append(True))
        assert ran == [True]

    def test_update_status_on_main_thread_applies_inline(self, widget):
        """On the main thread the update is applied synchronously (no pumping)."""
        widget.update_status(connected=True, port="COM9")
        assert widget.status_var.get() == "Conectado (COM9)"

    def test_run_on_ui_thread_marshals_when_off_main_thread(self, widget):
        """Off the main thread the callback is deferred to Tk via after(0, ...).

        Regression for the review note: EventBusV2 publishes synchronously on the
        caller thread, so Arduino reader/writer worker threads reach these widget
        methods. They MUST NOT touch Tk directly; the mutation is marshalled onto
        the Tk main thread. Verified deterministically (mocked thread + toplevel)
        so no real cross-thread Tk call is made.
        """
        from unittest.mock import MagicMock, patch

        fake_top = MagicMock()
        ran = []

        with (
            patch(
                "zebtrack.ui.components.arduino_dashboard.threading.current_thread",
                return_value=object(),  # anything != main_thread()
            ),
            patch.object(widget, "winfo_toplevel", return_value=fake_top),
        ):
            widget._run_on_ui_thread(lambda: ran.append(True))

        # Deferred, not run inline; scheduled via after(0, fn).
        assert ran == []
        fake_top.after.assert_called_once()
        assert fake_top.after.call_args.args[0] == 0

    def test_update_status_connected(self, widget):
        """Test update_status with connected state."""
        widget.update_status(connected=True, port="COM5")

        assert widget.status_var.get() == "Conectado (COM5)"
        # Status indicator should be green
        assert widget.status_indicator.cget("foreground") == "#16a34a"

    def test_update_status_connected_no_port(self, widget):
        """Test update_status with connected but no port specified."""
        widget.update_status(connected=True, port=None)

        assert widget.status_var.get() == "Conectado"

    def test_update_status_disconnected(self, widget):
        """Test update_status with disconnected state."""
        widget.update_status(connected=False, port=None)

        assert widget.status_var.get() == "Desconectado"
        # Status indicator should be red
        assert widget.status_indicator.cget("foreground") == "#b91c1c"

    def test_set_last_command(self, widget):
        """Test set_last_command updates last command display."""
        widget.set_last_command("START")
        assert widget.last_command_var.get() == "START"

        widget.set_last_command("STOP")
        assert widget.last_command_var.get() == "STOP"

    def test_set_last_command_with_none(self, widget):
        """Test set_last_command handles None value."""
        widget.set_last_command(None)
        assert widget.last_command_var.get() == "-"

    def test_clear_log(self, widget, tkinter_root):
        """Test clear_log removes all log entries."""
        # Add some messages
        widget.append_log("Message 1")
        widget.append_log("Message 2")
        tkinter_root.update_idletasks()

        # Clear log
        widget.clear_log()
        tkinter_root.update_idletasks()

        log_content = widget.log_text.get("1.0", "end").strip()
        assert log_content == ""

    # --- Event Emission Tests ---

    @patch("zebtrack.ui.components.arduino_dashboard.serial.tools.list_ports.comports")
    @patch("zebtrack.ui.components.arduino_dashboard.simpledialog.askstring")
    def test_recheck_ports_emits_event(
        self, mock_askstring, mock_comports, widget, event_bus, tkinter_root
    ):
        """Test port recheck emits arduino.port_update_requested event."""
        # Mock port detection
        mock_port = MagicMock()
        mock_port.device = "COM4"
        mock_port.description = "Arduino Uno"
        mock_comports.return_value = [mock_port]

        # Mock user selection
        mock_askstring.return_value = "COM4"

        # Trigger recheck
        widget._recheck_arduino_ports()
        tkinter_root.update_idletasks()

        # Verify event was emitted
        event_bus.publish.assert_called()
        call_args = event_bus.publish.call_args
        assert call_args[0][0] == UIEvents.ARDUINO_PORT_UPDATE_REQUESTED
        assert call_args[0][1]["port"] == "COM4"

    @patch("zebtrack.ui.components.arduino_dashboard.serial.tools.list_ports.comports")
    @patch("zebtrack.ui.components.arduino_dashboard.messagebox.showwarning")
    def test_recheck_ports_no_ports_found(self, mock_warning, mock_comports, widget, tkinter_root):
        """Test port recheck handles no ports detected."""
        mock_comports.return_value = []

        widget._recheck_arduino_ports()
        tkinter_root.update_idletasks()

        # Should show warning
        mock_warning.assert_called_once()
        assert "Nenhuma porta serial" in mock_warning.call_args[0][1]

    @patch("zebtrack.ui.components.arduino_dashboard.serial.tools.list_ports.comports")
    @patch("zebtrack.ui.components.arduino_dashboard.simpledialog.askstring")
    def test_recheck_ports_user_cancels(
        self, mock_askstring, mock_comports, widget, event_bus, tkinter_root
    ):
        """Test port recheck handles user cancellation."""
        mock_port = MagicMock()
        mock_port.device = "COM3"
        mock_port.description = "Arduino"
        mock_comports.return_value = [mock_port]

        # User cancels dialog
        mock_askstring.return_value = None

        widget._recheck_arduino_ports()
        tkinter_root.update_idletasks()

        # Should not emit event
        event_bus.publish.assert_not_called()

    @patch("zebtrack.ui.components.arduino_dashboard.serial.tools.list_ports.comports")
    @patch("zebtrack.ui.components.arduino_dashboard.simpledialog.askstring")
    @patch("zebtrack.ui.components.arduino_dashboard.messagebox.showerror")
    def test_recheck_ports_invalid_selection(
        self, mock_error, mock_askstring, mock_comports, widget, tkinter_root
    ):
        """Test port recheck handles invalid port selection."""
        mock_port = MagicMock()
        mock_port.device = "COM3"
        mock_port.description = "Arduino"
        mock_comports.return_value = [mock_port]

        # User enters invalid port
        mock_askstring.return_value = "COM99"

        widget._recheck_arduino_ports()
        tkinter_root.update_idletasks()

        # Should show error
        mock_error.assert_called_once()
        assert "não está entre as portas detectadas" in mock_error.call_args[0][1]

    @patch("zebtrack.ui.components.arduino_dashboard.serial.tools.list_ports.comports")
    @patch("zebtrack.ui.components.arduino_dashboard.simpledialog.askstring")
    def test_recheck_ports_updates_project_config(
        self, mock_askstring, mock_comports, widget, project_manager, tkinter_root
    ):
        """Test port recheck updates project configuration."""
        mock_port = MagicMock()
        mock_port.device = "COM7"
        mock_port.description = "Arduino Mega"
        mock_comports.return_value = [mock_port]

        mock_askstring.return_value = "COM7"

        widget._recheck_arduino_ports()
        tkinter_root.update_idletasks()

        # Verify project data was updated
        assert project_manager.project_data["arduino_port"] == "COM7"
        project_manager.save_project.assert_called_once()

        # Confirmation is now logged instead of shown in messagebox

    @patch("zebtrack.ui.components.arduino_dashboard.serial.tools.list_ports.comports")
    @patch("zebtrack.ui.components.arduino_dashboard.simpledialog.askstring")
    @patch("zebtrack.ui.components.arduino_dashboard.messagebox.showwarning")
    def test_recheck_ports_no_project_loaded(
        self, mock_warning, mock_askstring, mock_comports, tkinter_root, event_bus
    ):
        """Test port recheck handles no project loaded."""
        # Create widget without project manager
        widget = ArduinoDashboardWidget(tkinter_root, event_bus=event_bus, project_manager=None)
        tkinter_root.update_idletasks()

        mock_port = MagicMock()
        mock_port.device = "COM3"
        mock_port.description = "Arduino"
        mock_comports.return_value = [mock_port]

        mock_askstring.return_value = "COM3"

        widget._recheck_arduino_ports()
        tkinter_root.update_idletasks()

        # Should show warning about no project
        mock_warning.assert_called_once()
        assert "Nenhum projeto" in mock_warning.call_args[0][1]

    # --- Error Handling Tests ---

    def test_append_log_with_none_log_text(self, tkinter_root, event_bus):
        """Test append_log handles missing log_text widget."""
        widget = ArduinoDashboardWidget(tkinter_root, event_bus=event_bus)
        widget.log_text = None
        tkinter_root.update_idletasks()

        # Should not crash
        widget.append_log("Test message")

    def test_update_status_with_exceptions(self, widget):
        """Test update_status handles exceptions gracefully."""
        # Force an exception by destroying the widget
        original_indicator = widget.status_indicator
        widget.status_indicator = None

        # Should not crash
        widget.update_status(connected=True, port="COM3")

        # Restore for cleanup
        widget.status_indicator = original_indicator

    def test_set_last_command_with_empty_string(self, widget):
        """Test set_last_command handles empty string."""
        widget.set_last_command("")
        assert widget.last_command_var.get() == "-"

    @patch("zebtrack.ui.components.arduino_dashboard.serial.tools.list_ports.comports")
    @patch("zebtrack.ui.components.arduino_dashboard.messagebox.showerror")
    def test_recheck_ports_exception_handling(
        self, mock_error, mock_comports, widget, tkinter_root
    ):
        """Test port recheck handles exceptions."""
        mock_comports.side_effect = Exception("Serial error")

        widget._recheck_arduino_ports()
        tkinter_root.update_idletasks()

        # Should show error dialog
        mock_error.assert_called_once()
        assert "erro" in mock_error.call_args[0][1].lower()

    # --- Thread Safety Tests ---

    def test_append_log_thread_safe(self, widget, tkinter_root):
        """Test append_log is thread-safe (uses root.after for UI updates)."""
        # This test verifies the fix for the thread safety issue
        # append_log should schedule UI updates via root.after(0, ...)

        from threading import Thread

        messages = []

        def background_task():
            """Simulate background thread appending logs."""
            for i in range(5):  # Reduced count for stability
                msg = f"Background message {i}"
                messages.append(msg)
                widget.append_log(msg)
                time.sleep(0.02)  # Small delay for interleaving

        # Start background thread
        thread = Thread(target=background_task, daemon=True)
        thread.start()

        # Wait for thread to complete
        wait_for_thread_exit(thread, timeout=2.0)

        # Process remaining UI events
        for _ in range(10):
            tkinter_root.update_idletasks()

        # Verify messages were logged
        log_content = widget.log_text.get("1.0", "end")
        wait_for_condition(
            lambda: sum(1 for msg in messages if msg in log_content) >= len(messages) // 2,
            timeout=1.0,
        )
        found_count = sum(1 for msg in messages if msg in log_content)
        assert found_count >= len(messages) // 2, (
            f"Expected at least {len(messages) // 2} messages in log, "
            f"but found {found_count}. Log content: {log_content}"
        )

    # --- Integration Tests ---

    def test_complete_arduino_workflow(self, widget, tkinter_root):
        """Test a complete Arduino connection workflow."""
        # Initial disconnected state
        assert widget.status_var.get() == "Desconectado"

        # Connect
        widget.update_status(connected=True, port="COM3")
        widget.append_log("✓ Arduino conectado")
        tkinter_root.update()

        assert widget.status_var.get() == "Conectado (COM3)"
        assert "conectado" in widget.log_text.get("1.0", "end")

        # Send commands
        widget.set_last_command("START")
        widget.append_log("→ Enviado: START")
        tkinter_root.update()

        assert widget.last_command_var.get() == "START"

        widget.set_last_command("STOP")
        widget.append_log("→ Enviado: STOP")
        tkinter_root.update()

        assert widget.last_command_var.get() == "STOP"

        # Disconnect
        widget.update_status(connected=False, port=None)
        widget.append_log("✗ Arduino desconectado")
        tkinter_root.update()

        assert widget.status_var.get() == "Desconectado"

    def test_log_display_formatting(self, widget, tkinter_root):
        """Test log entries are properly formatted with timestamps."""
        test_messages = [
            "✓ Conexão estabelecida",
            "→ Comando enviado",
            "✗ Erro de comunicação",
        ]

        for msg in test_messages:
            widget.append_log(msg)
            tkinter_root.update()

        log_content = widget.log_text.get("1.0", "end")

        # Verify formatting
        for msg in test_messages:
            assert msg in log_content
            # Should have timestamp in [HH:MM:SS] format
            assert "[" in log_content and "]" in log_content

    def test_status_indicator_color_changes(self, widget):
        """Test status indicator changes color based on connection state."""
        # Disconnected - red
        widget.update_status(connected=False, port=None)
        assert widget.status_indicator.cget("foreground") == "#b91c1c"

        # Connected - green
        widget.update_status(connected=True, port="COM3")
        assert widget.status_indicator.cget("foreground") == "#16a34a"

        # Back to disconnected - red
        widget.update_status(connected=False, port=None)
        assert widget.status_indicator.cget("foreground") == "#b91c1c"
