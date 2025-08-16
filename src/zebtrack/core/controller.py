"""
This module contains the main controller for the Zebtrack application.

The AppController is responsible for managing the application's state,
handling business logic, and coordinating between the user interface (View)
and the backend modules (Model).
"""

import os
import queue
import threading

import structlog

from zebtrack.core.project_manager import ProjectManager
from zebtrack.io.arduino import Arduino
from zebtrack.io.camera import Camera
from zebtrack.io.recorder import Recorder
from zebtrack.ui.gui import ApplicationGUI

log = structlog.get_logger()


class AppController:
    """
    The main controller for the application.
    """

    def __init__(self, root):
        """
        Initializes the AppController.

        Args:
            root (tk.Tk): The root Tkinter window.
        """
        self.root = root
        self.view = ApplicationGUI(root, self)  # The View component

        # --- Backend Modules ---
        from zebtrack.settings import settings
        self.project_manager = ProjectManager()
        self.recorder = Recorder()
        self.arduino = Arduino(
            port=settings.arduino.port, baud_rate=settings.arduino.baud_rate
        )
        self.detector = None
        self.camera = None

        # --- State Variables ---
        self.is_processing = True
        self.is_capturing_for_video = False
        self.is_recording = False
        self.active_frame_source = None
        self.currently_processing_video = None

        # --- Threads and Queues ---
        self.program_exit_event = threading.Event()
        self.video_stop_event = threading.Event()
        self.frame_queue = queue.Queue(maxsize=10)
        self.video_queue = queue.Queue(maxsize=300)
        self.capture_thread = None
        self.processing_thread = None
        self.video_thread = None

        log.info("controller.init.success")

    def run(self):
        """
        Starts the application's main loop.
        """
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

        self.view.create_welcome_frame()
        log.info("project.close.finished")

    def create_project_workflow(
        self, project_path, project_type, use_openvino, video_files
    ):
        """Handles the logic of creating a new project."""
        success = self.project_manager.create_new_project(
            project_path,
            project_type,
            use_openvino=use_openvino,
            video_files=video_files,
        )
        if success:
            self.view._load_project_view()
        else:
            self.view.show_error("Error", "Failed to create the new project.")

    def open_project_workflow(self, project_path):
        """Handles the logic of opening an existing project."""
        if self.project_manager.load_project(project_path):
            self.view._load_project_view()
        else:
            self.view.show_error(
                "Error",
                "Failed to load the project. Check if it's a valid project folder.",
            )

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
        success = self.recorder.start_recording(
            output_folder, cam_props["width"], cam_props["height"]
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
        """Handles the business logic for processing the next pre-recorded video."""
        if self.is_recording:
            self.view.show_warning("Busy", "A video is already being processed.")
            return

        video_path = self.project_manager.get_next_video()
        if not video_path:
            self.view.show_info(
                "Project Complete", "All videos in this project have been processed."
            )
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
        except (IOError, FileNotFoundError) as e:
            self.view.show_error("Error", f"Could not open video file: {e}")
            return

        video_basename = os.path.splitext(os.path.basename(video_path))[0]
        output_folder_name = f"{video_basename}_{group_name}_{cobaia_number}"
        output_path = os.path.join(
            self.project_manager.project_path, output_folder_name
        )

        success = self.recorder.start_recording(
            output_path, video_props["width"], video_props["height"], is_video_file=True
        )

        if success:
            self.project_manager.update_video_status(video_path, "processing")
            self.is_recording = True
            self.active_frame_source = video_source
            self.currently_processing_video = video_path

            self.processing_thread = threading.Thread(
                target=self._file_processing_loop, name="ProcessingThread", daemon=True
            )
            self.processing_thread.start()

            self.view.update_button_state("process_video", "disabled")
            self.view.set_status(f"Processing: {os.path.basename(video_path)}")
        else:
            self.view.show_error(
                "Error", "Failed to start recorder for video processing."
            )
            video_source.release()

    def _file_processing_loop(self):
        """
        Loop for processing a video file. This is the core logic that runs in a thread.
        """
        import cv2

        from zebtrack.core.detector import draw_overlay
        from zebtrack.settings import settings

        show_preview = self.view.show_preview_var.get()
        try:
            processing_interval = int(self.view.processing_interval_var.get())
        except ValueError:
            processing_interval = 1
        if processing_interval < 1:
            processing_interval = 1

        video_source = self.active_frame_source
        total_frames = video_source.get_properties()["frame_count"]
        frame_number = -1

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
            if not show_preview and total_frames > 0:
                progress_percent = int((frame_number / total_frames) * 100)
                video_name = os.path.basename(self.currently_processing_video)
                status_msg = f"Processing: {video_name} ({progress_percent}%)"
                self.root.after(0, self.view.set_status, status_msg)
            detections, _ = self.detector.process_frame(frame, "pre-recorded")
            if detections:
                props = video_source.get_properties()
                timestamp = frame_number / props["fps"] if props["fps"] > 0 else 0
                self.recorder.write_detection_data(timestamp, frame_number, detections)
            if show_preview:
                draw_overlay(frame, detections, self.detector)
                cv2.imshow("File Processing", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    self.program_exit_event.set()
        if show_preview:
            cv2.destroyAllWindows()
        self.root.after(0, self.cleanup_after_processing)

    def cleanup_after_processing(self):
        """Cleans up resources after video processing is complete."""
        video_name = os.path.basename(self.currently_processing_video)
        log.info("video_processing.cleanup.start", video_name=video_name)

        self.is_recording = False
        self.recorder.stop_recording()
        self.project_manager.update_video_status(
            self.currently_processing_video, "complete"
        )

        if self.active_frame_source:
            self.active_frame_source.release()
            self.active_frame_source = None

        self.currently_processing_video = None
        self.view.update_button_state("process_video", "normal")

        next_video = self.project_manager.get_next_video()
        if next_video:
            status_msg = f"Ready to process: {os.path.basename(next_video)}"
            self.view.set_status(
                f"Project: {self.project_manager.get_project_name()} - {status_msg}"
            )
        else:
            status_msg = "All videos processed."
            self.view.set_status(
                f"Project: {self.project_manager.get_project_name()} - {status_msg}"
            )
