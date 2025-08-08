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

class ApplicationGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Zebtrack Controller")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # --- Initialize Modules ---
        try:
            self.camera = Camera()
        except IOError as e:
            messagebox.showerror("Camera Error", str(e))
            self.root.destroy()
            return

        self.arduino = Arduino()
        self.detector = Detector()
        self.recorder = Recorder()

        # --- State Variables ---
        self.project_folder_path = ""
        self.group_names = []
        self.is_processing = True
        self.is_capturing_for_video = False
        self.is_recording = False

        # --- Threading and Queues ---
        self.program_exit_event = threading.Event()
        self.video_stop_event = threading.Event()

        self.frame_queue = queue.Queue(maxsize=10) # For live processing and display
        self.video_queue = queue.Queue(maxsize=300) # For recording

        # --- UI Elements ---
        self._create_widgets()

        # --- Start Core Threads ---
        self.capture_thread = threading.Thread(target=self._frame_capture_loop, daemon=True)
        self.processing_thread = threading.Thread(target=self._object_detection_loop, daemon=True)

        self.capture_thread.start()
        self.processing_thread.start()

    def _create_widgets(self):
        frame = Frame(self.root)
        frame.pack(padx=10, pady=10)

        Button(frame, text="Create Project", command=self._create_project).pack(side="left", padx=5)
        self.start_rec_btn = Button(frame, text="Start Recording", command=self._start_recording)
        self.start_rec_btn.pack(side="left", padx=5)
        self.stop_rec_btn = Button(frame, text="Stop Recording", command=self._stop_recording, state="disabled")
        self.stop_rec_btn.pack(side="left", padx=5)
        Button(frame, text="End Project", command=self._end_project).pack(side="left", padx=5)
        Button(frame, text="Exit Program", command=self._on_close).pack(side="left", padx=5)

        self.status_var = StringVar(value="Status: Ready")
        Label(self.root, textvariable=self.status_var).pack(pady=5)

    # --- Core Application Loops (run in threads) ---

    def _frame_capture_loop(self):
        frame_count = 0
        while not self.program_exit_event.is_set():
            ret, frame = self.camera.get_frame()
            if not ret:
                print("Capture thread: failed to get frame.")
                time.sleep(0.1)
                continue

            frame_count += 1

            # Put frame in queue for processing/display
            if not self.frame_queue.full():
                self.frame_queue.put((frame_count, frame.copy()))

            # Put frame in queue for video recording if active
            if self.is_capturing_for_video and not self.video_queue.full():
                self.video_queue.put(frame.copy())

            time.sleep(1 / (config.FPS * 1.5)) # Sleep to not overwhelm queues

    def _object_detection_loop(self):
        while not self.program_exit_event.is_set():
            try:
                frame_count, frame = self.frame_queue.get(timeout=1)
            except queue.Empty:
                continue

            if self.is_processing:
                # Process every Nth frame to save resources
                if (frame_count - config.PROCESSING_OFFSET) % config.PROCESSING_INTERVAL == 0:
                    detections, command = self.detector.process_frame(frame)

                    if command is not None:
                        self.arduino.send_command(command)

                    if self.is_recording:
                        self.recorder.write_detection_data(frame_count, detections)
                else:
                    detections = [] # No detection on this frame

                # Draw overlays for display
                draw_overlay(frame, detections)

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

    # --- UI Command Methods ---

    def _create_project(self):
        selected_folder = filedialog.askdirectory(title="Select a folder to create the project in")
        if not selected_folder: return

        new_folder_name = simpledialog.askstring("Project Name", "Enter a name for the new project folder:")
        if not new_folder_name: return

        self.project_folder_path = os.path.join(selected_folder, new_folder_name)
        try:
            os.makedirs(self.project_folder_path, exist_ok=True)
            messagebox.showinfo("Success", f"Project '{new_folder_name}' created at:\n{self.project_folder_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not create project folder: {e}")
            return

        group_count = simpledialog.askinteger("Number of Groups", "Enter the number of groups:")
        if group_count:
            self.group_names = []
            for i in range(group_count):
                name = simpledialog.askstring("Group Name", f"Enter name for group {i+1}:")
                if name: self.group_names.append(name)
            self.status_var.set(f"Project '{new_folder_name}' created. Ready to record.")

    def _start_recording(self):
        if not self.project_folder_path or not self.group_names:
            messagebox.showwarning("Setup Required", "Please create a project and define groups first.")
            return

        # --- Group and Cobaia Selection Window ---
        selection_window = Toplevel(self.root)
        selection_window.title("Select Group")

        group_var = StringVar(value=self.group_names[0])
        Label(selection_window, text="Select Group:").pack(padx=10, pady=5)
        OptionMenu(selection_window, group_var, *self.group_names).pack(padx=10, pady=5)

        def on_confirm():
            cobaia_number = simpledialog.askstring("Cobaia Number", "Enter the cobaia number:")
            if not cobaia_number: return

            selection_window.destroy()

            # --- Start the recording process ---
            group_name = group_var.get()
            output_folder = os.path.join(self.project_folder_path, f"{group_name}_{cobaia_number}")

            cam_props = self.camera.get_properties()
            success = self.recorder.start_recording(output_folder, cam_props['width'], cam_props['height'])

            if success:
                # Clear queues
                with self.frame_queue.mutex: self.frame_queue.queue.clear()
                with self.video_queue.mutex: self.video_queue.queue.clear()

                # Set flags
                self.is_recording = True
                self.is_capturing_for_video = True

                # Start video thread
                self.video_stop_event.clear()
                self.video_thread = threading.Thread(target=self._video_recording_loop, daemon=True)
                self.video_thread.start()

                # Update UI
                self.start_rec_btn.config(state="disabled")
                self.stop_rec_btn.config(state="normal")
                self.status_var.set(f"Recording to: {os.path.basename(output_folder)}")
            else:
                messagebox.showerror("Error", "Failed to start recorder. Check console for details.")

        Button(selection_window, text="Confirm", command=on_confirm).pack(pady=10)

    def _stop_recording(self):
        self.is_recording = False
        self.is_capturing_for_video = False

        self.video_stop_event.set()
        if self.video_thread.is_alive():
            self.video_thread.join(timeout=5) # Wait for thread to finish

        self.recorder.stop_recording()

        self.start_rec_btn.config(state="normal")
        self.stop_rec_btn.config(state="disabled")
        self.status_var.set("Recording stopped. Ready.")
        messagebox.showinfo("Success", "Recording stopped and files saved.")

    def _end_project(self):
        if self.is_recording:
            self._stop_recording()

        self.project_folder_path = ""
        self.group_names = []
        self.status_var.set("Project ended. Create a new project to begin.")
        messagebox.showinfo("Project Ended", "Project settings have been reset.")

    def _on_close(self):
        if messagebox.askokcancel("Quit", "Do you want to exit the program?"):
            if self.is_recording:
                self._stop_recording()

            self.program_exit_event.set()

            # Wait for threads to finish
            if self.capture_thread.is_alive(): self.capture_thread.join()
            if self.processing_thread.is_alive(): self.processing_thread.join()

            # Release resources
            self.camera.release()
            self.arduino.close()

            self.root.destroy()

if __name__ == '__main__':
    # This block will not be executed when imported by main.py
    # It's here for potential standalone testing of the GUI.
    print("This file is intended to be imported, not run directly.")
    print("Run main.py to start the application.")
