"""Project ViewModel for project management workflows.

Phase 3C: Refactored to use ProjectLifecycleCoordinator instead of ProjectOrchestrator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.core.state_manager import StateCategory

if TYPE_CHECKING:
    from pathlib import Path

    from zebtrack.core.application_bootstrapper import BootstrapResult
    from zebtrack.core.dependency_container import MainViewModelDependencies

log = structlog.get_logger()


class ProjectViewModel:
    """ViewModel responsible for Project Management workflows.

    Phase 3C: Fully migrated to use ProjectLifecycleCoordinator.
    """

    def __init__(
        self,
        dependencies: MainViewModelDependencies,
        bootstrap_result: BootstrapResult,
        event_bus: Any,
    ):
        self.project_manager = dependencies.project_manager
        self.state_manager = dependencies.state_manager
        self.project_lifecycle_coordinator = dependencies.project_lifecycle_coordinator
        self.project_workflow_service = dependencies.project_workflow_service
        self.batch_configuration_service = bootstrap_result.batch_configuration_service
        self.ui_event_bus = event_bus
        self.settings = dependencies.settings_obj

    def create_project_workflow(self, **wizard_data):
        if self.project_lifecycle_coordinator:
            return self.project_lifecycle_coordinator.create_project(**wizard_data)
        return None

    def open_project_workflow(self, project_path: Path | str):
        if self.project_lifecycle_coordinator:
            return self.project_lifecycle_coordinator.open_project(project_path)
        return None

    def close_project(self):
        if self.project_lifecycle_coordinator:
            return self.project_lifecycle_coordinator.close_project()
        return None

    def on_video_selected(self, video_path: Path | str):
        """Handle video selection event."""
        if self.project_manager:
            self.project_manager.set_active_zone_video(video_path)

    def handle_delete_project_asset(
        self, video_path: Path | str, asset: str, delete_source: bool = False
    ):
        if self.project_lifecycle_coordinator:
            self.project_lifecycle_coordinator.delete_project_asset(
                video_path, asset, delete_source=delete_source
            )

    def handle_delete_hierarchy_node(
        self,
        node_type: str,
        *,
        group_id: str,
        day_id: str | None = None,
        subject_id: str | None = None,
        delete_files: bool = True,
    ) -> tuple[int, int]:
        if self.project_lifecycle_coordinator:
            return self.project_lifecycle_coordinator.delete_hierarchy_node(
                node_type,
                group_id=group_id,
                day_id=day_id,
                subject_id=subject_id,
                delete_files=delete_files,
            )
        return 0, 0

    def can_remove_project_asset(
        self, video_path: Path | str, asset: str
    ) -> tuple[bool, str | None]:
        if self.project_lifecycle_coordinator:
            return self.project_lifecycle_coordinator.can_remove_project_asset(video_path, asset)
        return (False, "ProjectLifecycleCoordinator not available")

    def apply_project_settings_to_batch(self, videos: list):
        return self.batch_configuration_service.apply_settings(videos)

    def resolve_project_model_settings(self, overrides: dict) -> tuple[str | None, bool]:
        if self.project_lifecycle_coordinator:
            return self.project_lifecycle_coordinator.resolve_project_model_settings(overrides)
        return None, False

    def save_project_model_overrides(
        self, active_weight: str | None, use_openvino: bool | None
    ) -> None:
        """Save model settings as project overrides.

        Uses state_manager to provide callbacks for state access.
        """
        if not self.project_lifecycle_coordinator:
            return

        def get_active_weight_name() -> str | None:
            if self.state_manager:
                return self.state_manager.get_state(StateCategory.DETECTOR).get(
                    "active_weight_name"
                )
            return None

        def get_use_openvino() -> bool:
            if self.state_manager:
                return self.state_manager.get_state(StateCategory.DETECTOR).get(
                    "use_openvino", False
                )
            return False

        self.project_lifecycle_coordinator.save_project_model_overrides(
            active_weight,
            use_openvino,
            get_active_weight_name,
            get_use_openvino,
        )

    def has_project_override_settings(self) -> bool:
        if self.project_lifecycle_coordinator:
            return self.project_lifecycle_coordinator.has_project_override_settings()
        return False

    def handle_calibration_copy_to_project(self):
        """Copy global model settings to project overrides."""
        if not self.project_lifecycle_coordinator:
            return

        def get_global_defaults() -> dict:
            return {
                "active_weight": self.settings.weights.det_filename if self.settings else None,
                "use_openvino": self.settings.model_selection.use_openvino
                if self.settings
                else False,
            }

        def get_active_weight_name() -> str | None:
            if self.state_manager:
                return self.state_manager.get_state(StateCategory.DETECTOR).get(
                    "active_weight_name"
                )
            return None

        self.project_lifecycle_coordinator.copy_global_model_settings_to_project(
            get_global_defaults=get_global_defaults,
            get_active_weight_name=get_active_weight_name,
        )

    def handle_calibration_save_to_project(self):
        """Save current calibration settings to project."""
        if not self.project_lifecycle_coordinator:
            return

        def get_active_weight_name() -> str | None:
            if self.state_manager:
                return self.state_manager.get_state(StateCategory.DETECTOR).get(
                    "active_weight_name"
                )
            return None

        def get_use_openvino() -> bool:
            if self.state_manager:
                return self.state_manager.get_state(StateCategory.DETECTOR).get(
                    "use_openvino", False
                )
            return False

        self.project_lifecycle_coordinator.save_current_calibration_to_project(
            get_active_weight_name=get_active_weight_name,
            get_use_openvino=get_use_openvino,
        )

    def get_calibration_scope_info(self) -> dict:
        """Get calibration scope information for display."""
        if not self.project_lifecycle_coordinator:
            return {
                "scope": "global",
                "label": "Global",
                "detail": "N/A",
                "project_loaded": False,
            }

        def get_active_weight_name() -> str | None:
            if self.state_manager:
                return self.state_manager.get_state(StateCategory.DETECTOR).get(
                    "active_weight_name"
                )
            return None

        return self.project_lifecycle_coordinator.get_calibration_scope_info(
            get_active_weight_name=get_active_weight_name,
        )

    @property
    def project_data(self) -> dict:
        if self.project_manager:
            return self.project_manager.project_data
        return {}
