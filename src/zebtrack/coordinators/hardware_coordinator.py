"""Hardware Coordinator - Phase 3 Consolidation.

Super coordinator for hardware and model management.

CONSOLIDATES (Phase 3 - Fase 3):
    - DetectorCoordinator (Sprint 5) - 886 lines
    - ModelDiagnosticsOrchestrator (Sprint 29) - 609 lines

Total: ~1495 lines consolidated into this unified coordinator

This coordinator manages:
    - Detector initialization and configuration (YOLO/OpenVINO)
    - Zone configuration and scaling
    - Tracking parameter management (ByteTrack)
    - Single subject mode configuration
    - Model diagnostic test execution
    - Diagnostic report generation

Architecture:
    - Zero MainViewModel dependency
    - Pure dependency injection pattern
    - Delegates to DetectorService and ModelService
    - Publishes events via EventBus
    - Updates StateManager for state tracking
"""

from __future__ import annotations

import glob
import os
import shutil
import threading
from typing import TYPE_CHECKING, Any, Callable, cast

import cv2
import structlog

from zebtrack.coordinators.base import BaseCoordinator, CoordinatorValidationError
from zebtrack.core.state_manager import StateCategory
from zebtrack.plugins import DETECTOR_PLUGINS
from zebtrack.ui.events import Events

try:
    from ultralytics import YOLO

    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False

if TYPE_CHECKING:
    from threading import Event

    from zebtrack.core.detector_service import DetectorService
    from zebtrack.core.model_service import ModelService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.weight_manager import WeightManager
    from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


# =============================================================================
# EXCEPTIONS
# =============================================================================


class HardwareCoordinatorError(Exception):
    """Base exception for HardwareCoordinator errors."""

    def __init__(self, message: str, context: dict[str, Any] | None = None):
        """Initialize exception with message and optional context.

        Args:
            message: Error message
            context: Optional context dictionary
        """
        super().__init__(message)
        self.context = context or {}


class DiagnosticAbortError(RuntimeError):
    """Signal used to stop diagnostic workflow without surfacing duplicate dialogs."""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _is_valid_openvino_directory(path: str | None) -> bool:
    """Validate if an OpenVINO model directory exists and contains required .xml files.

    Args:
        path: Path to the OpenVINO model directory

    Returns:
        True if the directory exists and contains at least one .xml file, False otherwise
    """
    if not path or not os.path.exists(path):
        return False

    if not os.path.isdir(path):
        return False

    xml_files = glob.glob(os.path.join(path, "*.xml"))
    return len(xml_files) > 0


# =============================================================================
# MAIN COORDINATOR
# =============================================================================


class HardwareCoordinator(BaseCoordinator):
    """Super coordinator for hardware and model management.

    Phase 3 Consolidation - ALL hardware responsibilities:
    - Detector setup and configuration
    - Zone management
    - Tracking parameters
    - Model diagnostics
    - Hardware state management

    Consolidated Components:
        - DetectorCoordinator (Sprint 5)
        - ModelDiagnosticsOrchestrator (Sprint 29)
    """

    def __init__(
        self,
        state_manager: StateManager,
        detector_service: DetectorService,
        weight_manager: WeightManager,
        model_service: ModelService | None = None,
        event_bus: EventBus | None = None,
        cancel_event: Event | None = None,
        # UI components (for callbacks - being phased out)
        root: Any = None,
        view: Any = None,
    ):
        """Initialize HardwareCoordinator with pure dependency injection.

        Args:
            state_manager: StateManager for centralized state tracking
            detector_service: DetectorService for detector operations
            weight_manager: WeightManager for active weight resolution
            model_service: ModelService for model/weight management (optional)
            event_bus: EventBus for UI notifications (optional)
            cancel_event: Threading event for cancellation (optional)
            root: Tkinter root window (legacy, being phased out)
            view: GUI view instance (legacy, being phased out)

        Note:
            CRITICAL: NEVER pass MainViewModel. All dependencies must be explicit.
            The root and view parameters are temporary for gradual migration and will
            be removed in future sprints as UI callbacks move to pure event-based system.
        """
        super().__init__(state_manager=state_manager, event_bus=event_bus)

        # Core services
        self.detector_service = detector_service
        self.model_service = model_service
        self.weight_manager = weight_manager
        self.cancel_event = cancel_event

        # UI components (temporary - being phased out)
        self.root = root
        self.view = view

        # Cache settings from detector_service
        self.settings = detector_service.settings

        # Recording callbacks (for session coordinator integration)
        self._trigger_recording_callback: Callable[[int], None] | None = None
        self._stop_recording_callback: Callable[[], None] | None = None

        log.info(
            "hardware_coordinator.initialized",
            has_model_service=model_service is not None,
            has_weight_manager=weight_manager is not None,
            has_cancel_event=cancel_event is not None,
        )

    def validate_dependencies(self) -> bool:
        """Validate that required dependencies are present.

        Returns:
            bool: True if all required dependencies are present

        Raises:
            CoordinatorValidationError: If required dependencies are missing
        """
        if self.detector_service is None:
            raise CoordinatorValidationError(
                "DetectorService is required but was None",
                context={
                    "coordinator": "HardwareCoordinator",
                    "missing_dependency": "detector_service",
                },
            )
        if self.weight_manager is None:
            raise CoordinatorValidationError(
                "WeightManager is required but was None",
                context={
                    "coordinator": "HardwareCoordinator",
                    "missing_dependency": "weight_manager",
                },
            )
        return True

    # =============================================================================
    # GROUP A: DETECTOR SETUP & CONFIGURATION (DetectorCoordinator)
    # =============================================================================

    def setup_detector(
        self,
        animal_method: str | None = None,
        use_openvino: bool = False,
        active_weight_name: str | None = None,
        detector_plugins: dict | None = None,
    ) -> tuple[bool, str | None]:
        """Initialize the detector instance based on configuration.

        Orchestrates detector initialization by:
        1. Validating dependencies
        2. Delegating to DetectorService.initialize_detector()
        3. Updating StateManager with detector state
        4. Publishing events for UI updates

        Args:
            animal_method: Detection method ('det' or 'seg'). If None, uses settings
            use_openvino: Whether to use OpenVINO backend
            active_weight_name: Name of the active weight to use
            detector_plugins: Dict mapping plugin names to plugin classes

        Returns:
            tuple: (success: bool, error_message: str | None)

        Raises:
            CoordinatorValidationError: If dependencies are invalid
            HardwareCoordinatorError: If detector initialization fails

        Example:
            >>> success, error = coordinator.setup_detector(
            ...     animal_method="det",
            ...     use_openvino=True,
            ...     active_weight_name="yolo11n"
            ... )
            >>> if success:
            ...     print("Detector initialized successfully")
        """
        # Validate dependencies
        if not self.validate_dependencies():
            raise CoordinatorValidationError(
                "Cannot setup detector - dependencies invalid",
                context={"animal_method": animal_method, "use_openvino": use_openvino},
            )

        # Validate inputs
        if animal_method is not None:
            self._validate_type(animal_method, str, "animal_method")
            if animal_method not in ("det", "seg"):
                raise ValueError(f"Invalid animal_method: {animal_method}. Must be 'det' or 'seg'")

        self._validate_type(use_openvino, bool, "use_openvino")

        if active_weight_name is not None:
            self._validate_type(active_weight_name, str, "active_weight_name")

        # Delegate to service
        try:
            success, error_message = self.detector_service.initialize_detector(
                animal_method=animal_method,
                use_openvino=use_openvino,
                active_weight_name=active_weight_name,
                detector_plugins=detector_plugins,
            )

            if success:
                # Update state
                self._update_state(
                    StateCategory.DETECTOR,
                    is_detector_initialized=True,
                    animal_method=animal_method
                    or self.detector_service.settings.detection.animal_method,
                    use_openvino=use_openvino,
                )

                log.info(
                    "hardware_coordinator.setup_detector.success",
                    animal_method=animal_method,
                    use_openvino=use_openvino,
                )
            else:
                log.error(
                    "hardware_coordinator.setup_detector.failed",
                    error=error_message,
                    animal_method=animal_method,
                    use_openvino=use_openvino,
                )

            return success, error_message

        except Exception as e:
            log.exception(
                "hardware_coordinator.setup_detector.exception",
                error=str(e),
                animal_method=animal_method,
            )
            raise HardwareCoordinatorError(
                f"Failed to setup detector: {e}",
                context={
                    "animal_method": animal_method,
                    "use_openvino": use_openvino,
                    "active_weight_name": active_weight_name,
                },
            ) from e

    def configure_zones(
        self,
        zones_data: list[dict] | None = None,
        video_width: int | None = None,
        video_height: int | None = None,
    ) -> bool:
        """Configure zones for the detector.

        Orchestrates zone configuration by:
        1. Validating dependencies and inputs
        2. Delegating to DetectorService.configure_zones()
        3. Updating StateManager with zone state
        4. Publishing events for UI updates

        Args:
            zones_data: List of zone dictionaries with zone definitions
            video_width: Width of the video for zone scaling
            video_height: Height of the video for zone scaling

        Returns:
            bool: True if zones were configured successfully

        Raises:
            CoordinatorValidationError: If dependencies are invalid
            HardwareCoordinatorError: If zone configuration fails

        Example:
            >>> zones = [{"name": "Zone1", "polygon": [[0,0], [100,0], [100,100], [0,100]]}]
            >>> success = coordinator.configure_zones(
            ...     zones_data=zones,
            ...     video_width=1920,
            ...     video_height=1080
            ... )
        """
        # Validate dependencies
        if not self.validate_dependencies():
            raise CoordinatorValidationError(
                "Cannot configure zones - dependencies invalid",
                context={"zones_count": len(zones_data) if zones_data else 0},
            )

        # Validate inputs
        if zones_data is not None:
            self._validate_type(zones_data, list, "zones_data")

        if video_width is not None:
            self._validate_type(video_width, int, "video_width")
            if video_width <= 0:
                raise ValueError("video_width must be > 0")

        if video_height is not None:
            self._validate_type(video_height, int, "video_height")
            if video_height <= 0:
                raise ValueError("video_height must be > 0")

        # Delegate to service
        try:
            success = self.detector_service.configure_zones(
                zones_data=zones_data,
                video_width=video_width,
                video_height=video_height,
            )

            if success:
                # Update state
                self._update_state(
                    StateCategory.DETECTOR,
                    zones_configured=True,
                    zones_count=len(zones_data) if zones_data else 0,
                )

                # Publish success event
                self._publish_event(
                    "ZONES_CONFIGURED",
                    {
                        "zones_count": len(zones_data) if zones_data else 0,
                        "video_width": video_width,
                        "video_height": video_height,
                    },
                )

                log.info(
                    "hardware_coordinator.configure_zones.success",
                    zones_count=len(zones_data) if zones_data else 0,
                )
            else:
                log.warning("hardware_coordinator.configure_zones.failed")

            return success

        except Exception as e:
            log.exception("hardware_coordinator.configure_zones.exception", error=str(e))
            raise HardwareCoordinatorError(
                f"Failed to configure zones: {e}",
                context={
                    "zones_count": len(zones_data) if zones_data else 0,
                    "video_width": video_width,
                    "video_height": video_height,
                },
            ) from e

    def update_tracking_parameters(
        self,
        track_threshold: float | None = None,
        match_threshold: float | None = None,
        track_buffer: int | None = None,
    ) -> bool:
        """Update ByteTrack tracking parameters.

        Orchestrates tracking parameter updates by:
        1. Validating dependencies and inputs
        2. Delegating to DetectorService.update_tracking_parameters()
        3. Updating StateManager with parameter state
        4. Publishing events for UI updates

        Args:
            track_threshold: Detection confidence threshold (0.0-1.0)
            match_threshold: IoU matching threshold (0.0-1.0)
            track_buffer: Number of frames to keep lost tracks

        Returns:
            bool: True if parameters were updated successfully

        Raises:
            CoordinatorValidationError: If dependencies are invalid
            HardwareCoordinatorError: If parameter update fails
            ValueError: If parameter values are out of valid range

        Example:
            >>> success = coordinator.update_tracking_parameters(
            ...     track_threshold=0.3,
            ...     match_threshold=0.2,
            ...     track_buffer=30
            ... )
        """
        # Validate dependencies
        if not self.validate_dependencies():
            raise CoordinatorValidationError(
                "Cannot update tracking parameters - dependencies invalid",
                context={
                    "track_threshold": track_threshold,
                    "match_threshold": match_threshold,
                },
            )

        # Validate inputs
        if track_threshold is not None:
            self._validate_type(track_threshold, (int, float), "track_threshold")
            if not 0.0 <= track_threshold <= 1.0:
                raise ValueError("track_threshold must be between 0.0 and 1.0")

        if match_threshold is not None:
            self._validate_type(match_threshold, (int, float), "match_threshold")
            if not 0.0 <= match_threshold <= 1.0:
                raise ValueError("match_threshold must be between 0.0 and 1.0")

        if track_buffer is not None:
            self._validate_type(track_buffer, int, "track_buffer")
            if track_buffer < 0:
                raise ValueError("track_buffer must be >= 0")

        # Delegate to service
        try:
            success = self.detector_service.update_tracking_parameters(
                track_threshold=track_threshold,
                match_threshold=match_threshold,
                track_buffer=track_buffer,
            )

            if success:
                # Update state
                state_update = {"tracking_parameters_updated": True}
                if track_threshold is not None:
                    state_update["track_threshold"] = track_threshold
                if match_threshold is not None:
                    state_update["match_threshold"] = match_threshold
                if track_buffer is not None:
                    state_update["track_buffer"] = track_buffer

                self._update_state(StateCategory.DETECTOR, **state_update)

                # Publish success event
                self._publish_event(
                    "TRACKING_PARAMETERS_UPDATED",
                    {
                        "track_threshold": track_threshold,
                        "match_threshold": match_threshold,
                        "track_buffer": track_buffer,
                    },
                )

                log.info(
                    "hardware_coordinator.update_tracking_parameters.success",
                    track_threshold=track_threshold,
                    match_threshold=match_threshold,
                    track_buffer=track_buffer,
                )
            else:
                log.warning("hardware_coordinator.update_tracking_parameters.failed")

            return success

        except Exception as e:
            log.exception(
                "hardware_coordinator.update_tracking_parameters.exception",
                error=str(e),
            )
            raise HardwareCoordinatorError(
                f"Failed to update tracking parameters: {e}",
                context={
                    "track_threshold": track_threshold,
                    "match_threshold": match_threshold,
                    "track_buffer": track_buffer,
                },
            ) from e

    def update_detector_parameters(
        self,
        params: dict[str, float],
        *,
        reset_overrides: bool = False,
        scope: str = "global",
    ) -> bool:
        """Update detector parameters using dict-based interface.

        Orchestrates detector parameter updates by:
        1. Validating dependencies and inputs
        2. Delegating to DetectorService.update_tracking_parameters()
        3. Updating StateManager with parameter state
        4. Publishing events for UI updates

        This method provides a dict-based interface for updating detector parameters,
        complementing the named-parameter interface of update_tracking_parameters().

        Args:
            params: Dict of parameters to update (e.g., {'conf_threshold': 0.5})
            reset_overrides: If True, reset overrides for the given scope
            scope: Whether changes apply globally or only to project ('global' or 'project')

        Returns:
            bool: True if parameters were updated successfully

        Raises:
            CoordinatorValidationError: If dependencies are invalid
            HardwareCoordinatorError: If parameter update fails
            ValueError: If scope or parameter values are invalid

        Example:
            >>> success = coordinator.update_detector_parameters(
            ...     params={'conf_threshold': 0.5, 'track_threshold': 0.3},
            ...     scope='project'
            ... )
            >>> if success:
            ...     print("Parameters updated successfully")

        Note:
            Sprint 7: Added to support MainViewModel delegation pattern.
        """
        # Validate dependencies
        if not self.validate_dependencies():
            raise CoordinatorValidationError(
                "Cannot update detector parameters - dependencies invalid",
                context={"params": params, "scope": scope},
            )

        # Validate scope
        if scope not in {"global", "project"}:
            raise ValueError(f"Invalid scope: {scope}. Must be 'global' or 'project'")

        # Delegate to service
        try:
            success = self.detector_service.update_tracking_parameters(
                params=params,
                reset_overrides=reset_overrides,
                scope=scope,
            )

            if success:
                # Update state with all parameters
                state_update = {
                    "detector_parameters_updated": True,
                    "last_update_scope": scope,
                }
                # Add all params to state
                for key, value in params.items():
                    state_update[key] = value

                self._update_state(StateCategory.DETECTOR, **state_update)

                # State update is sufficient - no need for event publication
                # (StateManager already notifies subscribers via state change callbacks)

                log.info(
                    "hardware_coordinator.update_detector_parameters.success",
                    params=params,
                    scope=scope,
                    reset_overrides=reset_overrides,
                )

            return success

        except ValueError as e:
            log.error(
                "hardware_coordinator.update_detector_parameters.validation_failed",
                error=str(e),
                params=params,
            )
            raise HardwareCoordinatorError(
                f"Parameter validation failed: {e}",
                context={"params": params, "scope": scope},
            ) from e
        except Exception as e:
            log.error(
                "hardware_coordinator.update_detector_parameters.failed",
                error=str(e),
                params=params,
            )
            raise HardwareCoordinatorError(
                f"Failed to update detector parameters: {e}",
                context={"params": params, "scope": scope},
            ) from e

    def reset_tracking_state(self) -> bool:
        """Reset the detector's tracking state.

        Orchestrates tracking state reset by:
        1. Validating dependencies
        2. Delegating to DetectorService.reset_tracking_state()
        3. Updating StateManager
        4. Publishing events for UI updates

        Returns:
            bool: True if tracking state was reset successfully

        Raises:
            CoordinatorValidationError: If dependencies are invalid
            HardwareCoordinatorError: If reset fails

        Example:
            >>> success = coordinator.reset_tracking_state()
            >>> if success:
            ...     print("Tracking state reset successfully")
        """
        # Validate dependencies
        if not self.validate_dependencies():
            raise CoordinatorValidationError(
                "Cannot reset tracking state - dependencies invalid",
                context={},
            )

        # Delegate to service
        try:
            self.detector_service.reset_tracking_state()

            # Update state
            self._update_state(
                StateCategory.DETECTOR,
                tracking_state_reset=True,
            )

            # State update is sufficient - no need for event publication
            # (StateManager already notifies subscribers via state change callbacks)

            log.info("hardware_coordinator.reset_tracking_state.success")
            return True

        except Exception as e:
            log.exception("hardware_coordinator.reset_tracking_state.exception", error=str(e))
            raise HardwareCoordinatorError(
                f"Failed to reset tracking state: {e}",
                context={},
            ) from e

    def set_single_subject_mode(self, enabled: bool) -> bool:
        """Enable or disable single subject tracking mode.

        Orchestrates single subject mode by:
        1. Validating dependencies and inputs
        2. Delegating to DetectorService.set_single_subject_mode()
        3. Updating StateManager with mode state
        4. Publishing events for UI updates

        Args:
            enabled: True to enable single subject mode, False to disable

        Returns:
            bool: True if mode was set successfully

        Raises:
            CoordinatorValidationError: If dependencies are invalid
            HardwareCoordinatorError: If mode change fails

        Example:
            >>> success = coordinator.set_single_subject_mode(enabled=True)
            >>> if success:
            ...     print("Single subject mode enabled")
        """
        # Validate dependencies
        if not self.validate_dependencies():
            raise CoordinatorValidationError(
                "Cannot set single subject mode - dependencies invalid",
                context={"enabled": enabled},
            )

        # Validate inputs
        self._validate_type(enabled, bool, "enabled")

        # Delegate to service
        try:
            self.detector_service.set_single_subject_mode(enabled=enabled)

            # Update state
            self._update_state(
                StateCategory.DETECTOR,
                single_subject_mode=enabled,
            )

            # Publish success event
            self._publish_event(
                "SINGLE_SUBJECT_MODE_CHANGED",
                {"enabled": enabled},
            )

            log.info(
                "hardware_coordinator.set_single_subject_mode.success",
                enabled=enabled,
            )
            return True

        except Exception as e:
            log.exception(
                "hardware_coordinator.set_single_subject_mode.exception",
                error=str(e),
            )
            raise HardwareCoordinatorError(
                f"Failed to set single subject mode: {e}",
                context={"enabled": enabled},
            ) from e

    def get_detector_parameters(self) -> dict[str, float]:
        """Get current detector tracking parameters.

        Delegates to DetectorService.get_detector_parameters().

        Returns:
            dict: Dictionary with current tracking parameters
                 Keys: 'track_threshold', 'match_threshold', 'track_buffer'

        Raises:
            CoordinatorValidationError: If dependencies are invalid
            HardwareCoordinatorError: If retrieval fails

        Example:
            >>> params = coordinator.get_detector_parameters()
            >>> print(f"Track threshold: {params['track_threshold']}")
        """
        # Validate dependencies
        if not self.validate_dependencies():
            raise CoordinatorValidationError(
                "Cannot get detector parameters - dependencies invalid",
                context={},
            )

        # Delegate to service
        try:
            params = self.detector_service.get_detector_parameters()
            log.debug("hardware_coordinator.get_detector_parameters", params=params)
            return params

        except Exception as e:
            log.exception("hardware_coordinator.get_detector_parameters.exception", error=str(e))
            raise HardwareCoordinatorError(
                f"Failed to get detector parameters: {e}",
                context={},
            ) from e

    def get_factory_detector_parameters(self) -> dict[str, float]:
        """Get factory default detector parameters.

        Delegates to DetectorService.get_factory_detector_parameters().

        Returns:
            dict: Dictionary with factory default tracking parameters

        Raises:
            CoordinatorValidationError: If dependencies are invalid
            HardwareCoordinatorError: If retrieval fails

        Example:
            >>> defaults = coordinator.get_factory_detector_parameters()
            >>> print(f"Default track threshold: {defaults['track_threshold']}")
        """
        # Validate dependencies
        if not self.validate_dependencies():
            raise CoordinatorValidationError(
                "Cannot get factory parameters - dependencies invalid",
                context={},
            )

        # Delegate to service
        try:
            params = self.detector_service.get_factory_detector_parameters()
            log.debug("hardware_coordinator.get_factory_detector_parameters", params=params)
            return params

        except Exception as e:
            log.exception(
                "hardware_coordinator.get_factory_detector_parameters.exception",
                error=str(e),
            )
            raise HardwareCoordinatorError(
                f"Failed to get factory detector parameters: {e}",
                context={},
            ) from e

    def restore_detector_settings(self, saved_detector_config: dict) -> bool:
        """Restore detector settings from saved configuration.

        Orchestrates settings restoration by:
        1. Validating dependencies and inputs
        2. Delegating to DetectorService.restore_detector_settings()
        3. Updating StateManager with restored state
        4. Publishing events for UI updates

        Args:
            saved_detector_config: Dictionary with saved detector configuration

        Returns:
            bool: True if settings were restored successfully

        Raises:
            CoordinatorValidationError: If dependencies are invalid
            HardwareCoordinatorError: If restoration fails

        Example:
            >>> config = {"track_threshold": 0.3, "match_threshold": 0.2}
            >>> success = coordinator.restore_detector_settings(config)
        """
        # Validate dependencies
        if not self.validate_dependencies():
            raise CoordinatorValidationError(
                "Cannot restore detector settings - dependencies invalid",
                context={},
            )

        # Validate inputs
        self._validate_type(saved_detector_config, dict, "saved_detector_config")

        # Delegate to service
        try:
            self.detector_service.restore_detector_settings(saved_detector_config)

            # Update state
            self._update_state(
                StateCategory.DETECTOR,
                settings_restored=True,
            )

            # Publish success event
            self._publish_event(
                "DETECTOR_SETTINGS_RESTORED",
                {"config": saved_detector_config},
            )

            log.info(
                "hardware_coordinator.restore_detector_settings.success",
                config_keys=list(saved_detector_config.keys()),
            )
            return True

        except Exception as e:
            log.exception(
                "hardware_coordinator.restore_detector_settings.exception",
                error=str(e),
            )
            raise HardwareCoordinatorError(
                f"Failed to restore detector settings: {e}",
                context={"config": saved_detector_config},
            ) from e

    def is_detector_initialized(self) -> bool:
        """Check if detector is initialized.

        Queries StateManager for detector initialization state.

        Returns:
            bool: True if detector is initialized

        Example:
            >>> if coordinator.is_detector_initialized():
            ...     print("Detector is ready")
        """
        detector_state = self.state_manager.get_state(StateCategory.DETECTOR)
        return detector_state.get("is_detector_initialized", False)

    def get_detector_info(self) -> dict[str, Any]:
        """Get information about current detector state.

        Queries StateManager and DetectorService for detector information.

        Returns:
            dict: Dictionary with detector information
                Keys: 'initialized', 'animal_method', 'use_openvino', 'zones_configured', etc.

        Example:
            >>> info = coordinator.get_detector_info()
            >>> print(f"Animal method: {info['animal_method']}")
        """
        detector_state = self.state_manager.get_state(StateCategory.DETECTOR)

        # Get detector parameters if initialized
        params = {}
        if self.is_detector_initialized():
            try:
                params = self.get_detector_parameters()
            except Exception as e:
                log.warning(
                    "hardware_coordinator.get_detector_info.params_unavailable",
                    error=str(e),
                )

        return {
            "initialized": detector_state.get("is_detector_initialized", False),
            "animal_method": detector_state.get("animal_method"),
            "use_openvino": detector_state.get("use_openvino", False),
            "zones_configured": detector_state.get("zones_configured", False),
            "zones_count": detector_state.get("zones_count", 0),
            "single_subject_mode": detector_state.get("single_subject_mode", False),
            "tracking_parameters": params,
        }

    # =============================================================================
    # GROUP B: MODEL DIAGNOSTICS (ModelDiagnosticsOrchestrator)
    # =============================================================================

    def run_model_diagnostic(self, config: dict):
        """Prepare for and launches the diagnostic test in a background thread.

        Now shows a progress dialog during execution.

        Args:
            config: Diagnostic configuration dictionary with:
                - video_path: Path to test video
                - frames_to_analyze: Number of frames to analyze
                - confidence_threshold: Detection confidence threshold
                - model_to_test: 'YOLO (PyTorch)', 'OpenVINO', or 'Ambos'
                - parent_dialog: Optional dialog to close after launching

        Note:
            This method validates dependencies, handles OpenVINO conversion if needed,
            creates a progress dialog, and launches the diagnostic in a background thread.
        """
        # Validate dependencies
        if not self.validate_dependencies():
            raise CoordinatorValidationError(
                "Cannot run diagnostic - dependencies invalid",
                context={"config": config},
            )

        log.info("hardware_coordinator.diagnostic.start", config=config)

        # Close the CalibrationDialog if passed
        parent_dialog = config.pop("parent_dialog", None)
        if parent_dialog:
            parent_dialog.destroy()

        if self.view:
            self.view.set_status("Iniciando diagnóstico do modelo...")
            self.view.update_idletasks()

        model_to_test = config["model_to_test"]

        # Get active weight details
        # 1. Try from config (passed by ViewModel)
        active_weight_name = config.get("active_weight_name")

        # 2. Fallback to WeightManager (if available, though typically stateless)
        if not active_weight_name:
            active_weight_name = getattr(self.weight_manager, "active_weight_name", None)

        if not active_weight_name and hasattr(self.weight_manager, "get_active_weight_name"):
            active_weight_name = self.weight_manager.get_active_weight_name()

        active_weight_details = self.weight_manager.get_weight_details(active_weight_name)

        log.info(
            "hardware_coordinator.diagnostic.active_weight",
            active_weight_name=active_weight_name,
            pytorch_path=(active_weight_details.get("path") if active_weight_details else None),
            openvino_path=(
                active_weight_details.get("openvino_path") if active_weight_details else None
            ),
        )

        if not active_weight_details:
            if self.event_bus:
                self.event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {"title": "Erro", "message": "Nenhum peso ativo selecionado."},
                )
            return

        # --- Pre-flight checks (OpenVINO conversion) ---
        if model_to_test in ["OpenVINO", "Ambos"]:
            ov_path = active_weight_details.get("openvino_path")
            # Validate that the OpenVINO directory exists AND contains .xml files
            if not _is_valid_openvino_directory(ov_path):
                log.warning(
                    "diagnostic.openvino.invalid_directory",
                    path=ov_path,
                    exists=os.path.exists(ov_path) if ov_path else False,
                )
                # Clean up corrupted/empty directory if it exists
                if ov_path and os.path.exists(ov_path) and os.path.isdir(ov_path):
                    try:
                        shutil.rmtree(ov_path, ignore_errors=True)
                        log.info("diagnostic.openvino.corrupted_directory_removed", path=ov_path)
                    except Exception as e:
                        log.warning(
                            "diagnostic.openvino.cleanup_failed", path=ov_path, error=str(e)
                        )

                if self.view and self.view.ask_ok_cancel(
                    "Converter Modelo?",
                    (
                        "O modelo OpenVINO não foi encontrado ou está incompleto. "
                        "Deseja convertê-lo agora?"
                    ),
                ):
                    # Note: This requires access to MainViewModel method
                    # In future sprints, this should be moved to ModelService
                    if hasattr(self, "_convert_weight_callback"):
                        self._convert_weight_callback(active_weight_name)
                    else:
                        log.error(
                            "hardware_coordinator.diagnostic.no_convert_callback",
                            message="Conversion callback not set",
                        )

                    # Refresh details after conversion
                    active_weight_details = self.weight_manager.get_weight_details(
                        active_weight_name
                    )
                    if not _is_valid_openvino_directory(active_weight_details.get("openvino_path")):
                        if self.event_bus:
                            self.event_bus.publish_event(
                                Events.UI_SHOW_ERROR,
                                {"title": "Erro", "message": "A conversão para OpenVINO falhou."},
                            )
                        return
                else:
                    log.warning("diagnostic.openvino.conversion_skipped")
                    # If user skips conversion, modify config to only run YOLO if possible
                    if model_to_test == "Ambos":
                        config["model_to_test"] = "YOLO (PyTorch)"
                    else:  # model_to_test was 'OpenVINO'
                        if self.event_bus:
                            self.event_bus.publish_event(
                                Events.UI_SET_STATUS, {"message": "Diagnóstico cancelado."}
                            )
                        return

        # --- Create and show progress dialog ---
        from zebtrack.ui.dialogs import DiagnosticProgressDialog

        progress_dialog = DiagnosticProgressDialog(self.root) if self.root else None
        config["progress_dialog"] = progress_dialog

        # --- Launch background thread ---
        if self.cancel_event:
            self.cancel_event.clear()

        thread = threading.Thread(
            target=self._diagnostic_processing_thread,
            args=(config, active_weight_details),
            daemon=True,
        )
        thread.start()

    def _diagnostic_processing_thread(self, config: dict, weight_details: dict):
        """Run actual diagnostic processing logic in a background thread.

        Updates progress dialog during execution.

        Args:
            config: Diagnostic configuration
            weight_details: Active weight details from WeightManager
        """
        video_path = config["video_path"]
        frames_to_analyze = config["frames_to_analyze"]
        conf_threshold = config["confidence_threshold"]
        model_to_test = config["model_to_test"]
        progress_dialog = config.get("progress_dialog")
        results: dict[str, list] = {}

        try:
            self._update_diagnostic_progress(progress_dialog, "Carregando modelos...")

            yolo_model = self._initialize_diagnostic_yolo_model(
                model_to_test, weight_details, results, progress_dialog
            )

            openvino_model = self._initialize_diagnostic_openvino_model(
                model_to_test, weight_details, results, progress_dialog
            )

            self._run_diagnostic_frame_loop(
                video_path,
                frames_to_analyze,
                conf_threshold,
                yolo_model,
                openvino_model,
                results,
                progress_dialog,
            )

            self._finish_progress_dialog(progress_dialog)

            # --- Schedule report generation on main thread ---
            if self.root:
                self.root.after(0, self._finish_diagnostic_and_save_report, config, results)
            else:
                self._finish_diagnostic_and_save_report(config, results)

        except DiagnosticAbortError:
            # DiagnosticAbortError is raised to abort diagnostics (e.g., user cancellation).
            # No further action needed; abort is intentional and handled gracefully.
            pass
        except Exception as e:
            log.error("diagnostic.thread.load_error", exc_info=True)
            self._finish_progress_dialog(progress_dialog)
            if self.event_bus:
                self.event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {"title": "Erro ao Carregar Modelo", "message": f"Falha: {e}"},
                )

    def _update_diagnostic_progress(
        self,
        progress_dialog,
        message: str,
        current: int | None = None,
        total: int | None = None,
    ) -> None:
        """Thread-safe progress dialog update helper.

        Args:
            progress_dialog: DiagnosticProgressDialog instance
            message: Status message to display
            current: Current progress value
            total: Total progress value
        """
        if not progress_dialog or not self.root:
            return

        def _update():
            if hasattr(progress_dialog, "update_progress"):
                progress_dialog.update_progress(message, current, total)

        self.root.after(0, _update)

    def _finish_progress_dialog(self, progress_dialog) -> None:
        """Safely close the diagnostic progress dialog.

        Args:
            progress_dialog: DiagnosticProgressDialog instance
        """
        if not progress_dialog or not self.root:
            return

        def _finish():
            if hasattr(progress_dialog, "destroy"):
                try:
                    progress_dialog.destroy()
                except Exception as e:
                    log.warning("hardware_coordinator.finish_progress.error", error=str(e))

        self.root.after(0, _finish)

    def _initialize_diagnostic_yolo_model(
        self,
        model_to_test: str,
        weight_details: dict,
        results: dict[str, list],
        progress_dialog,
    ) -> Any | None:
        """Set up YOLO model for diagnostics.

        Args:
            model_to_test: Model type to test
            weight_details: Active weight details
            results: Results dictionary to populate
            progress_dialog: Progress dialog instance

        Returns:
            YOLO model instance or None

        Raises:
            DiagnosticAbortError: If YOLO setup fails
        """
        if model_to_test not in ["YOLO (PyTorch)", "Ambos"]:
            return None

        if not ULTRALYTICS_AVAILABLE:
            log.error("diagnostic.yolo.unavailable")
            self._finish_progress_dialog(progress_dialog)
            if self.event_bus:
                self.event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro",
                        "message": "YOLO não está disponível (ultralytics não instalado)",
                    },
                )
            raise DiagnosticAbortError from None

        if YOLO is None:  # Defensive guard for type checkers.
            raise DiagnosticAbortError from None

        yolo_ctor = cast(Any, YOLO)
        yolo_model = yolo_ctor(weight_details["path"])
        if hasattr(yolo_model, "set_context"):
            yolo_model.set_context("diagnostic")
            log.info("diagnostic.thread.yolo_context_set", context="diagnostic")
        results["YOLO (PyTorch)"] = []
        return yolo_model

    def _initialize_diagnostic_openvino_model(
        self,
        model_to_test: str,
        weight_details: dict,
        results: dict[str, list],
        progress_dialog,
    ) -> Any | None:
        """Set up OpenVINO model for diagnostics.

        Args:
            model_to_test: Model type to test
            weight_details: Active weight details
            results: Results dictionary to populate
            progress_dialog: Progress dialog instance

        Returns:
            OpenVINO model instance or None

        Raises:
            DiagnosticAbortError: If OpenVINO setup fails
        """
        if model_to_test not in ["OpenVINO", "Ambos"]:
            return None

        ov_path = weight_details.get("openvino_path")

        if not _is_valid_openvino_directory(ov_path):
            log.error(
                "diagnostic.thread.openvino_invalid",
                path=ov_path,
                exists=os.path.exists(ov_path) if ov_path else False,
            )
            self._finish_progress_dialog(progress_dialog)
            if self.event_bus:
                self.event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro de Modelo",
                        "message": (
                            "O diretório do modelo OpenVINO não contém arquivos "
                            ".xml necessários. Por favor, reconverta o modelo."
                        ),
                    },
                )
            raise DiagnosticAbortError from None

        plugin_class = DETECTOR_PLUGINS.get("OpenVINO")
        if not plugin_class:
            log.error("diagnostic.thread.openvino_plugin_missing")
            self._finish_progress_dialog(progress_dialog)
            if self.event_bus:
                self.event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro de Plugin",
                        "message": "Plugin OpenVINO não encontrado para diagnóstico.",
                    },
                )
            raise DiagnosticAbortError from None

        openvino_model = plugin_class(ov_path)
        if not hasattr(openvino_model, "predict"):
            log.error(
                "diagnostic.thread.missing_predict_method",
                plugin_class=str(plugin_class),
            )
            self._finish_progress_dialog(progress_dialog)
            if self.event_bus:
                self.event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro de Plugin",
                        "message": "O plugin OpenVINO não possui o método predict necessário.",
                    },
                )
            raise DiagnosticAbortError from None

        if hasattr(openvino_model, "set_context"):
            openvino_model.set_context("diagnostic")
            log.info("diagnostic.thread.openvino_context_set", context="diagnostic")

        results["OpenVINO"] = []
        log.info("diagnostic.thread.openvino_loaded", path=ov_path)
        return openvino_model

    def _run_diagnostic_frame_loop(
        self,
        video_path: str,
        frames_to_analyze: int,
        conf_threshold: float,
        yolo_model,
        openvino_model,
        results: dict[str, list],
        progress_dialog,
    ) -> None:
        """Process video frames for the diagnostic routine.

        Args:
            video_path: Path to video file
            frames_to_analyze: Number of frames to process
            conf_threshold: Confidence threshold for detections
            yolo_model: YOLO model instance or None
            openvino_model: OpenVINO model instance or None
            results: Results dictionary to populate
            progress_dialog: Progress dialog instance

        Raises:
            DiagnosticAbortError: If processing is cancelled or fails
        """
        cap = cv2.VideoCapture(video_path)

        if not cap.isOpened():
            self._finish_progress_dialog(progress_dialog)
            if self.event_bus:
                self.event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro",
                        "message": f"Não foi possível abrir o vídeo: {video_path}",
                    },
                )
            raise DiagnosticAbortError from None

        try:
            for frame_count in range(frames_to_analyze):
                if self.cancel_event and self.cancel_event.is_set():
                    log.info("diagnostic.thread.cancelled_by_event")
                    self._finish_progress_dialog(progress_dialog)
                    return

                if progress_dialog and getattr(progress_dialog, "user_cancelled", False):
                    log.info("diagnostic.thread.cancelled_by_user")
                    self._finish_progress_dialog(progress_dialog)
                    return

                ret, frame = cap.read()
                if not ret:
                    break

                status_msg = f"Analisando frame {frame_count + 1}/{frames_to_analyze}..."
                self._update_diagnostic_progress(
                    progress_dialog,
                    status_msg,
                    frame_count + 1,
                    frames_to_analyze,
                )

                if self.event_bus:
                    self.event_bus.publish_event(Events.UI_SET_STATUS, {"message": status_msg})

                if yolo_model is not None:
                    preds = yolo_model.predict(frame, conf=conf_threshold, verbose=False)
                    results.setdefault("YOLO (PyTorch)", []).append(preds[0])

                if openvino_model is not None:
                    try:
                        log.debug(
                            "diagnostic.thread.openvino_predict_start",
                            frame=frame_count + 1,
                        )
                        preds = openvino_model.predict(frame, conf_threshold)
                        log.debug(
                            "diagnostic.thread.openvino_predict_success",
                            frame=frame_count + 1,
                            detections=len(preds),
                        )
                        results.setdefault("OpenVINO", []).append(preds)
                    except Exception as exc:  # pragma: no cover - plugin specific
                        log.error(
                            "diagnostic.thread.openvino_predict_error",
                            frame=frame_count + 1,
                            exc_info=True,
                        )
                        self._finish_progress_dialog(progress_dialog)
                        if self.event_bus:
                            self.event_bus.publish_event(
                                Events.UI_SHOW_ERROR,
                                {
                                    "title": "Erro de Inferência OpenVINO",
                                    "message": (
                                        f"Falha na inferência do frame {frame_count + 1}: {exc}"
                                    ),
                                },
                            )
                        raise DiagnosticAbortError from None
        finally:
            cap.release()

    def _finish_diagnostic_and_save_report(self, config, results):
        """Format and saves the report. Runs on the main UI thread.

        Args:
            config: Diagnostic configuration
            results: Diagnostic results from processing
        """
        report_str = self._format_diagnostic_report(config, results)

        if not self.view:
            log.warning("hardware_coordinator.diagnostic.no_view_for_save")
            return

        save_path = self.view.ask_save_filename(
            title="Salvar Relatório de Diagnóstico",
            defaultextension=".txt",
            initialfile="diagnostic_report.txt",
            filetypes=[("Arquivos de Texto", "*.txt")],
        )

        if save_path:
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(report_str)
                if self.event_bus:
                    self.event_bus.publish_event(
                        Events.UI_SHOW_INFO,
                        {
                            "title": "Sucesso",
                            "message": f"Relatório de diagnóstico salvo em:\n{save_path}",
                        },
                    )
            except OSError as e:
                if self.event_bus:
                    self.event_bus.publish_event(
                        Events.UI_SHOW_ERROR,
                        {
                            "title": "Erro ao Salvar",
                            "message": f"Não foi possível salvar o arquivo: {e}",
                        },
                    )

        if self.event_bus:
            self.event_bus.publish_event(
                Events.UI_SET_STATUS, {"message": "Diagnóstico concluído. Pronto."}
            )

    def _format_diagnostic_report(self, config, results) -> str:
        """Format the collected diagnostic data into a string.

        Args:
            config: Diagnostic configuration
            results: Diagnostic results from processing

        Returns:
            Formatted report string
        """
        report_lines = [
            "Relatório de Diagnóstico do Modelo",
            "-----------------------------------",
            f"- Vídeo: {config['video_path']}",
            f"- Frames Analisados: {config['frames_to_analyze']}",
            f"- Limiar de Confiança: {config['confidence_threshold']}",
            "-----------------------------------",
            "",
        ]

        for model_name, preds_list in results.items():
            report_lines.append(f"--- [ RESULTADOS {model_name.upper()} ] ---")
            report_lines.append("")

            for i, preds in enumerate(preds_list):
                frame_num = i + 1
                report_lines.append(f"Frame {frame_num}:")

                detections = []
                mask_only_detections = []

                # Handle ultralytics results object
                if hasattr(preds, "boxes") or hasattr(preds, "masks"):
                    # Processa boxes com suas máscaras
                    if preds.boxes is not None:
                        for j, box in enumerate(preds.boxes):
                            class_id = int(box.cls)
                            class_name = preds.names.get(class_id, "desconhecido")
                            conf = float(box.conf)
                            bbox = [int(coord) for coord in box.xyxy[0]]

                            # Verifica se tem máscara
                            has_mask = (
                                preds.masks is not None
                                and preds.masks.xy is not None
                                and j < len(preds.masks.xy)
                            )
                            mask_info = (
                                f", Máscara: {len(preds.masks.xy[j])} pontos" if has_mask else ""
                            )

                            detections.append(
                                f"  - Classe {class_id} ('{class_name}'), "
                                f"Conf: {conf:.2f}, BBox: {bbox}{mask_info}"
                            )

                    # Processa máscaras sem boxes (órfãs)
                    if preds.masks is not None and preds.masks.xy is not None:
                        num_boxes = len(preds.boxes) if preds.boxes else 0
                        for j in range(num_boxes, len(preds.masks.xy)):
                            mask = preds.masks.xy[j]
                            x_min = int(mask[:, 0].min())
                            y_min = int(mask[:, 1].min())
                            x_max = int(mask[:, 0].max())
                            y_max = int(mask[:, 1].max())
                            area = (x_max - x_min) * (y_max - y_min)

                            mask_only_detections.append(
                                f"  - [MÁSCARA SEM BOX] Provável Aquário, "
                                f"BBox aprox: [{x_min}, {y_min}, {x_max}, {y_max}], "
                                f"Área: {area}, Pontos: {len(mask)}"
                            )

                # Handle OpenVINO plugin format
                elif isinstance(preds, list):
                    for det in preds:
                        class_id = det["class_id"]
                        class_name = det["class_name"]
                        conf = det["confidence"]
                        bbox = det["box"]
                        mask_info = (
                            f", Máscara: {det.get('mask_points', 0)} pontos"
                            if det.get("has_mask")
                            else ""
                        )

                        detections.append(
                            f"  - Classe {class_id} ('{class_name}'), "
                            f"Conf: {conf:.2f}, BBox: {bbox}{mask_info}"
                        )

                # Adiciona detecções ao relatório
                if detections:
                    report_lines.extend(detections)
                if mask_only_detections:
                    report_lines.append("  Máscaras sem bounding box (possíveis aquários):")
                    report_lines.extend(mask_only_detections)
                if not detections and not mask_only_detections:
                    report_lines.append("  - Nenhuma detecção encontrada.")

                report_lines.append("")

            report_lines.append("")  # Spacer between models

        return "\n".join(report_lines)

    # =============================================================================
    # GROUP C: UTILITY METHODS
    # =============================================================================

    def set_convert_weight_callback(self, callback):
        """Set callback for OpenVINO weight conversion.

        This is a temporary bridge method until conversion is moved to ModelService.

        Args:
            callback: Function to call for weight conversion
        """
        self._convert_weight_callback = callback

    def set_recording_callbacks(
        self,
        trigger_callback: Callable[[int], None] | None,
        stop_callback: Callable[[], None] | None,
    ) -> None:
        """Set callbacks for recording events from session coordinator.

        This method allows the SessionCoordinator to register callbacks that will
        be invoked when recording operations are needed. This is part of the
        coordinator integration pattern.

        Args:
            trigger_callback: Function to call when recording should start.
                            Accepts event_code (int) as parameter.
            stop_callback: Function to call when recording should stop.
                          No parameters.
        """
        self._trigger_recording_callback = trigger_callback
        self._stop_recording_callback = stop_callback
        log.info(
            "hardware_coordinator.recording_callbacks_set",
            has_trigger=trigger_callback is not None,
            has_stop=stop_callback is not None,
        )

    def __repr__(self) -> str:
        """Return string representation of HardwareCoordinator."""
        initialized = self.is_detector_initialized()
        info = self.get_detector_info() if initialized else {}
        return (
            f"<HardwareCoordinator("
            f"initialized={initialized}, "
            f"method={info.get('animal_method', 'N/A')}, "
            f"openvino={info.get('use_openvino', False)}, "
            f"zones={info.get('zones_count', 0)}"
            f")>"
        )
