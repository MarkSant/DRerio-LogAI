"""Frame Processing Pipeline — capture, processing, video-recording threads.

Extracted from LiveCameraService (Phase 2.2 decomposition).
Provides the ``FrameProcessingMixin`` mixed into ``LiveCameraService``.
"""

from __future__ import annotations

import math
import queue
import threading
import time
from typing import TYPE_CHECKING, Any, NamedTuple

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

# Fallback for ``arduino.roi_exit_grace_frames`` when no settings object is
# attached (mixin used standalone, e.g. in focused tests). Mirrors the default
# declared on ``ArduinoSettings``.
DEFAULT_ARDUINO_EXIT_GRACE_FRAMES = 2


class VideoFrameMeta(NamedTuple):
    """Metadados que viajam com o frame até a thread de vídeo.

    Carregam o instante de captura (par perf/wall) e a classificação de cadência
    feitos na thread de CAPTURA, para que a thread de vídeo — que conhece o
    índice real do MP4 — escreva a linha completa do ledger.
    """

    pipeline_frame: int
    t_capture_perf: float | None
    t_capture_wall: float | None
    is_analysis_frame: bool
    queued_for_analysis: bool


def _unpack_video_item(item: Any) -> tuple[Any, VideoFrameMeta | None]:
    """Separa ``(frame, meta)`` de um item da ``video_queue``.

    Tolera o formato legado (o frame cru, sem metadados) usado por testes e
    chamadores antigos: nesse caso não há linha de ledger para produzir.
    """
    if isinstance(item, tuple) and len(item) == 6:
        frame_count, perf, wall, is_analysis, queued, frame = item
        return frame, VideoFrameMeta(
            pipeline_frame=int(frame_count),
            t_capture_perf=perf,
            t_capture_wall=wall,
            is_analysis_frame=bool(is_analysis),
            queued_for_analysis=bool(queued),
        )
    return item, None


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
    _arduino_missed_frames: int
    _arduino_inverted_ack_seen: set[tuple[str, str]]
    # Closed-loop latency logging state (lazily built once per live session).
    _closed_loop_log: Any
    _closed_loop_event_seq: int
    # Ledger de frames (pipeline_frame ↔ video_frame_index ↔ tempo de captura).
    _frame_ledger: Any

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
            # Ledger de frames da sessão: criado ANTES das threads (as duas
            # produzem linhas) e ligado à pasta de saída assim que o recorder
            # abre a gravação.
            self._reset_frame_ledger()

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

    # ------------------------------------------------------------------
    # Ledger de frames (pipeline_frame ↔ video_frame_index ↔ tempo)
    # ------------------------------------------------------------------
    def _reset_frame_ledger(self) -> None:
        """(Re)cria o ledger de frames para uma nova sessão.

        Criado ANTES da pasta de saída existir (a gravação pode só começar após
        a fase de detecção de aquário): as linhas ficam em memória até
        ``_maybe_bind_frame_ledger`` encontrar o ``output_folder`` do recorder.
        """
        from zebtrack.core.recording.frame_ledger import FrameLedger

        previous = getattr(self, "_frame_ledger", None)
        if previous is not None:
            # Sessão anterior encerrada de forma anômala — libera a thread de
            # flush antes de trocar a instância.
            try:
                previous.finalize()
            # except Exception justified: limpeza best-effort de artefato opcional.
            except Exception:  # pragma: no cover - defensivo
                log.warning("frame_ledger.previous_finalize_failed")
        self._frame_ledger = FrameLedger()

    def _maybe_bind_frame_ledger(self) -> None:
        """Liga o ledger à pasta do recorder assim que ela existir (idempotente)."""
        ledger = getattr(self, "_frame_ledger", None)
        if ledger is None or ledger.is_bound:
            return
        recorder = getattr(self, "recorder", None)
        output_folder = getattr(recorder, "output_folder", None)
        if not output_folder:
            return
        base_name = (
            getattr(recorder, "base_name", "")
            or getattr(self, "_current_base_name", "")
            or getattr(self, "_experiment_id", "")
            or "session"
        )
        ledger.bind(output_folder, base_name)
        ledger.set_anchor(
            recorder_start_time=getattr(recorder, "start_time", None),
            fps_nominal=getattr(recorder, "_fps", None) or getattr(self, "_actual_fps", None),
            analysis_interval_frames=getattr(self, "analysis_interval_frames", None),
        )

    def _ledger_record(
        self,
        pipeline_frame: int,
        t_capture_perf: float | None,
        t_capture_wall: float | None,
        outcome: str,
        *,
        video_frame_index: int = -1,
        is_analysis_frame: bool = False,
        queued_for_analysis: bool = False,
    ) -> None:
        """Registra uma linha no ledger (no-op se não houver ledger ativo)."""
        ledger = getattr(self, "_frame_ledger", None)
        if ledger is None:
            return
        ledger.record(
            pipeline_frame,
            t_capture_perf,
            t_capture_wall,
            outcome,
            video_frame_index=video_frame_index,
            is_analysis_frame=is_analysis_frame,
            queued_for_analysis=queued_for_analysis,
        )

    def _ledger_record_meta(
        self,
        meta: VideoFrameMeta | None,
        outcome: str,
        *,
        video_frame_index: int = -1,
    ) -> None:
        """Registra a linha da thread de vídeo a partir dos metadados do frame."""
        if meta is None:
            return  # item legado sem metadados — nada a correlacionar
        self._ledger_record(
            meta.pipeline_frame,
            meta.t_capture_perf,
            meta.t_capture_wall,
            outcome,
            video_frame_index=video_frame_index,
            is_analysis_frame=meta.is_analysis_frame,
            queued_for_analysis=meta.queued_for_analysis,
        )

    def _finalize_frame_ledger(self) -> None:
        """Escreve ``6_FrameLedger_<base>.parquet`` + âncora e encerra o ledger.

        Chamado no fim da sessão, DEPOIS do join das threads produtoras.
        """
        ledger = getattr(self, "_frame_ledger", None)
        if ledger is None:
            return
        self._maybe_bind_frame_ledger()
        try:
            ledger.finalize()
            log.info("live_camera_service.frame_ledger.finalized", rows=ledger.row_count)
        # except Exception justified: o encerramento da sessão nunca pode falhar
        # por causa de um artefato de análise opcional.
        except Exception:
            log.error("live_camera_service.frame_ledger.finalize_error", exc_info=True)
        self._frame_ledger = None

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
                # Monotonic capture instant (FRAME_T0) — rides with the frame
                # through the queue so the closed-loop latency log can measure
                # capture -> LED-ACK end-to-end. Uses perf_counter (not time())
                # so it is immune to wall-clock adjustments.
                capture_perf = time.perf_counter()

                # If we were disconnected, mark reconnection
                if self._camera_disconnected:
                    self._on_camera_reconnected()

                frame_count += 1
                self._last_captured_frame = frame_count

                # Create single copy of frame to share between queues
                frame_copy = frame.copy()

                # ANALYSIS FRAMES.
                # Avaliado ANTES do enfileiramento de vídeo (era o inverso) para
                # que a linha do ledger produzida pela thread de vídeo já carregue
                # ``is_analysis_frame``/``queued_for_analysis``. O conjunto de
                # operações bloqueantes por frame é o mesmo de antes — só a ordem
                # muda — e a fila de vídeo (600 slots ≈ 20 s) absorve a inversão.
                is_analysis_frame = (frame_count % self.analysis_interval_frames) == 0
                queued_for_analysis = False

                if is_analysis_frame:
                    try:
                        self.frame_queue.put((frame_count, frame_copy, capture_perf), timeout=0.5)
                        queued_for_analysis = True
                    except queue.Full:
                        self._dropped_frames_processing += 1
                        log.warning(
                            "live_camera_service.analysis_frame_dropped",
                            frame_count=frame_count,
                            queue_backlog=self.frame_queue.qsize(),
                        )
                elif not self.frame_queue.full():
                    # Enfileiramento OPORTUNISTA: o parquet contém mais do que os
                    # múltiplos de ``analysis_interval_frames``. Mantido (não
                    # perde dado), mas a linha do ledger marca a diferença para
                    # que a análise possa recuperar a cadência determinística.
                    self.frame_queue.put_nowait((frame_count, frame_copy, capture_perf))
                    queued_for_analysis = True

                # PRIORITY 1: VIDEO RECORDING - NEVER DROP
                if self.is_capturing_for_video:
                    try:
                        self.video_queue.put(
                            (
                                frame_count,
                                capture_perf,
                                current_time,
                                is_analysis_frame,
                                queued_for_analysis,
                                frame_copy,
                            ),
                            timeout=0.5,
                        )
                    except queue.Full:
                        self._dropped_frames_video += 1
                        # A thread de CAPTURA é a única que sabe deste descarte —
                        # o frame nunca chega à thread de vídeo. Sem esta linha o
                        # índice do MP4 desliza sem rastro no disco.
                        self._ledger_record(
                            frame_count,
                            capture_perf,
                            current_time,
                            "dropped_queue_full",
                            is_analysis_frame=is_analysis_frame,
                            queued_for_analysis=queued_for_analysis,
                        )
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
                else:
                    # Fora da janela de gravação: o frame existe na linha do
                    # tempo, mas não corresponde a nenhum frame do MP4.
                    self._ledger_record(
                        frame_count,
                        capture_perf,
                        current_time,
                        "not_recording",
                        is_analysis_frame=is_analysis_frame,
                        queued_for_analysis=queued_for_analysis,
                    )

                # Liga o ledger à pasta de saída assim que o recorder abre a
                # sessão (a gravação pode começar depois da detecção de aquário).
                self._maybe_bind_frame_ledger()

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
                item = self.video_queue.get(timeout=0.5)
                frame, meta = _unpack_video_item(item)

                if self.recorder and self.recorder.is_recording and self.recorder.video_writer:
                    try:
                        self.recorder.write_video_frame(frame)
                        # ``video_frame_index`` vem do CONSUMIDOR: é o índice
                        # real dentro do MP4, não a inferência
                        # ``frame_count - drops`` — que é justamente onde o
                        # deslocamento nasce.
                        video_index = self._video_frames_written
                        self._video_frames_written += 1
                        self._ledger_record_meta(meta, "written", video_frame_index=video_index)

                        if self._video_frames_written % 100 == 0:
                            log.debug(
                                "live_camera_service.video_frames_written",
                                count=self._video_frames_written,
                                queue_size=self.video_queue.qsize(),
                            )
                    except OSError as e:
                        # O frame saiu da fila mas NÃO foi escrito e
                        # ``_video_frames_written`` não avança: sem esta linha o
                        # índice do MP4 desliza sem explicação no disco.
                        self._ledger_record_meta(meta, "write_failed")
                        log.warning(
                            "live_camera_service.video_write_error",
                            error=str(e),
                            frames_written=self._video_frames_written,
                        )
                else:
                    self._ledger_record_meta(meta, "not_recording")

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
                item = self.frame_queue.get(timeout=1)
            except queue.Empty:
                continue

            # Instante em que o frame SAIU da fila. Separa a espera de fila
            # (frame_t0 → dequeue) da inferência (dequeue → decisão) no log
            # closed-loop; sem isso ``capture_to_decision_ms`` é um agregado
            # que mistura as duas e não diz o que domina a latência.
            dequeue_perf = time.perf_counter()

            # Frames carry a monotonic capture timestamp (FRAME_T0) as a third
            # element. Tolerate legacy 2-tuples (older tests / callers) with a
            # None capture time — closed-loop latency just isn't measured then.
            if len(item) >= 3:
                frame_number, frame, capture_ts = item[0], item[1], item[2]
            else:
                frame_number, frame = item[0], item[1]
                capture_ts = None

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
                            # ATENÇÃO: este ``timestamp`` é o relógio de
                            # PROCESSAMENTO — medido nesta thread, DEPOIS da
                            # espera de fila e da inferência. NÃO use para
                            # latência nem para datar o evento. O instante real
                            # de captura está no ledger
                            # (``6_FrameLedger_<base>``), coluna
                            # ``t_capture_perf``/``t_capture_wall``, ligado por
                            # ``pipeline_frame == frame``. O schema de
                            # ``3_CoordMovimento`` é imutável por contrato, por
                            # isso a correção é feita no consumo.
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
                        self._dispatch_arduino_zone_commands(
                            detections, frame_number, capture_ts, dequeue_perf
                        )
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

        # Flush unmatched latency triggers and write 5_ClosedLoop_<base>.parquet.
        self._finalize_closed_loop_log()

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
        self._arduino_missed_frames = 0
        self._arduino_inverted_ack_seen = set()

        # Reset closed-loop latency state for the new session and drop any sink
        # left registered on the shared ArduinoManager by a previous session.
        self._closed_loop_log = None
        self._closed_loop_event_seq = 0
        manager = self._arduino_manager()
        if manager is not None and hasattr(manager, "set_latency_sink"):
            manager.set_latency_sink(None)

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
            exit_grace_frames=self._arduino_exit_grace_frames(),
        )

        # A token that is an "enter" here and an "exit" there cannot mean the
        # same thing to the firmware — the classic off-by-one when filling the
        # bindings table. We cannot fix it (only the sketch knows the semantics)
        # but the session must not start silently on a mapping that will latch a
        # device on and never release it.
        conflicts = cfg.token_conflicts()
        if conflicts:
            log.warning(
                "live_camera_service.arduino_zone_commands.token_conflict",
                conflicts=[c.describe() for c in conflicts],
                hint=(
                    "Each token should have a single role. Check the per-zone "
                    "bindings against the tokens your sketch implements."
                ),
            )

    def _arduino_exit_grace_frames(self) -> int:
        """Consecutive empty frames tolerated before emitting ROI exit tokens.

        Read from ``arduino.roi_exit_grace_frames``; falls back to the setting's
        own default when no settings object is attached (e.g. focused tests).
        """
        settings_obj = getattr(self, "settings", None)
        arduino_settings = getattr(settings_obj, "arduino", None)
        value = getattr(arduino_settings, "roi_exit_grace_frames", None)
        if value is None:
            return DEFAULT_ARDUINO_EXIT_GRACE_FRAMES
        return int(value)

    def _build_arduino_evaluator(self) -> Any:
        """Lazily build the ROI evaluator from the detector's scaled polygons.

        Returns the evaluator, or None if the detector has no usable ROI
        polygons yet (in which case we retry on the next frame).

        A regra de inclusão vem da fonte canônica (projeto > global > default),
        a mesma que o relatório usa: sem isso o LED disparava por centroide
        enquanto o ``log_eventos`` contava por bbox.
        """
        from zebtrack.core.services.arduino_roi_evaluator import ArduinoRoiEvaluator
        from zebtrack.core.services.roi_rule_resolver import resolve_roi_rule

        detector = self.detector_service.detector
        if detector is None:
            return None
        roi_names = list(getattr(detector, "roi_names", []) or [])
        roi_polygons = list(getattr(detector, "scaled_roi_polygons", []) or [])
        if not roi_names or not roi_polygons:
            return None

        project_data = getattr(self.project_manager, "project_data", None)
        rule_config = resolve_roi_rule(project_data, getattr(self, "settings", None))
        evaluator = ArduinoRoiEvaluator(
            roi_names,
            roi_polygons,
            rule_config=rule_config,
            px_per_cm=self._arduino_buffer_px_per_cm(project_data),
        )
        log.info(
            "live_camera_service.arduino_zone_commands.rule_resolved",
            rule=evaluator.rule,
            configured_rule=rule_config.rule,
            rois=evaluator.roi_names,
        )
        return evaluator if evaluator.has_rois() else None

    @staticmethod
    def _arduino_buffer_px_per_cm(project_data: Any) -> float:
        """Escala px/cm usada para dilatar a ROI, igual à do ``ROIAnalyzer``.

        O analisador converte o raio de buffer com ``sqrt(pixelcm_x*pixelcm_y)``;
        sem calibração o raio permanece em pixels (fator 1.0).

        Nada aqui pode levantar: isto roda no loop ao vivo. Um projeto com
        ``calibration`` de tipo errado (lista, string) faria ``.get`` levantar
        ``AttributeError`` — que o ``except (TypeError, ValueError)`` não pega —
        e derrubaria a sessão. Tipo inesperado vira "sem calibração".
        """
        if not isinstance(project_data, dict):
            return 1.0
        calibration = project_data.get("calibration")
        if not isinstance(calibration, dict):
            return 1.0
        try:
            px_x = float(calibration.get("pixelcm_x", 1.0) or 1.0)
            px_y = float(calibration.get("pixelcm_y", 1.0) or 1.0)
        except (TypeError, ValueError):
            return 1.0
        if not math.isfinite(px_x) or not math.isfinite(px_y) or px_x <= 0 or px_y <= 0:
            return 1.0
        return float(math.sqrt(px_x * px_y))

    def _dispatch_arduino_zone_commands(
        self,
        detections: list,
        frame_number: int | None = None,
        capture_ts: float | None = None,
        dequeue_ts: float | None = None,
    ) -> None:
        """Emit edge-triggered enter/exit tokens for the current frame.

        Computes which ROIs are occupied (any-track), diffs against the previous
        frame via the mapper, and queues the resulting tokens fire-and-forget.

        ``dequeue_ts`` is the ``perf_counter`` stamped when this frame left
        ``frame_queue``; it splits the software pipeline into queue wait and
        inference in the closed-loop log.

        When ``capture_ts`` (the frame's monotonic FRAME_T0) is available and the
        ArduinoManager supports the tracked path, each token is sent with a
        closed-loop latency context so the serial ``t_send``/``t_ack`` can be
        attributed back to the ROI transition.

        A frame with no detections is not proof the animal left its ROI — the
        tracker drops low-confidence frames routinely. Such frames are absorbed
        for ``arduino.roi_exit_grace_frames`` before the occupancy is allowed to
        go empty, so a momentary miss no longer emits an exit token followed by
        a re-enter on the next hit.
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

        if detections:
            self._arduino_missed_frames = 0
        else:
            self._arduino_missed_frames += 1
            if self._arduino_missed_frames <= self._arduino_exit_grace_frames():
                log.debug(
                    "live_camera_service.arduino_zone_commands.exit_deferred",
                    frame_number=frame_number,
                    missed_frames=self._arduino_missed_frames,
                )
                return  # hold the current occupancy — likely a tracker miss

        # Bboxes cruas, não centroides: a regra ``bbox_intersects`` precisa da
        # área da caixa para calcular a fração de sobreposição — reduzir a
        # detecção ao centroide aqui era o que fazia o Arduino divergir do
        # relatório.
        boxes: list[tuple[float, float, float, float]] = []
        for det in detections:
            try:
                x1, y1, x2, y2 = det[0], det[1], det[2], det[3]
            except (IndexError, TypeError, ValueError):
                continue
            boxes.append((float(x1), float(y1), float(x2), float(y2)))

        occupied = self._arduino_evaluator.occupied_rois(boxes)
        events = self._arduino_mapper.update_detailed(occupied)
        if not events:
            return

        # Enable closed-loop latency logging only when we have a capture instant
        # AND the manager exposes the tracked path. The log is built lazily on the
        # first tracked trigger (the recorder's output folder is known by then).
        can_track = (
            capture_ts is not None
            and hasattr(manager, "enqueue_tracked")
            and hasattr(manager, "set_latency_sink")
        )
        if can_track and self._closed_loop_log is None:
            self._closed_loop_log = self._maybe_create_closed_loop_log()
            if self._closed_loop_log is not None:
                manager.set_latency_sink(self._on_arduino_latency_sample)
        log_enabled = can_track and self._closed_loop_log is not None

        decision_perf = time.perf_counter() if log_enabled else None
        wall_s: float | None = None
        session_ts: float | None = None
        if log_enabled and self.recorder and self.recorder.start_time:
            wall_s = time.time()
            session_ts = wall_s - self.recorder.start_time

        for event in events:
            if log_enabled:
                self._closed_loop_event_seq += 1
                context = {
                    "event_id": self._closed_loop_event_seq,
                    "frame": frame_number,
                    "roi": event.roi,
                    "edge": event.edge,
                    "token": event.token,
                    "frame_t0": capture_ts,
                    "dequeue_perf": dequeue_ts,
                    "decision_perf": decision_perf,
                    "session_ts_s": session_ts,
                    "trigger_wall_s": wall_s,
                    "analysis_interval_frames": self.analysis_interval_frames,
                    "fps": self._actual_fps,
                }
                manager.enqueue_tracked(event.token, context)
            else:
                manager.enqueue(event.token)

    def _on_arduino_latency_sample(
        self,
        context: dict[str, Any],
        t_send: float | None,
        t_ack: float | None,
        ack_text: str | None,
    ) -> None:
        """Latency sink: write the closed-loop row, then sanity-check the ACK.

        The firmware's reply says what the device actually did, so an ``enter``
        answered with "... OFF" (or an ``exit`` with "... ON") proves the binding
        is inverted — the animal arriving turns the stimulus off. We cannot fix
        it (only the sketch knows the semantics) but the session must not look
        healthy while every trigger does the opposite of what was intended.

        Warned once per (roi, edge): the loop is edge-triggered but a ROI can be
        crossed dozens of times in a session.
        """
        closed_loop_log = self._closed_loop_log
        if closed_loop_log is not None:
            closed_loop_log.on_sample(context, t_send, t_ack, ack_text)

        if not ack_text:
            return
        from zebtrack.core.services.arduino_ack_semantics import (
            describe_inversion,
            edge_ack_is_inverted,
        )

        edge = context.get("edge")
        roi = context.get("roi")
        if not edge_ack_is_inverted(edge, ack_text):
            return
        key = (str(roi), str(edge))
        if key in self._arduino_inverted_ack_seen:
            return
        self._arduino_inverted_ack_seen.add(key)
        log.warning(
            "live_camera_service.arduino_zone_commands.ack_inverted",
            detail=describe_inversion(roi, edge, context.get("token"), ack_text),
            roi=roi,
            edge=edge,
            token=context.get("token"),
            ack_text=ack_text,
            hint=(
                "Check the per-zone bindings against the tokens your sketch "
                "implements — the reference sketch pairs ON/OFF consecutively "
                "(1/2, 3/4, 5/6, 7/8)."
            ),
        )

    def _maybe_create_closed_loop_log(self) -> Any:
        """Build the closed-loop latency log once the recorder folder is known.

        Returns the log instance, or None if the recorder has no output folder
        yet (in which case we retry on the next tracked trigger).
        """
        recorder = getattr(self, "recorder", None)
        output_folder = getattr(recorder, "output_folder", None)
        if not output_folder:
            return None
        base_name = (
            getattr(recorder, "base_name", "")
            or getattr(self, "_current_base_name", "")
            or getattr(self, "_experiment_id", "")
            or "session"
        )
        from zebtrack.core.services.closed_loop_latency import ClosedLoopLatencyLog

        log.info(
            "live_camera_service.closed_loop.log_created",
            output_folder=str(output_folder),
            base_name=base_name,
        )
        return ClosedLoopLatencyLog(output_folder, base_name)

    def _finalize_closed_loop_log(self) -> None:
        """Flush unmatched pendings and write the parquet snapshot at session end."""
        closed_loop_log = getattr(self, "_closed_loop_log", None)
        if closed_loop_log is None:
            return
        manager = self._arduino_manager()
        if manager is not None and hasattr(manager, "flush_pending_acks"):
            manager.flush_pending_acks()
        if manager is not None and hasattr(manager, "set_latency_sink"):
            manager.set_latency_sink(None)
        try:
            closed_loop_log.finalize()
            log.info(
                "live_camera_service.closed_loop.finalized",
                rows=closed_loop_log.row_count,
            )
        # except Exception justified: session teardown must not raise on an
        # optional analytics artifact.
        except Exception:
            log.error("live_camera_service.closed_loop.finalize_error", exc_info=True)
        self._closed_loop_log = None

    def _arduino_zone_session_end_sweep(self) -> None:
        """Queue the 'turn everything off' tokens at session end.

        Emits every distinct exit token. This only clears the hardware if each
        exit token clears something in the sketch — see the conflict warning
        raised at session start when that assumption does not hold.
        """
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
