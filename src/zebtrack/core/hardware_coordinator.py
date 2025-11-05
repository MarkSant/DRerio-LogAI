"""Hardware coordination service for Arduino and camera management.

This module contains the HardwareCoordinator class, which coordinates hardware
operations including Arduino connection, command execution, and recording control.

Phase: REFACTOR-VIEWMODEL-001
Extracted from: MainViewModel (main_view_model.py)
Purpose: Reduce MainViewModel complexity by extracting hardware management logic
"""

import structlog

from zebtrack.core.project_manager import ProjectManager
from zebtrack.core.state_manager import StateManager
from zebtrack.hardware.arduino_manager import ArduinoManager
from zebtrack.settings import Settings
from zebtrack.ui.event_bus import EventBus, Events

log = structlog.get_logger()


class HardwareCoordinator:
    """Coordinates hardware operations including Arduino and camera.

    This class handles:
    - Arduino connection and disconnection
    - Arduino command execution
    - Arduino event handling
    - Recording service coordination
    - Hardware status tracking

    Responsibilities extracted from MainViewModel to follow
    Single Responsibility Principle.
    """

    def __init__(
        self,
        project_manager: ProjectManager,
        state_manager: StateManager,
        ui_event_bus: EventBus,
        settings_obj: Settings,
    ):
        """Initialize HardwareCoordinator with dependency injection.

        Args:
            project_manager: Project manager for accessing project settings
            state_manager: Centralized state manager
            ui_event_bus: Event bus for UI events
            settings_obj: Settings instance (injected)
        """
        self.project_manager = project_manager
        self.state_manager = state_manager
        self.ui_event_bus = ui_event_bus
        self.settings = settings_obj

        # Reference to Arduino manager (managed by MainViewModel)
        # This is set by MainViewModel after initialization
        self.arduino_manager: ArduinoManager | None = None

        log.info("hardware_coordinator.initialized")

    def _shutdown_arduino_manager(self):
        """Cleanly shut down and disconnect Arduino manager."""
        if self.arduino_manager:
            try:
                self.arduino_manager.disconnect()
                self.arduino_manager = None

                # Update StateManager: Arduino disconnected
                self.state_manager.update_recording_state(
                    source="hardware_coordinator.shutdown",
                    arduino_connected=False,
                    arduino_port=None,
                )
                log.info("hardware_coordinator.arduino_manager.shutdown")
            except Exception as exc:
                log.error(
                    "hardware_coordinator.arduino_manager.shutdown.error",
                    error=str(exc),
                )

    def log_arduino_event(self, message: str):
        """Log Arduino event to console and UI.

        Args:
            message: Event message to log
        """
        log.info("hardware_coordinator.arduino.event", message=message)
        if self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_LOG_ARDUINO_EVENT,
                {"message": message},
            )

    def on_arduino_status_change(self, connected: bool, port: str | None):
        """Handle Arduino connection status changes.

        Args:
            connected: Whether Arduino is connected
            port: Port Arduino is connected to (or None)
        """
        log.info(
            "hardware_coordinator.arduino.status_change",
            connected=connected,
            port=port,
        )

        # Update state manager
        self.state_manager.update_recording_state(
            source="hardware_coordinator.arduino_status",
            arduino_connected=connected,
            arduino_port=port,
        )

        # Notify UI
        if self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_ARDUINO_STATUS_CHANGED,
                {"connected": connected, "port": port},
            )

    def on_arduino_command_sent(self, command: int, success: bool, source: str):
        """Log Arduino command execution with success/failure status.

        Args:
            command: Command code that was sent
            success: Whether command execution succeeded
            source: Source of the command (e.g., "zone_enter", "zone_exit")
        """
        status = "success" if success else "failed"
        log.info(
            f"hardware_coordinator.arduino.command.{status}",
            command=command,
            source=source,
        )

        if self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_ARDUINO_COMMAND_SENT,
                {"command": command, "success": success, "source": source},
            )

    def on_arduino_event(self, event_code: int):
        """Route Arduino events (external trigger signals) to appropriate handlers.

        Args:
            event_code: Event code from Arduino
        """
        log.info("hardware_coordinator.arduino.event_received", code=event_code)

        # Update state manager with external trigger event
        self.state_manager.update_recording_state(
            source="hardware_coordinator.arduino_event",
            external_trigger_pending=True,
            external_trigger_code=event_code,
        )

        # Notify UI about external trigger
        if self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_ARDUINO_EVENT,
                {"event_code": event_code},
            )

    def _is_arduino_connected(self) -> bool:
        """Check if Arduino manager exists and is connected.

        Returns:
            True if Arduino is connected, False otherwise
        """
        if not self.arduino_manager:
            return False
        return self.arduino_manager.is_connected()

    def setup_arduino(self, arduino_manager: ArduinoManager, baud_rate: int) -> bool:
        """Initialize Arduino connection based on project settings.

        Args:
            arduino_manager: ArduinoManager instance from MainViewModel
            baud_rate: Baud rate for serial communication

        Returns:
            True if Arduino setup succeeded or is not required, False on error
        """
        self.arduino_manager = arduino_manager
        project_data = getattr(self.project_manager, "project_data", {}) or {}
        use_arduino = bool(project_data.get("use_arduino"))

        if not use_arduino:
            log.debug("hardware_coordinator.arduino.disabled")
            if self.arduino_manager:
                self.arduino_manager.disconnect()
                # Update StateManager: Arduino disconnected
                self.state_manager.update_recording_state(
                    source="hardware_coordinator.setup_arduino",
                    arduino_connected=False,
                    arduino_port=None,
                )
            return False

        port = (project_data.get("arduino_port") or "").strip()
        if not port:
            log.warning("hardware_coordinator.arduino.no_port_configured")
            return False

        if self.arduino_manager.is_connected() and self.arduino_manager.current_port() == port:
            log.debug("hardware_coordinator.arduino.already_connected", port=port)
            return True

        # Attempt connection
        log.info("hardware_coordinator.arduino.connecting", port=port)
        success = self.arduino_manager.connect(port, baud_rate)

        if success:
            log.info("hardware_coordinator.arduino.connected", port=port)
            # Update StateManager: Arduino connected
            self.state_manager.update_recording_state(
                source="hardware_coordinator.setup_arduino",
                arduino_connected=True,
                arduino_port=port,
            )
        else:
            log.error("hardware_coordinator.arduino.connection_failed", port=port)
            # Update StateManager: Arduino connection failed
            self.state_manager.update_recording_state(
                source="hardware_coordinator.setup_arduino",
                arduino_connected=False,
                arduino_port=None,
            )

        return success

    def send_arduino_command(self, command: int, source: str = "manual") -> bool:
        """Send command to Arduino if connected.

        Args:
            command: Command code to send
            source: Source of the command for logging

        Returns:
            True if command was sent successfully, False otherwise
        """
        if not self._is_arduino_connected():
            log.warning(
                "hardware_coordinator.arduino.command.not_connected",
                command=command,
                source=source,
            )
            return False

        try:
            success = self.arduino_manager.send_command(command)
            if success:
                log.info(
                    "hardware_coordinator.arduino.command.sent",
                    command=command,
                    source=source,
                )
            else:
                log.warning(
                    "hardware_coordinator.arduino.command.failed",
                    command=command,
                    source=source,
                )
            return success
        except Exception as exc:
            log.error(
                "hardware_coordinator.arduino.command.exception",
                command=command,
                source=source,
                error=str(exc),
            )
            return False

    def validate_hardware_for_recording(self) -> tuple[bool, str | None]:
        """Validate that hardware is ready for recording.

        Returns:
            Tuple of (is_valid, error_message)
        """
        project_data = getattr(self.project_manager, "project_data", {}) or {}
        use_arduino = bool(project_data.get("use_arduino"))

        if use_arduino and not self._is_arduino_connected():
            return False, "Arduino está configurado no projeto mas não está conectado"

        return True, None

    def cleanup(self):
        """Cleanup hardware resources on shutdown."""
        log.info("hardware_coordinator.cleanup.start")
        self._shutdown_arduino_manager()
        log.info("hardware_coordinator.cleanup.complete")
