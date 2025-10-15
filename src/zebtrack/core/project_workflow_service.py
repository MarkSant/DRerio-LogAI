"""
Project Workflow Service for ZebTrack-AI.

Phase 5: Project Workflow Simplification
Consolidates all project workflow logic (creation, opening, configuration)
from the controller into a dedicated service.

This service provides:
- Project creation orchestration with wizard integration
- Project opening and state restoration
- Model settings resolution and application
- Parameter validation and preparation
- Post-creation user guidance
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from zebtrack.core.model_service import ModelService
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.ui_coordinator import UICoordinator

log = structlog.get_logger()


class ProjectWorkflowService:
    """
    Service for managing project workflows.

    Phase 5: Consolidates project creation, opening, and configuration logic
    from MainViewModel, making project workflows testable and reducing controller complexity.

    Responsibilities:
    - Orchestrate project creation with wizard data
    - Orchestrate project opening and state restoration
    - Validate and prepare project parameters
    - Resolve and apply model settings
    - Import wizard data (parquets, ROIs, etc.)
    - Display post-creation guidance
    """

    def __init__(
        self,
        project_manager: ProjectManager,
        model_service: ModelService,
        state_manager: StateManager,
        ui_coordinator: UICoordinator | None = None,
    ):
        """
        Initialize ProjectWorkflowService.

        Args:
            project_manager: ProjectManager instance for project operations
            model_service: ModelService instance for model configuration
            state_manager: StateManager instance for state updates
            ui_coordinator: Optional UICoordinator for UI updates
        """
        self.project_manager = project_manager
        self.model_service = model_service
        self.state_manager = state_manager
        self.ui_coordinator = ui_coordinator

        # Tracking state
        self._using_project_overrides = False
        self._global_model_defaults: dict[str, Any] = {}

        log.info("project_workflow_service.initialized")

    def set_global_model_defaults(self, active_weight: str | None, use_openvino: bool) -> None:
        """
        Set global model defaults for fallback when project has no overrides.

        Args:
            active_weight: Default weight name
            use_openvino: Default OpenVINO usage
        """
        self._global_model_defaults = {
            "active_weight": active_weight,
            "use_openvino": use_openvino,
        }
        log.info(
            "project_workflow_service.defaults_set",
            active_weight=active_weight,
            use_openvino=use_openvino,
        )

    # === Parameter Validation and Preparation ===

    def validate_project_parameters(self, **kwargs: Any) -> tuple[bool, str | None]:
        """
        Validate project creation parameters.

        Phase 5: Extracted from create_project_workflow.

        Args:
            **kwargs: Project parameters to validate

        Returns:
            tuple: (is_valid, error_message)
        """
        animal_method = kwargs.get("animal_method")
        animals_per_aquarium = kwargs.get("animals_per_aquarium", 1)

        # Validate detection mode compatibility
        if animal_method == "det" and animals_per_aquarium != 1:
            error_msg = (
                "O modo de detecção (det) para animais só é compatível com 1 "
                f"animal por aquário.\n"
                f"Configuração atual: {animals_per_aquarium} "
                "animais por aquário.\n\n"
                "Para usar múltiplos animais por aquário, altere o método de "
                "detecção de animais para 'seg' (segmentação) nas configurações."
            )
            log.warning(
                "project_workflow_service.validation_failed",
                reason="det_mode_incompatible_with_multi_animal",
                animal_method=animal_method,
                animals_per_aquarium=animals_per_aquarium,
            )
            return False, error_msg

        return True, None

    def prepare_controller_parameters(self, **kwargs: Any) -> dict[str, Any]:
        """
        Prepare and filter parameters for project creation.

        Phase 5: Extracted from create_project_workflow.

        This uses a whitelist approach to ensure only valid parameters
        are passed to ProjectManager.create_new_project().

        Args:
            **kwargs: Raw parameters from wizard or dialog

        Returns:
            dict: Filtered parameters safe for create_new_project()
        """
        # WHITELIST APPROACH: Only pass parameters that create_new_project() accepts
        allowed_params = {
            "project_path",
            "project_type",
            "use_openvino",
            "active_weight",
            "video_files",
            "num_aquariums",
            "animals_per_aquarium",
            "aquarium_width_cm",
            "aquarium_height_cm",
            "use_timed_recording",
            "recording_duration_s",
            "use_countdown",
            "countdown_duration_s",
            "analysis_interval_frames",
            "display_interval_frames",
            "camera_index",
            "use_arduino",
            "arduino_port",
            "use_single_subject_tracker",
            # Live project params
            "experiment_days",
            "subjects_per_group",
            "num_groups",
            "group_names",
            # Wizard metadata
            "_wizard_metadata",
        }

        # Filter kwargs to only allowed parameters
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in allowed_params}

        log.info(
            "project_workflow_service.parameters_prepared",
            total_params=len(kwargs),
            filtered_params=len(filtered_kwargs),
        )

        return filtered_kwargs

    # === Model Settings Resolution and Application ===

    def resolve_project_model_settings(
        self, overrides: dict | None = None
    ) -> tuple[str | None, bool]:
        """
        Resolve model settings from project data and overrides.

        Phase 5: Moved from controller.resolve_project_model_settings().

        Resolution order:
        1. Explicit overrides parameter
        2. Project model_overrides
        3. Project active_weight/use_openvino
        4. Global model defaults
        5. Default weight from weight manager

        Args:
            overrides: Optional overrides to apply

        Returns:
            tuple: (resolved_weight_name, resolved_use_openvino)
        """
        project_data = getattr(self.project_manager, "project_data", {}) or {}
        base_overrides = project_data.get("model_overrides") or {}

        if overrides is not None:
            merged_overrides = base_overrides.copy()
            merged_overrides.update(overrides)
        else:
            merged_overrides = base_overrides

        # Parse weight override
        weight_override = merged_overrides.get("active_weight")
        if isinstance(weight_override, str):
            weight_override = weight_override.strip() or None

        # Parse OpenVINO override
        openvino_override = merged_overrides.get("use_openvino")
        if isinstance(openvino_override, str):
            lowered = openvino_override.strip().lower()
            if lowered in {"", "inherit", "auto"}:
                openvino_override = None
            else:
                openvino_override = lowered in {"true", "1", "yes", "on"}

        # Resolve weight with fallback chain
        resolved_weight = weight_override
        if not resolved_weight:
            resolved_weight = project_data.get("active_weight") or None
        if not resolved_weight:
            resolved_weight = self._global_model_defaults.get("active_weight")
        if not resolved_weight:
            default_weight, _ = self.model_service.get_default_weight()
            resolved_weight = default_weight

        # Validate weight exists
        available_weights = set(self.model_service.get_all_weight_names())
        if resolved_weight and resolved_weight not in available_weights:
            log.warning(
                "project_workflow_service.weight_missing",
                weight=resolved_weight,
                available=list(available_weights),
            )
            # Fallback to global default or first available
            fallback_weight = self._global_model_defaults.get("active_weight")
            if fallback_weight and fallback_weight in available_weights:
                resolved_weight = fallback_weight
            else:
                default_weight, _ = self.model_service.get_default_weight()
                resolved_weight = default_weight if default_weight else None

        # Resolve OpenVINO
        if openvino_override is None:
            if project_data.get("use_openvino") is not None:
                resolved_openvino = bool(project_data.get("use_openvino"))
            else:
                resolved_openvino = bool(self._global_model_defaults.get("use_openvino", False))
        else:
            resolved_openvino = bool(openvino_override)

        log.info(
            "project_workflow_service.model_settings_resolved",
            resolved_weight=resolved_weight,
            resolved_openvino=resolved_openvino,
        )

        return resolved_weight, resolved_openvino

    def apply_project_model_overrides(
        self,
        overrides: dict | None = None,
        active_weight_setter: callable = None,
        use_openvino_setter: callable = None,
    ) -> tuple[str | None, bool]:
        """
        Apply project model overrides and update project data.

        Phase 5: Moved from controller.apply_project_model_overrides().

        Args:
            overrides: Optional overrides to apply
            active_weight_setter: Callback to set active_weight in controller
            use_openvino_setter: Callback to set use_openvino in controller

        Returns:
            tuple: (resolved_weight_name, resolved_use_openvino)
        """
        if not getattr(self.project_manager, "project_data", None):
            # No project loaded, return current global defaults
            return (
                self._global_model_defaults.get("active_weight"),
                bool(self._global_model_defaults.get("use_openvino", False)),
            )

        resolved_weight, resolved_openvino = self.resolve_project_model_settings(overrides)

        self._using_project_overrides = True

        # Apply settings via setters if provided
        if active_weight_setter and resolved_weight:
            active_weight_setter(resolved_weight)

        if use_openvino_setter is not None:
            use_openvino_setter(resolved_openvino)

        # Update project data
        updated = False
        if self.project_manager.project_data.get("active_weight") != resolved_weight:
            self.project_manager.project_data["active_weight"] = resolved_weight
            updated = True

        if self.project_manager.project_data.get("use_openvino") != resolved_openvino:
            self.project_manager.project_data["use_openvino"] = resolved_openvino
            updated = True

        # Save project if updated
        if updated and getattr(self.project_manager, "project_path", None):
            self.project_manager.save_project()
            log.info(
                "project_workflow_service.model_settings_saved",
                weight=resolved_weight,
                openvino=resolved_openvino,
            )

        return resolved_weight, resolved_openvino

    # === Project Creation Orchestration ===

    def create_project(
        self,
        setup_detector_callback: callable,
        active_weight_setter: callable | None = None,
        use_openvino_setter: callable | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Orchestrate project creation workflow.

        Phase 5: Extracted from controller.create_project_workflow().

        This method handles:
        1. Parameter preparation and validation
        2. Project creation via ProjectManager
        3. State updates
        4. Model override application
        5. Wizard data import

        The controller is responsible for:
        - Calling setup_detector with the returned animal_method
        - Loading the project view
        - Updating UI controls
        - Displaying the post-creation guide

        Args:
            setup_detector_callback: Callback for detector setup (returns bool)
            active_weight_setter: Optional callback to set active_weight
            use_openvino_setter: Optional callback to set use_openvino
            **kwargs: Project parameters from wizard or dialog

        Returns:
            dict with:
                - success: bool
                - error_message: str | None
                - wizard_metadata: dict | None
                - animal_method: str | None
                - project_path: Path | None
                - import_success: bool | None
        """
        from pathlib import Path

        from zebtrack.settings import settings

        # Prepare parameters
        animal_method = kwargs.get("animal_method", settings.model_selection.animal_method)
        animals_per_aquarium = kwargs.get("animals_per_aquarium", 1)

        # Set use_single_subject_tracker if not provided
        if "use_single_subject_tracker" not in kwargs:
            kwargs["use_single_subject_tracker"] = animals_per_aquarium == 1
        else:
            kwargs["use_single_subject_tracker"] = bool(kwargs["use_single_subject_tracker"])

        # Validate parameters
        is_valid, error_msg = self.validate_project_parameters(**kwargs)
        if not is_valid:
            log.warning(
                "project_workflow_service.create_project.validation_failed",
                error=error_msg,
            )
            return {
                "success": False,
                "error_message": error_msg,
                "wizard_metadata": None,
                "animal_method": None,
                "project_path": None,
                "import_success": None,
            }

        # Log detection mode configuration
        if animal_method == "det" and animals_per_aquarium == 1:
            log.info(
                "project_workflow_service.create_project.det_single_animal",
                animal_method=animal_method,
                animals_per_aquarium=animals_per_aquarium,
            )

        # Apply OpenVINO setting if provided
        if "use_openvino" in kwargs and use_openvino_setter:
            use_openvino_setter(kwargs["use_openvino"])

        # Add active weight and OpenVINO to kwargs
        # These will be retrieved from global defaults via callbacks
        if active_weight_setter is not None:
            kwargs["active_weight"] = self._global_model_defaults.get("active_weight")
        if use_openvino_setter is not None:
            kwargs["use_openvino"] = self._global_model_defaults.get("use_openvino", False)

        # Filter parameters using whitelist
        filtered_kwargs = self.prepare_controller_parameters(**kwargs)

        # Create the project
        success = self.project_manager.create_new_project(**filtered_kwargs)

        if not success:
            log.error("project_workflow_service.create_project.failed")
            return {
                "success": False,
                "error_message": "Falha ao criar o novo projeto.",
                "wizard_metadata": None,
                "animal_method": None,
                "project_path": None,
                "import_success": None,
            }

        log.info(
            "project_workflow_service.create_project.success",
            path=self.project_manager.project_path,
        )

        # Update StateManager
        self.state_manager.update_project_state(
            source="project_workflow_service.create_project",
            project_path=Path(self.project_manager.project_path)
            if self.project_manager.project_path
            else None,
            project_data=self.project_manager.project_data.copy()
            if self.project_manager.project_data
            else {},
            active_zone_video=self.project_manager.get_active_zone_video(),
        )

        # Apply project model overrides
        self._using_project_overrides = True
        self.apply_project_model_overrides(
            overrides=None,
            active_weight_setter=active_weight_setter,
            use_openvino_setter=use_openvino_setter,
        )

        # Execute parquet import if wizard provided import configuration
        wizard_metadata = kwargs.get("_wizard_metadata", {})
        import_success = None

        if wizard_metadata:
            import_config = wizard_metadata.get("import_config", [])
            roi_merge_strategy = wizard_metadata.get("roi_merge_strategy", "replace")
            scanned_videos = wizard_metadata.get("scanned_videos", [])

            if import_config:
                log.info(
                    "project_workflow_service.create_project.importing_parquets",
                    video_count=len(import_config),
                    strategy=roi_merge_strategy,
                )
                import_success = self.project_manager.import_parquets_from_wizard(
                    import_config=import_config,
                    roi_merge_strategy=roi_merge_strategy,
                    scanned_videos=scanned_videos,
                )
                if import_success:
                    log.info("project_workflow_service.create_project.parquets_imported")
                else:
                    log.warning("project_workflow_service.create_project.parquet_import_failed")

        return {
            "success": True,
            "error_message": None,
            "wizard_metadata": wizard_metadata if wizard_metadata else None,
            "animal_method": animal_method,
            "project_path": Path(self.project_manager.project_path)
            if self.project_manager.project_path
            else None,
            "import_success": import_success,
        }

    # === Project Opening Orchestration ===

    def open_project(
        self,
        project_path: Path | str,
        active_weight_setter: callable | None = None,
        use_openvino_setter: callable | None = None,
        restore_detector_callback: callable | None = None,
        setup_zones_callback: callable | None = None,
    ) -> dict[str, Any]:
        """
        Orchestrate project opening workflow.

        Phase 5: Extracted from controller.open_project_workflow().

        This method handles:
        1. Loading project via ProjectManager
        2. Applying model overrides
        3. Restoring detector settings (via callback)
        4. Setting up zones (via callback)
        5. Collecting project information for display

        The controller is responsible for:
        - Setting up the detector
        - Loading the project view
        - Updating UI controls (checkboxes, dropdowns)
        - Displaying the success dialog

        Args:
            project_path: Path to project directory
            active_weight_setter: Optional callback to set active_weight
            use_openvino_setter: Optional callback to set use_openvino
            restore_detector_callback: Optional callback to restore detector settings
            setup_zones_callback: Optional callback to setup zones

        Returns:
            dict with:
                - success: bool
                - error_message: str | None
                - project_info: dict | None (name, videos_count, zone_status, etc.)
                - zone_data: ZoneData | None
                - resolved_weight: str | None
                - resolved_openvino: bool
        """
        from pathlib import Path

        log.info("project_workflow_service.open_project.start", path=project_path)

        # Load the project
        success = self.project_manager.load_project(project_path)

        if not success:
            log.error("project_workflow_service.open_project.failed")
            return {
                "success": False,
                "error_message": "Não foi possível carregar o projeto",
                "project_info": None,
                "zone_data": None,
                "resolved_weight": None,
                "resolved_openvino": False,
            }

        # Apply project-specific overrides
        self._using_project_overrides = True
        resolved_weight, resolved_openvino = self.apply_project_model_overrides(
            overrides=None,
            active_weight_setter=active_weight_setter,
            use_openvino_setter=use_openvino_setter,
        )

        log.info(
            "project_workflow_service.open_project.model_settings_applied",
            resolved_weight=resolved_weight,
            resolved_openvino=resolved_openvino,
        )

        # Restore detector settings if callback provided
        if restore_detector_callback:
            saved_detector_config = self.project_manager.get_detector_state()
            if saved_detector_config:
                restore_detector_callback(saved_detector_config)

        # Load and setup zones
        zone_data = self.project_manager.get_zone_data()
        if zone_data and (zone_data.polygon or zone_data.roi_polygons):
            log.info(
                "project_workflow_service.open_project.zones_found",
                has_polygon=bool(zone_data.polygon),
                roi_count=len(zone_data.roi_polygons),
            )

            # Setup zones via callback
            if setup_zones_callback:
                setup_zones_callback()

            log.info("project_workflow_service.open_project.zones_applied")

        # Collect project information for display
        project_name = self.project_manager.get_project_name()
        all_videos = self.project_manager.get_all_videos()
        videos_count = len(all_videos)
        zone_status = "✓" if zone_data and zone_data.polygon else "✗"
        roi_count = len(zone_data.roi_polygons) if zone_data else 0

        project_info = {
            "name": project_name,
            "videos_count": videos_count,
            "zone_status": zone_status,
            "roi_count": roi_count,
            "active_weight": resolved_weight or "Padrão",
            "use_openvino": resolved_openvino,
        }

        # Update StateManager
        self.state_manager.update_project_state(
            source="project_workflow_service.open_project",
            project_path=Path(project_path),
            project_data=self.project_manager.project_data.copy()
            if self.project_manager.project_data
            else {},
            active_zone_video=self.project_manager.get_active_zone_video(),
        )

        log.info(
            "project_workflow_service.open_project.success",
            project_name=project_name,
            videos=videos_count,
        )

        return {
            "success": True,
            "error_message": None,
            "project_info": project_info,
            "zone_data": zone_data,
            "resolved_weight": resolved_weight,
            "resolved_openvino": resolved_openvino,
        }

    # === Post-Creation Guide ===

    def generate_post_creation_guide(
        self, wizard_metadata: dict, check_suppression: bool = True
    ) -> dict[str, str] | None:
        """
        Generate post-creation guide content.

        Phase 5: Extracted from controller._show_post_creation_guide().

        This method analyzes the project and wizard metadata to generate
        a contextual onboarding message with recommended next steps.

        Args:
            wizard_metadata: Metadata from wizard with import_config, scanned_videos
            check_suppression: Whether to check suppression flags

        Returns:
            dict with 'title' and 'message' keys, or None if suppressed
        """
        import os

        if not wizard_metadata:
            return None

        # Check suppression flags
        if check_suppression:
            suppressed = os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get(
                "ZEBTRACK_SUPPRESS_POST_CREATION_GUIDE"
            )

            if suppressed:
                reason = (
                    "env_flag"
                    if os.environ.get("ZEBTRACK_SUPPRESS_POST_CREATION_GUIDE")
                    else "pytest"
                )
                log.info("project_workflow_service.post_creation_guide.skipped", reason=reason)
                return None

        # Extract wizard data
        import_config = wizard_metadata.get("import_config") or []
        scanned_videos = wizard_metadata.get("scanned_videos") or []

        # Build video source list
        project_videos = self.project_manager.get_all_videos()
        videos_source: list[dict] = []

        if project_videos:
            videos_source = project_videos
        elif scanned_videos:
            for video in scanned_videos:
                video_copy = dict(video)
                video_copy.setdefault("path", video_copy.get("video"))
                videos_source.append(video_copy)

        if not videos_source:
            return None

        # Build import lookup
        import_lookup = {
            config.get("video"): config for config in import_config if config.get("video")
        }

        key_map = {
            "has_arena": "import_arena",
            "has_rois": "import_rois",
            "has_trajectory": "import_trajectory",
        }

        def _feature_available(video: dict, feature_key: str) -> bool:
            """Check if a feature is available for a video."""
            if bool(video.get(feature_key)):
                return True

            metadata = video.get("metadata") or {}
            if bool(metadata.get(feature_key)):
                return True

            video_path = video.get("path") or video.get("video")
            if not video_path:
                return False

            import_cfg = import_lookup.get(video_path)
            if not import_cfg:
                return False

            import_key = key_map.get(feature_key)
            if not import_key:
                return False

            return bool(import_cfg.get(import_key))

        # Calculate statistics
        total_videos = len(videos_source)
        videos_with_arena = sum(
            1 for video in videos_source if _feature_available(video, "has_arena")
        )
        videos_with_rois = sum(
            1 for video in videos_source if _feature_available(video, "has_rois")
        )
        videos_with_trajectory = sum(
            1 for video in videos_source if _feature_available(video, "has_trajectory")
        )
        videos_pending = sum(
            1 for video in videos_source if not _feature_available(video, "has_trajectory")
        )

        # Build message
        lines: list[str] = []
        lines.append("🎉 Projeto criado com sucesso!")
        lines.append("")
        lines.append("📊 Status dos vídeos:")
        lines.append(f"  • Total de vídeos: {total_videos}")
        lines.append(f"  • Com arena definida: {videos_with_arena}")
        lines.append(f"  • Com ROIs definidas: {videos_with_rois}")
        lines.append(f"  • Com trajetória pronta: {videos_with_trajectory}")
        lines.append(f"  • Pendentes de processamento: {videos_pending}")
        lines.append("")
        lines.append("🚀 Próximos passos recomendados:")
        lines.append("")

        step_num = 1

        if videos_with_arena > 0 or videos_with_rois > 0:
            lines.append(f"{step_num}. Visualizar e ajustar zonas importadas")
            lines.append("   - Abra a aba 'Configuração de Zonas'")
            lines.append("   - Use o painel 'Selecionar Vídeo para Desenho'")
            lines.append("   - Clique duas vezes ou use 'Carregar Frame' para revisar")
            lines.append("   - Ajuste arena e ROIs conforme necessário")
            lines.append("")
            step_num += 1

        if videos_pending > 0:
            lines.append(f"{step_num}. Processar vídeos pendentes")
            lines.append("   - Vá até a aba 'Controle Principal'")
            lines.append("   - Confirme os intervalos de processamento")
            lines.append("   - Clique em 'Adicionar e Processar Novos Vídeos'")
            lines.append("")
            step_num += 1

        if videos_with_trajectory > 0:
            lines.append(f"{step_num}. Gerar relatórios")
            lines.append("   - Acesse a aba 'Relatórios'")
            lines.append("   - Navegue pela hierarquia de grupos, dias e sujeitos")
            lines.append("   - Gere relatórios individuais ou unificados conforme necessário")
            lines.append("")

        lines.append("💡 Dicas:")
        lines.append("  • Use a busca para localizar vídeos rapidamente")
        lines.append("  • Os símbolos de status indicam arenas, ROIs e trajetórias disponíveis")
        lines.append("  • Ajuste zonas antes de processar se necessário")

        message = "\n".join(lines)

        log.info(
            "project_workflow_service.post_creation_guide.generated",
            total_videos=total_videos,
            with_arena=videos_with_arena,
            with_rois=videos_with_rois,
            with_trajectory=videos_with_trajectory,
            pending=videos_pending,
        )

        return {"title": "Bem-vindo ao Projeto!", "message": message}
