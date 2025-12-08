from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.core.application_bootstrapper import BootstrapResult
    from zebtrack.core.dependency_container import MainViewModelDependencies

log = structlog.get_logger()


class AnalysisControlViewModel:
    """
    ViewModel responsible for Analysis Control workflows (Start/Stop/Pause/Processing).
    """

    def __init__(
        self,
        dependencies: MainViewModelDependencies,
        bootstrap_result: BootstrapResult,
        event_bus: Any,
    ):
        self.video_processing_orchestrator = bootstrap_result.video_processing_orchestrator
        self.video_processing_service = dependencies.video_processing_service
        self.processing_coordinator = dependencies.processing_coordinator
        # Phase 3A: analysis_orchestrator removed (no production calls)
        self.analysis_service = bootstrap_result.analysis_service
        self.state_manager = dependencies.state_manager
        self.ui_state_controller = bootstrap_result.ui_state_controller
        self.project_manager = dependencies.project_manager
        self.recorder = bootstrap_result.recorder
        self.settings = dependencies.settings_obj

        self.ui_event_bus = event_bus

        # Flags and state
        self.processing_thread = None
        self.processing_worker = None
        self.cancel_event = bootstrap_result.cancel_event

    @property
    def is_processing(self) -> bool:
        return self.state_manager.get_processing_state().is_processing

    def start_project_processing_workflow(self):
        # TODO Phase 3.4: Migrate to ProcessingCoordinator after extracting dialog logic
        # This method involves complex UI interaction (file picker, zone dialogs)
        # that needs to be factored out before migration
        if self.video_processing_orchestrator:
            self.video_processing_orchestrator.start_project_processing_workflow()

    def start_single_video_workflow(self, video_path, config, detector_vm=None):
        """
        Starts the workflow for a single video.
        Requires access to detector configuration (via HardwareStatusViewModel or passed in).
        """
        video_path = Path(video_path) if isinstance(video_path, str) else video_path

        self.project_manager.set_active_zone_video(str(video_path))

        # Validation
        animal_method = config.get("animal_method", self.settings.model_selection.animal_method)
        animals_per_aquarium = config.get("animals_per_aquarium", 1)

        if animal_method == "det" and animals_per_aquarium > 1:
            if self.ui_event_bus:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Configuração Inválida",
                        "message": (
                            f"O modo de detecção (det) suporta apenas 1 animal por aquário.\n"
                            f"Você configurou {animals_per_aquarium} animais por aquário.\n"
                            "Para múltiplos animais, use o modo de segmentação (seg)."
                        ),
                    },
                )
            return

        # We need to ensure detector is set up.
        # If detector_vm is provided, use it.
        if detector_vm:
            use_openvino = config.get("use_openvino", self.settings.model_selection.use_openvino)
            detector_vm.use_openvino = use_openvino  # setter

            if not detector_vm.detector:
                temp_animal_method = config.get("animal_method")
                if not detector_vm.setup_detector(temp_animal_method):
                    return

        self.ui_event_bus.publish_event(
            "ui:setup_zone_definition_for_single_video",
            {"video_path": video_path, "config": config},
        )

    def start_single_video_processing(self, **kwargs):
        # Phase 3.2: Redirect to ProcessingCoordinator (consolidated from VideoProcessingOrchestrator)
        if self.processing_coordinator:
            self.processing_coordinator.start_single_video_processing(
                video_path=kwargs.get("video_path"),
                config=kwargs.get("config", {}),
                zone_data=kwargs.get("zone_data"),
            )

    def cancel_current_analysis(self) -> None:
        # Check if ProcessingCoordinator has an active worker
        coord_worker_running = bool(
            self.processing_coordinator
            and self.processing_coordinator.processing_worker
            and self.processing_coordinator.processing_worker.is_running
        )
        coord_thread_running = bool(
            self.processing_coordinator
            and self.processing_coordinator.processing_thread
            and self.processing_coordinator.processing_thread.is_alive()
        )

        # Also check legacy attributes for backward compatibility
        legacy_worker_running = bool(self.processing_worker and self.processing_worker.is_running)
        legacy_thread_running = bool(self.processing_thread and self.processing_thread.is_alive())

        # If nothing is running, early return
        if not (
            coord_worker_running or coord_thread_running or legacy_worker_running or legacy_thread_running
        ):
            log.info("cancel_current_analysis.no_processing_active")
            return

        # Set cancel event to stop processing
        log.info(
            "cancel_current_analysis.setting_cancel_event",
            cancel_event_id=id(self.cancel_event),
            is_set_before=self.cancel_event.is_set(),
        )
        self.cancel_event.set()
        log.info(
            "cancel_current_analysis.cancel_event_set",
            cancel_event_id=id(self.cancel_event),
            is_set_after=self.cancel_event.is_set(),
        )

        # Delegate to coordinator to ensure worker is cancelled
        if self.processing_coordinator:
            self.processing_coordinator.cancel_processing()

        self.state_manager.update_processing_state(
            source="controller.cancel_current_analysis",
            cancel_requested=True,
        )

        if self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_SET_STATUS, {"message": "Cancelando análise em andamento..."}
            )

        if self.ui_state_controller:
            self.ui_state_controller._show_cancel_feedback()

        def _await_shutdown():
            # Handle legacy worker shutdown
            if self.processing_worker and self.processing_worker.is_running:
                self.processing_worker.cancel()
            elif self.processing_thread and self.processing_thread.is_alive():
                self.processing_thread.join(timeout=5.0)

            # Coordinator worker is handled by cancel_processing(),
            # but we can wait for its thread here if needed for UI responsiveness
            if (
                self.processing_coordinator
                and self.processing_coordinator.processing_thread
                and self.processing_coordinator.processing_thread.is_alive()
            ):
                self.processing_coordinator.processing_thread.join(timeout=5.0)

        threading.Thread(target=_await_shutdown, daemon=True).start()

    def save_manual_arena(self, polygon: list[tuple[int, int]]):
        return self.processing_coordinator.save_manual_arena(polygon)

    def set_main_arena_polygon(self, points: list) -> bool:
        if self.processing_coordinator:
            return self.processing_coordinator.set_main_arena_polygon(points)
        return False

    def add_roi_polygon(self, points: list, name: str, color: tuple) -> bool:
        if self.processing_coordinator:
            return self.processing_coordinator.add_roi_polygon(points, name, color)
        return False

    def auto_detect_zones(self, **kwargs):
        """
        Trigger auto-detection of aquarium zones via event.
        """
        if self.ui_event_bus:
            payload = {
                "video_path": kwargs.get("video_path"),
                "stabilization_frames": kwargs.get("stabilization_frames", 10),
            }
            self.ui_event_bus.publish_event(Events.ZONE_AUTO_DETECT, payload)

    def generate_parquet_summaries(self, video_paths: list[str]):
        """Generate summaries (Word/Excel) for the given video paths."""
        log.info("analysis_control.generate_summaries.start", count=len(video_paths))
        threading.Thread(
            target=self._generate_summaries_impl,
            args=(video_paths,),
            daemon=True
        ).start()

    def _generate_summaries_impl(self, video_paths: list[str]):
        """Implementation of summary generation running in a separate thread."""
        from zebtrack.analysis.reporter import Reporter
        import os

        if not self.ui_event_bus:
            return

        total = len(video_paths)
        for i, video_path in enumerate(video_paths):
            try:
                self.ui_event_bus.publish_event(
                    Events.UI_SET_STATUS,
                    {"message": f"Gerando relatório {i+1}/{total}..."}
                )

                # Check directly in PM to ensure we have valid entry
                entry = self.project_manager.find_video_entry(path=video_path)
                if not entry:
                    log.warning("generate_summaries.entry_not_found", path=video_path)
                    continue

                # Prepare Metadata
                video_stem = Path(video_path).stem
                experiment_id = entry.get("experiment_id", video_stem)

                metadata = dict(entry.get("metadata", {}))
                metadata.update({
                    "experiment_id": experiment_id,
                    "subject": entry.get("subject", "Unknown"),
                    "group": entry.get("group", "Unknown"),
                })

                results_dir = self.project_manager.resolve_results_directory(
                    experiment_id=experiment_id,
                    video_path=video_path,
                    metadata=metadata
                )

                # Check for trajectory file using correct naming convention
                parquet_filename = f"3_CoordMovimento_{experiment_id}.parquet"
                parquet_path = os.path.join(results_dir, parquet_filename)

                if not os.path.exists(parquet_path):
                    # Fallback to check generic name just in case
                    fallback_path = os.path.join(results_dir, "detections.parquet")
                    if os.path.exists(fallback_path):
                        parquet_path = fallback_path
                    else:
                        log.warning("generate_summaries.parquet_missing", path=parquet_path)
                        continue

                # Load Data
                # Retrieve zone data for analysis
                zone_data = self.project_manager.get_zone_data(video_path=video_path)
                arena_poly = zone_data.polygon or []

                # ROI objects
                from zebtrack.analysis.roi import ROI
                from shapely.geometry import Polygon  # Correctly import Polygon
                rois_list = []
                roi_polys = zone_data.roi_polygons or []
                roi_names = zone_data.roi_names or []
                roi_colors = zone_data.roi_colors or []
                roi_colors_dict = {}

                for idx, poly in enumerate(roi_polys):
                    name = roi_names[idx] if idx < len(roi_names) else f"ROI_{idx}"
                    color = roi_colors[idx] if idx < len(roi_colors) else (255, 0, 0)
                    # FIX: ROI expects a Shapely geometry, not a list of points.
                    # FIX: ROI constructor kwarg is 'geometry', not 'polygon'.
                    # FIX: These come from ZoneData (pixels), so specify coordinate_space="px".
                    try:
                        rois_list.append(ROI(name=name, geometry=Polygon(poly), coordinate_space="px"))
                        roi_colors_dict[name] = color
                    except Exception as e:
                        log.warning(f"Skipping invalid ROI {name}: {e}")

                # Retrieve analysis profile params
                analysis_profile = self.project_manager.resolve_analysis_profile(metadata)
                params = self.analysis_service.collect_analysis_parameters({"analysis_parameters": analysis_profile})

                # Load DataFrame using Service (efficient loading)
                df = self.analysis_service.load_trajectory_dataframe(parquet_path)

                # Run Analysis via DTO
                # Note: We assume 30 FPS if not available, or retrieve from video metadata if possible.
                # Ideally, FPS should be stored in parquet metadata or project entry.
                fps = entry.get("fps", 30.0)

                # Get Calibration
                pixelcm_x = 1.0
                pixelcm_y = 1.0
                # TODO: Retrieve real calibration from ProjectManager/Entry

                analysis_result = self.analysis_service.run_full_analysis_as_dto(
                    trajectory_df=df,
                    pixelcm_x=pixelcm_x,
                    pixelcm_y=pixelcm_y,
                    video_height_px=1080, # Placeholder, should come from video
                    arena_polygon_px=arena_poly,
                    rois=rois_list,
                    fps=fps,
                    metadata=metadata,
                    roi_colors=roi_colors_dict,
                    freezing_vel_threshold=params["freezing_vel_threshold"],
                    freezing_min_duration=params["freezing_min_duration"],
                    smoothing_window_length=params["smoothing_window_length"],
                    smoothing_polyorder=params["smoothing_polyorder"],
                    video_path=video_path
                )

                # Generate Reports
                reporter = Reporter.from_analysis(analysis_result)

                # sanitize helper
                def _san(s):
                    return "".join(c for c in str(s) if c.isalnum() or c in ('-', '_')).strip()

                # Construct descriptive names
                # Try to use display names if available or raw metadata
                group_tag = _san(metadata.get("group", "Grp")) or "Grp"
                day_tag = _san(metadata.get("day", "D")) or "D"
                subj_tag = _san(metadata.get("subject", "S")) or "S"

                # Format: Relatorio_Group_Day_Subject_ExperimentID
                base_name = f"{group_tag}_{day_tag}_{subj_tag}_{experiment_id}"

                excel_filename = f"Sumario_{base_name}.xlsx"
                docx_filename = f"Relatorio_{base_name}.docx"

                # Excel Summary
                excel_path = os.path.join(results_dir, excel_filename)
                reporter.export_summary_data(excel_path, format="excel")

                # Word Report
                docx_path = os.path.join(results_dir, docx_filename)
                reporter.export_individual_report(docx_path)

                # Register outputs with ProjectManager to keep state consistent
                # This ensures the 'summary' flag is set in the project data
                self.project_manager.register_processing_outputs(
                    video_path=video_path,
                    results_dir=results_dir,
                    summary_excel=excel_path,
                    report_path=docx_path
                )

                log.info("generate_summaries.success", video=video_path, report=docx_path)

            except Exception as e:
                log.error("generate_summaries.failed", video=video_path, error=str(e), exc_info=True)

        self.ui_event_bus.publish_event(Events.UI_SET_STATUS, {"message": "Geração de relatórios concluída."})

        # Refresh tree to show new artifacts
        self.ui_event_bus.publish_event(
            Events.UI_REFRESH_PROJECT_VIEWS,
            {"reason": "reports_generated", "append_summary": True, "immediate": False}
        )

    def _process_single_video(self, detector, **kwargs):
        return self.video_processing_service.process_single_video(
            detector=detector, recorder=self.recorder, **kwargs
        )
