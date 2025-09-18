from __future__ import annotations

import os
import tempfile
import threading
import time
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
from zebtrack.io.recorder import Recorder
from zebtrack.plugins import DETECTOR_PLUGINS
from zebtrack.settings import settings
from zebtrack.ui.gui import ApplicationGUI
from zebtrack.utils import IntegrityError

log = structlog.get_logger()


class AppController:
    def __init__(self, root):
        self.root = root
        self.view = ApplicationGUI(root, self)
        self.project_manager = ProjectManager()
        self.weight_manager = WeightManager()
        self.detector = None
        self.recorder = Recorder()
        self.report_results_paths = {}
        self.is_recording = False
        self.timed_recording_job = None
        # Other initializations...
        self.program_exit_event = threading.Event()
        self.processing_thread: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.pending_single_video_analysis = None

        # New state variables for model management
        self.active_weight_name, _ = self.weight_manager.get_default_weight()
        if self.active_weight_name is None:
            self.active_weight_name = ""
            log.warning("controller.init.no_default_weight")
        self.use_openvino = False  # Default to not using OpenVINO

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

        log.info("controller.shutdown.complete")

    def close_project(self):
        self.project_manager = ProjectManager()
        self.view._create_welcome_frame()

    def create_project_workflow(self, **kwargs):
        # Add the currently selected model info to the project data
        kwargs["active_weight"] = self.active_weight_name
        kwargs["use_openvino"] = self.use_openvino
        if self.project_manager.create_new_project(**kwargs):
            if self.setup_detector():
                self.view._load_project_view()
        else:
            self.view.show_error("Erro", "Falha ao criar o novo projeto.")

    def open_project_workflow(self, project_path):
        """Carrega projeto e configura tudo automaticamente"""
        log.info("controller.load_project.start", path=project_path)

        success = self.project_manager.load_project(project_path)

        if not success:
            self.view.show_error("Erro", "Não foi possível carregar o projeto")
            return False

        # Auto-configura o detector com o peso do projeto
        self.active_weight_name = self.project_manager.project_data.get("active_weight")
        if self.active_weight_name:
            log.info(
                "controller.load_project.weight_restored",
                weight=self.active_weight_name
            )

        # Auto-configura OpenVINO se estava ativo
        self.use_openvino = self.project_manager.project_data.get("use_openvino", False)
        log.info(
            "controller.load_project.openvino_restored", use_openvino=self.use_openvino
        )

        # Atualiza interface com configurações restauradas
        self.view.update_openvino_checkbox(self.use_openvino)
        if self.active_weight_name:
            self.view.set_active_weight_in_dropdown(self.active_weight_name)
        self.update_openvino_status()

        # Inicializa detector
        if not self.setup_detector():
            log.warning("controller.load_project.detector_setup_failed")
        else:
            # Carrega interface do projeto
            self.view._load_project_view()

        # NOVO: Carrega e aplica zonas salvas
        zone_data = self.project_manager.get_zone_data()
        if zone_data and (zone_data.polygon or zone_data.roi_polygons):
            log.info("controller.load_project.zones_found",
                    has_polygon=bool(zone_data.polygon),
                    roi_count=len(zone_data.roi_polygons))

            # Configura zonas no detector
            self.setup_detector_zones()

            # Atualiza visualização das zonas na GUI
            if hasattr(self.view, 'redraw_zones_from_project_data'):
                self.view.redraw_zones_from_project_data()
            if hasattr(self.view, 'update_zone_listbox'):
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
            f"• OpenVINO: {'✓' if self.use_openvino else '✗'}"
        )

        log.info("controller.load_project.complete",
                project=project_name,
                videos=videos_count,
                has_zones=bool(zone_data and zone_data.polygon),
                rois=roi_count)

        return True

    def setup_detector(self) -> bool:
        """Initializes the detector instance based on the globally selected model."""
        log.info(
            "detector.setup.start",
            active_weight=self.active_weight_name,
            use_openvino=self.use_openvino,
        )
        if not self.active_weight_name:
            self.view.show_error(
                "Erro de Detector", "Nenhum peso ativo está selecionado."
            )
            return False

        weight_details = self.weight_manager.get_weight_details(
            self.active_weight_name
        )
        if not weight_details:
            self.view.show_error(
                "Erro de Detector",
                "Não foi possível encontrar detalhes para o peso: "
                f"{self.active_weight_name}",
            )
            return False

        try:
            if self.use_openvino:
                plugin_name = "OpenVINO"
                model_path = weight_details.get("openvino_path")
                if not model_path or not os.path.exists(model_path):
                    raise ValueError(
                        "Caminho do modelo OpenVINO não encontrado ou inválido. "
                        "Por favor, converta o modelo primeiro."
                    )
            else:
                plugin_name = "YOLO (Ultralytics)"
                model_path = weight_details.get("path")
                if not model_path or not os.path.exists(model_path):
                    raise ValueError(
                        "Caminho do modelo YOLO .pt não encontrado ou inválido."
                    )

            plugin_class = DETECTOR_PLUGINS.get(plugin_name)
            if not plugin_class:
                raise ValueError(f"Detector plugin '{plugin_name}' not found.")

            log.info("detector.load.start", plugin=plugin_name, path=model_path)
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

            # Define contexto inicial baseado no modo
            if hasattr(plugin_instance, 'set_context'):
                plugin_instance.set_context('tracking')
                log.info("detector.context.set", context='tracking')

            log.info("detector.setup.success")
            return True
        except (ValueError, FileNotFoundError, IntegrityError) as e:
            log.error("detector.init.failed", error=str(e), exc_info=True)
            self.view.show_error(
                "Erro de Detector", f"Falha ao inicializar o detector: {e}"
            )
            return False

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
        if (self.detector and
                hasattr(self.detector.plugin, 'set_aquarium_region_defined')):
            has_aquarium = bool(zone_data and zone_data.polygon)
            self.detector.plugin.set_aquarium_region_defined(has_aquarium)
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

    def get_all_weight_names(self) -> list:
        return self.weight_manager.get_all_weights()

    def add_new_weight(self, path: str, set_as_default: bool):
        self.weight_manager.add_weight(path, set_as_default)
        new_name = os.path.basename(path)
        # Refresh UI
        self.view.update_weights_dropdown(self.get_all_weight_names())
        self.view.set_active_weight_in_dropdown(new_name)
        self.set_active_weight(new_name)  # This will also trigger conversion check

    def delete_weight(self, name: str):
        self.weight_manager.delete_weight(name)
        # Refresh UI
        self.view.update_weights_dropdown(self.get_all_weight_names())
        name, _ = self.weight_manager.get_default_weight()
        self.view.set_active_weight_in_dropdown(name)
        self.set_active_weight(name, None)

    def set_active_weight(self, name: str, dialog):
        if name and name in self.get_all_weight_names():
            self.active_weight_name = name
            log.info("controller.active_weight.set", name=name)
            self.update_openvino_status(dialog)
            if self.use_openvino:
                self.convert_active_weight_to_openvino(dialog)
        else:
            log.warning("controller.active_weight.not_found", name=name)
            self.active_weight_name = None
            self.update_openvino_status(dialog)


    def set_openvino_usage(self, use_openvino: bool, dialog):
        self.use_openvino = use_openvino
        log.info("controller.openvino_usage.set", enabled=use_openvino)
        if use_openvino and self.active_weight_name:
            # Trigger conversion if switching to OpenVINO and model isn't converted
            self.convert_active_weight_to_openvino(dialog)
        self.update_openvino_status(dialog)

    def convert_active_weight_to_openvino(self, dialog):
        if not self.active_weight_name:
            return
        self.view.set_status(f"Convertendo {self.active_weight_name} para OpenVINO...")
        self.view.update_idletasks()
        self.weight_manager.convert_to_openvino(self.active_weight_name)
        self.update_openvino_status(dialog)
        self.view.set_status("Verificação de conversão concluída. Pronto.")

    def update_openvino_status(self, dialog):
        """Updates the status label in the GUI based on the current state."""
        status = self.get_openvino_status()
        if dialog:
            dialog.update_openvino_status_label(status)

    def run_aquarium_detection(
        self, video_path: str | None = None, stabilization_frames: int = 10
    ):
        """Runs the aquarium detection model on the specified or first project video."""
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

            # Display the first frame of the video as a preview background
            self.view.display_roi_video_frame(video_path)

            weight_details = self.weight_manager.get_weight_details(
                self.active_weight_name
            )
            if not weight_details or not weight_details.get("path"):
                self.view.show_error(
                    "Erro",
                    "Não foi possível encontrar um caminho de modelo .pt válido.",
                )
                return

            model_path = weight_details["path"]
            detector = AquariumDetector(model_path=model_path)
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
                log.error("controller.polygon.invalid_points", count=len(points) if points else 0)
                return False

            # Validação 2: Projeto existe
            if not self.project_manager.project_path:
                log.error("controller.polygon.no_project")
                # Para single video workflow, cria projeto temporário
                if hasattr(self.view, 'pending_single_video_path') and self.view.pending_single_video_path:
                    import tempfile
                    temp_dir = tempfile.mkdtemp(prefix="zebtrack_temp_")
                    self.project_manager.project_path = temp_dir
                    self.project_manager.project_data = {
                        "project_name": "Temporary Single Video Project",
                        "project_type": "single_video",
                        "detection_zones": {}
                    }
                    log.warning("controller.polygon.created_temp_project", path=temp_dir)
                else:
                    return False

            # Validação 3: Estrutura de dados
            if "detection_zones" not in self.project_manager.project_data:
                self.project_manager.project_data["detection_zones"] = {}
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

        # Ensure the detection_zones dictionary exists
        if "detection_zones" not in self.project_manager.project_data:
            self.project_manager.project_data["detection_zones"] = {}

        zone_data = self.project_manager.get_zone_data()
        zone_data.polygon = polygon_points

        # Convert dataclass to dict and save
        from dataclasses import asdict
        self.project_manager.project_data["detection_zones"] = asdict(zone_data)
        self.project_manager.save_project()

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

                arena_poly = np.array(zone_data.polygon, dtype=np.int32)

                # Verifica se todos os pontos da ROI estão dentro da arena
                points_outside = 0
                for point in roi_points:
                    result = cv2.pointPolygonTest(arena_poly, tuple(point), False)
                    if result < 0:  # Ponto está fora
                        points_outside += 1

                if points_outside > 0:
                    outside_percent = (points_outside / len(roi_points)) * 100
                    log.warning("controller.roi.outside_arena",
                              name=name,
                              points_outside=points_outside,
                              percent=outside_percent)

                    if not self.view.ask_ok_cancel(
                        "ROI Fora da Arena",
                        f"A ROI '{name}' tem {points_outside} pontos ({outside_percent:.1f}%) "
                        "fora da arena principal.\n\nDeseja continuar mesmo assim?"
                    ):
                        return False

            # Validação 2: Verifica sobreposição com outras ROIs
            for i, existing_roi in enumerate(zone_data.roi_polygons):
                if len(existing_roi) >= 3:
                    # Calcula sobreposição simples verificando pontos
                    overlapping_points = 0

                    existing_poly = np.array(existing_roi, dtype=np.int32)

                    for point in roi_points:
                        result = cv2.pointPolygonTest(existing_poly, tuple(point), False)
                        if result >= 0:  # Ponto está dentro ou na borda
                            overlapping_points += 1

                    if overlapping_points > 0:
                        overlap_percent = (overlapping_points / len(roi_points)) * 100

                        if overlap_percent > 20:  # Mais de 20% de sobreposição
                            existing_name = zone_data.roi_names[i] if i < len(zone_data.roi_names) else f"ROI_{i+1}"
                            log.warning("controller.roi.overlap",
                                      name=name,
                                      existing=existing_name,
                                      percent=overlap_percent)

                            if not self.view.ask_ok_cancel(
                                "ROIs Sobrepostas",
                                f"A nova ROI '{name}' tem {overlap_percent:.1f}% de "
                                f"sobreposição com '{existing_name}'.\n\n"
                                "Deseja continuar?"
                            ):
                                return False

            # Adiciona a ROI após validações
            zone_data.roi_polygons.append(roi_points)
            zone_data.roi_names.append(name)
            zone_data.roi_colors.append(color)

            # Convert the dataclass back to a dict for JSON serialization
            from dataclasses import asdict
            self.project_manager.project_data["detection_zones"] = asdict(zone_data)

            # Save the project and reload the zones in the active detector
            self.project_manager.save_project()
            self.setup_detector_zones()
            log.info("controller.zone.add_roi.success", name=name)
            return True

        except Exception as e:
            log.error("controller.zone.add_roi.error", name=name, error=str(e))
            return False

    def run_live_calibration(self):
        """Records a short clip from the live camera and runs aquarium detection."""
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

            # 3. Run detection on the clip
            # Use the globally selected .pt model for this, not OpenVINO
            weight_details = self.weight_manager.get_weight_details(
                self.active_weight_name
            )
            if not weight_details or not weight_details.get("path"):
                self.view.show_error("Error", "Could not find a valid .pt model path.")
                return
            model_path = weight_details["path"]
            detector = AquariumDetector(model_path=model_path)
            polygons = detector.detect_aquariums(temp_video_path)

            if not polygons:
                self.view.show_warning(
                    "Detecção Falhou",
                    "Nenhum aquário foi detectado. "
                    "Por favor, desenhe a área manualmente.",
                )
                return

            main_polygon = polygons[0]
            self.view.display_suggested_polygon(main_polygon)

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

        # Validação de zonas para projetos Live
        if self.project_manager.project_path:
            zone_data = self.project_manager.get_zone_data()
            if not zone_data or not zone_data.polygon:
                log.warning("controller.recording.no_main_arena")

                response = self.view.ask_ok_cancel(
                    "Arena Principal Não Definida",
                    "O polígono principal do aquário não foi definido.\n\n"
                    "É recomendado definir a arena antes de iniciar gravação.\n"
                    "Deseja definir agora?"
                )

                if response:
                    # Muda para aba de zonas e inicia câmera para calibração
                    if hasattr(self.view, 'notebook') and hasattr(self.view, 'zone_tab_frame'):
                        self.view.notebook.select(self.view.zone_tab_frame)

                    self.view.show_info(
                        "Defina a Arena Principal",
                        "Por favor:\n"
                        "1. Use a câmera ao vivo para calibrar\n"
                        "2. Use 'Detectar Aquário (Auto)' ou\n"
                        "3. Desenhe manualmente o polígono principal\n"
                        "4. Depois volte para iniciar a gravação"
                    )
                    return
                else:
                    # Continua sem arena definida (usando padrão)
                    if not self.view.ask_ok_cancel(
                        "Continuar Sem Arena?",
                        "Deseja continuar a gravação sem arena definida?\n"
                        "(A arena padrão será o frame completo)"
                    ):
                        log.info("controller.recording.cancelled_no_arena")
                        return

                    log.info("controller.recording.proceeding_without_arena")

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

        # 4. Define the core recording logic as a callable
        def _do_record():
            zone_data = self.project_manager.get_zone_data()
            self.is_recording = self.recorder.start_recording(
                output_folder,
                self.view.camera.actual_width,
                self.view.camera.actual_height,
                zones=zone_data,
            )

            if not self.is_recording:
                self.view.show_error("Erro", "Não foi possível iniciar a gravação.")
                return

            # Update UI
            self.view.update_button_state("start_rec", "disabled")
            self.view.update_button_state("stop_rec", "normal")
            self.view.set_status(f"Recording session: {folder_name}")

            # Handle timed recording if enabled
            project_data = self.project_manager.project_data
            if project_data.get("use_timed_recording"):
                duration_s = project_data.get("recording_duration_s", 0)
                if duration_s > 0:
                    duration_ms = int(duration_s * 1000)
                    self.timed_recording_job = self.root.after(
                        duration_ms, self.stop_recording
                    )
                    log.info(
                        "controller.recording.timed_start", duration_s=duration_s
                    )

        # 5. Check for countdown and execute recording logic
        project_data = self.project_manager.project_data
        if project_data.get("use_countdown"):
            countdown_s = project_data.get("countdown_duration_s", 0)
            if countdown_s > 0:
                self._run_countdown(countdown_s, _do_record)
            else:
                _do_record()  # Countdown enabled but duration is 0, record immediately
        else:
            _do_record()  # No countdown, record immediately

    def stop_recording(self):
        """Stops the current recording session."""
        log.info("controller.recording.stop")
        # 1. Cancel any pending timed recording job
        if self.timed_recording_job:
            self.root.after_cancel(self.timed_recording_job)
            self.timed_recording_job = None
            log.info("controller.recording.timed_cancelled")

        # 2. Stop the recorder
        if self.is_recording:
            self.recorder.stop_recording()
            self.is_recording = False

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

        # Ensure the detector is set up before showing the UI that needs it.
        # This is crucial for the single video flow.
        if not self.detector:
            log.info("controller.single_video.setup_detector")
            if not self.setup_detector():
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

        # Permanecer na tela principal para exibir a barra de progresso
        # self.view._create_welcome_frame()
        self.view.show_info(
            "Análise Iniciada",
            "A análise do vídeo foi iniciada em segundo plano.\n"
            f"Você será notificado quando terminar. Os resultados serão salvos em:\n{output_dir}"
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
                "Deseja definir agora antes de processar?"
            )

            if response:
                # Muda para aba de zonas
                if hasattr(self.view, 'notebook') and hasattr(self.view, 'zone_tab_frame'):
                    self.view.notebook.select(self.view.zone_tab_frame)

                # Carrega frame do primeiro vídeo se disponível
                first_video = self.project_manager.get_next_video()
                if first_video and hasattr(self.view, 'load_video_frame_to_canvas'):
                    self.view.load_video_frame_to_canvas(first_video)

                self.view.show_info(
                    "Defina a Arena Principal",
                    "Por favor:\n"
                    "1. Use 'Detectar Aquário (Auto)' ou\n"
                    "2. Desenhe manualmente o polígono principal\n"
                    "3. Depois volte para adicionar vídeos"
                )
                return
            else:
                # Oferece arena padrão como fallback
                if not self.view.ask_ok_cancel(
                    "Usar Arena Padrão?",
                    "Deseja usar o frame completo como arena?\n"
                    "(Não recomendado para análise precisa)"
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

                    default_arena = [
                        [0, 0], [width, 0],
                        [width, height], [0, height]
                    ]

                    success = self.set_main_arena_polygon(default_arena)
                    if success:
                        log.info("workflow.project_processing.default_arena_created",
                                size=f"{width}x{height}")
                        self.view.show_info(
                            "Arena Padrão Criada",
                            f"Arena padrão criada ({width}x{height})\n"
                            "Recomenda-se ajustar manualmente depois."
                        )
                    else:
                        self.view.show_error("Erro", "Não foi possível criar arena padrão")
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
                "Deseja continuar?"
            ):
                log.info("workflow.project_processing.cancelled_by_user_no_roi")
                return

        log.info("workflow.project_processing.zones_validated",
                has_main_arena=bool(zone_data.polygon),
                roi_count=len(zone_data.roi_polygons))

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
            self.project_manager.project_data['analysis_interval_frames'] = analysis_interval
            self.project_manager.project_data['display_interval_frames'] = display_interval
            # Save the project to persist the intervals
            self.project_manager.save_project()
            log.info("controller.workflow.intervals_saved",
                    analysis=analysis_interval, display=display_interval)
        except (ValueError, AttributeError) as e:
            log.warning("controller.workflow.intervals_save_failed", error=str(e))
            # Use defaults if there's an issue
            self.project_manager.project_data['analysis_interval_frames'] = 10
            self.project_manager.project_data['display_interval_frames'] = 10

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

            # --- New: Calculate pixel/cm ratio before recording ---
            pixel_per_cm_ratio = None
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
            )

            frame_num = 0
            processed_frames_count = 0
            last_detections = []
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

                    # Cache the last detections for display
                    last_detections = detections
                    processed_frames_count += 1

                # Check if we should update the display (display interval based on processed frames)
                should_display = processed_frames_count > 0 and (processed_frames_count % display_interval_frames == 0)

                # Update GUI display
                if progress_callback:
                    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    progress_fraction = (
                        (frame_num + 1) / total_frames if total_frames > 0 else 0
                    )

                    if should_display and should_process:
                        # Draw overlay on current frame with fresh detections
                        self.detector.draw_overlay(frame, detections)
                        progress_callback(progress_fraction, "Gerando trajetória...", frame)
                    elif should_display and last_detections:
                        # Draw overlay using last cached detections
                        self.detector.draw_overlay(frame, last_detections)
                        progress_callback(progress_fraction, "Gerando trajetória...", frame)
                    else:
                        # Just update progress without frame
                        progress_callback(progress_fraction, "Gerando trajetória...", None)

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

    def validate_zone_configuration_comprehensive(self):
        """
        Comprehensive zone validation with detailed feedback.
        Returns (is_valid, issues_summary, recommendations)
        """
        zone_data = self.project_manager.get_zone_data()
        issues = []
        recommendations = []
        is_valid = True

        # Check main arena
        if not zone_data or not zone_data.polygon:
            is_valid = False
            issues.append("❌ Arena principal não definida")
            recommendations.append("• Use 'Detectar Aquário (Auto)' ou desenhe manualmente")
        else:
            issues.append("✅ Arena principal definida")

        # Check ROIs
        if zone_data and zone_data.roi_polygons:
            issues.append(f"✅ {len(zone_data.roi_polygons)} ROI(s) definida(s)")

            # Check for ROI overlaps and arena containment
            for i, roi_polygon in enumerate(zone_data.roi_polygons):
                roi_name = zone_data.roi_names[i] if i < len(zone_data.roi_names) else f"ROI {i+1}"

                # Check if ROI is contained in main arena
                if zone_data.polygon:
                    np.array(roi_polygon, dtype=np.float32).reshape(-1, 1, 2)
                    contained_points = 0
                    for point in roi_polygon:
                        if cv2.pointPolygonTest(np.array(zone_data.polygon, dtype=np.float32), point, False) >= 0:
                            contained_points += 1

                    containment_percent = (contained_points / len(roi_polygon)) * 100
                    if containment_percent < 80:
                        issues.append(f"⚠️ {roi_name}: {containment_percent:.1f}% dentro da arena")
                        recommendations.append(f"• Ajustar {roi_name} para ficar completamente dentro da arena")

                # Check overlaps with other ROIs
                for j, other_roi in enumerate(zone_data.roi_polygons):
                    if i != j:
                        other_name = zone_data.roi_names[j] if j < len(zone_data.roi_names) else f"ROI {j+1}"
                        overlapping_points = 0
                        for point in roi_polygon:
                            if cv2.pointPolygonTest(np.array(other_roi, dtype=np.float32), point, False) >= 0:
                                overlapping_points += 1

                        if overlapping_points > 0:
                            overlap_percent = (overlapping_points / len(roi_polygon)) * 100
                            if overlap_percent > 20:
                                issues.append(f"⚠️ {roi_name} e {other_name}: {overlap_percent:.1f}% sobreposição")
                                recommendations.append(f"• Reduzir sobreposição entre {roi_name} e {other_name}")
        else:
            issues.append("ℹ️ Nenhuma ROI definida (opcional)")
            recommendations.append("• Considere definir ROIs para análises mais detalhadas")

        # Summary
        summary = "\n".join(issues)
        if recommendations:
            summary += "\n\nRecomendações:\n" + "\n".join(recommendations)

        return is_valid, summary, recommendations

    def apply_project_settings_to_batch(self, videos: list):
        """Aplica configurações do projeto a novos vídeos"""
        if not self.project_manager.project_path:
            log.warning("controller.batch.no_project_path")
            return False

        # Obtém configurações do projeto
        project_data = self.project_manager.project_data
        zone_data = self.project_manager.get_zone_data()
        calibration = project_data.get('calibration', {})

        log.info("controller.batch.apply_settings",
                videos_count=len(videos),
                has_zones=bool(zone_data and zone_data.polygon),
                has_calibration=bool(calibration),
                has_rois=len(zone_data.roi_polygons) if zone_data else 0)

        # Para cada vídeo no lote
        settings_applied = 0
        for video_info in videos:
            video_path = video_info.get('path')
            if not video_path:
                continue

            video_name = os.path.splitext(os.path.basename(video_path))[0]

            # Cria diretório de resultados
            results_dir = os.path.join(
                self.project_manager.project_path,
                f"{video_name}_results"
            )

            try:
                os.makedirs(results_dir, exist_ok=True)

                # Salva configurações completas do projeto
                settings_file = os.path.join(results_dir, "project_settings.json")
                settings_data = {
                    "project_name": self.project_manager.get_project_name(),
                    "active_weight": project_data.get('active_weight'),
                    "use_openvino": project_data.get('use_openvino', False),
                    "calibration": calibration,
                    "video_settings": video_info,
                    "timestamp": self.project_manager.project_data.get('timestamp'),
                    "analysis_interval_frames": project_data.get('analysis_interval_frames', 10),
                    "display_interval_frames": project_data.get('display_interval_frames', 10),
                }

                import json
                with open(settings_file, 'w') as f:
                    json.dump(settings_data, f, indent=2)

                # Salva zonas no diretório de resultados
                if zone_data and (zone_data.polygon or zone_data.roi_polygons):
                    zones_file = os.path.join(results_dir, "zones.json")

                    from dataclasses import asdict
                    with open(zones_file, 'w') as f:
                        json.dump(asdict(zone_data), f, indent=2)

                    log.info("controller.batch.zones_saved",
                            video=video_name,
                            zones_file=zones_file,
                            settings_file=settings_file)

                settings_applied += 1

            except Exception as e:
                log.error("controller.batch.settings_save_error",
                         video=video_name,
                         error=str(e))

        log.info("controller.batch.settings_applied",
                total_videos=len(videos),
                successful=settings_applied)

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
        display_interval_frames = 10   # default

        if single_video_config:
            # For single video: take from config dict if present, else defaults
            analysis_interval_frames = single_video_config.get('analysis_interval_frames', 10)
            display_interval_frames = single_video_config.get('display_interval_frames', 10)
        else:
            # For batch projects: read from project_data
            if hasattr(self.project_manager, 'project_data') and self.project_manager.project_data:
                analysis_interval_frames = self.project_manager.project_data.get('analysis_interval_frames', 10)
                display_interval_frames = self.project_manager.project_data.get('display_interval_frames', 10)

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

            for i, video_info in enumerate(videos_to_process):
                if self.cancel_event.is_set():
                    was_cancelled = True
                    log.info("controller.processing.cancelled_by_user")
                    break

                video_path = video_info["path"]
                experiment_id = os.path.splitext(os.path.basename(video_path))[0]

                def progress_callback(progress_fraction, status_message, frame=None):
                    if self.cancel_event.is_set():
                        return
                    overall_progress = (
                        f"Processando {i+1}/{len(videos_to_process)}: {experiment_id}"
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
                    metadata = single_video_config
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
                        self.root.after(
                            0,
                            lambda: self.view.show_warning(
                                "Processamento Ignorado",
                                f"Metadados não fornecidos para {experiment_id}. "
                                "Ignorando vídeo.",
                            ),
                        )
                        continue

                zone_data = self.project_manager.get_zone_data()
                video_height_px = settings.camera.desired_height
                if not all([width_cm, height_cm, arena_polygon_px]):
                    self.root.after(
                        0,
                        lambda: self.view.show_error(
                            "Erro de Processamento", "Dados de calibração incompletos."
                        ),
                    )
                    continue

                cal = Calibration(np.array(arena_polygon_px), width_cm, height_cm)
                pixelcm_x, pixelcm_y = cal.pixel_per_cm_ratio
                rois = [
                    ROI(
                        name=zone_data.roi_names[i],
                        geometry=Polygon(p),
                    )
                    for i, p in enumerate(zone_data.roi_polygons)
                ]
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
                    arena_polygon_px=arena_polygon_px,
                    rois=rois,
                    fps=settings.video_processing.fps,
                    roi_colors=roi_colors,
                    video_path=video_path,
                    sharp_turn_threshold=st_thresh,
                    freezing_threshold=fz_thresh,
                    freezing_duration=fz_dur,
                )
                reporter.export_summary_data(
                    os.path.join(results_dir, f"{experiment_id}_summary.xlsx"),
                    format="excel",
                )
                reporter.export_individual_report_step_by_step(
                    os.path.join(results_dir, f"{experiment_id}_report.docx"),
                    progress_callback,
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
            summary_path = os.path.join(
                results_dir, f"{experiment_id}_summary.parquet"
            )

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
                    # If user skips conversion, modify config to only run YOLO if possible
                    if model_to_test == "Ambos":
                        config["model_to_test"] = "YOLO (PyTorch)"
                    else: # model_to_test was 'OpenVINO'
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
                if hasattr(yolo_model, 'set_context'):
                    yolo_model.set_context('diagnostic')
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
                            log.error("diagnostic.thread.missing_predict_method", plugin_class=str(plugin_class))
                            self.root.after(0, self.view.show_error, "Erro de Plugin",
                                          "O plugin OpenVINO não possui o método predict necessário para diagnóstico.")
                            return
                        # Set diagnostic context to allow all classes
                        if hasattr(openvino_model, "set_context"):
                            openvino_model.set_context("diagnostic")
                            log.info("diagnostic.thread.openvino_context_set", context="diagnostic")
                        results["OpenVINO"] = []
                        log.info("diagnostic.thread.openvino_loaded", path=ov_path)
        except Exception as e:
            log.error("diagnostic.thread.load_error", exc_info=True)
            self.root.after(0, self.view.show_error, "Erro ao Carregar Modelo", f"Falha: {e}")
            return

        # --- Video Processing ---
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            self.root.after(0, self.view.show_error, "Erro", f"Não foi possível abrir o vídeo: {video_path}")
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
                    log.debug("diagnostic.thread.openvino_predict_start", frame=frame_count + 1)
                    preds = openvino_model.predict(frame, conf_threshold)
                    log.debug("diagnostic.thread.openvino_predict_success",
                             frame=frame_count + 1, detections=len(preds))
                    results.setdefault("OpenVINO", []).append(preds)
                except Exception as e:
                    log.error("diagnostic.thread.openvino_predict_error",
                             frame=frame_count + 1, exc_info=True)
                    self.root.after(0, self.view.show_error, "Erro de Inferência OpenVINO",
                                  f"Falha na inferência do frame {frame_count + 1}: {e}")
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
                self.view.show_error("Erro ao Salvar", f"Não foi possível salvar o arquivo: {e}")

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
                if hasattr(preds, 'boxes') or hasattr(preds, 'masks'):
                    # Processa boxes com suas máscaras
                    if preds.boxes is not None:
                        for j, box in enumerate(preds.boxes):
                            class_id = int(box.cls)
                            class_name = preds.names.get(class_id, 'desconhecido')
                            conf = float(box.conf)
                            bbox = [int(coord) for coord in box.xyxy[0]]

                            # Verifica se tem máscara
                            has_mask = (preds.masks is not None and
                                      preds.masks.xy is not None and
                                      j < len(preds.masks.xy))
                            mask_info = f", Máscara: {len(preds.masks.xy[j])} pontos" if has_mask else ""

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
                        class_id = det['class_id']
                        class_name = det['class_name']
                        conf = det['confidence']
                        bbox = det['box']
                        mask_info = f", Máscara: {det.get('mask_points', 0)} pontos" if det.get('has_mask') else ""

                        detections.append(
                            f"  - Classe {class_id} ('{class_name}'), "
                            f"Conf: {conf:.2f}, BBox: {bbox}{mask_info}"
                        )

                # Adiciona detecções ao relatório
                if detections:
                    report_lines.extend(detections)
                if mask_only_detections:
                    report_lines.append("  Máscaras sem bounding box (possíveis aquários):")
                    report_lines.extend(mask_only_detections)
                if not detections and not mask_only_detections:
                    report_lines.append("  - Nenhuma detecção encontrada.")

                report_lines.append("")

            report_lines.append("") # Spacer between models

        return "\n".join(report_lines)
