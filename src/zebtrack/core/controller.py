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
from shapely.geometry import box

from zebtrack.analysis.reporter import Reporter
from zebtrack.analysis.roi import ROI
from zebtrack.core.aquarium_detector import AquariumDetector
from zebtrack.core.calibration import Calibration
from zebtrack.core.detector import Detector
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

        # New state variables for model management
        self.active_weight_name, _ = self.weight_manager.get_default_weight()
        if self.active_weight_name is None:
            self.active_weight_name = ""
            log.warning("controller.init.no_default_weight")
        self.use_openvino = False  # Default to not using OpenVINO

    def run(self):
        # Populate the GUI with initial model info before starting the main loop
        self.view.update_weights_dropdown(self.weight_manager.get_all_weights())
        self.view.set_active_weight_in_dropdown(self.active_weight_name)
        self.update_openvino_status()
        self.root.mainloop()

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

        if hasattr(self, "processing_thread") and self.processing_thread.is_alive():
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
        if self.project_manager.load_project(project_path):
            # When loading a project, reflect its settings in the controller
            self.use_openvino = self.project_manager.project_data.get(
                "use_openvino", False
            )
            self.active_weight_name = self.project_manager.project_data.get(
                "active_weight"
            )
            self.view.update_openvino_checkbox(self.use_openvino)
            self.view.set_active_weight_in_dropdown(self.active_weight_name)
            self.update_openvino_status()

            if self.setup_detector():
                self.view._load_project_view()
                # self.load_project_results_for_gui() # This is now handled in the UI

            # After loading, check if zones are defined.
            self.setup_detector_zones()

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
        self.set_active_weight(name)

    def set_active_weight(self, name: str):
        if name and name in self.get_all_weight_names():
            self.active_weight_name = name
            log.info("controller.active_weight.set", name=name)
            self.update_openvino_status()
            if self.use_openvino:
                self.convert_active_weight_to_openvino()
        else:
            log.warning("controller.active_weight.not_found", name=name)
            self.active_weight_name = None

    def set_openvino_usage(self, use_openvino: bool):
        self.use_openvino = use_openvino
        log.info("controller.openvino_usage.set", enabled=use_openvino)
        if use_openvino and self.active_weight_name:
            # Trigger conversion if switching to OpenVINO and model isn't converted
            self.convert_active_weight_to_openvino()
        self.update_openvino_status()

    def convert_active_weight_to_openvino(self):
        if not self.active_weight_name:
            return
        self.view.set_status(f"Convertendo {self.active_weight_name} para OpenVINO...")
        self.view.update_idletasks()
        self.weight_manager.convert_to_openvino(self.active_weight_name)
        self.update_openvino_status()
        self.view.set_status("Verificação de conversão concluída. Pronto.")

    def update_openvino_status(self):
        """Updates the status label in the GUI based on the current state."""
        if not self.active_weight_name:
            self.view.update_openvino_status_label("Nenhum peso selecionado.")
            return

        details = self.weight_manager.get_weight_details(self.active_weight_name)
        if not details:
            return

        if self.use_openvino:
            if details.get("openvino_path") and os.path.exists(
                details.get("openvino_path")
            ):
                self.view.update_openvino_status_label("O modelo OpenVINO está pronto.")
            else:
                self.view.update_openvino_status_label(
                    "Necessita de conversão para OpenVINO."
                )
        else:
            self.view.update_openvino_status_label("O OpenVINO está desativado.")

    def run_aquarium_detection(self):
        """Runs the aquarium detection model on the first video of the project."""
        log.info("controller.aquarium_detection.start")
        video_path = self.project_manager.get_next_video()
        if not video_path:
            self.view.show_warning(
                "Aviso", "Nenhum vídeo pendente encontrado no projeto."
            )
            return

        try:
            # Use the globally selected .pt model for this, not OpenVINO
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
            polygons = detector.detect_aquariums(video_path)

            if not polygons:
                self.view.show_warning(
                    "Detecção Falhou",
                    "Nenhum aquário foi detectado no vídeo. "
                    "Por favor, desenhe a área manualmente.",
                )
                return

            main_polygon = polygons[0]
            log.info(
                "controller.aquarium_detection.success",
                polygon_points=len(main_polygon),
            )
            # The view will handle drawing this polygon
            self.view.display_suggested_polygon(main_polygon)

        except Exception as e:
            log.error("controller.aquarium_detection.error", exc_info=True)
            self.view.show_error(
                "Erro na Detecção", f"Ocorreu um erro ao detectar o aquário: {e}"
            )

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
        """Starts a recording session (live mode)."""
        log.info("controller.recording.start")

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

    def start_single_video_workflow(self, video_path: str, config: dict):
        """Handles the 'Analyze Single Video' workflow."""
        log.info("workflow.single_video.start", video=video_path)

        # 1. Ensure the detector is set up
        if not self.detector:
            if not self.setup_detector():
                self.view.show_error(
                    "Erro",
                    "Não foi possível configurar o detector. "
                    "Por favor, configure um modelo na tela principal.",
                )
                return

        # 2. Scan the single video
        scanned_files = ProjectManager.scan_input_paths([video_path])
        if not scanned_files:
            self.view.show_error(
                "Erro", "Não foi possível identificar um arquivo de vídeo válido."
            )
            return

        video_to_process = scanned_files[0]

        # 3. Check for existing data
        if video_to_process["has_data"]:
            if not self.view.ask_ok_cancel(
                "Dados Encontrados",
                "Dados de análise existentes (.parquet) encontrados para este vídeo. "
                "Deseja substituí-los reprocessando o vídeo?",
            ):
                self.view.show_info("Cancelado", "Análise de vídeo único cancelada.")
                return

        # 4. Create a "mini-project" folder for the results
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        output_dir = os.path.join(os.path.dirname(video_path), f"{video_name}_results")
        os.makedirs(output_dir, exist_ok=True)

        # 5. Process the video, passing the config as temporary metadata
        self._process_videos(
            [video_to_process], output_dir, single_video_config=config
        )
        self.view.show_info(
            "Sucesso",
            f"Análise de vídeo único concluída. Resultados salvos em:\n{output_dir}",
        )

    def start_project_processing_workflow(self):
        """Handles adding and processing a new batch of videos in a project."""
        log.info("workflow.project_processing.start")
        if not self.project_manager.project_path:
            self.view.show_error("Error", "No project is currently open.")
            return

        # Check for ROIs and ask for confirmation if none are defined
        zone_data = self.project_manager.get_zone_data()
        if not zone_data.squares:  # .squares holds the ROIs
            if not self.view.ask_ok_cancel(
                "Nenhuma ROI Definida",
                "Nenhuma Área de Interesse (ROI) foi definida. A análise prosseguirá "
                "usando apenas a área total do aquário. Deseja continuar?",
            ):
                log.info("workflow.project_processing.cancelled_by_user_no_roi")
                self.view.show_info(
                    "Processamento Cancelado",
                    "O processamento foi cancelado pelo usuário.",
                )
                return

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

        # 5. Process the videos that need it
        self._process_videos(videos_to_process, self.project_manager.project_path)

        # 6. Update statuses in project file
        for video in videos_to_process:
            self.project_manager.update_video_status(video["path"], "complete")

        self.view.show_info(
            "Sucesso",
            f"{len(videos_to_process)} vídeo(s) foram processados e adicionados "
            "ao projeto.",
        )

    def _run_tracking_if_needed(
        self, video_path: str, results_dir: str, experiment_id: str
    ) -> tuple[bool, list | None]:
        """
        Checks if a trajectory file exists. If not, runs the tracking process
        to generate it. This is a blocking operation.

        Returns:
            A tuple containing:
            - bool: True if tracking was successful or already existed, False otherwise.
            - list | None: The arena polygon used for tracking, or None if tracking failed.
        """
        log.info("controller.tracking.check_or_run", video=experiment_id)
        trajectory_path = os.path.join(
            results_dir, f"3_CoordMovimento_{experiment_id}.parquet"
        )
        # Try to get the arena from the project manager first
        arena_polygon = self.project_manager.get_zone_data().polygon

        if os.path.exists(trajectory_path):
            log.info("controller.tracking.exists", path=trajectory_path)
            # If tracking exists, we still need to return the arena polygon if it's defined
            return True, arena_polygon if arena_polygon else None

        log.info("controller.tracking.generating", video=experiment_id)
        self.view.set_status(f"Gerando trajetória para {experiment_id}...")
        self.view.update_idletasks()

        recorder = Recorder()
        cap = cv2.VideoCapture(video_path)
        try:
            if not cap.isOpened():
                log.error("controller.tracking.video_open_failed", path=video_path)
                return False, None

            # This logic mirrors tests/test_integration.py
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            # Use a default full-frame arena if none is defined in the project
            # This is crucial for single-video analysis
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
                # Ensure arena_polygon is up-to-date if it was loaded
                arena_polygon = zone_data.polygon

            self.detector.set_zones(zone_data, frame_width, frame_height)

            # The key change: pass the explicit base_name to the recorder
            recorder.start_recording(
                output_folder=results_dir,
                frame_width=frame_width,
                frame_height=frame_height,
                zones=zone_data,
                is_video_file=True,  # We are analyzing, not saving a new video
                base_name=experiment_id,
            )

            frame_num = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                detections, _ = self.detector.process_frame(
                    frame, project_type="pre-recorded"
                )
                timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                recorder.write_detection_data(timestamp, frame_num, detections)
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

    def _process_videos(
        self,
        videos_to_process: list[dict],
        output_base_dir: str,
        single_video_config: dict | None = None,
    ):
        """
        Private helper to process a list of videos and save results using the
        new concrete analysis classes.
        """
        log.info("controller.processing.start", count=len(videos_to_process))
        self.view.set_status(
            f"Iniciando processamento para {len(videos_to_process)} vídeos..."
        )
        self.view.show_progress_bar()
        self.view.update_idletasks()

        for i, video_info in enumerate(videos_to_process):
            video_path = video_info["path"]
            experiment_id = os.path.splitext(os.path.basename(video_path))[0]

            # --- Progress Callback Definition ---
            def progress_callback(progress_fraction, status_message):
                # Update main status bar
                overall_progress = (
                    f"Processando {i+1}/{len(videos_to_process)}: {experiment_id}"
                )
                step_status = f"Etapa: {status_message}"
                self.view.set_status(f"{overall_progress} - {step_status}")

                # Update individual progress bar
                self.view.update_progress(progress_fraction)
                self.view.update_idletasks()

            # --- Display Video Frame ---
            try:
                cap = cv2.VideoCapture(video_path)
                ret, frame = cap.read()
                if ret:
                    self.view.display_frame(frame)
                cap.release()
            except Exception as e:
                log.warning("controller.progress.frame_display_error", error=str(e))


            # Define where to save results for this video
            if self.project_manager.project_path:
                results_dir = os.path.join(output_base_dir, f"{experiment_id}_results")
            else:
                results_dir = output_base_dir
            os.makedirs(results_dir, exist_ok=True)

            try:
                # 1. Run tracking if trajectory data is missing
                tracking_success, arena_polygon_px = self._run_tracking_if_needed(
                    video_path, results_dir, experiment_id
                )
                if not tracking_success:
                    continue  # Skip to the next video if tracking fails

                # If tracking was skipped, the arena might be undefined. Define a default.
                if not arena_polygon_px:
                    log.warning("controller.processing.no_arena_from_tracking.using_default")
                    cap = cv2.VideoCapture(video_path)
                    if cap.isOpened():
                        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        arena_polygon_px = [[0, 0], [w, 0], [w, h], [0, h]]
                        cap.release()

                # 2. Load trajectory data
                trajectory_path = os.path.join(
                    results_dir, f"3_CoordMovimento_{experiment_id}.parquet"
                )
                if not os.path.exists(trajectory_path):
                    log.error(
                        "controller.processing.no_trajectory_after_generation",
                        path=trajectory_path,
                    )
                    self.view.show_error(
                        "Erro de Processamento",
                        "Falha ao gerar ou encontrar o arquivo de trajetória para "
                        f"{experiment_id}.",
                    )
                    continue

                trajectory_df = pd.read_parquet(trajectory_path)

                # 2. Get calibration and geometry data
                if single_video_config:
                    # For single video, calibration data comes from the config dict
                    width_cm = single_video_config.get("aquarium_width_cm")
                    height_cm = single_video_config.get("aquarium_height_cm")
                else:
                    # For a full project, it comes from the project data
                    proj_data = self.project_manager.project_data
                    calib_data = proj_data.get("calibration", {})
                    width_cm = calib_data.get("aquarium_width_cm")
                    height_cm = calib_data.get("aquarium_height_cm")

                zone_data = self.project_manager.get_zone_data()
                video_height_px = settings.camera.desired_height

                if not all([width_cm, height_cm, arena_polygon_px]):
                    log.error("controller.processing.no_calibration")
                    self.view.show_error(
                        "Erro de Processamento",
                        "Os dados de calibração do projeto (dimensões, arena) "
                        "estão incompletos.",
                    )
                    continue

                # 3. Instantiate Calibration to get pixel/cm ratios
                cal = Calibration(np.array(arena_polygon_px), width_cm, height_cm)
                pixelcm_x, pixelcm_y = cal.pixel_per_cm_ratio
                if not all([pixelcm_x, pixelcm_y]):
                    log.error("controller.processing.bad_calibration_ratio")
                    self.view.show_error(
                        "Erro de Processamento",
                        "Não foi possível calcular a proporção de pixel para cm. "
                        "Verifique o polígono da arena.",
                    )
                    continue

                # 4. Get ROI definitions
                rois = []
                roi_colors = {}
                for j, square_coords in enumerate(zone_data.squares):
                    name = f"ROI {j+1}"
                    geom = box(
                        square_coords[0][0],
                        square_coords[0][1],
                        square_coords[1][0],
                        square_coords[1][1],
                    )
                    rois.append(ROI(name=name, geometry=geom))
                    if j < len(zone_data.colors):
                        roi_colors[name] = zone_data.colors[j]

                # 5. Get metadata
                if single_video_config:
                    metadata = single_video_config
                else:
                    metadata = self.project_manager.get_metadata_for_experiment(
                        experiment_id
                    )
                if not metadata:
                    log.warning("metadata.not_found", experiment_id=experiment_id)
                    # Ask user for input
                    metadata = self.view.ask_missing_metadata(experiment_id)
                    if not metadata:
                        log.error(
                            "metadata.user_cancelled", experiment_id=experiment_id
                        )
                        self.view.show_warning(
                            "Processamento Ignorado",
                            f"Metadados não fornecidos para {experiment_id}. "
                            "Ignorando vídeo.",
                        )
                        continue  # Skip to next video
                    # Add experiment_id to user-provided metadata
                    metadata["experiment_id"] = experiment_id

                # 6. Generate and save reports
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
                    sharp_turn_threshold=settings.video_processing.sharp_turn_threshold_deg_s,
                    freezing_threshold=settings.video_processing.freezing_velocity_threshold,
                    freezing_duration=settings.video_processing.freezing_min_duration_s,
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
                log.error(
                    "controller.processing.error",
                    video=experiment_id,
                    error=str(e),
                    exc_info=True,
                )
                self.view.show_error(
                    "Erro na Análise",
                    f"Ocorreu um erro inesperado ao processar "
                    f"{experiment_id}:\n{e}",
                )
                continue

        self.view.hide_progress_bar()
        self.view.set_status("Processamento concluído!")

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
