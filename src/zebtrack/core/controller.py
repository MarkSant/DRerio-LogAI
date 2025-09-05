"""Main application controller for Zebtrack.

Coordinates UI (View) with backend modules (Model): project management, video
capture/processing, detection pipeline, recording, Arduino I/O.
"""

from __future__ import annotations

import os
import queue
import threading
import time

try:
    import structlog  # type: ignore
except ImportError:  # Fallback lightweight logger so code still runs
    import logging as structlog  # type: ignore
    structlog.get_logger = lambda *a, **k: structlog.getLogger("zebtrack")

import pandas as pd

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer
from zebtrack.analysis.roi import ROI, ROIAnalyzer
from zebtrack.core.project_manager import ProjectManager
from zebtrack.core.aquarium_detector import AquariumDetector
from zebtrack.core.calibration import Calibration
from zebtrack.io.arduino import Arduino
from zebtrack.io.camera import Camera
from zebtrack.io.recorder import Recorder
from zebtrack.ui.gui import ApplicationGUI

log = structlog.get_logger()


class AppController:
    """Primary application controller."""

    def __init__(self, root):
        self.root = root
        self.view = ApplicationGUI(root, self)

        # Backend modules
        from zebtrack.settings import settings

        self.project_manager = ProjectManager()
        self.recorder = Recorder()
        self.arduino = Arduino(
            port=settings.arduino.port, baud_rate=settings.arduino.baud_rate
        )
        self.detector = None
        self.camera = None

        # ROI Analysis State
        self.roi_analysis_df = None
        self.roi_video_path = None
        self.roi_analysis_parquet_path = None

        # State
        self.is_processing = True
        self.is_capturing_for_video = False
        self.is_recording = False
        self.active_frame_source = None
        self.currently_processing_video: str | None = None
        self.processing_start_time: float | None = None
        self._last_frame_time: float | None = None

        # Threads / Queues
        self.program_exit_event = threading.Event()
        self.video_stop_event = threading.Event()
        self.frame_queue: queue.Queue = queue.Queue(maxsize=10)
        self.video_queue: queue.Queue = queue.Queue(maxsize=300)
        self.capture_thread: threading.Thread | None = None
        self.processing_thread: threading.Thread | None = None
        self.video_thread: threading.Thread | None = None

        log.info("controller.init.success")

    # ---------------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------------
    def run(self):
        log.info("ui.mainloop.start")
        self.root.mainloop()

    def on_close(self):
        """Handles the application shutdown process."""
        log.info("ui.close_button.clicked")
        if self.view.ask_ok_cancel("Quit", "Do you want to exit the program?"):
            log.info("user.quit.confirmed")

            self.program_exit_event.set()

            self.join_threads()

            if self.camera:
                self.camera.release()
            if self.active_frame_source and not isinstance(
                self.active_frame_source, Camera
            ):
                self.active_frame_source.release()
            self.arduino.close()

            self.root.destroy()
            log.info("application.shutdown.complete")

    def join_threads(self):
        """Waits for all core threads to finish."""
        log.info("threads.join.start")
        if (
            hasattr(self, "capture_thread")
            and self.capture_thread
            and self.capture_thread.is_alive()
        ):
            self.capture_thread.join()
        if (
            hasattr(self, "processing_thread")
            and self.processing_thread
            and self.processing_thread.is_alive()
        ):
            self.processing_thread.join()
        if (
            hasattr(self, "video_thread")
            and self.video_thread
            and self.video_thread.is_alive()
        ):
            self.video_thread.join(timeout=5)
        log.info("threads.join.finished")

    def stop_recording(self):
        """Stops the recording for a 'live' project."""
        self.is_recording = False
        self.is_capturing_for_video = False
        self.video_stop_event.set()

        if hasattr(self, "video_thread") and self.video_thread.is_alive():
            self.video_thread.join(timeout=5)

        self.recorder.stop_recording()

        self.view.update_button_state("start_rec", "normal")
        self.view.update_button_state("stop_rec", "disabled")
        self.view.set_status(
            f"Project: {self.project_manager.get_project_name()} (live) - Ready"
        )
        self.view.show_info("Success", "Recording stopped and files saved.")

    def close_project(self):
        """Closes the current project and returns to the welcome screen."""
        log.info("project.close.start")
        self.program_exit_event.set()

        if self.is_recording and self.project_manager.get_project_type() == "live":
            self.stop_recording()

        self.join_threads()
        self.program_exit_event.clear()

        if self.camera:
            self.camera.release()
            self.camera = None
        if self.active_frame_source:
            self.active_frame_source.release()
            self.active_frame_source = None

        self.project_manager = ProjectManager()

        self.view._create_welcome_frame()
        log.info("project.close.finished")

    def create_project_workflow(
        self,
        project_path,
        project_type,
        use_openvino,
        video_files,
        num_aquariums,
        aquarium_width_cm,
        aquarium_height_cm,
    ):
        """Handles the logic of creating a new project."""
        success = self.project_manager.create_new_project(
            project_path=project_path,
            project_type=project_type,
            use_openvino=use_openvino,
            video_files=video_files,
            num_aquariums=num_aquariums,
            aquarium_width_cm=aquarium_width_cm,
            aquarium_height_cm=aquarium_height_cm,
        )
        if success:
            self._run_automatic_calibration()
            self.view._load_project_view()
        else:
            self.view.show_error("Error", "Failed to create the new project.")

    def open_project_workflow(self, project_path):
        """Handles the logic of opening an existing project."""
        if self.project_manager.load_project(project_path):
            self._run_automatic_calibration()
            self.view._load_project_view()
        else:
            self.view.show_error(
                "Error",
                "Failed to load the project. Check if it's a valid project folder.",
            )

    def _run_automatic_calibration(self):
        """
        Runs the automatic aquarium detection and calibration process.
        This is intended to be called after a project is created or loaded.
        """
        from zebtrack.settings import settings

        log.info("calibration.auto.start")
        pm = self.project_manager

        # Check if calibration data already exists
        if pm.project_data.get("calibration", {}).get("homography_matrix"):
            log.info("calibration.auto.skip_already_done")
            return

        # Get the first video for analysis
        video_path = pm.get_next_video()
        if not video_path:
            log.warning("calibration.auto.no_video_found")
            if pm.get_project_type() == "pre-recorded":
                self.view.show_warning(
                    "Calibration Warning",
                    "Could not run automatic calibration: no video files found in project.",
                )
            return

        try:
            # 1. Detect aquariums
            model_path = settings.aquarium_segmentation_model.path
            detector = AquariumDetector(model_path)
            polygons = detector.detect_aquariums(video_path)

            if not polygons:
                self.view.show_warning(
                    "Calibration Failed",
                    "Could not automatically detect any aquariums in the video.",
                )
                return

            calib_settings = pm.project_data.get("calibration", {})
            num_expected = calib_settings.get("num_aquariums", 1)
            if len(polygons) != num_expected:
                self.view.show_warning(
                    "Calibration Warning",
                    f"Detected {len(polygons)} aquariums, but project is set to {num_expected}. "
                    "You may need to adjust project settings or check the video.",
                )

            arenas_data = []
            successful_calibrations = 0
            for i, polygon in enumerate(polygons):
                calibration = Calibration(
                    polygon=polygon,
                    real_width_cm=calib_settings.get("aquarium_width_cm", 0),
                    real_height_cm=calib_settings.get("aquarium_height_cm", 0),
                )
                if calibration.homography_matrix is not None:
                    arenas_data.append({
                        "id": i + 1,
                        "polygon_px": [p.tolist() for p in polygon],
                        "homography_matrix": calibration.homography_matrix.tolist(),
                        "pixel_per_cm_ratio": calibration.pixel_per_cm_ratio,
                        "target_dims_px": calibration.target_dims_px,
                    })
                    successful_calibrations += 1

            if successful_calibrations > 0:
                pm.project_data["calibration"]["arenas"] = arenas_data
                pm.save_project()
                self.view.show_info(
                    "Calibration Complete",
                    f"Successfully calibrated {successful_calibrations}/{len(polygons)} detected aquariums.",
                )
            else:
                self.view.show_error("Calibration Failed", "Could not create a valid calibration for any detected aquarium.")

        except Exception as e:
            log.error("calibration.auto.failed", error=str(e), exc_info=True)
            self.view.show_error("Calibration Error", f"An unexpected error occurred during calibration: {e}")


    def start_recording(self):
        """Handles the business logic for starting a recording session."""
        if not self.project_manager.project_data.get("groups"):
            self.view.show_warning(
                "Setup Required", "Please define groups for this project first."
            )
            return

        details = self.view.ask_recording_details(
            self.project_manager.project_data["groups"]
        )
        if not details:
            return

        group_name, cobaia_number = details
        output_folder = os.path.join(
            self.project_manager.project_path, f"{group_name}_{cobaia_number}"
        )

        cam_props = self.camera.get_properties()

        # Get calibration data
        calib_data = self.project_manager.project_data.get("calibration", {})
        ratio = calib_data.get("pixel_per_cm_ratio")

        success = self.recorder.start_recording(
            output_folder,
            cam_props["width"],
            cam_props["height"],
            pixel_per_cm_ratio=ratio,
        )

        if success:
            with self.frame_queue.mutex:
                self.frame_queue.queue.clear()
            with self.video_queue.mutex:
                self.video_queue.queue.clear()

            self.is_recording = True
            self.is_capturing_for_video = True
            self.video_stop_event.clear()
            self.video_thread = threading.Thread(
                target=self._video_recording_loop, daemon=True
            )
            self.video_thread.start()

            self.view.update_button_state("start_rec", "disabled")
            self.view.update_button_state("stop_rec", "normal")
            self.view.set_status(f"Recording to: {os.path.basename(output_folder)}")
        else:
            self.view.show_error("Error", "Failed to start recorder.")

    def _video_recording_loop(self):
        """
        Loop executed in a thread to write video frames to a file.
        """
        log.info("video_thread.start")
        while not self.video_stop_event.is_set():
            try:
                frame = self.video_queue.get(timeout=1)
                self.recorder.write_video_frame(frame)
            except queue.Empty:
                continue
        log.info("video_thread.finished")

    def process_next_video(self):
        """Start processing the next queued pre-recorded video."""
        log.info("process_next_video.start")
        if self.is_recording:
            self.view.show_warning("Busy", "A video is already being processed.")
            return

        video_path = self.project_manager.get_next_video()
        if not video_path:
            log.info("process_next_video.none_left")
            self.view.show_info(
                "Project Complete", "All videos in this project have been processed."
            )
            return

        # If all videos were previously complete and user restarts, optionally reset.
        # (Only reset if user confirms.)
        videos = self.project_manager.project_data.get("videos", [])
        completed_only = all(v.get("status") == "complete" for v in videos)
        if completed_only:
            # Non-blocking gentle reset without popup for now;
            # comment out if not desired.
            self.project_manager.reset_all_video_statuses("pending")
            video_path = self.project_manager.get_next_video()
            if not video_path:
                return

        if not self.project_manager.project_data.get("groups"):
            self.view.show_warning(
                "Setup Required", "Please define groups for this project first."
            )
            return

        details = self.view.ask_recording_details(
            self.project_manager.project_data["groups"]
        )
        if not details:
            return
        group_name, cobaia_number = details

        try:
            from zebtrack.io.video_source import VideoFileSource

            video_source = VideoFileSource(video_path)
            video_props = video_source.get_properties()
            self.detector.update_scaling(video_props["width"], video_props["height"])
            log.info(
                "process_next_video.video_opened",
                path=video_path,
                props=video_props,
            )
        except (IOError, FileNotFoundError) as e:
            self.view.show_error("Error", f"Could not open video file: {e}")
            log.error("process_next_video.video_open_fail", error=str(e))
            return

        video_basename = os.path.splitext(os.path.basename(video_path))[0]
        output_folder_name = f"{video_basename}_{group_name}_{cobaia_number}"
        output_path = os.path.join(
            self.project_manager.project_path, output_folder_name
        )

        # Get calibration data
        calib_data = self.project_manager.project_data.get("calibration", {})
        ratio = calib_data.get("pixel_per_cm_ratio")

        success = self.recorder.start_recording(
            output_path,
            video_props["width"],
            video_props["height"],
            is_video_file=True,
            pixel_per_cm_ratio=ratio,
        )
        if not success:
            log.error(
                "process_next_video.recorder_start_failed",
                output_path=output_path,
            )
            self.view.show_error(
                "Error", "Failed to start recorder for video processing."
            )
            video_source.release()
            return

        # Update state
        self.project_manager.update_video_status(video_path, "processing")
        self.is_recording = True
        self.active_frame_source = video_source
        self.currently_processing_video = video_path
        self.processing_start_time = time.time()

        # Persist preferences
        try:
            interval_val = int(self.view.processing_interval_var.get())
        except ValueError:
            interval_val = 1
        self.project_manager.project_data["last_processing_interval"] = interval_val
        self.project_manager.project_data["last_show_preview"] = bool(
            self.view.show_preview_var.get()
        )
        self.project_manager.save_project()
        log.info(
            "process_next_video.state_set",
            video=video_path,
            output=output_path,
            interval=interval_val,
            preview=self.view.show_preview_var.get(),
        )

        # Launch worker thread
        self.processing_thread = threading.Thread(
            target=self._file_processing_loop, name="ProcessingThread", daemon=True
        )
        self.processing_thread.start()

        # UI init
        self.view.update_button_state("process_video", "disabled")
        self.view.update_button_state("cancel_processing", "normal")
        self.view.set_status(f"Processing: {os.path.basename(video_path)}")
        self.view.update_progress(0)
        self.view.update_progress_stats(
            total=video_props["frame_count"],
            processed=0,
            detected=0,
            percent=0.0,
            elapsed=0.0,
            eta=-1,
        )
        log.info("process_next_video.thread_started")

    def _file_processing_loop(self):
        """Worker thread: processes a pre-recorded video file frame-by-frame."""
        import cv2

        from zebtrack.core.detector import draw_overlay
        from zebtrack.settings import settings

        try:
            processing_interval = int(self.view.processing_interval_var.get())
        except ValueError:
            processing_interval = 1
        if processing_interval < 1:
            processing_interval = 1
        show_preview = self.view.show_preview_var.get()

        video_source = self.active_frame_source
        props = video_source.get_properties()
        total_frames = props["frame_count"]
        frame_number = -1
        detected_frames = 0
        start_time = time.time()

        while not self.program_exit_event.is_set() and frame_number < total_frames:
            if frame_number < 0:
                offset = settings.video_processing.processing_offset
                target_frame = offset if offset > 0 else 1
            else:
                target_frame = frame_number + processing_interval
            if target_frame >= total_frames:
                break

            video_source.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = video_source.get_frame()
            if not ret:
                break
            frame_number = target_frame

            # Apply perspective warp if calibration data is available
            calib_data = self.project_manager.project_data.get("calibration", {})
            h_matrix = calib_data.get("homography_matrix")
            target_dims = calib_data.get("target_dims_px")

            if h_matrix and target_dims:
                import numpy as np
                h_matrix = np.array(h_matrix)
                frame = cv2.warpPerspective(frame, h_matrix, tuple(target_dims))

            progress_percent = (
                (frame_number / total_frames) * 100 if total_frames > 0 else 0
            )
            video_name = os.path.basename(self.currently_processing_video or "")
            status_msg = f"Processing: {video_name} ({progress_percent:.1f}%)"
            self.root.after(0, self.view.update_progress, progress_percent)
            self.root.after(0, self.view.set_status, status_msg)

            detections, _ = self.detector.process_frame(frame, "pre-recorded")
            if detections:
                detected_frames += 1
                timestamp = frame_number / props["fps"] if props["fps"] > 0 else 0
                self.recorder.write_detection_data(timestamp, frame_number, detections)

            elapsed = time.time() - start_time
            remaining = max(total_frames - frame_number, 0)
            fps_est = (frame_number / elapsed) if elapsed > 0 else 0
            eta = (remaining / fps_est) if fps_est > 0 else -1
            stats = {
                "total": total_frames,
                "processed": frame_number,
                "detected": detected_frames,
                "percent": progress_percent,
                "elapsed": elapsed,
                "eta": eta,
            }
            self.root.after(
                0, lambda s=stats: self.view.update_progress_stats(**s)
            )

            if show_preview:
                draw_overlay(frame, detections, self.detector)
                self.root.after(0, lambda f=frame.copy(): self.view.display_frame(f))

        # Cleanup on main thread
        self.root.after(0, self.cleanup_after_processing)

    def cancel_processing(self):
        """User-requested cancellation of current pre-recorded video processing."""
        if not self.is_recording or not self.currently_processing_video:
            return
        self.project_manager.update_video_status(
            self.currently_processing_video, "cancelled"
        )
        self.program_exit_event.set()
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=2)
        self.program_exit_event.clear()
        if self.active_frame_source:
            self.active_frame_source.release()
            self.active_frame_source = None
        self.recorder.stop_recording()
        self.is_recording = False
        self.currently_processing_video = None
        self.view.update_button_state("process_video", "normal")
        self.view.update_button_state("cancel_processing", "disabled")
        self.view.hide_progress_bar()
        self.view.set_status(
            f"Project: {self.project_manager.get_project_name()} - Cancelled"
        )

    def load_data_for_roi_analysis(self, parquet_path: str):
        """Loads trajectory data and populates the ROI analysis tab."""
        log.info("roi_analysis.load_data.start", path=parquet_path)
        try:
            self.roi_analysis_parquet_path = parquet_path
            self.roi_analysis_df = pd.read_parquet(parquet_path)

            # Populate arena selector
            arenas = self.project_manager.project_data.get("calibration", {}).get("arenas", [])
            arena_ids = [f"Aquário {a['id']}" for a in arenas]
            self.view.update_arena_selector(arena_ids)

            base_folder = os.path.dirname(parquet_path)
            folder_name = os.path.basename(base_folder)
            video_name_part = folder_name.split("_")[0]

            video_file_found = None
            for v in self.project_manager.project_data.get("videos", []):
                if video_name_part in os.path.basename(v['path']):
                    video_file_found = v['path']
                    break

            if not video_file_found:
                self.roi_video_path = None
                self.view.show_warning("Aviso", "Não foi possível encontrar o vídeo associado.")
            else:
                self.roi_video_path = video_file_found
                self.view.display_roi_video_frame(video_file_found)

            self.view.set_status(f"Pronto para definir ROIs em: {os.path.basename(parquet_path)}")

        except Exception as e:
            log.error("roi_analysis.load_data.failed", error=str(e))
            self.view.show_error("Erro ao Carregar Dados", f"Falha ao carregar {parquet_path}: {e}")
            self.roi_analysis_df = None
            self.roi_analysis_parquet_path = None

    def run_roi_analysis(self, rois_for_arena: list, flutter_n: int, num_animals: int, social_radius_cm: float, arena_id: str):
        """Executes the full ROI analysis pipeline for a specific arena."""
        if self.roi_analysis_df is None:
            self.view.show_error("Erro", "Nenhum dado de trajetória carregado.")
            return

        log.info("roi_analysis.run.start", arena=arena_id, animals=num_animals)
        try:
            from shapely.geometry import Point, Polygon

            # --- 1. Create ROI objects from GUI definitions ---
            rois = []
            for d in rois_for_arena:
                if d['type'] == 'polygon':
                    rois.append(ROI(name=d['name'], geometry=Polygon(d['coords'])))
                elif d['type'] == 'circle':
                    cx, cy, radius = d['coords']
                    rois.append(ROI(name=d['name'], geometry=Point(cx, cy).buffer(radius)))

            # --- 2. Get Arena-specific Data ---
            arena_idx = int(arena_id.split(" ")[-1]) - 1
            arenas_data = self.project_manager.project_data.get("calibration", {}).get("arenas", [])
            if arena_idx >= len(arenas_data):
                self.view.show_error("Erro", "ID de aquário selecionado inválido.")
                return

            arena_data = arenas_data[arena_idx]
            arena_poly_px = Polygon(arena_data["polygon_px"])
            pixel_cm_x, pixel_cm_y = arena_data["pixel_per_cm_ratio"]

            # --- 2. Filter trajectory data for the selected arena ---
            def is_in_arena(row):
                return Point(row["x_center_px"], row["y_center_px"]).within(arena_poly_px)

            arena_df = self.roi_analysis_df[self.roi_analysis_df.apply(is_in_arena, axis=1)].copy()
            if arena_df.empty:
                self.view.show_warning("Aviso", "Nenhuma trajetória detectada dentro do polígono do aquário selecionado.")
                return

            # --- 3. Perform Analysis ---
            rois = [ROI(name=d['name'], geometry=Polygon(d['coords'])) for d in rois_for_arena]
            report = f"### Relatório de Análise: {arena_id} ###\n"
            all_summaries = []

            track_ids = arena_df['track_id'].unique()

            # --- 3a. Single-Animal Metrics (run for each animal) ---
            for track_id in track_ids:
                animal_df = arena_df[arena_df['track_id'] == track_id]
                report += f"\n--- Animal ID: {track_id} ---\n"

                b_analyzer = ConcreteBehavioralAnalyzer(
                    trajectory_df=animal_df.copy(),
                    pixelcm_x=pixel_cm_x,
                    pixelcm_y=pixel_cm_y,
                    video_height_px=arena_data['target_dims_px'][1],
                    arena_polygon_px=arena_data['polygon_px']
                )
                roi_analyzer = ROIAnalyzer(b_analyzer, rois, flutter_n_frames=flutter_n)

                time_spent = roi_analyzer.get_time_spent_in_rois()
                # ... and other metrics ...

                for roi in rois:
                    roi_name = roi.name
                    report += f"  ROI: {roi_name} -> Tempo: {time_spent[roi_name]['seconds']:.2f}s\n"
                    all_summaries.append({'animal_id': track_id, 'roi_name': roi_name, **time_spent[roi_name]})

            # --- 3b. Multi-Animal Metrics ---
            if num_animals > 1:
                report += "\n--- Análise Social (Todos os Animais) ---\n"
                social_results = ROIAnalyzer.analyze_social_proximity(
                    arena_df, social_radius_cm, pixel_cm_x, pixel_cm_y
                )
                for track_id, seconds in social_results['social_time_seconds'].items():
                    percent = social_results['social_time_percentage'][track_id]
                    report += f"  - Animal {track_id}: {seconds:.2f}s em grupo social ({percent:.1f}%)\n"

            # --- 4. Display and Save Results ---
            self.view.display_roi_results(report)

            output_folder = os.path.dirname(self.roi_analysis_parquet_path)
            summary_df = pd.DataFrame(all_summaries)
            filename = os.path.join(output_folder, f"6_ROI_Analysis_{arena_id.replace(' ', '_')}.parquet")
            summary_df.to_parquet(filename)

            self.view.show_info("Sucesso", f"Análise concluída e salva em:\n{filename}")
            log.info("roi_analysis.run.success", arena=arena_id)

        except Exception as e:
            log.error("roi_analysis.run.failed", error=str(e), exc_info=True)
            self.view.show_error("Erro na Análise", f"Ocorreu um erro inesperado: {e}")

    def get_arena_data(self, arena_id: str) -> dict | None:
        """Returns the calibration data for a specific arena."""
        try:
            arena_idx = int(arena_id.split(" ")[-1]) - 1
            arenas_data = self.project_manager.project_data.get("calibration", {}).get("arenas", [])
            if arena_idx < len(arenas_data):
                return arenas_data[arena_idx]
        except (ValueError, IndexError):
            return None
        return None

    def run_center_periphery_analysis(self, arena_id: str, method: str, value: float):
        """Runs the center-periphery analysis and displays the results."""
        if self.roi_analysis_df is None:
            self.view.show_error("Erro", "Nenhum dado de trajetória carregado.")
            return
        log.info("center_periphery.run.start", arena=arena_id, method=method, value=value)
        try:
            # This analysis runs on the first animal found in the arena
            arena_data = self.get_arena_data(arena_id)
            if not arena_data:
                self.view.show_error("Erro", "Não foi possível encontrar dados para o aquário selecionado.")
                return

            def is_in_arena(row):
                from shapely.geometry import Point, Polygon
                return Point(row["x_center_px"], row["y_center_px"]).within(Polygon(arena_data['polygon_px']))

            arena_df = self.roi_analysis_df[self.roi_analysis_df.apply(is_in_arena, axis=1)].copy()
            if arena_df.empty:
                self.view.show_warning("Aviso", "Nenhuma trajetória detectada no aquário selecionado.")
                return

            # For simplicity, we run this on the first track ID found
            track_id = arena_df['track_id'].unique()[0]
            animal_df = arena_df[arena_df['track_id'] == track_id]

            b_analyzer = ConcreteBehavioralAnalyzer(
                trajectory_df=animal_df.copy(),
                pixelcm_x=arena_data['pixel_per_cm_ratio'][0],
                pixelcm_y=arena_data['pixel_per_cm_ratio'][1],
                video_height_px=arena_data['target_dims_px'][1],
                arena_polygon_px=arena_data['polygon_px']
            )

            # The ROIAnalyzer class has the method we need
            # We can instantiate it with no ROIs since we're calling a specific method
            temp_analyzer = ROIAnalyzer(b_analyzer, [], flutter_n_frames=1)
            results = temp_analyzer.analyze_center_vs_periphery(method=method, value=value)

            # Format and display
            report = f"### Análise Centro vs. Periferia ({arena_id}) ###\n"
            report += f"Método: {method}, Valor: {value}\n\n"
            for zone, metrics in results['time_spent'].items():
                report += f"--- Zona: {zone} ---\n"
                report += f"  - Tempo Gasto: {metrics['seconds']:.2f}s ({metrics['percentage']:.1f}%)\n"
                report += f"  - Distância: {results['distance'][zone]:.2f} cm\n"
                report += f"  - Entradas: {results['entry_counts'][zone]}\n\n"

            self.view.display_roi_results(report)

        except Exception as e:
            log.error("center_periphery.run.failed", error=str(e), exc_info=True)
            self.view.show_error("Erro na Análise", f"Ocorreu um erro: {e}")


    def cleanup_after_processing(self):
        """Finalize state after a video finishes processing (success path)."""
        log.info("processing.cleanup.start")
        # Stop recorder if still running
        try:
            if self.is_recording:
                self.recorder.stop_recording()
        except Exception as e:  # pragma: no cover - defensive
            log.error("processing.cleanup.recorder_stop_error", error=str(e))

        # Release video source
        if self.active_frame_source:
            try:
                self.active_frame_source.release()
            except Exception as e:  # pragma: no cover
                log.error("processing.cleanup.source_release_error", error=str(e))
            self.active_frame_source = None

        # Mark video complete if still in 'processing'
        if self.currently_processing_video:
            # Only update if not cancelled earlier
            for v in self.project_manager.project_data.get("videos", []):
                if (
                    v.get("path") == self.currently_processing_video
                    and v.get("status") == "processing"
                ):
                    self.project_manager.update_video_status(
                        self.currently_processing_video, "complete"
                    )
                    break

        if self.currently_processing_video:
            finished_video = os.path.basename(self.currently_processing_video)
        else:
            finished_video = "?"
        self.currently_processing_video = None
        self.is_recording = False

        # UI updates
        self.view.update_button_state("process_video", "normal")
        self.view.update_button_state("cancel_processing", "disabled")

        # Decide status message
        next_video = self.project_manager.get_next_video()
        if next_video:
            msg = f"Finished: {finished_video}. Ready for next video."
        else:
            msg = f"Finished: {finished_video}. All videos processed."
        self.view.set_status(
            f"Project: {self.project_manager.get_project_name()} - {msg}"
        )

        # Optionally hide progress bar after completion
        # (comment out if you want it to stay)
        self.view.hide_progress_bar()

        log.info("processing.cleanup.done", next_pending=bool(next_video))
