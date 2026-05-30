"""Live Calibration Coordinator - Phase 4.7 Decomposition.

Extracted from SessionCoordinator (Phase 3).

Responsibilities:
    - Camera calibration with auto-detection (run_live_calibration)
    - Reference frame capture for zone tab (_capture_reference_frame_for_zones)
    - Zone validation before recording (ensure_zones_before_recording)

Architecture:
    - Zero MainViewModel dependency
    - Pure dependency injection pattern
    - Creates Camera and AquariumDetector internally (not injected)
    - Publishes events via EventBus
"""

from __future__ import annotations

import datetime
import os
import time
from typing import TYPE_CHECKING, Any

import cv2
import structlog

from zebtrack.coordinators.base_coordinator import (
    BaseCoordinator,
    CoordinatorError,
)
from zebtrack.core.detection.aquarium_detector import AquariumDetector
from zebtrack.io.camera import Camera
from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import Event, UIEvents
from zebtrack.ui.payloads import VideoPathPayload

if TYPE_CHECKING:
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.services.detector_service import DetectorService
    from zebtrack.core.services.weight_manager import WeightManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2

log = structlog.get_logger()


# =============================================================================
# EXCEPTIONS
# =============================================================================


class LiveCalibrationCoordinatorError(CoordinatorError):
    """Base exception for LiveCalibrationCoordinator errors."""

    pass


# =============================================================================
# MAIN COORDINATOR
# =============================================================================


class LiveCalibrationCoordinator(BaseCoordinator):
    """Coordinator for live camera calibration and zone validation.

    Phase 4.7 Decomposition — extracted from SessionCoordinator.

    Responsibilities:
        - Auto-detect aquarium via ML model (run_live_calibration)
        - Capture reference frame for manual zone drawing
        - Validate that zones exist before recording starts
    """

    def __init__(
        self,
        state_manager: StateManager,
        project_manager: ProjectManager,
        detector_service: DetectorService,
        weight_manager: WeightManager,
        settings_obj: Settings,
        event_bus: EventBusV2 | None = None,
        # UI components (temporary - being phased out)
        root: Any = None,
        view: Any = None,
    ):
        """Initialize LiveCalibrationCoordinator with pure dependency injection.

        Args:
            state_manager: StateManager for centralized state tracking
            project_manager: ProjectManager for project data and zones
            detector_service: DetectorService for detection configuration
            weight_manager: WeightManager for model weights
            settings_obj: Settings configuration object
            event_bus: EventBusV2 for UI notifications (optional)
            root: Tkinter root window (legacy, being phased out)
            view: GUI view instance (legacy, being phased out)

        Note:
            CRITICAL: NEVER pass MainViewModel. All dependencies must be explicit.
        """
        super().__init__(state_manager=state_manager, event_bus=event_bus)

        # Core services
        self.project_manager = project_manager
        self.detector_service = detector_service
        self.weight_manager = weight_manager
        self.settings = settings_obj

        # UI components (temporary - being phased out)
        self.root = root
        self.view = view

        # Internal state
        self.camera: Camera | None = None
        self._pending_zone_confirmation = False
        self._session_count = 0
        # Source of the polygon for the pending session: "auto" (PreviewPolygonDialog
        # approved an auto-detected polygon) or "manual" (user drew it / fell back to
        # manual mode). Read by LiveCameraSessionCoordinator when publishing
        # LIVE_RECORDING_PENDING so the UI / completion metadata can show provenance.
        self._last_polygon_source: str | None = None

        # Detector cached during run_live_calibration so the PreviewPolygonDialog
        # retry callback can re-run inference without reloading model weights.
        self._calibration_detector: AquariumDetector | None = None
        self._calibration_initial_confidence: float = 0.05
        # Cached at run_live_calibration time so the retry callback uses the
        # same project flag without re-reading project_data.
        self._calibration_preserve_real_shape: bool = False

        # Tristate-ish exit reason from the most recent ``run_live_calibration``
        # call. ``True`` means the user explicitly cancelled (closed or rejected
        # the preview dialog) — distinct from a genuine detection failure.
        # ``attempt_zone_calibration`` reads this to decide whether to fall
        # through to manual drawing (genuine failure) or abort cleanly (cancel).
        self._last_calibration_cancelled: bool = False

        log.info("live_calibration_coordinator.initialized")

    def _release_calibration_camera(self, reason: str) -> None:
        """Tear down ``self.camera`` and signal its background thread to stop.

        Centralises the "stop background thread + release + drop reference"
        sequence so every early-return path in ``run_live_calibration`` (and
        the retry callback) releases the camera consistently. Without this,
        a rejected preview dialog leaves the Camera instance alive and its
        capture thread spams ``camera.frame_read.failed`` /
        ``camera.disconnected`` warnings indefinitely.

        Args:
            reason: Short tag appended to the log event for triage.
        """
        camera = self.camera
        if camera is None:
            return
        # Signal shutdown BEFORE release so the background thread does not
        # try to reconnect after the device handle is gone.
        stopped_event = getattr(camera, "_stopped", None)
        if stopped_event is not None and hasattr(stopped_event, "set"):
            try:
                stopped_event.set()
            # except Exception justified: defensive — release must not throw.
            except Exception:  # pragma: no cover
                log.debug("live_calibration_coordinator.camera.stop_signal_failed")
        release_fn = getattr(camera, "release", None)
        if callable(release_fn):
            try:
                release_fn()
            # except Exception justified: hardware/OS may already have torn
            # the device down — log and continue rather than propagating.
            except Exception:  # pragma: no cover
                log.debug("live_calibration_coordinator.camera.release_failed")
        self.camera = None
        log.info("live_calibration_coordinator.camera_released", reason=reason)

    @property
    def last_polygon_source(self) -> str | None:
        """Source of the most recently confirmed polygon ("auto" / "manual" / None)."""
        return self._last_polygon_source

    def _set_last_polygon_source(self, source: str | None) -> None:
        """Update ``_last_polygon_source`` and publish ``LIVE_POLYGON_SOURCE_CHANGED``.

        Centralised so the Zone tab context panel can mirror the value without
        polling. Publishes unconditionally (including no-op transitions) so the
        UI can re-render after a project reload that resets internal state.
        """
        self._last_polygon_source = source
        if self.event_bus is None:
            return
        try:
            self.event_bus.publish(
                Event(
                    type=UIEvents.LIVE_POLYGON_SOURCE_CHANGED,
                    data=payloads.LivePolygonSourceChangedPayload(source=source),
                    source="LiveCalibrationCoordinator._set_last_polygon_source",
                )
            )
        # except Exception justified: event bus must never break calibration flow.
        except Exception as exc:
            log.warning(
                "live_calibration_coordinator.polygon_source.publish_failed",
                error=str(exc),
            )

    def clear_last_polygon_source(self) -> None:
        """Reset the polygon-source tag (e.g. after a session is registered)."""
        self._set_last_polygon_source(None)

    # =============================================================================
    # ZONE VALIDATION
    # =============================================================================

    def ensure_zones_before_recording(self) -> bool:  # noqa: C901
        """Ensure project zones are defined before starting recording.

        New implementation uses ZoneCalibrationDialog and ZoneReuseDialog
        for enhanced user experience.

        Returns:
            True if recording can proceed, False if cancelled or waiting for zones
        """
        if not self.project_manager.project_path:
            return True

        project_type = self.project_manager.get_project_type()

        # Only apply special flow for live projects
        if project_type != "live":
            return self._ensure_zones_non_live()

        # === LIVE PROJECT ZONE FLOW ===

        zone_data = self.project_manager.get_zone_data()
        has_zones: bool = bool(zone_data and zone_data.polygon)

        # 1. If zones exist and this is not first recording, ask if want to reuse
        if has_zones and self._has_recorded_before():
            from zebtrack.ui.dialogs.zone_reuse_dialog import ZoneReuseDialog

            if not self.root:
                log.warning("live_calibration_coordinator.zones.no_root_for_reuse_dialog")
                # Default to reusing if can't show dialog
                return True

            dialog = ZoneReuseDialog(
                parent=self.root,
                zone_data=zone_data,
                project_manager=self.project_manager,
            )

            result = dialog.show()

            if result and result.get("reuse"):
                log.info("live_calibration_coordinator.zones.reused")
                # Em vez de iniciar a sessão imediatamente, abrir a aba de
                # zonas com o polígono reutilizado pré-selecionado para que o
                # usuário possa arrastá-lo inteiro e corrigir flutuações da
                # nova posição da câmera. A gravação só começa quando ele
                # clicar em "Iniciar Gravação" (replay com zones_validated=True).
                # Espelha o fluxo de auto-detecção (sucesso) abaixo, mas sem
                # re-detectar — apenas captura um frame de referência fresco.
                if not self._capture_reference_frame_for_zones():
                    log.warning("live_calibration_coordinator.zones.reuse_reference_frame_failed")

                if self.event_bus:
                    self.event_bus.publish(
                        Event(
                            type=UIEvents.UI_SELECT_TAB,
                            data=payloads.UISelectTabPayload(tab_name="zone_tab"),
                        )
                    )
                    self.event_bus.publish(
                        Event(
                            type=UIEvents.UI_UPDATE_ZONE_LIST,
                            data=payloads.EmptyPayload(),
                        )
                    )
                    self.event_bus.publish(
                        Event(
                            type=UIEvents.UI_REDRAW_ZONES,
                            data=payloads.ZonesUpdatedPayload(zone_data=None),
                        )
                    )

                    # Deferir a entrada em modo de edição por ~150 ms (mesmo
                    # motivo das linhas do fluxo auto: deixar o frame de
                    # referência terminar de renderizar antes de
                    # ``setup_interactive_polygon``). ``preselect_all=True``
                    # faz todos os vértices surgirem já selecionados.
                    try:
                        polygon = (zone_data.polygon if zone_data else None) or []
                        bus = self.event_bus
                        if polygon and bus is not None:
                            import numpy as np

                            _event = Event(
                                type=UIEvents.POLYGON_EDIT_REQUESTED,
                                data=payloads.PolygonEditRequestedPayload(
                                    polygon=np.array(polygon),
                                    preselect_all=True,
                                ),
                                source="LiveCalibrationCoordinator.reuse_zones",
                            )

                            def _publish_reuse_edit(event=_event, _bus=bus):
                                _bus.publish(event)
                                log.info(
                                    "live_calibration_coordinator.reuse_edit_mode.triggered",
                                )

                            root = getattr(self, "root", None) or getattr(
                                getattr(self, "view", None), "root", None
                            )
                            if root is not None and hasattr(root, "after"):
                                root.after(150, _publish_reuse_edit)
                            else:
                                bus.publish(_event)
                    # except Exception justified: edit-mode setup must never
                    # break the reuse flow; user can still adjust manually.
                    except Exception:
                        log.debug(
                            "live_calibration_coordinator.reuse_edit_mode.failed",
                            exc_info=True,
                        )

                    self.event_bus.publish(
                        Event(
                            type=UIEvents.UI_SHOW_INFO,
                            data=payloads.MessagePayload(
                                title="Ajustar Polígono",
                                message=(
                                    "Polígono reutilizado. Todos os vértices já estão "
                                    "selecionados.\n\n"
                                    "Arraste o polígono para corrigir a posição na nova "
                                    "imagem e clique em 'Iniciar Gravação' quando estiver "
                                    "pronto."
                                ),
                            ),
                        )
                    )

                # Defere o início da sessão até o usuário confirmar na aba de
                # zonas. Seta pending_zone_confirmation=True → block_detail trata
                # success=False como deferred (sem messagebox de erro).
                return self._wait_for_zone_confirmation()

            # Audit Erro 7 round 4 (2026-05-25): when user picks "Redefinir"
            # in ZoneReuseDialog we must actively wipe the existing zones
            # so the branch below (which depends on ``has_zones``) opens
            # ZoneCalibrationDialog → triggers a fresh autodetection. The
            # previous code just commented "continue to redefinition flow"
            # but never cleared ``has_zones``, so the condition stayed False
            # and the function fell through to ``return None`` (cancel).
            if result is not None and not result.get("reuse"):
                log.info("live_calibration_coordinator.zones.redefining")
                # Clear in-memory zones so the next condition opens the
                # calibration dialog. Use the active zone video key so the
                # zones_by_video entry is wiped along with the global
                # detection_zones (preserved by clear_zone_data_for_video).
                try:
                    active_video = self.project_manager.get_active_zone_video()
                    if active_video:
                        self.project_manager.clear_zone_data_for_video(active_video, persist=True)
                    # Also clear the global so has_zones below evaluates False.
                    pd = self.project_manager.project_data
                    if isinstance(pd, dict):
                        pd["detection_zones"] = {
                            "polygon": [],
                            "roi_polygons": [],
                            "roi_names": [],
                            "roi_colors": [],
                            "metadata": {},
                        }
                # except Exception justified: defensive — clearing must not
                # cancel the redefinition path.
                except Exception:
                    log.warning(
                        "live_calibration_coordinator.zones.redefine_clear_failed",
                        exc_info=True,
                    )
                # Recompute the gate so the calibration-dialog branch below runs.
                has_zones = False

        # 2. Ask user how to define zones (auto vs manual)
        if not has_zones or (has_zones and not self._has_recorded_before()):
            # First time or zones don't exist
            from zebtrack.ui.dialogs.zone_calibration_dialog import ZoneCalibrationDialog

            if not self.root:
                log.error("live_calibration_coordinator.zones.no_root_for_calibration_dialog")
                return False

            calibration_dialog = ZoneCalibrationDialog(parent=self.root)
            calibration_result = calibration_dialog.show()

            if not calibration_result:
                # User cancelled
                log.info("live_calibration_coordinator.zones.cancelled_by_user")
                return False

            method = calibration_result.get("method")

            # 3a. AUTO-DETECTION
            if method == "auto":
                log.info("live_calibration_coordinator.zones.attempting_auto_detection")

                # IMPORTANT: Use 30 frames for camera exposure adjustment
                # (not just aquarium detection)
                success = self.run_live_calibration(stabilization_frames=30, show_preview=True)

                if success:
                    # Polygon source ("auto" vs "manual") is recorded inside
                    # ``run_live_calibration`` based on whether the user dragged
                    # a vertex in the PreviewPolygonDialog. No override here.
                    # Navigate to zone tab to allow adjustments/ROIs.
                    if self.event_bus:
                        self.event_bus.publish(
                            Event(
                                type=UIEvents.UI_SELECT_TAB,
                                data=payloads.UISelectTabPayload(tab_name="zone_tab"),
                            )
                        )
                        # Refresh the zone tab so the auto-detected polygon and
                        # toolbar (ROIs / Concluir) materialise. Mirrors the
                        # manual flow below — without this event the canvas
                        # renders the reference frame but never replays the
                        # zone collection ``save_zone_data`` just persisted,
                        # leaving the user looking at a blank polygon.
                        self.event_bus.publish(
                            Event(
                                type=UIEvents.UI_UPDATE_ZONE_LIST,
                                data=payloads.EmptyPayload(),
                            )
                        )
                        # Audit Erro 7 round 4 (2026-05-25): UI_UPDATE_ZONE_LIST
                        # only refreshes the SIDEBAR listbox; the polygon
                        # overlay over the reference frame needs an explicit
                        # UI_REDRAW_ZONES so ``renderer.redraw_zones`` runs.
                        # Without this the user sees the new frame WITHOUT the
                        # auto-detected polygon and assumes detection failed.
                        self.event_bus.publish(
                            Event(
                                type=UIEvents.UI_REDRAW_ZONES,
                                data=payloads.ZonesUpdatedPayload(zone_data=None),
                            )
                        )

                        # Audit Erro 9 round 4 (2026-05-25): immediately enter
                        # polygon vertex-edit mode on the auto-detected arena
                        # so the user can refine drag/snap vertices without
                        # having to right-click → "Editar polígono". Mirrors
                        # the manual edit flow in zone_editor.py:447-466.
                        #
                        # Audit Erro 9 round 6 (2026-05-25): defer the
                        # POLYGON_EDIT_REQUESTED publish by ~150 ms via
                        # ``root.after`` so the UI_REDRAW_ZONES event above
                        # finishes its render cycle FIRST. Without this gap,
                        # ``setup_interactive_polygon`` could land on a canvas
                        # that hasn't received its background frame yet,
                        # leaving the user with draggable vertices floating on
                        # a blank canvas (item B9). The deferral is short
                        # enough that the user perceives no lag but long
                        # enough for Tk to flush a redraw.
                        try:
                            zone_data = self.project_manager.get_zone_data()
                            polygon = (zone_data.polygon if zone_data else None) or []
                            # Bind event_bus to a local so the deferred
                            # closure has a non-None reference (mypy cannot
                            # narrow ``self.event_bus`` inside a nested
                            # function — CI lint fix, PR #388).
                            bus = self.event_bus
                            if polygon and bus is not None:
                                import numpy as np

                                _event = Event(
                                    type=UIEvents.POLYGON_EDIT_REQUESTED,
                                    data=payloads.PolygonEditRequestedPayload(
                                        polygon=np.array(polygon)
                                    ),
                                    source="LiveCalibrationCoordinator.auto_detect.success",
                                )

                                def _publish_polygon_edit(event=_event, _bus=bus):
                                    _bus.publish(event)
                                    log.info(
                                        "live_calibration_coordinator.auto_edit_mode.triggered_deferred",
                                    )

                                root = getattr(self, "root", None) or getattr(
                                    getattr(self, "view", None), "root", None
                                )
                                if root is not None and hasattr(root, "after"):
                                    root.after(150, _publish_polygon_edit)
                                    log.info(
                                        "live_calibration_coordinator.auto_edit_mode.scheduled",
                                        delay_ms=150,
                                        polygon_vertices=len(polygon),
                                    )
                                else:
                                    # Fallback: publish synchronously when no
                                    # Tk root is wired (tests / headless).
                                    bus.publish(_event)
                                    log.info(
                                        "live_calibration_coordinator.auto_edit_mode.triggered",
                                        polygon_vertices=len(polygon),
                                    )
                        except Exception:
                            log.debug(
                                "live_calibration_coordinator.auto_edit_mode.failed",
                                exc_info=True,
                            )
                        self.event_bus.publish(
                            Event(
                                type=UIEvents.UI_SHOW_INFO,
                                data=payloads.MessagePayload(
                                    title="Aquário Detectado",
                                    message=(
                                        "Aquário detectado com sucesso!\n\n"
                                        "Você pode ajustar os vértices ou adicionar ROIs.\n"
                                        "Clique em 'Concluir' quando estiver pronto."
                                    ),
                                ),
                            )
                        )

                    # Wait for user confirmation
                    return self._wait_for_zone_confirmation()
                elif self._last_calibration_cancelled:
                    # User explicitly closed/rejected the preview dialog — do
                    # NOT fall through to manual mode and do NOT navigate to
                    # the zone tab. Abort cleanly so the wizard step stays
                    # where it was. The camera was already released by
                    # ``run_live_calibration``.
                    log.info("live_calibration_coordinator.zones.user_cancelled_auto_detect")
                    return False
                else:
                    # Detection failed for non-cancellation reasons (camera
                    # init failure, no polygon detected, model exception…).
                    # Inform the user and fall through to manual drawing.
                    if self.event_bus:
                        self.event_bus.publish(
                            Event(
                                type=UIEvents.UI_SHOW_ERROR,
                                data=payloads.ErrorOccurredPayload(
                                    title="Detecção Falhou",
                                    message=(
                                        "Não foi possível detectar o aquário automaticamente.\n\n"
                                        "Você será levado para a aba de zonas para desenhar "
                                        "manualmente."
                                    ),
                                ),
                            )
                        )

                    # Fallback to manual
                    method = "manual"

            # 3b. MANUAL DRAWING (or fallback from auto) → tag as manual
            if method == "manual":
                log.info("live_calibration_coordinator.zones.manual_mode")
                self._set_last_polygon_source("manual")

                # Capture reference frame
                if not self._capture_reference_frame_for_zones():
                    log.error("live_calibration_coordinator.zones.reference_frame_failed")
                    return False

                # Navigate to zone tab
                if self.event_bus:
                    self.event_bus.publish(
                        Event(
                            type=UIEvents.UI_SELECT_TAB,
                            data=payloads.UISelectTabPayload(tab_name="zone_tab"),
                        )
                    )

                    # ⚠️ FIX BUG #7: Don't publish UI_REDRAW_ZONES immediately after
                    # UI_DISPLAY_VIDEO_FRAME because redraw_zones() might be called
                    # before display_roi_video_frame() completes setting the active video.
                    # The image display event handler will redraw zones after loading.

                    # Only update zone list (not redraw - that happens after image loads)
                    self.event_bus.publish(
                        Event(
                            type=UIEvents.UI_UPDATE_ZONE_LIST,
                            data=payloads.EmptyPayload(),
                        )
                    )

                    self.event_bus.publish(
                        Event(
                            type=UIEvents.UI_SHOW_INFO,
                            data=payloads.MessagePayload(
                                title="Desenhe o Aquário",
                                message=(
                                    "Desenhe o polígono do aquário e ROIs (se necessário).\n\n"
                                    "Clique em 'Concluir' quando estiver pronto."
                                ),
                            ),
                        )
                    )

                # Wait for confirmation
                return self._wait_for_zone_confirmation()

        return False

    def _ensure_zones_non_live(self) -> bool:
        """Handle zone validation for non-live projects.

        Extracted from original _ensure_zones_before_recording logic.
        """
        zone_data = self.project_manager.get_zone_data()

        if not zone_data or not zone_data.polygon:
            log.warning("live_calibration_coordinator.recording.no_main_arena")

            if not self.view:
                return False

            response = self.view.dialog_manager.ask_ok_cancel(
                "Arena Principal Não Definida",
                "O polígono principal do aquário não foi definido.\n\n"
                "É recomendado definir a arena antes de iniciar gravação.\n"
                "Deseja definir agora?",
            )

            if response:
                if self.event_bus:
                    self.event_bus.publish(
                        Event(
                            type=UIEvents.UI_SELECT_TAB,
                            data=payloads.UISelectTabPayload(tab_name="zone_tab"),
                        )
                    )
                    self.event_bus.publish(
                        Event(
                            type=UIEvents.UI_SHOW_INFO,
                            data=payloads.MessagePayload(
                                title="Defina a Arena Principal",
                                message=(
                                    "Por favor:\n"
                                    "1. Use a câmera ao vivo para calibrar\n"
                                    "2. Use 'Detectar Aquário (Auto)' ou\n"
                                    "3. Desenhe manualmente o polígono principal\n"
                                    "4. Depois volte para iniciar a gravação"
                                ),
                            ),
                        )
                    )
                return False
            else:
                # Continue without arena defined
                if not self.view.dialog_manager.ask_ok_cancel(
                    "Continuar Sem Arena?",
                    "Deseja continuar a gravação sem arena definida?\n"
                    "(A arena padrão será o frame completo)",
                ):
                    log.info("live_calibration_coordinator.recording.cancelled_no_arena")
                    return False

                log.info("live_calibration_coordinator.recording.proceeding_without_arena")

        return True

    # =============================================================================
    # LIVE CALIBRATION
    # =============================================================================

    def run_live_calibration(  # noqa: C901
        self, stabilization_frames: int = 10, show_preview: bool = True
    ) -> bool:
        """Execute live aquarium calibration with auto-detection.

        Args:
            stabilization_frames: Number of frames to capture (default: 10)
            show_preview: If True, shows preview dialog for approval

        Returns:
            True if calibration successful, False otherwise
        """
        import time  # For delays between camera operations

        log.info("live_calibration_coordinator.live_calibration.start")
        # Reset the cancellation flag so a previous cancel doesn't leak into
        # this run's interpretation. The flag is only set to True on the
        # user-rejected path below.
        self._last_calibration_cancelled = False

        # Audit Erro 4 (2026-05-25): wipe any polygon that a previous live
        # session persisted under the static ``live_camera_reference_frame.png``
        # key in ``zones_by_video``, UNLESS the user explicitly opted into
        # template reuse for the next autodetections. Without this, a
        # concluded polygon from a past video would render on the canvas the
        # moment we publish UI_DISPLAY_VIDEO_FRAME for the new burst's
        # reference frame, giving the impression that detection "remembered"
        # the old shape.
        try:
            pre_run_project_data = self.project_manager.project_data or {}
            template_present = bool(
                (pre_run_project_data.get("arena_template") or {}).get("polygon")
            )
            if not template_present:
                ref_key = os.path.join(
                    str(self.project_manager.project_path or ""),
                    "live_camera_reference_frame.png",
                )
                zones_map = pre_run_project_data.get("zones_by_video", {})
                if ref_key in zones_map:
                    del zones_map[ref_key]
                    log.info(
                        "live_calibration_coordinator.stale_polygon.cleared",
                        ref_key=ref_key,
                    )
        except Exception:
            log.debug(
                "live_calibration_coordinator.stale_polygon.clear_failed",
                exc_info=True,
            )

        # Initialize camera if necessary
        if not self.camera or not hasattr(self.camera, "is_open") or not self.camera.is_open:
            try:
                # Use camera_index from project if available (for live projects)
                project_data = self.project_manager.project_data or {}
                camera_index = project_data.get("camera_index")

                if camera_index is not None:
                    # Temporarily override settings to use project camera
                    original_index = self.settings.camera.index
                    self.settings.camera.index = camera_index
                    self.camera = Camera(settings_obj=self.settings)
                    self.settings.camera.index = original_index  # Restore
                    log.info(
                        "live_calibration_coordinator.live_calibration.camera_initialized",
                        camera_index=camera_index,
                        source="project",
                    )
                else:
                    # Fallback to global settings
                    self.camera = Camera(settings_obj=self.settings)
                    log.info(
                        "live_calibration_coordinator.live_calibration.camera_initialized",
                        camera_index=self.settings.camera.index,
                        source="global",
                    )
            except (OSError, RuntimeError) as e:
                log.error(
                    "live_calibration_coordinator.live_calibration.camera_init_failed",
                    error=str(e),
                )
                return False

            # Warmup camera
            time.sleep(1.5)

        # Capture frames for stabilization
        frames = []
        for i in range(stabilization_frames):
            ret, frame = self.camera.get_frame()
            if not ret or frame is None:
                log.warning(
                    "live_calibration_coordinator.live_calibration.frame_capture_failed",
                    frame_num=i,
                )
                time.sleep(0.2)  # Wait before retry
                continue
            frames.append(frame)
            time.sleep(0.1)

        if len(frames) < stabilization_frames // 2:
            log.error(
                "live_calibration_coordinator.live_calibration.insufficient_frames",
                captured=len(frames),
            )
            self._release_calibration_camera(reason="insufficient_frames")
            return False

        # Auto-detect aquarium using configured model

        # Determine detection method (det/seg) from configuration
        method = "det"  # Default fallback

        # 1. Try project config
        project_data = self.project_manager.project_data or {}
        if "model_selection" in project_data:
            method = project_data["model_selection"].get("aquarium_method", method)

        # 2. Try global settings
        elif self.settings and hasattr(self.settings, "model_selection"):
            method = self.settings.model_selection.aquarium_method

        log.info("live_calibration_coordinator.live_calibration.method_selected", method=method)

        # Resolve perspective from project config for weight selection.
        # The wizard persists behavioral data under ``project_data["behavioral_config"]``
        # via ``ProjectWorkflowService._persist_project_data`` — that's the
        # canonical location. The nested ``calibration.behavioral_analysis``
        # layout is only used by some legacy project files / templates and
        # is kept as a fallback so older saved projects still resolve their
        # perspective correctly here.
        perspective: str | None = None
        bc_data = project_data.get("behavioral_config") or {}
        perspective = bc_data.get("aquarium_perspective") or None
        if perspective is None:
            cal_data = project_data.get("calibration") or {}
            ba_data = cal_data.get("behavioral_analysis") or {}
            perspective = ba_data.get("aquarium_perspective") or None

        # Get model path for aquarium detection (perspective-aware)
        model_path = self.weight_manager.get_weight_path_by_method(
            method=method,
            task="aquarium",
            perspective=perspective,
        )
        if not model_path:
            log.error(
                "live_calibration_coordinator.live_calibration.no_aquarium_model", method=method
            )
            self._release_calibration_camera(reason="no_aquarium_model")
            return False

        detector = AquariumDetector(model_path=model_path, mode=method)

        # Resolve initial confidence from settings (DI) — same value seeds the
        # PreviewPolygonDialog slider so the user can adjust + retry live.
        try:
            initial_confidence = float(
                getattr(self.settings.yolo_model, "confidence_threshold", 0.05) or 0.05
            )
        except AttributeError:
            initial_confidence = 0.05

        # Cache references for retry callback (re-captures + re-detects with new conf).
        self._calibration_detector = detector
        self._calibration_initial_confidence = initial_confidence
        preserve_real_shape = bool(project_data.get("preserve_real_aquarium_shape", False))
        self._calibration_preserve_real_shape = preserve_real_shape

        # Audit Erro 4 (2026-05-25): if the user previously opted into
        # "Reaproveitar este polígono em próximas autodetecções", reuse the
        # saved template polygon as the detection output. The user still
        # sees the preview dialog and can fine-tune it for this video.
        template = project_data.get("arena_template") or {}
        template_polygon = template.get("polygon") if isinstance(template, dict) else None
        if template_polygon:
            log.info(
                "live_calibration_coordinator.live_calibration.template_reused",
                points=len(template_polygon),
            )
            detected_polygons = [[list(point) for point in template_polygon]]
        else:
            try:
                detected_polygons = self._detect_polygon_on_burst(
                    detector=detector,
                    frames=frames,
                    confidence=initial_confidence,
                    preserve_real_shape=preserve_real_shape,
                )

            except Exception as e:  # except Exception justified: ML inference heterogeneous errors
                log.error(
                    "live_calibration_coordinator.live_calibration.detection_failed",
                    error=str(e),
                    exc_info=True,
                )

                self._release_calibration_camera(reason="detection_exception")

                # Fallback: Save and display the last captured frame for manual drawing
                if frames:
                    try:
                        reference_path = os.path.join(
                            str(self.project_manager.project_path or ""),
                            "live_camera_reference_frame.png",
                        )
                        cv2.imwrite(reference_path, frames[-1])

                        if self.event_bus:
                            self.event_bus.publish(
                                Event(
                                    type=UIEvents.UI_DISPLAY_VIDEO_FRAME,
                                    data=VideoPathPayload(video_path=reference_path),
                                )
                            )
                            self.event_bus.publish(
                                Event(
                                    type=UIEvents.UI_SHOW_WARNING,
                                    data=payloads.MessagePayload(
                                        title="Erro na Detecção",
                                        message=(
                                            f"Erro durante a detecção automática: {e!s}\n\n"
                                            "A imagem capturada foi carregada para desenho manual."
                                        ),
                                    ),
                                )
                            )
                    except OSError as fallback_err:
                        log.error(
                            "live_calibration_coordinator.live_calibration.fallback_failed",
                            error=str(fallback_err),
                        )

                return False

        if not detected_polygons or len(detected_polygons) == 0:
            log.warning("live_calibration_coordinator.live_calibration.no_polygon_detected")

            self._release_calibration_camera(reason="no_polygon_detected")

            # Fallback: Save and display the last captured frame for manual drawing
            if frames:
                try:
                    reference_path = os.path.join(
                        str(self.project_manager.project_path or ""),
                        "live_camera_reference_frame.png",
                    )
                    cv2.imwrite(reference_path, frames[-1])

                    if self.event_bus:
                        self.event_bus.publish(
                            Event(
                                type=UIEvents.UI_DISPLAY_VIDEO_FRAME,
                                data=VideoPathPayload(video_path=reference_path),
                            )
                        )
                        self.event_bus.publish(
                            Event(
                                type=UIEvents.UI_SHOW_WARNING,
                                data=payloads.MessagePayload(
                                    title="Detecção Automática Falhou",
                                    message=(
                                        "Não foi possível detectar o aquário automaticamente.\n\n"
                                        "A imagem capturada foi carregada para desenho manual.\n"
                                        "Por favor, use a ferramenta 'Polígono Principal' "
                                        "para definir a arena."
                                    ),
                                ),
                            )
                        )
                except OSError as e:
                    log.error(
                        "live_calibration_coordinator.live_calibration.fallback_failed",
                        error=str(e),
                    )

            return False

        polygon = detected_polygons[0]
        log.info(
            "live_calibration_coordinator.live_calibration.polygon_detected",
            vertices=len(polygon),
        )

        # Preview and approval
        approved = False
        if show_preview:
            if not self.root:
                log.warning("live_calibration_coordinator.live_calibration.no_root_for_preview")
                # Auto-approve if no root window available
                approved = True
            else:
                from zebtrack.ui.dialogs.preview_polygon_dialog import PreviewPolygonDialog

                # Use last captured frame as background
                preview_frame = frames[-1]

                dialog = PreviewPolygonDialog(
                    parent=self.root,
                    frame=preview_frame,
                    polygon=[
                        [float(p[0]), float(p[1])] for p in polygon
                    ],  # Convert to float for dialog
                    initial_confidence=initial_confidence,
                    on_retry=self._retry_aquarium_detection,
                )

                result = dialog.show()
                if result:
                    approved = result.get("approved", False)
                    if approved:
                        # Use polygon (and possibly frame) returned by dialog —
                        # may differ from the original if user adjusted the slider
                        # and retried, OR dragged individual vertices before
                        # approving.
                        polygon = result.get("polygon", polygon)
                        retried_frame = result.get("frame")
                        if retried_frame is not None:
                            frames[-1] = retried_frame
                        # Persist polygon provenance for downstream consumers
                        # (LiveCameraSessionCoordinator publishes it on
                        # LIVE_RECORDING_PENDING). "manual" iff the user
                        # dragged at least one vertex in the dialog.
                        self._set_last_polygon_source(result.get("source", "auto"))

                if not approved:
                    log.info("live_calibration_coordinator.live_calibration.user_rejected")
                    # Distinguish explicit cancellation from genuine detection
                    # failure so the caller doesn't fall through to manual
                    # drawing mode against the user's intent.
                    self._last_calibration_cancelled = True
                    self._release_calibration_camera(reason="user_rejected")
                    return False
        else:
            # No preview requested, auto-approve
            approved = True

        # Save detected zone if approved
        if approved:
            from zebtrack.core.project.zone_manager import ZoneData

            metadata = {
                "detection_method": "auto",
                "stabilization_frames": stabilization_frames,
                "timestamp": datetime.datetime.now().isoformat(),
                "width_cm": None,
                "height_cm": None,
            }

            # Ensure polygon is int for ZoneData
            int_polygon = [[int(p[0]), int(p[1])] for p in polygon]

            zone_data = ZoneData(
                polygon=int_polygon,
                metadata=metadata,
            )

            # Save reference frame to disk so the Zone tab canvas can load it.
            reference_frame_path = os.path.join(
                str(self.project_manager.project_path or ""), "live_camera_reference_frame.png"
            )
            cv2.imwrite(reference_frame_path, frames[-1])

            # IN-MEMORY ONLY (persist=False) — audit Erro 4 (2026-05-25).
            #
            # Previously this call used the default persist=True AND a second
            # save_zone_data(..., "live_camera") wrote the polygon to a legacy
            # template key. Both calls hit save_project(), so the polygon was
            # persisted to disk *before* the user had any chance to confirm or
            # discard. Reopening the project then showed the ghost polygon on
            # the zone canvas even though nothing had been concluded.
            #
            # The new model: auto-detect populates project_data["detection_zones"]
            # and zones_by_video[reference_frame_path] **in memory** so the
            # canvas and the in-progress recording can use the polygon, but
            # persistence to project.json is deferred to the user's "Concluir
            # Edição do Vídeo" click (which calls save_project()). Cancelling
            # without Concluir leaves nothing on disk.
            self.project_manager.save_zone_data(zone_data, reference_frame_path, persist=False)

            # Push the just-saved frame into the zone tab's canvas. Without
            # this event the polygon renders on a blank/white background
            # because no UI_DISPLAY_VIDEO_FRAME ever fires in the auto-detect
            # path (the manual path emits it from _capture_reference_frame_for_zones).
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_DISPLAY_VIDEO_FRAME,
                        data=VideoPathPayload(video_path=reference_frame_path),
                    )
                )

            log.info(
                "live_calibration_coordinator.live_calibration.success",
                polygon_points=len(polygon),
                reference_frame=reference_frame_path,
            )

            # Release camera so LiveCameraService can use it.
            self._release_calibration_camera(reason="approved")

            # CRITICAL: Allow hardware to fully release camera before LiveCameraService reopens it
            # Without this delay, warmup fails (frames_successful=0) and exposure is incorrect
            time.sleep(0.5)

            return True

        # Defensive: every non-approved code path above already releases the
        # camera and returns early. If control somehow reaches here (e.g.
        # ``approved`` flipped via future refactor), still release so the
        # background thread doesn't leak.
        self._release_calibration_camera(reason="unexpected_fallthrough")
        return False

    # =============================================================================
    # REFERENCE FRAME CAPTURE
    # =============================================================================

    def _capture_reference_frame_for_zones(self) -> bool:
        """Capture frame from camera for zone tab reference."""
        log.info("live_calibration_coordinator.capture_reference_frame.start")

        if not self.camera or not hasattr(self.camera, "is_open") or not self.camera.is_open:
            try:
                # Use camera_index from project if available (for live projects)
                project_data = self.project_manager.project_data or {}
                camera_index = project_data.get("camera_index")

                if camera_index is not None:
                    # Temporarily override settings to use project camera
                    original_index = self.settings.camera.index
                    self.settings.camera.index = camera_index
                    self.camera = Camera(settings_obj=self.settings)
                    self.settings.camera.index = original_index  # Restore
                    log.info(
                        "live_calibration_coordinator.capture_reference_frame.camera_initialized",
                        camera_index=camera_index,
                        source="project",
                    )
                else:
                    # Fallback to global settings
                    self.camera = Camera(settings_obj=self.settings)
                    log.info(
                        "live_calibration_coordinator.capture_reference_frame.camera_initialized",
                        camera_index=self.settings.camera.index,
                        source="global",
                    )
            except (OSError, RuntimeError) as e:
                log.error(
                    "live_calibration_coordinator.capture_reference_frame.camera_init_failed",
                    error=str(e),
                )
                return False

            # CRITICAL: Wait for Camera's background thread to start filling buffer
            # Camera uses background thread to continuously capture frames into buffer.
            # Must wait for first frame to become available before warmup loop.
            log.info(
                "live_calibration_coordinator.capture_reference_frame.waiting_for_thread_start"
            )
            time.sleep(0.5)  # Give background thread time to capture first frame

            # CRITICAL: Warm up camera by discarding first frames
            # Webcams often need time to adjust exposure/white balance
            # Use same logic as LiveCameraService for consistency
            camera_index = camera_index if camera_index is not None else self.settings.camera.index
            warmup_frames = 30 if camera_index <= 1 else 10

            log.info(
                "live_calibration_coordinator.capture_reference_frame.warmup_start",
                camera_index=camera_index,
                warmup_frames=warmup_frames,
            )

            successful_warmup = 0
            for _ in range(warmup_frames):
                ret, frame = self.camera.get_frame()
                if ret and frame is not None:
                    successful_warmup += 1
                time.sleep(0.05)  # 50ms between warmup frames

            log.info(
                "live_calibration_coordinator.capture_reference_frame.warmup_complete",
                frames_requested=warmup_frames,
                frames_successful=successful_warmup,
            )

        # Capture the actual reference frame (after warmup)
        frame = None
        for attempt in range(5):
            ret, captured = self.camera.get_frame()
            if ret and captured is not None:
                frame = captured
                log.info(
                    "live_calibration_coordinator.capture_reference_frame.captured",
                    attempt=attempt + 1,
                )
                break
            time.sleep(0.1)

        if frame is None:
            log.error("live_calibration_coordinator.capture_reference_frame.capture_failed")
            return False

        reference_path = os.path.join(
            str(self.project_manager.project_path or ""), "live_camera_reference_frame.png"
        )
        cv2.imwrite(reference_path, frame)

        if self.event_bus:
            self.event_bus.publish(
                Event(
                    type=UIEvents.UI_DISPLAY_VIDEO_FRAME,
                    data=VideoPathPayload(video_path=reference_path),
                )
            )

        log.info(
            "live_calibration_coordinator.capture_reference_frame.success", path=reference_path
        )

        # Release camera so LiveCameraService can use it
        # IMPORTANT: Must signal shutdown BEFORE release to prevent reconnection attempts
        if self.camera:
            if hasattr(self.camera, "_stopped"):
                self.camera._stopped.set()  # Stop the background thread first
            if hasattr(self.camera, "release"):
                self.camera.release()
            self.camera = None
            log.info("live_calibration_coordinator.capture_reference_frame.camera_released")

        return True

    # =============================================================================
    # HELPER METHODS
    # =============================================================================

    def _has_recorded_before(self) -> bool:
        """True if a recording already exists for this project.

        Considera duas fontes:

        1. ``_session_count`` — gravações feitas NESTA execução do app.
        2. Vídeos já registrados no projeto em disco — para que, ao
           **reabrir** um projeto que já possui gravações (e portanto um
           polígono persistido), o app ofereça o diálogo de **Reutilizar**
           em vez de rodar a auto-detecção novamente. Sem isto, o
           ``_session_count`` (zerado a cada reabertura) fazia o app "esquecer"
           o polígono pré-existente.
        """
        if self._session_count > 0:
            return True
        try:
            return bool(self.project_manager.get_all_videos())
        # except Exception justified: a leitura do projeto não pode quebrar a
        # decisão do fluxo de zonas; na dúvida, comporta-se como "nunca gravou".
        except Exception:
            log.debug(
                "live_calibration_coordinator.has_recorded_before.project_probe_failed",
                exc_info=True,
            )
            return False

    def increment_session_count(self) -> None:
        """Increment the session recording counter.

        Called by RecordingSessionCoordinator and LiveCameraSessionCoordinator
        after successful zone validation.
        """
        self._session_count += 1
        log.info(
            "live_calibration_coordinator.session_count.incremented", count=self._session_count
        )

    def _simplify_polygon(self, raw_polygon: Any) -> list[list[int]]:
        """Reduce the vertex count of a segmentation mask polygon.

        Audit Erro 8 round 4 (2026-05-25): YOLO segmentation masks return
        the raw contour from cv2.findContours, which carries one vertex
        per pixel along the boundary (often 200+ points). Apply
        Douglas-Peucker (``cv2.approxPolyDP``) so downstream consumers
        — the editable polygon canvas, the ArenaROI parquet, the
        recorder's draw_overlay — work with a clean ~6-12 vertex polygon
        that matches what the pre-recorded auto-detect pipeline produces.

        Args:
            raw_polygon: ndarray-like with shape (N, 2); pixel coords.

        Returns:
            Simplified polygon as a list of [x, y] integer pairs.
        """
        import numpy as np

        try:
            contour = np.asarray(raw_polygon, dtype=np.float32).reshape(-1, 1, 2)
            perimeter = float(cv2.arcLength(contour, closed=True))
            if perimeter <= 0:
                return [[int(p[0]), int(p[1])] for p in raw_polygon]

            # Read epsilon factor from settings, fall back to a sensible
            # 0.5% of the perimeter (preserves rectangular aquarium corners
            # while collapsing pixel-jitter along straight edges).
            epsilon_factor = 0.005
            try:
                epsilon_factor = float(
                    getattr(
                        self.settings.yolo_model,
                        "aquarium_polygon_epsilon",
                        epsilon_factor,
                    )
                )
            # except Exception justified: settings access may fail in tests
            # with stripped configs — fall back to default.
            except Exception:
                log.debug(
                    "live_calibration_coordinator.epsilon_settings_fallback",
                    exc_info=True,
                )

            epsilon = max(1.0, epsilon_factor * perimeter)
            approx = cv2.approxPolyDP(contour, epsilon, closed=True)

            if approx is None or len(approx) < 3:
                # Approximation collapsed to <3 points — keep the raw shape.
                return [[int(p[0]), int(p[1])] for p in raw_polygon]

            # ``approx`` from cv2.approxPolyDP has shape (N, 1, 2); each ``pt``
            # is a (1, 2) ndarray. Use explicit indexing flattened via .ravel()
            # so mypy can resolve the dtype without complaining that ``pt[0]``
            # is already a scalar.
            simplified = [[int(pt.ravel()[0]), int(pt.ravel()[1])] for pt in approx]
            log.info(
                "live_calibration_coordinator.polygon_simplified",
                raw_vertices=len(raw_polygon),
                simplified_vertices=len(simplified),
                epsilon_factor=epsilon_factor,
                perimeter_px=round(perimeter, 1),
            )
            return simplified
        except Exception:
            log.warning(
                "live_calibration_coordinator.polygon_simplify_failed",
                exc_info=True,
            )
            return [[int(p[0]), int(p[1])] for p in raw_polygon]

    def _detect_polygon_on_burst(
        self,
        *,
        detector: AquariumDetector,
        frames: list[Any],
        confidence: float,
        preserve_real_shape: bool = False,
    ) -> list[Any]:
        """Run aquarium detection over a captured frame burst.

        Returns a one-element list (compatible with the existing call sites)
        containing the largest valid polygon, or ``[]`` if none meet the
        area-ratio + confidence gates.

        When the underlying YOLO model is a segmentation model (``task == "segment"``)
        AND ``preserve_real_shape`` is True, the mask polygon (N vertices) is kept;
        otherwise a 4-corner bounding box approximation is returned. This matches
        the contract of the pre-recorded pipeline for non-rectangular aquariums.

        Args:
            detector: Already-initialized ``AquariumDetector``.
            frames: Captured frames from the live camera.
            confidence: YOLO ``conf`` value to use for this pass.
            preserve_real_shape: When True and the model is a segmentation model,
                return the multi-vertex mask polygon instead of a 4-corner bbox.
        """
        if not frames:
            return []

        good_polygons: list[list[list[int]]] = []
        frame_height, frame_width = frames[0].shape[:2]
        clamped_conf = max(0.01, min(0.95, float(confidence)))
        is_seg_model = getattr(getattr(detector, "model", None), "task", "") == "segment"
        use_masks = preserve_real_shape and is_seg_model

        for frame in frames:
            try:
                results = detector.model.predict(
                    frame, verbose=False, classes=[0], conf=clamped_conf
                )
            # except Exception justified: Ultralytics predict can raise heterogeneous
            # errors when model/weights/CUDA state is inconsistent — log and try next frame.
            except Exception as exc:
                log.warning(
                    "live_calibration_coordinator.burst_detect.predict_failed",
                    error=str(exc),
                )
                continue

            if not results or not results[0].boxes or len(results[0].boxes) == 0:
                continue

            boxes = results[0].boxes.xyxy.cpu().numpy()  # type: ignore[union-attr]
            areas = [(x2 - x1) * (y2 - y1) for x1, y1, x2, y2 in boxes]
            if not areas:
                continue

            max_idx = areas.index(max(areas))
            x1, y1, x2, y2 = boxes[max_idx]
            box_area = (x2 - x1) * (y2 - y1)
            frame_area = frame_width * frame_height
            area_ratio = (box_area / frame_area) if frame_area > 0 else 0

            if not (0.1 <= area_ratio <= 0.98):
                continue

            polygon_pts: list[list[int]] | None = None

            if use_masks:
                masks = getattr(results[0], "masks", None)
                mask_xy = getattr(masks, "xy", None) if masks is not None else None
                if mask_xy is not None and len(mask_xy) > max_idx:
                    raw_polygon = mask_xy[max_idx]
                    if raw_polygon is not None and len(raw_polygon) >= 3:
                        # Audit Erro 8 round 4 (2026-05-25): apply
                        # Douglas-Peucker (cv2.approxPolyDP) to the raw mask
                        # contour so the aquarium outline doesn't carry the
                        # 200+ vertices YOLO returns. Default epsilon is
                        # 0.5% of the perimeter — preserves corners while
                        # collapsing micro-jitter on the borders. Tunable
                        # via ``settings.yolo_model.aquarium_polygon_epsilon``
                        # (per-project override possible).
                        polygon_pts = self._simplify_polygon(raw_polygon)

                if polygon_pts is None:
                    log.warning(
                        "live_calibration_coordinator.burst_detect.mask_unavailable_fallback",
                        message="Segmentation requested but mask missing; using bbox fallback.",
                    )

            if polygon_pts is None:
                polygon_pts = [
                    [int(x1), int(y1)],
                    [int(x2), int(y1)],
                    [int(x2), int(y2)],
                    [int(x1), int(y2)],
                ]

            good_polygons.append(polygon_pts)

        log.info(
            "live_calibration_coordinator.burst_detect.summary",
            confidence=clamped_conf,
            frames_analyzed=len(frames),
            polygons_found=len(good_polygons),
            preserve_real_shape=preserve_real_shape,
            used_segmentation_masks=use_masks,
        )

        return good_polygons[:1] if good_polygons else []

    def _retry_aquarium_detection(self, confidence: float) -> tuple[Any, list[list[float]]] | None:
        """Retry aquarium auto-detection with a user-chosen confidence threshold.

        Invoked by the PreviewPolygonDialog "🔁 Tentar novamente" button. Captures
        a small frame burst from the live camera and runs detection again with the
        supplied confidence. Pure compute — must NOT touch UI; the dialog owns
        rendering.

        Returns:
            ``(frame, polygon)`` if detection succeeds, otherwise ``None``.
        """
        if self.camera is None or self._calibration_detector is None:
            log.warning(
                "live_calibration_coordinator.retry.no_camera_or_detector",
                has_camera=self.camera is not None,
                has_detector=self._calibration_detector is not None,
            )
            return None

        import time as _time

        frames: list[Any] = []
        for _ in range(5):
            try:
                ret, frame = self.camera.get_frame()
            except (OSError, RuntimeError) as exc:
                log.warning(
                    "live_calibration_coordinator.retry.frame_capture_error",
                    error=str(exc),
                )
                return None
            if ret and frame is not None:
                frames.append(frame)
            _time.sleep(0.05)

        if not frames:
            log.warning("live_calibration_coordinator.retry.no_frames")
            return None

        detected = self._detect_polygon_on_burst(
            detector=self._calibration_detector,
            frames=frames,
            confidence=confidence,
            preserve_real_shape=self._calibration_preserve_real_shape,
        )
        if not detected:
            log.info(
                "live_calibration_coordinator.retry.no_polygon",
                confidence=confidence,
            )
            return None

        polygon = [[float(p[0]), float(p[1])] for p in detected[0]]
        log.info(
            "live_calibration_coordinator.retry.success",
            confidence=confidence,
            polygon_points=len(polygon),
        )
        return (frames[-1], polygon)

    def _wait_for_zone_confirmation(self) -> bool:
        """Wait for user to conclude zone definition."""
        log.info("live_calibration_coordinator.waiting_for_zone_confirmation")
        self._pending_zone_confirmation = True
        return False

    @property
    def pending_zone_confirmation(self) -> bool:
        """Whether we are waiting for zone confirmation."""
        return self._pending_zone_confirmation

    @pending_zone_confirmation.setter
    def pending_zone_confirmation(self, value: bool) -> None:
        """Set the pending zone confirmation flag."""
        self._pending_zone_confirmation = value

    def __repr__(self) -> str:
        """Return string representation of LiveCalibrationCoordinator."""
        return (
            f"<LiveCalibrationCoordinator("
            f"has_camera={self.camera is not None}, "
            f"session_count={self._session_count}"
            f")>"
        )
