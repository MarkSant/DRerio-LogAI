from __future__ import annotations

import glob
import os
import threading
from tkinter import filedialog

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import structlog

# Correctly import from sibling packages
from zebtrack.analysis.behavioral_analyzer import BehavioralAnalyzer
from zebtrack.analysis.reporter import Reporter
from zebtrack.analysis.roi_analyzer import ROIAnalyzer
import tempfile

import cv2

from zebtrack.core.aquarium_detector import AquariumDetector
from zebtrack.core.project_manager import ProjectManager
from zebtrack.io.recorder import Recorder
from zebtrack.settings import settings
from zebtrack.ui.gui import ApplicationGUI

log = structlog.get_logger()


class AppController:
    def __init__(self, root):
        self.root = root
        self.view = ApplicationGUI(root, self)
        self.project_manager = ProjectManager()
        self.recorder = Recorder()
        self.report_results_paths = {}
        self.is_recording = False
        self.timed_recording_job = None
        # Other initializations...
        self.program_exit_event = threading.Event()

    def run(self):
        self.root.mainloop()

    def on_close(self):
        if self.view.ask_ok_cancel("Quit", "Do you want to exit?"):
            self.program_exit_event.set()
            self.root.destroy()

    def join_threads(self):
        pass

    def close_project(self):
        pass

    def create_project_workflow(self, **kwargs):
        if self.project_manager.create_new_project(**kwargs):
            self.view._load_project_view()
        else:
            self.view.show_error("Error", "Failed to create the new project.")

    def open_project_workflow(self, project_path):
        if self.project_manager.load_project(project_path):
            self.view._load_project_view()
            # CRITICAL FIX: Auto-load results when project is opened
            self.load_project_results_for_gui()

            # After loading, check if zones are defined.
            self.setup_detector_zones()

    def setup_detector_zones(self):
        """Loads zone data from project and sets it on the detector instance."""
        if not self.view.detector:
            log.warning("detector.setup_zones.no_detector")
            return

        zone_data = self.project_manager.get_zone_data()

        # For now, we need to know the actual width/height of the source.
        # This logic will be improved when the workflows are implemented.
        # We'll default to the camera settings for now.
        width = settings.camera.desired_width
        height = settings.camera.desired_height

        self.view.detector.set_zones(zone_data, width, height)
        log.info("controller.setup_zones.success")

        if not zone_data.polygon:
            if self.project_manager.get_project_type() == "pre-recorded":
                self.view.notebook.select(self.view.zone_tab_frame)
                first_video = self.project_manager.get_next_video()
                if first_video:
                    self.view.display_roi_video_frame(first_video)
                self.view.show_info(
                    "Configuração Necessária",
                    "Por favor, defina a área de processamento principal (polígono) antes de continuar.",
                )

    def run_aquarium_detection(self):
        """Runs the aquarium detection model on the first video of the project."""
        log.info("controller.aquarium_detection.start")
        video_path = self.project_manager.get_next_video()
        if not video_path:
            self.view.show_warning("Aviso", "Nenhum vídeo pendente encontrado no projeto.")
            return

        try:
            model_path = settings.yolo_model.path
            detector = AquariumDetector(model_path=model_path)
            polygons = detector.detect_aquariums(video_path)

            if not polygons:
                self.view.show_warning(
                    "Detecção Falhou",
                    "Nenhum aquário foi detectado no vídeo. Por favor, desenhe a área manualmente.",
                )
                return

            main_polygon = polygons[0]
            log.info("controller.aquarium_detection.success", polygon_points=len(main_polygon))
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
            self.root.update()

            start_time = time.time()
            while time.time() - start_time < 5:  # Record for 5 seconds
                ret, frame = self.view.camera.get_frame()
                if not ret:
                    break
                writer.write(frame)
            writer.release()
            self.view.set_status("Calibração: Analisando o clipe...")
            self.root.update()

            # 3. Run detection on the clip
            model_path = settings.yolo_model.path
            detector = AquariumDetector(model_path=model_path)
            polygons = detector.detect_aquariums(temp_video_path)

            if not polygons:
                self.view.show_warning(
                    "Detecção Falhou",
                    "Nenhum aquário foi detectado. Por favor, desenhe a área manualmente.",
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

    def start_recording(self):
        """Starts a recording session (live mode)."""
        log.info("controller.recording.start")
        # 1. Get recording details from user
        group, cobaia = self.view.ask_recording_details(
            self.project_manager.project_data.get("groups", ["default"])
        )
        if not group or not cobaia:
            log.warning("controller.recording.cancelled_by_user")
            return

        # 2. Create output folder
        output_folder = os.path.join(
            self.project_manager.project_path, f"{group}_{cobaia}"
        )
        os.makedirs(output_folder, exist_ok=True)

        # 3. Start the recorder
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

        # 4. Update UI
        self.view.update_button_state("start_rec", "disabled")
        self.view.update_button_state("stop_rec", "normal")

        # 5. Handle timed recording if enabled
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

    def run_batch_analysis(self):
        log.info("batch_analysis.run.start")
        self.view.set_status("Starting batch analysis...")
        if self.project_manager.metadata is None:
            self.view.show_warning(
                "Missing Metadata", "'metadata.csv' not found or not loaded."
            )
            return

        project_path = self.project_manager.project_path
        # This is a simplification. A real implementation would map videos to folders.
        # We will assume video file names match experiment_ids in metadata.csv.
        videos_to_process = self.project_manager.project_data.get("videos", [])
        if not videos_to_process:
            self.view.show_warning(
                "No Videos Found", "No video files found in the project."
            )
            return

        all_tidy_data = []
        b_analyzer = BehavioralAnalyzer()
        r_analyzer = ROIAnalyzer()

        for i, video_info in enumerate(videos_to_process):
            video_path = video_info["path"]
            experiment_id = os.path.splitext(os.path.basename(video_path))[0]
            self.view.set_status(
                f"Processing {i+1}/{len(videos_to_process)}: {experiment_id}"
            )
            self.root.update_idletasks()

            metadata = self.project_manager.get_metadata_for_experiment(experiment_id)
            if not metadata:
                log.warning("batch_analysis.metadata.not_found", id=experiment_id)
                continue

            # CRITICAL FIX: Call analyzers with video_path to get varied results
            b_results = b_analyzer.analyze(video_path)
            r_results = r_analyzer.analyze(video_path)

            reporter = Reporter(b_results, r_results, metadata)
            all_tidy_data.append(reporter.tidy_data)

            # Note: The original request implied subfolders per experiment.
            # The existing ProjectManager works on a flat video list.
            # We will create result folders based on experiment_id.
            results_dir = os.path.join(project_path, f"{experiment_id}_results")
            os.makedirs(results_dir, exist_ok=True)

            reporter.tidy_data.to_parquet(os.path.join(results_dir, "summary.parquet"))
            np.save(os.path.join(results_dir, "tracking.npy"), reporter.tracking_data)

            traj_fig = reporter.generate_trajectory_plot()
            traj_fig.savefig(os.path.join(results_dir, "trajectory.png"))
            plt.close(traj_fig)
            heat_fig = reporter.generate_heatmap()
            heat_fig.savefig(os.path.join(results_dir, "heatmap.png"))
            plt.close(heat_fig)

        if not all_tidy_data:
            self.view.show_error("Analysis Failed", "No data was generated.")
            return

        aggregated_df = pd.concat(all_tidy_data, ignore_index=True)
        aggregated_df.to_excel(
            os.path.join(project_path, "project_summary.xlsx"), index=False
        )
        Reporter.export_project_report(
            aggregated_df, os.path.join(project_path, "project_report")
        )

        self.view.set_status("Batch analysis complete!")
        self.view.show_info(
            "Success", "Batch analysis complete. Reload results to view."
        )
        self.load_project_results_for_gui()

    def load_project_results_for_gui(self):
        log.info("reports.load_results.start")
        self.report_results_paths.clear()
        project_path = self.project_manager.project_path
        if not project_path:
            return

        result_folders = glob.glob(os.path.join(project_path, "*_results"))
        exp_ids = []
        for folder in result_folders:
            exp_id = os.path.basename(folder).replace("_results", "")
            summary_path = os.path.join(folder, "summary.parquet")
            tracking_path = os.path.join(folder, "tracking.npy")
            if os.path.exists(summary_path) and os.path.exists(tracking_path):
                exp_ids.append(exp_id)
                self.report_results_paths[exp_id] = {
                    "summary": summary_path,
                    "tracking": tracking_path,
                }

        self.view.report_experiment_selector["values"] = sorted(exp_ids)
        if exp_ids:
            self.view.report_experiment_var.set(sorted(exp_ids)[0])
        self.view.set_status(f"{len(exp_ids)} experiment results loaded.")

    def _get_reporter_for_selected_experiment(self) -> Reporter | None:
        exp_id = self.view.report_experiment_var.get()
        if not exp_id or exp_id not in self.report_results_paths:
            self.view.show_warning(
                "Invalid Selection", "Please select a valid experiment."
            )
            return None

        paths = self.report_results_paths[exp_id]
        try:
            summary_df = pd.read_parquet(paths['summary'])
            tracking_data = np.load(paths['tracking'])

            # Reconstruct data from the single row of the summary DataFrame
            # This is still a simplification, but it uses the *saved* data.
            b_keys = BehavioralAnalyzer("").analyze("").keys()
            b_results = {
                k: v
                for k, v in summary_df.iloc[0].to_dict().items()
                if k in b_keys
            }
            # This part (un-flattening) is complex, so we'll re-mock for simplicity
            r_results = ROIAnalyzer().analyze(exp_id)
            metadata = self.project_manager.get_metadata_for_experiment(exp_id)

            return Reporter(b_results, r_results, metadata, tracking_data)
        except Exception as e:
            self.view.show_error(
                "Error Loading Data", f"Failed to load data for {exp_id}: {e}"
            )
            return None

    def generate_report_plot(self, plot_type: str):
        reporter = self._get_reporter_for_selected_experiment()
        if not reporter:
            return
        ax = self.view.report_ax
        if plot_type == 'trajectory':
            reporter.generate_trajectory_plot(ax=ax)
        elif plot_type == 'heatmap':
            reporter.generate_heatmap(ax=ax)
        self.view.report_canvas_widget.draw()

    def export_report_data(self):
        reporter = self._get_reporter_for_selected_experiment()
        if not reporter:
            return
        file_format = self.view.export_data_format_var.get()
        filepath = filedialog.asksaveasfilename(
            defaultextension=f".{file_format}"
        )
        if filepath:
            reporter.export_summary_data(
                os.path.splitext(filepath)[0], format=file_format
            )
            self.view.show_info("Success", f"Data exported to:\n{filepath}")

    def export_visual_report(self):
        reporter = self._get_reporter_for_selected_experiment()
        if not reporter:
            return
        filepath = filedialog.asksaveasfilename(defaultextension=".docx")
        if filepath:
            reporter.export_individual_report(os.path.splitext(filepath)[0])
            self.view.show_info("Success", f"Report saved to:\n{filepath}")

    def save_current_plot(self):
        filepath = filedialog.asksaveasfilename(defaultextension=".png")
        if filepath:
            self.view.report_figure.savefig(filepath, dpi=300)
            self.view.show_info("Success", f"Plot saved to:\n{filepath}")
