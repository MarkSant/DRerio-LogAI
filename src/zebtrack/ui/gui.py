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
    Canvas,
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
import numpy as np
import serial.tools.list_ports
import structlog
from PIL import Image, ImageTk

# Import custom modules
from zebtrack.io.camera import Camera
from zebtrack.io.video_source import VideoFileSource
from zebtrack.settings import settings

log = structlog.get_logger()


class ManageWeightsDialog(simpledialog.Dialog):
    """Dialog to manage the available weights."""

    def __init__(self, parent, controller):
        self.controller = controller
        super().__init__(parent, "Manage Detection Weights")

    def body(self, master):
        self.listbox = ttk.Treeview(
            master, columns=("name", "is_default"), show="headings", height=5
        )
        self.listbox.heading("name", text="Weight Name")
        self.listbox.heading("is_default", text="Default")
        self.listbox.column("is_default", width=60, anchor="center")
        self.listbox.pack(padx=5, pady=5, fill="both", expand=True)

        self.populate_list()

        button_frame = ttk.Frame(master)
        button_frame.pack(pady=5)

        ttk.Button(button_frame, text="Set as Default", command=self.set_default).pack(
            side="left", padx=5
        )
        ttk.Button(button_frame, text="Delete Selected", command=self.delete).pack(
            side="left", padx=5
        )

    def populate_list(self):
        for item in self.listbox.get_children():
            self.listbox.delete(item)

        weights = self.controller.get_all_weight_names()
        default_name, _ = self.controller.weight_manager.get_default_weight()

        for name in sorted(weights):
            is_default_str = "Yes" if name == default_name else ""
            self.listbox.insert("", "end", values=(name, is_default_str))

    def get_selected_item_name(self):
        selected = self.listbox.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a weight first.")
            return None
        return self.listbox.item(selected[0])["values"][0]

    def set_default(self):
        name = self.get_selected_item_name()
        if name:
            self.controller.weight_manager.set_default_weight(name)
            self.populate_list()
            # Also update the main GUI dropdown
            self.master.master.set_active_weight_in_dropdown(name)

    def delete(self):
        name = self.get_selected_item_name()
        if name:
            if messagebox.askyesno(
                "Confirm Deletion", f"Are you sure you want to delete '{name}'?"
            ):
                self.controller.delete_weight(name)
                self.populate_list()

    def buttonbox(self):
        # Override to have only a close button
        box = ttk.Frame(self)
        w = ttk.Button(box, text="Close", width=10, command=self.ok, default="active")
        w.pack(side="left", padx=5, pady=5)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack()


class CreateProjectDialog(simpledialog.Dialog):
    """A custom dialog to gather all new project information."""

    def __init__(self, parent):
        self.project_path = None
        self.result = None
        super().__init__(parent, "Create New Project")

    def body(self, master):
        self.project_name_var = StringVar()
        self.num_aquariums_var = StringVar(value="1")
        self.aquarium_width_var = StringVar(value="10.0")
        self.aquarium_height_var = StringVar(value="10.0")
        self.project_type_var = StringVar(value="pre-recorded")
        self.video_files = []
        self.video_list_var = StringVar(value="No videos selected.")
        self.use_timed_recording_var = BooleanVar(value=False)
        self.recording_duration_var = StringVar(value="5")

        # --- Project Name ---
        Label(master, text="Project Name:").grid(
            row=0, column=0, sticky="w", padx=5, pady=2
        )
        Entry(master, textvariable=self.project_name_var, width=40).grid(
            row=0, column=1, columnspan=2, sticky="ew", padx=5
        )

        # --- Base Path ---
        Label(master, text="Project Folder:").grid(
            row=1, column=0, sticky="w", padx=5, pady=2
        )
        self.path_entry = Entry(master, text="", width=40)
        self.path_entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=5)
        Button(master, text="Browse...", command=self._select_path).grid(
            row=1, column=3, padx=5
        )

        # --- Calibration ---
        Label(master, text="Number of Aquariums:").grid(
            row=2, column=0, sticky="w", padx=5, pady=2
        )
        Entry(master, textvariable=self.num_aquariums_var, width=10).grid(
            row=2, column=1, sticky="w", padx=5
        )

        Label(master, text="Aquarium Width (cm):").grid(
            row=3, column=0, sticky="w", padx=5, pady=2
        )
        Entry(master, textvariable=self.aquarium_width_var, width=10).grid(
            row=3, column=1, sticky="w", padx=5
        )

        Label(master, text="Aquarium Height (cm):").grid(
            row=4, column=0, sticky="w", padx=5, pady=2
        )
        Entry(master, textvariable=self.aquarium_height_var, width=10).grid(
            row=4, column=1, sticky="w", padx=5
        )

        # --- Project Type & Videos ---
        Label(master, text="Project Type:").grid(
            row=5, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Radiobutton(
            master,
            text="Pre-recorded",
            variable=self.project_type_var,
            value="pre-recorded",
            command=self._toggle_video_button,
        ).grid(row=5, column=1, sticky="w", padx=5)
        ttk.Radiobutton(
            master,
            text="Live",
            variable=self.project_type_var,
            value="live",
            command=self._toggle_video_button,
        ).grid(row=5, column=2, sticky="w", padx=5)

        self.video_button = Button(
            master, text="Select Videos...", command=self._select_videos
        )
        self.video_button.grid(row=6, column=0, padx=5, pady=5)
        Label(master, textvariable=self.video_list_var, wraplength=300).grid(
            row=6, column=1, columnspan=3, sticky="w", padx=5
        )

        # --- Live Recording Options ---
        self.live_options_frame = Frame(master)
        self.live_options_frame.grid(
            row=7, column=0, columnspan=4, sticky="ew", padx=5
        )
        Checkbutton(
            self.live_options_frame,
            text="Use timed recording?",
            variable=self.use_timed_recording_var,
            command=self._update_project_type_options,
        ).pack(side="left")
        self.duration_entry = Entry(
            self.live_options_frame, textvariable=self.recording_duration_var, width=5
        )
        self.duration_entry.pack(side="left", padx=5)
        Label(self.live_options_frame, text="minutes").pack(side="left")

        self._update_project_type_options()  # Set initial state
        return self.path_entry  # initial focus

    def _select_path(self):
        path = filedialog.askdirectory(title="Select a Parent Folder for the Project")
        if path:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, path)

    def _select_videos(self):
        files = filedialog.askopenfilenames(
            title="Select Video Files", filetypes=[("Video files", "*.mp4 *.avi")]
        )
        if files:
            self.video_files = files
            self.video_list_var.set(f"{len(files)} video(s) selected.")
        else:
            self.video_files = []
            self.video_list_var.set("No videos selected.")

    def _update_project_type_options(self):
        """Shows/hides options based on the selected project type."""
        if self.project_type_var.get() == "pre-recorded":
            self.video_button.config(state="normal")
            self.live_options_frame.grid_remove()
        else:  # Live
            self.video_button.config(state="disabled")
            self.video_list_var.set("Not applicable for live projects.")
            self.live_options_frame.grid()
            if self.use_timed_recording_var.get():
                self.duration_entry.config(state="normal")
            else:
                self.duration_entry.config(state="disabled")

    def validate(self):
        base_path = self.path_entry.get()
        if not base_path or not os.path.isdir(base_path):
            messagebox.showerror("Error", "Please select a valid parent folder.")
            return 0

        project_name = self.project_name_var.get()
        if not project_name.strip():
            messagebox.showerror("Error", "Project name cannot be empty.")
            return 0

        self.project_path = os.path.join(base_path, project_name)
        if os.path.exists(self.project_path) and os.listdir(self.project_path):
            messagebox.showerror(
                "Error",
                "A project folder with this name already exists and is not empty.",
            )
            return 0

        if self.project_type_var.get() == "pre-recorded" and not self.video_files:
            messagebox.showerror(
                "Error",
                "Please select at least one video file for pre-recorded analysis.",
            )
            return 0

        try:
            int(self.num_aquariums_var.get())
            float(self.aquarium_width_var.get())
            float(self.aquarium_height_var.get())
        except ValueError:
            messagebox.showerror("Error", "Aquarium dimensions must be valid numbers.")
            return 0

        if self.project_type_var.get() == "live":
            if self.use_timed_recording_var.get():
                try:
                    duration = float(self.recording_duration_var.get())
                    if duration <= 0:
                        raise ValueError("Duration must be positive.")
                except ValueError:
                    messagebox.showerror(
                        "Error", "Recording duration must be a positive number."
                    )
                    return 0
        return 1

    def apply(self):
        duration = 0
        if self.use_timed_recording_var.get():
            try:
                # Duration in minutes, convert to seconds for internal use
                duration = float(self.recording_duration_var.get()) * 60
            except ValueError:
                pass  # Should be caught by validate

        self.result = {
            "project_path": self.project_path,
            "project_type": self.project_type_var.get(),
            "video_files": self.video_files,
            "num_aquariums": int(self.num_aquariums_var.get()),
            "aquarium_width_cm": float(self.aquarium_width_var.get()),
            "aquarium_height_cm": float(self.aquarium_height_var.get()),
            "use_timed_recording": self.use_timed_recording_var.get(),
            "recording_duration_s": duration,
        }


class LiveConfigDialog(simpledialog.Dialog):
    """A dialog to configure live analysis settings (camera and Arduino)."""

    def __init__(self, parent):
        self.result = None
        self.available_cameras = {}
        self.available_ports = {}
        super().__init__(parent, "Live Analysis Configuration")

    def body(self, master):
        # --- Detect devices first ---
        self._detect_devices()

        # --- Tkinter Variables ---
        self.camera_var = StringVar()
        self.use_arduino_var = BooleanVar(value=True)
        self.arduino_port_var = StringVar()

        # --- Camera Selection ---
        Label(master, text="Select Camera:").grid(
            row=0, column=0, sticky="w", padx=5, pady=5
        )
        camera_names = list(self.available_cameras.keys())
        if not camera_names:
            camera_names = ["No cameras found"]
        self.camera_menu = OptionMenu(master, self.camera_var, *camera_names)
        self.camera_menu.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        if self.available_cameras:
            self.camera_var.set(list(self.available_cameras.keys())[0])
        else:
            self.camera_menu.config(state="disabled")

        # --- Arduino Selection ---
        self.arduino_check = Checkbutton(
            master,
            text="Use Arduino",
            variable=self.use_arduino_var,
            command=self._toggle_arduino_menu,
        )
        self.arduino_check.grid(
            row=1, column=0, columnspan=2, sticky="w", padx=5, pady=5
        )

        Label(master, text="Arduino Port:").grid(
            row=2, column=0, sticky="w", padx=5, pady=5
        )
        port_names = list(self.available_ports.keys())
        if not port_names:
            port_names = ["No ports found"]
        self.arduino_menu = OptionMenu(master, self.arduino_port_var, *port_names)
        self.arduino_menu.grid(row=2, column=1, sticky="ew", padx=5, pady=5)

        if self.available_ports:
            self.arduino_port_var.set(list(self.available_ports.keys())[0])

        self._toggle_arduino_menu()  # Set initial state
        return self.camera_menu  # Initial focus

    def _detect_devices(self):
        """Detects available cameras and serial ports."""
        # Detect cameras
        log.info("device_detection.camera.start")
        for i in range(10):  # Check up to 10 indices
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                self.available_cameras[f"Camera {i}"] = i
                cap.release()
        log.info("device_detection.camera.found", cameras=self.available_cameras)

        # Detect serial ports
        try:
            log.info("device_detection.ports.start")
            ports = serial.tools.list_ports.comports()
            for port in ports:
                # Use description for user-friendliness, device for connection
                self.available_ports[f"{port.description}"] = port.device
            log.info("device_detection.ports.found", ports=self.available_ports)
        except Exception as e:
            log.warning("device_detection.ports.error", error=str(e))
            self.available_ports = {}

    def _toggle_arduino_menu(self):
        """Enable or disable the Arduino port dropdown based on the checkbox."""
        if self.use_arduino_var.get() and self.available_ports:
            self.arduino_menu.config(state="normal")
        else:
            self.arduino_menu.config(state="disabled")
            if not self.available_ports:
                self.use_arduino_var.set(False)


    def validate(self):
        """Validate the inputs before closing the dialog."""
        if not self.available_cameras:
            messagebox.showerror(
                "Error", "No camera detected. Cannot start a live session."
            )
            return 0
        if self.use_arduino_var.get() and not self.available_ports:
            messagebox.showerror(
                "Error",
                "Arduino is enabled, but no serial port was found. Please check the connection or disable the 'Use Arduino' option.",
            )
            return 0
        return 1

    def apply(self):
        """Process the data and set the result."""
        use_arduino = self.use_arduino_var.get()
        selected_port_key = self.arduino_port_var.get()
        self.result = {
            "camera_index": self.available_cameras.get(self.camera_var.get()),
            "use_arduino": use_arduino,
            "arduino_port": self.available_ports.get(selected_port_key)
            if use_arduino
            else None,
        }


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
        self.notebook = None
        self.main_controls_frame = None
        self.zone_tab_frame = None
        self.status_var = StringVar()

        # ROI Tab Widgets
        self.roi_listbox = None
        self.run_analysis_btn = None
        self.zone_prop_name_var = StringVar()
        self.zone_prop_color_var = StringVar()
        self.zone_prop_enter_cmd_var = StringVar()
        self.zone_prop_exit_cmd_var = StringVar()

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

        # Model management variables
        self.active_weight_var = StringVar()
        self.use_openvino_var = BooleanVar(value=False)
        self.openvino_status_var = StringVar(value="Initializing...")

        self._create_welcome_frame()

    def _create_welcome_frame(self):
        """Creates the initial UI for project selection and model configuration."""
        if self.notebook:
            self.notebook.destroy()
            self.notebook = None
        if self.main_controls_frame:
            self.main_controls_frame.destroy()
            self.main_controls_frame = None

        self.root.geometry("")  # Let it resize
        self.welcome_frame = ttk.Frame(self.root, padding="10")
        self.welcome_frame.pack(expand=True, fill="both")

        # --- Title ---
        ttk.Label(
            self.welcome_frame,
            text="Welcome to Zebtrack Controller",
            font=("Helvetica", 16),
        ).pack(pady=(0, 15))

        # --- Model Configuration ---
        self._create_model_config_frame()

        # --- Project Actions ---
        project_actions_frame = ttk.LabelFrame(
            self.welcome_frame, text="Project Actions", padding=10
        )
        project_actions_frame.pack(fill="x", pady=10, expand=True)

        ttk.Button(
            project_actions_frame,
            text="Create New Project",
            command=self._create_project_workflow,
        ).pack(side="left", padx=10, expand=True, fill="x")
        ttk.Button(
            project_actions_frame,
            text="Open Existing Project",
            command=self._open_project_workflow,
        ).pack(side="left", padx=10, expand=True, fill="x")

    def _create_model_config_frame(self):
        """Builds the UI for model and OpenVINO configuration."""
        model_frame = ttk.LabelFrame(
            self.welcome_frame, text="Model Configuration", padding=10
        )
        model_frame.pack(fill="x", pady=5)
        model_frame.columnconfigure(1, weight=1)

        # --- Row 0: Weight Selection ---
        ttk.Label(model_frame, text="Active Weight:").grid(
            row=0, column=0, sticky="w", padx=5, pady=3
        )
        self.weights_dropdown = ttk.Combobox(
            model_frame, textvariable=self.active_weight_var, state="readonly"
        )
        self.weights_dropdown.grid(row=0, column=1, sticky="ew", padx=5, pady=3)
        self.weights_dropdown.bind(
            "<<ComboboxSelected>>", self._on_weight_selected
        )

        # --- Row 1: Weight Management Buttons ---
        btn_frame = ttk.Frame(model_frame)
        btn_frame.grid(row=1, column=1, sticky="w", padx=5, pady=3)
        ttk.Button(
            btn_frame, text="Load New Weight...", command=self._load_new_weight_clicked
        ).pack(side="left", padx=(0, 5))
        ttk.Button(
            btn_frame, text="Manage Weights...", command=self._manage_weights_clicked
        ).pack(side="left")

        # --- Row 2: OpenVINO Toggle ---
        self.openvino_checkbox = ttk.Checkbutton(
            model_frame,
            text="Optimize with OpenVINO (for Intel hardware)",
            variable=self.use_openvino_var,
            command=self._on_openvino_toggled,
        )
        self.openvino_checkbox.grid(
            row=2, column=0, columnspan=2, sticky="w", padx=5, pady=(8, 2)
        )

        # --- Row 3: OpenVINO Status ---
        self.openvino_status_label = ttk.Label(
            model_frame, textvariable=self.openvino_status_var, font=("Segoe UI", 8)
        )
        self.openvino_status_label.grid(
            row=3, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 5)
        )

    def _create_main_control_frame(self):
        """Creates the main UI with tabs for controlling the app."""
        if self.welcome_frame:
            self.welcome_frame.destroy()
        self.root.geometry("")  # Let it resize

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both", padx=5, pady=5)

        # Create the tabs
        self._create_main_controls_tab()
        self._create_roi_analysis_tab()
        self._create_reports_tab()

        # Status frame below the notebook
        status_text = (
            f"Project: {self.controller.project_manager.get_project_name()} "
            f"({self.controller.project_manager.get_project_type()})"
        )
        self.status_var.set(status_text)
        status_frame = Frame(self.root)
        status_frame.pack(pady=5, fill="x", padx=10, side="bottom")
        Label(status_frame, textvariable=self.status_var).pack()

        # Progress + video frame (hidden until needed)
        self._build_progress_frame()

    def _create_main_controls_tab(self):
        """Creates the tab with the main project controls."""
        self.main_controls_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.main_controls_frame, text="Main Control")

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
            self.batch_analysis_btn = Button(
                button_frame,
                text="Run Batch Analysis",
                command=self.controller.run_batch_analysis,
            )
            self.batch_analysis_btn.pack(side="left", padx=5)
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

    def _create_roi_analysis_tab(self):
        """Creates the tab for ROI and detection zone configuration."""
        # This tab is now for defining detection zones (polygon, squares)
        # and will replace the old ROI analysis functionality.
        self.roi_data = {}  # This will be repurposed for the new zone data
        self.drawing_mode = None
        self.current_polygon_points = []
        self.current_circle_center = None
        self._canvas_bg_image = None  # Keep a reference to the image

        # 1. Create the main frame for the tab and rename it
        self.zone_tab_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.zone_tab_frame, text="Configuração de Zonas")

        # 2. Create the PanedWindow for side-by-side panels
        main_pane = ttk.PanedWindow(self.zone_tab_frame, orient="horizontal")
        main_pane.pack(expand=True, fill="both")

        # 3. Create the control panel on the left
        self.zone_controls_frame = ttk.Frame(
            main_pane, padding=5, relief="groove", borderwidth=2
        )
        main_pane.add(self.zone_controls_frame, weight=1)

        # 4. Create the visualization panel on the right
        viz_frame = ttk.Frame(main_pane, padding=5, relief="sunken", borderwidth=2)
        main_pane.add(viz_frame, weight=4)

        # 5. Create the canvas for drawing
        self.roi_canvas = Canvas(viz_frame, bg="gray")
        self.roi_canvas.pack(expand=True, fill="both")

        # --- Drawing Actions ---
        actions_frame = ttk.LabelFrame(
            self.zone_controls_frame, text="Ações de Desenho", padding=10
        )
        actions_frame.pack(fill="x", pady=5)

        if self.controller.project_manager.get_project_type() == "pre-recorded":
            ttk.Button(
                actions_frame,
                text="Detectar Aquário (Auto)",
                command=self.controller.run_aquarium_detection,
            ).pack(fill="x", pady=2)
        else:  # Live mode
            ttk.Button(
                actions_frame,
                text="Iniciar Calibração",
                command=self.controller.run_live_calibration,
            ).pack(fill="x", pady=2)

        ttk.Button(
            actions_frame, text="Desenhar Polígono Principal", command=lambda: None
        ).pack(fill="x", pady=2)
        ttk.Button(
            actions_frame, text="Desenhar Área de Interesse", command=lambda: None
        ).pack(fill="x", pady=2)

        # --- Zone List ---
        zone_list_frame = ttk.LabelFrame(
            self.zone_controls_frame, text="Zonas Definidas", padding=10
        )
        zone_list_frame.pack(fill="both", expand=True, pady=5)

        self.zone_listbox = ttk.Treeview(
            zone_list_frame, columns=("name", "type"), show="headings"
        )
        self.zone_listbox.heading("name", text="Nome")
        self.zone_listbox.heading("type", text="Tipo")
        self.zone_listbox.column("type", width=60)
        self.zone_listbox.pack(side="left", fill="both", expand=True)

        # Scrollbar for the listbox
        scrollbar = ttk.Scrollbar(
            zone_list_frame, orient="vertical", command=self.zone_listbox.yview
        )
        self.zone_listbox.configure(yscrollcommand=scrollbar.set)
        self.zone_listbox.bind("<<TreeviewSelect>>", self._on_zone_select)
        scrollbar.pack(side="right", fill="y")

        # Buttons to manage the list
        zone_list_buttons_frame = ttk.Frame(self.zone_controls_frame)
        zone_list_buttons_frame.pack(fill="x", pady=(0, 5))
        ttk.Button(
            zone_list_buttons_frame, text="Salvar Propriedades", command=lambda: None
        ).pack(side="left", expand=True, fill="x", padx=2)
        ttk.Button(
            zone_list_buttons_frame, text="Remover Selecionada", command=lambda: None
        ).pack(side="left", expand=True, fill="x", padx=2)

        # --- Properties Panel ---
        self.zone_properties_frame = ttk.LabelFrame(
            self.zone_controls_frame, text="Propriedades da Zona", padding=10
        )
        self.zone_properties_frame.pack(fill="x", pady=5)

        # Create the widgets but don't show them initially
        self.prop_widgets = {}
        prop_grid_frame = ttk.Frame(self.zone_properties_frame)

        # Name
        self.prop_widgets["name_label"] = ttk.Label(prop_grid_frame, text="Nome:")
        self.prop_widgets["name_entry"] = ttk.Entry(
            prop_grid_frame, textvariable=self.zone_prop_name_var
        )

        # Color
        self.prop_widgets["color_label"] = ttk.Label(prop_grid_frame, text="Cor:")
        self.prop_widgets["color_combo"] = ttk.Combobox(
            prop_grid_frame,
            textvariable=self.zone_prop_color_var,
            values=["Vermelho", "Verde", "Azul", "Amarelo", "Ciano", "Magenta"],
            state="readonly",
        )

        # Arduino Commands Frame
        self.prop_widgets["arduino_frame"] = ttk.LabelFrame(
            prop_grid_frame, text="Comandos Arduino", padding=5
        )
        ttk.Label(self.prop_widgets["arduino_frame"], text="Entrada:").pack(
            side="left", padx=2
        )
        ttk.Entry(
            self.prop_widgets["arduino_frame"],
            textvariable=self.zone_prop_enter_cmd_var,
            width=5,
        ).pack(side="left", padx=2)
        ttk.Label(self.prop_widgets["arduino_frame"], text="Saída:").pack(
            side="left", padx=2
        )
        ttk.Entry(
            self.prop_widgets["arduino_frame"],
            textvariable=self.zone_prop_exit_cmd_var,
            width=5,
        ).pack(side="left", padx=2)

        self.prop_widgets["placeholder_label"] = ttk.Label(
            self.zone_properties_frame, text="Selecione uma zona para editar..."
        )
        self.prop_widgets["placeholder_label"].pack(pady=10)

    def _on_zone_select(self, event=None):
        """Shows and populates the properties panel when a zone is selected."""
        selected_items = self.zone_listbox.selection()

        # Hide all property widgets first
        for widget in self.prop_widgets.values():
            manager = widget.winfo_manager()
            if manager == "pack":
                widget.pack_forget()
            elif manager == "grid":
                widget.grid_forget()
            elif manager == "place":
                widget.place_forget()

        if not selected_items:
            # No item selected, show placeholder
            self.prop_widgets["placeholder_label"].pack(pady=10)
            return

        # An item is selected, show the property grid
        self.prop_widgets["name_label"].grid(row=0, column=0, sticky="w", pady=2)
        self.prop_widgets["name_entry"].grid(row=0, column=1, sticky="ew", pady=2)
        self.prop_widgets["color_label"].grid(row=1, column=0, sticky="w", pady=2)
        self.prop_widgets["color_combo"].grid(row=1, column=1, sticky="ew", pady=2)

        # Get data for the selected zone (mocked for now)
        # In a future step, this will come from a real data source
        item = self.zone_listbox.item(selected_items[0])
        zone_type = item["values"][1]

        # Mock data population
        self.zone_prop_name_var.set(item["values"][0])
        self.zone_prop_color_var.set("Vermelho")

        # Show Arduino frame only for "Área de Interesse" and if Arduino is enabled
        is_arduino_enabled = True  # Mock: This will be checked from project settings
        if zone_type == "Área de Interesse" and is_arduino_enabled:
            self.prop_widgets["arduino_frame"].grid(
                row=2, column=0, columnspan=2, sticky="ew", pady=5
            )
            self.zone_prop_enter_cmd_var.set("1")
            self.zone_prop_exit_cmd_var.set("2")

    def display_suggested_polygon(self, polygon: np.ndarray):
        """Draws a detected polygon on the canvas for user confirmation."""
        # Clear any previously suggested polygon
        self.roi_canvas.delete("suggested_polygon")

        # Store the points for potential editing or saving
        self.current_polygon_points = polygon.tolist()

        # Draw the new polygon with a distinct style
        self.roi_canvas.create_polygon(
            self.current_polygon_points,
            fill="",  # No fill
            outline="yellow",
            dash=(4, 4),
            width=2,
            tags="suggested_polygon",
        )
        self.set_status(
            "Detecção automática concluída. Aceite, edite ou desenhe manualmente."
        )

    def _create_reports_tab(self):
        """Creates the tab for generating reports and visualizations."""
        reports_tab_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(reports_tab_frame, text="Reports and Visualization")

        # Top section with main view and controls
        top_pane = ttk.PanedWindow(reports_tab_frame, orient="horizontal")
        top_pane.pack(expand=True, fill="both", pady=5)

        # --- Central Visualization Panel (Left) ---
        viz_frame = ttk.LabelFrame(top_pane, text="Visualization", padding=5)
        top_pane.add(viz_frame, weight=3)

        # Matplotlib Canvas
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
            self.report_figure = Figure(figsize=(5, 4), dpi=100)
            self.report_canvas_widget = FigureCanvasTkAgg(
                self.report_figure, master=viz_frame
            )
            self.report_canvas_widget.get_tk_widget().pack(
                side="top", fill="both", expand=True
            )
            self.report_ax = self.report_figure.add_subplot(111)
            self.report_ax.set_title("Analysis Plot")
            self.report_ax.set_xlabel("X")
            self.report_ax.set_ylabel("Y")
        except ImportError:
            Label(
                viz_frame, text="Matplotlib not found. Visualization is disabled."
            ).pack()


        # --- Side Control Panel (Right) ---
        controls_frame = ttk.LabelFrame(top_pane, text="Controls", padding=10)
        top_pane.add(controls_frame, weight=1)

        # Experiment selection
        ttk.Button(
            controls_frame,
            text="Load Project Results",
            command=self.controller.load_project_results_for_gui,
        ).pack(fill="x", pady=5, padx=5)
        ttk.Label(controls_frame, text="Select Experiment:").pack(fill="x", pady=2)
        self.report_experiment_var = StringVar()
        self.report_experiment_selector = ttk.Combobox(
            controls_frame, textvariable=self.report_experiment_var, state="readonly"
        )
        self.report_experiment_selector.pack(fill="x", pady=2, padx=5)

        # Action Buttons
        ttk.Button(
            controls_frame,
            text="Generate Trajectory",
            command=lambda: self.controller.generate_report_plot("trajectory"),
        ).pack(fill="x", pady=5, padx=5)

        ttk.Button(
            controls_frame,
            text="Generate Heatmap",
            command=lambda: self.controller.generate_report_plot("heatmap"),
        ).pack(fill="x", pady=5, padx=5)

        # Customization Checkboxes
        self.report_overlay_rois_var = BooleanVar(value=True)
        ttk.Checkbutton(
            controls_frame, text="Overlay ROIs", variable=self.report_overlay_rois_var
        ).pack(anchor="w", pady=5, padx=5)

        self.report_use_background_var = BooleanVar(value=False)
        ttk.Checkbutton(
            controls_frame,
            text="Use Video Background",
            variable=self.report_use_background_var,
        ).pack(anchor="w", pady=5, padx=5)

        # --- Bottom Export Panel ---
        export_frame = ttk.LabelFrame(reports_tab_frame, text="Export", padding=10)
        export_frame.pack(fill="x", pady=10)

        # Buttons
        ttk.Button(
            export_frame,
            text="Export Data (Summary)",
            command=lambda: self.controller.export_report_data(),
        ).grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(
            export_frame,
            text="Export Visual Report",
            command=lambda: self.controller.export_visual_report(),
        ).grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(
            export_frame,
            text="Save Current Plot (PNG)",
            command=lambda: self.controller.save_current_plot(),
        ).grid(row=0, column=2, padx=5, pady=5)

        # Format Options
        self.export_data_format_var = StringVar(value="excel")
        ttk.Label(export_frame, text="Data Format:").grid(
            row=1, column=0, sticky="w", padx=5
        )
        format_frame = ttk.Frame(export_frame)
        format_frame.grid(row=1, column=1, columnspan=2, sticky="w")
        ttk.Radiobutton(
            format_frame,
            text="Excel",
            variable=self.export_data_format_var,
            value="excel",
        ).pack(side="left")
        ttk.Radiobutton(
            format_frame, text="CSV", variable=self.export_data_format_var, value="csv"
        ).pack(side="left", padx=5)
        ttk.Radiobutton(
            format_frame,
            text="Parquet",
            variable=self.export_data_format_var,
            value="parquet",
        ).pack(side="left")

        self.export_report_format_var = StringVar(value="word")
        ttk.Label(export_frame, text="Report Format:").grid(
            row=2, column=0, sticky="w", padx=5
        )
        ttk.Radiobutton(
            export_frame,
            text="Word",
            variable=self.export_report_format_var,
            value="word",
        ).grid(row=2, column=0, sticky="e", padx=5)
        ttk.Radiobutton(
            export_frame,
            text="PDF",
            variable=self.export_report_format_var,
            value="pdf",
            state="disabled",
        ).grid(row=2, column=1, sticky="w")

    def _load_roi_data(self):
        """Opens a parquet file and tells the controller to load it."""
        parquet_path = self.ask_open_filenames(
            "Select data file (.parquet)", [("Parquet files", "*.parquet")]
        )
        if not parquet_path:
            return

        # This now calls the controller, which will call back to populate the UI
        self.controller.load_data_for_roi_analysis(parquet_path[0])

    def update_arena_selector(self, arena_ids: list):
        """Populates the arena selector combobox."""
        self.arena_selector["values"] = arena_ids
        if arena_ids:
            self.arena_selector_var.set(arena_ids[0])
            self.arena_selector.event_generate("<<ComboboxSelected>>")
        # Enable analysis button only when data and arenas are loaded
        self.run_analysis_btn.config(state="normal" if arena_ids else "disabled")

    def _on_arena_select(self, event=None):
        """Handles switching between arenas, updating the ROI list and canvas."""
        # Clear current listbox
        for item in self.roi_listbox.get_children():
            self.roi_listbox.delete(item)

        # Clear canvas drawings (but not the background image)
        self.roi_canvas.delete("all")
        if self._canvas_bg_image:
            self.roi_canvas.create_image(0, 0, anchor="nw", image=self._canvas_bg_image)

        # Repopulate with ROIs for the selected arena
        selected_arena_id = self.arena_selector_var.get()
        if selected_arena_id and selected_arena_id in self.roi_data:
            for roi in self.roi_data[selected_arena_id]:
                self.roi_listbox.insert("", "end", values=(roi["name"],))
                # Redraw the finalized polygon
                if roi["type"] == "polygon":
                    self.roi_canvas.create_polygon(
                        roi["coords"],
                        fill="cyan",
                        outline="blue",
                        stipple="gray25",
                        width=2,
                    )
                elif roi["type"] == "circle":
                    cx, cy, radius = roi["coords"]
                    self.roi_canvas.create_oval(
                        cx - radius,
                        cy - radius,
                        cx + radius,
                        cy + radius,
                        outline="blue",
                        fill="cyan",
                        stipple="gray25",
                        width=2,
                    )

    def display_roi_video_frame(self, video_path: str):
        """Receives a video path from the controller and displays its first frame."""
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                self.show_error(
                    "Error", "Could not open the associated video file."
                )
                return
            ret, frame = cap.read()
            cap.release()
            if not ret:
                self.show_error(
                    "Error", "Could not read the frame from the associated video."
                )
                return

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)

            canvas_w, canvas_h = (
                self.roi_canvas.winfo_width(),
                self.roi_canvas.winfo_height(),
            )
            if canvas_w < 2 or canvas_h < 2:
                self.root.update_idletasks()
                canvas_w, canvas_h = (
                    self.roi_canvas.winfo_width(),
                    self.roi_canvas.winfo_height(),
                )

            img.thumbnail((canvas_w, canvas_h), Image.Resampling.LANCZOS)

            self._canvas_bg_image = ImageTk.PhotoImage(image=img)
            self._on_arena_select()  # Redraw canvas and ROIs

        except Exception as e:
            self.show_error(
                "Processing Error",
                f"An error occurred while displaying the video frame: {e}",
            )

    def _run_analysis_clicked(self):
        """Gathers UI data and tells the controller to run the analysis."""
        try:
            flutter_n = int(self.flutter_n_var.get())
            num_animals = int(self.num_animals_var.get())
            social_radius = float(self.social_radius_var.get())
            arena_id = self.arena_selector_var.get()
        except (ValueError, TypeError):
            self.show_error(
                "Invalid Input",
                "Configuration values must be valid numbers.",
            )
            return

        if not arena_id:
            self.show_error(
                "Selection Required",
                "Please select an active aquarium for the analysis.",
            )
            return

        rois_for_arena = self.roi_data.get(arena_id, [])
        self.controller.run_roi_analysis(
            rois_for_arena=rois_for_arena,
            flutter_n=flutter_n,
            num_animals=num_animals,
            social_radius_cm=social_radius,
            arena_id=arena_id,
        )

    def display_roi_results(self, report_text: str):
        """Displays the analysis report in the results text widget."""
        self.results_text.config(state="normal")
        self.results_text.delete("1.0", "end")
        self.results_text.insert("1.0", report_text)
        self.results_text.config(state="disabled")

    def _start_polygon_drawing(self):
        """Activates polygon drawing mode."""
        self._stop_drawing()  # Ensure clean state
        self.drawing_mode = "polygon"
        self.current_polygon_points = []
        self.roi_canvas.config(cursor="crosshair")
        self.roi_canvas.bind("<Button-1>", self._on_canvas_click)
        self.roi_canvas.bind("<Double-Button-1>", self._on_canvas_double_click)
        self.roi_canvas.bind("<Motion>", self._on_canvas_motion)
        self.set_status(
            "Drawing Mode (Polygon): Click to add points, double-click to finish."
        )

    def _stop_drawing(self):
        """Deactivates any drawing mode and unbinds all associated events."""
        self.drawing_mode = None
        self.roi_canvas.config(cursor="")
        # Unbind all possible drawing events
        self.roi_canvas.unbind("<Button-1>")
        self.roi_canvas.unbind("<Double-Button-1>")
        self.roi_canvas.unbind("<Motion>")
        self.roi_canvas.unbind("<ButtonPress-1>")
        self.roi_canvas.unbind("<B1-Motion>")
        self.roi_canvas.unbind("<ButtonRelease-1>")

        self.roi_canvas.delete("elastic_line")
        self.roi_canvas.delete("temp_vertex")
        self.set_status("Ready.")

    def _on_canvas_click(self, event):
        """Handles single clicks on the canvas during polygon drawing."""
        if self.drawing_mode != "polygon":
            return

        self.current_polygon_points.append((event.x, event.y))
        # Draw a small circle to mark the vertex
        self.roi_canvas.create_oval(
            event.x - 2,
            event.y - 2,
            event.x + 2,
            event.y + 2,
            fill="red",
            outline="red",
            tags="temp_vertex",
        )

    def _on_canvas_motion(self, event):
        """Handles mouse movement for drawing elastic lines."""
        if self.drawing_mode != "polygon" or not self.current_polygon_points:
            return

        self.roi_canvas.delete("elastic_line")
        last_point = self.current_polygon_points[-1]
        first_point = self.current_polygon_points[0]

        # Line from last vertex to cursor
        self.roi_canvas.create_line(
            last_point[0],
            last_point[1],
            event.x,
            event.y,
            fill="yellow",
            dash=(4, 4),
            tags="elastic_line",
        )
        # Line from cursor to first vertex (if more than one point exists)
        if len(self.current_polygon_points) > 1:
            self.roi_canvas.create_line(
                event.x,
                event.y,
                first_point[0],
                first_point[1],
                fill="yellow",
                dash=(4, 4),
                tags="elastic_line",
            )

    def _on_canvas_double_click(self, event):
        """Finalizes the polygon drawing."""
        if self.drawing_mode != "polygon" or len(self.current_polygon_points) < 3:
            self._stop_drawing()
            return

        # Ask for a name
        roi_name = self.ask_string(
            "ROI Name", "Enter a name for this new Region of Interest:"
        )
        if not roi_name:
            self.current_polygon_points = []
            self._stop_drawing()
            return

        # Save and draw the final polygon
        current_arena_id = self.arena_selector_var.get()
        if not current_arena_id:
            self.show_error("Error", "No active aquarium selected.")
            self._stop_drawing()
            return

        new_roi = {
            "name": roi_name,
            "type": "polygon",
            "coords": self.current_polygon_points,
        }
        self.roi_data.setdefault(current_arena_id, []).append(new_roi)

        self.roi_canvas.create_polygon(
            self.current_polygon_points,
            fill="cyan",
            outline="blue",
            stipple="gray25",
            width=2,
        )

        # Update the listbox
        self.roi_listbox.insert("", "end", values=(roi_name,))

        self.current_polygon_points = []
        self._stop_drawing()

    def _remove_selected_roi(self):
        """Removes the ROI selected in the listbox."""
        selected_items = self.roi_listbox.selection()
        if not selected_items:
            self.show_warning(
                "No Selection", "Please select an ROI from the list to remove."
            )
            return

        selected_arena_id = self.arena_selector_var.get()
        if not selected_arena_id or selected_arena_id not in self.roi_data:
            return  # Should not happen if an item is selected

        # Find the index and name of the item to remove
        selected_item = selected_items[0]
        item_index = self.roi_listbox.index(selected_item)

        # Remove from data source
        del self.roi_data[selected_arena_id][item_index]

        # Refresh the view
        self._on_arena_select()

    def _run_center_periphery_analysis(self):
        """Runs the center-periphery analysis."""
        current_arena_id = self.arena_selector_var.get()
        if not current_arena_id:
            self.show_error(
                "Error", "Select an active aquarium and load the data first."
            )
            return

        dialog = CenterPeripheryDialog(self.root)
        if not dialog.result:
            return

        self.controller.run_center_periphery_analysis(
            arena_id=current_arena_id,
            method=dialog.result["method"],
            value=dialog.result["value"],
        )

    def _create_template_rois(self):
        """Opens a dialog to create ROIs from a template."""
        current_arena_id = self.arena_selector_var.get()
        if not current_arena_id:
            self.show_error("Error", "Select an active aquarium first.")
            return

        # Get the arena polygon bounds from the controller
        arena_data = self.controller.get_arena_data(current_arena_id)
        if not arena_data or "polygon_px" not in arena_data:
            self.show_error(
                "Error", "Could not get the aquarium polygon data."
            )
            return

        import numpy as np

        poly_points = np.array(arena_data["polygon_px"])
        x_min, y_min = poly_points.min(axis=0)
        x_max, y_max = poly_points.max(axis=0)
        width = x_max - x_min
        height = y_max - y_min

        dialog = TemplateDialog(self.root)
        if not dialog.result:
            return

        rois_to_add = []
        template = dialog.result
        if template["type"] == "vertical":
            lane_width = width / template["lanes"]
            for i in range(template["lanes"]):
                x1 = x_min + i * lane_width
                x2 = x1 + lane_width
                coords = [(x1, y_min), (x2, y_min), (x2, y_max), (x1, y_max)]
                rois_to_add.append(
                    {"name": f"V_Lane_{i + 1}", "type": "polygon", "coords": coords}
                )
        elif template["type"] == "horizontal":
            lane_height = height / template["lanes"]
            for i in range(template["lanes"]):
                y1 = y_min + i * lane_height
                y2 = y1 + lane_height
                coords = [(x_min, y1), (x_max, y1), (x_max, y2), (x_min, y2)]
                rois_to_add.append(
                    {"name": f"H_Lane_{i + 1}", "type": "polygon", "coords": coords}
                )
        elif template["type"] == "grid":
            col_width = width / template["cols"]
            row_height = height / template["rows"]
            for r in range(template["rows"]):
                for c in range(template["cols"]):
                    x1 = x_min + c * col_width
                    y1 = y_min + r * row_height
                    x2 = x1 + col_width
                    y2 = y1 + row_height
                    coords = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
                    rois_to_add.append(
                        {
                            "name": f"Grid_{r + 1}-{c + 1}",
                            "type": "polygon",
                            "coords": coords,
                        }
                    )

        self.roi_data.setdefault(current_arena_id, []).extend(rois_to_add)
        self._on_arena_select()

    def _start_circle_drawing(self):
        """Activates circle drawing mode."""
        self._stop_drawing()  # Ensure clean state
        self.drawing_mode = "circle"
        self.current_circle_center = None
        self.roi_canvas.config(cursor="crosshair")
        self.roi_canvas.bind("<ButtonPress-1>", self._on_canvas_press_circle)
        self.roi_canvas.bind("<B1-Motion>", self._on_canvas_drag_circle)
        self.roi_canvas.bind("<ButtonRelease-1>", self._on_canvas_release_circle)
        self.set_status(
            "Drawing Mode (Circle): Click and drag to define the radius."
        )

    def _on_canvas_press_circle(self, event):
        if self.drawing_mode != "circle":
            return
        self.current_circle_center = (event.x, event.y)

    def _on_canvas_drag_circle(self, event):
        if self.drawing_mode != "circle" or not self.current_circle_center:
            return

        self.roi_canvas.delete("elastic_line")
        cx, cy = self.current_circle_center
        radius = ((event.x - cx) ** 2 + (event.y - cy) ** 2) ** 0.5
        self.roi_canvas.create_oval(
            cx - radius,
            cy - radius,
            cx + radius,
            cy + radius,
            outline="yellow",
            dash=(4, 4),
            tags="elastic_line",
        )

    def _on_canvas_release_circle(self, event):
        if self.drawing_mode != "circle" or not self.current_circle_center:
            return

        cx, cy = self.current_circle_center
        radius = ((event.x - cx) ** 2 + (event.y - cy) ** 2) ** 0.5

        if radius < 2:  # Ignore tiny circles
            self._stop_drawing()
            return

        roi_name = self.ask_string(
            "ROI Name", "Enter a name for this new Region of Interest (Circle):"
        )
        if not roi_name:
            self._stop_drawing()
            return

        current_arena_id = self.arena_selector_var.get()
        if not current_arena_id:
            self.show_error("Error", "No active aquarium selected.")
            self._stop_drawing()
            return

        new_roi = {"name": roi_name, "type": "circle", "coords": (cx, cy, radius)}
        self.roi_data.setdefault(current_arena_id, []).append(new_roi)

        self.roi_canvas.create_oval(
            cx - radius,
            cy - radius,
            cx + radius,
            cy + radius,
            outline="blue",
            fill="cyan",
            stipple="gray25",
            width=2,
        )
        self.roi_listbox.insert("", "end", values=(roi_name,))

        self._stop_drawing()

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

        self._create_main_control_frame()

        project_type = pm.get_project_type()
        if project_type == "live":
            # Only attempt to connect if a port is configured from the dialog
            if settings.arduino.port:
                if not self.controller.arduino.connect():
                    self.show_warning(
                        "Arduino Warning",
                        f"Could not connect to Arduino on port {settings.arduino.port}. Running in offline mode.",
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
        Loop to capture frames from a LIVE source (camera).
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
        Loop to process frames from a LIVE source.
        """
        while not self.controller.program_exit_event.is_set():
            try:
                frame_number, frame = self.controller.frame_queue.get(timeout=1)
            except queue.Empty:
                continue

            if self.controller.is_processing:
                # Apply perspective warp if calibration data is available
                calib_data = self.controller.project_manager.project_data.get(
                    "calibration", {}
                )
                h_matrix = calib_data.get("homography_matrix")
                target_dims = calib_data.get("target_dims_px")

                if h_matrix and target_dims:
                    import numpy as np

                    h_matrix = np.array(h_matrix)
                    frame = cv2.warpPerspective(frame, h_matrix, tuple(target_dims))

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
                self.controller.detector.draw_overlay(frame, detections)

            cv2.imshow("Live View", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                self.controller.on_close()
                break
        cv2.destroyAllWindows()
        log.info("gui.live_processing_loop.finished")

    def _file_processing_loop(self):
        """
        Loop to efficiently process a video FILE.
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
                self.controller.detector.draw_overlay(frame, detections)
                cv2.imshow("File Processing", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    self.controller.program_exit_event.set()

        if show_preview:
            cv2.destroyAllWindows()
        self.root.after(0, self._cleanup_after_processing)

    # --- New UI Methods for Model Management ---

    def update_weights_dropdown(self, weights_list: list):
        """Clears and repopulates the weights dropdown."""
        self.weights_dropdown["values"] = weights_list
        if not weights_list:
            self.active_weight_var.set("No weights found.")
            self.weights_dropdown.config(state="disabled")
        else:
            self.weights_dropdown.config(state="readonly")

    def set_active_weight_in_dropdown(self, weight_name: str | None):
        """Sets the currently selected value in the dropdown."""
        if weight_name:
            self.active_weight_var.set(weight_name)

    def update_openvino_status_label(self, status_text: str):
        """Updates the text of the OpenVINO status label."""
        self.openvino_status_var.set(status_text)

    def update_openvino_checkbox(self, is_checked: bool):
        """Sets the state of the OpenVINO checkbox."""
        self.use_openvino_var.set(is_checked)

    def _on_weight_selected(self, event=None):
        """Callback when user selects a new weight from the dropdown."""
        selected_weight = self.active_weight_var.get()
        self.controller.set_active_weight(selected_weight)

    def _on_openvino_toggled(self):
        """Callback when user toggles the OpenVINO checkbox."""
        self.controller.set_openvino_usage(self.use_openvino_var.get())

    def _load_new_weight_clicked(self):
        """Handles the 'Load New Weight' button click."""
        filepath = filedialog.askopenfilename(
            title="Select a .pt Weight File",
            filetypes=[("PyTorch Weights", "*.pt")],
        )
        if not filepath:
            return

        # Ask user what to do with the new weight
        # The 'type' option creates custom buttons
        choice = messagebox.askquestion(
            "Add Weight",
            "Do you want to set this new weight as the default for all projects?",
            icon="question",
            type="yesnocancel",
        )

        if choice == "cancel":
            return
        elif choice == "yes":
            # Add as new default
            self.controller.add_new_weight(filepath, set_as_default=True)
        else:  # 'no'
            # Add as an alternative
            self.controller.add_new_weight(filepath, set_as_default=False)

    def _manage_weights_clicked(self):
        """Opens the weight management dialog."""
        ManageWeightsDialog(self.root, self.controller)

    def _create_project_workflow(self):
        """
        Handles the UI part of creating a new project by opening a comprehensive dialog,
        then calls the controller with the collected data.
        """
        dialog = CreateProjectDialog(self.root)
        if not dialog.result:
            return  # User cancelled

        # If live project, get device configuration
        if dialog.result["project_type"] == "live":
            live_config_dialog = LiveConfigDialog(self.root)
            if not live_config_dialog.result:
                return  # User cancelled live config

            # Update global settings object before creating the project
            live_config = live_config_dialog.result
            settings.camera.index = live_config["camera_index"]
            if live_config["use_arduino"] and live_config["arduino_port"]:
                settings.arduino.port = live_config["arduino_port"]
            else:
                # Set port to empty string to prevent connection attempt
                settings.arduino.port = ""

        # Call controller, which will now pass the model info automatically
        self.controller.create_project_workflow(
            project_path=dialog.result["project_path"],
            project_type=dialog.result["project_type"],
            video_files=dialog.result["video_files"],
            num_aquariums=dialog.result["num_aquariums"],
            aquarium_width_cm=dialog.result["aquarium_width_cm"],
            aquarium_height_cm=dialog.result["aquarium_height_cm"],
        )

    def _open_project_workflow(self):
        """Handles the UI part of opening a project, then calls the controller."""
        project_path = self.ask_directory(title="Select an Existing Project Folder")
        if not project_path:
            return

        self.controller.open_project_workflow(project_path)

    def _define_groups(self):
        """Allows the user to define names for the treatment groups."""
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
            # Convert and embed
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            imgtk = ImageTk.PhotoImage(image=img)
            if self.video_label:
                self.video_label.configure(image=imgtk)
                self.video_label.image = imgtk  # keep reference
        except Exception:
            # Fallback to OpenCV window if Pillow not installed or other error
            try:
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
        if button_name == "start_rec" and hasattr(self, "start_rec_btn"):
            self.start_rec_btn.config(state=state)
        elif button_name == "stop_rec" and hasattr(self, "stop_rec_btn"):
            self.stop_rec_btn.config(state=state)
        elif button_name == "process_video" and hasattr(self, "process_video_btn"):
            self.process_video_btn.config(state=state)
        elif button_name == "cancel_processing" and hasattr(self, "cancel_proc_btn"):
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
            cobaia_number = self.ask_string(
                "Subject Number", "Enter the subject number:"
            )
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


class TemplateDialog(simpledialog.Dialog):
    """Dialog to create ROI templates."""

    def body(self, master):
        self.template_type = StringVar(value="vertical")
        self.num_lanes = StringVar(value="3")
        self.num_rows = StringVar(value="2")
        self.num_cols = StringVar(value="2")

        ttk.Radiobutton(
            master,
            text="Vertical Lanes",
            variable=self.template_type,
            value="vertical",
        ).pack(anchor="w")
        ttk.Radiobutton(
            master,
            text="Horizontal Lanes",
            variable=self.template_type,
            value="horizontal",
        ).pack(anchor="w")
        ttk.Radiobutton(
            master, text="Grid", variable=self.template_type, value="grid"
        ).pack(anchor="w")

        ttk.Label(master, text="# of Lanes:").pack(anchor="w", pady=(5, 0))
        ttk.Entry(master, textvariable=self.num_lanes).pack(anchor="w")

        ttk.Label(master, text="Grid (Rows x Columns):").pack(
            anchor="w", pady=(5, 0)
        )
        grid_frame = ttk.Frame(master)
        grid_frame.pack(anchor="w")
        ttk.Entry(grid_frame, textvariable=self.num_rows, width=5).pack(side="left")
        ttk.Label(grid_frame, text="x").pack(side="left")
        ttk.Entry(grid_frame, textvariable=self.num_cols, width=5).pack(side="left")
        return master

    def apply(self):
        try:
            self.result = {
                "type": self.template_type.get(),
                "lanes": int(self.num_lanes.get()),
                "rows": int(self.num_rows.get()),
                "cols": int(self.num_cols.get()),
            }
        except (ValueError, TypeError):
            self.result = None


class CenterPeripheryDialog(simpledialog.Dialog):
    """Dialog for center-periphery analysis settings."""

    def body(self, master):
        self.method = StringVar(value="distance")
        self.value = StringVar(value="5.0")

        ttk.Label(master, text="Method:").pack(anchor="w")
        ttk.Radiobutton(
            master,
            text="Distance from Edge (cm)",
            variable=self.method,
            value="distance",
        ).pack(anchor="w")
        ttk.Radiobutton(
            master,
            text="Area Ratio (0.0-1.0)",
            variable=self.method,
            value="area_ratio",
        ).pack(anchor="w")

        ttk.Label(master, text="Value:").pack(anchor="w", pady=(5, 0))
        ttk.Entry(master, textvariable=self.value).pack(anchor="w")
        return master

    def apply(self):
        try:
            self.result = {
                "method": self.method.get(),
                "value": float(self.value.get()),
            }
        except (ValueError, TypeError):
            self.result = None


if __name__ == "__main__":
    # Using print is fine here as it's for direct execution feedback
    print("This file is intended to be imported, not run directly.")
    print("Run the main application script to start Zebtrack.")
