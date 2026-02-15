"""
CreateProjectDialog.

Extracted from gui.py for better modularity.
"""

import os
from tkinter import (
    BooleanVar,
    Button,
    Checkbutton,
    Entry,
    Frame,
    Label,
    StringVar,
    filedialog,
    messagebox,
    simpledialog,
    ttk,
)
from typing import Any

from zebtrack.ui.window_utils import schedule_maximize


class CreateProjectDialog(simpledialog.Dialog):
    """A custom dialog to gather all new project information."""

    def __init__(self, parent):
        """Initialize the create project dialog.

        Args:
            parent: Parent widget.
        """
        self.project_path: str | None = None
        self.result: dict[str, Any] | None = None
        self.video_paths: list[str] = []
        super().__init__(parent, "Criar Novo Projeto")

    def body(self, master):
        """Create project creation dialog body with all configuration fields.

        Args:
            master: Parent widget for dialog body.

        Returns:
            The initial focus widget.
        """
        schedule_maximize(self)
        self.project_name_var = StringVar()
        self.num_aquariums_var = StringVar(value="1")
        self.animals_per_aquarium_var = StringVar(value="1")
        self.aquarium_width_var = StringVar(value="10.0")
        self.aquarium_height_var = StringVar(value="10.0")
        self.project_type_var = StringVar(value="pre-recorded")
        self.video_files = []
        self.video_list_var = StringVar(value="Nenhum vídeo selecionado.")
        self.use_timed_recording_var = BooleanVar(value=False)
        self.recording_duration_var = StringVar(value="5")
        self.use_countdown_var = BooleanVar(value=False)
        self.countdown_duration_var = StringVar(value="5")

        # Vars for live project experimental design
        self.total_days_var = StringVar(value="1")
        self.subjects_per_group_var = StringVar(value="1")
        self.num_groups_var = StringVar(value="1")
        self.group_name_vars = [StringVar() for _ in range(6)]

        # Frame interval configuration variables
        self.analysis_interval_var = StringVar(value="10")
        self.display_interval_var = StringVar(value="10")

        # Detection method configuration variables
        self.aquarium_method_var = StringVar(value="seg")  # Default from settings
        self.animal_method_var = StringVar(value="det")  # Default from settings

        # --- Project Name ---
        Label(master, text="Nome do Projeto:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        Entry(master, textvariable=self.project_name_var, width=40).grid(
            row=0, column=1, columnspan=2, sticky="ew", padx=5
        )

        # --- Base Path ---
        Label(master, text="Pasta do Projeto:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.path_entry = Entry(master, width=40)
        self.path_entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=5)
        Button(master, text="Procurar...", command=self._select_path).grid(row=1, column=3, padx=5)

        # --- Calibration ---
        Label(master, text="Número de Aquários:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        Entry(master, textvariable=self.num_aquariums_var, width=10).grid(
            row=2, column=1, sticky="w", padx=5
        )

        Label(master, text="Animais por Aquário:").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        Entry(master, textvariable=self.animals_per_aquarium_var, width=10).grid(
            row=3, column=1, sticky="w", padx=5
        )

        Label(master, text="Largura do Aquário (cm):").grid(
            row=4, column=0, sticky="w", padx=5, pady=2
        )
        Entry(master, textvariable=self.aquarium_width_var, width=10).grid(
            row=4, column=1, sticky="w", padx=5
        )

        Label(master, text="Altura do Aquário (cm):").grid(
            row=5, column=0, sticky="w", padx=5, pady=2
        )
        Entry(master, textvariable=self.aquarium_height_var, width=10).grid(
            row=5, column=1, sticky="w", padx=5
        )

        # --- Frame Intervals ---
        Label(master, text="Intervalo de Análise (frames):").grid(
            row=6, column=0, sticky="w", padx=5, pady=2
        )
        Entry(master, textvariable=self.analysis_interval_var, width=10).grid(
            row=6, column=1, sticky="w", padx=5
        )

        Label(master, text="Intervalo de Exibição (frames):").grid(
            row=7, column=0, sticky="w", padx=5, pady=2
        )
        Entry(master, textvariable=self.display_interval_var, width=10).grid(
            row=7, column=1, sticky="w", padx=5
        )

        # --- Detection Methods ---
        Label(master, text="Método para Aquário:").grid(row=8, column=0, sticky="w", padx=5, pady=2)
        aquarium_method_combo = ttk.Combobox(
            master,
            textvariable=self.aquarium_method_var,
            values=["seg", "det"],
            state="readonly",
            width=8,
        )
        aquarium_method_combo.grid(row=8, column=1, sticky="w", padx=5)

        Label(master, text="Método para Animais:").grid(row=9, column=0, sticky="w", padx=5, pady=2)
        animal_method_combo = ttk.Combobox(
            master,
            textvariable=self.animal_method_var,
            values=["seg", "det"],
            state="readonly",
            width=8,
        )
        animal_method_combo.grid(row=9, column=1, sticky="w", padx=5)

        # --- Project Type & Videos ---
        Label(master, text="Tipo de Projeto:").grid(row=10, column=0, sticky="w", padx=5, pady=2)
        ttk.Radiobutton(
            master,
            text="Pré-gravado",
            variable=self.project_type_var,
            value="pre-recorded",
            command=self._update_project_type_options,
        ).grid(row=10, column=1, sticky="w", padx=5)
        ttk.Radiobutton(
            master,
            text="Ao Vivo",
            variable=self.project_type_var,
            value="live",
            command=self._update_project_type_options,
        ).grid(row=10, column=2, sticky="w", padx=5)

        # Video/Folder selection buttons
        video_selection_frame = Frame(master)
        video_selection_frame.grid(row=11, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        self.video_files_button = Button(
            video_selection_frame,
            text="Selecionar Vídeos...",
            command=self._select_video_files,
        )
        self.video_files_button.pack(side="left", padx=(0, 5))

        self.video_folder_button = Button(
            video_selection_frame,
            text="Selecionar Pasta...",
            command=self._select_video_folder,
        )
        self.video_folder_button.pack(side="left")

        Label(master, textvariable=self.video_list_var, wraplength=400).grid(
            row=11, column=2, columnspan=2, sticky="w", padx=5
        )

        # --- Live Recording Options ---
        self.live_options_frame = Frame(master)
        self.live_options_frame.grid(row=12, column=0, columnspan=4, sticky="ew", padx=5)
        Checkbutton(
            self.live_options_frame,
            text="Usar gravação com tempo?",
            variable=self.use_timed_recording_var,
            command=self._update_project_type_options,
        ).pack(side="left")
        self.duration_entry = Entry(
            self.live_options_frame, textvariable=self.recording_duration_var, width=5
        )
        self.duration_entry.pack(side="left", padx=5)
        Label(self.live_options_frame, text="minutos").pack(side="left", padx=(0, 10))

        # Countdown options
        Checkbutton(
            self.live_options_frame,
            text="Usar contagem regressiva?",
            variable=self.use_countdown_var,
            command=self._update_project_type_options,
        ).pack(side="left")
        self.countdown_entry = Entry(
            self.live_options_frame, textvariable=self.countdown_duration_var, width=5
        )
        self.countdown_entry.pack(side="left", padx=5)
        Label(self.live_options_frame, text="segundos").pack(side="left")

        # --- Live Project Experimental Design ---
        self.live_project_frame = ttk.LabelFrame(
            master, text="Design Experimental (Projeto ao Vivo)", padding=10
        )
        self.live_project_frame.grid(row=13, column=0, columnspan=4, sticky="ew", padx=5, pady=5)
        # Widgets inside live_project_frame
        ttk.Label(self.live_project_frame, text="Total de Dias do Experimento:").grid(
            row=0, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(self.live_project_frame, textvariable=self.total_days_var, width=10).grid(
            row=0, column=1, sticky="w", padx=5
        )
        ttk.Label(self.live_project_frame, text="Cobaias por Grupo:").grid(
            row=1, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(self.live_project_frame, textvariable=self.subjects_per_group_var, width=10).grid(
            row=1, column=1, sticky="w", padx=5
        )
        ttk.Label(self.live_project_frame, text="Número de Grupos:").grid(
            row=2, column=0, sticky="w", padx=5, pady=2
        )
        num_groups_entry = ttk.Entry(
            self.live_project_frame, textvariable=self.num_groups_var, width=10
        )
        num_groups_entry.grid(row=2, column=1, sticky="w", padx=5)
        self.num_groups_var.trace_add("write", self._on_num_groups_change)
        self.group_names_frame = ttk.LabelFrame(
            self.live_project_frame, text="Nomes dos Grupos", padding=5
        )
        self.group_names_frame.grid(row=3, column=0, columnspan=4, sticky="ew", padx=5, pady=5)
        self.group_name_entries = []
        for i in range(6):
            row, col = divmod(i, 2)
            ttk.Label(self.group_names_frame, text=f"Grupo {i + 1}:").grid(
                row=row, column=col * 2, sticky="w", padx=5, pady=2
            )
            entry = ttk.Entry(
                self.group_names_frame, textvariable=self.group_name_vars[i], width=20
            )
            entry.grid(row=row, column=col * 2 + 1, sticky="ew", padx=5)
            self.group_name_entries.append(entry)

        self._update_project_type_options()  # Set initial state
        self._on_num_groups_change()  # Set initial state for group names
        return self.path_entry  # initial focus

    def _select_path(self):
        path = filedialog.askdirectory(title="Selecione uma Pasta Principal para o Projeto")
        if path:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, path)

    def _select_video_files(self):
        """Select individual video files."""
        files = filedialog.askopenfilenames(
            title="Selecione os Arquivos de Vídeo",
            filetypes=[("Arquivos de vídeo", "*.mp4 *.avi *.mov")],
        )
        if files:
            # Initialize if needed
            if not hasattr(self, "video_paths") or not isinstance(self.video_paths, list):
                self.video_paths = []

            # Add new files to the list (avoid duplicates)
            for f in files:
                if f not in self.video_paths:
                    self.video_paths.append(f)

            self._update_video_selection_display()

    def _select_video_folder(self):
        """Select a folder containing videos."""
        folder = filedialog.askdirectory(title="Selecione uma Pasta Contendo Vídeos")
        if folder:
            # Initialize if needed
            if not hasattr(self, "video_paths") or not isinstance(self.video_paths, list):
                self.video_paths = []

            # Add folder to the list (avoid duplicates)
            if folder not in self.video_paths:
                self.video_paths.append(folder)

            self._update_video_selection_display()

    def _update_video_selection_display(self):
        """Update the display showing selected videos/folders."""
        if not hasattr(self, "video_paths") or not self.video_paths:
            self.video_list_var.set("Nenhum vídeo/pasta selecionado.")
            return

        # Count files and folders
        files = [p for p in self.video_paths if os.path.isfile(p)]
        folders = [p for p in self.video_paths if os.path.isdir(p)]

        parts = []
        if files:
            parts.append(f"{len(files)} arquivo(s)")
        if folders:
            parts.append(f"{len(folders)} pasta(s)")

        if parts:
            self.video_list_var.set(" + ".join(parts) + " selecionado(s).")
        else:
            self.video_list_var.set("Seleção contém caminhos inválidos.")

    def _on_num_groups_change(self, *args):
        try:
            num_groups = int(self.num_groups_var.get())
        except (ValueError, TypeError):
            num_groups = 0
        if not 0 <= num_groups <= 6:
            num_groups = 0  # Treat invalid numbers as 0
            # Optionally show a warning or clear the field
        for i, entry in enumerate(self.group_name_entries):
            if i < num_groups:
                entry.config(state="normal")
            else:
                entry.config(state="disabled")
                self.group_name_vars[i].set("")  # Clear disabled fields

    def _update_project_type_options(self):
        """Shows/hides options based on the selected project type."""
        if self.project_type_var.get() == "pre-recorded":
            self.video_files_button.config(state="normal")
            self.video_folder_button.config(state="normal")
            self.live_options_frame.grid_remove()
            self.live_project_frame.grid_remove()
        else:  # Live
            self.video_files_button.config(state="disabled")
            self.video_folder_button.config(state="disabled")
            self.video_list_var.set("Não aplicável para projetos ao vivo.")
            self.live_options_frame.grid()
            self.live_project_frame.grid()  # Show the new frame
            if self.use_timed_recording_var.get():
                self.duration_entry.config(state="normal")
            else:
                self.duration_entry.config(state="disabled")

            if self.use_countdown_var.get():
                self.countdown_entry.config(state="normal")
            else:
                self.countdown_entry.config(state="disabled")

    def validate(self):
        """Validate all project configuration fields.

        Returns:
            True if all required fields are valid, False otherwise.
        """
        # Run a sequence of focused validators. Each returns (ok, message)
        validators = [
            self._validate_base_path_and_name,
            self._validate_video_selection_if_prerecorded,
            self._validate_calibration_numbers,
            self._validate_live_settings_if_needed,
            self._validate_intervals,
        ]

        for validator in validators:
            ok, msg = validator()
            if not ok:
                messagebox.showerror("Erro", msg)
                return 0

        return 1

    # ---------------------- helper validators ------------------------
    def _validate_base_path_and_name(self) -> tuple[bool, str]:
        base_path = self.path_entry.get()
        if not base_path or not os.path.isdir(base_path):
            return False, "Por favor, selecione uma pasta principal válida."

        project_name = self.project_name_var.get()
        if not project_name.strip():
            return False, "O nome do projeto não pode estar vazio."

        self.project_path = os.path.join(base_path, project_name)
        if os.path.exists(self.project_path) and os.listdir(self.project_path):
            return False, "Uma pasta de projeto com este nome já existe e não está vazia."

        return True, ""

    def _validate_video_selection_if_prerecorded(self) -> tuple[bool, str]:
        if self.project_type_var.get() != "pre-recorded":
            return True, ""

        if not hasattr(self, "video_paths") or not self.video_paths:
            return False, (
                "Por favor, selecione pelo menos um arquivo de vídeo ou pasta para "
                "análise pré-gravada."
            )

        return True, ""

    def _validate_calibration_numbers(self) -> tuple[bool, str]:
        try:
            num_aquariums = int(self.num_aquariums_var.get())
            animals_per_aquarium = int(self.animals_per_aquarium_var.get())
            float(self.aquarium_width_var.get())
            float(self.aquarium_height_var.get())
            if num_aquariums <= 0 or animals_per_aquarium <= 0:
                raise ValueError
        except ValueError:
            return False, "Os valores devem ser positivos."

        return True, ""

    def _validate_live_settings_if_needed(self) -> tuple[bool, str]:
        if self.project_type_var.get() != "live":
            return True, ""

        try:
            total_days = int(self.total_days_var.get())
            subjects_per_group = int(self.subjects_per_group_var.get())
            num_groups = int(self.num_groups_var.get())
            if total_days <= 0 or subjects_per_group <= 0 or num_groups <= 0:
                raise ValueError
            if not 1 <= num_groups <= 6:
                return False, "O número de grupos deve ser entre 1 e 6."
            for i in range(num_groups):
                if not self.group_name_vars[i].get().strip():
                    return False, f"O nome do Grupo {i + 1} não pode estar vazio."
        except (ValueError, TypeError):
            return False, (
                "Os parâmetros do design experimental devem ser números positivos válidos."
            )

        if self.use_timed_recording_var.get():
            try:
                duration = float(self.recording_duration_var.get())
                if duration <= 0:
                    raise ValueError
            except ValueError:
                return False, "A duração da gravação deve ser um número positivo."

        if self.use_countdown_var.get():
            try:
                countdown = int(self.countdown_duration_var.get())
                if countdown <= 0:
                    raise ValueError
            except ValueError:
                return False, "A duração da contagem regressiva deve ser um inteiro positivo."

        return True, ""

    def _validate_intervals(self) -> tuple[bool, str]:
        try:
            analysis_interval = int(self.analysis_interval_var.get())
            display_interval = int(self.display_interval_var.get())
            if analysis_interval <= 0 or display_interval <= 0:
                raise ValueError
        except ValueError:
            return False, (
                "Os intervalos de análise e exibição devem ser números inteiros positivos."
            )

        return True, ""

    def apply(self):
        """Apply the project configuration and store in result dictionary."""
        duration = 0.0
        if self.use_timed_recording_var.get():
            try:
                # Duration in minutes, convert to seconds for internal use
                duration = float(self.recording_duration_var.get()) * 60
            except ValueError:
                pass  # Should be caught by validate

        countdown_duration = 0
        if self.use_countdown_var.get():
            try:
                countdown_duration = int(self.countdown_duration_var.get())
            except ValueError:
                pass

        # Use video_paths if available, fallback to empty list
        video_paths = getattr(self, "video_paths", [])

        num_aquariums = int(self.num_aquariums_var.get())
        animals_per_aquarium = int(self.animals_per_aquarium_var.get())

        self.result = {
            "project_path": self.project_path,
            "project_type": self.project_type_var.get(),
            "video_files": video_paths,  # Now can contain files AND folders
            "num_aquariums": num_aquariums,
            "animals_per_aquarium": animals_per_aquarium,
            "aquarium_width_cm": float(self.aquarium_width_var.get()),
            "aquarium_height_cm": float(self.aquarium_height_var.get()),
            "use_timed_recording": self.use_timed_recording_var.get(),
            "recording_duration_s": float(duration),
            "use_countdown": self.use_countdown_var.get(),
            "countdown_duration_s": countdown_duration,
            "analysis_interval_frames": int(self.analysis_interval_var.get()),
            "display_interval_frames": int(self.display_interval_var.get()),
            "aquarium_method": self.aquarium_method_var.get(),
            "animal_method": self.animal_method_var.get(),
            "use_single_subject_tracker": animals_per_aquarium == 1,
            # Initialize new keys to None
            "experiment_days": None,
            "subjects_per_group": None,
            "num_groups": None,
            "group_names": None,
        }

        if self.project_type_var.get() == "live":
            num_groups = int(self.num_groups_var.get())
            self.result["experiment_days"] = int(self.total_days_var.get())
            self.result["subjects_per_group"] = int(self.subjects_per_group_var.get())
            self.result["num_groups"] = num_groups
            self.result["group_names"] = [
                self.group_name_vars[i].get().strip() for i in range(num_groups)
            ]
