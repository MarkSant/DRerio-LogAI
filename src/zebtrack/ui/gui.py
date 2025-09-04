"""
Este módulo define a interface gráfica principal (GUI) para a aplicação Zebtrack.
"""

import os
import queue
import threading
import time
from tkinter import (
    BooleanVar,
    Button,
    Checkbutton,
    Entry,
    Frame,
    Label,
    OptionMenu,
    StringVar,
    Toplevel,
    filedialog,
    messagebox,
    simpledialog,
    ttk,
)

import cv2
import structlog

# Import custom modules
from zebtrack.core.detector import Detector, draw_overlay
from zebtrack.io.camera import Camera
from zebtrack.io.video_source import VideoFileSource
from zebtrack.plugins import DETECTOR_PLUGINS
from zebtrack.settings import settings

log = structlog.get_logger()


class ApplicationGUI:
    """
    A classe principal que gerencia a interface gráfica (a "Visão").
    """

    def __init__(self, root, controller):
        """
        Inicializa a ApplicationGUI.
        """
        self.root = root
        self.controller = controller
        self.root.title("Zebtrack Controller")
        self.root.protocol("WM_DELETE_WINDOW", self.controller.on_close)

        # Dynamic widgets / state variables
        self.welcome_frame = None
        self.main_controls_frame = None
        self.status_var = StringVar()
        # Progress + stats (created later)
        self.progress_frame: Frame | None = None
        self.progress_bar = None
        self.progress_labels: dict[str, StringVar] = {}
        self.video_label: Label | None = None

        # User options
        self.processing_interval_var = StringVar(
            value=str(settings.video_processing.processing_interval)
        )
        self.show_preview_var = BooleanVar(value=True)
        self.use_openvino_var = BooleanVar(value=True)

        self._create_welcome_frame()

    def _create_welcome_frame(self):
        """Creates the initial UI for project selection."""
        if self.main_controls_frame:
            self.main_controls_frame.destroy()

        self.root.geometry("400x150")
        self.welcome_frame = Frame(self.root)
        self.welcome_frame.pack(expand=True)

        Label(
            self.welcome_frame,
            text="Welcome to Zebtrack Controller",
            font=("Helvetica", 16),
        ).pack(pady=10)

        btn_frame = Frame(self.welcome_frame)
        btn_frame.pack(pady=10)

        Button(
            btn_frame, text="Create New Project", command=self._create_project_workflow
        ).pack(side="left", padx=10)
        Button(
            btn_frame, text="Open Existing Project", command=self._open_project_workflow
        ).pack(side="left", padx=10)

    def _create_main_control_frame(self):
        """Creates the main UI for controlling the app after a project is loaded."""
        if self.welcome_frame:
            self.welcome_frame.destroy()

        self.root.geometry("")
        self.main_controls_frame = Frame(self.root)
        self.main_controls_frame.pack(padx=10, pady=10)

        project_type = self.controller.project_manager.get_project_type()

        if project_type == "live":
            Button(
                self.main_controls_frame,
                text="Define Groups",
                command=self._define_groups,
            ).pack(side="left", padx=5)
            self.start_rec_btn = Button(
                self.main_controls_frame,
                text="Start Recording",
                command=self.controller.start_recording,
            )
            self.start_rec_btn.pack(side="left", padx=5)
            self.stop_rec_btn = Button(
                self.main_controls_frame,
                text="Stop Recording",
                command=self.controller.stop_recording,
                state="disabled",
            )
            self.stop_rec_btn.pack(side="left", padx=5)
        elif project_type == "pre-recorded":
            prerecorded_controls_frame = Frame(self.main_controls_frame)
            prerecorded_controls_frame.pack(side="left")

            button_frame = Frame(prerecorded_controls_frame)
            button_frame.pack(fill="x", padx=5, pady=2)
            Button(
                button_frame, text="Define Groups", command=self._define_groups
            ).pack(side="left")
            self.process_video_btn = Button(
                button_frame,
                text="Process Next Video",
                command=self.controller.process_next_video,
            )
            self.process_video_btn.pack(side="left", padx=5)
            self.cancel_proc_btn = Button(
                button_frame,
                text="Cancel",
                state="disabled",
                command=self.controller.cancel_processing,
            )
            self.cancel_proc_btn.pack(side="left", padx=5)

            options_frame = Frame(prerecorded_controls_frame)
            options_frame.pack(fill="x", padx=5, pady=2)
            Label(options_frame, text="Frame Interval:").pack(side="left")
            Entry(
                options_frame, textvariable=self.processing_interval_var, width=5
            ).pack(side="left")
            Checkbutton(
                options_frame, text="Show Preview", variable=self.show_preview_var
            ).pack(side="left", padx=10)

        Button(
            self.main_controls_frame,
            text="Close Project",
            command=self.controller.close_project,
        ).pack(side="left", padx=5)

        status_text = (
            f"Project: {self.controller.project_manager.get_project_name()} "
            f"({project_type})"
        )
        self.status_var.set(status_text)

        status_frame = Frame(self.root)
        status_frame.pack(pady=5, fill="x", padx=10)
        Label(status_frame, textvariable=self.status_var).pack()

        # Progress + video frame (hidden until needed)
        self._build_progress_frame()

    def _build_progress_frame(self):
        if self.progress_frame:
            self.progress_frame.destroy()
        self.progress_frame = Frame(self.root)
        # Video preview area (placed above bar as requested: bar below video)
        self.video_label = Label(self.progress_frame)
        self.video_label.pack(pady=3)
        self.progress_bar = ttk.Progressbar(
            self.progress_frame, orient="horizontal", length=400, mode="determinate"
        )
        self.progress_bar.pack(pady=3, fill="x")
        stats_container = Frame(self.progress_frame)
        stats_container.pack(fill="x")
        for key, label_text in [
            ("total", "Total Frames:"),
            ("processed", "Processed:"),
            ("detected", "Detected Frames:"),
            ("percent", "Completed:"),
            ("elapsed", "Elapsed:"),
            ("eta", "ETA:"),
        ]:
            f = Frame(stats_container)
            f.pack(side="left", padx=5)
            Label(f, text=label_text).pack(anchor="w")
            var = StringVar(value="-")
            Label(f, textvariable=var).pack(anchor="w")
            self.progress_labels[key] = var
        self.progress_frame.pack_forget()

    def _load_project_view(self):
        """
        Transitions from the welcome screen to the main control view and
        initializes the detector with the appropriate plugin.
        """
        pm = self.controller.project_manager
        use_openvino = pm.project_data.get("use_openvino", False)

        # Load persisted user preferences if present
        if pm.get_project_type() == "pre-recorded":
            if pm.project_data.get("last_processing_interval") is not None:
                try:
                    self.processing_interval_var.set(
                        str(int(pm.project_data["last_processing_interval"]))
                    )
                except (ValueError, TypeError):
                    pass
            if pm.project_data.get("last_show_preview") is not None:
                try:
                    self.show_preview_var.set(
                        bool(pm.project_data["last_show_preview"])  # type: ignore[arg-type]
                    )
                except Exception:  # noqa: BLE001
                    pass

        try:
            if use_openvino:
                plugin_name = "OpenVINO"
                model_path = pm.project_data.get("openvino_model_path")
                if not model_path or not os.path.exists(model_path):
                    raise ValueError("OpenVINO model path not found or invalid.")
            else:
                plugin_name = "YOLO (Ultralytics)"
                model_path = settings.yolo_model.path

            plugin_class = DETECTOR_PLUGINS.get(plugin_name)
            if not plugin_class:
                raise ValueError(f"Detector plugin '{plugin_name}' not found.")

            plugin_instance = plugin_class(model_path=model_path)
            self.controller.detector = Detector(plugin=plugin_instance)

        except (ValueError, FileNotFoundError) as e:
            log.error("detector.init.failed", error=str(e), exc_info=True)
            self.show_error(
                "Detector Error", f"Failed to initialize the detector: {e}"
            )
            self._create_welcome_frame()
            return

        self._create_main_control_frame()

        project_type = pm.get_project_type()
        if project_type == "live":
            if not self.controller.arduino.connect():
                self.show_warning(
                    "Arduino Warning",
                    "Could not connect to Arduino. Running in offline mode.",
                )
            try:
                self.controller.camera = Camera()
                self.controller.active_frame_source = self.controller.camera
                self.controller.detector.update_scaling(
                    self.controller.camera.actual_width,
                    self.controller.camera.actual_height,
                )
            except IOError as e:
                self.show_error("Camera Error", str(e))
                self._create_welcome_frame()
                return
        elif project_type == "pre-recorded":
            next_video = pm.get_next_video()
            if next_video is None:
                self.process_video_btn.config(state="disabled")
                self.set_status(
                    f"Project: {pm.get_project_name()} - All videos processed."
                )
            else:
                video_name = os.path.basename(next_video)
                self.set_status(
                    f"Project: {pm.get_project_name()} - Ready to process: {video_name}"
                )

        if project_type == "live":
            self.controller.capture_thread = threading.Thread(
                target=self._live_frame_capture_loop, name="CaptureThread", daemon=True
            )
            self.controller.processing_thread = threading.Thread(
                target=self._live_processing_loop, name="ProcessingThread", daemon=True
            )
            self.controller.capture_thread.start()
            self.controller.processing_thread.start()

    def _live_frame_capture_loop(self):
        """
        Loop para capturar quadros de uma fonte AO VIVO (câmera).
        """
        live_frame_count = 0
        while not self.controller.program_exit_event.is_set():
            if not self.controller.active_frame_source:
                time.sleep(0.1)
                continue

            ret, frame = self.controller.active_frame_source.get_frame()
            if not ret:
                log.error("gui.capture_thread.get_frame_failed")
                time.sleep(0.5)
                continue

            live_frame_count += 1

            if not self.controller.frame_queue.full():
                self.controller.frame_queue.put((live_frame_count, frame.copy()))
            if (
                self.controller.is_capturing_for_video
                and not self.controller.video_queue.full()
            ):
                self.controller.video_queue.put(frame.copy())

            time.sleep(1 / (settings.video_processing.fps * 1.5))

    def _live_processing_loop(self):
        """
        Loop para processar quadros de uma fonte AO VIVO.
        """
        while not self.controller.program_exit_event.is_set():
            try:
                frame_number, frame = self.controller.frame_queue.get(timeout=1)
            except queue.Empty:
                continue

            if self.controller.is_processing:
                detections, command = self.controller.detector.process_frame(
                    frame, "live"
                )
                if command is not None:
                    self.controller.arduino.send_command(command)
                if self.controller.is_recording and detections:
                    timestamp = time.time() - self.controller.recorder.start_time
                    self.controller.recorder.write_detection_data(
                        timestamp, frame_number, detections
                    )
                draw_overlay(frame, detections, self.controller.detector)

            cv2.imshow("Live View", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                self.controller.on_close()
                break
        cv2.destroyAllWindows()
        log.info("gui.live_processing_loop.finished")

    def _file_processing_loop(self):
        """
        Loop para processar um ARQUIVO de vídeo de forma eficiente.
        """
        if not self.controller.is_recording or not isinstance(
            self.controller.active_frame_source, VideoFileSource
        ):
            log.error("gui.file_processing_loop.invalid_state")
            return

        show_preview = self.show_preview_var.get()
        try:
            processing_interval = int(self.processing_interval_var.get())
        except ValueError:
            processing_interval = 1

        if processing_interval < 1:
            processing_interval = 1

        video_source = self.controller.active_frame_source
        total_frames = video_source.get_properties()["frame_count"]
        frame_number = -1

        while (
            not self.controller.program_exit_event.is_set()
            and frame_number < total_frames
        ):
            target_frame = (
                (
                    settings.video_processing.processing_offset
                    if settings.video_processing.processing_offset > 0
                    else 1
                )
                if frame_number < 0
                else frame_number + processing_interval
            )

            if target_frame >= total_frames:
                break

            video_source.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = video_source.get_frame()
            if not ret:
                break

            frame_number = target_frame
            log.info("gui.file_processing_loop.progress", frame=frame_number)

            if not show_preview and total_frames > 0:
                progress_percent = int((frame_number / total_frames) * 100)
                video_name = os.path.basename(
                    self.controller.currently_processing_video
                )
                status_msg = f"Processing: {video_name} ({progress_percent}%)"
                self.root.after(0, self.status_var.set, status_msg)

            detections, _ = self.controller.detector.process_frame(
                frame, "pre-recorded"
            )
            if detections:
                props = video_source.get_properties()
                timestamp = frame_number / props["fps"] if props["fps"] > 0 else 0
                self.controller.recorder.write_detection_data(
                    timestamp, frame_number, detections
                )

            if show_preview:
                draw_overlay(frame, detections, self.controller.detector)
                cv2.imshow("File Processing", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    self.controller.program_exit_event.set()

        if show_preview:
            cv2.destroyAllWindows()
        self.root.after(0, self._cleanup_after_processing)

    def _create_project_workflow(self):
        """
        Handles the UI part of creating a new project, then calls the controller.
        """
        base_path = self.ask_directory(title="Select a Parent Folder for the Project")
        if not base_path:
            return

        project_name = self.ask_string(
            "Project Name", "Enter a name for the new project:"
        )
        if not project_name:
            return

        project_path = os.path.join(base_path, project_name)
        if os.path.exists(project_path) and os.listdir(project_path):
            self.show_error(
                "Error",
                "A project folder with this name already exists and is not empty.",
            )
            return

        type_window = Toplevel(self.root)
        type_window.title("Project Type")
        type_var = StringVar()
        Label(type_window, text="Choose the project type:").pack(padx=20, pady=10)
        Checkbutton(
            type_window,
            text="Optimize with OpenVINO (for Intel GPUs)",
            variable=self.use_openvino_var,
        ).pack(padx=20, pady=5)
        Button(
            type_window,
            text="Live Analysis",
            command=lambda: [type_var.set("live"), type_window.destroy()],
        ).pack(fill="x", padx=20, pady=5)
        Button(
            type_window,
            text="Pre-recorded Analysis",
            command=lambda: [type_var.set("pre-recorded"), type_window.destroy()],
        ).pack(fill="x", padx=20, pady=5)
        self.root.wait_window(type_window)
        project_type = type_var.get()

        if not project_type:
            return

        video_files = []
        if project_type == "pre-recorded":
            video_files = self.ask_open_filenames(
                title="Select Video Files",
                filetypes=[("Video files", "*.mp4 *.avi")],
            )
            if not video_files:
                return

        use_openvino = self.use_openvino_var.get()

        self.controller.create_project_workflow(
            project_path, project_type, use_openvino, video_files
        )

    def _open_project_workflow(self):
        """Handles the UI part of opening a project, then calls the controller."""
        project_path = self.ask_directory(title="Select an Existing Project Folder")
        if not project_path:
            return

        self.controller.open_project_workflow(project_path)

    def _define_groups(self):
        """Permite que o usuário defina nomes para os grupos de tratamento."""
        group_count = self.ask_string(
            "Number of Groups", "Enter the total number of groups:"
        )
        if group_count is not None:
            try:
                num_groups = int(group_count)
                group_names = []
                for i in range(num_groups):
                    name = self.ask_string(
                        "Group Name", f"Enter name for group {i + 1}:"
                    )
                    if name:
                        group_names.append(name)
                self.controller.project_manager.project_data["groups"] = group_names
                self.controller.project_manager.save_project()
                self.show_info("Success", "Group names have been updated.")
            except (ValueError, TypeError):
                self.show_error(
                    "Invalid Input", "Please enter a valid number for the group count."
                )

    def _on_close(self):
        """Delegates the close action to the controller."""
        self.controller.on_close()

    def _join_threads(self):
        """Delegates thread joining to the controller."""
        self.controller.join_threads()

    def set_status(self, text):
        """Updates the UI status bar."""
        self.status_var.set(text)

    def update_progress(self, value):
        """Updates the progress bar."""
        if self.progress_bar:
            if not self.progress_frame.winfo_viewable():
                self.progress_frame.pack(pady=5, fill="x", padx=10)
            self.progress_bar["value"] = value
            self.root.update_idletasks()

    def update_progress_stats(
        self,
        *,
        total=None,
        processed=None,
        detected=None,
        percent=None,
        elapsed=None,
        eta=None,
    ):
        """Update textual statistics for file processing."""
        if not self.progress_labels:
            return
        if total is not None:
            self.progress_labels["total"].set(str(total))
        if processed is not None:
            self.progress_labels["processed"].set(str(processed))
        if detected is not None:
            self.progress_labels["detected"].set(str(detected))
        if percent is not None:
            self.progress_labels["percent"].set(f"{percent:.1f}%")
        if elapsed is not None:
            self.progress_labels["elapsed"].set(self._format_time(elapsed))
        if eta is not None:
            self.progress_labels["eta"].set(self._format_time(eta) if eta >= 0 else "-")

    def hide_progress_bar(self):
        """Hides the progress bar."""
        if self.progress_frame and self.progress_frame.winfo_viewable():
            self.progress_frame.pack_forget()

    def display_frame(self, frame):
        """Display a video frame inside the GUI (used for preview)."""
        try:
            import cv2
            try:
                from PIL import Image, ImageTk  # type: ignore
                # Convert and embed
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame_rgb)
                imgtk = ImageTk.PhotoImage(image=img)
                if self.video_label:
                    self.video_label.configure(image=imgtk)
                    self.video_label.image = imgtk  # keep reference
            except ImportError:
                # Fallback to OpenCV window if Pillow not installed
                cv2.imshow("Preview", frame)
                cv2.waitKey(1)
        except Exception:
            pass

    @staticmethod
    def _format_time(seconds: float) -> str:
        if seconds is None or seconds < 0:
            return "-"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:d}h {m:02d}m {s:02d}s"
        if m:
            return f"{m:d}m {s:02d}s"
        return f"{s:d}s"

    def show_error(self, title, message):
        """Shows an error message box."""
        messagebox.showerror(title, message)

    def show_warning(self, title, message):
        """Shows a warning message box."""
        messagebox.showwarning(title, message)

    def show_info(self, title, message):
        """Shows an info message box."""
        messagebox.showinfo(title, message)

    def ask_ok_cancel(self, title, message):
        """Shows a confirmation dialog."""
        return messagebox.askokcancel(title, message)

    def ask_string(self, title, prompt):
        """Shows a dialog for string input."""
        return simpledialog.askstring(title, prompt)

    def ask_directory(self, title):
        """Shows a dialog to select a directory."""
        return filedialog.askdirectory(title=title)

    def ask_open_filenames(self, title, filetypes):
        """Shows a dialog to select one or more files."""
        return filedialog.askopenfilenames(title=title, filetypes=filetypes)

    def update_button_state(self, button_name, state):
        """Updates the state of a button ('normal' or 'disabled')."""
        if button_name == "start_rec" and hasattr(self, 'start_rec_btn'):
            self.start_rec_btn.config(state=state)
        elif button_name == "stop_rec" and hasattr(self, 'stop_rec_btn'):
            self.stop_rec_btn.config(state=state)
        elif button_name == "process_video" and hasattr(self, 'process_video_btn'):
            self.process_video_btn.config(state=state)
        elif button_name == "cancel_processing" and hasattr(self, 'cancel_proc_btn'):
            self.cancel_proc_btn.config(state=state)

    def ask_recording_details(self, group_names):
        """Shows a dialog to get group and cobaia number from the user."""
        selection_window = Toplevel(self.root)
        selection_window.title("Select Group")
        group_var = StringVar(value=group_names[0])
        Label(selection_window, text="Select Group:").pack(padx=10, pady=5)
        OptionMenu(selection_window, group_var, *group_names).pack(padx=10, pady=5)

        result = {}

        def on_confirm():
            cobaia_number = self.ask_string("Cobaia Number", "Enter the cobaia number:")
            if not cobaia_number:
                result["group"] = None
                result["cobaia"] = None
            else:
                result["group"] = group_var.get()
                result["cobaia"] = cobaia_number
            selection_window.destroy()

        Button(selection_window, text="Confirm", command=on_confirm).pack(pady=10)
        self.root.wait_window(selection_window)

        if result.get("cobaia"):
            return result["group"], result["cobaia"]
        return None


if __name__ == "__main__":
    # Using print is fine here as it's for direct execution feedback
    print("This file is intended to be imported, not run directly.")
    print("Run the main application script to start Zebtrack.")
