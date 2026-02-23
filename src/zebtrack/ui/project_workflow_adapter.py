"""
Project Workflow Adapter for ZebTrack-AI.

Phase 2, Task P2-T2: Extract project workflow orchestration from MainViewModel.

This adapter coordinates UI-level project workflows, delegating business logic
to ProjectWorkflowService while managing UI events and detector setup.

Responsibilities:
- Orchestrate create/open/close project workflows with UI updates
- Apply wizard detector overrides
- Show post-creation guides
- Coordinate detector and zone setup
- Publish UI events for state changes
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.project.project_workflow_service import ProjectWorkflowService
    from zebtrack.core.services.detector_service import DetectorService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.ui.event_bus_v2 import EventBusV2

log = structlog.get_logger()


class ProjectWorkflowAdapter:
    """
    Adapter for project workflow orchestration with UI coordination.

    Extracted from MainViewModel (P2-T2) to reduce god object complexity
    and separate UI orchestration from business logic.

    This adapter sits between the UI layer and ProjectWorkflowService,
    handling UI event publishing and detector/zone setup coordination.
    """

    def __init__(
        self,
        project_workflow_service: ProjectWorkflowService,
        project_manager: ProjectManager,
        detector_service: DetectorService,
        state_manager: StateManager,
        ui_event_bus: EventBusV2 | None,
    ):
        """
        Initialize ProjectWorkflowAdapter.

        Args:
            project_workflow_service: Service for project workflow business logic
            project_manager: Project manager for state operations
            detector_service: Detector service for detector configuration
            state_manager: State manager for state updates
            ui_event_bus: Event bus for publishing UI events (optional)
        """
        self.project_workflow_service = project_workflow_service
        self.project_manager = project_manager
        self.detector_service = detector_service
        self.state_manager = state_manager
        self.ui_event_bus = ui_event_bus

        log.info("project_workflow_adapter.initialized")

    def _publish_event(self, event_type: Any, data: Any = None) -> None:
        """Safely publish an event if the event bus is available."""
        if self.ui_event_bus:
            from zebtrack.ui.event_bus_v2 import Event

            self.ui_event_bus.publish(Event(type=event_type, data=data or {}))

    def close_project(
        self,
        restore_global_defaults_callback: Callable[[], None],
        settings_obj: Any,
    ) -> ProjectManager:
        """
        Close the current project and restore global defaults.

        Args:
            restore_global_defaults_callback: Callback to restore global model defaults
            settings_obj: Settings instance for ProjectManager
        """
        # Restore global defaults before clearing project state
        restore_global_defaults_callback()

        # Reset project manager (pass StateManager reference and settings)
        # Note: This creates a new ProjectManager instance
        from zebtrack.core.project.project_manager import ProjectManager

        new_project_manager = ProjectManager(
            state_manager=self.state_manager, settings_obj=settings_obj
        )

        # Update StateManager: project closed
        self.state_manager.update_project_state(
            source="project_workflow_adapter.close_project",
            project_path=None,
            project_data={},
            active_zone_video=None,
        )

        # Navigate to welcome screen
        from zebtrack.ui.event_bus_v2 import UIEvents

        self._publish_event(UIEvents.NAVIGATE_TO_WELCOME)

        log.info("project_workflow_adapter.close_project.complete")

        # Return new project manager for caller to replace
        return new_project_manager

    def create_project_workflow(
        self,
        setup_detector_callback: Callable[[str | None], bool],
        set_active_weight_callback: Callable[[str], None],
        set_openvino_usage_callback: Callable[[bool], None],
        update_openvino_status_callback: Callable[[], None],
        get_active_weight_name: Callable[[], str],
        get_use_openvino: Callable[[], bool],
        apply_wizard_overrides_callback: Callable[[dict], None],
        view_suppress_guide_check: Callable[[], bool] | None = None,
        **kwargs,
    ) -> bool:
        """
        Create project workflow with UI orchestration.

        Args:
            setup_detector_callback: Callback to setup detector (returns success bool)
            set_active_weight_callback: Callback to set active weight
            set_openvino_usage_callback: Callback to set OpenVINO usage
            update_openvino_status_callback: Callback to update OpenVINO status
            get_active_weight_name: Callback to get active weight name
            get_use_openvino: Callback to get OpenVINO usage flag
            apply_wizard_overrides_callback: Callback to apply wizard detector overrides
            view_suppress_guide_check: Optional callback to check if guide suppression is enabled
            **kwargs: Additional arguments for project creation
        Returns:
            True if project created successfully, False otherwise
        """
        from zebtrack.ui.event_bus_v2 import UIEvents

        # Update global model defaults before creation
        self.project_workflow_service.set_global_model_defaults(
            active_weight=get_active_weight_name() or None,
            use_openvino=get_use_openvino(),
        )

        # Orchestrate project creation via service
        result = self.project_workflow_service.create_project(
            setup_detector_callback=setup_detector_callback,
            active_weight_setter=set_active_weight_callback,
            use_openvino_setter=set_openvino_usage_callback,
            **kwargs,
        )

        # Handle failure
        if not result["success"]:
            self._publish_event(
                UIEvents.SHOW_ERROR,
                {"title": "Configuração Inválida", "message": result["error_message"]},
            )
            return False

        # Extract result data
        animal_method = result["animal_method"]
        wizard_metadata = result["wizard_metadata"]

        # Setup detector with the resolved animal method
        if setup_detector_callback(animal_method):
            if wizard_metadata:
                apply_wizard_overrides_callback(wizard_metadata)

            # Update UI
            self._publish_event(UIEvents.UI_NAVIGATE_TO_PROJECT_VIEW, {})
            self._publish_event(
                UIEvents.UI_UPDATE_OPENVINO_CHECKBOX, {"is_checked": get_use_openvino()}
            )
            self._publish_event(
                UIEvents.UI_SET_ACTIVE_WEIGHT, {"weight_name": get_active_weight_name()}
            )
            update_openvino_status_callback()

            # Show post-creation guide if wizard metadata provided
            if wizard_metadata:
                self._show_post_creation_guide(wizard_metadata, view_suppress_guide_check)

            log.info("project_workflow_adapter.create_project.success")
            return True
        else:
            self._publish_event(
                UIEvents.SHOW_ERROR,
                {"title": "Erro", "message": "Falha ao configurar o detector."},
            )
            log.error("project_workflow_adapter.create_project.detector_setup_failed")
            return False

    def open_project_workflow(
        self,
        project_path: Path | str,
        setup_detector_callback: Callable[[], bool],
        set_active_weight_callback: Callable[[str], None],
        set_openvino_usage_callback: Callable[[bool], None],
        update_openvino_status_callback: Callable[[], None],
        setup_zones_callback: Callable[[], None],
        restore_detector_callback: Callable[[dict], None],
        get_active_weight_name: Callable[[], str],
        get_use_openvino: Callable[[], bool],
    ) -> bool:
        """
        Open project workflow with UI orchestration.

        Args:
            project_path: Path to project file
            setup_detector_callback: Callback to setup detector (returns success bool)
            set_active_weight_callback: Callback to set active weight
            set_openvino_usage_callback: Callback to set OpenVINO usage
            update_openvino_status_callback: Callback to update OpenVINO status
            setup_zones_callback: Callback to setup zones from project
            restore_detector_callback: Callback to restore detector settings
            get_active_weight_name: Callback to get active weight name
            get_use_openvino: Callback to get OpenVINO usage flag

        Returns:
            True if project opened successfully, False otherwise
        """
        from zebtrack.ui.event_bus_v2 import UIEvents

        project_path = Path(project_path) if isinstance(project_path, str) else project_path

        # Update global model defaults before opening
        self.project_workflow_service.set_global_model_defaults(
            active_weight=get_active_weight_name() or None,
            use_openvino=get_use_openvino(),
        )

        # Orchestrate project opening via service
        result = self.project_workflow_service.open_project(
            project_path=project_path,
            active_weight_setter=set_active_weight_callback,
            use_openvino_setter=set_openvino_usage_callback,
            restore_detector_callback=restore_detector_callback,
            setup_zones_callback=setup_zones_callback,
        )

        # Handle failure
        if not result["success"]:
            self._publish_event(
                UIEvents.SHOW_ERROR,
                {"title": "Erro", "message": result["error_message"]},
            )
            return False

        # Extract result data
        project_info = result["project_info"]

        # Update UI to reflect restored state
        self._publish_event(
            UIEvents.UI_UPDATE_OPENVINO_CHECKBOX,
            {"is_checked": get_use_openvino()},
        )
        self._publish_event(
            UIEvents.UI_SET_ACTIVE_WEIGHT,
            {"weight_name": get_active_weight_name()},
        )
        update_openvino_status_callback()

        # Initialize detector
        if not setup_detector_callback():
            log.warning("project_workflow_adapter.open_project.detector_setup_failed")
            return False
        else:
            # Load project view
            self._publish_event(UIEvents.UI_NAVIGATE_TO_PROJECT_VIEW, {})

        # Display success message
        self._publish_event(
            UIEvents.SHOW_INFO,
            {
                "title": "Projeto Carregado",
                "message": f"Projeto '{project_info['name']}' carregado com sucesso!\n\n"
                f"• Vídeos: {project_info['videos_count']}\n"
                f"• Arena Principal: {project_info['zone_status']}\n"
                f"• ROIs: {project_info['roi_count']}\n"
                f"• Peso: {project_info['active_weight']}\n"
                f"• OpenVINO: {'✓' if project_info['use_openvino'] else '✗'}",
            },
        )

        log.info(
            "project_workflow_adapter.open_project.complete",
            project=project_info["name"],
            videos=project_info["videos_count"],
        )

        return True

    def setup_zones_from_project(
        self,
        setup_detector_zones_callback: Callable[[], None],
    ) -> None:
        """
        Set up zones from project data.

        Args:
            setup_detector_zones_callback: Callback to setup zones in detector
        """
        from zebtrack.ui.event_bus_v2 import UIEvents

        # Setup zones in detector
        setup_detector_zones_callback()

        # Update zone visualization in GUI
        self._publish_event(UIEvents.UI_REDRAW_ZONES)
        self._publish_event(UIEvents.UI_UPDATE_ZONE_LIST)

        log.debug("project_workflow_adapter.setup_zones.complete")

    def _show_post_creation_guide(
        self,
        wizard_metadata: dict,
        view_suppress_guide_check: Callable[[], bool] | None = None,
    ) -> None:
        """
        Display a contextual onboarding message after project creation.

        Args:
            wizard_metadata: Metadata from wizard
            view_suppress_guide_check: Optional callback to check if guide suppression is enabled
        """
        from zebtrack.ui.event_bus_v2 import UIEvents

        # Check view-level suppression flag if callback provided
        if view_suppress_guide_check and view_suppress_guide_check():
            log.info("project_workflow_adapter.post_creation_guide.skipped", reason="view_flag")
            return

        # Generate guide content via service
        guide = self.project_workflow_service.generate_post_creation_guide(
            wizard_metadata=wizard_metadata,
            check_suppression=True,
        )

        # Display guide if generated
        if guide:
            self._publish_event(
                UIEvents.SHOW_INFO, {"title": guide["title"], "message": guide["message"]}
            )
            log.debug("project_workflow_adapter.post_creation_guide.shown")
