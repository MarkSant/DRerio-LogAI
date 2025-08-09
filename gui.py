import tkinter as tk
from tkinter import (filedialog, simpledialog, messagebox, Button, Label, Frame,
                     StringVar, OptionMenu, Toplevel)
import threading
import queue
import time
import os
import cv2

# Import custom modules
import config
from camera import Camera
from arduino import Arduino
from detector import Detector, draw_overlay
from recorder import Recorder
from project_manager import ProjectManager
from video_source import VideoFileSource

class ApplicationGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Zebtrack Controller")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # --- Initialize Modules ---
        self.camera = None  # Will be initialized if needed
        self.arduino = Arduino()
        self.detector = Detector()
        self.recorder = Recorder()
        self.project_manager = ProjectManager()

        # --- State Variables ---
        self.is_processing = True
        self.is_capturing_for_video = False
        self.is_recording = False
        self.active_frame_source = None
        self.welcome_frame = None
        self.main_controls_frame = None
        self.currently_processing_video = None

        # --- Threading and Queues ---
        self.program_exit_event = threading.Event()
        self.video_stop_event = threading.Event()
        self.frame_queue = queue.Queue(maxsize=10)
        self.video_queue = queue.Queue(maxsize=300)

        # --- UI Elements ---
        self._create_welcome_frame()

    def _create_welcome_frame(self):
        """Creates the initial UI for project selection."""
        if self.main_controls_frame:
            self.main_controls_frame.destroy()

        self.root.geometry("400x150")
        self.welcome_frame = Frame(self.root)
        self.welcome_frame.pack(expand=True)

        Label(self.welcome_frame, text="Welcome to Zebtrack Controller", font=("Helvetica", 16)).pack(pady=10)

        btn_frame = Frame(self.welcome_frame)
        btn_frame.pack(pady=10)

        Button(btn_frame, text="Create New Project", command=self._create_project_workflow).pack(side="left", padx=10)
        Button(btn_frame, text="Open Existing Project", command=self._open_project_workflow).pack(side="left", padx=10)

    def _create_main_control_frame(self):
        """Creates the main UI for controlling the application after a project is loaded."""
        if self.welcome_frame:
            self.welcome_frame.destroy()

        self.root.geometry("") # Reset geometry
        self.main_controls_frame = Frame(self.root)
        self.main_controls_frame.pack(padx=10, pady=10)

        project_type = self.project_manager.get_project_type()

        if project_type == "live":
            Button(self.main_controls_frame, text="Define Groups", command=self._define_groups).pack(side="left", padx=5)
            self.start_rec_btn = Button(self.main_controls_frame, text="Start Recording", command=self._start_recording)
            self.start_rec_btn.pack(side="left", padx=5)
            self.stop_rec_btn = Button(self.main_controls_frame, text="Stop Recording", command=self._stop_recording, state="disabled")
            self.stop_rec_btn.pack(side="left", padx=5)
        elif project_type == "pre-recorded":
            Button(self.main_controls_frame, text="Define Groups", command=self._define_groups).pack(side="left", padx=5)
            self.process_video_btn = Button(self.main_controls_frame, text="Process Next Video", command=self._process_next_video)
            self.process_video_btn.pack(side="left", padx=5)

        Button(self.main_controls_frame, text="Close Project", command=self._close_project).pack(side="left", padx=5)

        status_text = f"Project: {self.project_manager.get_project_name()} ({project_type})"
        self.status_var = StringVar(value=status_text)
        Label(self.root, textvariable=self.status_var).pack(pady=5)

    def _load_project_view(self):
        """Transitions from the welcome screen to the main control view and starts threads."""
        self._create_main_control_frame()

        project_type = self.project_manager.get_project_type()
        if project_type == "live":
            try:
                self.camera = Camera()
                self.active_frame_source = self.camera
            except IOError as e:
                messagebox.showerror("Camera Error", str(e))
                self._create_welcome_frame() # Go back to welcome screen
                return
        elif project_type == "pre-recorded":
            # Update UI based on project state
            next_video = self.project_manager.get_next_video()
            if next_video is None:
                self.process_video_btn.config(state="disabled")
                self.status_var.set(f"Project: {self.project_manager.get_project_name()} - All videos processed.")
            else:
                self.status_var.set(f"Project: {self.project_manager.get_project_name()} - Ready to process: {os.path.basename(next_video)}")

        # --- Start Core Threads ---
        self.capture_thread = threading.Thread(target=self._frame_capture_loop, daemon=True)
        self.processing_thread = threading.Thread(target=self._object_detection_loop, daemon=True)

        self.capture_thread.start()
        self.processing_thread.start()

    # --- Core Application Loops (run in threads) ---
    def _frame_capture_loop(self):
        frame_count = 0
        while not self.program_exit_event.is_set():
            if not self.active_frame_source:
                time.sleep(0.1)
                continue

            # Identify if the source is a file
            is_file_source = isinstance(self.active_frame_source, VideoFileSource)

            ret, frame = self.active_frame_source.get_frame()
            if not ret:
                print("Capture thread: end of source.")
                if is_file_source:
                    self.root.after(0, self._handle_source_finished)
                self.active_frame_source = None
                continue

            frame_count += 1
            if not self.frame_queue.full():
                self.frame_queue.put((frame_count, frame.copy()))
            if self.is_capturing_for_video and not self.video_queue.full():
                self.video_queue.put(frame.copy())

            # For files, we can sleep less to process faster
            if not is_file_source:
                time.sleep(1 / (config.FPS * 1.5))

    def _object_detection_loop(self):
        while not self.program_exit_event.is_set():
            try:
                frame_count, frame = self.frame_queue.get(timeout=1)
            except queue.Empty:
                continue

            # Determine if the source is a file before processing
            is_file_source = isinstance(self.active_frame_source, VideoFileSource)
            project_type = self.project_manager.get_project_type()

            if self.is_processing:
                # Use a consistent processing interval, respecting the config file
                if (frame_count - config.PROCESSING_OFFSET) % config.PROCESSING_INTERVAL == 0:
                    # Pass project_type to the detector
                    detections, command = self.detector.process_frame(frame, project_type)

                    # Arduino command is now only generated for 'live' projects inside detector
                    if command is not None:
                        self.arduino.send_command(command)

                    if self.is_recording:
                        timestamp = 0
                        log_frame_num = 0
                        if is_file_source:
                            props = self.active_frame_source.get_properties()
                            log_frame_num = int(self.active_frame_source.get_current_frame_number())
                            timestamp = log_frame_num / props['fps'] if props['fps'] > 0 else 0
                        else:
                            log_frame_num = frame_count - self.recorder.recording_start_frame
                            timestamp = time.time() - self.recorder.start_time

                        self.recorder.write_detection_data(timestamp, log_frame_num, detections)
                else:
                    detections = []

                # Always draw the overlay with detections
                draw_overlay(frame, detections)

            # Add progress bar for file sources
            if is_file_source and self.active_frame_source:
                props = self.active_frame_source.get_properties()
                total_frames = props.get('frame_count', 0)
                current_frame_num = self.active_frame_source.get_current_frame_number()
                if total_frames > 0:
                    progress = current_frame_num / total_frames
                    bar_width = int(progress * frame.shape[1])
                    bar_height = 20
                    # Draw background
                    cv2.rectangle(frame, (0, frame.shape[0] - bar_height), (frame.shape[1], frame.shape[0]), (50, 50, 50), -1)
                    # Draw foreground
                    cv2.rectangle(frame, (0, frame.shape[0] - bar_height), (bar_width, frame.shape[0]), (0, 255, 0), -1)

            # Optimize Video Display Speed
            if is_file_source:
                if frame_count % 60 == 0:
                    cv2.imshow('Live View', frame)
            else:
                cv2.imshow('Live View', frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                self._on_close()
                break
        cv2.destroyAllWindows()

    def _video_recording_loop(self):
        while not self.video_stop_event.is_set():
            try:
                frame = self.video_queue.get(timeout=1)
                self.recorder.write_video_frame(frame)
            except queue.Empty:
                continue
        print("Video recording thread finished.")

    # --- Project Workflow Methods ---
    def _create_project_workflow(self):
        base_path = filedialog.askdirectory(title="Select a Parent Folder for the Project")
        if not base_path: return

        project_name = simpledialog.askstring("Project Name", "Enter a name for the new project:")
        if not project_name: return

        project_path = os.path.join(base_path, project_name)
        if os.path.exists(project_path) and os.listdir(project_path):
            messagebox.showerror("Error", "A project folder with this name already exists and is not empty.")
            return

        type_window = Toplevel(self.root)
        type_window.title("Project Type")
        type_var = StringVar()
        Label(type_window, text="Choose the project type:").pack(padx=20, pady=10)
        Button(type_window, text="Live Analysis", command=lambda: [type_var.set("live"), type_window.destroy()]).pack(fill="x", padx=20, pady=5)
        Button(type_window, text="Pre-recorded Analysis", command=lambda: [type_var.set("pre-recorded"), type_window.destroy()]).pack(fill="x", padx=20, pady=5)
        self.root.wait_window(type_window)
        project_type = type_var.get()

        if not project_type: return

        video_files = []
        if project_type == "pre-recorded":
            video_files = filedialog.askopenfilenames(title="Select Video Files", filetypes=[("Video files", "*.mp4 *.avi")])
            if not video_files: return

        success = self.project_manager.create_new_project(project_path, project_type, video_files)
        if success:
            self._load_project_view()
        else:
            messagebox.showerror("Error", "Failed to create the new project.")

    def _open_project_workflow(self):
        project_path = filedialog.askdirectory(title="Select an Existing Project Folder")
        if not project_path: return

        if self.project_manager.load_project(project_path):
            self._load_project_view()
        else:
            messagebox.showerror("Error", "Failed to load the project. Check if it's a valid project folder.")

    def _close_project(self):
        if self.is_recording:
            if self.project_manager.get_project_type() == 'live':
                self._stop_recording()
            else:
                self._handle_source_finished()

        self.program_exit_event.set()
        if self.capture_thread and self.capture_thread.is_alive(): self.capture_thread.join()
        if self.processing_thread and self.processing_thread.is_alive(): self.processing_thread.join()
        self.program_exit_event.clear()

        if self.camera:
            self.camera.release()
            self.camera = None
        if self.active_frame_source:
             self.active_frame_source.release()
        self.active_frame_source = None

        self.project_manager = ProjectManager()
        self._create_welcome_frame()

    # --- UI Command Methods ---
    def _define_groups(self):
        group_count = simpledialog.askinteger("Number of Groups", "Enter the total number of groups:")
        if group_count is not None:
            group_names = []
            for i in range(group_count):
                name = simpledialog.askstring("Group Name", f"Enter name for group {i + 1}:")
                if name: group_names.append(name)
            self.project_manager.project_data["groups"] = group_names
            self.project_manager.save_project()
            messagebox.showinfo("Success", "Group names have been updated.")

    def _start_recording(self):
        if not self.project_manager.project_data.get("groups"):
            messagebox.showwarning("Setup Required", "Please define groups for this project first.")
            return

        selection_window = Toplevel(self.root)
        selection_window.title("Select Group")
        group_names = self.project_manager.project_data["groups"]
        group_var = StringVar(value=group_names[0])
        Label(selection_window, text="Select Group:").pack(padx=10, pady=5)
        OptionMenu(selection_window, group_var, *group_names).pack(padx=10, pady=5)

        def on_confirm():
            cobaia_number = simpledialog.askstring("Cobaia Number", "Enter the cobaia number:")
            if not cobaia_number: return
            selection_window.destroy()

            group_name = group_var.get()
            output_folder = os.path.join(self.project_manager.project_path, f"{group_name}_{cobaia_number}")

            cam_props = self.camera.get_properties()
            success = self.recorder.start_recording(output_folder, cam_props['width'], cam_props['height'])

            if success:
                with self.frame_queue.mutex: self.frame_queue.queue.clear()
                with self.video_queue.mutex: self.video_queue.queue.clear()
                self.is_recording = True
                self.is_capturing_for_video = True
                self.video_stop_event.clear()
                self.video_thread = threading.Thread(target=self._video_recording_loop, daemon=True)
                self.video_thread.start()
                self.start_rec_btn.config(state="disabled")
                self.stop_rec_btn.config(state="normal")
                self.status_var.set(f"Recording to: {os.path.basename(output_folder)}")
            else:
                messagebox.showerror("Error", "Failed to start recorder.")

        Button(selection_window, text="Confirm", command=on_confirm).pack(pady=10)

    def _stop_recording(self):
        self.is_recording = False
        self.is_capturing_for_video = False
        self.video_stop_event.set()
        if hasattr(self, 'video_thread') and self.video_thread.is_alive():
            self.video_thread.join(timeout=5)
        self.recorder.stop_recording()
        self.start_rec_btn.config(state="normal")
        self.stop_rec_btn.config(state="disabled")
        self.status_var.set(f"Project: {self.project_manager.get_project_name()} (live) - Ready")
        messagebox.showinfo("Success", "Recording stopped and files saved.")

    def _process_next_video(self):
        if self.is_recording:
            messagebox.showwarning("Busy", "A video is already being processed.")
            return

        video_path = self.project_manager.get_next_video()
        if not video_path:
            messagebox.showinfo("Project Complete", "All videos in this project have been processed.")
            return

        if not self.project_manager.project_data.get("groups"):
            messagebox.showwarning("Setup Required", "Please define groups for this project first.")
            return

        selection_window = Toplevel(self.root)
        selection_window.title("Select Group for this Run")
        group_names = self.project_manager.project_data["groups"]
        group_var = StringVar(value=group_names[0])
        Label(selection_window, text="Select Group:").pack(padx=10, pady=5)
        OptionMenu(selection_window, group_var, *group_names).pack(padx=10, pady=5)

        def on_confirm():
            cobaia_number = simpledialog.askstring("Cobaia Number", "Enter the cobaia number for this run:")
            if not cobaia_number: return
            selection_window.destroy()

            try:
                self.active_frame_source = VideoFileSource(video_path)
            except (IOError, FileNotFoundError) as e:
                messagebox.showerror("Error", f"Could not open video file: {e}")
                return

            self.currently_processing_video = video_path
            video_props = self.active_frame_source.get_properties()
            video_basename = os.path.splitext(os.path.basename(video_path))[0]

            group_name = group_var.get()
            output_folder_name = f"{video_basename}_{group_name}_{cobaia_number}"
            output_path = os.path.join(self.project_manager.project_path, output_folder_name)

            success = self.recorder.start_recording(output_path, video_props['width'], video_props['height'])

            if success:
                self.project_manager.update_video_status(video_path, "processing")
                with self.frame_queue.mutex: self.frame_queue.queue.clear()
                with self.video_queue.mutex: self.video_queue.queue.clear()
                self.is_recording = True
                self.is_capturing_for_video = True # Save video output as well
                self.video_stop_event.clear()
                self.video_thread = threading.Thread(target=self._video_recording_loop, daemon=True)
                self.video_thread.start()
                self.process_video_btn.config(state="disabled")
                self.status_var.set(f"Processing: {os.path.basename(video_path)}")
            else:
                messagebox.showerror("Error", "Failed to start recorder for video processing.")
                self.active_frame_source.release()
                self.active_frame_source = None

        Button(selection_window, text="Confirm", command=on_confirm).pack(pady=10)

    def _handle_source_finished(self):
        """Called from the capture thread when a video file ends."""
        if not self.is_recording:
            return

        print(f"Source finished: {os.path.basename(self.currently_processing_video)}")
        self.is_recording = False
        self.is_capturing_for_video = False
        self.video_stop_event.set()
        if hasattr(self, 'video_thread') and self.video_thread.is_alive():
            self.video_thread.join(timeout=5)

        self.recorder.stop_recording()
        self.project_manager.update_video_status(self.currently_processing_video, "complete")

        self.currently_processing_video = None
        self.process_video_btn.config(state="normal")
        self.status_var.set(f"Project: {self.project_manager.get_project_name()} (pre-recorded) - Ready for next video.")
        messagebox.showinfo("Processing Complete", "Finished processing video.")

    def _on_close(self):
        if messagebox.askokcancel("Quit", "Do you want to exit the program?"):
            if self.is_recording:
                if self.project_manager.get_project_type() == 'live':
                    self._stop_recording()
                else:
                    self._handle_source_finished()

            self.program_exit_event.set()
            if hasattr(self, 'capture_thread') and self.capture_thread.is_alive(): self.capture_thread.join()
            if hasattr(self, 'processing_thread') and self.processing_thread.is_alive(): self.processing_thread.join()

            if self.camera: self.camera.release()
            if self.active_frame_source and not isinstance(self.active_frame_source, Camera):
                self.active_frame_source.release()
            self.arduino.close()
            self.root.destroy()

if __name__ == '__main__':
    print("This file is intended to be imported, not run directly.")
    print("Run main.py to start the application.")
