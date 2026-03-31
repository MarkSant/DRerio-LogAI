"""Live Analysis Post-Processor — session completion, arena definition, reporting.

Extracted from LiveCameraService (Phase 2.2 decomposition).
Provides the ``LiveAnalysisPostProcessorMixin`` mixed into ``LiveCameraService``.
"""

from __future__ import annotations

import datetime
import glob
import math
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import structlog

if TYPE_CHECKING:
    from zebtrack.core.detection.multi_aquarium_detector import MultiAquariumDetector
    from zebtrack.core.main_view_model import MainViewModel
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.recording.recording_service import RecordingService
    from zebtrack.core.services.detector_service import DetectorService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.io.camera import Camera
    from zebtrack.ui.dialogs import LivePreviewWindow
    from zebtrack.ui.event_bus_v2 import EventBusV2

log = structlog.get_logger()


class LiveAnalysisPostProcessorMixin:
    """Mixin providing session-completion, arena-definition, and reporting logic.

    Methods:
        _on_session_complete, _show_completion_message,
        _start_recording_after_arena, _define_arena_from_detections,
        _run_multi_aquarium_detection
    """

    # -- Typing stubs for attributes defined by LiveCameraService.__init__ --
    controller: MainViewModel | None
    state_manager: StateManager
    project_manager: ProjectManager
    recording_service: RecordingService
    detector_service: DetectorService
    settings: Any
    recorder: Any
    event_bus: EventBusV2
    root: Any
    _lock: threading.Lock
    _analysis_completed: bool
    _session_duration_s: float
    _actual_fps: float
    _actual_height: int
    _actual_width: int
    _analysis_params: dict
    _experiment_id: str
    _current_base_name: str
    _animals_per_aquarium: int
    _aquarium_detection_phase: bool
    _detected_aquarium_bboxes: list
    _arena_defined_event: threading.Event
    _multi_aq_detector: MultiAquariumDetector | None

    # Properties from facade
    camera: Camera | None
    preview_window: LivePreviewWindow | None
    is_capturing_for_video: bool
    current_output_dir: Path | None

    # Methods from other mixins
    def stop_session(self) -> bool: ...  # type: ignore[empty-body]
    def _setup_session_timer(self, duration_s: float, output_dir: Path) -> None: ...

    def _on_session_complete(self, output_dir: Path) -> None:  # noqa: C901
        """Handle session completion and trigger post-processing analysis.

        Task 1.4: Thread-safe check-and-set pattern to prevent race conditions.
        """
        with self._lock:
            if self._analysis_completed:
                log.info(
                    "live_camera_service.analysis_already_completed",
                    output_dir=str(output_dir),
                )
                return
            self._analysis_completed = True

        log.info("live_camera_service.session_complete", output_dir=str(output_dir))

        # Stop threads and cleanup
        self.stop_session()

        log.info("live_camera_service.starting_post_analysis", output_dir=str(output_dir))

        def _run_post_analysis() -> None:  # noqa: C901
            """Background thread worker for post-processing analysis."""
            try:
                from zebtrack.analysis.analysis_service import AnalysisService
                from zebtrack.analysis.reporters import (
                    ExcelReporter,
                    ReporterContext,
                    WordReporter,
                )

                # Find generated trajectory parquet
                trajectory_files = glob.glob(str(output_dir / "3_CoordMovimento_*.parquet"))

                if not trajectory_files:
                    log.warning(
                        "live_camera_service.no_trajectory_found", output_dir=str(output_dir)
                    )
                    if self.root:
                        self.root.after(0, self._show_completion_message, output_dir, False)
                    return

                trajectory_file = Path(trajectory_files[0])
                df = pd.read_parquet(trajectory_file)

                if df.empty:
                    log.warning("live_camera_service.empty_trajectory")
                    if self.root:
                        self.root.after(
                            0,
                            self._show_completion_message,
                            output_dir,
                            False,
                            None,
                            "no_detections",
                        )
                    return

                # --- FULL BEHAVIORAL ANALYSIS ---
                log.info("live_camera_service.full_analysis.start")

                analysis_service = AnalysisService(settings_obj=self.settings)
                params = analysis_service.collect_analysis_parameters(
                    self.project_manager.project_data
                )

                # Update with session-specific overrides
                if self._analysis_params:
                    if "freezing_velocity_threshold" in self._analysis_params:
                        params["freezing_vel_threshold"] = self._analysis_params[
                            "freezing_velocity_threshold"
                        ]
                    if "freezing_min_duration_s" in self._analysis_params:
                        params["freezing_min_duration"] = self._analysis_params[
                            "freezing_min_duration_s"
                        ]
                    if "smoothing_window_length" in self._analysis_params:
                        params["smoothing_window_length"] = self._analysis_params[
                            "smoothing_window_length"
                        ]
                    if "smoothing_polyorder" in self._analysis_params:
                        params["smoothing_polyorder"] = self._analysis_params["smoothing_polyorder"]
                    if "behavioral_analysis" in self._analysis_params:
                        params["behavioral_config"].update(
                            self._analysis_params["behavioral_analysis"]
                        )

                # Get calibration and zone data
                calib_data = self.project_manager.project_data.get("calibration", {})
                pixelcm_x = calib_data.get("pixelcm_x", 1.0)
                pixelcm_y = calib_data.get("pixelcm_y", 1.0)
                video_height = self._actual_height

                zone_data = self.project_manager.get_zone_data()
                arena_polygon = zone_data.polygon or []
                arena_polygon_tuples = [(float(p[0]), float(p[1])) for p in arena_polygon]

                # Build ROI objects
                from zebtrack.analysis.roi import ROI

                rois = []
                roi_colors = {}
                if zone_data.roi_polygons:
                    for i, poly in enumerate(zone_data.roi_polygons):
                        name = (
                            zone_data.roi_names[i] if i < len(zone_data.roi_names) else f"ROI_{i}"
                        )
                        color = (
                            zone_data.roi_colors[i]
                            if i < len(zone_data.roi_colors)
                            else (255, 0, 0)
                        )
                        from shapely.geometry import Polygon

                        rois.append(ROI(name=name, geometry=Polygon(poly), coordinate_space="px"))
                        roi_colors[name] = color

                # Run full analysis
                fps = self._actual_fps
                video_filename = f"{self._current_base_name}.mp4"
                video_path = output_dir / video_filename

                metadata = {
                    "experiment_id": self._experiment_id,
                    "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "camera_index": self._analysis_params.get("camera_index", "N/A"),
                    "num_aquariums": 1,
                    "animals_per_aquarium": self._animals_per_aquarium,
                }

                if self._analysis_params:
                    for key in ["group", "day", "subject_id"]:
                        if key in self._analysis_params:
                            metadata[key] = self._analysis_params[key]

                analysis_result = analysis_service.run_full_analysis_as_dto(
                    trajectory_df=df,
                    pixelcm_x=pixelcm_x,
                    pixelcm_y=pixelcm_y,
                    video_height_px=video_height,
                    arena_polygon_px=arena_polygon_tuples,
                    rois=rois,
                    fps=fps,
                    metadata=metadata,
                    roi_colors=roi_colors,
                    freezing_vel_threshold=params["freezing_vel_threshold"],
                    freezing_min_duration=params["freezing_min_duration"],
                    smoothing_window_length=params["smoothing_window_length"],
                    smoothing_polyorder=params["smoothing_polyorder"],
                    behavioral_config=params["behavioral_config"],
                    video_path=str(video_path),
                )

                # Generate Reports
                ctx = ReporterContext.from_analysis(analysis_result)

                excel_path = output_dir / f"4_RelatorioSumario_{self._experiment_id}.xlsx"
                ExcelReporter(ctx).export_summary(str(excel_path))

                word_path = output_dir / f"5_RelatorioIndividual_{self._experiment_id}.docx"
                WordReporter(ctx).export_individual_report(str(word_path))

                log.info(
                    "live_camera_service.reports_generated",
                    excel=str(excel_path),
                    word=str(word_path),
                )

                # Register outputs in project if active
                if self.project_manager.project_path:
                    self.project_manager.register_processing_outputs(
                        video_path=str(video_path),
                        results_dir=str(output_dir),
                        trajectory_path=str(trajectory_file),
                        summary_excel=str(excel_path),
                        report_path=str(word_path),
                        experiment_id=self._experiment_id,
                        group=self._analysis_params.get("group"),
                        day=self._analysis_params.get("day"),
                        subject_id=self._analysis_params.get("subject_id"),
                    )

                    if self.event_bus:
                        from zebtrack.ui import payloads
                        from zebtrack.ui.event_bus_v2 import Event, UIEvents

                        self.event_bus.publish(
                            Event(
                                type=UIEvents.UI_REFRESH_PROJECT_VIEWS,
                                data=payloads.ProjectViewsRefreshRequestedPayload(
                                    reason="Live analysis complete"
                                ),
                            )
                        )

                # Finalize
                total_frames = df["frame"].nunique()
                total_detections = len(df)
                unique_tracks = df["track_id"].nunique() if "track_id" in df.columns else 0

                if self.root:
                    stats = {
                        "frames": total_frames,
                        "detections": total_detections,
                        "tracks": unique_tracks,
                    }
                    self.root.after(0, self._show_completion_message, output_dir, True, stats, None)

            # except Exception justified: recording subsystem boundary — heterogeneous I/O
            except Exception as e:
                log.error("live_camera_service.post_analysis_error", error=str(e), exc_info=True)
                if self.root:
                    self.root.after(
                        0, self._show_completion_message, output_dir, False, None, "error"
                    )

        # Start background thread for post-analysis
        analysis_thread = threading.Thread(
            target=_run_post_analysis,
            name="PostAnalysisThread",
            daemon=True,
        )
        analysis_thread.start()
        log.info("live_camera_service.post_analysis_thread_started")

    def _show_completion_message(
        self,
        output_dir: Path,
        analysis_success: bool = True,
        stats: dict | None = None,
        reason: str | None = None,
    ) -> None:
        """Show completion message with analysis results."""
        if not self.event_bus:
            return

        from zebtrack.ui.event_bus_v2 import Event, UIEvents
        from zebtrack.ui.payloads import MessagePayload

        if analysis_success and stats:
            message = (
                f"✅ Análise de câmera concluída com sucesso!\n\n"
                f"📊 Estatísticas:\n"
                f"  • Frames processados: {stats['frames']}\n"
                f"  • Detecções totais: {stats['detections']}\n"
                f"  • Trilhas únicas: {stats['tracks']}\n\n"
                f"📁 Dados salvos em:\n{output_dir}\n\n"
                f"💡 Arquivos gerados:\n"
                f"  • *_trajectory.parquet (trajetória)\n"
                f"  • *_zones.parquet (zonas)\n"
                f"  • *.mp4/.avi (vídeo gravado)"
            )
            title = "Análise Concluída"
        elif reason == "no_detections":
            message = (
                f"⚠️ Gravação concluída, mas nenhuma detecção foi encontrada.\n\n"
                f"Possíveis causas:\n"
                f"  • Nenhum objeto detectável no campo de visão\n"
                f"  • Arena muito restritiva\n"
                f"  • Limiar de confiança muito alto\n\n"
                f"📁 Dados salvos em:\n{output_dir}"
            )
            title = "Análise Concluída - Sem Detecções"
        else:
            message = (
                f"⚠️ Gravação concluída, mas a análise automática falhou.\n\n"
                f"📁 Dados brutos salvos em:\n{output_dir}\n\n"
                f"Você pode analisar manualmente pela interface."
            )
            title = "Gravação Concluída"

        self.event_bus.publish(
            Event(
                type=UIEvents.UI_SHOW_INFO,
                data=MessagePayload(title=title, message=message),
            ),
        )

    def _start_recording_after_arena(self) -> None:
        """Start recorder and timer AFTER arena has been defined.

        Ensures we only record animal detections, not the aquarium detection phase.
        """
        from zebtrack.core.detection import ZoneData
        from zebtrack.core.project.zone_manager import MultiAquariumZoneData

        zone_data = self.project_manager.get_zone_data() if self.project_manager else ZoneData()

        is_multi_aquarium = isinstance(zone_data, MultiAquariumZoneData)

        if self.is_capturing_for_video and self.recorder:
            try:
                if isinstance(zone_data, MultiAquariumZoneData):
                    if len(zone_data.aquariums) <= 2:
                        zones_by_aquarium = {
                            aq_data.id: aq_data.to_zone_data() for aq_data in zone_data.aquariums
                        }

                        recorder_started = self.recorder.start_recording_multi_aquarium(
                            output_folder=str(self.current_output_dir),
                            width=self.camera.actual_width if self.camera else 640,
                            height=self.camera.actual_height if self.camera else 480,
                            zones_by_aquarium=zones_by_aquarium,
                            base_name=f"{self._experiment_id}",
                        )

                        log.info(
                            "live_camera_service.recorder_started_multi_aquarium",
                            aquarium_count=len(zones_by_aquarium),
                        )
                    elif len(zone_data.aquariums) > 2:
                        log.error(
                            "live_camera_service.multi_aquarium_limit_exceeded",
                            count=len(zone_data.aquariums),
                            max=2,
                        )
                        return
                else:
                    recorder_started = self.recorder.start_recording(
                        output_folder=str(self.current_output_dir),
                        frame_width=self.camera.actual_width if self.camera else 640,
                        frame_height=self.camera.actual_height if self.camera else 480,
                        zones=zone_data,
                        is_video_file=False,
                        base_name=f"{self._experiment_id}",
                    )

                if not recorder_started:
                    log.error("live_camera_service.recorder_start_failed_after_arena")
                    return

                log.info(
                    "live_camera_service.recorder_started_after_arena",
                    output_dir=str(self.current_output_dir),
                    multi_aquarium=is_multi_aquarium,
                )

            # except Exception justified: recording subsystem boundary — heterogeneous I/O
            except Exception as e:
                log.error(
                    "live_camera_service.recorder_init_error_after_arena",
                    error=str(e),
                    exc_info=True,
                )
                return

        # Start session timer NOW (after arena defined)
        if self.current_output_dir and self._session_duration_s > 0:
            self._setup_session_timer(self._session_duration_s, self.current_output_dir)
            log.info(
                "live_camera_service.timer_started_after_arena",
                duration_s=self._session_duration_s,
            )

            if self.preview_window:
                self.preview_window.start_timer()

    def _define_arena_from_detections(self) -> None:
        """Define arena based on collected aquarium detections or fallback to default.

        Called after aquarium detection phase completes (30 frames or manual stop).
        """
        from zebtrack.core.detection import ZoneData

        w = self._actual_width
        h = self._actual_height

        if self._detected_aquarium_bboxes:
            bboxes_array = np.array(self._detected_aquarium_bboxes)
            x1 = int(np.median(bboxes_array[:, 0]))
            y1 = int(np.median(bboxes_array[:, 1]))
            x2 = int(np.median(bboxes_array[:, 2]))
            y2 = int(np.median(bboxes_array[:, 3]))

            arena_polygon = [
                [x1, y1],
                [x2, y1],
                [x2, y2],
                [x1, y2],
            ]

            log.info(
                "live_camera_service.arena_from_aquarium_detection",
                num_detections=len(self._detected_aquarium_bboxes),
                bbox=(x1, y1, x2, y2),
            )
        else:
            area_ratio = 3.0
            side = math.sqrt((w * h) / area_ratio)
            cx, cy = w / 2, h / 2
            half = side / 2

            arena_polygon = [
                [int(cx - half), int(cy - half)],
                [int(cx + half), int(cy - half)],
                [int(cx + half), int(cy + half)],
                [int(cx - half), int(cy + half)],
            ]

            log.info(
                "live_camera_service.arena_fallback_2x",
                width=w,
                height=h,
                side=side,
                reason="no_aquarium_detected",
            )

        zone_data = ZoneData(polygon=arena_polygon)

        # Calculate pixel-to-cm ratio if dimensions provided
        if self._analysis_params:
            width_cm = self._analysis_params.get("aquarium_width_cm", 0)
            height_cm = self._analysis_params.get("aquarium_height_cm", 0)

            if width_cm > 0 and height_cm > 0:
                pts = np.array(arena_polygon)
                min_x, min_y = np.min(pts, axis=0)
                max_x, max_y = np.max(pts, axis=0)
                width_px = max_x - min_x
                height_px = max_y - min_y

                if width_px > 0 and height_px > 0:
                    pixelcm_x = width_px / width_cm
                    pixelcm_y = height_px / height_cm

                    calib = self.project_manager.project_data.setdefault("calibration", {})
                    calib["pixelcm_x"] = pixelcm_x
                    calib["pixelcm_y"] = pixelcm_y
                    calib["aquarium_width_cm"] = width_cm
                    calib["aquarium_height_cm"] = height_cm

                    log.info(
                        "live_camera_service.calibration_calculated",
                        pixelcm_x=f"{pixelcm_x:.2f}",
                        pixelcm_y=f"{pixelcm_y:.2f}",
                        width_cm=width_cm,
                        height_cm=height_cm,
                    )

        should_persist = bool(self.project_manager.project_path)
        self.project_manager.save_zone_data(zone_data, video_path=None, persist=should_persist)

        if self.camera:
            self.detector_service.configure_zones(
                zone_data=zone_data,
                width=self.camera.actual_width,
                height=self.camera.actual_height,
            )

        if self.detector_service and self.detector_service.detector:
            self.detector_service.detector.set_aquarium_region_defined(True)

            use_single_subject = self._animals_per_aquarium == 1
            self.detector_service.detector.set_single_subject_mode(use_single_subject)

            log.info(
                "live_camera_service.detector_switched_to_animals",
                aquarium_defined=True,
                single_subject_mode=use_single_subject,
                animals_per_aquarium=self._animals_per_aquarium,
            )

        self._arena_defined_event.set()
        self._aquarium_detection_phase = False

    def _run_multi_aquarium_detection(
        self, frame: np.ndarray, frame_number: int, zone_data: Any
    ) -> list:
        """Run detection for multi-aquarium setup using partitioned processing.

        Creates (or reuses) a ``MultiAquariumDetector`` that shares the same
        plugin, zone_scaler, and post_processor from the existing
        ``SingleDetector`` held by ``detector_service``.

        Args:
            frame: Full camera frame
            frame_number: Current frame number
            zone_data: MultiAquariumZoneData with per-aquarium zones

        Returns:
            List of detections with adjusted track IDs (aquarium_id * 1000 + local_id)
        """
        import time

        detector = self.detector_service.detector
        if not detector:
            return []

        try:
            # Lazily create MultiAquariumDetector sharing the same plugin
            if self._multi_aq_detector is None:
                from zebtrack.core.detection.multi_aquarium_detector import (
                    MultiAquariumDetector,
                )

                self._multi_aq_detector = MultiAquariumDetector(
                    plugin=detector.plugin,
                    zone_scaler=detector.zone_scaler,
                    post_processor=detector.post_processor,
                    base_width=detector.base_width,
                    base_height=detector.base_height,
                    settings_obj=detector.settings,
                )
                if hasattr(zone_data, "aquariums") and zone_data.aquariums:
                    h, w = frame.shape[:2]
                    self._multi_aq_detector.set_multi_aquarium_zones(
                        zone_data.aquariums,
                        w,
                        h,
                    )

            all_detections = self._multi_aq_detector.detect_partitioned_optimized(
                frame=frame,
            )

            # Record detections per aquarium
            if self.recorder and self.recorder.start_time:
                timestamp = time.time() - self.recorder.start_time

                if hasattr(self.recorder, "write_partitioned_detection_data"):
                    self.recorder.write_partitioned_detection_data(
                        timestamp=timestamp,
                        frame=frame_number,
                        aquarium_detections=all_detections,
                    )
                else:
                    flat_detections = []
                    for _aq_id, dets in all_detections.items():
                        flat_detections.extend(dets)

                    if flat_detections:
                        self.recorder.write_detection_data(timestamp, frame_number, flat_detections)

                log.info(
                    "live_camera_service.multi_aquarium_detection_written",
                    frame_number=frame_number,
                    aquariums=len(all_detections),
                    total_detections=sum(len(dets) for dets in all_detections.values()),
                )

            # Flatten detections for preview overlay
            flat_detections = []
            for _aq_id, dets in all_detections.items():
                flat_detections.extend(dets)

            return flat_detections

        # except Exception justified: cv2 frame processing — poorly-typed errors
        except Exception as e:
            log.error(
                "live_camera_service.multi_aquarium_detection_failed",
                error=str(e),
                exc_info=True,
            )
            detections, _ = detector.detect(frame, "live")
            return detections
