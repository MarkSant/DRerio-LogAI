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
from zebtrack.core.aquarium_detector import AquariumDetector
from zebtrack.io.camera import Camera
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.core.detector_service import DetectorService
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.weight_manager import WeightManager
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus import EventBus

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
        event_bus: EventBus | None = None,
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
            event_bus: EventBus for UI notifications (optional)
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

        log.info("live_calibration_coordinator.initialized")

    # =============================================================================
    # ZONE VALIDATION
    # =============================================================================

    def ensure_zones_before_recording(self) -> bool:
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
        has_zones = zone_data and zone_data.polygon

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
                return True
            # If not reusing, continue to redefinition flow

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
                    # Detection successful and approved
                    # Navigate to zone tab to allow adjustments/ROIs
                    if self.event_bus:
                        self.event_bus.publish_event(Events.UI_SELECT_TAB, {"tab_name": "zone_tab"})
                        self.event_bus.publish_event(
                            Events.UI_SHOW_INFO,
                            {
                                "title": "Aquário Detectado",
                                "message": (
                                    "Aquário detectado com sucesso!\n\n"
                                    "Você pode ajustar os vértices ou adicionar ROIs.\n"
                                    "Clique em 'Concluir' quando estiver pronto."
                                ),
                            },
                        )

                    # Wait for user confirmation
                    return self._wait_for_zone_confirmation()
                else:
                    # Detection failed
                    if self.event_bus:
                        self.event_bus.publish_event(
                            Events.UI_SHOW_ERROR,
                            {
                                "title": "Detecção Falhou",
                                "message": (
                                    "Não foi possível detectar o aquário automaticamente.\n\n"
                                    "Você será levado para a aba de zonas para desenhar "
                                    "manualmente."
                                ),
                            },
                        )

                    # Fallback to manual
                    method = "manual"

            # 3b. MANUAL DRAWING (or fallback from auto)
            if method == "manual":
                log.info("live_calibration_coordinator.zones.manual_mode")

                # Capture reference frame
                if not self._capture_reference_frame_for_zones():
                    log.error("live_calibration_coordinator.zones.reference_frame_failed")
                    return False

                # Navigate to zone tab
                if self.event_bus:
                    self.event_bus.publish_event(Events.UI_SELECT_TAB, {"tab_name": "zone_tab"})

                    # ⚠️ FIX BUG #7: Don't publish UI_REDRAW_ZONES immediately after
                    # UI_DISPLAY_VIDEO_FRAME because redraw_zones() might be called
                    # before display_roi_video_frame() completes setting the active video.
                    # The image display event handler will redraw zones after loading.

                    # Only update zone list (not redraw - that happens after image loads)
                    self.event_bus.publish_event(Events.UI_UPDATE_ZONE_LIST, {})

                    self.event_bus.publish_event(
                        Events.UI_SHOW_INFO,
                        {
                            "title": "Desenhe o Aquário",
                            "message": (
                                "Desenhe o polígono do aquário e ROIs (se necessário).\n\n"
                                "Clique em 'Concluir' quando estiver pronto."
                            ),
                        },
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

            response = self.view.ask_ok_cancel(
                "Arena Principal Não Definida",
                "O polígono principal do aquário não foi definido.\n\n"
                "É recomendado definir a arena antes de iniciar gravação.\n"
                "Deseja definir agora?",
            )

            if response:
                if self.event_bus:
                    self.event_bus.publish_event(Events.UI_SELECT_TAB, {"tab_name": "zone_tab"})
                    self.event_bus.publish_event(
                        Events.UI_SHOW_INFO,
                        {
                            "title": "Defina a Arena Principal",
                            "message": (
                                "Por favor:\n"
                                "1. Use a câmera ao vivo para calibrar\n"
                                "2. Use 'Detectar Aquário (Auto)' ou\n"
                                "3. Desenhe manualmente o polígono principal\n"
                                "4. Depois volte para iniciar a gravação"
                            ),
                        },
                    )
                return False
            else:
                # Continue without arena defined
                if not self.view.ask_ok_cancel(
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

        # Get model path for aquarium detection
        model_path = self.weight_manager.get_weight_path_by_method(method=method, task="aquarium")
        if not model_path:
            log.error(
                "live_calibration_coordinator.live_calibration.no_aquarium_model", method=method
            )
            return False

        detector = AquariumDetector(model_path=model_path, mode=method)

        try:
            # Process frames directly (AquariumDetector.detect_aquariums expects video_path)
            # So we'll process frames manually here
            good_polygons = []
            frame_height, frame_width = frames[0].shape[:2] if frames else (0, 0)

            for _, frame in enumerate(frames):
                # Detect aquarium (class 0) with low confidence threshold
                results = detector.model.predict(frame, verbose=False, classes=[0], conf=0.05)

                if results and results[0].boxes and len(results[0].boxes) > 0:
                    # Get the largest detection box
                    boxes = results[0].boxes.xyxy.cpu().numpy()
                    areas = [(x2 - x1) * (y2 - y1) for x1, y1, x2, y2 in boxes]
                    max_idx = areas.index(max(areas)) if areas else 0
                    x1, y1, x2, y2 = boxes[max_idx]

                    # Check area ratio
                    box_area = (x2 - x1) * (y2 - y1)
                    frame_area = frame_width * frame_height
                    area_ratio = box_area / frame_area if frame_area > 0 else 0

                    if 0.1 <= area_ratio <= 0.98:
                        # Convert box to polygon (rectangle corners)
                        polygon = [
                            [int(x1), int(y1)],
                            [int(x2), int(y1)],
                            [int(x2), int(y2)],
                            [int(x1), int(y2)],
                        ]
                        good_polygons.append(polygon)

            detected_polygons = good_polygons[:1] if good_polygons else []

        except Exception as e:  # except Exception justified: ML inference heterogeneous errors
            log.error(
                "live_calibration_coordinator.live_calibration.detection_failed",
                error=str(e),
                exc_info=True,
            )

            # Release camera on exception too
            if self.camera:
                if hasattr(self.camera, "_stopped"):
                    self.camera._stopped.set()
                if hasattr(self.camera, "release"):
                    self.camera.release()
                self.camera = None
                log.info(
                    "live_calibration_coordinator.live_calibration.camera_released_on_exception"
                )

            # Fallback: Save and display the last captured frame for manual drawing
            if frames:
                try:
                    reference_path = os.path.join(
                        str(self.project_manager.project_path or ""),
                        "live_camera_reference_frame.png",
                    )
                    cv2.imwrite(reference_path, frames[-1])

                    if self.event_bus:
                        self.event_bus.publish_event(
                            Events.UI_DISPLAY_VIDEO_FRAME, {"video_path": reference_path}
                        )
                        self.event_bus.publish_event(
                            Events.UI_SHOW_WARNING,
                            {
                                "title": "Erro na Detecção",
                                "message": (
                                    f"Erro durante a detecção automática: {e!s}\n\n"
                                    "A imagem capturada foi carregada para desenho manual."
                                ),
                            },
                        )
                except OSError as fallback_err:
                    log.error(
                        "live_calibration_coordinator.live_calibration.fallback_failed",
                        error=str(fallback_err),
                    )

            return False

        if not detected_polygons or len(detected_polygons) == 0:
            log.warning("live_calibration_coordinator.live_calibration.no_polygon_detected")

            # Release camera when no polygon detected
            if self.camera:
                if hasattr(self.camera, "_stopped"):
                    self.camera._stopped.set()
                if hasattr(self.camera, "release"):
                    self.camera.release()
                self.camera = None
                log.info("live_calibration_coordinator.live_calibration.camera_released_no_polygon")

            # Fallback: Save and display the last captured frame for manual drawing
            if frames:
                try:
                    reference_path = os.path.join(
                        str(self.project_manager.project_path or ""),
                        "live_camera_reference_frame.png",
                    )
                    cv2.imwrite(reference_path, frames[-1])

                    if self.event_bus:
                        self.event_bus.publish_event(
                            Events.UI_DISPLAY_VIDEO_FRAME, {"video_path": reference_path}
                        )
                        self.event_bus.publish_event(
                            Events.UI_SHOW_WARNING,
                            {
                                "title": "Detecção Automática Falhou",
                                "message": (
                                    "Não foi possível detectar o aquário automaticamente.\n\n"
                                    "A imagem capturada foi carregada para desenho manual.\n"
                                    "Por favor, use a ferramenta 'Polígono Principal' "
                                    "para definir a arena."
                                ),
                            },
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
                )

                result = dialog.show()
                if result:
                    approved = result.get("approved", False)
                    if approved:
                        # Use polygon from dialog (in case user wants adjustments in future)
                        polygon = result.get("polygon", polygon)

                if not approved:
                    log.info("live_calibration_coordinator.live_calibration.user_rejected")
                    return False
        else:
            # No preview requested, auto-approve
            approved = True

        # Save detected zone if approved
        if approved:
            from zebtrack.core.zone_manager import ZoneData

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

            video_path = "live_camera"
            # Use ProjectManager to save zone data generically
            self.project_manager.save_zone_data(zone_data, video_path)

            # Save reference frame
            reference_frame_path = os.path.join(
                str(self.project_manager.project_path or ""), "live_camera_reference_frame.png"
            )
            cv2.imwrite(reference_frame_path, frames[-1])

            log.info(
                "live_calibration_coordinator.live_calibration.success",
                polygon_points=len(polygon),
                reference_frame=reference_frame_path,
            )

            # Release camera so LiveCameraService can use it
            # IMPORTANT: Must signal shutdown BEFORE release to prevent reconnection attempts
            if self.camera:
                if hasattr(self.camera, "_stopped"):
                    self.camera._stopped.set()  # Stop the background thread first
                if hasattr(self.camera, "release"):
                    self.camera.release()
                self.camera = None
                log.info("live_calibration_coordinator.live_calibration.camera_released")

            # CRITICAL: Allow hardware to fully release camera before LiveCameraService reopens it
            # Without this delay, warmup fails (frames_successful=0) and exposure is incorrect
            time.sleep(0.5)

            return True

        # Release camera on failure too
        if self.camera:
            if hasattr(self.camera, "_stopped"):
                self.camera._stopped.set()  # Stop the background thread first
            if hasattr(self.camera, "release"):
                self.camera.release()
            self.camera = None
            log.info("live_calibration_coordinator.live_calibration.camera_released_on_failure")

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
            self.event_bus.publish_event(
                Events.UI_DISPLAY_VIDEO_FRAME, {"video_path": reference_path}
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
        """Check if any recording has been made in this session."""
        return self._session_count > 0

    def increment_session_count(self) -> None:
        """Increment the session recording counter.

        Called by RecordingSessionCoordinator and LiveCameraSessionCoordinator
        after successful zone validation.
        """
        self._session_count += 1
        log.info(
            "live_calibration_coordinator.session_count.incremented", count=self._session_count
        )

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
