"""Camera Connection Handler — setup, preview, disconnect/reconnect logic.

Extracted from LiveCameraService (Phase 2.2 decomposition).
Provides the ``CameraConnectionMixin`` mixed into ``LiveCameraService``.
"""

from __future__ import annotations

import time
from dataclasses import is_dataclass
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.ui import payloads as payloads

if TYPE_CHECKING:
    from zebtrack.core.main_view_model import MainViewModel
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.recording.recording_service import RecordingService
    from zebtrack.core.services.detector_service import DetectorService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.io.camera import Camera
    from zebtrack.ui.dialogs import LivePreviewWindow
    from zebtrack.ui.event_bus_v2 import EventBusV2

log = structlog.get_logger()


def _payload_get(payload: payloads.EventPayload | dict[str, Any], key: str, default=None):
    if isinstance(payload, dict):
        return payload.get(key, default)
    if is_dataclass(payload) and not isinstance(payload, type):
        return getattr(payload, key, default)
    return default


class CameraConnectionMixin:
    """Mixin providing camera setup, preview, disconnect/reconnect for LiveCameraService.

    Methods:
        _setup_camera, _create_preview_window, _check_camera_disconnect,
        _on_camera_reconnected, _on_disconnect_user_action
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
    _last_valid_frame_time: float | None
    _camera_disconnect_threshold_s: float
    _camera_disconnected: bool
    _disconnect_gaps: list[tuple[float, float | None]]
    _recording_paused: bool
    _analysis_params: dict
    _user_disconnect_action: str | None
    _animals_per_aquarium: int

    camera: Camera | None
    preview_window: LivePreviewWindow | None

    def stop_session(self) -> bool: ...  # type: ignore[empty-body]  # from LiveSessionManagerMixin

    def _setup_camera(self, camera_index: int) -> bool:
        """Set up camera with given index."""
        try:
            from zebtrack.io.camera import Camera

            log.info("live_camera_service.setting_up_camera", camera_index=camera_index)

            # Defensive cleanup: release any Camera handle currently parked on
            # ``hardware_vm.camera`` BEFORE opening the session camera. Since
            # Etapa 10b ``ProjectInitializer.initialize_live_components`` no
            # longer opens a Camera at project init — but other code paths
            # (legacy preview features, future contributions) might still
            # leave a handle attached. If so, we'd hold two device handles at
            # once and with per-session camera overrides could even power on
            # two physically different cameras simultaneously (LEDs lit, USB
            # bandwidth contention, possible CAP_DSHOW open failure). The
            # helper is a no-op when ``hardware_vm.camera`` is None, which is
            # the normal path today.
            self._release_preview_camera_if_any()

            # Create temporary settings with desired camera index and force 720p resolution
            temp_settings = self.settings.model_copy(deep=True)
            log.info(
                "live_camera_service.settings_before_override",
                original_index=temp_settings.camera.index,
                requested_index=camera_index,
            )
            temp_settings.camera.index = camera_index

            # Force 1280x720 resolution for consistent performance across all cameras
            temp_settings.camera.desired_width = 1280
            temp_settings.camera.desired_height = 720
            log.info(
                "live_camera_service.settings_after_override",
                new_index=temp_settings.camera.index,
                forced_resolution="1280x720",
                reason="consistent_performance",
            )

            self.camera = Camera(settings_obj=temp_settings)

            if not self.camera.is_opened():
                log.error("live_camera_service.camera_not_opened", camera_index=camera_index)
                return False

            # CRITICAL: Warm up camera by discarding first frames
            log.info("live_camera_service.camera_warmup_start", camera_index=camera_index)

            warmup_frames = 50
            warmup_timeout = 5.0
            min_success_ratio = 0.3

            successful_warmup = 0
            warmup_start = time.time()
            for _warmup_count in range(warmup_frames):
                if time.time() - warmup_start > warmup_timeout:
                    log.warning(
                        "live_camera_service.camera_warmup_timeout",
                        camera_index=camera_index,
                        elapsed=time.time() - warmup_start,
                    )
                    break

                ret, frame = self.camera.get_frame()
                if ret and frame is not None:
                    successful_warmup += 1
                else:
                    time.sleep(0.1)
                time.sleep(0.05)

            success_ratio = successful_warmup / warmup_frames if warmup_frames > 0 else 0
            log.info(
                "live_camera_service.camera_warmup_complete",
                camera_index=camera_index,
                frames_requested=warmup_frames,
                frames_successful=successful_warmup,
                success_ratio=f"{success_ratio:.1%}",
                warmup_duration=f"{time.time() - warmup_start:.2f}s",
            )

            if success_ratio < min_success_ratio:
                log.warning(
                    "live_camera_service.camera_warmup_poor",
                    camera_index=camera_index,
                    success_ratio=f"{success_ratio:.1%}",
                    recommendation="Camera may not be fully ready. Consider longer warmup.",
                )

            actual_camera_index = self.camera._camera_index
            log.info(
                "live_camera_service.camera_ready",
                requested_camera_index=camera_index,
                actual_camera_index=actual_camera_index,
                width=self.camera.actual_width,
                height=self.camera.actual_height,
            )

            if actual_camera_index != camera_index:
                log.error(
                    "live_camera_service.camera_index_mismatch",
                    requested=camera_index,
                    actual=actual_camera_index,
                )
                return False

            return True

        # except Exception justified: camera hardware I/O — heterogeneous failures
        except Exception as e:
            log.error(
                "live_camera_service.camera_setup_failed",
                camera_index=camera_index,
                error=str(e),
                exc_info=True,
            )
            return False

    def _release_preview_camera_if_any(self) -> None:
        """Release any Camera handle currently parked on ``hardware_vm.camera``.

        Since Etapa 10b ``ProjectInitializer.initialize_live_components`` no
        longer opens a Camera at project load (the previous behaviour kept a
        handle alive purely to feed a now-deleted ``detector.update_scaling``
        API), so on the normal path ``hardware_vm.camera`` is None and this
        helper is a no-op. It remains as defensive cleanup in case some
        other code path (legacy preview features, future contributions)
        leaves a handle attached — if so, releasing it here before opening
        the session camera prevents double-device-power-on and CAP_DSHOW
        conflicts.
        """
        controller = getattr(self, "controller", None)
        hardware_vm = getattr(controller, "hardware_vm", None) if controller else None
        preview_camera = getattr(hardware_vm, "camera", None) if hardware_vm else None
        if preview_camera is None:
            return
        try:
            preview_camera.release()
            log.info("live_camera_service.preview_camera.released")
        # except Exception justified: best-effort cleanup of legacy preview camera
        except Exception as e:
            log.warning("live_camera_service.preview_camera.release_failed", error=str(e))
        finally:
            hardware_vm.camera = None  # type: ignore[union-attr]
            if getattr(hardware_vm, "active_frame_source", None) is preview_camera:
                hardware_vm.active_frame_source = None  # type: ignore[union-attr]

    def _create_preview_window(self, camera_index: int, duration_s: float) -> None:
        """Create the live preview window."""
        from zebtrack.core.project.zone_manager import MultiAquariumZoneData
        from zebtrack.ui.dialogs import LivePreviewWindow
        from zebtrack.ui.dialogs.multi_aquarium_live_preview_window import (
            MultiAquariumLivePreviewWindow,
        )

        def on_stop_callback():
            """Handle manual stop from preview window."""
            log.info("live_camera_service.manual_stop_requested")
            self.stop_session()

        zone_data = self.project_manager.get_zone_data() if self.project_manager else None

        if isinstance(zone_data, MultiAquariumZoneData) and zone_data.aquariums:
            num_aquariums = len(zone_data.aquariums)
            self.preview_window = MultiAquariumLivePreviewWindow(
                parent=self.root,
                camera_index=camera_index,
                num_aquariums=num_aquariums,
                duration_s=duration_s,
                on_stop_callback=on_stop_callback,
            )
            log.info(
                "live_camera_service.multi_aquarium_preview_window_created",
                num_aquariums=num_aquariums,
            )
        else:
            self.preview_window = LivePreviewWindow(
                parent=self.root,
                camera_index=camera_index,
                duration_s=duration_s,
                on_stop_callback=on_stop_callback,
            )
            log.info("live_camera_service.preview_window_created")

    def _check_camera_disconnect(self) -> None:
        """Check if camera has been disconnected based on frame gap.

        Detects disconnects when no valid frames received for > threshold seconds.
        Publishes CAMERA_DISCONNECT_DETECTED event and pauses recorder.
        """
        if self._last_valid_frame_time is None:
            return

        current_time = time.time()
        gap_duration = current_time - self._last_valid_frame_time

        if gap_duration > self._camera_disconnect_threshold_s and not self._camera_disconnected:
            self._camera_disconnected = True
            gap_start_time = self._last_valid_frame_time

            log.error(
                "live_camera_service.camera_disconnected",
                gap_duration=f"{gap_duration:.1f}s",
                threshold=f"{self._camera_disconnect_threshold_s}s",
            )

            # Pause recorder to avoid writing invalid/cached frames
            if self.recorder and not self._recording_paused:
                try:
                    self.recorder.pause_recording()
                    self._recording_paused = True
                    log.info("live_camera_service.recorder_paused")
                except AttributeError:
                    log.warning("live_camera_service.recorder_pause_not_supported")
                except OSError as e:
                    log.error("live_camera_service.recorder_pause_failed", error=str(e))

            # Publish disconnect event
            if self.event_bus:
                from zebtrack.ui.event_bus_v2 import Event, UIEvents

                self.event_bus.publish(
                    Event(
                        type=UIEvents.CAMERA_DISCONNECT_DETECTED,
                        data=payloads.CameraDisconnectPayload(
                            gap_duration_s=gap_duration,
                            gap_start_time=gap_start_time,
                            experiment_id=self._analysis_params.get("experiment_id", "unknown"),
                        ),
                    ),
                )

            # Record gap start
            self._disconnect_gaps.append((gap_start_time, None))

    def _on_camera_reconnected(self) -> None:
        """Handle camera reconnection after disconnect.

        Resumes recorder and logs gap duration for metadata.
        """
        if not self._camera_disconnected:
            return

        current_time = time.time()
        gap_duration = 0.0

        # Find the open gap and close it
        if self._disconnect_gaps and self._disconnect_gaps[-1][1] is None:
            gap_start = self._disconnect_gaps[-1][0]
            gap_duration = current_time - gap_start
            self._disconnect_gaps[-1] = (gap_start, current_time)

            log.info(
                "live_camera_service.camera_reconnected",
                gap_duration=f"{gap_duration:.1f}s",
            )

        # Resume recorder
        if self.recorder and self._recording_paused:
            try:
                self.recorder.resume_recording()
                self._recording_paused = False
                log.info("live_camera_service.recorder_resumed")
            except AttributeError:
                log.warning("live_camera_service.recorder_resume_not_supported")
            except OSError as e:
                log.error("live_camera_service.recorder_resume_failed", error=str(e))

        # Publish reconnect event
        if self.event_bus:
            from zebtrack.ui.event_bus_v2 import Event, UIEvents

            self.event_bus.publish(
                Event(
                    type=UIEvents.CAMERA_RECONNECTED,
                    data=payloads.CameraDisconnectPayload(
                        gap_duration_s=gap_duration if self._disconnect_gaps else 0.0,
                        total_gaps=len(self._disconnect_gaps),
                    ),
                ),
            )

        self._camera_disconnected = False

    def _on_disconnect_user_action(
        self, event_data: payloads.EventPayload | dict[str, Any]
    ) -> None:
        """Handle user action from disconnect recovery dialog.

        Args:
            event_data: Event payload with 'action' (wait|resume|stop) and 'experiment_id'
        """
        action = _payload_get(event_data, "action", "wait")
        experiment_id = _payload_get(event_data, "experiment_id", "unknown")

        log.info(
            "live_camera_service.disconnect_user_action",
            action=action,
            experiment_id=experiment_id,
        )

        with self._lock:
            self._user_disconnect_action = action

        if action == "resume":
            if self._camera_disconnected:
                log.info("live_camera_service.force_resume_attempt")
        elif action == "stop":
            log.info("live_camera_service.stop_by_user_action")
            self.stop_session()
        # else action == "wait": Continue monitoring for automatic reconnection
