"""Sequential multi-aquarium processing coordinator.

Phase 4: Extracted from ProcessingCoordinator.
Handles the sequential processing mode where each aquarium is processed
in a separate complete video pass (2 passes for 2 aquariums).

Estimated size: ~450 lines (target <800).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.coordinators.base_coordinator import BaseCoordinator
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from threading import Event

    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.services.detector_service import DetectorService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.ui_scheduler import UIScheduler
    from zebtrack.io.recorder_factory import RecorderFactory
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


class SequentialProcessingCoordinator(BaseCoordinator):
    """Coordinator for sequential multi-aquarium processing.

    Responsibilities:
        - Starting sequential multi-aquarium processing workflows
        - Processing each aquarium in sequence (one complete video pass each)
        - Advancing to the next aquarium when the current one completes
        - Triggering report generation after all aquariums are processed

    Phase 4: All methods moved from ProcessingCoordinator without logic changes.
    """

    def __init__(
        self,
        state_manager: StateManager,
        project_manager: ProjectManager,
        detector_service: DetectorService,
        settings_obj: Settings,
        ui_coordinator: UIScheduler,
        cancel_event: Event,
        recorder_factory: RecorderFactory | None = None,
        event_bus: EventBus | None = None,
        view: Any = None,
        root: Any = None,
    ) -> None:
        super().__init__(state_manager, event_bus)
        self.project_manager = project_manager
        self.detector_service = detector_service
        self.settings = settings_obj
        self.ui_coordinator = ui_coordinator
        self.cancel_event = cancel_event
        self.recorder_factory = recorder_factory
        self.view = view
        self.root = root

        # Sequential context state
        self._sequential_context: dict[str, Any] | None = None

        # Cross-coordinator references (set post-construction)
        self._report_coordinator: Any = None
        self._progress_coordinator: Any = None
        self._video_processing_coordinator: Any = None

        log.info("sequential_processing_coordinator.initialized")

    @property
    def sequential_context(self) -> dict[str, Any] | None:
        """Expose sequential context for cross-coordinator access."""
        return self._sequential_context

    @sequential_context.setter
    def sequential_context(self, value: dict[str, Any] | None) -> None:
        self._sequential_context = value

    # ========================================================================
    # Sequential Processing Entry Point
    # ========================================================================

    def _start_sequential_multi_aquarium_processing(
        self,
        video_path: str,
        multi_zone_data: Any,
        single_video_config: dict | None = None,
    ) -> None:
        """Start sequential multi-aquarium processing (one video pass per aquarium).

        Args:
            video_path: Path to the source video file.
            multi_zone_data: MultiAquariumZoneData with aquarium definitions.
            single_video_config: Optional per-video configuration overrides.
        """
        aquariums = multi_zone_data.aquariums or []
        aq_count = len(aquariums)

        log.info(
            "processing_coordinator.sequential.start",
            video=os.path.basename(video_path),
            aquarium_count=aq_count,
        )

        # Initialize sequential context
        self._sequential_context = {
            "video_path": video_path,
            "multi_zone_data": multi_zone_data,
            "single_video_config": single_video_config,
            "aquariums": aquariums,
            "current_index": 0,
            "total": aq_count,
            "completed": [],
            "failed": [],
        }

        # Start processing the first aquarium
        self._process_next_aquarium_in_sequence()

    def _process_next_aquarium_in_sequence(self) -> None:
        """Process the next aquarium in the sequential workflow.

        Called initially and after each aquarium completes.
        """
        ctx = self._sequential_context
        if not ctx:
            log.warning("processing_coordinator.sequential.no_context")
            return

        idx = ctx["current_index"]
        total = ctx["total"]

        if idx >= total:
            # All aquariums processed
            self._finalize_sequential_processing()
            return

        aquarium = ctx["aquariums"][idx]
        video_path = ctx["video_path"]
        aq_id = getattr(aquarium, "id", idx)

        log.info(
            "processing_coordinator.sequential.next_aquarium",
            index=idx,
            total=total,
            aquarium_id=aq_id,
            video=os.path.basename(video_path),
        )

        self._publish_event(
            Events.UI_SET_STATUS,
            {"message": f"Processando aquário {aq_id + 1}/{total}..."},
        )

        self._start_single_aquarium_for_sequential(aquarium, ctx)

    def _start_single_aquarium_for_sequential(self, aquarium: Any, ctx: dict[str, Any]) -> None:
        """Start processing a single aquarium in sequential mode.

        Converts aquarium data to standard ZoneData and runs the standard
        single-video processing pipeline.
        """
        from zebtrack.core.detection import ZoneData
        from zebtrack.core.video.processing_worker import (
            ProcessingCallbacks,
            ProcessingContext,
            ProcessingWorker,
        )

        video_path = ctx["video_path"]
        _multi_zone_data = ctx["multi_zone_data"]
        single_video_config = ctx.get("single_video_config")
        aq_id = getattr(aquarium, "id", ctx["current_index"])
        experiment_id = os.path.splitext(os.path.basename(video_path))[0]

        # Convert aquarium to ZoneData for standard processing
        zone_data = ZoneData(
            polygon=aquarium.polygon or [],
            roi_polygons=getattr(aquarium, "roi_polygons", []) or [],
            roi_names=getattr(aquarium, "roi_names", []) or [],
            roi_colors=getattr(aquarium, "roi_colors", []) or [],
        )

        # Resolve results directory for this aquarium
        aq_metadata = {
            "group": getattr(aquarium, "group", ""),
            "group_display_name": getattr(aquarium, "group", ""),
            "subject": getattr(aquarium, "subject_id", ""),
            "day": getattr(aquarium, "day", "1"),
        }
        results_dir = str(
            self.project_manager.resolve_results_directory(
                experiment_id=f"{experiment_id}_aq{aq_id}",
                video_path=video_path,
                metadata=aq_metadata,
            )
        )
        os.makedirs(results_dir, exist_ok=True)

        # Set up detector zones
        self.detector_service.configure_zones(zones_data=zone_data)

        # Determine intervals
        analysis_interval = self.settings.video_processing.processing_interval
        display_interval = self.settings.video_processing.display_interval

        if single_video_config:
            if "analysis_interval_frames" in single_video_config:
                analysis_interval = int(single_video_config["analysis_interval_frames"])
            if "display_interval_frames" in single_video_config:
                display_interval = int(single_video_config["display_interval_frames"])

        # Build processing context (matches ProcessingContext dataclass fields)
        video_info = {
            "video_path": video_path,
            "experiment_id": f"{experiment_id}_aq{aq_id}",
            "output_dir": results_dir,
            **aq_metadata,
        }
        processing_context = ProcessingContext(
            videos_to_process=[video_info],
            output_base_dir=results_dir,
            cancel_event=self.cancel_event,
            settings=self.settings,
            single_video_config=single_video_config,
            zone_data={
                "polygon": zone_data.polygon,
                "roi_polygons": zone_data.roi_polygons,
                "roi_names": zone_data.roi_names,
                "roi_colors": zone_data.roi_colors,
            },
            analysis_interval_frames=analysis_interval,
            display_interval_frames=display_interval,
        )

        # Build callbacks
        def on_sequential_complete(result: dict) -> None:
            """Handle completion of a single aquarium in sequential mode."""
            success = result.get("success", True)

            if success:
                ctx["completed"].append(aq_id)
                # Register outputs
                entry = self.project_manager.find_video_entry(path=video_path)
                if entry:
                    multi_outputs = entry.setdefault("multi_aquarium_outputs", {})
                    aq_key = str(aq_id)
                    multi_outputs.setdefault(aq_key, {})
                    multi_outputs[aq_key]["results_dir"] = results_dir

                    # Scan for generated files
                    traj_candidates = [
                        f
                        for f in os.listdir(results_dir)
                        if f.startswith("3_CoordMovimento") and f.endswith(".parquet")
                    ]
                    if traj_candidates:
                        pf = multi_outputs[aq_key].setdefault("parquet_files", {})
                        pf["trajectory"] = os.path.join(results_dir, traj_candidates[0])

                    # Update metadata
                    multi_outputs[aq_key]["group"] = aq_metadata.get("group", "")
                    multi_outputs[aq_key]["subject_id"] = aq_metadata.get("subject", "")
                    multi_outputs[aq_key]["day"] = aq_metadata.get("day", "1")

                    self.project_manager.save_project()

                log.info(
                    "processing_coordinator.sequential.aquarium_done",
                    aquarium_id=aq_id,
                    success=True,
                )
            else:
                ctx["failed"].append(aq_id)
                log.warning(
                    "processing_coordinator.sequential.aquarium_failed",
                    aquarium_id=aq_id,
                    error=result.get("error", ""),
                )

            # Advance to next aquarium
            ctx["current_index"] += 1

            # Schedule next aquarium on the main thread
            if self.root:
                self.root.after(100, self._process_next_aquarium_in_sequence)
            else:
                self._process_next_aquarium_in_sequence()

        callbacks = ProcessingCallbacks(
            on_started=lambda: log.info(
                "processing_coordinator.sequential.aq_started",
                aquarium=aq_id,
            ),
            on_progress=lambda idx, total, exp_id, frac, msg, stats: None,
            on_frame_processed=lambda frame, dets, fn: None,
            on_video_completed=lambda idx, total, exp_id, success: on_sequential_complete(
                {"success": success}
            ),
            on_error=lambda exc, msg: log.warning(
                "processing_coordinator.sequential.aq_error",
                aquarium=aq_id,
                error=str(exc),
            ),
            on_completed=lambda success, msg, data: on_sequential_complete(
                {"success": success, "error": msg if not success else ""}
            ),
            on_fatal_error=lambda exc, msg, data: on_sequential_complete(
                {"success": False, "error": str(exc)}
            ),
        )

        # Create worker and start processing
        worker = ProcessingWorker(
            context=processing_context,
            callbacks=callbacks,
        )

        # Store reference for cancellation access
        vpc = self._video_processing_coordinator
        if vpc:
            vpc.processing_worker = worker

        thread = worker.start_in_thread()

        if vpc:
            vpc.processing_thread = thread

    # ========================================================================
    # Sequential Advancement (from _on_video_completed)
    # ========================================================================

    def _handle_sequential_multi_aquarium(self, video_path: str) -> bool:
        """Check and advance sequential multi-aquarium processing.

        Called from _on_video_completed to check if we need to advance
        to the next aquarium in a sequential workflow.

        Returns:
            True if sequential processing was active and handled the event.
        """
        ctx = self._sequential_context
        if not ctx:
            return False

        if ctx.get("video_path") != video_path:
            return False

        # The on_sequential_complete callback handles advancement
        # This method is for the case where _on_video_completed is called
        # by the batch processing path
        return True

    def _handle_sequential_single_video_start(
        self, video_path: str, multi_zone_data: Any, single_video_config: dict | None
    ) -> bool:
        """Handle starting sequential processing for a single video.

        Called from start_single_video_processing when the video has
        multi-aquarium data with sequential_processing=True.

        Returns:
            True if sequential processing was started.
        """
        if not multi_zone_data or not getattr(multi_zone_data, "sequential_processing", False):
            return False

        log.info(
            "processing_coordinator.sequential.single_video_start",
            video=os.path.basename(video_path),
        )

        self._start_sequential_multi_aquarium_processing(
            video_path, multi_zone_data, single_video_config
        )
        return True

    # ========================================================================
    # Finalization
    # ========================================================================

    def _finalize_sequential_processing(self) -> None:
        """Finalize sequential multi-aquarium processing.

        Generates reports for all aquariums and shows completion summary.
        """
        ctx = self._sequential_context
        if not ctx:
            return

        video_path = ctx["video_path"]
        completed = ctx.get("completed", [])
        failed = ctx.get("failed", [])

        log.info(
            "processing_coordinator.sequential.finalized",
            video=os.path.basename(video_path),
            completed=len(completed),
            failed=len(failed),
        )

        # Reset state
        self.state_manager.update_processing_state(
            source="processing_coordinator.sequential.finalized",
            is_processing=False,
            current_video=None,
        )

        if self.view and self.root:

            def _cleanup_ui() -> None:
                if self.view:
                    self.ui_coordinator.update_view(self.view, "stop_analysis_view_mode")
                    self.ui_coordinator.hide_progress_bar(self.view)

            self.root.after(0, _cleanup_ui)

        # Generate reports if report coordinator is available
        if self._report_coordinator:
            try:
                self._report_coordinator.generate_project_reports([video_path])
            except Exception:  # except Exception justified: non-critical post-processing reports
                log.warning(
                    "processing_coordinator.sequential.report_generation.suppressed",
                    exc_info=True,
                )

        # Show summary
        total = len(completed) + len(failed)
        msg = f"Processamento sequencial concluído: {len(completed)}/{total} aquários."
        if failed:
            msg += f"\n\n❌ Falhas: {', '.join(str(f) for f in failed)}"

        self._publish_event(
            Events.UI_SHOW_INFO if not failed else Events.UI_SHOW_WARNING,
            {"title": "Processamento Sequencial", "message": msg},
        )
        self._publish_event(Events.UI_REFRESH_PROJECT_VIEWS, {})

        # Clear context
        self._sequential_context = None
