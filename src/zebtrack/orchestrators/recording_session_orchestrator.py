"""Recording session orchestration logic extracted from MainViewModel.

Sprint 26 - Extracted to reduce MainViewModel complexity.
"""

from __future__ import annotations

import os
import tempfile
import time
from typing import TYPE_CHECKING, Any

import cv2
import structlog

from zebtrack.core.aquarium_detector import AquariumDetector
from zebtrack.core.processing_mode import ProcessingMode
from zebtrack.core.state_manager import StateCategory
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.core.main_view_model import MainViewModel

log = structlog.get_logger()


class RecordingSessionOrchestrator:
    """Orchestrates recording session lifecycle and live camera analysis.

    Extracted from MainViewModel in Sprint 26 to reduce its size.
    Maintains reference to MainViewModel for delegation during gradual extraction.
    """

    def __init__(self, main_view_model: MainViewModel):
        """Initialize with MainViewModel reference.

        Args:
            main_view_model: Reference to MainViewModel for delegation
        """
        self.main_view_model = main_view_model

        # Cache frequently used attributes from MainViewModel
        self.state_manager = main_view_model.state_manager
        self.view = main_view_model.view
        self.root = main_view_model.root
        self.settings = main_view_model.settings
        self.project_manager = main_view_model.project_manager
        self.detector_service = main_view_model.detector_service
        self.ui_event_bus = main_view_model.ui_event_bus
        self.weight_manager = main_view_model.weight_manager

        # Move instance variable from MainViewModel
        self._pending_external_trigger: dict | None = None

    # ========== Phase 1: State Management (87 lines) ==========

    @property
    def recording_service(self):
        return self.main_view_model.recording_service

    @recording_service.setter
    def recording_service(self, value):
        self.main_view_model.recording_service = value

    @property
    def live_camera_service(self):
        return self.main_view_model.live_camera_service

    @live_camera_service.setter
    def live_camera_service(self, value):
        self.main_view_model.live_camera_service = value

    @property
    def recording_coordinator(self):
        return self.main_view_model.recording_coordinator

    @recording_coordinator.setter
    def recording_coordinator(self, value):
        self.main_view_model.recording_coordinator = value

    @property
    def _pending_external_trigger(self):
        return self.main_view_model._pending_external_trigger

    @_pending_external_trigger.setter
    def _pending_external_trigger(self, value):
        self.main_view_model._pending_external_trigger = value

    @property
    def is_recording(self) -> bool:
        """Get recording status from StateManager."""
        return self.state_manager.get_recording_state().is_recording

    @is_recording.setter
    def is_recording(self, value: bool) -> None:
        """Update recording status in StateManager."""
        self.state_manager.update_recording_state(
            source="controller.is_recording_setter",
            is_recording=value,
        )

    def _on_recording_state_changed(
        self, category: StateCategory, key: str, old_value: Any, new_value: Any
    ):
        """Publica eventos de UI em resposta a mudanças no estado de Gravação."""
        if not self.ui_event_bus:
            return
        if key == "is_recording":
            self.ui_event_bus.publish_event(
                Events.UI_UPDATE_BUTTON_STATE,
                {"button_name": "start_rec", "state": "disabled" if new_value else "normal"},
            )
            self.ui_event_bus.publish_event(
                Events.UI_UPDATE_BUTTON_STATE,
                {"button_name": "stop_rec", "state": "normal" if new_value else "disabled"},
            )
        elif key == "arduino_connected":
            port = self.state_manager.get_recording_state().arduino_port
            self.ui_event_bus.publish_event(
                Events.UI_UPDATE_ARDUINO_STATUS, {"connected": new_value, "port": port}
            )

    def _setup_recording_service_callbacks(self) -> None:
        """Set up UI callbacks for RecordingService."""
        if self.recording_service is None:
            return

        # Inject UI callbacks for view updates
        self.recording_service.set_ui_callbacks(
            {
                "show_error": lambda title, msg: self.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR, {"title": title, "message": msg}
                ),
                "update_button_state": lambda btn, state: self.ui_event_bus.publish_event(
                    Events.UI_UPDATE_BUTTON_STATE, {"button_name": btn, "state": state}
                ),
                "set_status": lambda msg: self.ui_event_bus.publish_event(
                    Events.UI_SET_STATUS, {"message": msg}
                ),
                "stop_recording_callback": self.stop_recording,
            }
        )

    def _init_recording_service(self) -> None:
        """
        Initialize RecordingService with dependencies and UI callbacks.

        Phase 2.2: Extracts recording orchestration logic from MainViewModel.

        Note:
        - recorder, state_manager, project_manager are passed as references (will update)
        - arduino_manager is initially None and updated via _sync_recording_service_arduino()
          when setup_arduino() is called.
        """
        # Store controller reference so RecordingService can access current recorder/managers
        from zebtrack.core.recording_service import RecordingService

        self.recording_service = RecordingService(
            controller=self.main_view_model,  # Pass main_view_model to access current recorder/arduino_manager  # noqa: E501
            state_manager=self.state_manager,
            project_manager=self.project_manager,
            root=self.root,
        )

        # Setup UI callbacks
        self._setup_recording_service_callbacks()

        # Initialize LiveCameraService (Phase: Live Camera Analysis)
        if self.main_view_model._live_camera_service_param is None:
            from zebtrack.core.live_camera_service import LiveCameraService

            self.live_camera_service = LiveCameraService(
                controller=self.main_view_model,
                state_manager=self.state_manager,
                project_manager=self.project_manager,
                recording_service=self.recording_service,
                detector_service=self.detector_service,
                root=self.root,
            )
        else:
            self.live_camera_service = self.main_view_model._live_camera_service_param

    # ========== Phase 2: Helpers (37 lines) ==========

    def _clear_external_trigger_wait(self):
        if not self._pending_external_trigger:
            return

        self._pending_external_trigger = None
        self.ui_event_bus.publish_event(Events.UI_CLEAR_EXTERNAL_TRIGGER_NOTICE)
        self.ui_event_bus.publish_event(
            Events.UI_UPDATE_BUTTON_STATE, {"button_name": "start_rec", "state": "normal"}
        )
        self.ui_event_bus.publish_event(
            Events.UI_UPDATE_BUTTON_STATE, {"button_name": "stop_rec", "state": "disabled"}
        )
        self.ui_event_bus.publish_event(Events.UI_SET_STATUS, {"message": "Pronto."})

    def _schedule_recording(
        self,
        context: dict,
        project_data: dict,
        *,
        trigger_source: str,
    ) -> None:
        """
        Schedule a recording session via RecordingCoordinator.

        Sprint 15: Updated to use RecordingCoordinator instead of RecordingService directly.
        """
        # Inject camera dimensions into context
        camera_width = getattr(self.view.camera, "actual_width", None)
        camera_height = getattr(self.view.camera, "actual_height", None)
        context["camera_width"] = camera_width
        context["camera_height"] = camera_height

        coordinator = self.recording_coordinator
        if coordinator is not None:
            try:
                coordinator.start_recording(
                    context=context,
                    project_data=project_data,
                    trigger_source=trigger_source,
                )
                return
            except Exception as exc:  # pragma: no cover - defensive fallback
                log.warning(
                    "controller.recording.coordinator_start_failed",
                    error=str(exc),
                )

        if self.recording_service is None:  # pragma: no cover - should not occur
            raise RuntimeError("RecordingService not available for scheduling")

        self.recording_service.schedule_recording(
            context=context,
            project_data=project_data,
            trigger_source=trigger_source,
        )

    # ========== Phase 3: External Trigger (84 lines) ==========

    def _handle_external_trigger(self, context: dict, arduino_enabled: bool) -> bool:
        """
        Handle external trigger setup for recording.

        Sprint 15: Extracted from start_recording() to reduce complexity (~40 lines → ~15 lines).

        Args:
            context: Recording context with session details
            arduino_enabled: Whether Arduino is available

        Returns:
            bool: True if waiting for trigger (stop processing), False if proceed
        """
        project_data = self.project_manager.project_data or {}
        external_trigger_requested = bool(project_data.get("external_trigger_mode"))

        if external_trigger_requested and not arduino_enabled:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Trigger Externo Indisponível",
                    "message": "O modo de trigger externo exige um Arduino configurado.",
                },
            )
            return True

        if external_trigger_requested and arduino_enabled:
            self._pending_external_trigger = context
            port = context.get("arduino_port", "")
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_EXTERNAL_TRIGGER_NOTICE,
                {
                    "folder_name": context["folder_name"],
                    "day": context["day"],
                    "group": context["group"],
                    "cobaia": context["cobaia"],
                    "port": port,
                },
            )
            self.ui_event_bus.publish_event(
                Events.UI_SET_STATUS,
                {"message": f"Aguardando sinal externo... (porta {port})"},
            )
            return True

        return False

    def trigger_recording(self, event_code: int | None = None):
        """Trigger a pending recording session from external Arduino event.

        Args:
            event_code: Optional Arduino event code that triggered recording.
        """
        if not self._pending_external_trigger:
            log.warning("controller.external_trigger.no_pending", code=event_code)
            return

        context = self._pending_external_trigger
        self._pending_external_trigger = None

        if self.ui_event_bus:
            self.ui_event_bus.publish_event(Events.UI_CLEAR_EXTERNAL_TRIGGER_NOTICE)
        project_data = self.project_manager.project_data or {}
        self._schedule_recording(context, project_data, trigger_source="external")

    def on_arduino_event(self, event_code: int):
        """Handle Arduino event signals for external trigger control.

        Args:
            event_code: Integer code from Arduino (1 for start, 0 for stop).
        """
        log.info("controller.arduino.event_received", code=event_code)
        self.main_view_model.log_arduino_event(f"Evento {event_code} recebido do Arduino.")

        if event_code == 1:
            if self._pending_external_trigger:
                self.main_view_model.log_arduino_event(
                    "Sinal externo recebido. Iniciando gravação..."
                )
                self.main_view_model.trigger_recording(event_code)
            else:
                log.warning("controller.arduino.event.unexpected_start")
        elif event_code == 0:
            if self.is_recording or self._pending_external_trigger:
                self.main_view_model.log_arduino_event("Sinal externo solicitando parada.")
                self.stop_recording()
        else:
            log.info("controller.arduino.event.ignored", code=event_code)

    # ========== Phase 4: Core Recording (150 lines) ==========

    def _ensure_zones_before_recording(self) -> bool:
        """Ensure project zones are defined (live or non-live) before starting recording.

        Returns True if recording can proceed, False if it should be cancelled.
        """
        # Enhanced zone validation for Live projects
        if self.project_manager.project_path:
            project_type = self.project_manager.get_project_type()
            zone_data = self.project_manager.get_zone_data()

            if project_type == "live" and (not zone_data or not zone_data.polygon):
                log.info("controller.recording.live_zone_validation.start")

                # For Live projects, prompt for automatic calibration
                response = self.view.ask_ok_cancel(
                    "Calibração Necessária",
                    "Deseja fazer calibração automática do aquário?\n"
                    "(Recomendado para projetos ao vivo)",
                )

                if response:
                    # Run auto-calibration
                    self.run_live_calibration()

                    # Check if calibration was successful
                    zone_data = self.project_manager.get_zone_data()
                    if not zone_data or not zone_data.polygon:
                        self.ui_event_bus.publish_event(
                            Events.UI_SHOW_ERROR,
                            {
                                "title": "Calibração Falhou",
                                "message": "Não foi possível detectar o aquário.\nPor favor, desenhe manualmente.",  # noqa: E501
                            },
                        )
                        # Switch to zones tab
                        self.ui_event_bus.publish_event(
                            Events.UI_SELECT_TAB, {"tab_name": "zone_tab"}
                        )
                        return False
                    else:
                        log.info("controller.recording.live_zone_validation.success")
                else:
                    # User declined calibration
                    self.ui_event_bus.publish_event(
                        Events.UI_SHOW_ERROR,
                        {
                            "title": "Zonas Obrigatórias",
                            "message": "Projetos ao vivo requerem definição de zonas.\n"
                            "Defina o polígono principal antes de gravar.",
                        },
                    )
                    return False

            elif not zone_data or not zone_data.polygon:
                # Generic validation for non-Live projects (preserve existing behavior)
                log.warning("controller.recording.no_main_arena")

                response = self.view.ask_ok_cancel(
                    "Arena Principal Não Definida",
                    "O polígono principal do aquário não foi definido.\n\n"
                    "É recomendado definir a arena antes de iniciar gravação.\n"
                    "Deseja definir agora?",
                )

                if response:
                    # Muda para aba de zonas e inicia câmera para calibração
                    self.ui_event_bus.publish_event(Events.UI_SELECT_TAB, {"tab_name": "zone_tab"})

                    self.ui_event_bus.publish_event(
                        Events.UI_SHOW_INFO,
                        {
                            "title": "Defina a Arena Principal",
                            "message": "Por favor:\n"
                            "1. Use a câmera ao vivo para calibrar\n"
                            "2. Use 'Detectar Aquário (Auto)' ou\n"
                            "3. Desenhe manualmente o polígono principal\n"
                            "4. Depois volte para iniciar a gravação",
                        },
                    )
                    return False
                else:
                    # Continua sem arena definida (usando padrão)
                    if not self.view.ask_ok_cancel(
                        "Continuar Sem Arena?",
                        "Deseja continuar a gravação sem arena definida?\n"
                        "(A arena padrão será o frame completo)",
                    ):
                        log.info("controller.recording.cancelled_no_arena")
                        return False

                    log.info("controller.recording.proceeding_without_arena")

        return True

    def start_recording(
        self, day: int | None = None, group: str | None = None, cobaia: str | None = None, **kwargs
    ):
        """
        Start a recording session (live mode) with zone validation.

        Sprint 15: Simplified by extracting external trigger logic.
        """
        log.info("controller.recording.start", extra_args=kwargs)

        self.project_manager.set_active_zone_video(None)
        self._clear_external_trigger_wait()

        if not self._ensure_zones_before_recording():
            return

        if not self.main_view_model.detector and not self.main_view_model.setup_detector():
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro", "message": "Falha ao configurar detector."},
            )
            return

        self.main_view_model.setup_detector_zones()

        # Get recording details
        if not all((day, group, cobaia)):
            details = self.view.ask_recording_details_unified()
            if not details:
                log.warning("controller.recording.cancelled_by_user")
                return
            day, group, cobaia = details["day"], details["group"], details["cobaia"]

        # Save session details
        self.project_manager.save_last_session_details(day, group)

        # Create output folder
        folder_name = f"D{day}_G{group}_S{cobaia}"
        output_folder = os.path.join(self.project_manager.project_path, folder_name)
        os.makedirs(output_folder, exist_ok=True)

        # Setup Arduino if needed
        project_data = self.project_manager.project_data or {}
        arduino_enabled = bool(
            project_data.get("use_arduino") and self.main_view_model.setup_arduino()
        )

        # Build recording context
        context = {
            "day": day,
            "group": group,
            "cobaia": cobaia,
            "folder_name": folder_name,
            "output_folder": output_folder,
            "arduino_enabled": arduino_enabled,
            "arduino_port": (project_data.get("arduino_port") or "").strip(),
        }

        # Handle external trigger (may wait for signal)
        if self._handle_external_trigger(context, arduino_enabled):
            return

        # Start recording immediately
        self._pending_external_trigger = None
        self._schedule_recording(context, project_data, trigger_source="manual")

    def stop_recording(self):
        """
        Stop the current recording session.

        Sprint 15: Updated to use RecordingCoordinator instead of RecordingService directly.
        """
        log.info("controller.recording.stop")

        if self._pending_external_trigger:
            self._clear_external_trigger_wait()

        coordinator = self.recording_coordinator
        if coordinator is not None:
            try:
                coordinator.stop_recording()
            except Exception as exc:  # pragma: no cover - defensive fallback
                log.warning("controller.recording.coordinator_stop_failed", error=str(exc))

        recording_service = self.recording_service
        if recording_service is not None:
            try:
                recording_service.stop_session()
            except Exception as exc:  # pragma: no cover - defensive fallback
                log.warning("controller.recording.service_stop_failed", error=str(exc))

        # Update UI on main thread
        self.ui_event_bus.publish_event(
            Events.UI_UPDATE_BUTTON_STATE, {"button_name": "start_rec", "state": "normal"}
        )
        self.ui_event_bus.publish_event(
            Events.UI_UPDATE_BUTTON_STATE, {"button_name": "stop_rec", "state": "disabled"}
        )

    def start_live_project_session(
        self,
        day: int,
        group: str,
        subject: str,
        duration_s: float | None = None,
    ) -> bool:
        """
        Start a live recording session for a Live project.

        This method replaces the legacy thread-based system in gui.py,
        using LiveCameraService for unified camera management.

        Args:
            day: Day number (from project grid)
            group: Group identifier
            subject: Subject/animal identifier
            duration_s: Optional duration override (uses project default if None)

        Returns:
            True if session started successfully, False otherwise
        """
        pm = self.project_manager

        # Validate project type
        if pm.get_project_type() != "live":
            log.error("start_live_project_session.wrong_project_type")
            return False

        # Extract project configuration
        project_data = pm.project_data
        camera_index = project_data.get("camera_index", 0)

        # Duration: use parameter, project default, or fallback
        if duration_s is None:
            duration_s = project_data.get("recording_duration_s", 300.0)

        # Intervals
        analysis_interval_frames = project_data.get("analysis_interval_frames", 1)
        display_interval_frames = project_data.get("display_interval_frames", 1)

        # Experiment ID for this session
        experiment_id = f"day{day}_{group}_{subject}"

        log.info(
            "controller.live_project_session.start",
            project=pm.get_project_name(),
            experiment_id=experiment_id,
            camera_index=camera_index,
            duration_s=duration_s,
        )

        # Delegate to LiveCameraService (unified system)
        success = self.live_camera_service.start_session(
            camera_index=camera_index,
            duration_s=duration_s,
            experiment_id=experiment_id,
            analysis_interval_frames=analysis_interval_frames,
            display_interval_frames=display_interval_frames,
            record_video=True,  # Projects always record
        )

        return success

    # ========== Phase 5: Live Camera (164 lines) ==========

    def start_live_camera_analysis(self, camera_index: int | None = None):
        """
        Start a live camera analysis session.

        Delegates to LiveCameraService for thread management and coordination.
        Shows a dialog to configure the session if camera_index is not provided.

        Args:
            camera_index: Optional camera index. If provided, uses this camera directly
                         without showing the configuration dialog. If None, shows dialog.
        """
        log.info("controller.live_analysis.start", camera_index=camera_index)

        # Get configuration from dialog or use defaults
        if camera_index is not None:
            # Use camera directly with default settings
            if hasattr(self.settings, "live_analysis"):
                duration_s = self.settings.live_analysis.default_duration_s
            else:
                duration_s = 300
            experiment_id = f"camera_{camera_index}"
            analysis_interval_frames = 1
            display_interval_frames = 1
            record_video = True
        else:
            # Show configuration dialog
            from zebtrack.ui.dialogs import LiveAnalysisDialog

            dialog = LiveAnalysisDialog(self.view.root, settings_obj=self.settings)

            if not dialog.result:
                log.info("controller.live_analysis.cancelled")
                return

            config = dialog.result
            camera_index = config["camera_index"]
            duration_s = config["duration_s"]
            experiment_id = config["experiment_id"]
            analysis_interval_frames = config.get("analysis_interval_frames", 1)
            display_interval_frames = config.get("display_interval_frames", 1)
            record_video = config.get("record_video", True)

        # Delegate to LiveCameraService
        success = self.live_camera_service.start_session(
            camera_index=camera_index,
            duration_s=duration_s,
            experiment_id=experiment_id,
            analysis_interval_frames=analysis_interval_frames,
            display_interval_frames=display_interval_frames,
            record_video=record_video,
        )

        if success and self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_SET_STATUS,
                {"message": f"Analisando câmera {camera_index} por {duration_s}s..."},
            )
        elif not success and self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro na Análise",
                    "message": "Falha ao iniciar análise de câmera.",
                },
            )

    def run_live_calibration(self, temp_aquarium_method: str | None = None):
        """Record a short clip from the live camera and runs aquarium detection.

        Args:
            temp_aquarium_method: Temporary override for aquarium detection method
                ('det' or 'seg'). If None, uses global self.settings.
        """
        log.info("controller.live_calibration.start")
        if not self.view.camera or not self.view.camera.is_opened():
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro", "message": "A câmera não está disponível ou aberta."},
            )
            return

        temp_video_path = None
        self.main_view_model._publish_processing_mode(
            source="calibration.live.start",
            force=True,
            mode_override=ProcessingMode.SINGLE_SUBJECT,
        )
        try:
            # 1. Create a temporary file for the calibration video
            temp_video_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            temp_video_path = temp_video_file.name
            temp_video_file.close()

            # 2. Record a short clip
            w, h = self.view.camera.actual_width, self.view.camera.actual_height
            fps = self.settings.video_processing.fps
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(temp_video_path, fourcc, fps, (w, h))

            self.ui_event_bus.publish_event(
                Events.UI_SET_STATUS,
                {"message": "Calibrando... Gravando um pequeno clipe."},
            )

            start_time = time.time()
            while time.time() - start_time < 5:  # Record for 5 seconds
                ret, frame = self.view.camera.get_frame()
                if not ret:
                    break
                writer.write(frame)
            writer.release()
            self.ui_event_bus.publish_event(
                Events.UI_SET_STATUS,
                {"message": "Calibração: Analisando o clipe..."},
            )

            # 3. Run detection on the clip using selected aquarium method
            # Use temporary override if provided, otherwise use global settings
            aquarium_method = temp_aquarium_method or self.settings.model_selection.aquarium_method
            model_path = self.weight_manager.get_weight_path_by_method(aquarium_method, "aquarium")

            if not model_path:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro",
                        "message": f"Não foi possível encontrar um modelo {aquarium_method} para "
                        "detecção do aquário.",
                    },
                )
                return

            detector = AquariumDetector(model_path=model_path, mode=aquarium_method)
            polygons = detector.detect_aquariums(temp_video_path)

            if not polygons:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Detecção Falhou",
                        "message": "Nenhum aquário foi detectado. Por favor, desenhe a área manualmente.",  # noqa: E501
                    },
                )
                return

            main_polygon = polygons[0]
            self.ui_event_bus.publish_event(
                Events.UI_SETUP_INTERACTIVE_POLYGON, {"polygon": main_polygon}
            )

        except Exception as e:
            log.error("controller.live_calibration.error", exc_info=True)
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro na Calibração", "message": f"Ocorreu um erro: {e}"},
            )
        finally:
            # 4. Clean up the temporary file
            if temp_video_path and os.path.exists(temp_video_path):
                os.remove(temp_video_path)
            self.main_view_model._publish_processing_mode(
                source="calibration.live.complete",
                force=True,
            )
            self.ui_event_bus.publish_event(Events.UI_SET_STATUS, {"message": "Pronto."})
