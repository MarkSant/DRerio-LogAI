"""Hardware coordination service for ZebTrack-AI.

Extracted from MainViewModel (Task 2.2: REFACTOR-VIEWMODEL-001).
Handles detector setup, Arduino management, and zone configuration.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebtrack.settings import Settings

import structlog

from zebtrack.core.detector_service import DetectorService
from zebtrack.core.project_manager import ProjectManager
from zebtrack.core.state_manager import StateManager
from zebtrack.io.arduino import Arduino
from zebtrack.io.arduino_manager import ArduinoManager
from zebtrack.ui.event_bus import EventBus
from zebtrack.ui.events import Events

log = structlog.get_logger()


class HardwareCoordinator:
    """
    Coordinates hardware setup and management.

    Responsibilities:
    - Detector initialization and configuration
    - Arduino connection and event handling
    - Zone configuration for detector
    - Hardware state synchronization with StateManager

    Phase: Task 2.2 (REFACTOR-VIEWMODEL-001)
    Extracted from: MainViewModel (10 methods, ~400 lines)
    """

    def __init__(
        self,
        state_manager: StateManager,
        ui_event_bus: EventBus,
        settings_obj: Settings,
        project_manager: ProjectManager,
        detector_service: DetectorService,
        arduino_manager_cls=None,
    ):
        """Initialize HardwareCoordinator with dependency injection.

        Args:
            state_manager: Centralized state manager
            ui_event_bus: Event bus for UI events
            settings_obj: Settings instance (injected)
            project_manager: Project manager
            detector_service: Detector service
            arduino_manager_cls: ArduinoManager class (for DI, defaults to ArduinoManager)
        """
        self.state_manager = state_manager
        self.ui_event_bus = ui_event_bus
        self.settings = settings_obj
        self.project_manager = project_manager
        self.detector_service = detector_service

        # Arduino management
        self.arduino: Arduino | None = None
        self.arduino_manager: ArduinoManager | None = None
        self._arduino_manager_cls = arduino_manager_cls or ArduinoManager

        # Pending external trigger context (for Arduino-triggered recording)
        self._pending_external_trigger = None

        # Recording callbacks (set by MainViewModel)
        self._trigger_recording_callback = None
        self._stop_recording_callback = None

    # =============================================================================
    # DETECTOR SETUP & CONFIGURATION
    # =============================================================================

    def setup_detector(
        self,
        temp_animal_method: str | None = None,
        use_openvino: bool = False,
        active_weight_name: str = "",
    ) -> bool:
        """
        Initializes the detector instance based on the animal method selection.

        Delegates to DetectorService for actual initialization.

        Args:
            temp_animal_method: Temporary override for animal detection method
                ('det' or 'seg'). If None, uses global settings.
            use_openvino: Whether to use OpenVINO backend
            active_weight_name: Name of the active weight to use

        Returns:
            True if successful, False otherwise
        """
        success, error = self.detector_service.initialize_detector(
            animal_method=temp_animal_method,
            use_openvino=use_openvino,
            active_weight_name=active_weight_name,
        )

        if not success:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro de Detector",
                    "message": error or "Falha ao inicializar o detector",
                },
            )
            return False

        log.info(
            "hardware_coordinator.setup_detector.success",
            method=temp_animal_method or "default",
            openvino=use_openvino,
            weight=active_weight_name or "default",
        )
        return True

    def setup_detector_zones(self) -> None:
        """
        Loads zone data from project and sets it on the detector instance.

        Delegates zone configuration to DetectorService.
        """
        # Delegate zone configuration to service
        success = self.detector_service.configure_zones()

        if not success:
            log.warning("hardware_coordinator.setup_zones.failed")
            return

        # UI logic: notify if no arena polygon defined
        zone_data = self.project_manager.get_zone_data()
        if not zone_data.polygon:
            if self.project_manager.get_project_type() == "pre-recorded":
                self.ui_event_bus.publish_event(Events.UI_SELECT_TAB, {"tab_name": "zone_tab"})
                first_video = self.project_manager.get_next_video()
                if first_video:
                    self.ui_event_bus.publish_event(
                        Events.UI_DISPLAY_VIDEO_FRAME, {"video_path": first_video}
                    )
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Configuração Necessária",
                        "message": "Erro: A área de processamento principal (aquário) não foi "
                        "definida. Por favor, defina-a na aba 'Configuração de Zonas' "
                        "antes de continuar.",
                    },
                )

    # =============================================================================
    # ARDUINO MANAGEMENT
    # =============================================================================

    def setup_arduino(self) -> bool:
        """Ensures the Arduino connection is ready when the project requests it.

        Returns:
            True if Arduino is connected and ready, False otherwise
        """
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

        manager = self._get_arduino_manager()
        if manager.is_connected() and manager.current_port() == port:
            log.debug("hardware_coordinator.arduino.already_connected", port=port)
            self.arduino = manager.arduino
            return True

        baud_rate = self.settings.arduino.baud_rate
        if manager.connect(port, baud_rate):
            self.arduino = manager.arduino
            # Update StateManager: Arduino connected
            self.state_manager.update_recording_state(
                source="hardware_coordinator.setup_arduino",
                arduino_connected=True,
                arduino_port=port,
            )
            return True

        # Update StateManager: Arduino connection failed
        self.state_manager.update_recording_state(
            source="hardware_coordinator.setup_arduino",
            arduino_connected=False,
            arduino_port=None,
        )
        return False

    def is_arduino_connected(self) -> bool:
        """Checks whether there is an active Arduino connection.

        Returns:
            True if Arduino is connected, False otherwise
        """
        if not self.arduino_manager:
            return False
        return self.arduino_manager.is_connected()

    def shutdown_arduino(self) -> None:
        """Gracefully shutdown Arduino connection."""
        if self.arduino_manager:
            try:
                self.arduino_manager.shutdown()
            except OSError as exc:
                log.error(
                    "hardware_coordinator.arduino.shutdown_io_failed", error=str(exc), exc_info=True
                )
            except Exception as exc:  # pragma: no cover - unexpected errors
                log.exception(
                    "hardware_coordinator.arduino.shutdown_unexpected_error", error=str(exc)
                )
            self.arduino_manager = None
        self.arduino = None

    def _get_arduino_manager(self) -> ArduinoManager:
        """Get or create ArduinoManager instance.

        Returns:
            ArduinoManager instance
        """
        if self.arduino_manager is None:
            # Note: ArduinoManager expects controller, but we're passing self
            # This might need adjustment depending on ArduinoManager implementation
            self.arduino_manager = self._arduino_manager_cls(self)
        return self.arduino_manager

    # =============================================================================
    # ARDUINO EVENT HANDLERS
    # =============================================================================

    def log_arduino_event(self, message: str) -> None:
        """Log an Arduino event and publish to UI.

        Args:
            message: Event message to log
        """
        log.info("hardware_coordinator.arduino.log", message=message)
        self.ui_event_bus.publish_event(Events.UI_APPEND_ARDUINO_LOG, {"message": message})

    def on_arduino_status_change(self, connected: bool, port: str | None) -> None:
        """Handle Arduino connection status change.

        Args:
            connected: True if connected, False if disconnected
            port: Serial port name or None
        """
        log.info("hardware_coordinator.arduino.status", connected=connected, port=port)
        self.ui_event_bus.publish_event(
            Events.UI_UPDATE_ARDUINO_STATUS, {"connected": connected, "port": port}
        )

    def on_arduino_command_sent(self, command: int, success: bool, source: str) -> None:
        """Handle Arduino command sent notification.

        Args:
            command: Command code sent
            success: True if command sent successfully
            source: Source of the command (for logging)
        """
        label_text = str(command) if success else f"{command} (falha)"
        self.ui_event_bus.publish_event(
            Events.UI_SET_STATUS, {"message": f"Comando Arduino: {label_text}"}
        )

    def on_arduino_event(self, event_code: int) -> None:
        """Handle Arduino event received.

        Called by ArduinoManager when events are received from Arduino.

        Args:
            event_code: Event code from Arduino (0=stop, 1=start, etc.)
        """
        log.info("hardware_coordinator.arduino.event_received", code=event_code)
        self.log_arduino_event(f"Evento {event_code} recebido do Arduino.")

        if event_code == 1:
            if self._pending_external_trigger:
                self.log_arduino_event("Sinal externo recebido. Iniciando gravação...")
                if self._trigger_recording_callback:
                    self._trigger_recording_callback(event_code)
            else:
                log.warning("hardware_coordinator.arduino.event.unexpected_start")
        elif event_code == 0:
            # Note: This check depends on recording state which is in StateManager
            is_recording = self.state_manager.get_recording_state().get("is_recording", False)
            if is_recording or self._pending_external_trigger:
                self.log_arduino_event("Sinal externo solicitando parada.")
                if self._stop_recording_callback:
                    self._stop_recording_callback()
        else:
            log.info("hardware_coordinator.arduino.event.ignored", code=event_code)

    def set_pending_external_trigger(self, context: dict | None) -> None:
        """Set pending external trigger context for Arduino-triggered recording.

        Args:
            context: Recording context or None to clear
        """
        self._pending_external_trigger = context

    def get_pending_external_trigger(self) -> dict | None:
        """Get pending external trigger context.

        Returns:
            Recording context or None
        """
        return self._pending_external_trigger

    def clear_pending_external_trigger(self) -> None:
        """Clear pending external trigger context."""
        self._pending_external_trigger = None
        if self.ui_event_bus:
            self.ui_event_bus.publish_event(Events.UI_CLEAR_EXTERNAL_TRIGGER_NOTICE)

    def set_recording_callbacks(
        self,
        trigger_callback: Callable[[int], None] | None,
        stop_callback: Callable[[], None] | None,
    ) -> None:
        """Set callbacks for Arduino-triggered recording events.

        Args:
            trigger_callback: Function to call when Arduino triggers recording start.
                             Accepts event_code (int) as parameter.
            stop_callback: Function to call when Arduino triggers recording stop.
                          No parameters.
        """
        self._trigger_recording_callback = trigger_callback
        self._stop_recording_callback = stop_callback
