from __future__ import annotations

import os
import tempfile
import threading
import time
from contextlib import contextmanager
from tkinter import Label, Toplevel

import cv2
import numpy as np
import pandas as pd
import structlog
from shapely.geometry import Polygon

try:
    from ultralytics import YOLO

    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False

from zebtrack.analysis.reporter import Reporter
from zebtrack.analysis.roi import ROI
from zebtrack.core.aquarium_detector import AquariumDetector
from zebtrack.core.calibration import Calibration
from zebtrack.core.detector import Detector, ZoneData
from zebtrack.core.project_manager import ProjectManager
from zebtrack.core.weight_manager import WeightManager
from zebtrack.io.arduino import Arduino
from zebtrack.io.arduino_manager import ArduinoManager
from zebtrack.io.recorder import Recorder
from zebtrack.plugins import DETECTOR_PLUGINS
from zebtrack.settings import settings
from zebtrack.ui.gui import ApplicationGUI
from zebtrack.utils import IntegrityError

log = structlog.get_logger()


class AppController:
    def __init__(self, root):
        self.root = root
        self.project_manager = ProjectManager()
        self.weight_manager = WeightManager()

        # New state variables for model management (must exist before view)
        default_weight, _ = self._safe_get_default_weight()
        self.active_weight_name = default_weight if default_weight is not None else ""
        if self.active_weight_name is None:
            self.active_weight_name = ""
            log.warning("controller.init.no_default_weight")
        self.use_openvino = False  # Default to not using OpenVINO
        self._global_model_defaults = {
            "active_weight": self.active_weight_name or None,
            "use_openvino": self.use_openvino,
        }
        self._using_project_overrides = False

        # Core runtime attributes
        self.detector = None
        self.recorder = Recorder()
        self.arduino: Arduino | None = None
        self.arduino_manager: ArduinoManager | None = None
        self._arduino_manager_cls = ArduinoManager
        self.report_results_paths = {}
        self.is_recording = False
        self.timed_recording_job = None

        # Create view after core state is ready so it can reflect it
        self.view = ApplicationGUI(root, self)
        # Other initializations...
        self.program_exit_event = threading.Event()
        self.processing_thread: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.pending_single_video_analysis = None

        self._pending_external_trigger: dict | None = None

    def run(self):
        # The GUI is now responsible for populating its own widgets when created.
        self.root.mainloop()

    def get_openvino_status(self) -> str:
        """Gets the current OpenVINO status text based on the model and settings."""
        if not self.active_weight_name:
            return "Nenhum peso selecionado."

        details = self.weight_manager.get_weight_details(self.active_weight_name)
        if not details:
            return "Detalhes do peso não encontrados."

        if self.use_openvino:
            if details.get("openvino_path") and os.path.exists(
                details.get("openvino_path")
            ):
                return "O modelo OpenVINO está pronto."
            else:
                return "Necessita de conversão para OpenVINO."
        else:
            return "O OpenVINO está desativado."

    def on_close(self):
        if self.view.ask_ok_cancel("Sair", "Deseja realmente sair?"):
            self.join_threads()
            self.root.destroy()

    def join_threads(self):
        """Signals all threads to stop and waits for them to finish."""
        log.info("controller.shutdown.start")
        self.program_exit_event.set()

        # Join background threads
        if hasattr(self, "capture_thread") and self.capture_thread.is_alive():
            log.info("controller.shutdown.join_capture_thread")
            self.capture_thread.join()

        if self.processing_thread is not None and self.processing_thread.is_alive():
            log.info("controller.shutdown.join_processing_thread")
            self.processing_thread.join()

        # Release camera resources
        if hasattr(self, "camera") and self.camera:
            log.info("controller.shutdown.release_camera")
            self.camera.release()

        self._shutdown_arduino_manager()

        log.info("controller.shutdown.complete")

    def _get_arduino_manager(self) -> ArduinoManager:
        if self.arduino_manager is None:
            self.arduino_manager = self._arduino_manager_cls(self)
        return self.arduino_manager

    def _shutdown_arduino_manager(self):
        if self.arduino_manager:
            try:
                self.arduino_manager.shutdown()
            except Exception:
                log.warning("controller.arduino.shutdown_failed", exc_info=True)
            self.arduino_manager = None
        self.arduino = None

    def _schedule_on_ui(self, func, *args, **kwargs):
        try:
            self.root.after(0, lambda: func(*args, **kwargs))
        except Exception:
            func(*args, **kwargs)

    def refresh_project_views(
        self,
        reason: str | None = None,
        *,
        append_summary: bool = False,
        immediate: bool = False,
    ) -> None:
        """Request a refresh of project-related UI components on the main thread."""

        if not getattr(self, "view", None):
            return

        refresh_fn = getattr(self.view, "refresh_project_views", None)
        if not callable(refresh_fn):
            return

        self._schedule_on_ui(
            refresh_fn,
            reason,
            append_summary=append_summary,
            immediate=immediate,
        )

    def _clear_external_trigger_wait(self):
        if not self._pending_external_trigger:
            return

        self._pending_external_trigger = None
        if hasattr(self.view, "clear_external_trigger_notice"):
            self._schedule_on_ui(self.view.clear_external_trigger_notice)
        self._schedule_on_ui(self.view.update_button_state, "start_rec", "normal")
        self._schedule_on_ui(self.view.update_button_state, "stop_rec", "disabled")
        self._schedule_on_ui(self.view.set_status, "Pronto.")

    def log_arduino_event(self, message: str):
        log.info("controller.arduino.log", message=message)
        if hasattr(self.view, "append_arduino_log"):
            self._schedule_on_ui(self.view.append_arduino_log, message)

    def on_arduino_status_change(self, connected: bool, port: str | None):
        log.info("controller.arduino.status", connected=connected, port=port)
        if hasattr(self.view, "update_arduino_status_indicator"):
            self._schedule_on_ui(
                self.view.update_arduino_status_indicator, connected, port
            )

    def on_arduino_command_sent(self, command: int, success: bool, source: str):
        label_text = str(command) if success else f"{command} (falha)"
        if hasattr(self.view, "set_arduino_last_command"):
            self._schedule_on_ui(self.view.set_arduino_last_command, label_text)

    def on_arduino_event(self, event_code: int):
        log.info("controller.arduino.event_received", code=event_code)
        self.log_arduino_event(f"Evento {event_code} recebido do Arduino.")

        if event_code == 1:
            if self._pending_external_trigger:
                self.log_arduino_event(
                    "Sinal externo recebido. Iniciando gravação..."
                )
                self.trigger_recording(event_code)
            else:
                log.warning("controller.arduino.event.unexpected_start")
        elif event_code == 0:
            if self.is_recording or self._pending_external_trigger:
                self.log_arduino_event("Sinal externo solicitando parada.")
                self._schedule_on_ui(self.stop_recording)
        else:
            log.info("controller.arduino.event.ignored", code=event_code)

    def trigger_recording(self, event_code: int | None = None):
        if not self._pending_external_trigger:
            log.warning(
                "controller.external_trigger.no_pending", code=event_code
            )
            return

        context = self._pending_external_trigger
        self._pending_external_trigger = None

        def _start_from_trigger():
            if hasattr(self.view, "clear_external_trigger_notice"):
                self.view.clear_external_trigger_notice()
            project_data = self.project_manager.project_data or {}
            self._schedule_recording(context, project_data, trigger_source="external")

        self._schedule_on_ui(_start_from_trigger)

    def _schedule_recording(
        self,
        context: dict,
        project_data: dict,
        *,
        trigger_source: str,
    ) -> None:
        countdown_s = int(project_data.get("countdown_duration_s", 0) or 0)
        use_countdown = bool(project_data.get("use_countdown")) and countdown_s > 0

        def _start_now():
            self._start_recording_now(context, project_data, trigger_source)

        if use_countdown:
            self._run_countdown(countdown_s, _start_now)
        else:
            _start_now()

    def _start_recording_now(
        self,
        context: dict,
        project_data: dict,
        trigger_source: str,
    ) -> None:
        folder_name = context["folder_name"]
        output_folder = context["output_folder"]

        zone_data = self.project_manager.get_zone_data()
        camera_width = getattr(self.view.camera, "actual_width", None)
        camera_height = getattr(self.view.camera, "actual_height", None)

        if camera_width is None or camera_height is None:
            self.view.show_error(
                "Erro",
                "Configuração da câmera indisponível para iniciar a gravação.",
            )
            self._schedule_on_ui(
                self.view.update_button_state, "start_rec", "normal"
            )
            return

        self.is_recording = self.recorder.start_recording(
            output_folder,
            camera_width,
            camera_height,
            zones=zone_data,
        )

        if not self.is_recording:
            self.view.show_error("Erro", "Não foi possível iniciar a gravação.")
            self._schedule_on_ui(
                self.view.update_button_state, "start_rec", "normal"
            )
            self._schedule_on_ui(
                self.view.update_button_state, "stop_rec", "disabled"
            )
            return

        self._schedule_on_ui(self.view.update_button_state, "start_rec", "disabled")
        self._schedule_on_ui(self.view.update_button_state, "stop_rec", "normal")
        self._schedule_on_ui(
            self.view.set_status, f"Recording session: {folder_name}"
        )

        if context.get("arduino_enabled") and self.arduino_manager:
            box_number = self._get_box_number(
                context["day"], context["group"], context["cobaia"]
            )
            if box_number is None:
                log.warning(
                    "controller.recording.arduino_invalid_box",
                    day=context["day"],
                    group=context["group"],
                    cobaia=context["cobaia"],
                )
            else:
                self.arduino_manager.send_command(
                    box_number, source=f"{trigger_source}-start"
                )

        project_data = project_data or {}
        if project_data.get("use_timed_recording"):
            duration_s = project_data.get("recording_duration_s", 0) or 0
            if duration_s > 0:
                duration_ms = int(duration_s * 1000)
                self.timed_recording_job = self.root.after(
                    duration_ms, self.stop_recording
                )
                log.info(
                    "controller.recording.timed_start",
                    duration_s=duration_s,
                    trigger=trigger_source,
                )

    def close_project(self):
        # Restore global defaults before clearing project state
        self._restore_global_model_defaults()

        # Reset project manager
        self.project_manager = ProjectManager()
        # _create_welcome_frame handles all UI cleanup
        self.view._create_welcome_frame()

    def create_project_workflow(self, **kwargs):
        # Use detection methods from kwargs if provided, otherwise fall back to
        # global settings
        animal_method = kwargs.get(
            "animal_method", settings.model_selection.animal_method
        )
        animals_per_aquarium = kwargs.get("animals_per_aquarium", 1)

        if animal_method == "det" and animals_per_aquarium != 1:
            self.view.show_error(
                "Configuração Inválida",
                (
                    "O modo de detecção (det) para animais só é compatível com 1 "
                    f"animal por aquário.\n"
                    f"Configuração atual: {animals_per_aquarium} "
                    "animais por aquário.\n\n"
                    "Para usar múltiplos animais por aquário, altere o método de "
                    "detecção de animais para 'seg' (segmentação) nas configurações."
                ),
            )
            return

        # If using detection mode with single animal,
        # optionally enable single_animal_per_aquarium
        if animal_method == "det" and animals_per_aquarium == 1:
            log.info(
                "controller.create_project.det_single_animal",
                animal_method=animal_method,
                animals_per_aquarium=animals_per_aquarium,
            )

        # Add the currently selected model info to the project data
        kwargs["active_weight"] = self.active_weight_name
        kwargs["use_openvino"] = self.use_openvino

        # WHITELIST APPROACH: Only pass parameters that create_new_project() accepts
        # This is more robust than manually removing unsupported params (blacklist)
        # See ProjectManager.create_new_project() signature
        # at project_manager.py:260-282
        allowed_params = {
            'project_path', 'project_type', 'use_openvino', 'active_weight',
            'video_files', 'num_aquariums', 'animals_per_aquarium',
            'aquarium_width_cm', 'aquarium_height_cm', 'use_timed_recording',
            'recording_duration_s', 'use_countdown', 'countdown_duration_s',
            'analysis_interval_frames', 'display_interval_frames',
            'camera_index', 'use_arduino', 'arduino_port',
            # Live project params (also valid for pre-recorded if user wants to
            # track design)
            'experiment_days', 'subjects_per_group', 'num_groups', 'group_names',
            # Wizard metadata
            '_wizard_metadata'
        }

        # Filter kwargs to only allowed parameters
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in allowed_params}

        if self.project_manager.create_new_project(**filtered_kwargs):
            # Projects start by inheriting global settings unless overrides apply later
            self._using_project_overrides = True
            self.apply_project_model_overrides()

            # Execute parquet import if wizard provided import configuration
            wizard_metadata = kwargs.get("_wizard_metadata", {})
            if wizard_metadata:
                import_config = wizard_metadata.get("import_config", [])
                roi_merge_strategy = wizard_metadata.get(
                    "roi_merge_strategy", "replace"
                )
                scanned_videos = wizard_metadata.get("scanned_videos", [])

                if import_config:
                    log.info(
                        "controller.create_project.importing_parquets",
                        video_count=len(import_config),
                        strategy=roi_merge_strategy,
                    )
                    success = self.project_manager.import_parquets_from_wizard(
                        import_config=import_config,
                        roi_merge_strategy=roi_merge_strategy,
                        scanned_videos=scanned_videos,
                    )
                    if success:
                        log.info("controller.create_project.parquets_imported")
                    else:
                        log.warning("controller.create_project.parquet_import_failed")

            # Pass animal_method to setup_detector if it was specified in dialog
            if self.setup_detector(temp_animal_method=animal_method):
                self.view._load_project_view()
                self.view.update_openvino_checkbox(self.use_openvino)
                self.view.set_active_weight_in_dropdown(self.active_weight_name)
                self.update_openvino_status()

                if wizard_metadata:
                    self._show_post_creation_guide(wizard_metadata)
        else:
            self.view.show_error("Erro", "Falha ao criar o novo projeto.")

    def _show_post_creation_guide(self, wizard_metadata: dict):
        """Display a contextual onboarding message after project creation."""

        if not wizard_metadata:
            return

        suppressed = (
            os.environ.get("PYTEST_CURRENT_TEST")
            or os.environ.get("ZEBTRACK_SUPPRESS_POST_CREATION_GUIDE")
            or getattr(self.view, "suppress_post_creation_guide", False)
        )

        if suppressed:
            reason = (
                "env_flag"
                if os.environ.get("ZEBTRACK_SUPPRESS_POST_CREATION_GUIDE")
                else "pytest"
            )
            log.info("controller.post_creation_guide.skipped", reason=reason)
            return

        import_config = wizard_metadata.get("import_config") or []
        scanned_videos = wizard_metadata.get("scanned_videos") or []

        project_videos = self.project_manager.get_all_videos()
        videos_source: list[dict] = []

        if project_videos:
            videos_source = project_videos
        elif scanned_videos:
            for video in scanned_videos:
                video_copy = dict(video)
                video_copy.setdefault("path", video_copy.get("video"))
                videos_source.append(video_copy)

        if not videos_source:
            return

        import_lookup = {
            config.get("video"): config
            for config in import_config
            if config.get("video")
        }

        key_map = {
            "has_arena": "import_arena",
            "has_rois": "import_rois",
            "has_trajectory": "import_trajectory",
        }

        def _feature_available(video: dict, feature_key: str) -> bool:
            if bool(video.get(feature_key)):
                return True

            metadata = video.get("metadata") or {}
            if bool(metadata.get(feature_key)):
                return True

            video_path = video.get("path") or video.get("video")
            if not video_path:
                return False

            import_cfg = import_lookup.get(video_path)
            if not import_cfg:
                return False

            import_key = key_map.get(feature_key)
            if not import_key:
                return False

            return bool(import_cfg.get(import_key))

        total_videos = len(videos_source)
        videos_with_arena = sum(
            1 for video in videos_source if _feature_available(video, "has_arena")
        )
        videos_with_rois = sum(
            1 for video in videos_source if _feature_available(video, "has_rois")
        )
        videos_with_trajectory = sum(
            1
            for video in videos_source
            if _feature_available(video, "has_trajectory")
        )
        videos_pending = sum(
            1
            for video in videos_source
            if not _feature_available(video, "has_trajectory")
        )

        lines: list[str] = []
        lines.append("🎉 Projeto criado com sucesso!")
        lines.append("")
        lines.append("📊 Status dos vídeos:")
        lines.append(f"  • Total de vídeos: {total_videos}")
        lines.append(f"  • Com arena definida: {videos_with_arena}")
        lines.append(f"  • Com ROIs definidas: {videos_with_rois}")
        lines.append(f"  • Com trajetória pronta: {videos_with_trajectory}")
        lines.append(f"  • Pendentes de processamento: {videos_pending}")
        lines.append("")
        lines.append("🚀 Próximos passos recomendados:")
        lines.append("")

        step_num = 1

        if videos_with_arena > 0 or videos_with_rois > 0:
            lines.append(f"{step_num}. Visualizar e ajustar zonas importadas")
            lines.append("   - Abra a aba 'Configuração de Zonas'")
            lines.append("   - Use o painel 'Selecionar Vídeo para Desenho'")
            lines.append("   - Clique duas vezes ou use 'Carregar Frame' para revisar")
            lines.append("   - Ajuste arena e ROIs conforme necessário")
            lines.append("")
            step_num += 1

        if videos_pending > 0:
            lines.append(f"{step_num}. Processar vídeos pendentes")
            lines.append("   - Vá até a aba 'Controle Principal'")
            lines.append("   - Confirme os intervalos de processamento")
            lines.append("   - Clique em 'Adicionar e Processar Novos Vídeos'")
            lines.append("")
            step_num += 1

        if videos_with_trajectory > 0:
            lines.append(f"{step_num}. Gerar relatórios")
            lines.append("   - Acesse a aba 'Relatórios'")
            lines.append("   - Navegue pela hierarquia de grupos, dias e sujeitos")
            lines.append(
                "   - Gere relatórios individuais ou unificados "
                "conforme necessário"
            )
            lines.append("")

        lines.append("💡 Dicas:")
        lines.append("  • Use a busca para localizar vídeos rapidamente")
        lines.append(
            "  • Os símbolos de status indicam arenas, ROIs "
            "e trajetórias disponíveis"
        )
        lines.append("  • Ajuste zonas antes de processar se necessário")

        message = "\n".join(lines)

        self.view.show_info("Bem-vindo ao Projeto!", message)

        log.info(
            "controller.post_creation_guide.shown",
            total_videos=total_videos,
            with_arena=videos_with_arena,
            with_rois=videos_with_rois,
            with_trajectory=videos_with_trajectory,
            pending=videos_pending,
        )

    def open_project_workflow(self, project_path):
        """Carrega projeto e configura tudo automaticamente"""
        log.info("controller.load_project.start", path=project_path)

        success = self.project_manager.load_project(project_path)

        if not success:
            self.view.show_error("Erro", "Não foi possível carregar o projeto")
            return False

        # Apply project-specific overrides (or inherit global defaults)
        self._using_project_overrides = True
        resolved_weight, resolved_openvino = self.apply_project_model_overrides()

        log.info(
            "controller.load_project.model_settings_applied",
            resolved_weight=resolved_weight,
            resolved_openvino=resolved_openvino,
        )

        # Ensure UI reflects the restored state before detector setup
        self.view.update_openvino_checkbox(self.use_openvino)
        self.view.set_active_weight_in_dropdown(self.active_weight_name)
        self.update_openvino_status()

        # Inicializa detector
        if not self.setup_detector():
            log.warning("controller.load_project.detector_setup_failed")
        else:
            # Restore detector settings from saved state
            saved_detector_config = self.project_manager.get_detector_state()
            if saved_detector_config and self.detector:
                log.info(
                    "controller.detector.state.restore_start",
                    config=saved_detector_config,
                )

                plugin = self.detector.plugin
                settings_changed = False

                # Restore confidence threshold
                if "confidence_threshold" in saved_detector_config and hasattr(
                    plugin, "conf_threshold"
                ):
                    old_conf = plugin.conf_threshold
                    new_conf = saved_detector_config["confidence_threshold"]
                    if old_conf != new_conf:
                        plugin.conf_threshold = new_conf
                        settings_changed = True
                        log.info(
                            "controller.detector.threshold.restored",
                            old=old_conf,
                            new=new_conf,
                            type="confidence",
                        )

                # Restore NMS threshold
                if "nms_threshold" in saved_detector_config and hasattr(
                    plugin, "nms_threshold"
                ):
                    old_nms = plugin.nms_threshold
                    new_nms = saved_detector_config["nms_threshold"]
                    if old_nms != new_nms:
                        plugin.nms_threshold = new_nms
                        settings_changed = True
                        log.info(
                            "controller.detector.threshold.restored",
                            old=old_nms,
                            new=new_nms,
                            type="nms",
                        )

                # Restore context
                if "context" in saved_detector_config and hasattr(
                    plugin, "set_context"
                ):
                    saved_context = saved_detector_config["context"]
                    current_context = getattr(plugin, "_context", "tracking")
                    if current_context != saved_context:
                        plugin.set_context(saved_context)
                        settings_changed = True
                        log.info(
                            "controller.detector.context.restored",
                            old=current_context,
                            new=saved_context,
                        )

                # Log restoration summary
                if settings_changed:
                    log.info(
                        "controller.detector.state.restored",
                        plugin=saved_detector_config.get("plugin_name"),
                        last_updated=saved_detector_config.get("last_updated"),
                    )
                    # Save back to project to ensure consistency
                    current_config = {
                        "plugin_name": saved_detector_config.get(
                            "plugin_name",
                            "OpenVINO"
                            if self.use_openvino
                            else "YOLO (Ultralytics)",
                        ),
                        "confidence_threshold": plugin.conf_threshold,
                        "nms_threshold": plugin.nms_threshold,
                        "context": getattr(plugin, "_context", "tracking"),
                    }
                    self.project_manager.save_detector_state(current_config)
                else:
                    log.info("controller.detector.state.no_changes_needed")

            # Carrega interface do projeto
            self.view._load_project_view()

        # NOVO: Carrega e aplica zonas salvas
        zone_data = self.project_manager.get_zone_data()
        if zone_data and (zone_data.polygon or zone_data.roi_polygons):
            log.info(
                "controller.load_project.zones_found",
                has_polygon=bool(zone_data.polygon),
                roi_count=len(zone_data.roi_polygons),
            )

            # Configura zonas no detector
            self.setup_detector_zones()

            # Atualiza visualização das zonas na GUI
            if hasattr(self.view, "redraw_zones_from_project_data"):
                self.view.redraw_zones_from_project_data()
            if hasattr(self.view, "update_zone_listbox"):
                self.view.update_zone_listbox()

            log.info("controller.load_project.zones_applied")

        # Coleta informações do projeto para feedback
        project_name = self.project_manager.get_project_name()
        all_videos = self.project_manager.get_all_videos()
        videos_count = len(all_videos)

        # Mostra status detalhado
        zone_status = "✓" if zone_data and zone_data.polygon else "✗"
        roi_count = len(zone_data.roi_polygons) if zone_data else 0

        self.view.show_info(
            "Projeto Carregado",
            f"Projeto '{project_name}' carregado com sucesso!\n\n"
            f"• Vídeos: {videos_count}\n"
            f"• Arena Principal: {zone_status}\n"
            f"• ROIs: {roi_count}\n"
            f"• Peso: {self.active_weight_name or 'Padrão'}\n"
            f"• OpenVINO: {'✓' if self.use_openvino else '✗'}",
        )

        log.info(
            "controller.load_project.complete",
            project=project_name,
            videos=videos_count,
            has_zones=bool(zone_data and zone_data.polygon),
            rois=roi_count,
        )

        return True

    def setup_detector(self, temp_animal_method: str | None = None) -> bool:
        """Initializes the detector instance based on the animal method selection.

        Args:
            temp_animal_method: Temporary override for animal detection method
                ('det' or 'seg'). If None, uses global settings.
        """
        # Use temporary override if provided, otherwise use global settings
        animal_method = temp_animal_method or settings.model_selection.animal_method
        log.info(
            "detector.setup.start",
            animal_method=animal_method,
            temp_override=temp_animal_method is not None,
            use_openvino=self.use_openvino,
        )

        # Get weight path based on animal method
        model_path = self.weight_manager.get_weight_path_by_method(
            animal_method, "animal"
        )
        log.info(
            "detector.setup.model_path_selected",
            animal_method=animal_method,
            task="animal",
            model_path=model_path,
        )
        if not model_path:
            self.view.show_error(
                "Erro de Detector",
                f"Nenhum modelo {animal_method} está disponível para detecção de "
                "animais.",
            )
            return False

        # Check if we need to use OpenVINO version
        weight_details = None
        if self.use_openvino:
            # Find weight details to get OpenVINO path - use the first matching weight
            for name, details in self.weight_manager.weights.items():
                if details.get("path") == model_path:
                    weight_details = details
                    break

        try:
            if self.use_openvino:
                plugin_name = "OpenVINO"
                if not weight_details:
                    raise ValueError(
                        "Não foi possível encontrar detalhes do peso para OpenVINO"
                    )

                openvino_model_path = weight_details.get("openvino_path")
                if not openvino_model_path or not os.path.exists(openvino_model_path):
                    raise ValueError(
                        "Caminho do modelo OpenVINO não encontrado ou inválido. "
                        "Por favor, converta o modelo primeiro."
                    )
                model_path = openvino_model_path
            else:
                plugin_name = "YOLO (Ultralytics)"
                if not os.path.exists(model_path):
                    raise ValueError(
                        "Caminho do modelo YOLO .pt não encontrado ou inválido."
                    )

            plugin_class = DETECTOR_PLUGINS.get(plugin_name)
            if not plugin_class:
                raise ValueError(f"Detector plugin '{plugin_name}' not found.")

            log.info(
                "detector.load.start",
                plugin=plugin_name,
                path=model_path,
                method=animal_method,
            )
            # Pass hash for OpenVINO models for integrity check
            if self.use_openvino:
                expected_hash = weight_details.get("openvino_hash")
                plugin_instance = plugin_class(
                    model_path=model_path, expected_hash=expected_hash
                )
            else:
                plugin_instance = plugin_class(model_path=model_path)

            self.detector = Detector(
                plugin=plugin_instance,
                base_width=settings.camera.desired_width,
                base_height=settings.camera.desired_height,
            )

            # Set context for tracking
            if hasattr(plugin_instance, "set_context"):
                plugin_instance.set_context("tracking")
                log.info("detector.context.set", context="tracking")

            # Save detector state to project
            if self.project_manager.project_data:
                detector_config = {
                    "plugin_name": (
                        "OpenVINO" if self.use_openvino else "YOLO (Ultralytics)"
                    ),
                    "confidence_threshold": plugin_instance.conf_threshold,
                    "nms_threshold": plugin_instance.nms_threshold,
                    "context": getattr(plugin_instance, "_context", "tracking"),
                }

                if hasattr(plugin_instance, "get_context_info"):
                    # For plugins that provide more detailed context info
                    context_info = plugin_instance.get_context_info()
                    detector_config["context"] = context_info.get("context", "tracking")

                save_result = self.project_manager.save_detector_state(detector_config)
                if save_result:
                    log.info("controller.detector.state.saved", config=detector_config)
                else:
                    log.warning("controller.detector.state.save_failed")

            log.info("detector.setup.success", method=animal_method)
            return True
        except (ValueError, FileNotFoundError, IntegrityError) as e:
            log.error("detector.init.failed", error=str(e), exc_info=True)
            self.view.show_error(
                "Erro de Detector", f"Falha ao inicializar o detector: {e}"
            )
            return False

    def _is_arduino_connected(self) -> bool:
        """Checks whether there is an active Arduino connection."""
        if not self.arduino_manager:
            return False
        return self.arduino_manager.is_connected()

    def setup_arduino(self) -> bool:
        """Ensures the Arduino connection is ready when the project requests it."""
        project_data = getattr(self.project_manager, "project_data", {}) or {}
        use_arduino = bool(project_data.get("use_arduino"))
        if not use_arduino:
            log.debug("controller.arduino.disabled")
            if self.arduino_manager:
                self.arduino_manager.disconnect()
            return False

        port = (project_data.get("arduino_port") or "").strip()
        if not port:
            log.warning("controller.arduino.no_port_configured")
            return False

        manager = self._get_arduino_manager()
        if manager.is_connected() and manager.current_port() == port:
            log.debug("controller.arduino.already_connected", port=port)
            self.arduino = manager.arduino
            return True

        baud_rate = settings.arduino.baud_rate
        if manager.connect(port, baud_rate):
            self.arduino = manager.arduino
            return True

        return False

    def _get_box_number(self, day, group, cobaia) -> int | None:
        """Resolves the Arduino box number for this session.

        By default we convert the cobaia identifier to an integer so each subject
        maps to the same relay channel. Override this helper if your setup requires a
        different mapping (e.g., mapping groups or arenas to relays).
        """

        try:
            return int(cobaia)
        except (TypeError, ValueError):
            log.warning(
                "controller.recording.arduino_box_resolution_failed",
                day=day,
                group=group,
                cobaia=cobaia,
            )
            return None

    def setup_detector_zones(self):
        """Loads zone data from project and sets it on the detector instance."""
        if not self.detector:
            log.warning("detector.setup_zones.no_detector")
            return

        zone_data = self.project_manager.get_zone_data()

        # For now, we need to know the actual width/height of the source.
        # This logic will be improved when the workflows are implemented.
        # We'll default to the camera settings for now.
        width = settings.camera.desired_width
        height = settings.camera.desired_height

        self.detector.set_zones(zone_data, width, height)
        log.info("controller.setup_zones.success")

        # Informa ao plugin se o aquário está definido
        plugin = getattr(self.detector, "plugin", None)
        if plugin and hasattr(plugin, "set_aquarium_region_defined"):
            has_aquarium = bool(zone_data and zone_data.polygon)
            plugin.set_aquarium_region_defined(has_aquarium)
            log.info("detector.aquarium_status", defined=has_aquarium)

        if not zone_data.polygon:
            if self.project_manager.get_project_type() == "pre-recorded":
                self.view.notebook.select(self.view.zone_tab_frame)
                first_video = self.project_manager.get_next_video()
                if first_video:
                    self.view.display_roi_video_frame(first_video)
                self.view.show_error(
                    "Configuração Necessária",
                    "Erro: A área de processamento principal (aquário) não foi "
                    "definida. Por favor, defina-a na aba 'Configuração de Zonas' "
                    "antes de continuar.",
                )

    # --- New Methods for Weight Management ---

    def _safe_get_default_weight(self) -> tuple[str | None, dict | None]:
        manager = getattr(self, "weight_manager", None)
        if manager is None:
            return None, None
        try:
            result = manager.get_default_weight()
        except Exception:
            log.warning("controller.default_weight.safe_get_failed", exc_info=True)
            return None, None
        if isinstance(result, tuple):
            if not result:
                return None, None
            if len(result) == 1:
                return result[0], None
            return result[0], result[1]
        if result:
            return result, None
        return None, None

    def get_all_weight_names(self) -> list:
        return self.weight_manager.get_all_weights()

    def classify_weight_type(self, filename: str) -> str | None:
        """Classify weight type from filename - delegates to weight manager."""
        return self.weight_manager._classify_weight_type(filename)

    def add_new_weight(self, path: str, set_as_default: bool, weight_type: str = None):
        """Add a new weight with type classification."""
        self.weight_manager.add_weight(path, set_as_default, weight_type)
        new_name = os.path.basename(path)
        # Refresh UI
        self.view.update_weights_dropdown(self.get_all_weight_names())
        self.view.set_active_weight_in_dropdown(new_name)
        self.set_active_weight(new_name)  # This will also trigger conversion check

    def delete_weight(self, name: str):
        self.weight_manager.delete_weight(name)
        # Refresh UI
        self.view.update_weights_dropdown(self.get_all_weight_names())
        name, _ = self._safe_get_default_weight()
        self.view.set_active_weight_in_dropdown(name)
        self.set_active_weight(name, None)

    def set_active_weight(self, name: str | None, dialog=None):
        candidate = name or ""
        available = set(self.get_all_weight_names())

        if candidate and candidate in available:
            self.active_weight_name = candidate
            log.info("controller.active_weight.set", name=candidate)
            if hasattr(self.view, "set_active_weight_in_dropdown"):
                try:
                    self.view.set_active_weight_in_dropdown(candidate)
                except Exception:
                    log.warning(
                        "controller.active_weight.view_update_failed", exc_info=True
                    )
            self.update_openvino_status(dialog)
            if self.use_openvino:
                self.convert_active_weight_to_openvino(dialog)
        else:
            if candidate:
                log.warning("controller.active_weight.not_found", name=name)
            self.active_weight_name = ""
            if hasattr(self.view, "set_active_weight_in_dropdown"):
                try:
                    self.view.set_active_weight_in_dropdown("")
                except Exception:
                    log.warning(
                        "controller.active_weight.view_update_failed", exc_info=True
                    )
            self.update_openvino_status(dialog)

        if not self._using_project_overrides:
            self._global_model_defaults["active_weight"] = (
                self.active_weight_name or None
            )

    def set_openvino_usage(self, use_openvino: bool, dialog=None):
        self.use_openvino = bool(use_openvino)
        log.info("controller.openvino_usage.set", enabled=self.use_openvino)
        if hasattr(self.view, "update_openvino_checkbox"):
            try:
                self.view.update_openvino_checkbox(self.use_openvino)
            except Exception:
                log.warning(
                    "controller.openvino_usage.view_update_failed", exc_info=True
                )
        if self.use_openvino and self.active_weight_name:
            # Trigger conversion if switching to OpenVINO and model isn't converted
            self.convert_active_weight_to_openvino(dialog)
        self.update_openvino_status(dialog)

        if not self._using_project_overrides:
            self._global_model_defaults["use_openvino"] = self.use_openvino

    def convert_active_weight_to_openvino(self, dialog):
        if not self.active_weight_name:
            return
        self.view.set_status(f"Convertendo {self.active_weight_name} para OpenVINO...")
        self.view.update_idletasks()
        self.weight_manager.convert_to_openvino(self.active_weight_name)
        self.update_openvino_status(dialog)
        self.view.set_status("Verificação de conversão concluída. Pronto.")

    def update_openvino_status(self, dialog=None):
        """Updates the status label in the GUI based on the current state."""
        status = self.get_openvino_status()
        if dialog:
            dialog.update_openvino_status_label(status)
        if hasattr(self.view, "update_openvino_status_display"):
            try:
                self.view.update_openvino_status_display(status)
            except Exception:
                log.warning(
                    "controller.openvino_status.view_update_failed", exc_info=True
                )

    @property
    def are_project_overrides_active(self) -> bool:
        return bool(self._using_project_overrides)

    def get_global_model_defaults(self) -> dict:
        return {
            "active_weight": self._global_model_defaults.get("active_weight"),
            "use_openvino": self._global_model_defaults.get("use_openvino", False),
        }

    def _get_project_data_dict(self) -> dict:
        project_data = getattr(self.project_manager, "project_data", None)
        if not isinstance(project_data, dict):
            project_data = {} if not project_data else dict(project_data)
            self.project_manager.project_data = project_data
        return project_data

    def _ensure_project_overrides_record(self) -> dict:
        project_data = self._get_project_data_dict()
        overrides = project_data.get("model_overrides")
        if not isinstance(overrides, dict):
            overrides = {"active_weight": None, "use_openvino": None}
            project_data["model_overrides"] = overrides
        return overrides

    def has_project_override_settings(self) -> bool:
        if not getattr(self.project_manager, "project_path", None):
            return False
        overrides = self._ensure_project_overrides_record()
        return any(value not in (None, "", "inherit") for value in overrides.values())

    def get_calibration_scope_info(self) -> dict:
        project_path = getattr(self.project_manager, "project_path", None)
        project_loaded = bool(project_path)
        project_name = None
        if project_loaded and hasattr(self.project_manager, "get_project_name"):
            try:
                project_name = self.project_manager.get_project_name()
            except Exception:  # pragma: no cover - defensive
                project_name = None

        overrides_active = self.has_project_override_settings()
        inheriting_globals = project_loaded and not overrides_active
        scope = (
            "project"
            if project_loaded and self._using_project_overrides
            else "global"
        )

        if scope == "project":
            label = (
                f"Escopo: Projeto ({project_name})"
                if project_name
                else "Escopo: Projeto"
            )
            if overrides_active:
                detail = (
                    "Este projeto usa overrides salvos. Ajustes nesta janela são "
                    "persistidos apenas neste projeto."
                )
            else:
                detail = (
                    "Este projeto está herdando os padrões globais. Ao salvar "
                    "aqui, os valores se tornam overrides específicos."
                )
        else:
            label = "Escopo: Configuração Global"
            if project_loaded:
                detail = (
                    "Alterações atualizam o padrão global. Use a ação de cópia para "
                    "fixar estes valores no projeto atual."
                )
            else:
                detail = (
                    "Nenhum projeto carregado; ajustes atualizam os padrões "
                    "globais."
                )

        return {
            "scope": scope,
            "project_loaded": project_loaded,
            "project_name": project_name,
            "overrides_active": overrides_active,
            "inheriting_globals": inheriting_globals,
            "label": label,
            "detail": detail,
        }

    def _persist_project_model_settings(
        self, weight: str | None, use_openvino: bool
    ) -> dict:
        project_data = self._get_project_data_dict()
        overrides = self._ensure_project_overrides_record()
        overrides["active_weight"] = weight
        overrides["use_openvino"] = use_openvino
        project_data["active_weight"] = weight
        project_data["use_openvino"] = bool(use_openvino)
        self.project_manager.project_data = project_data
        if getattr(self.project_manager, "project_path", None):
            self.project_manager.save_project()
        return overrides

    def copy_global_model_settings_to_project(self) -> tuple[str | None, bool] | None:
        if not getattr(self.project_manager, "project_path", None):
            if hasattr(self.view, "show_warning"):
                self.view.show_warning(
                    "Nenhum Projeto",
                    "Abra um projeto antes de copiar configurações globais.",
                )
            return None

        defaults = self.get_global_model_defaults()
        weight = defaults.get("active_weight") or (self.active_weight_name or None)
        use_openvino = bool(defaults.get("use_openvino", False))

        overrides = self._persist_project_model_settings(weight, use_openvino)

        message = "Configurações globais aplicadas ao projeto."
        if hasattr(self.view, "set_status"):
            self.view.set_status(message)
        self.refresh_project_views(reason=message, append_summary=True)

        return overrides.get("active_weight"), bool(overrides.get("use_openvino"))

    def save_current_calibration_to_project(self) -> tuple[str | None, bool] | None:
        if not getattr(self.project_manager, "project_path", None):
            if hasattr(self.view, "show_warning"):
                self.view.show_warning(
                    "Nenhum Projeto",
                    "Abra um projeto antes de salvar overrides de calibração.",
                )
            return None

        overrides = self._persist_project_model_settings(
            self.active_weight_name or None,
            bool(self.use_openvino),
        )

        # Garantir que o estado em memória reflita os overrides recém-salvos
        self.apply_project_model_overrides(overrides)

        message = "Overrides do projeto atualizados a partir desta calibração."
        if hasattr(self.view, "set_status"):
            self.view.set_status(message)
        self.refresh_project_views(reason=message, append_summary=True)

        return overrides.get("active_weight"), bool(overrides.get("use_openvino"))

    def _apply_model_settings(
        self, weight_name: str | None, use_openvino: bool, dialog=None
    ) -> None:
        if weight_name:
            self.set_active_weight(weight_name, dialog)
        else:
            self.set_active_weight("", dialog)
        self.set_openvino_usage(bool(use_openvino), dialog)

    def resolve_project_model_settings(
        self, overrides: dict | None = None
    ) -> tuple[str | None, bool]:
        project_data = getattr(self.project_manager, "project_data", {}) or {}
        base_overrides = project_data.get("model_overrides") or {}
        if overrides is not None:
            merged_overrides = base_overrides.copy()
            merged_overrides.update(overrides)
        else:
            merged_overrides = base_overrides

        weight_override = merged_overrides.get("active_weight")
        if isinstance(weight_override, str):
            weight_override = weight_override.strip() or None

        openvino_override = merged_overrides.get("use_openvino")
        if isinstance(openvino_override, str):
            lowered = openvino_override.strip().lower()
            if lowered in {"", "inherit", "auto"}:
                openvino_override = None
            else:
                openvino_override = lowered in {"true", "1", "yes", "on"}

        resolved_weight = weight_override
        if not resolved_weight:
            resolved_weight = project_data.get("active_weight") or None
        if not resolved_weight:
            resolved_weight = self._global_model_defaults.get("active_weight")
        if not resolved_weight:
            default_weight, _ = self._safe_get_default_weight()
            resolved_weight = default_weight

        available_weights = set(self.get_all_weight_names())
        if resolved_weight and resolved_weight not in available_weights:
            log.warning(
                "controller.project_overrides.weight_missing",
                weight=resolved_weight,
                available=list(available_weights),
            )
            fallback_weight = self._global_model_defaults.get("active_weight")
            if fallback_weight and fallback_weight in available_weights:
                resolved_weight = fallback_weight
            else:
                default_weight, _ = self._safe_get_default_weight()
                resolved_weight = default_weight if default_weight else None

        if openvino_override is None:
            if project_data.get("use_openvino") is not None:
                resolved_openvino = bool(project_data.get("use_openvino"))
            else:
                resolved_openvino = bool(
                    self._global_model_defaults.get("use_openvino", False)
                )
        else:
            resolved_openvino = bool(openvino_override)

        return resolved_weight, resolved_openvino

    def apply_project_model_overrides(
        self, overrides: dict | None = None
    ) -> tuple[str | None, bool]:
        if not getattr(self.project_manager, "project_data", None):
            return self.active_weight_name or None, bool(self.use_openvino)

        resolved_weight, resolved_openvino = self.resolve_project_model_settings(
            overrides
        )

        self._using_project_overrides = True
        self._apply_model_settings(resolved_weight, resolved_openvino)

        updated = False
        if (
            self.project_manager.project_data.get("active_weight")
            != resolved_weight
        ):
            self.project_manager.project_data["active_weight"] = resolved_weight
            updated = True
        if (
            self.project_manager.project_data.get("use_openvino")
            != resolved_openvino
        ):
            self.project_manager.project_data["use_openvino"] = resolved_openvino
            updated = True

        if updated and getattr(self.project_manager, "project_path", None):
            self.project_manager.save_project()

        return resolved_weight, resolved_openvino

    def save_project_model_overrides(
        self, active_weight_override: str | None, use_openvino_override: bool | None
    ) -> tuple[str | None, bool]:
        if not getattr(self.project_manager, "project_path", None):
            log.warning("controller.project_overrides.no_project_loaded")
            return self.active_weight_name or None, self.use_openvino

        overrides = self.project_manager.project_data.setdefault(
            "model_overrides",
            {"active_weight": None, "use_openvino": None},
        )
        overrides["active_weight"] = active_weight_override or None
        overrides["use_openvino"] = use_openvino_override

        resolved_weight, resolved_openvino = self.apply_project_model_overrides(
            overrides
        )

        self.project_manager.project_data["model_overrides"] = overrides
        self.project_manager.save_project()

        return resolved_weight, resolved_openvino

    def _restore_global_model_defaults(self) -> None:
        target_weight = self._global_model_defaults.get("active_weight")
        target_openvino = bool(self._global_model_defaults.get("use_openvino", False))
        self._using_project_overrides = False
        self._apply_model_settings(target_weight, target_openvino)

    @contextmanager
    def global_calibration_session(self):
        previous_flag = self._using_project_overrides
        self._using_project_overrides = False
        try:
            yield
        finally:
            self._global_model_defaults["active_weight"] = (
                self.active_weight_name or None
            )
            self._global_model_defaults["use_openvino"] = self.use_openvino
            self._using_project_overrides = previous_flag
            if previous_flag and getattr(self.project_manager, "project_path", None):
                self.apply_project_model_overrides()

    def run_aquarium_detection(
        self,
        video_path: str | None = None,
        stabilization_frames: int = 10,
        temp_aquarium_method: str = None,
    ):
        """Runs the aquarium detection model on the specified or first project video.

        Args:
            video_path: Path to video file, if None uses next project video
            stabilization_frames: Number of frames to analyze for stabilization
            temp_aquarium_method: Temporary override for aquarium detection method
                ('det' or 'seg'). If None, uses global settings.
        """
        log.info("controller.aquarium_detection.start")
        self.view.set_status("Detectando aquário, por favor aguarde...")
        self.view.update_idletasks()

        try:
            if video_path is None:
                video_path = self.project_manager.get_next_video()

            if not video_path:
                self.view.show_warning(
                    "Aviso",
                    "Nenhum vídeo foi encontrado para a detecção.",
                )
                return

            self.project_manager.set_active_zone_video(video_path)

            # Display the first frame of the video as a preview background
            self.view.display_roi_video_frame(video_path)

            # Use selected aquarium method and get appropriate weight
            # Use temporary override if provided, otherwise use global settings
            aquarium_method = (
                temp_aquarium_method or settings.model_selection.aquarium_method
            )
            model_path = self.weight_manager.get_weight_path_by_method(
                aquarium_method, "aquarium"
            )

            if not model_path:
                self.view.show_error(
                    "Erro",
                    f"Não foi possível encontrar um modelo {aquarium_method} para "
                    "detecção do aquário.",
                )
                return

            detector = AquariumDetector(model_path=model_path, mode=aquarium_method)
            polygons = detector.detect_aquariums(
                video_path, stabilization_frames=stabilization_frames
            )

            if not polygons:
                self.view.show_warning(
                    "Detecção Automática Falhou",
                    (
                        "Não foi possível identificar uma área de aquário estável "
                        "no vídeo. Isso pode ocorrer devido a reflexos, pouca luz ou "
                        "movimento excessivo da câmera.\n\nPor favor, defina a área "
                        "do aquário manualmente utilizando a ferramenta 'Desenhar "
                        "Polígono Principal'."
                    ),
                )
                return

            main_polygon = polygons[0]
            log.info(
                "controller.aquarium_detection.success",
                polygon_points=len(main_polygon),
            )
            # The view will handle drawing this polygon interactively
            self.view.setup_interactive_polygon(main_polygon)

        except Exception as e:
            log.error("controller.aquarium_detection.error", exc_info=True)
            self.view.show_error(
                "Erro na Detecção", f"Ocorreu um erro ao detectar o aquário: {e}"
            )
        finally:
            self.view.set_status("Pronto.")

    def set_main_arena_polygon(self, points: list) -> bool:
        """Salva polígono com validações robustas"""
        try:
            # Validação 1: Pontos válidos
            if not points or len(points) < 3:
                log.error(
                    "controller.polygon.invalid_points",
                    count=len(points) if points else 0,
                )
                return False

            # Validação 2: Projeto existe
            if not self.project_manager.project_path:
                log.error("controller.polygon.no_project")
                # Para single video workflow, cria projeto temporário
                if (
                    hasattr(self.view, "pending_single_video_path")
                    and self.view.pending_single_video_path
                ):
                    import tempfile

                    temp_dir = tempfile.mkdtemp(prefix="zebtrack_temp_")
                    self.project_manager.project_path = temp_dir
                    self.project_manager.project_data = {
                        "project_name": "Temporary Single Video Project",
                        "project_type": "single_video",
                        "detection_zones": {},
                    }
                    log.warning(
                        "controller.polygon.created_temp_project", path=temp_dir
                    )
                else:
                    return False

            # Validação 3: Estrutura de dados
            if "detection_zones" not in self.project_manager.project_data:
                self.project_manager.save_zone_data(ZoneData(), persist=False)
                log.info("controller.polygon.initialized_detection_zones")

            # Salva
            self.project_manager.update_main_polygon(points)

            # Força atualização visual
            self.root.after(100, self.view.redraw_zones_from_project_data)

            log.info("controller.polygon.saved", points=len(points))
            return True

        except Exception as e:
            log.error("controller.polygon.save_error", error=str(e))
            return False

    def save_manual_arena(self, polygon_points: list[list[int]]):
        """Saves the manually adjusted arena and updates the detector."""
        log.info("controller.arena.save_manual", points_count=len(polygon_points))
        self.update_main_arena(polygon_points)

    def update_main_arena(self, polygon_points: list[list[int]]):
        """Updates the main arena polygon in the project's zone data."""
        log.info("controller.zone.update_arena", points=len(polygon_points))

        zone_data = self.project_manager.get_zone_data()
        zone_data.polygon = polygon_points
        self.project_manager.save_zone_data(zone_data)

        # After updating, we need to reload the zones in the detector
        self.setup_detector_zones()
        log.info("controller.zone.update_arena.success")

    def add_roi_polygon(
        self, roi_points: list[list[int]], name: str, color: tuple[int, int, int]
    ):
        """Adiciona ROI com validação de sobreposição"""
        try:
            log.info("controller.zone.add_roi", name=name, points=len(roi_points))

            # Critical Fix #4: Add project validation before saving ROI
            if not self.project_manager.project_path:
                log.error("controller.zone.add_roi.no_project", name=name)
                return False

            zone_data = self.project_manager.get_zone_data()

            # Validação 1: Verifica se está dentro da arena principal
            if zone_data.polygon and len(zone_data.polygon) >= 3:
                import cv2
                import numpy as np

                arena_poly = np.array(zone_data.polygon, dtype=np.float32)

                # First pass: adjust points that are slightly outside (likely from
                # snapping)
                adjusted_points = []
                # Calculate arena centroid once (convert to native Python float)
                centroid_x = float(np.mean(arena_poly[:, 0]))
                centroid_y = float(np.mean(arena_poly[:, 1]))

                for point in roi_points:
                    px, py = float(point[0]), float(point[1])
                    # True returns signed distance
                    result = cv2.pointPolygonTest(arena_poly, (px, py), True)

                    # If point is slightly outside (within 3 pixels), nudge it inside
                    if -3.0 <= result < 0:
                        # Move point toward centroid by 3 pixels
                        dx = centroid_x - px
                        dy = centroid_y - py
                        length = float(np.sqrt(dx*dx + dy*dy))
                        if length > 0:
                            px += (dx / length) * 3.0
                            py += (dy / length) * 3.0

                    # Ensure values are native Python float, not numpy types
                    adjusted_points.append([float(px), float(py)])

                # Second pass: validate adjusted points
                points_outside = 0
                for point in adjusted_points:
                    result = cv2.pointPolygonTest(arena_poly, tuple(point), False)
                    if result < 0:  # Ponto está fora
                        points_outside += 1

                # If adjustment worked, use adjusted points
                if points_outside == 0:
                    roi_points = adjusted_points

                if points_outside > 0:
                    outside_percent = (points_outside / len(roi_points)) * 100
                    log.warning(
                        "controller.roi.outside_arena",
                        name=name,
                        points_outside=points_outside,
                        percent=outside_percent,
                    )

                    if not self.view.ask_ok_cancel(
                        "ROI Fora da Arena",
                        (
                            f"A ROI '{name}' tem {points_outside} pontos "
                            f"({outside_percent:.1f}%) "
                            "fora da arena principal.\n\nDeseja continuar mesmo assim?"
                        ),
                    ):
                        return False

            # Validação 2: Verifica sobreposição com outras ROIs
            for i, existing_roi in enumerate(zone_data.roi_polygons):
                if len(existing_roi) >= 3:
                    # Calcula sobreposição simples verificando pontos
                    overlapping_points = 0

                    existing_poly = np.array(existing_roi, dtype=np.int32)

                    for point in roi_points:
                        result = cv2.pointPolygonTest(
                            existing_poly, tuple(point), False
                        )
                        if result >= 0:  # Ponto está dentro ou na borda
                            overlapping_points += 1

                    if overlapping_points > 0:
                        overlap_percent = (overlapping_points / len(roi_points)) * 100

                        if overlap_percent > 20:  # Mais de 20% de sobreposição
                            existing_name = (
                                zone_data.roi_names[i]
                                if i < len(zone_data.roi_names)
                                else f"ROI_{i + 1}"
                            )
                            log.warning(
                                "controller.roi.overlap",
                                name=name,
                                existing=existing_name,
                                percent=overlap_percent,
                            )

                            if not self.view.ask_ok_cancel(
                                "ROIs Sobrepostas",
                                f"A nova ROI '{name}' tem {overlap_percent:.1f}% de "
                                f"sobreposição com '{existing_name}'.\n\n"
                                "Deseja continuar?",
                            ):
                                return False

            # Adiciona a ROI após validações
            zone_data.roi_polygons.append(roi_points)
            zone_data.roi_names.append(name)
            zone_data.roi_colors.append(color)

            # Save the project and reload the zones in the active detector
            self.project_manager.save_zone_data(zone_data)
            self.setup_detector_zones()
            log.info("controller.zone.add_roi.success", name=name)
            return True

        except Exception as e:
            log.error("controller.zone.add_roi.error", name=name, error=str(e))
            return False

    def run_live_calibration(self, temp_aquarium_method: str = None):
        """Records a short clip from the live camera and runs aquarium detection.

        Args:
            temp_aquarium_method: Temporary override for aquarium detection method
                ('det' or 'seg'). If None, uses global settings.
        """
        log.info("controller.live_calibration.start")
        if not self.view.camera or not self.view.camera.is_opened():
            self.view.show_error("Erro", "A câmera não está disponível ou aberta.")
            return

        temp_video_path = None
        try:
            # 1. Create a temporary file for the calibration video
            temp_video_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            temp_video_path = temp_video_file.name
            temp_video_file.close()

            # 2. Record a short clip
            w, h = self.view.camera.actual_width, self.view.camera.actual_height
            fps = settings.video_processing.fps
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(temp_video_path, fourcc, fps, (w, h))

            self.view.set_status("Calibrando... Gravando um pequeno clipe.")
            self.view.update_idletasks()

            start_time = time.time()
            while time.time() - start_time < 5:  # Record for 5 seconds
                ret, frame = self.view.camera.get_frame()
                if not ret:
                    break
                writer.write(frame)
            writer.release()
            self.view.set_status("Calibração: Analisando o clipe...")
            self.view.update_idletasks()

            # 3. Run detection on the clip using selected aquarium method
            # Use temporary override if provided, otherwise use global settings
            aquarium_method = (
                temp_aquarium_method or settings.model_selection.aquarium_method
            )
            model_path = self.weight_manager.get_weight_path_by_method(
                aquarium_method, "aquarium"
            )

            if not model_path:
                self.view.show_error(
                    "Erro",
                    f"Não foi possível encontrar um modelo {aquarium_method} para "
                    "detecção do aquário.",
                )
                return

            detector = AquariumDetector(model_path=model_path, mode=aquarium_method)
            polygons = detector.detect_aquariums(temp_video_path)

            if not polygons:
                self.view.show_warning(
                    "Detecção Falhou",
                    "Nenhum aquário foi detectado. "
                    "Por favor, desenhe a área manualmente.",
                )
                return

            main_polygon = polygons[0]
            self.view.setup_interactive_polygon(main_polygon)

        except Exception as e:
            log.error("controller.live_calibration.error", exc_info=True)
            self.view.show_error("Erro na Calibração", f"Ocorreu um erro: {e}")
        finally:
            # 4. Clean up the temporary file
            if temp_video_path and os.path.exists(temp_video_path):
                os.remove(temp_video_path)
            self.view.set_status("Pronto.")

    def _run_countdown(self, duration_s: int, callback):
        """Displays a countdown window and then executes a callback."""
        countdown_window = Toplevel(self.root)
        countdown_window.overrideredirect(True)  # Remove title bar
        countdown_label = Label(
            countdown_window, font=("Helvetica", 150, "bold"), bg="black", fg="white"
        )
        countdown_label.pack(expand=True, fill="both")

        # Center the window
        win_w, win_h = 200, 200
        pos_x = (self.root.winfo_screenwidth() // 2) - (win_w // 2)
        pos_y = (self.root.winfo_screenheight() // 2) - (win_h // 2)
        countdown_window.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")

        def update_timer(seconds_left):
            if seconds_left > 0:
                countdown_label.config(text=str(seconds_left))
                self.root.after(1000, lambda: update_timer(seconds_left - 1))
            else:
                countdown_window.destroy()
                callback()

        update_timer(duration_s)

    def start_recording(self, day: int = None, group: str = None, cobaia: str = None):
        """Starts a recording session (live mode) with zone validation."""
        log.info("controller.recording.start")

        # Live recordings rely on project-wide zones, not per-video ones
        self.project_manager.set_active_zone_video(None)

        # Reset any previous waiting state before starting a new session
        self._clear_external_trigger_wait()

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
                    "(Recomendado para projetos ao vivo)"
                )

                if response:
                    # Run auto-calibration
                    self.run_live_calibration()

                    # Check if calibration was successful
                    zone_data = self.project_manager.get_zone_data()
                    if not zone_data or not zone_data.polygon:
                        self.view.show_error(
                            "Calibração Falhou",
                            "Não foi possível detectar o aquário.\n"
                            "Por favor, desenhe manualmente."
                        )
                        # Switch to zones tab
                        if hasattr(self.view, "notebook") and hasattr(
                            self.view, "zone_tab_frame"
                        ):
                            self.view.notebook.select(self.view.zone_tab_frame)
                        return
                    else:
                        log.info("controller.recording.live_zone_validation.success")
                else:
                    # User declined calibration
                    self.view.show_error(
                        "Zonas Obrigatórias",
                        "Projetos ao vivo requerem definição de zonas.\n"
                        "Defina o polígono principal antes de gravar."
                    )
                    return

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
                    if hasattr(self.view, "notebook") and hasattr(
                        self.view, "zone_tab_frame"
                    ):
                        self.view.notebook.select(self.view.zone_tab_frame)

                    self.view.show_info(
                        "Defina a Arena Principal",
                        "Por favor:\n"
                        "1. Use a câmera ao vivo para calibrar\n"
                        "2. Use 'Detectar Aquário (Auto)' ou\n"
                        "3. Desenhe manualmente o polígono principal\n"
                        "4. Depois volte para iniciar a gravação",
                    )
                    return
                else:
                    # Continua sem arena definida (usando padrão)
                    if not self.view.ask_ok_cancel(
                        "Continuar Sem Arena?",
                        "Deseja continuar a gravação sem arena definida?\n"
                        "(A arena padrão será o frame completo)",
                    ):
                        log.info("controller.recording.cancelled_no_arena")
                        return

                    log.info("controller.recording.proceeding_without_arena")

        # Ensure detector is set up before recording
        if not self.detector:
            if not self.setup_detector():
                self.view.show_error("Erro", "Falha ao configurar detector.")
                return

        # Apply zones to detector
        self.setup_detector_zones()

        # 1. Get recording details
        if not all((day, group, cobaia)):
            # Details not provided, ask user with the new unified dialog
            details = self.view.ask_recording_details_unified()
            if not details:
                log.warning("controller.recording.cancelled_by_user")
                return
            day, group, cobaia = (
                details["day"],
                details["group"],
                details["cobaia"],
            )
        else:
            log.info(
                "controller.recording.details_from_grid",
                day=day,
                group=group,
                cobaia=cobaia,
            )

        # 2. Save the selected day and group for "Smart State Retention"
        self.project_manager.save_last_session_details(day, group)

        # 3. Create output folder with the new naming convention
        folder_name = f"D{day}_G{group}_S{cobaia}"
        output_folder = os.path.join(self.project_manager.project_path, folder_name)
        os.makedirs(output_folder, exist_ok=True)

        project_data = self.project_manager.project_data or {}

        arduino_enabled = False
        if project_data.get("use_arduino"):
            arduino_enabled = self.setup_arduino()
            if not arduino_enabled:
                log.warning(
                    "controller.recording.arduino_unavailable",
                    port=project_data.get("arduino_port"),
                )

        context = {
            "day": day,
            "group": group,
            "cobaia": cobaia,
            "folder_name": folder_name,
            "output_folder": output_folder,
            "arduino_enabled": arduino_enabled,
        }

        arduino_port = (project_data.get("arduino_port") or "").strip()
        if arduino_port:
            context["arduino_port"] = arduino_port

        external_trigger_requested = bool(project_data.get("external_trigger_mode"))
        if external_trigger_requested and not arduino_enabled:
            self.view.show_error(
                "Trigger Externo Indisponível",
                (
                    "O modo de trigger externo exige um Arduino configurado e "
                    "conectado. Verifique o hardware e tente novamente."
                ),
            )
            return

        external_trigger_active = external_trigger_requested and arduino_enabled

        if external_trigger_active:
            self._pending_external_trigger = context
            waiting_message = "Aguardando sinal externo do Arduino para iniciar..."
            if arduino_port:
                waiting_message = f"{waiting_message} (porta {arduino_port})"

            if hasattr(self.view, "show_external_trigger_notice"):
                try:
                    self.view.show_external_trigger_notice(
                        folder_name,
                        day=day,
                        group=group,
                        cobaia=cobaia,
                        port=arduino_port,
                    )
                except TypeError:
                    # Backward compatibility for implementations expecting a single
                    # message
                    self.view.show_external_trigger_notice(waiting_message)

            self.view.update_button_state("start_rec", "disabled")
            self.view.update_button_state("stop_rec", "disabled")
            self.view.set_status(waiting_message)
            self.log_arduino_event(
                "Modo trigger externo habilitado. Aguardando sinal do Arduino."
            )
            return

        self._pending_external_trigger = None
        self._schedule_recording(context, project_data, trigger_source="manual")

    def stop_recording(self):
        """Stops the current recording session."""
        log.info("controller.recording.stop")

        if self._pending_external_trigger:
            self._clear_external_trigger_wait()

        # 1. Cancel any pending timed recording job
        if self.timed_recording_job:
            self.root.after_cancel(self.timed_recording_job)
            self.timed_recording_job = None
            log.info("controller.recording.timed_cancelled")

        # 2. Stop the recorder
        if self.is_recording:
            self.recorder.stop_recording()
            self.is_recording = False

        project_data = getattr(self.project_manager, "project_data", {}) or {}
        if project_data.get("use_arduino"):
            manager = self.arduino_manager
            if manager and manager.is_connected():
                if not manager.send_command(0, source="manual-stop"):
                    log.warning("controller.recording.arduino_stop_failed")
            else:
                log.warning("controller.recording.arduino_stop_not_connected")

        # 3. Update UI
        self.view.update_button_state("start_rec", "normal")
        self.view.update_button_state("stop_rec", "disabled")

    # --- New Refactored Workflows ---

    def cancel_current_analysis(self):
        """Sets the event to signal the running analysis thread to stop."""
        if self.processing_thread and self.processing_thread.is_alive():
            log.info("controller.analysis.cancel_requested")
            self.cancel_event.set()

    def start_single_video_workflow(self, video_path: str, config: dict):
        """Prepares the UI for zone definition in the single video workflow."""
        log.info("workflow.single_video.setup_start", video=video_path)

        self.project_manager.set_active_zone_video(video_path)

        # Use detection methods from config if provided, otherwise fall back to
        # global settings
        animal_method = config.get(
            "animal_method", settings.model_selection.animal_method
        )
        animals_per_aquarium = config.get("animals_per_aquarium", 1)

        # Apply OpenVINO setting from config
        use_openvino = config.get("use_openvino", settings.model_selection.use_openvino)
        self.use_openvino = use_openvino
        log.info("controller.single_video.openvino_set", use_openvino=use_openvino)

        if animal_method == "det" and animals_per_aquarium != 1:
            self.view.show_error(
                "Configuração Inválida",
                (
                    "O modo de detecção (det) para animais só é compatível com 1 "
                    f"animal por aquário.\n"
                    f"Configuração atual: {animals_per_aquarium} "
                    "animais por aquário.\n\n"
                    "Para usar múltiplos animais por aquário, altere o método de "
                    "detecção de animais para 'seg' (segmentação) nas configurações."
                ),
            )
            return

        # Ensure the detector is set up before showing the UI that needs it.
        # This is crucial for the single video flow.
        if not self.detector:
            log.info("controller.single_video.setup_detector")
            # Pass the animal method from config to setup detector with temporary
            # override
            temp_animal_method = config.get("animal_method")
            if not self.setup_detector(temp_animal_method):
                # setup_detector shows its own error message
                return

        # The processing logic has been moved to a new method.
        # This function now only delegates to the UI to prepare the drawing screen.
        self.view.setup_zone_definition_for_single_video(video_path, config)

    def start_single_video_processing(
        self, video_path: str, config: dict, zone_data: ZoneData
    ):
        """Starts the actual processing for a single video after zone setup."""
        log.info("workflow.single_video.processing_start", video=video_path)

        self.project_manager.set_active_zone_video(video_path)

        # Enable single animal mode if animals_per_aquarium == 1
        animals_per_aquarium = config.get("animals_per_aquarium", 1)
        if animals_per_aquarium == 1:
            settings.video_processing.single_animal_per_aquarium = True
            log.info("controller.single_video.single_animal_mode_enabled")

        # 1. Update the detector with the newly created zone data
        # We need to know the video dimensions to set up the zones correctly
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            self.view.show_error(
                "Erro", f"Não foi possível abrir o vídeo: {video_path}"
            )
            return
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        self.detector.set_zones(zone_data, width, height)
        log.info(
            "controller.single_video.zones_set",
            count=len(zone_data.roi_polygons) + (1 if zone_data.polygon else 0),
        )

        # Inform plugin that aquarium region is defined
        if self.detector and hasattr(
            self.detector.plugin, "set_aquarium_region_defined"
        ):
            has_aquarium = bool(zone_data and zone_data.polygon)
            self.detector.plugin.set_aquarium_region_defined(has_aquarium)
            log.info(
                "controller.single_video.aquarium_status",
                defined=has_aquarium,
                plugin=self.detector.plugin.get_name(),
                context=getattr(self.detector.plugin, "_context", "unknown"),
            )

        # 2. Prepare the environment for _process_videos
        scanned_files = ProjectManager.scan_input_paths([video_path])
        if not scanned_files:
            self.view.show_error(
                "Erro", "Não foi possível identificar um arquivo de vídeo válido."
            )
            return
        video_to_process = scanned_files[0]

        video_name = os.path.splitext(os.path.basename(video_path))[0]
        output_dir = os.path.join(os.path.dirname(video_path), f"{video_name}_results")
        os.makedirs(output_dir, exist_ok=True)

        # 3. Call the processing in a background thread
        self.cancel_event.clear()
        self.processing_thread = threading.Thread(
            target=self._process_videos,
            args=([video_to_process], output_dir),
            kwargs={"single_video_config": config},
            daemon=True,
        )
        self.processing_thread.start()

        # 4. Switch to analysis view mode immediately
        self.view.start_analysis_view_mode()

        # Permanecer na tela principal para exibir a barra de progresso
        # self.view._create_welcome_frame()
        self.view.show_info(
            "Análise Iniciada",
            "A análise do vídeo foi iniciada em segundo plano.\n"
            "Você será notificado quando terminar. Os resultados serão salvos em:\n"
            f"{output_dir}",
        )

    def start_project_processing_workflow(self):
        """Adiciona vídeos com validação robusta de zonas"""
        log.info("workflow.project_processing.start")

        if self.processing_thread and self.processing_thread.is_alive():
            self.view.show_warning(
                "Análise em Andamento",
                "Uma análise de vídeo já está em andamento. "
                "Por favor, aguarde ou cancele a análise atual.",
            )
            return

        # Validação 1: Projeto existe
        if not self.project_manager.project_path:
            self.view.show_error("Erro", "Nenhum projeto carregado")
            return

        # Validação 2: Zonas definidas
        zone_data = self.project_manager.get_zone_data()
        if not zone_data or not zone_data.polygon:
            log.warning("workflow.project_processing.no_main_arena")

            response = self.view.ask_ok_cancel(
                "Arena Principal Não Definida",
                "O polígono principal do aquário não foi definido.\n\n"
                "É necessário definir a arena principal para análise precisa.\n"
                "Deseja definir agora antes de processar?",
            )

            if response:
                # Muda para aba de zonas
                if hasattr(self.view, "notebook") and hasattr(
                    self.view, "zone_tab_frame"
                ):
                    self.view.notebook.select(self.view.zone_tab_frame)

                # Carrega frame do primeiro vídeo se disponível
                first_video = self.project_manager.get_next_video()
                if first_video and hasattr(self.view, "load_video_frame_to_canvas"):
                    self.view.load_video_frame_to_canvas(first_video)

                self.view.show_info(
                    "Defina a Arena Principal",
                    "Por favor:\n"
                    "1. Use 'Detectar Aquário (Auto)' ou\n"
                    "2. Desenhe manualmente o polígono principal\n"
                    "3. Depois volte para adicionar vídeos",
                )
                return
            else:
                # Oferece arena padrão como fallback
                if not self.view.ask_ok_cancel(
                    "Usar Arena Padrão?",
                    "Deseja usar o frame completo como arena?\n"
                    "(Não recomendado para análise precisa)",
                ):
                    log.info("workflow.project_processing.cancelled_no_arena")
                    return

                # Cria arena padrão baseada no primeiro vídeo
                first_video = self.project_manager.get_next_video()
                if first_video:
                    import cv2

                    cap = cv2.VideoCapture(first_video)
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    cap.release()

                    default_arena = [[0, 0], [width, 0], [width, height], [0, height]]

                    success = self.set_main_arena_polygon(default_arena)
                    if success:
                        log.info(
                            "workflow.project_processing.default_arena_created",
                            size=f"{width}x{height}",
                        )
                        self.view.show_info(
                            "Arena Padrão Criada",
                            f"Arena padrão criada ({width}x{height})\n"
                            "Recomenda-se ajustar manualmente depois.",
                        )
                    else:
                        self.view.show_error(
                            "Erro", "Não foi possível criar arena padrão"
                        )
                        return
                else:
                    self.view.show_error("Erro", "Nenhum vídeo encontrado no projeto")
                    return

        # Validação 3: Aviso sobre ROIs (opcional, mas informativo)
        if not zone_data.roi_polygons:
            if not self.view.ask_ok_cancel(
                "Nenhuma ROI Definida",
                "Nenhuma Área de Interesse (ROI) foi definida.\n\n"
                "A análise usará apenas a arena principal.\n"
                "Para análises detalhadas, considere definir ROIs.\n\n"
                "Deseja continuar?",
            ):
                log.info("workflow.project_processing.cancelled_by_user_no_roi")
                return

        log.info(
            "workflow.project_processing.zones_validated",
            has_main_arena=bool(zone_data.polygon),
            roi_count=len(zone_data.roi_polygons),
        )

        # 1. Ask user to select files or folders
        paths = self.view.ask_open_filenames(
            "Selecione Vídeos ou Pastas para Adicionar ao Projeto",
            [
                ("Todos os arquivos", "*.*"),
                ("Arquivos de vídeo", "*.mp4 *.avi *.mov"),
                ("Pastas", "*/"),
            ],
        )
        if not paths:
            return

        # 2. Scan the inputs
        scanned_videos = self.project_manager.scan_input_paths(paths)
        if not scanned_videos:
            self.view.show_warning(
                "Nenhum Vídeo Encontrado",
                "Nenhum novo arquivo de vídeo foi encontrado "
                "nos caminhos selecionados.",
            )
            return

        # 3. Handle mixed data scenario
        videos_to_process = []
        with_data = [v for v in scanned_videos if v["has_data"]]
        without_data = [v for v in scanned_videos if not v["has_data"]]

        if with_data and without_data:
            # The complex case: some have data, some don't
            msg = (
                f"{len(with_data)} vídeo(s) já possuem dados de análise.\n"
                f"{len(without_data)} vídeo(s) precisam ser processados.\n\n"
                "Deseja reprocessar os vídeos que já possuem dados?"
            )
            if self.view.ask_ok_cancel("Dados Mistos Encontrados", msg):
                # User wants to re-process everything
                videos_to_process = scanned_videos
            else:
                # User wants to skip re-processing
                videos_to_process = without_data
        elif with_data and not without_data:
            # All selected videos have data
            if self.view.ask_ok_cancel(
                "Dados Encontrados",
                "Todos os vídeos selecionados já possuem dados de análise. "
                "Deseja reprocessá-los todos?",
            ):
                videos_to_process = with_data
            else:
                self.view.show_info(
                    "Processamento Ignorado", "Nenhum novo vídeo foi processado."
                )
                # Still add them to the project for reporting purposes
                self.project_manager.add_video_batch(scanned_videos)
                return
        else:
            # No videos have data, process all of them
            videos_to_process = without_data

        if not videos_to_process:
            self.view.show_info(
                "Processamento Concluído", "Nenhum novo vídeo para processar."
            )
            return

        # 4. Add the batch to the project
        self.project_manager.add_video_batch(scanned_videos)

        # 4.5. Save current interval settings to project data
        try:
            analysis_interval = int(self.view.analysis_interval_var.get())
            display_interval = int(self.view.display_interval_var.get())
            self.project_manager.project_data["analysis_interval_frames"] = (
                analysis_interval
            )
            self.project_manager.project_data["display_interval_frames"] = (
                display_interval
            )
            # Save the project to persist the intervals
            self.project_manager.save_project()
            log.info(
                "controller.workflow.intervals_saved",
                analysis=analysis_interval,
                display=display_interval,
            )
        except (ValueError, AttributeError) as e:
            log.warning("controller.workflow.intervals_save_failed", error=str(e))
            # Use defaults if there's an issue
            self.project_manager.project_data["analysis_interval_frames"] = 10
            self.project_manager.project_data["display_interval_frames"] = 10

        # 5. Process the videos that need it in a background thread
        self.cancel_event.clear()
        self.processing_thread = threading.Thread(
            target=self._process_videos,
            args=(videos_to_process, self.project_manager.project_path),
            daemon=True,
        )
        self.processing_thread.start()

        # 6. Update statuses in project file
        for video in videos_to_process:
            self.project_manager.update_video_status(video["path"], "complete")

        self.view.show_info(
            "Sucesso",
            f"{len(videos_to_process)} vídeo(s) foram processados e adicionados "
            "ao projeto.",
        )

    def process_pending_project_videos(
        self,
        video_paths: list[str] | None = None,
    ) -> None:
        """Processa vídeos já adicionados ao projeto que possuem dados pendentes."""
        log.info(
            "workflow.project_processing.resume_requested",
            targeted=len(video_paths or []),
        )

        if self.processing_thread and self.processing_thread.is_alive():
            self.view.show_warning(
                "Análise em Andamento",
                (
                    "Um processamento já está ativo. Aguarde a conclusão ou "
                    "cancele a análise atual antes de iniciar um novo lote."
                ),
            )
            return

        if not self.project_manager.project_path:
            self.view.show_error("Erro", "Nenhum projeto carregado")
            return

        all_videos = self.project_manager.get_all_videos() or []
        if not all_videos:
            self.view.show_info(
                "Processamento", "Nenhum vídeo cadastrado no projeto atualmente."
            )
            return

        videos_by_norm: dict[str, dict] = {}
        for video in all_videos:
            path_value = video.get("path")
            if isinstance(path_value, str) and path_value:
                videos_by_norm[os.path.normpath(path_value)] = video

        skip_dialog = bool(video_paths)

        if video_paths:
            normalized_targets: list[str] = []
            raw_lookup: dict[str, str] = {}
            for raw_path in video_paths:
                if not isinstance(raw_path, str) or not raw_path:
                    continue
                norm_path = os.path.normpath(raw_path)
                normalized_targets.append(norm_path)
                raw_lookup.setdefault(norm_path, raw_path)

            if not normalized_targets:
                self.view.show_info(
                    "Processamento",
                    "Nenhum vídeo selecionado para processamento.",
                )
                return

            candidate_entries = [
                videos_by_norm[norm_path]
                for norm_path in normalized_targets
                if norm_path in videos_by_norm
            ]

            missing_targets = [
                norm_path
                for norm_path in normalized_targets
                if norm_path not in videos_by_norm
            ]
            if missing_targets:
                sample = [
                    os.path.basename(raw_lookup[norm])
                    for norm in missing_targets[:5]
                ]
                if len(missing_targets) > 5:
                    sample.append(f"... (+{len(missing_targets) - 5})")
                self.view.show_warning(
                    "Vídeos fora do projeto",
                    "Alguns itens selecionados não pertencem ao projeto atual:\n"
                    + "\n".join(sample),
                )

            if not candidate_entries:
                self.view.show_info(
                    "Processamento",
                    "Nenhum dos vídeos selecionados pertence ao projeto ativo.",
                )
                return
        else:
            candidate_entries = [
                video
                for video in all_videos
                if video.get("status") not in {"processed", "complete"}
            ]
            if not candidate_entries:
                self.view.show_info(
                    "Processamento", "Nenhum vídeo pendente para ser processado."
                )
                return

        candidate_paths = [
            video.get("path")
            for video in candidate_entries
            if isinstance(video.get("path"), str) and video.get("path")
        ]
        if not candidate_paths:
            self.view.show_error(
                "Erro",
                (
                    "Não foi possível localizar caminhos válidos para os vídeos "
                    "selecionados."
                ),
            )
            return

        scanned_videos = ProjectManager.scan_input_paths(candidate_paths)
        info_by_norm = {
            os.path.normpath(info["path"]): info
            for info in scanned_videos
            if isinstance(info.get("path"), str)
        }

        missing_files = [
            path
            for path in candidate_paths
            if os.path.normpath(path) not in info_by_norm
        ]
        if missing_files:
            sample_names = [os.path.basename(path) for path in missing_files[:5]]
            if len(missing_files) > 5:
                sample_names.append(f"... (+{len(missing_files) - 5})")
            self.view.show_warning(
                "Vídeos Não Encontrados",
                "Alguns vídeos foram ignorados porque não foram localizados:\n"
                + "\n".join(sample_names),
            )
            log.warning(
                "workflow.project_processing.missing_sources",
                missing=len(missing_files),
            )

        ready_with_trajectory: list[dict] = []
        ready_with_zones: list[dict] = []
        arena_only: list[dict] = []
        without_arena: list[dict] = []

        data_changed = False

        for video in candidate_entries:
            path = video.get("path")
            if not isinstance(path, str) or not path:
                continue

            info = info_by_norm.get(os.path.normpath(path))
            if not info:
                continue

            for key in (
                "has_arena",
                "has_rois",
                "has_trajectory",
                "has_complete_data",
            ):
                new_value = info.get(key, False)
                if video.get(key) != new_value:
                    video[key] = new_value
                    data_changed = True

            if info.get("has_arena"):
                if info.get("has_trajectory"):
                    ready_with_trajectory.append(info)
                elif info.get("has_rois"):
                    ready_with_zones.append(info)
                else:
                    arena_only.append(info)
            else:
                without_arena.append(info)

        if data_changed:
            self.project_manager.save_project()

        if not (ready_with_trajectory or ready_with_zones or arena_only):
            self.view.show_info(
                "Processamento",
                (
                    "Nenhum vídeo elegível foi encontrado com dados "
                    "suficientes para análise."
                ),
            )
            return

        eligible_videos: list[dict] = []

        if skip_dialog:
            eligible_videos.extend(ready_with_trajectory)
            eligible_videos.extend(ready_with_zones)

            if arena_only:
                skipped_names = [
                    os.path.basename(info.get("path", "")) or "(desconhecido)"
                    for info in arena_only[:5]
                ]
                if len(arena_only) > 5:
                    skipped_names.append(f"... (+{len(arena_only) - 5})")
                self.view.show_warning(
                    "Processamento",
                    (
                        "Alguns vídeos selecionados foram ignorados porque não "
                        "possuem ROIs desenhadas:\n"
                        + "\n".join(f"• {name}" for name in skipped_names)
                    ),
                )

            if not eligible_videos:
                self.view.show_info(
                    "Processamento",
                    (
                        "Nenhum dos vídeos selecionados contém arena e ROIs "
                        "suficientes para gerar trajetórias."
                    ),
                )
                return
        else:
            dialog_result = self.view.show_pending_videos_dialog(
                ready_with_trajectory=ready_with_trajectory,
                ready_with_zones=ready_with_zones,
                arena_only=arena_only,
                without_arena=without_arena,
            )

            if not dialog_result or not dialog_result.get("confirmed"):
                log.info("workflow.project_processing.resume_cancelled_by_user")
                return

            include_arena_only = bool(dialog_result.get("include_arena_only"))

            eligible_videos.extend(ready_with_trajectory)
            eligible_videos.extend(ready_with_zones)
            if include_arena_only:
                eligible_videos.extend(arena_only)
            elif arena_only:
                log.info(
                    "workflow.project_processing.skip_arena_only",
                    skipped=len(arena_only),
                )

            if not eligible_videos:
                self.view.show_info(
                    "Processamento",
                    (
                        "Nenhum vídeo foi selecionado para processamento "
                        "neste momento."
                    ),
                )
                return

        zones_updated = False
        for video_info in eligible_videos:
            if video_info.get("has_arena") or video_info.get("has_rois"):
                try:
                    zone_data = ProjectManager.load_zones_from_parquet(video_info)
                except Exception as exc:  # pragma: no cover - defensive
                    log.warning(
                        "workflow.project_processing.zone_load_failed",
                        video=os.path.basename(video_info.get("path", "")),
                        error=str(exc),
                    )
                    zone_data = None
                if zone_data and (zone_data.polygon or zone_data.roi_polygons):
                    self.project_manager.save_zone_data(
                        zone_data, video_info["path"], persist=False
                    )
                    zones_updated = True

        if zones_updated:
            self.project_manager.save_project()

        self.cancel_event.clear()
        self.processing_thread = threading.Thread(
            target=self._process_videos,
            args=(eligible_videos, self.project_manager.project_path),
            daemon=True,
        )
        self.processing_thread.start()

        for video_info in eligible_videos:
            path_value = video_info.get("path")
            if path_value:
                self.project_manager.update_video_status(path_value, "complete")

        self.view.set_status(
            f"Processando {len(eligible_videos)} vídeo(s) com dados existentes..."
        )
        display_names = [
            os.path.basename(video_info.get("path", "")) or "(arquivo desconhecido)"
            for video_info in eligible_videos
        ]
        preview_lines = [f"• {name}" for name in display_names[:5]]
        if len(display_names) > 5:
            preview_lines.append(f"• ... (+{len(display_names) - 5} restante(s))")

        message = (
            f"O processamento de {len(eligible_videos)} vídeo(s) foi iniciado em "
            "segundo plano."
        )
        if preview_lines:
            message += "\n\nFila:\n" + "\n".join(preview_lines)

        self.view.show_info("Processamento Iniciado", message)

        log.info(
            "workflow.project_processing.resume_started",
            total=len(eligible_videos),
            with_trajectory=len(ready_with_trajectory),
            with_zones=len(ready_with_zones),
            targeted=bool(video_paths),
        )

    def generate_parquet_summaries(self, video_paths: list[str]) -> None:
        """Regera arquivos de sumário em Parquet para os vídeos selecionados."""
        log.info(
            "workflow.summaries.generate_requested",
            requested=len(video_paths or []),
        )

        if self.processing_thread and self.processing_thread.is_alive():
            self.view.show_warning(
                "Processamento em andamento",
                (
                    "Aguarde a conclusão do processamento atual antes de gerar "
                    "os sumários."
                ),
            )
            return

        if not video_paths:
            self.view.show_info(
                "Sumários",
                "Nenhum vídeo selecionado para geração de sumários.",
            )
            return

        if not self.project_manager.project_path:
            self.view.show_error(
                "Projeto ausente",
                "Abra um projeto antes de gerar sumários parquet.",
            )
            return

        all_videos = self.project_manager.get_all_videos() or []
        if not all_videos:
            self.view.show_info(
                "Sumários",
                "Nenhum vídeo cadastrado no projeto atualmente.",
            )
            return

        normalized_targets: set[str] = set()
        raw_lookup: dict[str, str] = {}
        for raw_path in video_paths:
            if not isinstance(raw_path, str) or not raw_path:
                continue
            norm_path = os.path.normpath(raw_path)
            normalized_targets.add(norm_path)
            raw_lookup.setdefault(norm_path, raw_path)

        if not normalized_targets:
            self.view.show_info(
                "Sumários",
                "Nenhum vídeo selecionado para geração de sumários.",
            )
            return

        videos_by_norm = {
            os.path.normpath(video.get("path") or ""): video
            for video in all_videos
            if isinstance(video.get("path"), str) and video.get("path")
        }

        selected_videos = [
            videos_by_norm[norm_path]
            for norm_path in normalized_targets
            if norm_path in videos_by_norm
        ]

        missing_targets = [
            norm_path
            for norm_path in normalized_targets
            if norm_path not in videos_by_norm
        ]
        if missing_targets:
            sample = [
                os.path.basename(raw_lookup[norm])
                for norm in list(missing_targets)[:5]
            ]
            if len(missing_targets) > 5:
                sample.append(f"... (+{len(missing_targets) - 5})")
            self.view.show_warning(
                "Vídeos fora do projeto",
                "Alguns itens selecionados não pertencem ao projeto atual:\n"
                + "\n".join(sample),
            )

        if not selected_videos:
            self.view.show_info(
                "Sumários",
                "Nenhum dos vídeos selecionados pertence ao projeto ativo.",
            )
            return

        eligible_videos = [
            video for video in selected_videos if video.get("has_trajectory")
        ]
        if not eligible_videos:
            self.view.show_info(
                "Sumários",
                "Nenhum dos vídeos selecionados possui trajetória gerada.",
            )
            return

        settings_obj = settings

        def worker(target_videos: list[dict]) -> None:
            completed: list[str] = []
            skipped: list[str] = []
            details: list[str] = []
            data_changed = False

            for video in target_videos:
                path = video.get("path")
                if not isinstance(path, str) or not path:
                    skipped.append("(desconhecido)")
                    details.append("• Caminho do vídeo não definido.")
                    continue

                experiment_id = os.path.splitext(os.path.basename(path))[0]
                base_dir = self.project_manager.project_path or os.path.dirname(path)
                results_dir = os.path.join(base_dir, f"{experiment_id}_results")

                parquet_info = video.get("parquet_files") or {}
                trajectory_path = parquet_info.get("trajectory")
                if trajectory_path and not os.path.exists(trajectory_path):
                    trajectory_path = None
                if not trajectory_path:
                    candidates = [
                        os.path.join(
                            results_dir,
                            f"3_CoordMovimento_{experiment_id}.parquet",
                        ),
                        os.path.join(
                            os.path.dirname(path),
                            f"3_CoordMovimento_{experiment_id}.parquet",
                        ),
                    ]
                    for candidate in candidates:
                        if os.path.exists(candidate):
                            trajectory_path = candidate
                            break

                if not trajectory_path:
                    skipped.append(experiment_id)
                    details.append(
                        f"• {experiment_id}: arquivo de trajetória ausente."
                    )
                    continue

                try:
                    trajectory_df = pd.read_parquet(trajectory_path)
                except Exception as exc:  # pragma: no cover - I/O defensive
                    skipped.append(experiment_id)
                    details.append(
                        f"• {experiment_id}: falha ao ler trajetória ({exc})."
                    )
                    continue

                if trajectory_df.empty:
                    skipped.append(experiment_id)
                    details.append(
                        f"• {experiment_id}: trajetória vazia, sumário não gerado."
                    )
                    continue

                self.project_manager.set_active_zone_video(path)
                try:
                    zone_data = self.project_manager.get_zone_data(video_path=path)

                    arena_polygon_px = list(zone_data.polygon or [])

                    if not arena_polygon_px:
                        cap = cv2.VideoCapture(path)
                        if not cap.isOpened():
                            skipped.append(experiment_id)
                            details.append(
                                f"• {experiment_id}: não foi possível abrir o vídeo."
                            )
                            continue
                        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        cap.release()
                        arena_polygon_px = [
                            [0, 0],
                            [frame_width, 0],
                            [frame_width, frame_height],
                            [0, frame_height],
                        ]

                    calib_data = self.project_manager.project_data.get(
                        "calibration",
                        {},
                    )
                    width_cm = calib_data.get("aquarium_width_cm")
                    height_cm = calib_data.get("aquarium_height_cm")
                    if not width_cm or not height_cm:
                        skipped.append(experiment_id)
                        details.append(
                            f"• {experiment_id}: calibração incompleta (px/cm)."
                        )
                        continue

                    cal = Calibration(np.array(arena_polygon_px), width_cm, height_cm)
                    video_width_px, video_height_px = cal.target_dims_px
                    pixelcm_x, pixelcm_y = cal.pixel_per_cm_ratio
                    arena_polygon_warped = cal.transform_points(arena_polygon_px)

                    roi_polygons = list(zone_data.roi_polygons or [])
                    roi_names = list(zone_data.roi_names or [])
                    roi_colors_list = list(zone_data.roi_colors or [])

                    rois: list[ROI] = []
                    for idx, roi_points in enumerate(roi_polygons):
                        warped_points = cal.transform_points(roi_points)
                        roi_points_cm = [
                            (
                                x / pixelcm_x,
                                (video_height_px - y) / pixelcm_y,
                            )
                            for x, y in warped_points
                        ]
                        roi_name = (
                            roi_names[idx]
                            if idx < len(roi_names)
                            else f"ROI {idx + 1}"
                        )
                        rois.append(
                            ROI(name=roi_name, geometry=Polygon(roi_points_cm))
                        )

                    roi_colors = {
                        (
                            roi_names[i]
                            if i < len(roi_names)
                            else f"ROI {i + 1}"
                        ): roi_colors_list[i]
                        for i in range(len(roi_colors_list))
                    }

                    metadata = self.project_manager.get_metadata_for_experiment(
                        experiment_id
                    ) or {
                        "experiment_id": experiment_id,
                        "video_name": experiment_id,
                    }

                    reporter = Reporter(
                        trajectory_df=trajectory_df,
                        metadata=metadata,
                        pixelcm_x=pixelcm_x,
                        pixelcm_y=pixelcm_y,
                        video_height_px=video_height_px,
                        arena_polygon_px=arena_polygon_warped,
                        rois=rois,
                        fps=settings_obj.video_processing.fps,
                        roi_colors=roi_colors,
                        video_path=path,
                        calibration=cal,
                        sharp_turn_threshold=settings_obj.video_processing.sharp_turn_threshold_deg_s,
                        freezing_threshold=settings_obj.video_processing.freezing_velocity_threshold,
                        freezing_duration=settings_obj.video_processing.freezing_min_duration_s,
                    )

                    os.makedirs(results_dir, exist_ok=True)
                    parquet_path = os.path.join(
                        results_dir, f"{experiment_id}_summary.parquet"
                    )
                    reporter.export_summary_data(parquet_path, format="parquet")

                    video.setdefault("parquet_files", {})["summary"] = parquet_path
                    video["has_complete_data"] = True
                    data_changed = True
                    completed.append(experiment_id)
                except Exception as exc:  # pragma: no cover - defensive
                    skipped.append(experiment_id)
                    details.append(
                        f"• {experiment_id}: erro inesperado ({exc})."
                    )
                finally:
                    self.project_manager.set_active_zone_video(None)

            if data_changed:
                self.project_manager.save_project()

            def finalize() -> None:
                if completed:
                    self.view.show_info(
                        "Sumários Gerados",
                        (
                            "Sumários parquet atualizados para "
                            f"{len(completed)} vídeo(s).\n"
                            + "\n".join(f"• {item}" for item in completed)
                        ),
                    )
                    status_msg = (
                        f"Σ Sumários atualizados: {len(completed)} vídeo(s)."
                    )
                else:
                    status_msg = "Nenhum sumário foi atualizado."

                if details:
                    self.view.show_warning(
                        "Vídeos ignorados",
                        "Alguns sumários não puderam ser gerados:\n"
                        + "\n".join(details),
                    )

                self.view.set_status(status_msg)
                self.refresh_project_views(
                    reason=status_msg,
                    append_summary=True,
                )
                self.processing_thread = None

            self.root.after(0, finalize)

        self.processing_thread = threading.Thread(
            target=worker,
            args=(eligible_videos,),
            daemon=True,
        )
        self.processing_thread.start()

    def _run_tracking_if_needed(
        self,
        video_path: str,
        results_dir: str,
        experiment_id: str,
        progress_callback=None,
        calibration_data: dict | None = None,
        analysis_interval_frames: int = 10,
        display_interval_frames: int = 10,
    ) -> tuple[bool, list | None]:
        """
        Checks if a trajectory file exists. If not, runs the tracking process
        to generate it. This is a blocking operation.
        Returns:
            A tuple containing:
            - bool: True if tracking was successful or already existed, False otherwise.
            - list | None: The arena polygon used for tracking, or None if tracking
              failed.
        """
        log.info("controller.tracking.check_or_run", video=experiment_id)
        trajectory_path = os.path.join(
            results_dir, f"3_CoordMovimento_{experiment_id}.parquet"
        )
        arena_polygon = self.project_manager.get_zone_data().polygon
        if os.path.exists(trajectory_path):
            log.info("controller.tracking.exists", path=trajectory_path)
            return True, arena_polygon

        log.info("controller.tracking.generating", video=experiment_id)
        self.view.set_status(f"Gerando trajetória para {experiment_id}...")
        self.view.update_idletasks()

        recorder = Recorder()
        cap = cv2.VideoCapture(video_path)
        try:
            if not cap.isOpened():
                log.error("controller.tracking.video_open_failed", path=video_path)
                return False, None

            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            zone_data = self.project_manager.get_zone_data()
            if not zone_data.polygon:
                log.warning("controller.tracking.no_arena_defined.using_default")
                arena_polygon = [
                    [0, 0],
                    [frame_width, 0],
                    [frame_width, frame_height],
                    [0, frame_height],
                ]
                zone_data.polygon = arena_polygon
            else:
                arena_polygon = zone_data.polygon

            self.detector.set_zones(zone_data, frame_width, frame_height)

            # Inform plugin that aquarium region is defined
            if self.detector and hasattr(
                self.detector.plugin, "set_aquarium_region_defined"
            ):
                has_aquarium = bool(zone_data and zone_data.polygon)
                self.detector.plugin.set_aquarium_region_defined(has_aquarium)
                log.info(
                    "controller.tracking.aquarium_status",
                    defined=has_aquarium,
                    plugin=self.detector.plugin.get_name(),
                    context=getattr(self.detector.plugin, "_context", "unknown"),
                )

            # --- New: Calculate pixel/cm ratio before recording ---
            pixel_per_cm_ratio = None
            cal = None
            if calibration_data:
                width_cm = calibration_data.get("aquarium_width_cm")
                height_cm = calibration_data.get("aquarium_height_cm")
                if width_cm and height_cm and arena_polygon:
                    cal = Calibration(np.array(arena_polygon), width_cm, height_cm)
                    pixel_per_cm_ratio = cal.pixel_per_cm_ratio

            recorder.start_recording(
                output_folder=results_dir,
                frame_width=frame_width,
                frame_height=frame_height,
                zones=zone_data,
                is_video_file=True,
                base_name=experiment_id,
                pixel_per_cm_ratio=pixel_per_cm_ratio,
                calibration=cal,
            )

            frame_num = 0
            processed_frames_count = 0
            detected_frames_count = 0  # Frames that actually have detections
            import time
            start_time = time.time()  # Track processing start time
            log.info("controller.tracking.loop.start", video=experiment_id)
            while not self.cancel_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    log.info("controller.tracking.loop.end_of_video", frame=frame_num)
                    break

                # Check if we should process this frame (analysis interval)
                should_process = frame_num % analysis_interval_frames == 0

                if should_process:
                    detections, _ = self.detector.process_frame(
                        frame, project_type="pre-recorded"
                    )

                    timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                    recorder.write_detection_data(timestamp, frame_num, detections)

                    processed_frames_count += 1

                    # Count frames that actually have detections
                    if detections:
                        detected_frames_count += 1

                # Update GUI display every processed frame for smoother visualization
                if progress_callback and should_process:
                    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    progress_fraction = (
                        (frame_num + 1) / total_frames if total_frames > 0 else 0
                    )

                    # Prepare statistics for GUI update
                    stats = {
                        'total_frames': total_frames,
                        'current_frame': frame_num + 1,  # For accurate ETA calculation
                        'processed_frames': processed_frames_count,
                        'detected_frames': detected_frames_count,
                        'start_time': start_time
                    }

                    # Always draw overlay on processed frames
                    self.detector.draw_overlay(frame, detections)
                    progress_callback(
                        progress_fraction, "Gerando trajetória...", frame, stats
                    )

                frame_num += 1

            recorder.stop_recording()  # This saves the parquet file
            log.info("controller.tracking.success", path=trajectory_path)
            self.view.set_status(f"Trajetória para {experiment_id} gerada.")
            return True, arena_polygon

        except Exception as e:
            log.error(
                "controller.tracking.error",
                video=experiment_id,
                error=str(e),
                exc_info=True,
            )
            self.view.show_error(
                "Erro de Rastreamento",
                f"Ocorreu um erro inesperado ao gerar a trajetória "
                f"para {experiment_id}:\n{e}",
            )
            return False, None
        finally:
            if cap.isOpened():
                cap.release()

    def apply_project_settings_to_batch(self, videos: list):
        """Aplica configurações do projeto a novos vídeos"""
        if not self.project_manager.project_path:
            log.warning("controller.batch.no_project_path")
            return False

        # Obtém configurações do projeto
        project_data = self.project_manager.project_data
        zone_data = self.project_manager.get_zone_data()
        calibration = project_data.get("calibration", {})

        log.info(
            "controller.batch.apply_settings",
            videos_count=len(videos),
            has_zones=bool(zone_data and zone_data.polygon),
            has_calibration=bool(calibration),
            has_rois=len(zone_data.roi_polygons) if zone_data else 0,
        )

        # Para cada vídeo no lote
        settings_applied = 0
        for video_info in videos:
            video_path = video_info.get("path")
            if not video_path:
                continue

            video_name = os.path.splitext(os.path.basename(video_path))[0]

            # Cria diretório de resultados
            results_dir = os.path.join(
                self.project_manager.project_path, f"{video_name}_results"
            )

            try:
                os.makedirs(results_dir, exist_ok=True)

                # Salva configurações completas do projeto
                settings_file = os.path.join(results_dir, "project_settings.json")
                settings_data = {
                    "project_name": self.project_manager.get_project_name(),
                    "active_weight": project_data.get("active_weight"),
                    "use_openvino": project_data.get("use_openvino", False),
                    "calibration": calibration,
                    "video_settings": video_info,
                    "timestamp": self.project_manager.project_data.get("timestamp"),
                    "analysis_interval_frames": project_data.get(
                        "analysis_interval_frames", 10
                    ),
                    "display_interval_frames": project_data.get(
                        "display_interval_frames", 10
                    ),
                    "detector_config": self.project_manager.get_detector_state(),
                }

                import json

                with open(settings_file, "w") as f:
                    json.dump(settings_data, f, indent=2)

                # Salva zonas no diretório de resultados
                if zone_data and (zone_data.polygon or zone_data.roi_polygons):
                    zones_file = os.path.join(results_dir, "zones.json")

                    from dataclasses import asdict

                    with open(zones_file, "w") as f:
                        json.dump(asdict(zone_data), f, indent=2)

                    log.info(
                        "controller.batch.zones_saved",
                        video=video_name,
                        zones_file=zones_file,
                        settings_file=settings_file,
                    )

                settings_applied += 1

            except Exception as e:
                log.error(
                    "controller.batch.settings_save_error",
                    video=video_name,
                    error=str(e),
                )

        log.info(
            "controller.batch.settings_applied",
            total_videos=len(videos),
            successful=settings_applied,
        )

        return settings_applied == len(videos)

    def _process_videos(
        self,
        videos_to_process: list[dict],
        output_base_dir: str,
        single_video_config: dict | None = None,
    ):
        """
        Private helper to process a list of videos and save results. This is
        designed to be run in a background thread.
        """
        log.info("controller.processing.start", count=len(videos_to_process))

        # Resolve intervals from config
        analysis_interval_frames = 10  # default
        display_interval_frames = 10  # default

        if single_video_config:
            # For single video: take from config dict if present, else defaults
            analysis_interval_frames = single_video_config.get(
                "analysis_interval_frames", 10
            )
            display_interval_frames = single_video_config.get(
                "display_interval_frames", 10
            )
            log.info(
                "controller.processing.intervals_single_video",
                analysis_interval=analysis_interval_frames,
                display_interval=display_interval_frames,
                config_keys=list(single_video_config.keys()),
            )
        else:
            # For batch projects: read from project_data
            if (
                hasattr(self.project_manager, "project_data")
                and self.project_manager.project_data
            ):
                analysis_interval_frames = self.project_manager.project_data.get(
                    "analysis_interval_frames", 10
                )
                display_interval_frames = self.project_manager.project_data.get(
                    "display_interval_frames", 10
                )

        # Aplica configurações do projeto ao lote ANTES do processamento
        if not single_video_config:  # Só para projetos batch, não single video
            settings_success = self.apply_project_settings_to_batch(videos_to_process)
            if not settings_success:
                log.warning("controller.processing.settings_partial_failure")

        was_cancelled = False
        final_output_dir = output_base_dir

        try:
            self.root.after(0, self.view.show_progress_bar)
            self.root.after(
                0,
                lambda: self.view.set_status(
                    f"Iniciando processamento para {len(videos_to_process)} vídeos..."
                ),
            )

            # Default to project-wide zones until a video is activated
            self.project_manager.set_active_zone_video(None)

            for i, video_info in enumerate(videos_to_process):
                if self.cancel_event.is_set():
                    was_cancelled = True
                    log.info("controller.processing.cancelled_by_user")
                    break

                video_path = video_info["path"]
                experiment_id = os.path.splitext(os.path.basename(video_path))[0]

                self.project_manager.set_active_zone_video(video_path)

                def progress_callback(
                    progress_fraction, status_message, frame=None, stats=None
                ):
                    if self.cancel_event.is_set():
                        return
                    overall_progress = (
                        f"Processando {i + 1}/{len(videos_to_process)}: {experiment_id}"
                    )
                    step_status = f"Etapa: {status_message}"
                    self.root.after(
                        0,
                        lambda: self.view.set_status(
                            f"{overall_progress} - {step_status}"
                        ),
                    )
                    self.root.after(
                        0, lambda p=progress_fraction: self.view.update_progress(p)
                    )
                    # Update analysis progress overlay as well
                    self.root.after(
                        0,
                        lambda p=progress_fraction, s=step_status: (
                            self.view.update_analysis_progress(p, s)
                        ),
                    )
                    # Update processing statistics in real-time
                    if stats:
                        self.root.after(
                            0,
                            lambda: self.view.update_processing_stats(
                                total_frames=stats.get('total_frames'),
                                processed_frames=stats.get('processed_frames'),
                                detected_frames=stats.get('detected_frames'),
                                start_time=stats.get('start_time'),
                                current_frame=stats.get('current_frame')
                            )
                        )
                    if frame is not None:
                        # A GUI desenhará as zonas automaticamente
                        self.view.display_frame(frame)

                # Display first frame before starting
                try:
                    cap = cv2.VideoCapture(video_path)
                    ret, frame = cap.read()
                    if ret:
                        self.root.after(0, lambda f=frame: self.view.display_frame(f))
                    cap.release()
                except Exception as e:
                    log.warning("controller.progress.frame_display_error", error=str(e))

                results_dir = output_base_dir
                if self.project_manager.project_path and not single_video_config:
                    results_dir = os.path.join(
                        output_base_dir, f"{experiment_id}_results"
                    )
                os.makedirs(results_dir, exist_ok=True)

                tracking_success, arena_polygon_px = self._run_tracking_if_needed(
                    video_path,
                    results_dir,
                    experiment_id,
                    progress_callback,
                    calibration_data=single_video_config,
                    analysis_interval_frames=analysis_interval_frames,
                    display_interval_frames=display_interval_frames,
                )
                if self.cancel_event.is_set():
                    was_cancelled = True
                    break
                if not tracking_success:
                    continue

                if not arena_polygon_px:
                    cap = cv2.VideoCapture(video_path)
                    if cap.isOpened():
                        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        arena_polygon_px = [[0, 0], [w, 0], [w, h], [0, h]]
                        cap.release()

                trajectory_path = os.path.join(
                    results_dir, f"3_CoordMovimento_{experiment_id}.parquet"
                )
                if not os.path.exists(trajectory_path):
                    self.root.after(
                        0,
                        lambda: self.view.show_error(
                            "Erro de Processamento",
                            f"Falha ao gerar arquivo de trajetória para "
                            f"{experiment_id}.",
                        ),
                    )
                    continue
                trajectory_df = pd.read_parquet(trajectory_path)

                if single_video_config:
                    width_cm = single_video_config.get("aquarium_width_cm")
                    height_cm = single_video_config.get("aquarium_height_cm")
                    st_thresh = single_video_config.get(
                        "sharp_turn_threshold_deg_s",
                        settings.video_processing.sharp_turn_threshold_deg_s,
                    )
                    fz_thresh = single_video_config.get(
                        "freezing_velocity_threshold",
                        settings.video_processing.freezing_velocity_threshold,
                    )
                    fz_dur = single_video_config.get(
                        "freezing_min_duration_s",
                        settings.video_processing.freezing_min_duration_s,
                    )
                    metadata = dict(single_video_config)
                    metadata.setdefault("experiment_id", experiment_id)
                    metadata.setdefault("video_name", experiment_id)
                    if not metadata.get("group_id"):
                        metadata["group_id"] = "single_video"
                else:
                    proj_data = self.project_manager.project_data
                    calib_data = proj_data.get("calibration", {})
                    width_cm = calib_data.get("aquarium_width_cm")
                    height_cm = calib_data.get("aquarium_height_cm")
                    st_thresh = settings.video_processing.sharp_turn_threshold_deg_s
                    fz_thresh = settings.video_processing.freezing_velocity_threshold
                    fz_dur = settings.video_processing.freezing_min_duration_s
                    metadata = self.project_manager.get_metadata_for_experiment(
                        experiment_id
                    )
                    if not metadata:
                        metadata = self.project_manager.derive_processing_metadata(
                            experiment_id,
                            video_path,
                        )
                        log.info(
                            "controller.processing.metadata_fallback", 
                            experiment_id=experiment_id,
                            fields=list(metadata.keys()),
                        )

                zone_data = self.project_manager.get_zone_data()
                if not all([width_cm, height_cm, arena_polygon_px]):
                    self.root.after(
                        0,
                        lambda: self.view.show_error(
                            "Erro de Processamento", "Dados de calibração incompletos."
                        ),
                    )
                    continue

                cal = Calibration(np.array(arena_polygon_px), width_cm, height_cm)
                # Get warped dimensions from calibration
                video_width_px, video_height_px = cal.target_dims_px
                pixelcm_x, pixelcm_y = cal.pixel_per_cm_ratio

                # Transform the original arena polygon to warped space
                # This preserves the user's original drawing shape
                arena_polygon_warped = cal.transform_points(arena_polygon_px)

                # Transform ROI polygons from original video coordinates to warped
                # coordinates
                rois = []
                for i, p in enumerate(zone_data.roi_polygons):
                    # Transform ROI points from original to warped space
                    warped_roi_points = cal.transform_points(p)
                    # Convert warped points to cm
                    roi_points_cm = [
                        (x / pixelcm_x, (video_height_px - y) / pixelcm_y)
                        for x, y in warped_roi_points
                    ]
                    rois.append(
                        ROI(
                            name=zone_data.roi_names[i],
                            geometry=Polygon(roi_points_cm),
                        )
                    )

                roi_colors = {
                    zone_data.roi_names[i]: color
                    for i, color in enumerate(zone_data.roi_colors)
                }

                reporter = Reporter(
                    trajectory_df=trajectory_df,
                    metadata=metadata,
                    pixelcm_x=pixelcm_x,
                    pixelcm_y=pixelcm_y,
                    video_height_px=video_height_px,
                    arena_polygon_px=arena_polygon_warped,
                    rois=rois,
                    fps=settings.video_processing.fps,
                    roi_colors=roi_colors,
                    video_path=video_path,
                    calibration=cal,
                    sharp_turn_threshold=st_thresh,
                    freezing_threshold=fz_thresh,
                    freezing_duration=fz_dur,
                )
                summary_parquet_path = os.path.join(
                    results_dir, f"{experiment_id}_summary.parquet"
                )
                summary_excel_path = os.path.join(
                    results_dir, f"{experiment_id}_summary.xlsx"
                )
                report_docx_path = os.path.join(
                    results_dir, f"{experiment_id}_report.docx"
                )

                reporter.export_summary_data(
                    summary_parquet_path,
                    format="parquet",
                )
                reporter.export_summary_data(
                    summary_excel_path,
                    format="excel",
                )
                reporter.export_individual_report_step_by_step(
                    report_docx_path,
                    progress_callback,
                )

                if not single_video_config:
                    self.project_manager.register_processing_outputs(
                        video_path,
                        results_dir=results_dir,
                        trajectory_path=trajectory_path,
                        summary_parquet=summary_parquet_path,
                        summary_excel=summary_excel_path,
                        report_path=report_docx_path,
                    )
                    self.refresh_project_views(
                        reason="processing_progress",
                        append_summary=True,
                    )

        except Exception as e:
            log.error("controller.processing.error", error=str(e), exc_info=True)
            self.root.after(
                0,
                lambda e=e: self.view.show_error(
                    "Erro na Análise", f"Ocorreu um erro inesperado: {e}"
                ),
            )
        finally:
            self.project_manager.set_active_zone_video(None)
            self.root.after(0, self.view.stop_analysis_view_mode)
            self.root.after(0, self.view.hide_progress_bar)
            if was_cancelled:
                self.root.after(
                    0,
                    lambda: self.view.show_info(
                        "Cancelado", "A análise de vídeo foi cancelada."
                    ),
                )
            elif videos_to_process and not was_cancelled:
                msg = f"Análise concluída. Resultados salvos em:\n{final_output_dir}"
                self.root.after(0, lambda: self.view.show_info("Sucesso", msg))
            self.root.after(0, lambda: self.view.set_status("Pronto."))
            self.refresh_project_views()

    def generate_report(self, videos: list[dict], report_type: str = "unified"):
        """
        Generates a report from a list of processed videos.
        """
        log.info("reports.generate.start", count=len(videos), type=report_type)
        if not videos:
            self.view.show_warning(
                "Nenhum Vídeo", "Nenhum vídeo selecionado para o relatório."
            )
            return

        all_tidy_data = []
        if self.project_manager.project_path:
            project_path = self.project_manager.project_path
        else:
            project_path = os.path.dirname(videos[0]["path"])

        for video_info in videos:
            experiment_id = os.path.splitext(os.path.basename(video_info["path"]))[0]
            results_dir = os.path.join(project_path, f"{experiment_id}_results")
            summary_path = os.path.join(results_dir, f"{experiment_id}_summary.parquet")

            if os.path.exists(summary_path):
                try:
                    df = pd.read_parquet(summary_path)
                    all_tidy_data.append(df)
                except Exception as e:
                    log.warning("reports.load.error", path=summary_path, error=e)
            else:
                log.warning("reports.load.not_found", path=summary_path)

        if not all_tidy_data:
            self.view.show_error(
                "Erro no Relatório",
                "Não foi possível encontrar dados de resumo para os vídeos "
                "selecionados.",
            )
            return

        aggregated_df = pd.concat(all_tidy_data, ignore_index=True)
        save_path = self.view.ask_save_filename(
            title=f"Salvar Relatório {report_type.capitalize()}",
            defaultextension=".xlsx",
            initialfile=f"{report_type}_report.xlsx",
            filetypes=[
                ("Pasta de Trabalho do Excel", "*.xlsx"),
                ("Arquivo CSV", "*.csv"),
                ("Arquivo Parquet", "*.parquet"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if not save_path:
            return

        # Determine format from extension and export data
        file_extension = os.path.splitext(save_path)[1].lower()
        if file_extension == ".xlsx":
            aggregated_df.to_excel(save_path, index=False)
        elif file_extension == ".csv":
            aggregated_df.to_csv(save_path, index=False)
        elif file_extension == ".parquet":
            aggregated_df.to_parquet(save_path, index=False)
        else:
            # Default to Excel if extension is unknown or missing
            if not file_extension:
                save_path += ".xlsx"
            aggregated_df.to_excel(save_path, index=False)

        # Also generate the visual .docx report, except for parquet
        if file_extension != ".parquet":
            docx_path = os.path.splitext(save_path)[0] + "_report.docx"
            Reporter.export_project_report(aggregated_df, docx_path)

        self.view.show_info("Relatório Gerado", f"Relatório salvo em:\n{save_path}")

    def run_model_diagnostic(self, config: dict):
        """
        Prepares for and launches the diagnostic test in a background thread.
        """
        log.info("controller.diagnostic.start", config=config)
        self.view.set_status("Iniciando diagnóstico do modelo...")
        self.view.update_idletasks()

        model_to_test = config["model_to_test"]
        active_weight_details = self.weight_manager.get_weight_details(
            self.active_weight_name
        )
        log.info(
            "controller.diagnostic.active_weight",
            active_weight_name=self.active_weight_name,
            pytorch_path=(
                active_weight_details.get("path") if active_weight_details else None
            ),
            openvino_path=(
                active_weight_details.get("openvino_path")
                if active_weight_details
                else None
            ),
        )
        if not active_weight_details:
            self.view.show_error("Erro", "Nenhum peso ativo selecionado.")
            return

        # --- Pre-flight checks (OpenVINO conversion) ---
        if model_to_test in ["OpenVINO", "Ambos"]:
            ov_path = active_weight_details.get("openvino_path")
            if not ov_path or not os.path.exists(ov_path):
                if self.view.ask_ok_cancel(
                    "Converter Modelo?",
                    "O modelo OpenVINO não foi encontrado. Deseja convertê-lo agora?",
                ):
                    self.convert_active_weight_to_openvino()
                    # Refresh details after conversion
                    active_weight_details = self.weight_manager.get_weight_details(
                        self.active_weight_name
                    )
                    if not active_weight_details.get("openvino_path"):
                        self.view.show_error(
                            "Erro", "A conversão para OpenVINO falhou."
                        )
                        return
                else:
                    log.warning("diagnostic.openvino.conversion_skipped")
                    # If user skips conversion, modify config to only run YOLO if
                    # possible
                    if model_to_test == "Ambos":
                        config["model_to_test"] = "YOLO (PyTorch)"
                    else:  # model_to_test was 'OpenVINO'
                        self.view.set_status("Diagnóstico cancelado.")
                        return

        # --- Launch background thread ---
        self.cancel_event.clear()
        thread = threading.Thread(
            target=self._diagnostic_processing_thread,
            args=(config, active_weight_details),
            daemon=True,
        )
        thread.start()

    def _diagnostic_processing_thread(self, config: dict, weight_details: dict):
        """
        The actual diagnostic processing logic that runs in a background thread.
        """
        video_path = config["video_path"]
        frames_to_analyze = config["frames_to_analyze"]
        conf_threshold = config["confidence_threshold"]
        model_to_test = config["model_to_test"]
        results = {}

        # --- Model Loading ---
        yolo_model = None
        openvino_model = None

        try:
            if model_to_test in ["YOLO (PyTorch)", "Ambos"]:
                if not ULTRALYTICS_AVAILABLE:
                    log.error("diagnostic.yolo.unavailable")
                    config["update_progress"](
                        "Erro: YOLO não está disponível (ultralytics não instalado)"
                    )
                    return

                yolo_model = YOLO(weight_details["path"])
                # Define contexto diagnóstico
                if hasattr(yolo_model, "set_context"):
                    yolo_model.set_context("diagnostic")
                    log.info("diagnostic.thread.yolo_context_set", context="diagnostic")
                results["YOLO (PyTorch)"] = []

            if model_to_test in ["OpenVINO", "Ambos"]:
                ov_path = weight_details.get("openvino_path")
                if ov_path and os.path.exists(ov_path):
                    plugin_class = DETECTOR_PLUGINS.get("OpenVINO")
                    if plugin_class:
                        openvino_model = plugin_class(ov_path)
                        # Verify the plugin has the required predict method
                        if not hasattr(openvino_model, "predict"):
                            log.error(
                                "diagnostic.thread.missing_predict_method",
                                plugin_class=str(plugin_class),
                            )
                            self.root.after(
                                0,
                                self.view.show_error,
                                "Erro de Plugin",
                                "O plugin OpenVINO não possui o método predict "
                                "necessário para diagnóstico.",
                            )
                            return
                        # Set diagnostic context to allow all classes
                        if hasattr(openvino_model, "set_context"):
                            openvino_model.set_context("diagnostic")
                            log.info(
                                "diagnostic.thread.openvino_context_set",
                                context="diagnostic",
                            )
                        results["OpenVINO"] = []
                        log.info("diagnostic.thread.openvino_loaded", path=ov_path)
        except Exception as e:
            log.error("diagnostic.thread.load_error", exc_info=True)
            self.root.after(
                0,
                self.view.show_error,
                "Erro ao Carregar Modelo",
                f"Falha: {e}",
            )
            return

        # --- Video Processing ---
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            self.root.after(
                0,
                self.view.show_error,
                "Erro",
                f"Não foi possível abrir o vídeo: {video_path}",
            )
            return

        for frame_count in range(frames_to_analyze):
            if self.cancel_event.is_set():
                break
            ret, frame = cap.read()
            if not ret:
                break

            status_msg = f"Analisando frame {frame_count + 1}/{frames_to_analyze}..."
            self.root.after(0, self.view.set_status, status_msg)

            if yolo_model:
                preds = yolo_model.predict(frame, conf=conf_threshold, verbose=False)
                results.setdefault("YOLO (PyTorch)", []).append(preds[0])

            if openvino_model:
                try:
                    log.debug(
                        "diagnostic.thread.openvino_predict_start",
                        frame=frame_count + 1,
                    )
                    preds = openvino_model.predict(frame, conf_threshold)
                    log.debug(
                        "diagnostic.thread.openvino_predict_success",
                        frame=frame_count + 1,
                        detections=len(preds),
                    )
                    results.setdefault("OpenVINO", []).append(preds)
                except Exception as e:
                    log.error(
                        "diagnostic.thread.openvino_predict_error",
                        frame=frame_count + 1,
                        exc_info=True,
                    )
                    self.root.after(
                        0,
                        self.view.show_error,
                        "Erro de Inferência OpenVINO",
                        f"Falha na inferência do frame {frame_count + 1}: {e}",
                    )
                    return
        cap.release()

        # --- Schedule report generation on main thread ---
        self.root.after(0, self._finish_diagnostic_and_save_report, config, results)

    def _finish_diagnostic_and_save_report(self, config, results):
        """Formats and saves the report. Runs on the main UI thread."""
        report_str = self._format_diagnostic_report(config, results)
        save_path = self.view.ask_save_filename(
            title="Salvar Relatório de Diagnóstico",
            defaultextension=".txt",
            initialfile="diagnostic_report.txt",
            filetypes=[("Arquivos de Texto", "*.txt")],
        )

        if save_path:
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(report_str)
                self.view.show_info(
                    "Sucesso", f"Relatório de diagnóstico salvo em:\n{save_path}"
                )
            except IOError as e:
                self.view.show_error(
                    "Erro ao Salvar", f"Não foi possível salvar o arquivo: {e}"
                )

        self.view.set_status("Diagnóstico concluído. Pronto.")

    def _format_diagnostic_report(self, config, results) -> str:
        """Formats the collected diagnostic data into a string."""
        report_lines = [
            "Relatório de Diagnóstico do Modelo",
            "-----------------------------------",
            f"- Vídeo: {config['video_path']}",
            f"- Frames Analisados: {config['frames_to_analyze']}",
            f"- Limiar de Confiança: {config['confidence_threshold']}",
            "-----------------------------------",
            "",
        ]

        for model_name, preds_list in results.items():
            report_lines.append(f"--- [ RESULTADOS {model_name.upper()} ] ---")
            report_lines.append("")

            for i, preds in enumerate(preds_list):
                frame_num = i + 1
                report_lines.append(f"Frame {frame_num}:")

                detections = []
                mask_only_detections = []

                # Handle ultralytics results object
                if hasattr(preds, "boxes") or hasattr(preds, "masks"):
                    # Processa boxes com suas máscaras
                    if preds.boxes is not None:
                        for j, box in enumerate(preds.boxes):
                            class_id = int(box.cls)
                            class_name = preds.names.get(class_id, "desconhecido")
                            conf = float(box.conf)
                            bbox = [int(coord) for coord in box.xyxy[0]]

                            # Verifica se tem máscara
                            has_mask = (
                                preds.masks is not None
                                and preds.masks.xy is not None
                                and j < len(preds.masks.xy)
                            )
                            mask_info = (
                                f", Máscara: {len(preds.masks.xy[j])} pontos"
                                if has_mask
                                else ""
                            )

                            detections.append(
                                f"  - Classe {class_id} ('{class_name}'), "
                                f"Conf: {conf:.2f}, BBox: {bbox}{mask_info}"
                            )

                    # Processa máscaras sem boxes (órfãs)
                    if preds.masks is not None and preds.masks.xy is not None:
                        num_boxes = len(preds.boxes) if preds.boxes else 0
                        for j in range(num_boxes, len(preds.masks.xy)):
                            mask = preds.masks.xy[j]
                            x_min = int(mask[:, 0].min())
                            y_min = int(mask[:, 1].min())
                            x_max = int(mask[:, 0].max())
                            y_max = int(mask[:, 1].max())
                            area = (x_max - x_min) * (y_max - y_min)

                            mask_only_detections.append(
                                f"  - [MÁSCARA SEM BOX] Provável Aquário, "
                                f"BBox aprox: [{x_min}, {y_min}, {x_max}, {y_max}], "
                                f"Área: {area}, Pontos: {len(mask)}"
                            )

                # Handle OpenVINO plugin format
                elif isinstance(preds, list):
                    for det in preds:
                        class_id = det["class_id"]
                        class_name = det["class_name"]
                        conf = det["confidence"]
                        bbox = det["box"]
                        mask_info = (
                            f", Máscara: {det.get('mask_points', 0)} pontos"
                            if det.get("has_mask")
                            else ""
                        )

                        detections.append(
                            f"  - Classe {class_id} ('{class_name}'), "
                            f"Conf: {conf:.2f}, BBox: {bbox}{mask_info}"
                        )

                # Adiciona detecções ao relatório
                if detections:
                    report_lines.extend(detections)
                if mask_only_detections:
                    report_lines.append(
                        "  Máscaras sem bounding box (possíveis aquários):"
                    )
                    report_lines.extend(mask_only_detections)
                if not detections and not mask_only_detections:
                    report_lines.append("  - Nenhuma detecção encontrada.")

                report_lines.append("")

            report_lines.append("")  # Spacer between models

        return "\n".join(report_lines)
