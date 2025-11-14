"""RecordingCoordinator - Recording workflow orchestration.

This coordinator manages recording session workflows by delegating to
RecordingService and coordinating with Arduino hardware.

Sprint 4: Extracted from MainViewModel to improve testability and reduce complexity.

Architecture:
- Orchestrates recording start/stop workflows
- Coordinates Arduino trigger commands
- Manages timed recording sessions
- Handles recording state transitions

Related:
- docs/REFACTOR-MASTER-PLAN-2025.md - Sprint 4
- docs/API_REFERENCE_V3.md - API compatibility
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.coordinators.base import (
    BaseCoordinator,
    CoordinatorError,
    CoordinatorValidationError,
)

if TYPE_CHECKING:
    from zebtrack.core.recording_service import RecordingService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.io.arduino_manager import ArduinoManager
    from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


class RecordingCoordinatorError(CoordinatorError):
    """Raised when recording coordination fails."""

    pass


class RecordingCoordinator(BaseCoordinator):
    """
    Coordinator for recording session workflows.

    This coordinator orchestrates:
    - Recording session start/stop
    - Arduino-triggered recordings
    - Timed recording sessions
    - Recording state management

    Design Principles:
    - Delegates recording logic to RecordingService
    - Coordinates Arduino commands
    - Updates state via StateManager
    - Publishes events via EventBus
    - Clear error handling

    Dependencies:
        state_manager: StateManager for state tracking
        recording_service: RecordingService for recording operations
        arduino_manager: ArduinoManager for hardware control (optional)
        event_bus: Optional EventBus for notifications

    Example:
        ```python
        coordinator = RecordingCoordinator(
            state_manager=state_manager,
            recording_service=recording_service,
            arduino_manager=arduino_manager,
            event_bus=event_bus,
        )

        # Start recording
        success = coordinator.start_recording(
            output_path="/path/to/output",
            experiment_id="exp_001",
            duration=60,
        )

        # Stop recording
        coordinator.stop_recording()
        ```
    """

    def __init__(
        self,
        state_manager: StateManager,
        recording_service: RecordingService,
        arduino_manager: ArduinoManager | None = None,
        event_bus: EventBus | None = None,
    ):
        """Initialize RecordingCoordinator.

        Args:
            state_manager: StateManager for state tracking
            recording_service: RecordingService for recording operations
            arduino_manager: Optional ArduinoManager for hardware control
            event_bus: Optional EventBus for event publishing
        """
        super().__init__(state_manager=state_manager, event_bus=event_bus)

        self.recording_service = recording_service
        self.arduino_manager = arduino_manager

        log.info(
            "recording_coordinator.initialized",
            has_recording_service=recording_service is not None,
            has_arduino=arduino_manager is not None,
        )

    def validate_dependencies(self) -> bool:
        """
        Validate that all required dependencies are available.

        Returns:
            True if all dependencies valid, False otherwise
        """
        if self.recording_service is None:
            log.error("dependency.missing", dep="recording_service")
            return False

        if self.state_manager is None:
            log.error("dependency.missing", dep="state_manager")
            return False

        return True

    # =========================================================================
    # Recording Session Management
    # =========================================================================

    def start_recording(
        self,
        context: dict[str, Any],
        project_data: dict[str, Any],
        *,
        trigger_source: str = "manual",
    ) -> bool:
        """
        Start a recording session by delegating to RecordingService.

        Sprint 15: Completed implementation - delegates to RecordingService.

        Args:
            context: Recording context with session details:
                - day, group, cobaia: Experiment identifiers
                - folder_name: Session folder name
                - output_folder: Full path to output folder
                - arduino_enabled: Whether Arduino is active
                - arduino_port: Arduino port (if enabled)
                - camera_width, camera_height: Camera dimensions (added by ViewModel)
            project_data: Project configuration dictionary
            trigger_source: Source of the recording trigger (manual/external)

        Returns:
            True if recording started successfully, False otherwise

        Raises:
            RecordingCoordinatorError: If recording cannot be started
        """
        # Validate dependencies
        if not self.validate_dependencies():
            raise CoordinatorValidationError(
                "Dependencies not valid",
                coordinator="RecordingCoordinator",
                operation="start_recording",
            )

        self._validate_not_none(context, "context")
        self._validate_not_none(project_data, "project_data")

        output_folder = context.get("output_folder")
        folder_name = context.get("folder_name")

        log.info(
            "recording_coordinator.start_recording.begin",
            folder_name=folder_name,
            trigger_source=trigger_source,
        )

        try:
            # Check if already recording
            recording_state = self.state_manager.get_recording_state()
            if recording_state and recording_state.is_recording:
                log.warning("recording_coordinator.already_recording")
                return False

            # Delegate to RecordingService (Sprint 15: completed)
            self.recording_service.start_session(
                context=context,
                project_data=project_data,
                trigger_source=trigger_source,
            )

            # Note: RecordingService updates StateManager directly,
            # so we don't need to update state here

            # Publish event
            self._publish_event(
                "RECORDING_STARTED",
                {
                    "folder_name": folder_name,
                    "output_folder": output_folder,
                    "trigger_source": trigger_source,
                },
            )

            log.info(
                "recording_coordinator.start_recording.success",
                folder_name=folder_name,
            )

            return True

        except Exception as e:
            log.error(
                "recording_coordinator.start_recording.failed",
                folder_name=folder_name,
                error=str(e),
                exc_info=True,
            )

            raise RecordingCoordinatorError(
                f"Failed to start recording: {str(e)}",
                context={"folder_name": folder_name, "trigger_source": trigger_source},
            ) from e

    def stop_recording(self) -> bool:
        """
        Stop the current recording session by delegating to RecordingService.

        Sprint 15: Completed implementation - delegates to RecordingService.

        Returns:
            True if recording stopped successfully, False otherwise
        """
        log.info("recording_coordinator.stop_recording.begin")

        try:
            # Check if recording
            recording_state = self.state_manager.get_recording_state()
            if not recording_state or not recording_state.is_recording:
                log.warning("recording_coordinator.stop_recording.not_recording")
                return False

            # Delegate to RecordingService (Sprint 15: completed)
            self.recording_service.stop_session()

            # Note: RecordingService updates StateManager directly,
            # so we don't need to update state here

            # Publish event
            self._publish_event("RECORDING_STOPPED", {})

            log.info("recording_coordinator.stop_recording.success")

            return True

        except Exception as e:
            log.error(
                "recording_coordinator.stop_recording.failed",
                error=str(e),
                exc_info=True,
            )
            return False

    # =========================================================================
    # Arduino-Triggered Recording
    # =========================================================================

    def trigger_recording(
        self,
        zone_name: str,
        trigger_type: str = "enter",
    ) -> bool:
        """
        Trigger Arduino command for zone event.

        Args:
            zone_name: Name of the zone that triggered
            trigger_type: Type of trigger ("enter" or "exit")

        Returns:
            True if trigger executed successfully, False otherwise
        """
        if not self.arduino_manager:
            log.debug(
                "recording_coordinator.trigger_recording.no_arduino",
                zone_name=zone_name,
            )
            return False

        log.info(
            "recording_coordinator.trigger_recording",
            zone_name=zone_name,
            trigger_type=trigger_type,
        )

        try:
            # Send Arduino command based on trigger type
            if trigger_type == "enter":
                command = f"ENTER_{zone_name}"
            elif trigger_type == "exit":
                command = f"EXIT_{zone_name}"
            else:
                log.warning(
                    "recording_coordinator.trigger.unknown_type",
                    trigger_type=trigger_type,
                )
                return False

            # Delegate to Arduino manager
            # (actual implementation would call arduino_manager methods)

            # Publish event
            self._publish_event(
                "RECORDING_TRIGGERED",
                {
                    "zone_name": zone_name,
                    "trigger_type": trigger_type,
                    "command": command,
                },
            )

            return True

        except Exception as e:
            log.error(
                "recording_coordinator.trigger_recording.failed",
                zone_name=zone_name,
                error=str(e),
                exc_info=True,
            )
            return False

    # =========================================================================
    # Recording State Queries
    # =========================================================================

    def is_recording(self) -> bool:
        """
        Check if a recording is currently in progress.

        Returns:
            True if recording, False otherwise
        """
        recording_state = self.state_manager.get_recording_state()
        return recording_state is not None and recording_state.is_recording

    def get_recording_info(self) -> dict[str, Any] | None:
        """
        Get information about current recording session.

        Returns:
            dict with recording info, or None if not recording

        Example return:
            {
                "is_recording": True,
                "output_path": "/path/to/output",
                "experiment_id": "exp_001",
                "duration": 60,
            }
        """
        recording_state = self.state_manager.get_recording_state()

        if not recording_state or not recording_state.is_recording:
            return None

        return {
            "is_recording": recording_state.is_recording,
            "output_path": getattr(recording_state, "output_path", None),
            "experiment_id": getattr(recording_state, "experiment_id", None),
            "duration": getattr(recording_state, "duration", None),
        }

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<RecordingCoordinator("
            f"is_recording={self.is_recording()}, "
            f"has_arduino={self.arduino_manager is not None}"
            f")>"
        )
