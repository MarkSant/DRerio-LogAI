from __future__ import annotations

import os
import tempfile
import threading
import time

import cv2
import numpy as np
import pandas as pd
import structlog

from zebtrack.analysis.behavioral_analyzer import BehavioralAnalyzer
from zebtrack.analysis.reporter import Reporter
from zebtrack.analysis.roi_analyzer import ROIAnalyzer
from zebtrack.core.aquarium_detector import AquariumDetector
from zebtrack.core.detector import Detector
from zebtrack.core.project_manager import ProjectManager
from zebtrack.core.weight_manager import WeightManager
from zebtrack.io.recorder import Recorder
from zebtrack.plugins import DETECTOR_PLUGINS
from zebtrack.settings import settings
from zebtrack.ui.gui import ApplicationGUI

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
        if self.view.ask_ok_cancel("Quit", "Do you want to exit?"):
            self.program_exit_event.set()
            self.root.destroy()

    def join_threads(self):
        pass

    def close_project(self):
        # TODO: Implement project closing logic, e.g., asking to save changes
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
            self.view.show_error("Error", "Failed to create the new project.")

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
            self.view.show_error("Detector Error", "No active weight is selected.")
            return False

        weight_details = self.weight_manager.get_weight_details(self.active_weight_name)
        if not weight_details:
            self.view.show_error(
                "Detector Error",
                f"Could not find details for weight: {self.active_weight_name}",
            )
            return False

        try:
            if self.use_openvino:
                plugin_name = "OpenVINO"
                model_path = weight_details.get("openvino_path")
                if not model_path or not os.path.exists(model_path):
                    raise ValueError(
                        "OpenVINO model path not found or invalid. "
                        "Please convert the model first."
                    )
            else:
                plugin_name = "YOLO (Ultralytics)"
                model_path = weight_details.get("path")
                if not model_path or not os.path.exists(model_path):
                    raise ValueError("YOLO .pt model path not found or invalid.")

            plugin_class = DETECTOR_PLUGINS.get(plugin_name)
            if not plugin_class:
                raise ValueError(f"Detector plugin '{plugin_name}' not found.")

            log.info("detector.load.start", plugin=plugin_name, path=model_path)
            plugin_instance = plugin_class(model_path=model_path)
            self.detector = Detector(
                plugin=plugin_instance,
                base_width=settings.camera.desired_width,
                base_height=settings.camera.desired_height,
            )
            log.info("detector.setup.success")
            return True
        except (ValueError, FileNotFoundError) as e:
            log.error("detector.init.failed", error=str(e), exc_info=True)
            self.view.show_error(
                "Detector Error", f"Failed to initialize the detector: {e}"
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
                self.view.show_info(
                    "Configuração Necessária",
                    "Por favor, defina a área de processamento principal (polígono) "
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
        self.view.set_status(f"Converting {self.active_weight_name} to OpenVINO...")
        self.view.update_idletasks()
        self.weight_manager.convert_to_openvino(self.active_weight_name)
        self.update_openvino_status()
        self.view.set_status("Conversion check complete. Ready.")

    def update_openvino_status(self):
        """Updates the status label in the GUI based on the current state."""
        if not self.active_weight_name:
            self.view.update_openvino_status_label("No weight selected.")
            return

        details = self.weight_manager.get_weight_details(self.active_weight_name)
        if not details:
            return

        if self.use_openvino:
            if details.get("openvino_path") and os.path.exists(
                details.get("openvino_path")
            ):
                self.view.update_openvino_status_label("OpenVINO model is ready.")
            else:
                self.view.update_openvino_status_label(
                    "Needs conversion to OpenVINO."
                )
        else:
            self.view.update_openvino_status_label("OpenVINO is disabled.")

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
                self.view.show_error("Error", "Could not find a valid .pt model path.")
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

        # 4. Start the recorder
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

        # 5. Update UI
        self.view.update_button_state("start_rec", "disabled")
        self.view.update_button_state("stop_rec", "normal")
        self.view.set_status(f"Recording session: {folder_name}")

        # 6. Handle timed recording if enabled
        project_data = self.project_manager.project_data
        if project_data.get("use_timed_recording"):
            duration_s = project_data.get("recording_duration_s", 0)
            if duration_s > 0:
                duration_ms = int(duration_s * 1000)
                self.timed_recording_job = self.root.after(
                    duration_ms, self.stop_recording
                )
                log.info("controller.recording.timed_start", duration_s=duration_s)

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
                    "Error",
                    "Could not set up the detector. "
                    "Please configure a model on the main screen.",
                )
                return

        # 2. Scan the single video
        scanned_files = ProjectManager.scan_input_paths([video_path])
        if not scanned_files:
            self.view.show_error("Error", "Could not identify a valid video file.")
            return

        video_to_process = scanned_files[0]

        # 3. Check for existing data
        if video_to_process["has_data"]:
            if not self.view.ask_ok_cancel(
                "Data Found",
                "Existing analysis data (.parquet) found for this video. "
                "Do you want to overwrite it by re-processing the video?",
            ):
                self.view.show_info("Cancelled", "Single video analysis cancelled.")
                return

        # 4. Create a "mini-project" folder for the results
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        output_dir = os.path.join(os.path.dirname(video_path), f"{video_name}_Results")
        os.makedirs(output_dir, exist_ok=True)

        # 5. Process the video, passing the config as temporary metadata
        self._process_videos(
            [video_to_process], output_dir, single_video_config=config
        )
        self.view.show_info(
            "Success",
            f"Single video analysis complete. Results saved in:\n{output_dir}",
        )

    def start_project_processing_workflow(self):
        """Handles adding and processing a new batch of videos in a project."""
        log.info("workflow.project_processing.start")
        if not self.project_manager.project_path:
            self.view.show_error("Error", "No project is currently open.")
            return

        # 1. Ask user to select files or folders
        paths = self.view.ask_open_filenames(
            "Select Videos or Folders to Add to Project",
            [
                ("All files", "*.*"),
                ("Video files", "*.mp4 *.avi *.mov"),
                ("Folders", "*/"),
            ],
        )
        if not paths:
            return

        # 2. Scan the inputs
        scanned_videos = self.project_manager.scan_input_paths(paths)
        if not scanned_videos:
            self.view.show_warning(
                "No Videos Found", "No new video files were found in the selected paths."
            )
            return

        # 3. Handle mixed data scenario
        videos_to_process = []
        with_data = [v for v in scanned_videos if v["has_data"]]
        without_data = [v for v in scanned_videos if not v["has_data"]]

        if with_data and without_data:
            # The complex case: some have data, some don't
            msg = (
                f"{len(with_data)} video(s) already have analysis data.\n"
                f"{len(without_data)} video(s) need to be processed.\n\n"
                "Do you want to re-process the videos that already have data?"
            )
            if self.view.ask_ok_cancel("Mixed Data Found", msg):
                # User wants to re-process everything
                videos_to_process = scanned_videos
            else:
                # User wants to skip re-processing
                videos_to_process = without_data
        elif with_data and not without_data:
            # All selected videos have data
            if self.view.ask_ok_cancel(
                "Data Found",
                "All selected videos already have analysis data. "
                "Do you want to re-process them all?",
            ):
                videos_to_process = with_data
            else:
                self.view.show_info(
                    "Processing Skipped", "No new videos were processed."
                )
                # Still add them to the project for reporting purposes
                self.project_manager.add_video_batch(scanned_videos)
                return
        else:
            # No videos have data, process all of them
            videos_to_process = without_data

        if not videos_to_process:
            self.view.show_info("Processing Complete", "No new videos to process.")
            return

        # 4. Add the batch to the project
        self.project_manager.add_video_batch(scanned_videos)

        # 5. Process the videos that need it
        self._process_videos(videos_to_process, self.project_manager.project_path)

        # 6. Update statuses in project file
        for video in videos_to_process:
            self.project_manager.update_video_status(video["path"], "complete")

        self.view.show_info(
            "Success",
            f"{len(videos_to_process)} video(s) were processed and added to the project.",
        )

    def _process_videos(
        self,
        videos_to_process: list[dict],
        output_base_dir: str,
        single_video_config: dict | None = None,
    ):
        """
        Private helper to process a list of videos and save results.
        """
        log.info("controller.processing.start", count=len(videos_to_process))
        self.view.set_status(
            f"Starting processing for {len(videos_to_process)} videos..."
        )
        self.view.update_idletasks()

        b_analyzer = BehavioralAnalyzer()
        r_analyzer = ROIAnalyzer()

        for i, video_info in enumerate(videos_to_process):
            video_path = video_info["path"]
            experiment_id = os.path.splitext(os.path.basename(video_path))[0]
            self.view.set_status(
                f"Processing {i+1}/{len(videos_to_process)}: {experiment_id}"
            )
            self.view.update_idletasks()

            if single_video_config:
                # Use the provided config as metadata
                metadata = single_video_config
            else:
                # Get metadata from the project file
                metadata = self.project_manager.get_metadata_for_experiment(
                    experiment_id
                )

            # Perform analysis
            b_results = b_analyzer.analyze(video_path)
            r_results = r_analyzer.analyze(video_path)
            reporter = Reporter(b_results, r_results, metadata)

            # Define where to save results for this video
            # In project mode, it's a sub-folder. In single mode, it's the main
            # output dir.
            if self.project_manager.project_path:
                results_dir = os.path.join(output_base_dir, f"{experiment_id}_results")
            else:
                results_dir = output_base_dir
            os.makedirs(results_dir, exist_ok=True)

            # Save all results
            reporter.tidy_data.to_parquet(
                os.path.join(results_dir, f"{experiment_id}_summary.parquet")
            )
            # We need a placeholder for tracking data for now
            tracking_data_placeholder = np.array([[0, 0]])
            np.save(
                os.path.join(results_dir, f"{experiment_id}_tracking.npy"),
                tracking_data_placeholder,
            )
            reporter.export_individual_report(
                os.path.join(results_dir, f"{experiment_id}_report")
            )

        self.view.set_status("Processing complete!")

    def generate_report(self, videos: list[dict], report_type: str = "unified"):
        """
        Generates a report from a list of processed videos.
        """
        log.info("reports.generate.start", count=len(videos), type=report_type)
        if not videos:
            self.view.show_warning("No Videos", "No videos selected for the report.")
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
                "Report Error", "Could not find any summary data for the selected videos."
            )
            return

        aggregated_df = pd.concat(all_tidy_data, ignore_index=True)
        save_path = self.view.ask_save_filename(
            title=f"Save {report_type.capitalize()} Report",
            defaultextension=".xlsx",
            initialfile=f"{report_type}_report.xlsx",
        )
        if not save_path:
            return

        # Export to Excel and a combined visual report
        aggregated_df.to_excel(save_path, index=False)
        Reporter.export_project_report(aggregated_df, os.path.splitext(save_path)[0])

        self.view.show_info("Report Generated", f"Report saved to:\n{save_path}")
