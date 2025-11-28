"""Detector Coordinator - Sprint 5.

Orchestrates detector setup, zone configuration, and tracking parameter management.
Delegates business logic to DetectorService.

Sprint: 5 of REFACTOR-MASTER-PLAN-2025.md
Extracted from: HardwareCoordinator detector-related methods
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.coordinators.base import (
    BaseCoordinator,
    CoordinatorValidationError,
)
from zebtrack.core.state_manager import StateCategory

if TYPE_CHECKING:
    from zebtrack.core.detector_service import DetectorService
    from zebtrack.core.model_service import ModelService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.weight_manager import WeightManager
    from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


class DetectorCoordinatorError(Exception):
    """Base exception for DetectorCoordinator errors."""

    def __init__(self, message: str, context: dict[str, Any] | None = None):
        """Initialize exception with message and optional context.

        Args:
            message: Error message
            context: Optional context dictionary
        """
        super().__init__(message)
        self.context = context or {}


class DetectorCoordinator(BaseCoordinator):
    """
    Coordinator for detector setup and configuration workflows.

    Orchestrates:
    - Detector initialization (YOLO/OpenVINO)
    - Zone configuration and scaling
    - Tracking parameter management (ByteTrack)
    - Single subject mode configuration
    - Detector settings persistence and restoration

    Delegates to:
    - DetectorService: Core detector operations
    - ModelService: Model and weight management
    - WeightManager: Active weight resolution
    - StateManager: Detector state persistence
    - EventBus: UI notifications

    Sprint 5: Extracted from HardwareCoordinator
    Related: REFACTOR-MASTER-PLAN-2025.md
    """

    def __init__(
        self,
        state_manager: StateManager,
        detector_service: DetectorService,
        model_service: ModelService | None = None,
        weight_manager: WeightManager | None = None,
        event_bus: EventBus | None = None,
    ):
        """Initialize DetectorCoordinator with dependency injection.

        Args:
            state_manager: StateManager for centralized state tracking
            detector_service: DetectorService for detector operations
            model_service: ModelService for model/weight management (optional)
            weight_manager: WeightManager for active weight resolution (optional)
            event_bus: EventBus for UI notifications (optional)
        """
        super().__init__(state_manager=state_manager, event_bus=event_bus)
        self.detector_service = detector_service
        self.model_service = model_service
        self.weight_manager = weight_manager

        log.info(
            "detector_coordinator.initialized",
            has_model_service=model_service is not None,
            has_weight_manager=weight_manager is not None,
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
                    "coordinator": "DetectorCoordinator",
                    "missing_dependency": "detector_service",
                },
            )
        return True

    def setup_detector(
        self,
        animal_method: str | None = None,
        use_openvino: bool = False,
        active_weight_name: str | None = None,
        detector_plugins: dict | None = None,
    ) -> tuple[bool, str | None]:
        """
        Initialize the detector instance based on configuration.

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
            DetectorCoordinatorError: If detector initialization fails

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

                # Publish success event
                self._publish_event(
                    "DETECTOR_INITIALIZED",
                    {
                        "animal_method": animal_method,
                        "use_openvino": use_openvino,
                        "active_weight_name": active_weight_name,
                    },
                )

                log.info(
                    "detector_coordinator.setup_detector.success",
                    animal_method=animal_method,
                    use_openvino=use_openvino,
                )
            else:
                log.error(
                    "detector_coordinator.setup_detector.failed",
                    error=error_message,
                    animal_method=animal_method,
                    use_openvino=use_openvino,
                )

            return success, error_message

        except Exception as e:
            log.exception(
                "detector_coordinator.setup_detector.exception",
                error=str(e),
                animal_method=animal_method,
            )
            raise DetectorCoordinatorError(
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
        """
        Configure zones for the detector.

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
            DetectorCoordinatorError: If zone configuration fails

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
                    "detector_coordinator.configure_zones.success",
                    zones_count=len(zones_data) if zones_data else 0,
                )
            else:
                log.warning("detector_coordinator.configure_zones.failed")

            return success

        except Exception as e:
            log.exception("detector_coordinator.configure_zones.exception", error=str(e))
            raise DetectorCoordinatorError(
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
        """
        Update ByteTrack tracking parameters.

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
            DetectorCoordinatorError: If parameter update fails
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
                    "detector_coordinator.update_tracking_parameters.success",
                    track_threshold=track_threshold,
                    match_threshold=match_threshold,
                    track_buffer=track_buffer,
                )
            else:
                log.warning("detector_coordinator.update_tracking_parameters.failed")

            return success

        except Exception as e:
            log.exception(
                "detector_coordinator.update_tracking_parameters.exception",
                error=str(e),
            )
            raise DetectorCoordinatorError(
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
        """
        Update detector parameters using dict-based interface.

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
            DetectorCoordinatorError: If parameter update fails
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
                # Update state with filtered parameters
                state_update = {
                    "detector_parameters_updated": True,
                    # Store scope if you want to track it in generic state, but verify model support
                    # "last_update_scope": scope, 
                }
                
                # Map and filter params for state update
                # Valid keys from DetectorState: conf_threshold, track_threshold, match_threshold, track_buffer
                valid_state_keys = {"conf_threshold", "track_threshold", "match_threshold", "track_buffer"}
                
                for key, value in params.items():
                    # Map confidence_threshold to conf_threshold
                    if key == "confidence_threshold":
                        state_update["conf_threshold"] = value
                    elif key in valid_state_keys:
                        state_update[key] = value
                    # Ignore other keys for state update to avoid warnings

                self._update_state(StateCategory.DETECTOR, **state_update)

                # State update is sufficient - no need for event publication
                # (StateManager already notifies subscribers via state change callbacks)

                log.info(
                    "detector_coordinator.update_detector_parameters.success",
                    params=params,
                    scope=scope,
                    reset_overrides=reset_overrides,
                )

            return success

        except ValueError as e:
            log.error(
                "detector_coordinator.update_detector_parameters.validation_failed",
                error=str(e),
                params=params,
            )
            raise DetectorCoordinatorError(
                f"Parameter validation failed: {e}",
                context={"params": params, "scope": scope},
            ) from e
        except Exception as e:
            log.error(
                "detector_coordinator.update_detector_parameters.failed",
                error=str(e),
                params=params,
            )
            raise DetectorCoordinatorError(
                f"Failed to update detector parameters: {e}",
                context={"params": params, "scope": scope},
            ) from e

    def reset_tracking_state(self) -> bool:
        """
        Reset the detector's tracking state.

        Orchestrates tracking state reset by:
        1. Validating dependencies
        2. Delegating to DetectorService.reset_tracking_state()
        3. Updating StateManager
        4. Publishing events for UI updates

        Returns:
            bool: True if tracking state was reset successfully

        Raises:
            CoordinatorValidationError: If dependencies are invalid
            DetectorCoordinatorError: If reset fails

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

            log.info("detector_coordinator.reset_tracking_state.success")
            return True

        except Exception as e:
            log.exception("detector_coordinator.reset_tracking_state.exception", error=str(e))
            raise DetectorCoordinatorError(
                f"Failed to reset tracking state: {e}",
                context={},
            ) from e

    def set_single_subject_mode(self, enabled: bool) -> bool:
        """
        Enable or disable single subject tracking mode.

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
            DetectorCoordinatorError: If mode change fails

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
                "detector_coordinator.set_single_subject_mode.success",
                enabled=enabled,
            )
            return True

        except Exception as e:
            log.exception(
                "detector_coordinator.set_single_subject_mode.exception",
                error=str(e),
            )
            raise DetectorCoordinatorError(
                f"Failed to set single subject mode: {e}",
                context={"enabled": enabled},
            ) from e

    def get_detector_parameters(self) -> dict[str, float]:
        """
        Get current detector tracking parameters.

        Delegates to DetectorService.get_detector_parameters().

        Returns:
            dict: Dictionary with current tracking parameters
                 Keys: 'track_threshold', 'match_threshold', 'track_buffer'

        Raises:
            CoordinatorValidationError: If dependencies are invalid
            DetectorCoordinatorError: If retrieval fails

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
            log.debug("detector_coordinator.get_detector_parameters", params=params)
            return params

        except Exception as e:
            log.exception("detector_coordinator.get_detector_parameters.exception", error=str(e))
            raise DetectorCoordinatorError(
                f"Failed to get detector parameters: {e}",
                context={},
            ) from e

    def get_factory_detector_parameters(self) -> dict[str, float]:
        """
        Get factory default detector parameters.

        Delegates to DetectorService.get_factory_detector_parameters().

        Returns:
            dict: Dictionary with factory default tracking parameters

        Raises:
            CoordinatorValidationError: If dependencies are invalid
            DetectorCoordinatorError: If retrieval fails

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
            log.debug("detector_coordinator.get_factory_detector_parameters", params=params)
            return params

        except Exception as e:
            log.exception(
                "detector_coordinator.get_factory_detector_parameters.exception",
                error=str(e),
            )
            raise DetectorCoordinatorError(
                f"Failed to get factory detector parameters: {e}",
                context={},
            ) from e

    def restore_detector_settings(self, saved_detector_config: dict) -> bool:
        """
        Restore detector settings from saved configuration.

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
            DetectorCoordinatorError: If restoration fails

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
                "detector_coordinator.restore_detector_settings.success",
                config_keys=list(saved_detector_config.keys()),
            )
            return True

        except Exception as e:
            log.exception(
                "detector_coordinator.restore_detector_settings.exception",
                error=str(e),
            )
            raise DetectorCoordinatorError(
                f"Failed to restore detector settings: {e}",
                context={"config": saved_detector_config},
            ) from e

    def is_detector_initialized(self) -> bool:
        """
        Check if detector is initialized.

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
        """
        Get information about current detector state.

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
                    "detector_coordinator.get_detector_info.params_unavailable",
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

    def __repr__(self) -> str:
        """Return string representation of DetectorCoordinator."""
        initialized = self.is_detector_initialized()
        info = self.get_detector_info() if initialized else {}
        return (
            f"<DetectorCoordinator("
            f"initialized={initialized}, "
            f"method={info.get('animal_method', 'N/A')}, "
            f"openvino={info.get('use_openvino', False)}, "
            f"zones={info.get('zones_count', 0)}"
            f")>"
        )
