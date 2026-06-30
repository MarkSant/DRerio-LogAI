"""Frame Processing Pipeline — capture, processing, video-recording threads.

Extracted from LiveCameraService (Phase 2.2 decomposition).
Provides the ``FrameProcessingMixin`` mixed into ``LiveCameraService``.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np
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


class FrameProcessingMixin:
    """Mixin providing frame capture, processing, and recording threads.

    Methods:
        _start_threads, _capture_loop, _video_recording_loop,
        _processing_loop, _clear_queues, _adjust_fps_dynamically
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
    _lock: Any
    frame_queue: queue.Queue[Any]
    video_queue: queue.Queue[Any]
    exit_event: threading.Event
    capture_thread: threading.Thread | None
    processing_thread: threading.Thread | None
    video_recording_thread: threading.Thread | None
    analysis_interval_frames: int
    display_interval_frames: int
    _video_frames_written: int
    _live_detected_frames: int
    _analysis_lag_frames: int
    _last_analyzed_frame: int
    _last_captured_frame: int
    _analysis_lag_warning_threshold: int
    _dropped_frames_processing: int
    _dropped_frames_video: int
    _last_valid_frame_time: float | None
    _camera_disconnected: bool
    _preview_window_destroyed: bool
    _use_external_preview: bool
    _aquarium_detection_phase: bool
    _aquarium_detection_frames: int
    _aquarium_detection_max_frames: int
    _detected_aquarium_bboxes: list
    _analysis_params: dict
    _actual_fps: float
    _actual_height: int
    _actual_width: int
    _animals_per_aquarium: int
    _target_fps: float
    _current_fps: float
    _processing_times: list[float]
    _frame_skip_count: int
    _fps_adjustment_interval: int
    _multi_aq_detector: MultiAquariumDetector | None
    _experiment_id: str
    # Per-zone Arduino command state (lazily built once per live session).
    _arduino_zone_enabled: bool
    _arduino_evaluator: Any
    _arduino_mapper: Any
    _arduino_session_end_tokens: list[int]

    # Properties from facade
    camera: Camera | None
    preview_window: LivePreviewWindow | None
    is_capturing_for_video: bool

    # Methods from other mixins
    def _on_session_active(self) -> None: ...
    def _publish_analysis_lag_status(self, lag_seconds: float) -> None: ...
    def _publish_video_drop_status(self) -> None: ...

    def _post_preview_status(self, message: str, color: str = "white") -> None:
        """Schedule a preview-window status update on the Tk main thread.

        ``LivePreviewWindow.update_status_text`` writes Tk widget
        properties, so it must run on the thread that owns the widget
        (CLAUDE.md: all UI updates from worker threads must use
        ``root.after(0, ...)``). This helper bounces the call through
        ``root.after`` when ``self.root`` is available, and falls back
        to a direct call when no Tk root is present (tests / headless).
        """
        preview = getattr(self, "preview_window", None)
        if preview is None:
            return
        root = getattr(self, "root", None)
        if root is not None and hasattr(root, "after"):
            try:
                root.after(0, preview.update_status_text, message, color)
                return
            # except Exception justified: ``root.after`` may be unavailable
            # during shutdown (TclError); fall through to a direct call so
            # we still log the intent.
            except Exception:  # pragma: no cover - defensive
                log.debug("live_camera_service.post_preview_status.after_failed")
        preview.update_status_text(message, color)

    def _check_camera_disconnect(self) -> None: ...
    def _on_camera_reconnected(self) -> None: ...
    def _define_arena_from_detections(self) -> None:
        """Delegate to the next mixin implementation in the MRO."""
        super_method = getattr(super(), "_define_arena_from_detections", None)
        if super_method is None:
            raise NotImplementedError("_define_arena_from_detections is not implemented")
        super_method()

    def _start_recording_after_arena(self) -> None:
        """Delegate to the next mixin implementation in the MRO."""
        super_method = getattr(super(), "_start_recording_after_arena", None)
        if super_method is None:
            raise NotImplementedError("_start_recording_after_arena is not implemented")
        super_method()

    def _run_multi_aquarium_detection(
        self, frame: np.ndarray, frame_number: int, zone_data: Any
    ) -> list:
        """Delegate to the next mixin implementation in the MRO."""
        super_method = getattr(super(), "_run_multi_aquarium_detection", None)
        if super_method is None:
            raise NotImplementedError("_run_multi_aquarium_detection is not implemented")
        return super_method(frame, frame_number, zone_data)

    def get_last_detections(self) -> list: ...  # type: ignore[empty-body]
    def set_last_detections(self, detections: list) -> None: ...

    def _start_threads(self) -> bool:
        """Start capture, processing, and video recording threads."""
        try:
            # Clear exit event
            self.exit_event.clear()
            self._video_frames_written = 0  # Reset counter

            # Start capture thread
            self.capture_thread = threading.Thread(
                target=self._capture_loop,
                name="LiveCameraCaptureThread",
                daemon=True,
            )
            self.capture_thread.start()
            log.info("live_camera_service.capture_thread_started")

            # Start processing thread (detection + display)
            self.processing_thread = threading.Thread(
                target=self._processing_loop,
                name="LiveCameraProcessingThread",
                daemon=True,
            )
            self.processing_thread.start()
            log.info("live_camera_service.processing_thread_started")

            # Start dedicated video recording thread
            self.video_recording_thread = threading.Thread(
                target=self._video_recording_loop,
                name="LiveCameraVideoRecordingThread",
                daemon=True,
            )
            self.video_recording_thread.start()
            log.info("live_camera_service.video_recording_thread_started")

            return True

        # except Exception justified: camera hardware I/O — heterogeneous failures
        except Exception as e:
            log.error("live_camera_service.thread_start_failed", error=str(e), exc_info=True)
            return False

    def _capture_loop(self) -> None:
        """Thread loop for capturing frames from camera."""
        log.info("live_camera_service.capture_loop_started")

        if self.camera:
            log.info(
                "live_camera_service.capture_loop_using_camera",
                camera_index=self.camera._camera_index,
            )

        frame_count = 0

        while not self.exit_event.is_set():
            if not self.camera:
                log.warning("live_camera_service.camera_not_initialized")
                time.sleep(0.1)
                continue

            try:
                ret, frame = self.camera.get_frame()
                if not ret or frame is None:
                    log.warning("live_camera_service.frame_capture_failed", frame_count=frame_count)
                    self._check_camera_disconnect()
                    time.sleep(0.1)
                    continue

                # Update last valid frame timestamp
                current_time = time.time()
                self._last_valid_frame_time = current_time

                # If we were disconnected, mark reconnection
                if self._camera_disconnected:
                    self._on_camera_reconnected()

                frame_count += 1
                self._last_captured_frame = frame_count

                # Create single copy of frame to share between queues
                frame_copy = frame.copy()

                # PRIORITY 1: VIDEO RECORDING - NEVER DROP
                if self.is_capturing_for_video:
                    try:
                        self.video_queue.put(frame_copy, timeout=0.5)
                    except queue.Full:
                        self._dropped_frames_video += 1
                        log.error(
                            "live_camera_service.video_frame_dropped_critical",
                            frame_count=frame_count,
                            queue_size=self.video_queue.qsize(),
                            note="video_recording_may_have_gaps",
                        )
                        # Phase 5 / B2: surface video drops to the UI so
                        # the user notices a slow disk before the recorder
                        # accumulates a noticeable gap. Throttled so a
                        # bursty queue.Full does not spam the status bar.
                        if self._dropped_frames_video % 10 == 1:
                            self._publish_video_drop_status()

                # PRIORITY 2: ANALYSIS FRAMES
                is_analysis_frame = (frame_count % self.analysis_interval_frames) == 0

                if is_analysis_frame:
                    try:
                        self.frame_queue.put((frame_count, frame_copy), timeout=0.5)
                    except queue.Full:
                        self._dropped_frames_processing += 1
                        log.warning(
                            "live_camera_service.analysis_frame_dropped",
                            frame_count=frame_count,
                            queue_backlog=self.frame_queue.qsize(),
                        )
                elif not self.frame_queue.full():
                    self.frame_queue.put_nowait((frame_count, frame_copy))

                # Control capture rate
                default_fps = 30.0
                fps = self.settings.video_processing.fps if self.settings else default_fps
                time.sleep(1 / (fps * 1.5))

            # except Exception justified: daemon thread fault-isolation
            except Exception as e:
                log.error("live_camera_service.capture_error", error=str(e), exc_info=True)
                time.sleep(0.5)

        # Log final metrics including dropped frames
        drop_rate_proc = (self._dropped_frames_processing / max(frame_count, 1)) * 100
        drop_rate_vid = (self._dropped_frames_video / max(frame_count, 1)) * 100
        log.info(
            "live_camera_service.capture_loop_finished",
            total_frames=frame_count,
            dropped_frames_processing=self._dropped_frames_processing,
            dropped_frames_video=self._dropped_frames_video,
            drop_rate_processing=f"{drop_rate_proc:.1f}%",
            drop_rate_video=f"{drop_rate_vid:.1f}%",
        )

    def _video_recording_loop(self) -> None:
        """Dedicated thread for video recording.

        Reads from video_queue (separate from frame_queue used by detection).
        Blocks waiting for frames (with timeout for clean exit).
        Writes EVERY frame to the video file independent of detection speed.
        """
        log.info("live_camera_service.video_recording_loop_started")

        while not self.exit_event.is_set():
            if not self.is_capturing_for_video or not self.recorder:
                time.sleep(0.05)
                continue

            try:
                frame = self.video_queue.get(timeout=0.5)

                if self.recorder and self.recorder.is_recording and self.recorder.video_writer:
                    try:
                        self.recorder.write_video_frame(frame)
                        self._video_frames_written += 1

                        if self._video_frames_written % 100 == 0:
                            log.debug(
                                "live_camera_service.video_frames_written",
                                count=self._video_frames_written,
                                queue_size=self.video_queue.qsize(),
                            )
                    except OSError as e:
                        log.warning(
                            "live_camera_service.video_write_error",
                            error=str(e),
                            frames_written=self._video_frames_written,
                        )

            except queue.Empty:
                continue
            # except Exception justified: daemon thread fault-isolation
            except Exception as e:
                log.error(
                    "live_camera_service.video_recording_error",
                    error=str(e),
                    exc_info=True,
                )
                time.sleep(0.1)

        log.info(
            "live_camera_service.video_recording_loop_finished",
            total_frames_written=self._video_frames_written,
        )

    def _processing_loop(self) -> None:  # noqa: C901
        """Thread loop for processing frames with detection."""
        log.info("live_camera_service.processing_loop_started")
        processed_count = 0
        first_frame_active = False
        frames_received = 0
        last_lag_update_time = 0.0

        # Per-zone Arduino command loop — built once for this session (no-op
        # unless the project opted into Arduino and defined bindings).
        self._reset_arduino_zone_state()

        while not self.exit_event.is_set():
            try:
                frame_number, frame = self.frame_queue.get(timeout=1)
            except queue.Empty:
                continue

            frames_received += 1
            self._last_analyzed_frame = frame_number

            # Calculate and report analysis lag
            self._analysis_lag_frames = self._last_captured_frame - frame_number
            current_time = time.time()

            if self._analysis_lag_frames > self._analysis_lag_warning_threshold:
                if current_time - last_lag_update_time > 2.0:
                    last_lag_update_time = current_time
                    lag_seconds = self._analysis_lag_frames / 30.0
                    self._publish_analysis_lag_status(lag_seconds)

            try:
                # Trigger session timer on first frame
                if not first_frame_active:
                    first_frame_active = True
                    if self.root:
                        self.root.after(0, self._on_session_active)

                # PHASE 1: Aquarium Detection (if needed)
                if self._aquarium_detection_phase:
                    # Exibe o feed da câmera no canvas integrado JÁ durante a
                    # fase de detecção de aquário. Sem isto, o fluxo de vídeo
                    # único ao vivo (sem projeto) deixava a aba "Análise" em
                    # branco até a arena ser definida — ao contrário dos
                    # projetos, que já têm arena e mostram o feed desde o 1º
                    # frame. Emite o frame cru (sem overlay; arena ainda não
                    # existe) e stats parciais, throttled pelo display_interval.
                    if (
                        not self._use_external_preview
                        and self.event_bus
                        and not self.exit_event.is_set()
                        and (frames_received % max(self.display_interval_frames, 1)) == 0
                    ):
                        from zebtrack.ui import payloads
                        from zebtrack.ui.event_bus_v2 import Event, UIEvents

                        self.event_bus.publish(
                            Event(
                                type=UIEvents.UI_UPDATE_LIVE_FRAME,
                                data=payloads.UIUpdateLiveFramePayload(
                                    frame=frame,
                                    detections=[],
                                    fps=self._actual_fps,
                                ),
                            ),
                        )
                        self.event_bus.publish(
                            Event(
                                type=UIEvents.UI_UPDATE_PROCESSING_STATS,
                                data=payloads.ProcessingStatsWrapperPayload(
                                    stats={
                                        "processed_frames": int(frame_number),
                                        "detected_frames": int(self._live_detected_frames),
                                    }
                                ),
                                source="frame_processing_pipeline.aquarium_detection",
                            ),
                        )

                    # Warmup period (skip first 30 frames ~1.5s)
                    if frame_number < 30:
                        if self.preview_window and frame_number % 5 == 0:
                            # Tk widgets must be touched from the main thread —
                            # marshal status updates through root.after(0,...)
                            # instead of calling update_status_text directly
                            # from this worker (Phase 5 / M3).
                            self._post_preview_status(
                                f"⏳ Estabilizando imagem... ({frame_number}/30)",
                                color="orange",
                            )
                        continue

                    # Process only every 5th frame
                    if frame_number % 5 != 0:
                        continue

                    # Update preview status (Phase 5 / M3 — main-thread bounce)
                    if self.preview_window and frame_number % 5 == 0:
                        status_msg = (
                            f"🔍 Detectando aquário... "
                            f"({self._aquarium_detection_frames}/{self._aquarium_detection_max_frames})"
                        )
                        self._post_preview_status(status_msg, color="yellow")

                    # Run detection to find aquarium (class_id=0)
                    detector = self.detector_service.detector
                    if detector:
                        detections, _ = detector.detect(frame, "live", conf_threshold=0.05)

                    # Collect aquarium bboxes
                    if detector:
                        target_class_id = detector.aquarium_class_id
                    else:
                        target_class_id = 0

                    h, w = frame.shape[:2]
                    frame_area = w * h
                    min_ratio = 0.10
                    if hasattr(self.settings, "detection_zones"):
                        min_ratio = self.settings.detection_zones.min_aquarium_area_ratio

                    min_aquarium_area = frame_area * min_ratio

                    detection_found_in_frame = False
                    # Phase 5 / M7: lazily produce ONE shared snapshot per
                    # frame iteration, regardless of how many detections
                    # we publish events for. The previous code copied the
                    # frame for every accepted/rejected detection, which
                    # on multi-aquarium scenes meant N copies per frame.
                    # Subscribers must treat ``frame_image`` as read-only.
                    detection_frame_snapshot: np.ndarray | None = None

                    for det in detections:
                        if len(det) >= 7:
                            x1, y1, x2, y2, conf, track_id, class_id = det

                            if class_id == target_class_id:
                                bbox_area = (x2 - x1) * (y2 - y1)
                                if bbox_area >= min_aquarium_area:
                                    self._detected_aquarium_bboxes.append(
                                        (int(x1), int(y1), int(x2), int(y2))
                                    )
                                    detection_found_in_frame = True
                                    if (
                                        len(self._detected_aquarium_bboxes) == 1
                                        or len(self._detected_aquarium_bboxes) % 5 == 0
                                    ):
                                        log.info(
                                            "live_camera_service.aquarium_detected",
                                            frame=frame_number,
                                            total_collected=len(self._detected_aquarium_bboxes),
                                            area_ratio=f"{bbox_area / frame_area:.2f}",
                                        )

                                    # Publish progress event
                                    if self.event_bus:
                                        from zebtrack.ui import payloads
                                        from zebtrack.ui.event_bus_v2 import Event, UIEvents

                                        if detection_frame_snapshot is None:
                                            detection_frame_snapshot = frame.copy()
                                        self.event_bus.publish(
                                            Event(
                                                type=UIEvents.AQUARIUM_DETECTION_PROGRESS,
                                                data=payloads.AquariumDetectionProgressPayload(
                                                    frame_number=self._aquarium_detection_frames,
                                                    max_frames=self._aquarium_detection_max_frames,
                                                    frame_image=detection_frame_snapshot,
                                                    detected_bbox=(
                                                        int(x1),
                                                        int(y1),
                                                        int(x2),
                                                        int(y2),
                                                    ),
                                                    is_valid=True,
                                                    experiment_id=self._analysis_params.get(
                                                        "experiment_id", "unknown"
                                                    ),
                                                    valid_count=len(self._detected_aquarium_bboxes),
                                                ),
                                            ),
                                        )
                                else:
                                    log.info(
                                        "live_camera_service.aquarium_rejected_area",
                                        frame=frame_number,
                                        area_ratio=f"{bbox_area / frame_area:.2f}",
                                        min_ratio=min_ratio,
                                        bbox=(int(x1), int(y1), int(x2), int(y2)),
                                    )

                                    if self.event_bus and frame_number % 5 == 0:
                                        from zebtrack.ui import payloads
                                        from zebtrack.ui.event_bus_v2 import Event, UIEvents

                                        if detection_frame_snapshot is None:
                                            detection_frame_snapshot = frame.copy()
                                        self.event_bus.publish(
                                            Event(
                                                type=UIEvents.AQUARIUM_DETECTION_PROGRESS,
                                                data=payloads.AquariumDetectionProgressPayload(
                                                    frame_number=self._aquarium_detection_frames,
                                                    max_frames=self._aquarium_detection_max_frames,
                                                    frame_image=detection_frame_snapshot,
                                                    detected_bbox=(
                                                        int(x1),
                                                        int(y1),
                                                        int(x2),
                                                        int(y2),
                                                    ),
                                                    is_valid=False,
                                                    experiment_id=self._analysis_params.get(
                                                        "experiment_id", "unknown"
                                                    ),
                                                    valid_count=len(self._detected_aquarium_bboxes),
                                                ),
                                            ),
                                        )

                    if not detection_found_in_frame:
                        if frame_number % 5 == 0:
                            log.info(
                                "live_camera_service.no_valid_aquarium_in_frame",
                                frame=frame_number,
                                num_raw_detections=len(detections),
                                target_class_id=target_class_id,
                            )

                    self._aquarium_detection_frames += 1

                    # Check if detection phase is complete
                    if (
                        self._aquarium_detection_frames >= 10
                        or len(self._detected_aquarium_bboxes) >= 4
                    ):
                        log.info(
                            "live_camera_service.aquarium_detection_complete",
                            frames_analyzed=self._aquarium_detection_frames,
                            detections_collected=len(self._detected_aquarium_bboxes),
                        )

                        self._define_arena_from_detections()
                        self._start_recording_after_arena()

                        # Tk widget mutation must run on the main thread
                        # (Phase 5 / M3).
                        if self.preview_window:
                            self._post_preview_status("● Gravando", color="red")

                    continue

                # PHASE 2: Normal Processing (after arena is defined)
                should_analyze = (frames_received % self.analysis_interval_frames) == 0
                should_display = (frames_received % self.display_interval_frames) == 0

                detections = []

                if should_analyze:
                    frame_start_time = time.time()
                    processed_count += 1

                    # Apply calibration if available
                    calib_data = self.project_manager.project_data.get("calibration", {})
                    h_matrix = calib_data.get("homography_matrix")
                    target_dims = calib_data.get("target_dims_px")

                    if h_matrix and target_dims:
                        h_matrix = np.array(h_matrix)
                        frame = cv2.warpPerspective(frame, h_matrix, tuple(target_dims))

                    # Run detection
                    detector = self.detector_service.detector
                    if detector:
                        zone_data = self.project_manager.get_zone_data()
                        is_multi_aquarium = hasattr(zone_data, "aquariums") and zone_data.aquariums

                        log.debug(
                            "live_camera_service.detection_attempt",
                            frame_number=frame_number,
                            is_multi_aquarium=is_multi_aquarium,
                            has_detector=detector is not None,
                            conf_threshold=getattr(detector.plugin, "conf_threshold", None)
                            if hasattr(detector, "plugin")
                            else None,
                        )

                        if is_multi_aquarium:
                            detections = self._run_multi_aquarium_detection(
                                frame, frame_number, zone_data
                            )
                        else:
                            detections, _command = detector.detect(
                                frame, "live", conf_threshold=0.05
                            )

                    # Adjust FPS dynamically based on processing time
                    frame_processing_time = time.time() - frame_start_time
                    should_continue_processing = self._adjust_fps_dynamically(
                        frame_number, frame_processing_time
                    )

                    if not should_continue_processing:
                        log.debug(
                            "live_camera_service.fps_skip_triggered",
                            frame_number=frame_number,
                            processing_time=frame_processing_time,
                        )

                    # Cache detections for persistent overlay
                    self.set_last_detections(detections)

                    log.info(
                        "live_camera_service.detection_result",
                        frame_number=frame_number,
                        num_detections=len(detections),
                        has_recorder=self.recorder is not None,
                        recorder_start_time=self.recorder.start_time if self.recorder else None,
                    )

                    # Record detections
                    if self.recorder and self.recorder.start_time:
                        if detections:
                            timestamp = time.time() - self.recorder.start_time
                            self.recorder.write_detection_data(timestamp, frame_number, detections)
                            log.info(
                                "live_camera_service.detection_written",
                                frame_number=frame_number,
                                num_detections=len(detections),
                                timestamp=timestamp,
                            )
                        else:
                            log.info(
                                "live_camera_service.detection_skipped_empty",
                                frame_number=frame_number,
                            )
                    else:
                        log.warning(
                            "live_camera_service.detection_skipped_no_recorder",
                            frame_number=frame_number,
                            has_recorder=self.recorder is not None,
                            recorder_start_time=self.recorder.start_time if self.recorder else None,
                        )

                    # Per-zone Arduino commands: edge-triggered enter/exit tokens
                    # while recording. Fire-and-forget (queued), so it never
                    # stalls this loop. No-op unless Arduino + bindings are set.
                    if self.recorder and self.recorder.start_time:
                        self._dispatch_arduino_zone_commands(detections)
                else:
                    detections = self.get_last_detections()

                # Draw overlay when displaying.
                # IMPORTANT: draw ZONES ONLY here (empty detections list). The
                # detection bounding boxes are drawn exactly once by the frame
                # consumer — integrated canvas (VideoFrameManager.update_video_frame
                # → _draw_detection_overlay_on_frame) or the external
                # LivePreviewWindow.update_frame. Passing ``detections`` here would
                # burn a SECOND box onto the frame (different color/label), so each
                # animal showed two overlapping bboxes. This mirrors the pre-recorded
                # path (processing_worker.py calls draw_overlay(frame, [])).
                detector = self.detector_service.detector
                if detector and should_display:
                    detector.draw_overlay(frame, [])
                    log.debug(
                        "live_camera_service.overlay_drawn",
                        frame_number=frame_number,
                        num_boxes=len(detections),
                        zones_only=True,
                        is_cached=not should_analyze,
                    )

                # Update preview window if exists
                if self.preview_window and should_display:
                    if self.camera:
                        camera_idx = self.camera._camera_index
                        cv2.putText(
                            frame,
                            f"CAMERA INDEX: {camera_idx}",
                            (10, 50),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            2.0,
                            (0, 255, 0),
                            4,
                            cv2.LINE_AA,
                        )

                    if self.root and not self._preview_window_destroyed:
                        self.root.after(
                            0,
                            self.preview_window.update_frame,
                            frame,
                            detections,
                            self._video_frames_written,
                        )

                # Integrated Canvas: Emit event for main UI when NOT using external preview
                if (
                    should_display
                    and not self._use_external_preview
                    and self.event_bus
                    and not self.exit_event.is_set()
                ):
                    from zebtrack.ui.event_bus_v2 import Event, UIEvents

                    log.debug(
                        "live_camera_service.emitting_ui_update_frame",
                        frame_number=frame_number,
                        has_detections=len(detections) if detections else 0,
                    )

                    from zebtrack.ui import payloads

                    self.event_bus.publish(
                        Event(
                            type=UIEvents.UI_UPDATE_LIVE_FRAME,
                            data=payloads.UIUpdateLiveFramePayload(
                                frame=frame,
                                detections=detections,
                                fps=self._actual_fps,
                            ),
                        ),
                    )

                    # Audit Erro 7b follow-up (2026-05-25): publish progress
                    # stats so the "Análise de Vídeo" tab labels (Total/
                    # Processados/Detectados/Tempo) reflect the live session
                    # instead of staying at "-". Live recording has no fixed
                    # ``total_frames``, so we publish the running count and
                    # ``start_time`` — the StateSynchronizer formats elapsed
                    # from there. Throttled to display frames (we're already
                    # inside the should_display branch).
                    if detections:
                        self._live_detected_frames += 1
                    live_stats: dict[str, Any] = {
                        "processed_frames": int(frame_number),
                        "detected_frames": int(self._live_detected_frames),
                    }
                    if self.recorder and self.recorder.start_time:
                        live_stats["start_time"] = self.recorder.start_time
                    self.event_bus.publish(
                        Event(
                            type=UIEvents.UI_UPDATE_PROCESSING_STATS,
                            data=payloads.ProcessingStatsWrapperPayload(stats=live_stats),
                            source="frame_processing_pipeline.live_progress",
                        )
                    )
                elif (
                    should_display
                    and not self._use_external_preview
                    and not self.exit_event.is_set()
                ):
                    log.warning(
                        "live_camera_service.no_event_bus",
                        frame_number=frame_number,
                        has_event_bus=self.event_bus is not None,
                    )

                # Explicit frame cleanup to hint garbage collector
                del frame

            # except Exception justified: daemon thread fault-isolation
            except Exception as e:
                log.error("live_camera_service.processing_error", error=str(e), exc_info=True)
                if "frame" in locals():
                    del frame

        # Session ended (timer complete or cancel) — turn everything off on the
        # Arduino so LEDs/relays do not stay latched after recording stops.
        self._arduino_zone_session_end_sweep()

        log.info("live_camera_service.processing_loop_finished", processed=processed_count)

    # ------------------------------------------------------------------
    # Per-zone Arduino command loop
    # ------------------------------------------------------------------
    def _arduino_manager(self) -> Any:
        """Return the shared ArduinoManager (via controller), or None."""
        return getattr(self.controller, "arduino_manager", None)

    def _reset_arduino_zone_state(self) -> None:
        """(Re)build the per-zone Arduino command state for a new session.

        Cheap no-op unless the project enabled Arduino AND defined at least one
        binding. The ROI evaluator is built lazily on the first analyzed frame
        (the detector's scaled ROI polygons are only populated once it has seen
        the actual frame dimensions).
        """
        self._arduino_zone_enabled = False
        self._arduino_evaluator = None
        self._arduino_mapper = None
        self._arduino_session_end_tokens = []

        project_data = getattr(self.project_manager, "project_data", {}) or {}
        if not project_data.get("use_arduino"):
            return

        from zebtrack.core.services.arduino_bindings import ArduinoBindingConfig
        from zebtrack.core.services.arduino_event_mapper import ArduinoEventMapper

        cfg = ArduinoBindingConfig.from_project_data(project_data)
        if cfg.is_empty():
            return

        self._arduino_mapper = ArduinoEventMapper(cfg.bindings)
        self._arduino_session_end_tokens = cfg.session_end_tokens()
        self._arduino_zone_enabled = True
        log.info(
            "live_camera_service.arduino_zone_commands.enabled",
            bindings=len(cfg.bindings),
            rois=cfg.roi_names(),
        )

    def _build_arduino_evaluator(self) -> Any:
        """Lazily build the ROI evaluator from the detector's scaled polygons.

        Returns the evaluator, or None if the detector has no usable ROI
        polygons yet (in which case we retry on the next frame).
        """
        from zebtrack.core.services.arduino_roi_evaluator import ArduinoRoiEvaluator

        detector = self.detector_service.detector
        if detector is None:
            return None
        roi_names = list(getattr(detector, "roi_names", []) or [])
        roi_polygons = list(getattr(detector, "scaled_roi_polygons", []) or [])
        if not roi_names or not roi_polygons:
            return None
        evaluator = ArduinoRoiEvaluator(roi_names, roi_polygons)
        return evaluator if evaluator.has_rois() else None

    def _dispatch_arduino_zone_commands(self, detections: list) -> None:
        """Emit edge-triggered enter/exit tokens for the current frame.

        Computes which ROIs are occupied (any-track), diffs against the previous
        frame via the mapper, and queues the resulting tokens fire-and-forget.
        """
        if not self._arduino_zone_enabled:
            return
        manager = self._arduino_manager()
        if manager is None or not manager.is_connected():
            return

        if self._arduino_evaluator is None:
            self._arduino_evaluator = self._build_arduino_evaluator()
            if self._arduino_evaluator is None:
                return  # detector ROIs not ready yet — try again next frame

        centroids: list[tuple[float, float]] = []
        for det in detections:
            try:
                x1, y1, x2, y2 = det[0], det[1], det[2], det[3]
            except (IndexError, TypeError, ValueError):
                continue
            centroids.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0))

        occupied = self._arduino_evaluator.occupied_rois(centroids)
        for token in self._arduino_mapper.update(occupied):
            manager.enqueue(token)

    def _arduino_zone_session_end_sweep(self) -> None:
        """Queue the 'turn everything off' tokens at session end."""
        if not self._arduino_zone_enabled or not self._arduino_session_end_tokens:
            return
        manager = self._arduino_manager()
        if manager is None or not manager.is_connected():
            return
        for token in self._arduino_session_end_tokens:
            manager.enqueue(token)
        log.info(
            "live_camera_service.arduino_zone_commands.session_end_sweep",
            tokens=self._arduino_session_end_tokens,
        )

    def _clear_queues(self) -> None:
        """Clear all queues."""
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break

        while not self.video_queue.empty():
            try:
                self.video_queue.get_nowait()
            except queue.Empty:
                break

    def _adjust_fps_dynamically(self, frame_number: int, processing_time: float) -> bool:
        """Adjust FPS dynamically based on processing performance.

        Uses exponentially weighted moving average for smoothing.

        Args:
            frame_number: Current frame number
            processing_time: Time taken to process this frame (seconds)

        Returns:
            True if frame should be processed, False if should skip
        """
        self._processing_times.append(processing_time)

        max_samples = 30
        if len(self._processing_times) > max_samples:
            self._processing_times = self._processing_times[-max_samples:]

        if frame_number % self._fps_adjustment_interval == 0 and len(self._processing_times) >= 10:
            avg_processing_time = sum(self._processing_times) / len(self._processing_times)
            self._current_fps = 1.0 / avg_processing_time if avg_processing_time > 0 else 30.0

            if self._current_fps < self._target_fps * 0.7:
                self._frame_skip_count = min(4, self._frame_skip_count + 1)
                log.warning(
                    "live_camera_service.fps_too_low",
                    measured_fps=f"{self._current_fps:.1f}",
                    target_fps=f"{self._target_fps:.1f}",
                    frame_skip=self._frame_skip_count,
                )
            elif self._current_fps > self._target_fps * 1.2 and self._frame_skip_count > 0:
                self._frame_skip_count = max(0, self._frame_skip_count - 1)
                log.info(
                    "live_camera_service.fps_improved",
                    measured_fps=f"{self._current_fps:.1f}",
                    target_fps=f"{self._target_fps:.1f}",
                    frame_skip=self._frame_skip_count,
                )

        if self._frame_skip_count > 0:
            should_process = (frame_number % (self._frame_skip_count + 1)) == 0
            if not should_process:
                log.debug(
                    "live_camera_service.frame_skipped",
                    frame_number=frame_number,
                    skip_pattern=self._frame_skip_count + 1,
                )
            return should_process

        return True
