"""Video selection, validation, and zone-loading mixin for VPC.

Phase 4 size reduction: Extracted from VideoProcessingCoordinator to keep
the main coordinator under 1200 lines.

This mixin provides:
- Video selection with dialog interaction
- Processing precondition validation
- Live session detection
- Zone loading for eligible videos
- Project settings snapshot creation
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.coordinators.processing_types import ValidationResult
from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.ui.event_bus_v2 import UIEvents

if TYPE_CHECKING:
    from zebtrack.core.detection import ZoneData
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.video.processing_worker import ProcessingWorker
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2

log = structlog.get_logger()


class VideoSelectionMixin:
    """Mixin providing video selection, validation, and zone loading.

    Must be composed with a coordinator that satisfies
    :class:`~zebtrack.coordinators._protocols.VideoSelectionHost`.

    Host-provided attributes (declared for mypy, set by coordinator __init__):
    """

    # Declare host-provided attributes for mypy (set by coordinator __init__)
    project_manager: ProjectManager
    state_manager: StateManager
    settings: Settings
    event_bus: EventBusV2 | None
    view: Any
    processing_worker: ProcessingWorker | None
    processing_thread: Any
    _multi_aquarium_coordinator: Any

    # Host-provided method (declared for mypy, implemented by coordinator)
    _publish_event: Any  # (event: Any, data: Any) -> None

    # ------------------------------------------------------------------
    # Video selection
    # ------------------------------------------------------------------

    def select_eligible_videos(
        self, skip_dialog, ready_traj, ready_zones, arena_only, without_arena
    ) -> list[dict] | None:
        """Select eligible videos for processing."""
        eligible_videos: list[dict] = []

        if ready_traj and self.view:
            if not self.view.dialog_manager.ask_ok_cancel(
                "Resultados Existentes",
                f"{len(ready_traj)} vídeos já possuem trajetórias processadas.\n"
                "Deseja reprocessá-los (sobrescrevendo os dados anteriores)?",
            ):
                ready_traj = []

        if skip_dialog:
            eligible_videos.extend(ready_traj)
            eligible_videos.extend(ready_zones)
            eligible_videos.extend(arena_only)
            if not eligible_videos:
                self._publish_event(
                    UIEvents.UI_SHOW_INFO,
                    {
                        "title": "Processamento",
                        "message": "Nenhum dos vídeos selecionados contém arena definida.",
                    },
                )
                return None
        else:
            if not self.view:
                return None
            dialog_result = self.view.dialog_manager.show_pending_videos_dialog(
                ready_with_trajectory=ready_traj,
                ready_with_zones=ready_zones,
                arena_only=arena_only,
                without_arena=without_arena,
            )
            if not dialog_result or not dialog_result.get("confirmed"):
                return None
            eligible_videos.extend(ready_traj)
            eligible_videos.extend(ready_zones)
            if dialog_result.get("include_arena_only"):
                eligible_videos.extend(arena_only)
            if not eligible_videos:
                self._publish_event(
                    UIEvents.UI_SHOW_INFO,
                    {
                        "title": "Processamento",
                        "message": "Nenhum vídeo foi selecionado para processamento.",
                    },
                )
                return None

        return eligible_videos

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_can_start_processing(
        self,
        *,
        check_project_loaded: bool = True,
        check_zones: bool = False,
        check_videos_exist: bool = False,
    ) -> ValidationResult:
        """Validate that processing can start."""
        processing_state = self.state_manager.get_processing_state()
        if processing_state.is_processing:
            worker_running = bool(self.processing_worker and self.processing_worker.is_running)
            thread_running = bool(self.processing_thread and self.processing_thread.is_alive())
            live_active = self._is_live_session_currently_active(processing_state)

            if not live_active and not worker_running and not thread_running:
                self.state_manager.update_processing_state(
                    source="validation.stale_reset",
                    is_processing=False,
                    current_video=None,
                    cancel_requested=False,
                    is_live_session_active=False,
                )
                mac = self._multi_aquarium_coordinator
                if mac:
                    mac._publish_processing_mode(source="validation.stale_reset", force=True)
            else:
                return ValidationResult.failure(
                    error_code="processing_already_active",
                    error_message=(
                        "Uma análise de vídeo já está em andamento. "
                        "Por favor, aguarde ou cancele a análise atual."
                    ),
                    context={"current_video": processing_state.current_video},
                )

        if check_project_loaded and not self.project_manager.project_path:
            return ValidationResult.failure(
                error_code="no_project_loaded",
                error_message="Nenhum projeto carregado",
            )

        if check_zones:
            zone_data = self.project_manager.get_zone_data()
            if not zone_data or not zone_data.polygon:
                return ValidationResult.failure(
                    error_code="no_main_arena",
                    error_message="O polígono principal do aquário não foi definido",
                )

        if check_videos_exist:
            all_videos = self.project_manager.get_all_videos() or []
            if not all_videos:
                return ValidationResult.failure(
                    error_code="no_videos_in_project",
                    error_message="Nenhum vídeo cadastrado no projeto atualmente",
                )

        return ValidationResult.success()

    def _is_live_session_currently_active(self, processing_state: Any) -> bool:
        """Check if a live session is truly active."""
        state_flag = bool(getattr(processing_state, "is_live_session_active", False))
        if not state_flag:
            return False
        controller = getattr(self.view, "controller", None) if self.view else None
        live_cam_coordinator = (
            getattr(controller, "live_camera_session_coordinator", None) if controller else None
        )
        if live_cam_coordinator is None:
            return state_flag
        is_active_fn = getattr(live_cam_coordinator, "is_live_session_active", None)
        if callable(is_active_fn):
            try:
                result = is_active_fn()
                if isinstance(result, bool):
                    return result
            except (AttributeError, RuntimeError):
                log.debug("live_session.active_check.fallback", exc_info=True)
        camera = getattr(getattr(live_cam_coordinator, "live_camera_service", None), "camera", None)
        return camera is not None

    # ------------------------------------------------------------------
    # Selection helpers
    # ------------------------------------------------------------------

    def _show_validation_error(self, val) -> None:
        """Show validation error to UI."""
        self._publish_event(
            UIEvents.UI_SHOW_WARNING,
            {"title": "Validação Falhou", "message": val.error_message},
        )

    def _handle_targeted_selection_errors(
        self, selection_result, video_paths: list[Path | str]
    ) -> bool:
        """Handle UI feedback for targeted selection mode errors."""
        if not video_paths:
            self._publish_event(
                UIEvents.UI_SHOW_INFO,
                {"title": "Processamento", "message": "Nenhum vídeo selecionado."},
            )
            return False
        if selection_result.has_missing:
            sample = [os.path.basename(p) for p in selection_result.missing_targets[:5]]
            if len(selection_result.missing_targets) > 5:
                sample.append(f"... (+{len(selection_result.missing_targets) - 5})")
            self._publish_event(
                UIEvents.UI_SHOW_WARNING,
                {
                    "title": "Vídeos fora do projeto",
                    "message": "Itens selecionados não pertencem ao projeto:\n" + "\n".join(sample),
                },
            )
        if selection_result.candidate_count == 0:
            self._publish_event(
                UIEvents.UI_SHOW_INFO,
                {
                    "title": "Processamento",
                    "message": "Nenhum dos vídeos selecionados pertence ao projeto ativo.",
                },
            )
            return False
        return True

    def _handle_pending_selection_errors(self, selection_result) -> bool:
        """Handle UI feedback for pending selection mode errors."""
        if selection_result.candidate_count == 0:
            self._publish_event(
                UIEvents.UI_SHOW_INFO,
                {"title": "Processamento", "message": "Nenhum vídeo pendente para processar."},
            )
            return False
        return True

    def _extract_and_validate_candidate_paths(self, candidate_entries) -> list[str] | None:
        """Extract and validate video paths from candidate entries."""
        candidate_paths = [
            v.get("path")
            for v in candidate_entries
            if isinstance(v.get("path"), str) and v.get("path")
        ]
        if not candidate_paths:
            self._publish_event(
                UIEvents.UI_SHOW_ERROR,
                {
                    "title": "Erro",
                    "message": "Não foi possível localizar caminhos válidos para os vídeos.",
                },
            )
            return None
        return candidate_paths

    def _handle_missing_files_warning(self, scan_result) -> None:
        """Show warning UI if scanned files are missing."""
        if scan_result.has_missing:
            sample = [os.path.basename(p) for p in scan_result.missing_files[:5]]
            if len(scan_result.missing_files) > 5:
                sample.append(f"... (+{len(scan_result.missing_files) - 5})")
            self._publish_event(
                UIEvents.UI_SHOW_WARNING,
                {
                    "title": "Vídeos Não Encontrados",
                    "message": "Vídeos ignorados:\n" + "\n".join(sample),
                },
            )

    # ------------------------------------------------------------------
    # Zone loading
    # ------------------------------------------------------------------

    def _load_zones_for_eligible_videos(self, eligible_videos: list) -> None:
        """Load zone data from parquet files for eligible videos."""
        zones_updated = False
        from zebtrack.core.project.zone_manager import ZoneManager

        for video_info in eligible_videos:
            video_path = video_info.get("path", "")
            experiment_id = os.path.splitext(os.path.basename(video_path))[0] if video_path else ""
            metadata = video_info.get("metadata", {})
            results_path = self.project_manager.resolve_results_directory(
                experiment_id=experiment_id,
                video_path=video_path,
                metadata=metadata,
            )
            video_info["results_dir"] = str(results_path)

            multi_data = self.project_manager.get_multi_aquarium_zone_data(video_path)
            if multi_data:
                video_info["zone_data"] = ZoneManager.multi_aquarium_zone_data_to_dict(multi_data)
                continue

            if video_info.get("has_arena") or video_info.get("has_rois"):
                try:
                    zone_data: ZoneData | None = ProjectManager.load_zones_from_parquet(video_info)
                except (OSError, ValueError, KeyError):
                    log.debug("video_selection.load_zones_from_parquet.fallback", video=video_path)
                    zone_data = None

                if not zone_data or not zone_data.polygon:
                    zone_data = self.project_manager.get_zone_data(video_path=video_path)

                if zone_data and (zone_data.polygon or zone_data.roi_polygons):
                    self.project_manager.save_zone_data(
                        zone_data, video_info["path"], persist=False
                    )
                    zones_updated = True
                    video_info["zone_data"] = {
                        "polygon": zone_data.polygon,
                        "roi_polygons": zone_data.roi_polygons,
                        "roi_names": zone_data.roi_names,
                        "roi_colors": zone_data.roi_colors,
                    }

        if zones_updated and self.project_manager.project_path:
            self.project_manager.save_project()

    # ------------------------------------------------------------------
    # Settings snapshot
    # ------------------------------------------------------------------

    def _create_project_settings_snapshot(self) -> Any:
        """Create a Settings object with project-specific overrides applied."""
        snapshot = self.settings.model_copy(deep=True)
        project_data = self.project_manager.project_data or {}

        if "analysis_offset_frames" in project_data:
            snapshot.video_processing.processing_offset = project_data["analysis_offset_frames"]

        analysis_params = project_data.get("analysis_parameters", {})
        if "smoothing_window_length" in analysis_params:
            snapshot.trajectory_smoothing.window_length = analysis_params["smoothing_window_length"]
        if "smoothing_polyorder" in analysis_params:
            snapshot.trajectory_smoothing.polyorder = analysis_params["smoothing_polyorder"]

        roi_settings = project_data.get("roi_settings", {})
        if "roi_inclusion_rule" in roi_settings:
            snapshot.roi_inclusion_rule = roi_settings["roi_inclusion_rule"]
        if "roi_buffer_radius_value" in roi_settings:
            snapshot.roi_buffer_radius_value = roi_settings["roi_buffer_radius_value"]
        if "roi_min_bbox_overlap_ratio" in roi_settings:
            snapshot.roi_min_bbox_overlap_ratio = roi_settings["roi_min_bbox_overlap_ratio"]

        behavioral_config = project_data.get("behavioral_config", {})
        if behavioral_config and hasattr(snapshot, "behavioral_analysis"):
            ba = snapshot.behavioral_analysis
            if "aquarium_perspective" in behavioral_config:
                raw = (
                    str(behavioral_config["aquarium_perspective"]).strip().lower().replace("-", "_")
                )
                ba.aquarium_perspective = (
                    "top_down"
                    if raw in {"top_down", "top_down_view", "topdown", "top"}
                    else "lateral"
                )
            if "thigmotaxis_distance_cm" in behavioral_config:
                ba.default_thigmotaxis_distance_cm = behavioral_config["thigmotaxis_distance_cm"]
            if "geotaxis_distance_cm" in behavioral_config:
                ba.default_geotaxis_distance_cm = behavioral_config["geotaxis_distance_cm"]
            if "geotaxis_num_zones" in behavioral_config:
                ba.default_geotaxis_num_zones = behavioral_config["geotaxis_num_zones"]
            if "geotaxis_bottom_zones" in behavioral_config:
                ba.default_geotaxis_bottom_zones = behavioral_config["geotaxis_bottom_zones"]
            if "geotaxis_mode" in behavioral_config:
                ba.geotaxis_mode = behavioral_config["geotaxis_mode"]

        return snapshot
