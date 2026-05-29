"""Project Lifecycle Coordinator - Phase 3 Super Coordinator.

Thin coordinator for project lifecycle and asset management.
Delegates model-override logic to ModelOverrideService and calibration
logic to CalibrationCoordinator (Phase 5B decomposition).

Consolidates:
- ProjectOrchestrator (Sprint 27)  — Groups A + B retained here
- CalibrationOrchestrator (Sprint 32) — delegated to CalibrationCoordinator
- Model Override management — delegated to ModelOverrideService

CRITICAL: No dependency on MainViewModel. All dependencies injected explicitly.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import structlog

from zebtrack.coordinators.base_coordinator import BaseCoordinator
from zebtrack.core.project.project_manager import AssetType
from zebtrack.ui import payloads as payloads
from zebtrack.ui.event_bus_v2 import UIEvents

if TYPE_CHECKING:
    from zebtrack.coordinators.calibration_coordinator import (
        CalibrationCoordinator as CalibrationCoordinatorType,
    )
    from zebtrack.core.detection.calibration import Calibration
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.project.project_workflow_service import ProjectWorkflowService
    from zebtrack.core.recording.live_camera_service import LiveCameraService
    from zebtrack.core.services.detector_service import DetectorService
    from zebtrack.core.services.model_override_service import ModelOverrideService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2
    from zebtrack.ui.project_workflow_adapter import ProjectWorkflowAdapter

log = structlog.get_logger()


def _payload_get(payload: payloads.EventPayload | dict[str, Any], key: str, default=None):
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


class ProjectLifecycleCoordinator(BaseCoordinator):
    """Thin coordinator for project lifecycle and asset management.

    Responsibilities (retained):
    - Project lifecycle (create, open, close)
    - Project asset management (delete, validate, register outputs)
    - Zone setup from project data
    - Event handling (aquarium config updates)

    Delegated (Phase 5B):
    - Model override management → ModelOverrideService
    - Calibration scope/context → CalibrationCoordinator

    Phase 3: Consolidates ProjectOrchestrator + CalibrationOrchestrator
    Phase 5B: Decomposed into thin coordinator + 2 delegates
    """

    def __init__(
        self,
        state_manager: StateManager,
        project_manager: ProjectManager,
        project_workflow_service: ProjectWorkflowService,
        project_workflow_adapter: ProjectWorkflowAdapter,
        settings_obj: Settings,
        event_bus: EventBusV2 | None = None,
        detector_service: DetectorService | None = None,
        model_override_service: ModelOverrideService | None = None,
        calibration_coordinator: CalibrationCoordinatorType | None = None,
        live_camera_service: LiveCameraService | None = None,
    ):
        """Initialize ProjectLifecycleCoordinator with dependency injection.

        Args:
            state_manager: StateManager for state updates
            project_manager: ProjectManager for project operations
            project_workflow_service: Service for project workflow logic
            project_workflow_adapter: Adapter for workflow coordination
            settings_obj: Settings instance
            event_bus: Optional EventBus for publishing events
            detector_service: Optional DetectorService for detector setup callbacks
            model_override_service: Optional delegate for model override logic
            calibration_coordinator: Optional delegate for calibration logic
            live_camera_service: Optional LiveCameraService used to stop a
                running live session before the project state is reset on
                close (prevents camera lock and worker-thread leaks).

        Note:
            NEVER pass MainViewModel. All dependencies must be explicit.
        """
        super().__init__(state_manager, event_bus)
        self.project_manager = project_manager
        self.project_workflow_service = project_workflow_service
        self.project_workflow_adapter = project_workflow_adapter
        self.settings = settings_obj
        self.detector_service = detector_service
        self.live_camera_service = live_camera_service

        # Phase 5B delegates
        self._model_override_service = model_override_service
        self._calibration_coordinator = calibration_coordinator

        # Backward-compat: expose state via properties for callers that
        # read _using_project_overrides / _global_model_defaults directly.
        if model_override_service is None:
            self._using_project_overrides: bool = False
            self._global_model_defaults: dict[str, Any] = {}

        # Zone manager reference for aquarium config updates
        self._zone_manager: Any = None

        log.info("project_lifecycle_coordinator.initialized")

    def register_event_handlers(self, zone_manager: Any = None) -> None:
        """Register event handlers for project lifecycle events.

        Phase 5: Added for multi-aquarium event handling.

        Args:
            zone_manager: Optional ZoneManager for aquarium config updates
        """
        if zone_manager:
            self._zone_manager = zone_manager

        if not self.event_bus:
            return

        # Subscribe to aquarium config update events
        self.event_bus.subscribe(
            UIEvents.ZONE_AQUARIUM_CONFIG_UPDATED,
            self._handle_aquarium_config_updated,
        )

        log.info("project_lifecycle_coordinator.register_handlers.complete")

    def _handle_aquarium_config_updated(self, payload: payloads.EventPayload) -> None:
        """Handle aquarium configuration update event.

        Phase 5: Updates aquarium configuration in zone data.

        Args:
            payload: Event payload with aquarium_id, config, and video_path.
        """
        aquarium_id = _payload_get(payload, "aquarium_id")
        config = _payload_get(payload, "config")
        video_path = _payload_get(payload, "video_path")

        if aquarium_id is None or not config or not video_path:
            log.warning(
                "aquarium_config_update.missing_data",
                has_id=aquarium_id is not None,
                has_config=bool(config),
                has_video=bool(video_path),
            )
            return

        if not self._zone_manager:
            log.warning("aquarium_config_update.no_zone_manager")
            return

        try:
            zone_data = self._zone_manager.get_multi_aquarium_zone_data(
                self.project_manager.project_data, video_path
            )
            if not zone_data:
                log.warning(
                    "aquarium_config_update.no_zone_data",
                    video_path=str(video_path),
                )
                return

            aquarium = zone_data.get_aquarium(aquarium_id)
            if not aquarium:
                log.warning(
                    "aquarium_config_update.aquarium_not_found",
                    aquarium_id=aquarium_id,
                )
                return

            # Update aquarium config
            if hasattr(config, "group"):
                aquarium.group = config.group
            elif isinstance(config, dict):
                aquarium.group = config.get("group", aquarium.group)

            if hasattr(config, "subject_id"):
                aquarium.subject_id = config.subject_id
            elif isinstance(config, dict):
                aquarium.subject_id = config.get("subject_id", aquarium.subject_id)

            if hasattr(config, "day"):
                aquarium.day = config.day
            elif isinstance(config, dict):
                aquarium.day = config.get("day", aquarium.day)

            # Save updated zone data
            self._zone_manager.save_multi_aquarium_zone_data(video_path, zone_data)

            log.info(
                "aquarium_config_update.success",
                aquarium_id=aquarium_id,
                video_path=str(video_path),
            )

        except Exception as e:  # except Exception justified: event handler fault isolation
            log.error(
                "aquarium_config_update.failed",
                aquarium_id=aquarium_id,
                error=str(e),
            )

    # ========================================================================
    # Group A: Project Lifecycle (create, open, close)
    # ========================================================================

    def _stop_live_session_if_active(self) -> None:
        """Stop a running live camera session, if any.

        Called from ``close_project`` so that switching/closing a project
        while the live pipeline is recording cleanly releases the camera,
        joins worker threads, and finalizes the recorder before the
        project state is wiped.
        """
        live_service = self.live_camera_service
        if live_service is None:
            return
        is_active_fn = getattr(live_service, "is_session_active", None)
        if not callable(is_active_fn) or not is_active_fn():
            return
        try:
            live_service.stop_session()
            self.logger.info("project.close.live_session_stopped")
        # except Exception justified: cleanup boundary — never block close
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.warning(
                "project.close.live_session_stop_failed", error=str(exc), exc_info=True
            )

    def close_project(
        self,
        *,
        restore_global_defaults_callback: Callable[[], None] | None = None,
    ) -> ProjectManager:
        """Close the current project.

        Args:
            restore_global_defaults_callback: Optional callback to restore global model defaults

        Returns:
            New ProjectManager instance

        Phase 3: Consolidated from ProjectOrchestrator.close_project
        """
        self.logger.info("project.close.start")

        # Stop any active live camera session BEFORE resetting project
        # state. Otherwise capture/processing/recording threads keep
        # holding the camera handle and writing into the about-to-be-
        # invalidated project folder.
        self._stop_live_session_if_active()

        # Delegate to adapter which handles all UI coordination
        new_project_manager = self.project_workflow_adapter.close_project(
            restore_global_defaults_callback=restore_global_defaults_callback
            or (
                self._model_override_service.restore_global_model_defaults
                if self._model_override_service
                else self._restore_global_model_defaults
            ),
            settings_obj=self.settings,
        )

        # Update reference
        self.project_manager = new_project_manager

        # Notify all services about the new project manager
        self._publish_event(
            UIEvents.PROJECT_MANAGER_REPLACED,
            payloads.ProjectManagerReplacedPayload(new_manager=new_project_manager),
        )
        self._publish_event(UIEvents.PROJECT_CLOSED, payloads.EmptyPayload())
        self.logger.info("project.close.complete")

        return new_project_manager

    def create_project(
        self,
        *,
        setup_detector_callback: Callable[[str | None], bool] | None = None,
        set_active_weight_callback: Callable[[str], None] | None = None,
        set_openvino_usage_callback: Callable[[bool], None] | None = None,
        update_openvino_status_callback: Callable[[], None] | None = None,
        get_active_weight_name: Callable[[], str] | None = None,
        get_use_openvino: Callable[[], bool] | None = None,
        apply_wizard_overrides_callback: Callable[[dict], None] | None = None,
        **wizard_data,
    ) -> bool:
        """Create new project with wizard data."""
        self.logger.info("project.create.start", wizard_data_keys=list(wizard_data.keys()))

        setup_detector = setup_detector_callback or self._default_setup_detector
        set_active_weight = set_active_weight_callback or self._default_set_active_weight
        set_openvino_usage = set_openvino_usage_callback or self._default_set_openvino_usage
        update_openvino_status = (
            update_openvino_status_callback or self._default_update_openvino_status
        )
        get_active_weight_name = get_active_weight_name or self._default_get_active_weight_name
        get_use_openvino = get_use_openvino or self._default_get_use_openvino
        apply_wizard_overrides = (
            apply_wizard_overrides_callback or self._default_apply_wizard_overrides
        )

        self.project_workflow_service.set_global_model_defaults(
            active_weight=get_active_weight_name() or None,
            use_openvino=get_use_openvino(),
        )

        result = self.project_workflow_service.create_project(
            active_weight_setter=set_active_weight,
            use_openvino_setter=set_openvino_usage,
            **wizard_data,
        )

        if not result["success"]:
            self._publish_event(
                UIEvents.SHOW_ERROR,
                payloads.MessagePayload(
                    title="Configuração Inválida",
                    message=result["error_message"] or "",
                ),
            )
            self.logger.warning("project.create.failed")
            return False

        animal_method = result["animal_method"]
        wizard_metadata = result["wizard_metadata"]

        if setup_detector(animal_method):
            if wizard_metadata:
                apply_wizard_overrides(wizard_metadata)

            self._publish_event(UIEvents.UI_NAVIGATE_TO_PROJECT_VIEW, payloads.EmptyPayload())
            self._publish_event(
                UIEvents.UI_UPDATE_OPENVINO_CHECKBOX,
                payloads.UIUpdateOpenVinoCheckboxPayload(is_checked=get_use_openvino()),
            )
            self._publish_event(
                UIEvents.UI_SET_ACTIVE_WEIGHT,
                payloads.UISetActiveWeightPayload(weight_name=get_active_weight_name()),
            )
            update_openvino_status()

            if wizard_metadata:
                self._show_post_creation_guide(wizard_metadata)

            self.logger.info("project.create.complete")
            return True

        self._publish_event(
            UIEvents.SHOW_ERROR,
            payloads.MessagePayload(
                title="Erro",
                message="Falha ao configurar o detector.",
            ),
        )
        self.logger.error("project.create.detector_setup_failed")
        return False

    def _default_setup_detector(self, animal_method: str | None) -> bool:
        """Default detector setup using detector_service if available."""
        if self.detector_service:
            try:
                use_openvino = False
                active_weight = None
                if self.state_manager:
                    detector_state = self.state_manager.get_detector_state()
                    use_openvino = detector_state.use_openvino
                    active_weight = detector_state.active_weight_name

                if use_openvino and active_weight:
                    if hasattr(self.detector_service, "model_service"):
                        if not self.detector_service.model_service.is_openvino_ready(active_weight):
                            self.logger.warning(
                                "project.create.openvino_not_ready_fallback",
                                weight=active_weight,
                                message="Falling back to PyTorch",
                            )
                            use_openvino = False
                            if self.state_manager:
                                self.state_manager.update_detector_state(
                                    source="project_lifecycle_coordinator.openvino_fallback",
                                    use_openvino=False,
                                )

                success, error = self.detector_service.initialize_detector(
                    animal_method=animal_method,
                    use_openvino=use_openvino,
                )
                if not success:
                    self.logger.error("project.create.detector_setup_failed", error=error)
                return success
            except Exception as e:  # except Exception justified: ML inference heterogeneous errors
                self.logger.error("project.create.detector_setup_failed", error=str(e))
                return False
        return True

    def _default_set_active_weight(self, weight_name: str) -> None:
        """Default weight setter using state_manager."""
        if self.state_manager:
            self.state_manager.update_detector_state(
                source="project_lifecycle_coordinator.create_project",
                active_weight_name=weight_name,
            )

    def _default_set_openvino_usage(self, use_openvino: bool) -> None:
        """Default OpenVINO setter using state_manager."""
        if self.state_manager:
            self.state_manager.update_detector_state(
                source="project_lifecycle_coordinator.create_project",
                use_openvino=use_openvino,
            )

    def _default_update_openvino_status(self) -> None:
        """Default no-op for OpenVINO status update."""
        return None

    def _default_get_active_weight_name(self) -> str:
        """Default getter for active weight name from state_manager."""
        if self.state_manager:
            detector_state = self.state_manager.get_detector_state()
            return detector_state.active_weight_name or ""
        return self.settings.weights.det_filename if self.settings else ""  # type: ignore[attr-defined]

    def _default_get_use_openvino(self) -> bool:
        """Default getter for OpenVINO usage from state_manager."""
        if self.state_manager:
            detector_state = self.state_manager.get_detector_state()
            return detector_state.use_openvino
        return self.settings.model_selection.use_openvino if self.settings else False

    def _default_apply_wizard_overrides(self, metadata: dict) -> None:
        """Default wizard overrides applier using detector_service."""
        if self.detector_service and metadata:
            detector_params = metadata.get("detector_parameters", {})
            if detector_params:
                try:
                    self.detector_service.update_tracking_parameters(
                        params=detector_params,
                        scope="project",
                    )
                except Exception as e:  # except Exception justified: non-critical fallback
                    self.logger.warning("project.create.wizard_overrides_failed", error=str(e))

    def _show_post_creation_guide(self, wizard_metadata: dict) -> None:
        guide = self.project_workflow_service.generate_post_creation_guide(
            wizard_metadata=wizard_metadata,
            check_suppression=True,
        )
        if guide:
            self._publish_event(
                UIEvents.SHOW_INFO,
                payloads.MessagePayload(
                    title=guide["title"],
                    message=guide["message"],
                ),
            )

    def _apply_detector_zones_from_active_video(self) -> None:
        """Apply project zones to detector using the active video context."""
        if not self.detector_service or not self.detector_service.detector:
            self.logger.debug("project.zones.setup.detector_not_ready")
            return

        active_video = self.project_manager.get_active_zone_video()
        zone_data = self.project_manager.get_zone_data(video_path=active_video)
        self.detector_service.configure_zones(zones_data=zone_data)

    def _default_setup_zones_from_project(self) -> None:
        """Default zone setup callback used during open-project workflow."""
        self._setup_zones_from_project(
            setup_detector_zones_callback=self._apply_detector_zones_from_active_video
        )

    def open_project(
        self,
        project_path: Path | str,
        *,
        setup_detector_callback: Callable[[], bool] | None = None,
        set_active_weight_callback: Callable[[str], None] | None = None,
        set_openvino_usage_callback: Callable[[bool], None] | None = None,
        update_openvino_status_callback: Callable[[], None] | None = None,
        setup_zones_callback: Callable[[], None] | None = None,
        restore_detector_callback: Callable[[dict], None] | None = None,
        get_active_weight_name: Callable[[], str] | None = None,
        get_use_openvino: Callable[[], bool] | None = None,
    ) -> bool:
        """Open existing project and configure everything automatically.

        Args:
            project_path: Path to project directory
            setup_detector_callback: Callback to setup detector
            set_active_weight_callback: Callback to set active weight
            set_openvino_usage_callback: Callback to set OpenVINO usage
            update_openvino_status_callback: Callback to update OpenVINO status
            setup_zones_callback: Callback to setup zones from project
            restore_detector_callback: Callback to restore detector settings
            get_active_weight_name: Callback to get active weight name
            get_use_openvino: Callback to get OpenVINO usage

        Returns:
            True if successful, False otherwise

        Phase 3: Consolidated from ProjectOrchestrator.open_project_workflow
        """
        self.logger.info("project.open.start", path=str(project_path))

        # Provide default callbacks using available dependencies
        def _default_setup_detector() -> bool:
            """Default detector setup - initializes detector with current settings."""
            if self.detector_service:
                try:
                    # Get use_openvino from state_manager
                    use_openvino = False
                    if self.state_manager:
                        detector_state = self.state_manager.get_detector_state()
                        use_openvino = detector_state.use_openvino
                    success, error = self.detector_service.initialize_detector(
                        animal_method=None,  # Use settings default
                        use_openvino=use_openvino,
                    )
                    if not success:
                        self.logger.error("project.open.detector_setup_failed", error=error)
                    else:
                        # Re-apply zones after detector initialization so detector
                        # receives project geometry even when the first open-project
                        # zone hook ran before detector creation.
                        self._default_setup_zones_from_project()
                    return success
                # except Exception justified: ML inference heterogeneous errors
                except Exception as e:
                    self.logger.error("project.open.detector_setup_failed", error=str(e))
                    return False
            return True

        def _default_set_active_weight(weight_name: str) -> None:
            """Default weight setter using state_manager."""
            if self.state_manager:
                self.state_manager.update_detector_state(
                    source="project_lifecycle_coordinator.open_project",
                    active_weight_name=weight_name,
                )

        def _default_set_openvino_usage(use_openvino: bool) -> None:
            """Default OpenVINO setter using state_manager."""
            if self.state_manager:
                self.state_manager.update_detector_state(
                    source="project_lifecycle_coordinator.open_project",
                    use_openvino=use_openvino,
                )

        def _default_update_openvino_status() -> None:
            """Default no-op for OpenVINO status update."""
            pass

        def _default_restore_detector(settings: dict) -> None:
            """Default detector restore using detector_service."""
            if self.detector_service and settings:
                try:
                    self.detector_service.restore_detector_settings(settings)
                except Exception as e:  # except Exception justified: non-critical fallback
                    self.logger.warning("project.open.restore_detector_failed", error=str(e))

        def _default_get_active_weight_name() -> str:
            """Default getter for active weight name from state_manager."""
            if self.state_manager:
                detector_state = self.state_manager.get_detector_state()
                return detector_state.active_weight_name or ""
            return self.settings.weights.det_filename if self.settings else ""  # type: ignore[attr-defined]

        def _default_get_use_openvino() -> bool:
            """Default getter for OpenVINO usage from state_manager."""
            if self.state_manager:
                detector_state = self.state_manager.get_detector_state()
                return detector_state.use_openvino
            return self.settings.model_selection.use_openvino if self.settings else False

        # Delegate to adapter which handles all UI coordination
        success = self.project_workflow_adapter.open_project_workflow(
            project_path=project_path,
            setup_detector_callback=setup_detector_callback or _default_setup_detector,
            set_active_weight_callback=set_active_weight_callback or _default_set_active_weight,
            set_openvino_usage_callback=set_openvino_usage_callback or _default_set_openvino_usage,
            update_openvino_status_callback=update_openvino_status_callback
            or _default_update_openvino_status,
            setup_zones_callback=setup_zones_callback or self._default_setup_zones_from_project,
            restore_detector_callback=restore_detector_callback or _default_restore_detector,
            get_active_weight_name=get_active_weight_name or _default_get_active_weight_name,
            get_use_openvino=get_use_openvino or _default_get_use_openvino,
        )

        if success:
            # NOTE: Removed PROJECT_OPENED event emission (no handlers exist; all UI updates
            # are already handled by project_workflow_adapter.open_project_workflow)
            self.logger.info("project.open.complete", path=str(project_path))
        else:
            self.logger.warning("project.open.failed", path=str(project_path))

        return success

    # ========================================================================
    # Group B: Asset Management
    # ========================================================================

    def can_remove_project_asset(
        self, video_path: Path | str, asset: str
    ) -> tuple[bool, str | None]:
        """Validate whether a project asset can be safely removed.

        Args:
            video_path: Path to video file
            asset: Asset type to remove

        Returns:
            Tuple of (can_remove, error_message)

        Phase 3: Consolidated from ProjectOrchestrator.can_remove_project_asset
        """
        video_path = Path(video_path) if isinstance(video_path, str) else video_path

        try:
            asset_type = cast(AssetType, asset)
            return self.project_manager.can_remove_asset(str(video_path), asset_type)
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.error(
                "project.asset.can_remove_failed",
                asset=asset,
                video=str(video_path),
                error=str(exc),
            )
            return False, "Não foi possível validar a remoção solicitada."

    def delete_project_asset(
        self,
        video_path: Path | str,
        asset: str,
        *,
        delete_source: bool = True,
    ) -> bool:
        """Remove a project asset (arena, ROIs, trajectory, summary, or video).

        Args:
            video_path: Path to video file
            asset: Asset type to remove
            delete_source: Whether to delete source files

        Returns:
            True if successful, False otherwise

        Phase 3: Consolidated from ProjectOrchestrator.delete_project_asset
        """
        video_path = Path(video_path) if isinstance(video_path, str) else video_path

        try:
            asset_type = cast(AssetType, asset)
            removed = self.project_manager.remove_asset(
                str(video_path),
                asset_type,
                delete_files=delete_source,
            )
            self.logger.info(
                "project.asset.removal_result",
                asset=asset,
                video=str(video_path),
                removed=removed,
                delete_source=delete_source,
            )
            return removed
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.error(
                "project.asset.remove_failed",
                asset=asset,
                video=str(video_path),
                error=str(exc),
                exc_info=True,
            )
            return False

    # ====================================================================
    # Hierarchy cascade deletion  (Phase 3C.2)
    # ====================================================================

    def delete_hierarchy_node(
        self,
        node_type: str,
        *,
        group_id: str,
        day_id: str | None = None,
        subject_id: str | None = None,
        delete_files: bool = True,
    ) -> tuple[int, int]:
        """Remove a group, day, or subject and refresh project views.

        Returns:
            ``(removed, failed)`` counts.
        """
        pm = self.project_manager
        if not pm:
            return 0, 0

        if node_type == "subject" and day_id and subject_id:
            removed, failed = pm.remove_subject(
                group_id, day_id, subject_id, delete_files=delete_files
            )
        elif node_type == "day" and day_id:
            removed, failed = pm.remove_day(group_id, day_id, delete_files=delete_files)
        elif node_type == "group":
            removed, failed = pm.remove_group(group_id, delete_files=delete_files)
        else:
            self.logger.warning("project.hierarchy_delete.bad_type", node_type=node_type)
            return 0, 0

        self.logger.info(
            "project.hierarchy_delete.result",
            node_type=node_type,
            group=group_id,
            day=day_id,
            subject=subject_id,
            removed=removed,
            failed=failed,
        )

        # Trigger full tree refresh
        if self.event_bus and removed:
            self.event_bus.publish(
                UIEvents.VIDEO_TREE_REFRESH_REQUESTED, {"source": "hierarchy_delete"}
            )

        return removed, failed

    def delete_aquarium_scope(
        self,
        video_path: Path | str,
        aquarium_id: int,
        *,
        delete_files: bool = True,
        delete_zone: bool = True,
    ) -> bool:
        """Delete one aquarium scope from a multi-aquarium video."""
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        try:
            removed = self.project_manager.remove_aquarium_scope(
                str(video_path),
                aquarium_id,
                delete_files=delete_files,
                delete_zone=delete_zone,
            )
            self.logger.info(
                "project.aquarium_delete.result",
                video=str(video_path),
                aquarium_id=aquarium_id,
                removed=removed,
                delete_files=delete_files,
                delete_zone=delete_zone,
            )
            if self.event_bus and removed:
                self.event_bus.publish(
                    UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                    {"source": "aquarium_delete_scope"},
                )
            return removed
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.error(
                "project.aquarium_delete.failed",
                video=str(video_path),
                aquarium_id=aquarium_id,
                error=str(exc),
                exc_info=True,
            )
            return False

    def clear_aquarium_subject(
        self,
        video_path: Path | str,
        aquarium_id: int,
        *,
        delete_analysis_data: bool = True,
        delete_files: bool = True,
    ) -> bool:
        """Clear subject binding for one aquarium while keeping aquarium geometry."""
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        try:
            removed = self.project_manager.clear_aquarium_subject(
                str(video_path),
                aquarium_id,
                delete_analysis_data=delete_analysis_data,
                delete_files=delete_files,
            )
            self.logger.info(
                "project.aquarium_subject_clear.result",
                video=str(video_path),
                aquarium_id=aquarium_id,
                removed=removed,
                delete_analysis_data=delete_analysis_data,
                delete_files=delete_files,
            )
            if self.event_bus and removed:
                self.event_bus.publish(
                    UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                    {"source": "aquarium_clear_subject"},
                )
            return removed
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.error(
                "project.aquarium_subject_clear.failed",
                video=str(video_path),
                aquarium_id=aquarium_id,
                error=str(exc),
                exc_info=True,
            )
            return False

    def reset_analysis_data(
        self,
        video_path: Path | str,
        *,
        aquarium_id: int | None = None,
        delete_files: bool = True,
    ) -> bool:
        """Reset analysis artifacts while preserving aquarium drawings/zones."""
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        try:
            removed = self.project_manager.reset_analysis_data(
                str(video_path),
                aquarium_id=aquarium_id,
                delete_files=delete_files,
            )
            self.logger.info(
                "project.analysis_reset.result",
                video=str(video_path),
                aquarium_id=aquarium_id,
                removed=removed,
                delete_files=delete_files,
            )
            if self.event_bus and removed:
                self.event_bus.publish(
                    UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                    {"source": "analysis_reset"},
                )
            return removed
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.error(
                "project.analysis_reset.failed",
                video=str(video_path),
                aquarium_id=aquarium_id,
                error=str(exc),
                exc_info=True,
            )
            return False

    def register_project_outputs(
        self,
        *,
        video_path: str,
        results_dir: str,
        trajectory_path: str,
        summary_parquet: str,
        summary_excel: str,
        report_path: str,
        refresh_callback: Callable[[str, bool], None] | None = None,
    ) -> None:
        """Register processing outputs to project.

        Args:
            video_path: Path to processed video
            results_dir: Results directory path
            trajectory_path: Trajectory parquet path
            summary_parquet: Summary parquet path
            summary_excel: Summary excel path
            report_path: Report docx path
            refresh_callback: Optional callback to refresh project views

        Phase 3: Consolidated from ProjectOrchestrator._register_project_outputs
        """
        self.logger.info("project.outputs.register.start", video=video_path)

        # Register through project manager
        if hasattr(self.project_manager, "register_processing_outputs"):
            self.project_manager.register_processing_outputs(
                video_path=video_path,
                results_dir=results_dir,
                trajectory_path=trajectory_path,
                summary_parquet=summary_parquet,
                summary_excel=summary_excel,
                report_path=report_path,
            )

        # Refresh views if callback provided
        if refresh_callback:
            refresh_callback("processing_progress", True)

        self.logger.info("project.outputs.register.complete", video=video_path)

    # ========================================================================
    # Group C: Model Override Management (delegated to ModelOverrideService)
    # ========================================================================

    def are_project_overrides_active(self) -> bool:
        """Check if project-specific model overrides are currently active."""
        if self._model_override_service:
            return self._model_override_service.are_project_overrides_active()
        return bool(self._using_project_overrides)

    def has_project_override_settings(self) -> bool:
        """Check if project has any non-empty model override settings."""
        if self._model_override_service:
            return self._model_override_service.has_project_override_settings()
        return False

    def copy_global_model_settings_to_project(
        self,
        get_global_defaults: Callable[[], dict],
        get_active_weight_name: Callable[[], str | None],
        refresh_callback: Callable[[str, bool], None] | None = None,
    ) -> tuple[str | None, bool] | None:
        """Copy global model settings to current project as overrides."""
        if self._model_override_service:
            return self._model_override_service.copy_global_model_settings_to_project(
                get_global_defaults, get_active_weight_name, refresh_callback
            )
        return None

    def resolve_project_model_settings(
        self, overrides: dict | None = None
    ) -> tuple[str | None, bool]:
        """Resolve model settings considering project overrides and global defaults."""
        if self._model_override_service:
            return self._model_override_service.resolve_project_model_settings(overrides)
        return self.project_workflow_service.resolve_project_model_settings(overrides)

    def save_current_calibration_to_project(
        self,
        get_active_weight_name: Callable[[], str | None],
        get_use_openvino: Callable[[], bool],
        refresh_callback: Callable[[str, bool], None] | None = None,
    ) -> tuple[str | None, bool] | None:
        """Save current model settings as project-specific overrides."""
        if self._model_override_service:
            return self._model_override_service.save_current_calibration_to_project(
                get_active_weight_name, get_use_openvino, refresh_callback
            )
        return None

    def apply_project_model_overrides(
        self,
        *,
        overrides: dict | None = None,
        active_weight_setter: Callable[[str], None],
        use_openvino_setter: Callable[[bool], None],
    ) -> tuple[str | None, bool]:
        """Apply project-specific model overrides to current settings."""
        if self._model_override_service:
            return self._model_override_service.apply_project_model_overrides(
                overrides=overrides,
                active_weight_setter=active_weight_setter,
                use_openvino_setter=use_openvino_setter,
            )
        return self.project_workflow_service.apply_project_model_overrides(
            overrides=overrides,
            active_weight_setter=active_weight_setter,
            use_openvino_setter=use_openvino_setter,
        )

    def save_project_model_overrides(
        self,
        active_weight_override: str | None,
        use_openvino_override: bool | None,
        get_active_weight_name: Callable[[], str | None],
        get_use_openvino: Callable[[], bool],
    ) -> tuple[str | None, bool]:
        """Save model settings as project overrides and apply them."""
        if self._model_override_service:
            return self._model_override_service.save_project_model_overrides(
                active_weight_override,
                use_openvino_override,
                get_active_weight_name,
                get_use_openvino,
            )
        # Fallback: no delegate, return current values
        return get_active_weight_name() or None, get_use_openvino()

    def save_project_model_slot_overrides(
        self,
        slot_weights: dict[str, str | None] | None,
        use_openvino_override: bool | None,
    ) -> tuple[str | None, bool]:
        """Save explicit per-slot model overrides for the active project."""
        if self._model_override_service:
            return self._model_override_service.save_project_model_slot_overrides(
                slot_weights,
                use_openvino_override,
            )
        return None, bool(use_openvino_override)

    # ========================================================================
    # Group D: Calibration Management (delegated to CalibrationCoordinator)
    # ========================================================================

    def get_calibration_scope_info(
        self,
        get_active_weight_name: Callable[[], str | None] | None = None,
        gui_instance: Any | None = None,
    ) -> dict[str, Any]:
        """Get calibration scope information for UI display."""
        if self._calibration_coordinator:
            return self._calibration_coordinator.get_calibration_scope_info(
                get_active_weight_name, gui_instance
            )
        return {
            "scope": "global",
            "project_loaded": False,
            "label": "Escopo: Configuração Global",
            "detail": "Delegates not available.",
        }

    def build_calibration_context(
        self,
        arena_polygon: list[list[int]] | list | None,
        calibration_data: dict | None,
    ) -> tuple[Calibration | None, tuple[float, float] | None]:
        """Calculate calibration and pixel/cm ratio for tracking outputs."""
        if self._calibration_coordinator:
            return self._calibration_coordinator.build_calibration_context(
                arena_polygon, calibration_data
            )
        return None, None

    @contextmanager
    def global_calibration_session(
        self,
        get_active_weight_name: Callable[[], str | None],
        get_use_openvino: Callable[[], bool],
    ) -> Generator[None, None, None]:
        """Context manager for global calibration mode."""
        if self._calibration_coordinator:
            with self._calibration_coordinator.global_calibration_session(
                get_active_weight_name, get_use_openvino
            ):
                yield
        else:
            yield

    @contextmanager
    def project_calibration_session(self) -> Generator[None, None, None]:
        """Context manager for project-specific calibration mode."""
        if self._calibration_coordinator:
            with self._calibration_coordinator.project_calibration_session():
                yield
        else:
            yield

    # ========================================================================
    # Group E: Supporting Methods (Private)
    # ========================================================================

    def _setup_zones_from_project(
        self,
        setup_detector_zones_callback: Callable[[], None] | None = None,
    ) -> None:
        """Set up zones from project data.

        Args:
            setup_detector_zones_callback: Callback to setup detector zones
        """
        if setup_detector_zones_callback is None:
            self.logger.warning("project.zones.setup.no_callback")
            return

        self.project_workflow_adapter.setup_zones_from_project(
            setup_detector_zones_callback=setup_detector_zones_callback,
        )

    def _restore_global_model_defaults(self) -> None:
        """Restore global model defaults (backward-compat fallback)."""
        if self._model_override_service:
            self._model_override_service.restore_global_model_defaults()
        else:
            detector_state = self.state_manager.get_detector_state()
            self._global_model_defaults["active_weight"] = detector_state.active_weight_name
            self._global_model_defaults["use_openvino"] = detector_state.use_openvino
            self._using_project_overrides = False
            self.logger.info("project.model_defaults.restored")
