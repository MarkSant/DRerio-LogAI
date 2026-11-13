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

from zebtrack.core.recording.frame_ledger import OUTCOME_DROPPED_ON_STOP
from zebtrack.core.services.processing_interval_resolver import (
    is_analysis_frame as _is_analysis_frame,
)
from zebtrack.i18n import _
from zebtrack.io.camera import CapturedFrame

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


def _recorder_takes_video(recorder: Any) -> bool:
    """Whether the recorder would write a video frame now.

    Asks ``Recorder.is_capturing_video()``, which also covers the parent of a
    multi-aquarium live session: it owns the session MP4 but never has
    ``is_recording`` set, so the old ``is_recording and video_writer`` test
    marked every frame of such a session ``not_recording`` (#635). Recorders
    without the probe (or answering with something that is not a ``bool``,
    as a ``MagicMock`` does) keep the old test.
    """
    if recorder is None:
        return False
    probe = getattr(recorder, "is_capturing_video", None)
    if callable(probe):
        verdict = probe()
        if isinstance(verdict, bool):
            return verdict
    is_recording = getattr(recorder, "is_recording", False)
    return bool(is_recording and getattr(recorder, "video_writer", None))


class _CameraRead(NamedTuple):
    """A frame for the capture loop and when it was captured."""

    frame: Any
    t_perf: float
    t_wall: float
    paced_by_camera: bool  # True: the source blocked until a NEW frame existed


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
    #: Which frame of each interval is analysed (#638); a class default so a
    #: host that never sets it keeps the offset-0 cadence.
    analysis_offset_frames: int = 0
    display_interval_frames: int
    _video_frames_written: int
    _live_detected_frames: int
    _analysis_lag_frames: int
    _last_analyzed_frame: int
    _tracker_frame_time_s: float | None
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
    #: Aquariums of a 2+-aquarium session (``None`` otherwise), resolved at
    #: ``start_session``; see ``_resolve_session_multi_zone_data`` (#635).
    _live_multi_zone_data: Any
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
    # Live analysis window (ADR-011, v8 F5). ``_analysis_window_raw`` is set by
    # ``start_session`` from the PROJECT (live project) or the dialog config (ad
    # hoc) — never from the shared ``Settings``.
    _analysis_window_raw: Any
    _condition_runtime: Any
    _condition_roi_evaluator: Any
    _condition_end_requested: bool
    _condition_clock_warned: bool
    _arduino_outputs_swept: bool

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

    def _declare_tracker_frame_time(self, detector: Any, capture_ts: float | None) -> None:
        """Hand the frame's CAPTURE instant to ByteTrack before detecting it (#654).

        Lost tracks then age in seconds of the camera's clock. The driver's fps
        (what ``set_source_fps`` gets) says nothing about the frames this thread
        actually analyses: a full queue drops analysis frames, the capture loop
        misses sensor frames, and webcams declaring 30 fps deliver 39-41. The
        multi-aquarium detector is created lazily, so it reads
        ``_tracker_frame_time_s`` itself (``_run_multi_aquarium_detection``).

        Args:
            detector: The detector about to run, or ``None`` for the multi path.
            capture_ts: ``t_perf`` of the frame's capture, ``None`` if unknown.
        """
        self._tracker_frame_time_s = capture_ts
        set_frame_time = getattr(detector, "set_frame_time", None)
        if detector is not None and callable(set_frame_time):
            set_frame_time(capture_ts)

    def get_last_detections(self) -> list: ...  # type: ignore[empty-body]
    def set_last_detections(self, detections: list) -> None: ...

    def _start_threads(self) -> bool:
        """Start capture, processing, and video recording threads."""
        try:
            # Clear exit event
            self.exit_event.clear()
            # Camera cursor of ``_read_camera_frame`` (#637).
            self._last_camera_seq = 0
            self._camera_frames_skipped = 0
            # Stops ONLY the capture thread, so the video thread can drain its
            # queue at stop time (#636); see ``_drain_video_queue_for_stop``.
            self._capture_stop_event = threading.Event()
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
            # Sensor frames read by the camera but never taken by the pipeline
            # (it was slower than the sensor): not rows, but not invisible.
            ledger.set_anchor(camera_frames_skipped=int(getattr(self, "_camera_frames_skipped", 0)))
            ledger.finalize()
            log.info("live_camera_service.frame_ledger.finalized", rows=ledger.row_count)
        # except Exception justified: o encerramento da sessão nunca pode falhar
        # por causa de um artefato de análise opcional.
        except Exception:
            log.error("live_camera_service.frame_ledger.finalize_error", exc_info=True)
        self._frame_ledger = None

    def _read_camera_frame(self) -> _CameraRead | None:
        """Next frame of the session source, with its capture instant.

        A ``Camera`` (``read_next_frame``) hands each sensor frame out once, with
        the instant ``cap.read`` returned it, and blocks until a new one exists;
        sensor frames the pipeline was too slow to take are counted in
        ``_camera_frames_skipped`` (they never became pipeline frames, so they
        have no ledger row). Any other source falls back to ``get_frame()``,
        stamped now and paced by the caller.
        """
        reader = getattr(self.camera, "read_next_frame", None)
        if callable(reader):
            last_seq = int(getattr(self, "_last_camera_seq", 0) or 0)
            captured = reader(last_seq, timeout=0.5)
            if captured is None:
                return None
            if isinstance(captured, CapturedFrame):
                gap = captured.seq - last_seq - 1
                if last_seq > 0 and gap > 0:
                    self._camera_frames_skipped = (
                        int(getattr(self, "_camera_frames_skipped", 0) or 0) + gap
                    )
                self._last_camera_seq = captured.seq
                return _CameraRead(captured.frame, captured.t_perf, captured.t_wall, True)
        ret, frame = self.camera.get_frame()  # type: ignore[union-attr]
        if not ret or frame is None:
            return None
        return _CameraRead(frame, time.perf_counter(), time.time(), False)

    def _capture_loop(self) -> None:
        """Thread loop for capturing frames from camera."""
        log.info("live_camera_service.capture_loop_started")

        if self.camera:
            log.info(
                "live_camera_service.capture_loop_using_camera",
                camera_index=self.camera._camera_index,
            )

        frame_count = 0

        while not self.exit_event.is_set() and not self._capture_stop_requested():
            if not self.camera:
                log.warning("live_camera_service.camera_not_initialized")
                time.sleep(0.1)
                continue

            try:
                read = self._read_camera_frame()
                if read is None:
                    log.warning("live_camera_service.frame_capture_failed", frame_count=frame_count)
                    self._check_camera_disconnect()
                    time.sleep(0.1)
                    continue
                frame = read.frame
                paced_by_camera = read.paced_by_camera

                # Update last valid frame timestamp
                current_time = read.t_wall
                self._last_valid_frame_time = current_time
                # Monotonic capture instant (FRAME_T0) — rides with the frame
                # through the queue so the closed-loop latency log can measure
                # capture -> LED-ACK end-to-end. perf_counter (not time()), so it
                # is immune to wall-clock adjustments. From a ``Camera`` it is the
                # instant ``cap.read`` returned, not the instant of this loop (#637).
                capture_perf = read.t_perf

                # If we were disconnected, mark reconnection
                if self._camera_disconnected:
                    self._on_camera_reconnected()

                frame_count += 1
                self._last_captured_frame = frame_count
                if frame_count == 1:
                    # ``t_s = 0`` of the session, fixed BEFORE frame 1 is queued
                    # anywhere: the live analysis window reads it while running,
                    # ``retime_from_ledger`` reads the same value from the anchor.
                    self._pin_capture_origin(capture_perf, current_time)

                # Create single copy of frame to share between queues
                frame_copy = frame.copy()

                # ANALYSIS FRAMES.
                # Avaliado ANTES do enfileiramento de vídeo (era o inverso) para
                # que a linha do ledger produzida pela thread de vídeo já carregue
                # ``is_analysis_frame``/``queued_for_analysis``. O conjunto de
                # operações bloqueantes por frame é o mesmo de antes — só a ordem
                # muda — e a fila de vídeo (600 slots ≈ 20 s) absorve a inversão.
                # Pipeline frames count from 1; the rule counts from the
                # source's first frame (0), the pre-recorded worker's way (#638).
                is_analysis_frame = _is_analysis_frame(
                    frame_count - 1, self.analysis_interval_frames, self.analysis_offset_frames
                )
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

                # Control capture rate — only for sources that do not block until
                # a NEW frame exists. A ``Camera`` paces this loop by itself: the
                # old fixed poll at 1.5x the configured fps duplicated sensor
                # frames whenever it outran the camera (#637).
                if not paced_by_camera:
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
            camera_frames_skipped=getattr(self, "_camera_frames_skipped", 0),
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

                if _recorder_takes_video(self.recorder):
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

    def _write_track_masks(self, frame_number: int, detections: list) -> None:
        """Grava as máscaras do quadro no sidecar ``3b_Mascaras_*``.

        No-op quando a captura está desligada: ``pop_track_masks`` devolve um
        dicionário vazio e o recorder não escreve nada, então o caminho normal
        (sem ``seg_overlap``) não paga custo algum.

        DEGRADA, nunca interrompe. Uma máscara perdida custa uma linha a menos no
        sidecar e faz o ROI cair no ``bbox_intersects`` com aviso; uma exceção
        aqui derrubaria a thread de processamento e levaria junto a GRAVAÇÃO,
        que é o dado que não volta.
        """
        detector = getattr(self.detector_service, "detector", None)
        popper = getattr(detector, "pop_track_masks", None)
        if not callable(popper):
            return

        try:
            masks = popper(detections)
            if masks:
                self.recorder.write_mask_data(frame_number, masks)
        # except Exception justified: recording-boundary — decodificação de
        # máscara e I/O do sidecar não podem abortar a sessão em andamento.
        except Exception:
            log.warning(
                "live_camera_service.mask_write_failed",
                frame_number=frame_number,
                exc_info=True,
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
        # Live analysis window (no-op without a spec). After the Arduino state:
        # it registers the inbound-event sink on the same manager.
        self._reset_condition_runtime()

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
                                _("⏳ Stabilizing image... ({current}/{total})").format(
                                    current=frame_number, total=30
                                ),
                                color="orange",
                            )
                        continue

                    # Process only every 5th frame
                    if frame_number % 5 != 0:
                        continue

                    # Update preview status (Phase 5 / M3 — main-thread bounce)
                    if self.preview_window and frame_number % 5 == 0:
                        status_msg = _("🔍 Detecting aquarium... ({current}/{total})").format(
                            current=self._aquarium_detection_frames,
                            total=self._aquarium_detection_max_frames,
                        )
                        self._post_preview_status(status_msg, color="yellow")

                    # Run detection to find aquarium (class_id=0)
                    detector = self.detector_service.detector
                    if detector:
                        # NOT `detections, _ =`: binding `_` locally shadows the
                        # gettext alias for the WHOLE function, including the
                        # status message a few lines above.
                        self._declare_tracker_frame_time(detector, capture_ts)
                        detections, _annotated = detector.detect(frame, "live", conf_threshold=0.05)

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
                            self._post_preview_status(_("● Recording"), color="red")

                    continue

                # PHASE 2: Normal Processing (after arena is defined)
                # ONE cadence, the capture thread's: a frame is analysed iff its
                # PIPELINE number is a multiple of N — exactly the ledger's
                # ``is_analysis_frame``. Counting the frames this thread happened
                # to RECEIVE (a subset, thinned by the opportunistic queueing)
                # decimated a second time: N to ~N^2 under load (#637).
                # Opportunistic frames still serve the display.
                should_analyze = _is_analysis_frame(
                    frame_number - 1, self.analysis_interval_frames, self.analysis_offset_frames
                )
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
                    # The session's aquariums, NOT ``get_zone_data()``: that is the
                    # aquarium-0 shim, never multi, so this branch was unreachable
                    # and a 2-aquarium session ran the single detector (#635).
                    multi_zone_data = self._session_multi_zone_data()
                    is_multi_aquarium = multi_zone_data is not None
                    if detector:
                        zone_data = (
                            multi_zone_data
                            if multi_zone_data is not None
                            else self.project_manager.get_zone_data()
                        )

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
                            self._declare_tracker_frame_time(None, capture_ts)
                            detections = self._run_multi_aquarium_detection(
                                frame, frame_number, zone_data
                            )
                        else:
                            self._declare_tracker_frame_time(detector, capture_ts)
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

                    # DEBUG, nao INFO: isto dispara a CADA frame analisado
                    # (~6/s com intervalo 5). Em INFO o proprio logging vira
                    # I/O dentro do laco quente da sessao.
                    log.debug(
                        "live_camera_service.detection_result",
                        frame_number=frame_number,
                        num_detections=len(detections),
                        has_recorder=self.recorder is not None,
                        recorder_start_time=self.recorder.start_time if self.recorder else None,
                    )

                    # Record detections
                    # Subject + context detections of THIS frame, popped once:
                    # the object sidecar and the analysis window both read them.
                    class_observations: list = []
                    if self.recorder and self.recorder.start_time:
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
                        class_observations = self._pop_class_observations()
                        if is_multi_aquarium:
                            # ``_run_multi_aquarium_detection`` already wrote the
                            # rows, partitioned per aquarium; the parent recorder
                            # has no trajectory of its own.
                            pass
                        elif detections:
                            self.recorder.write_detection_data(timestamp, frame_number, detections)
                            # Depois da trajetória e com as MESMAS detecções: o
                            # ``track_id`` que indexa a máscara é o que acabou de
                            # ser gravado na linha. Sem esta chamada o sidecar
                            # ``3b_Mascaras_*`` nunca existia ao vivo e
                            # ``seg_overlap`` degradava sempre para
                            # ``bbox_intersects``.
                            self._write_track_masks(frame_number, detections)
                            log.debug(
                                "live_camera_service.detection_written",
                                frame_number=frame_number,
                                num_detections=len(detections),
                                timestamp=timestamp,
                            )
                        else:
                            log.debug(
                                "live_camera_service.detection_skipped_empty",
                                frame_number=frame_number,
                            )
                        # ``3c_Objetos_`` heartbeat on EVERY analysed frame, with
                        # or without detections: the trajectory only gets a row
                        # when something was detected, so without this "nothing
                        # there" and "frame not analysed" look the same.
                        self._write_object_frame(
                            timestamp,
                            frame_number,
                            capture_ts,
                            class_observations,
                            multi_zone_data=multi_zone_data,
                        )
                    else:
                        log.warning(
                            "live_camera_service.detection_skipped_no_recorder",
                            frame_number=frame_number,
                            has_recorder=self.recorder is not None,
                            recorder_start_time=self.recorder.start_time if self.recorder else None,
                        )

                    # Analysis window, then per-zone Arduino commands: edge-triggered
                    # enter/exit tokens while recording. The window steps FIRST so
                    # the frame that confirms START already dispatches and the one
                    # that confirms STOP sweeps instead. Fire-and-forget (queued),
                    # so it never stalls this loop. No-op unless a window /
                    # Arduino + bindings are set.
                    if self.recorder and self.recorder.start_time:
                        self._step_condition_runtime(
                            frame_number, capture_ts, detections, class_observations
                        )
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

        # Close the analysis window (end-of-stream STOP if it is still open,
        # artifact next to the trajectory) BEFORE the session-end sweep: an open
        # window sweeps at its own STOP, so the sweep below finds it done.
        self._finalize_condition_runtime()

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
        self._arduino_outputs_swept = False

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
        # With an analysis window, per-ROI commands run ONLY inside it: nothing
        # before START, and the outputs were swept at STOP.
        runtime = getattr(self, "_condition_runtime", None)
        if runtime is not None and not runtime.window_open:
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
                # ``fps`` é a taxa REALMENTE alcançada, medida a partir dos
                # timestamps de captura (mesma fonte do frame ledger) — nunca o
                # valor configurado, que a câmera pode exceder (e às vezes
                # excede). O configurado vai em campo próprio, sem ambiguidade.
                frame_ledger = getattr(self, "_frame_ledger", None)
                measured_fps = (
                    frame_ledger.current_fps_measured() if frame_ledger is not None else None
                )
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
                    "fps": measured_fps,
                    "fps_configured": self._actual_fps,
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

        With an analysis window the sweep belongs to the window's STOP (see
        :meth:`_handle_condition_update`); here it only runs if the window never
        swept — and not at all if the window never opened, because then no
        per-ROI command was ever sent.
        """
        runtime = getattr(self, "_condition_runtime", None)
        if runtime is not None and not runtime.window_opened:
            log.info("live_camera_service.arduino_zone_commands.sweep_skipped_window_never_opened")
            return
        self._sweep_arduino_zone_outputs("session_end")

    def _sweep_arduino_zone_outputs(self, reason: str) -> None:
        """Enqueue every exit token, at most once per session."""
        if getattr(self, "_arduino_outputs_swept", False):
            return
        if not self._arduino_zone_enabled or not self._arduino_session_end_tokens:
            return
        manager = self._arduino_manager()
        if manager is None or not manager.is_connected():
            return
        self._arduino_outputs_swept = True
        for token in self._arduino_session_end_tokens:
            manager.enqueue(token)
        log.info(
            "live_camera_service.arduino_zone_commands.session_end_sweep",
            tokens=self._arduino_session_end_tokens,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Capture clock, object sidecar and live analysis window (ADR-011, v8 F5)
    # ------------------------------------------------------------------
    def _pin_capture_origin(self, t_perf: float, t_wall: float | None) -> None:
        """Pin ``t0`` of the session on the frame ledger (capture thread, frame 1)."""
        ledger = getattr(self, "_frame_ledger", None)
        pin = getattr(ledger, "pin_origin", None)
        if callable(pin):
            pin(t_perf, t_wall)

    def _capture_clock_origin(self) -> float | None:
        """``t0_perf`` of the session (the ledger anchor), or ``None`` if unknown."""
        ledger = getattr(self, "_frame_ledger", None)
        origin = getattr(ledger, "origin_perf", None)
        return float(origin) if isinstance(origin, int | float) else None

    def _capture_seconds(self, capture_ts: float | None) -> float:
        """Capture instant of a frame on the session clock (``t_capture_perf - t0``).

        ``NaN`` when the frame has no capture stamp or the session has no ledger
        anchor: an honest "unknown", never the processing clock in disguise.
        """
        origin = self._capture_clock_origin()
        if capture_ts is None or origin is None:
            return float("nan")
        return float(capture_ts) - origin

    def _pop_class_observations(self) -> list:
        """Subject + context detections of the last ``detect()`` (one-shot).

        The multi-aquarium detector, when it ran, holds this frame's
        observations; otherwise the single detector does. Never raises.
        """
        source = getattr(self, "_multi_aq_detector", None) or getattr(
            self.detector_service, "detector", None
        )
        pop = getattr(source, "pop_class_observations", None)
        if not callable(pop):
            return []
        try:
            observations = pop()
        # except Exception justified: an observation hook must never take the
        # processing thread (and with it the recording) down.
        except Exception:
            log.warning("live_camera_service.class_observations_failed", exc_info=True)
            return []
        return list(observations) if observations else []

    def _live_recording_fps(self) -> float | None:
        """Rate to write the session MP4 at: what the camera really delivers (#637).

        In order: the session ledger (the frames the pipeline actually took, so
        exactly the frames the MP4 will hold) once it has a stable sample — the
        case when recording starts after the arena-detection phase; else the
        camera's own measurement of its reads (it has been reading since it was
        opened, before the detector loaded); else what the driver reports;
        ``None`` lets the recorder use the settings.
        """
        ledger = getattr(self, "_frame_ledger", None)
        if ledger is not None and getattr(ledger, "row_count", 0) >= 30:
            measured = ledger.current_fps_measured()
            if isinstance(measured, int | float) and measured > 0:
                return float(measured)
        camera = getattr(self, "camera", None)
        probe = getattr(camera, "measured_fps", None)
        if callable(probe):
            measured = probe()
            if isinstance(measured, int | float) and measured > 0:
                return float(measured)
        reported = getattr(camera, "actual_fps", None)
        if isinstance(reported, int | float) and reported > 0:
            return float(reported)
        return None

    def _live_object_metadata(self) -> Any:
        """``3c_Objetos_`` metadata of a live recording (role map + capture clock).

        ``None`` when it cannot be built: the recorder then still records, with
        the clock inferred from the pipeline (``capture_perf`` for a camera).
        """
        from zebtrack.io.object_sidecar import CLOCK_CAPTURE, ObjectSidecarMetadata

        detector = getattr(getattr(self, "detector_service", None), "detector", None)
        try:
            return ObjectSidecarMetadata.from_role_map(
                getattr(detector, "class_role_map", None),
                clock=CLOCK_CAPTURE,
                analysis_interval_frames=getattr(self, "analysis_interval_frames", None),
            )
        # except Exception justified: metadata is an audit aid; recording goes on.
        except Exception:
            log.warning("live_camera_service.object_metadata_failed", exc_info=True)
            return None

    def _write_object_frame(
        self,
        timestamp: float,
        frame_number: int,
        capture_ts: float | None,
        observations: list,
        *,
        multi_zone_data: Any = None,
    ) -> None:
        """One ``3c_Objetos_`` heartbeat (+ observations) for an analysed frame.

        ``timestamp`` is the trajectory's (processing clock, kept for the join);
        ``t_event_s`` is the CAPTURE clock, the one the analysis window uses.
        A multi-aquarium session writes every aquarium's sidecar (one heartbeat
        each, rows routed by aquarium polygon), which the per-aquarium window
        of the post-analysis reads.
        DEGRADES, never raises — the recording is the data that does not return.
        """
        t_event_s = self._capture_seconds(capture_ts)
        if multi_zone_data is not None:
            partitioned = getattr(self.recorder, "write_partitioned_object_data", None)
            if not callable(partitioned):
                return
            polygons = {aq.id: aq.polygon for aq in multi_zone_data.aquariums}
            try:
                partitioned(timestamp, frame_number, t_event_s, observations, polygons)
            # except Exception justified: recording-boundary — sidecar I/O cannot
            # abort the session.
            except Exception:
                log.warning(
                    "live_camera_service.object_sidecar_write_failed",
                    frame_number=frame_number,
                    exc_info=True,
                )
            return
        writer = getattr(self.recorder, "write_object_data", None)
        if not callable(writer):
            return
        try:
            writer(timestamp, frame_number, t_event_s, observations)
        # except Exception justified: recording-boundary — sidecar I/O cannot
        # abort the session.
        except Exception:
            log.warning(
                "live_camera_service.object_sidecar_write_failed",
                frame_number=frame_number,
                exc_info=True,
            )

    def _reset_condition_runtime(self) -> None:
        """Build this session's analysis-window runtime (no-op without a spec).

        The spec comes from ``start_session(analysis_window=...)``: the project's
        ``analysis_window`` (live project) or the dialog config (ad hoc), never
        the shared ``Settings``. Multi-aquarium live is outside the window's
        scope in v8: the session records normally and the window is skipped with
        a warning (the analysis can still apply it offline per aquarium).
        """
        from zebtrack.core.recording.condition_runtime import (
            ConditionRuntime,
            parse_window_spec,
            role_names_from_role_map,
        )

        self._condition_runtime = None
        self._condition_roi_evaluator = None
        self._condition_end_requested = False
        self._condition_clock_warned = False

        manager = self._arduino_manager()
        if manager is not None and hasattr(manager, "set_event_sink"):
            manager.set_event_sink(None)

        spec = parse_window_spec(getattr(self, "_analysis_window_raw", None))
        if spec is None:
            return
        if self._is_multi_aquarium_session():
            log.warning("live_camera_service.analysis_window.multi_aquarium_unsupported")
            return

        detector = getattr(self.detector_service, "detector", None)
        role_names = role_names_from_role_map(getattr(detector, "class_role_map", None))
        runtime = ConditionRuntime(
            spec, role_names=role_names, clock_origin=self._capture_clock_origin
        )
        self._condition_runtime = runtime
        if manager is not None and hasattr(manager, "set_event_sink"):
            manager.set_event_sink(self._on_arduino_condition_event)
        log.info(
            "live_camera_service.analysis_window.armed",
            listens_arduino=runtime.listens_to("arduino"),
            listens_manual=runtime.listens_to("manual"),
            on_stop=spec.on_stop,
            roles=sorted(role_names),
        )
        self._post_window_state(runtime)

    def _session_multi_zone_data(self) -> Any:
        """The session's aquariums when it films 2+ of them, else ``None``."""
        return getattr(self, "_live_multi_zone_data", None)

    def _is_multi_aquarium_session(self) -> bool:
        # Was a probe of ``project_manager.get_zone_data()``, the aquarium-0
        # shim, which never carries ``aquariums``: the window was armed in
        # 2-aquarium sessions and stepped with both aquariums' detections.
        return self._session_multi_zone_data() is not None

    def _on_arduino_condition_event(self, code: int, t_read_perf: float) -> bool:
        """``ArduinoManager`` event sink (reader thread): hand the code to the window.

        Returns ``True`` (claimed) when the window waits for Arduino events: the
        code is then an ENGINE event and never reaches the recording
        coordinators (it must not start or stop a session as well).
        """
        runtime = getattr(self, "_condition_runtime", None)
        if runtime is None:
            return False
        return bool(runtime.offer_external("arduino", code, t_read_perf))

    def push_manual_condition_event(self) -> bool:
        """The operator's "Mark start/stop" press (Tk thread), stamped now.

        Returns:
            ``False`` when no analysis window is running (nothing recorded).
        """
        runtime = getattr(self, "_condition_runtime", None)
        if runtime is None:
            return False
        runtime.push_manual()
        return True

    def _condition_subject_rois(self, detections: list) -> frozenset[str]:
        """ROIs the subject occupies, by the SAME rule as the Arduino commands."""
        if not detections:
            return frozenset()
        if self._condition_roi_evaluator is None:
            self._condition_roi_evaluator = self._build_arduino_evaluator()
            if self._condition_roi_evaluator is None:
                return frozenset()  # detector ROIs not ready yet
        boxes: list[tuple[float, float, float, float]] = []
        for det in detections:
            try:
                boxes.append((float(det[0]), float(det[1]), float(det[2]), float(det[3])))
            except (IndexError, TypeError, ValueError):
                continue
        return frozenset(self._condition_roi_evaluator.occupied_rois(boxes))

    def _step_condition_runtime(
        self,
        frame_number: int,
        capture_ts: float | None,
        detections: list,
        observations: list,
    ) -> None:
        """Feed one analysed frame to the window (processing thread).

        Dated by the frame's CAPTURE instant; the trajectory ``timestamp`` is a
        processing clock and is never used. A frame without a capture stamp is
        skipped (warned once) rather than dated wrongly.
        """
        runtime = getattr(self, "_condition_runtime", None)
        if runtime is None:
            return
        if capture_ts is None:
            if not getattr(self, "_condition_clock_warned", False):
                self._condition_clock_warned = True
                log.warning("live_camera_service.analysis_window.frame_without_capture_stamp")
            return
        from zebtrack.core.recording.condition_runtime import classes_from_observations

        try:
            update = runtime.step(
                frame=frame_number,
                t_capture_perf=capture_ts,
                classes=classes_from_observations(observations),
                subject_rois=self._condition_subject_rois(detections),
                # Wall time ELAPSED is what ``TimeReached(clock="wall")`` reads;
                # perf_counter differences are exactly that, without wall jumps.
                t_wall=capture_ts,
            )
        # except Exception justified: the window is an analysis aid; it must
        # never stop the processing thread, which also feeds the recording.
        except Exception:
            log.error("live_camera_service.analysis_window.step_failed", exc_info=True)
            return
        self._handle_condition_update(update)

    def _handle_condition_update(self, update: Any) -> None:
        """Act on what the window decided: sweep, UI state, session end."""
        runtime = getattr(self, "_condition_runtime", None)
        if update.stop_confirmed:
            self._sweep_arduino_zone_outputs("window_stop")
        if update.phase_changed and runtime is not None:
            self._post_window_state(runtime)
        if update.end_session and not getattr(self, "_condition_end_requested", False):
            self._condition_end_requested = True
            self._request_window_session_end()

    def _request_window_session_end(self) -> None:
        """``on_stop="end_session"``: finish NOW, keeping the data (Tk thread).

        Goes through ``finish_session_early`` — the "End and Save" path, with
        ``keep_data=True`` — never ``_on_session_complete(output_dir)`` raw:
        an early stop without ``keep_data`` falls into the 50 % heuristic,
        which writes ``.cancelled`` and erases the project polygon.
        """
        finish = getattr(self, "finish_session_early", None)
        root = getattr(self, "root", None)
        if not callable(finish) or root is None or not hasattr(root, "after"):
            log.warning("live_camera_service.analysis_window.end_session_unavailable")
            return
        log.info("live_camera_service.analysis_window.end_session_requested")
        root.after(0, finish)

    def _post_window_state(self, runtime: Any) -> None:
        """Show the window phase: preview status + ``ANALYSIS_WINDOW_STATE_CHANGED``.

        Both go through the Tk thread (``root.after``); ``EventBusV2.publish``
        is synchronous, so publishing from the processing thread would run the
        UI handlers there.
        """
        from zebtrack.core.recording.condition_runtime import WindowPhase, window_phase_message
        from zebtrack.ui import payloads

        phase = runtime.phase
        result = runtime.result
        event = result.stop if phase is WindowPhase.FINISHED else result.start
        t_s = None if event is None or phase is WindowPhase.WAITING_START else event.t_s
        reason = None if event is None or phase is WindowPhase.WAITING_START else event.reason
        payload = payloads.AnalysisWindowStatePayload(
            state=phase.value,
            t_s=t_s,
            reason=reason,
            on_start_not_met=runtime.spec.on_start_not_met,
            on_stop=runtime.spec.on_stop,
            experiment_id=getattr(self, "_experiment_id", None) or None,
        )
        colors = {
            WindowPhase.WAITING_START: "orange",
            WindowPhase.IN_ANALYSIS: "red",
            WindowPhase.FINISHED: "green",
            WindowPhase.START_NOT_MET: "yellow",
        }
        self._post_preview_status(
            window_phase_message(phase, t_s=t_s, on_start_not_met=payload.on_start_not_met),
            color=colors[phase],
        )
        root = getattr(self, "root", None)
        if root is not None and hasattr(root, "after"):
            root.after(0, self._publish_window_state, payload)
        else:
            self._publish_window_state(payload)

    def _publish_window_state(self, payload: Any) -> None:
        """Publish ``ANALYSIS_WINDOW_STATE_CHANGED`` (runs on the Tk thread)."""
        event_bus = getattr(self, "event_bus", None)
        if event_bus is None:
            return
        from zebtrack.ui.event_bus_v2 import Event, UIEvents

        event_bus.publish(
            Event(
                type=UIEvents.ANALYSIS_WINDOW_STATE_CHANGED,
                data=payload,
                source="frame_processing_pipeline.analysis_window",
            )
        )

    def _finalize_condition_runtime(self) -> None:
        """Session end: close the window, write ``7_AnalysisWindow_`` (online part).

        Runs on the processing thread after its loop, BEFORE the recorder is
        stopped (``stop_session`` joins this thread first), so the recorder still
        knows the output folder and base name of the trajectory.
        """
        manager = self._arduino_manager()
        if manager is not None and hasattr(manager, "set_event_sink"):
            manager.set_event_sink(None)
        runtime = getattr(self, "_condition_runtime", None)
        if runtime is None:
            return
        try:
            self._handle_condition_update(runtime.finish())
        # except Exception justified: session teardown must not raise.
        except Exception:
            log.error("live_camera_service.analysis_window.finish_failed", exc_info=True)

        recorder = getattr(self, "recorder", None)
        output_folder = getattr(recorder, "output_folder", None)
        base_name = getattr(recorder, "base_name", "") or getattr(self, "_current_base_name", "")
        if not output_folder or not base_name:
            log.warning("live_camera_service.analysis_window.artifact_no_output")
            return
        ledger = getattr(self, "_frame_ledger", None)
        fps = ledger.current_fps_measured() if ledger is not None else None
        try:
            runtime.write_artifact(output_folder, base_name, fps_video=fps)
        # except Exception justified: optional analysis artifact; the analysis
        # recomputes the window from the recorded inputs without it.
        except Exception:
            log.error("live_camera_service.analysis_window.artifact_failed", exc_info=True)

    def _capture_stop_requested(self) -> bool:
        """Whether the stop sequence asked the capture thread (only) to end."""
        event = getattr(self, "_capture_stop_event", None)
        return bool(event is not None and event.is_set())

    def _drain_video_queue_for_stop(self, timeout_s: float) -> int:
        """Stop capturing, then let the video thread write what is queued (#636).

        The stop used to set ``exit_event`` and empty both queues at once: up to
        ``video_queue.maxsize`` frames (~20 s) captured but never written, and,
        since a recorded frame gets its ledger row only when the video thread
        consumes it, never logged either — the end of the session vanished.

        Order: the capture thread is told to stop (no new frames), then the
        video thread, still running, empties the queue until it is empty or
        ``timeout_s`` runs out. What is left is the caller's to record as
        ``dropped_on_stop`` (``_clear_queues``).

        Returns:
            How many video frames are still queued.
        """
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        event = getattr(self, "_capture_stop_event", None)
        if event is not None:
            event.set()
        capture = getattr(self, "capture_thread", None)
        if capture is not None and capture.is_alive():
            capture.join(timeout=max(0.0, deadline - time.monotonic()))
        writer = getattr(self, "video_recording_thread", None)
        while (
            writer is not None
            and writer.is_alive()
            and not self.video_queue.empty()
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        left = self.video_queue.qsize()
        log.info(
            "live_camera_service.video_queue_drained_for_stop",
            frames_written=getattr(self, "_video_frames_written", 0),
            frames_left=left,
        )
        return left

    def _clear_queues(self) -> None:
        """Empty both queues; every discarded VIDEO frame gets its ledger row.

        Analysis-queue items are dropped silently on purpose: the same frame is
        (or was) in the video queue, whose item carries its ledger row. A video
        item discarded here never reached the MP4, so it is recorded as
        ``dropped_on_stop`` (#636): one ledger row per captured frame holds
        up to the very end of the session.
        """
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break

        dropped = 0
        while not self.video_queue.empty():
            try:
                item = self.video_queue.get_nowait()
            except queue.Empty:
                break
            _frame, meta = _unpack_video_item(item)
            self._ledger_record_meta(meta, OUTCOME_DROPPED_ON_STOP)
            dropped += 1
        if dropped:
            log.warning(
                "live_camera_service.video_frames_dropped_on_stop",
                frames=dropped,
                note="logged in 6_FrameLedger as dropped_on_stop",
            )

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
