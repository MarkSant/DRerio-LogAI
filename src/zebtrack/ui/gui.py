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
from zebtrack.settings import settings

log = structlog.get_logger()


class CalibrationDialog(simpledialog.Dialog):
    """Dialog for model calibration and diagnostics."""

    def __init__(self, parent, controller):
        self.controller = controller
        # Still need this for some callbacks like _manage_weights_clicked
        self.view = controller.view

        # Local Tkinter variables for this dialog
        self.active_weight_var = StringVar()
        self.use_openvino_var = BooleanVar()
        self.openvino_status_var = StringVar()

        # --- Vars for diagnostic ---
        self.frames_to_analyze_var = StringVar(value="10")
        self.confidence_threshold_var = StringVar(value="0.25")
        self.video_path_label_var = StringVar(value="Nenhum vídeo selecionado.")
        self.diagnostic_video_path = ""
        self.model_test_var = StringVar(value="YOLO (PyTorch)")

        # --- Vars for sensitivity control ---
        self.sensitivity_var = StringVar(value="0.15")

        super().__init__(parent, "Calibração e Diagnóstico")

    def body(self, master):
        # --- Frame for model configuration ---
        model_frame = ttk.LabelFrame(
            master, text="Configuração do Modelo", padding=10
        )
        model_frame.pack(fill="x", pady=5, padx=5)
        model_frame.columnconfigure(1, weight=1)

        # --- Row 0: Weight Selection ---
        ttk.Label(model_frame, text="Peso Ativo:").grid(
            row=0, column=0, sticky="w", padx=5, pady=3
        )
        self.weights_dropdown = ttk.Combobox(
            model_frame, textvariable=self.active_weight_var, state="readonly"
        )
        self.weights_dropdown.grid(row=0, column=1, sticky="ew", padx=5, pady=3)
        self.weights_dropdown.bind(
            "<<ComboboxSelected>>", self._on_weight_selected_local
        )
        self._populate_weights_dropdown()

        # --- Row 1: Weight Management Buttons ---
        btn_frame = ttk.Frame(model_frame)
        btn_frame.grid(row=1, column=1, sticky="w", padx=5, pady=3)
        ttk.Button(
            btn_frame,
            text="Carregar Novo Peso...",
            command=self._load_new_weight_local,
        ).pack(side="left", padx=(0, 5))
        ttk.Button(
            btn_frame, text="Gerenciar Pesos...", command=self._manage_weights_local
        ).pack(side="left")

        # --- Row 2: OpenVINO Toggle ---
        self.openvino_checkbox = ttk.Checkbutton(
            model_frame,
            text="Otimizar com OpenVINO (para hardware Intel)",
            variable=self.use_openvino_var,
            command=self._on_openvino_toggled_local,
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

        # Set initial state from controller
        self.use_openvino_var.set(self.controller.use_openvino)
        self.update_openvino_status_label(self.controller.get_openvino_status())

        # --- Frame for diagnostics ---
        diag_frame = ttk.LabelFrame(
            master, text="Diagnóstico de Desempenho do Modelo", padding=10
        )
        diag_frame.pack(fill="x", pady=10, padx=5)

        # --- Video Selection ---
        video_frame = ttk.Frame(diag_frame)
        video_frame.pack(fill="x", padx=10, pady=5)
        ttk.Button(
            video_frame,
            text="Selecionar Vídeo...",
            command=self._select_diagnostic_video
        ).pack(side="left")
        ttk.Label(video_frame, textvariable=self.video_path_label_var).pack(
            side="left", padx=5
        )

        # --- Parameters ---
        params_frame = ttk.Frame(diag_frame, padding=5)
        params_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(params_frame, text="Nº de Frames para Analisar:").grid(
            row=0, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(
            params_frame, textvariable=self.frames_to_analyze_var, width=10
        ).grid(row=0, column=1, sticky="w", padx=5)

        ttk.Label(params_frame, text="Limiar de Confiança:").grid(
            row=1, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(
            params_frame, textvariable=self.confidence_threshold_var, width=10
        ).grid(row=1, column=1, sticky="w", padx=5)

        # --- Model Selection for Diagnostic ---
        ttk.Label(params_frame, text="Modelo(s) a Testar:").grid(
            row=2, column=0, sticky="w", padx=5, pady=2
        )
        self.model_test_dropdown = ttk.Combobox(
            params_frame, textvariable=self.model_test_var, state="readonly",
            values=["YOLO (PyTorch)", "OpenVINO", "Ambos"], width=15
        )
        self.model_test_dropdown.grid(row=2, column=1, sticky="w", padx=5)

        # --- Row 3: Sensitivity Control ---
        ttk.Label(params_frame, text="Ajuste de Sensibilidade:").grid(
            row=3, column=0, sticky="w", padx=5, pady=2
        )

        sensitivity_frame = ttk.Frame(params_frame)
        sensitivity_frame.grid(row=3, column=1, sticky="w", padx=5)

        self.sensitivity_scale = ttk.Scale(
            sensitivity_frame,
            from_=0.05,
            to=0.50,
            orient="horizontal",
            length=150,
            command=self._on_sensitivity_change
        )
        self.sensitivity_scale.set(0.15)  # Valor padrão para modelo com baixa confiança
        self.sensitivity_scale.pack(side="left")

        self.sensitivity_label = ttk.Label(sensitivity_frame, text="0.15")
        self.sensitivity_label.pack(side="left", padx=(5, 0))

        # --- Tooltip para sensibilidade ---
        tooltip_label = ttk.Label(params_frame, text="(Valores menores detectam mais objetos)",
                                font=("Segoe UI", 8), foreground="gray")
        tooltip_label.grid(row=4, column=1, sticky="w", padx=5, pady=(0, 5))

        ttk.Button(
            diag_frame,
            text="Testar Modelo em Vídeo...",
            command=self._run_diagnostic_test,
        ).pack(fill="x", padx=10, pady=5)

    def _populate_weights_dropdown(self):
        """(Re)populates the weights dropdown in the dialog."""
        weights_list = self.controller.get_all_weight_names()
        self.weights_dropdown["values"] = weights_list
        if not weights_list:
            self.active_weight_var.set("Nenhum peso encontrado.")
            self.weights_dropdown.config(state="disabled")
        else:
            self.weights_dropdown.config(state="readonly")
            # Set to the controller's current weight
            current_weight = self.controller.active_weight_name
            if current_weight in weights_list:
                self.active_weight_var.set(current_weight)
            elif weights_list:
                self.active_weight_var.set(weights_list[0])

    def _on_weight_selected_local(self, event=None):
        """Callback when user selects a new weight from the dropdown."""
        selected_weight = self.active_weight_var.get()
        self.controller.set_active_weight(selected_weight, self)

    def _on_openvino_toggled_local(self):
        """Callback when user toggles the OpenVINO checkbox."""
        self.controller.set_openvino_usage(self.use_openvino_var.get(), self)

    def update_openvino_status_label(self, status: str):
        """Updates the status label with the given text."""
        self.openvino_status_var.set(status)

    def _load_new_weight_local(self):
        """Handles the 'Load New Weight' button click."""
        # This can call the view's method as it's just a file dialog
        self.view._load_new_weight_clicked()
        # Repopulate this dialog's dropdown after the controller has the new weight
        self._populate_weights_dropdown()
        # Status is updated by the controller when the weight is set.

    def _manage_weights_local(self):
        """Opens the weight management dialog and provides a callback to refresh."""
        # The callback will be called by the ManageWeightsDialog upon closing
        def refresh_callback():
            self._populate_weights_dropdown()
            # The controller will handle the status update when a new weight is selected
            # or the default is changed.

        ManageWeightsDialog(self.parent, self.controller, refresh_callback)

    def _select_diagnostic_video(self):
        path = filedialog.askopenfilename(
            title="Selecione o Vídeo para Diagnóstico",
            filetypes=[("Arquivos de vídeo", "*.mp4 *.avi *.mov")],
        )
        if path:
            self.diagnostic_video_path = path
            self.video_path_label_var.set(os.path.basename(path))

    def _on_sensitivity_change(self, value):
        """Atualiza label quando threshold muda e aplica globalmente"""
        threshold_value = float(value)
        self.sensitivity_label.config(text=f"{threshold_value:.2f}")
        self.sensitivity_var.set(f"{threshold_value:.2f}")

        # Atualiza threshold globalmente no detector ativo
        if hasattr(self.controller, 'detector') and self.controller.detector:
            if hasattr(self.controller.detector.plugin, 'conf_threshold'):
                old_threshold = self.controller.detector.plugin.conf_threshold
                self.controller.detector.plugin.conf_threshold = threshold_value

                # Log da mudança para debug (usando print simples para evitar dependências)
                print(f"Sensitivity changed: {old_threshold:.2f} → {threshold_value:.2f}")

        # Atualiza também a variável de confidence threshold para diagnósticos
        self.confidence_threshold_var.set(f"{threshold_value:.2f}")

    def _run_diagnostic_test(self):
        # --- Validation ---
        if not self.diagnostic_video_path:
            messagebox.showerror("Erro", "Por favor, selecione um arquivo de vídeo.")
            return

        try:
            frames = int(self.frames_to_analyze_var.get())
            if frames <= 0:
                messagebox.showerror(
                    "Erro", "O número de frames deve ser um inteiro positivo."
                )
                return
        except ValueError:
            messagebox.showerror(
                "Erro", "O número de frames deve ser um número inteiro."
            )
            return

        try:
            conf = float(self.confidence_threshold_var.get())
            if not 0.0 <= conf <= 1.0:
                messagebox.showerror(
                    "Erro", "O limiar de confiança deve ser um número entre 0.0 e 1.0."
                )
                return
        except ValueError:
            messagebox.showerror(
                "Erro", "O limiar de confiança deve ser um número válido."
            )
            return

        # --- Config Build ---
        model_to_test = self.model_test_var.get()

        config = {
            "video_path": self.diagnostic_video_path,
            "frames_to_analyze": int(self.frames_to_analyze_var.get()),
            "confidence_threshold": float(self.confidence_threshold_var.get()),
            "model_to_test": model_to_test,
        }

        self.controller.run_model_diagnostic(config)
        self.destroy()

    def buttonbox(self):
        # Override to have only a close button
        box = ttk.Frame(self)
        w = ttk.Button(box, text="Fechar", width=10, command=self.ok, default="active")
        w.pack(side="left", padx=5, pady=5)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack()


class ManageWeightsDialog(simpledialog.Dialog):
    """Dialog to manage the available weights."""

    def __init__(self, parent, controller, refresh_callback=None):
        self.controller = controller
        self.refresh_callback = refresh_callback
        super().__init__(parent, "Gerenciar Pesos de Detecção")

    def body(self, master):
        self.listbox = ttk.Treeview(
            master, columns=("name", "is_default"), show="headings", height=5
        )
        self.listbox.heading("name", text="Nome do Peso")
        self.listbox.heading("is_default", text="Padrão")
        self.listbox.column("is_default", width=60, anchor="center")
        self.listbox.pack(padx=5, pady=5, fill="both", expand=True)

        self.populate_list()

        button_frame = ttk.Frame(master)
        button_frame.pack(pady=5)

        ttk.Button(
            button_frame, text="Definir como Padrão", command=self.set_default
        ).pack(side="left", padx=5)
        ttk.Button(
            button_frame, text="Excluir Selecionado", command=self.delete
        ).pack(side="left", padx=5)

    def populate_list(self):
        for item in self.listbox.get_children():
            self.listbox.delete(item)

        weights = self.controller.get_all_weight_names()
        default_name, _ = self.controller.weight_manager.get_default_weight()

        for name in sorted(weights):
            is_default_str = "Sim" if name == default_name else ""
            self.listbox.insert("", "end", values=(name, is_default_str))

    def get_selected_item_name(self):
        selected = self.listbox.selection()
        if not selected:
            messagebox.showwarning(
                "Nenhuma Seleção", "Por favor, selecione um peso primeiro."
            )
            return None
        return self.listbox.item(selected[0])["values"][0]

    def set_default(self):
        name = self.get_selected_item_name()
        if name:
            self.controller.weight_manager.set_default_weight(name)
            self.populate_list()
            # No longer need to update the main GUI dropdown directly

    def delete(self):
        name = self.get_selected_item_name()
        if name:
            if messagebox.askyesno(
                "Confirmar Exclusão", f"Tem certeza que deseja excluir '{name}'?"
            ):
                self.controller.delete_weight(name)
                self.populate_list()

    def destroy(self):
        # Override destroy to call the callback if it exists
        if self.refresh_callback:
            self.refresh_callback()
        super().destroy()

    def buttonbox(self):
        # Override to have only a close button
        box = ttk.Frame(self)
        w = ttk.Button(box, text="Fechar", width=10, command=self.ok, default="active")
        w.pack(side="left", padx=5, pady=5)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack()


class CreateProjectDialog(simpledialog.Dialog):
    """A custom dialog to gather all new project information."""

    def __init__(self, parent):
        self.project_path = None
        self.result = None
        super().__init__(parent, "Criar Novo Projeto")

    def body(self, master):
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

        # --- Project Name ---
        Label(master, text="Nome do Projeto:").grid(
            row=0, column=0, sticky="w", padx=5, pady=2
        )
        Entry(master, textvariable=self.project_name_var, width=40).grid(
            row=0, column=1, columnspan=2, sticky="ew", padx=5
        )

        # --- Base Path ---
        Label(master, text="Pasta do Projeto:").grid(
            row=1, column=0, sticky="w", padx=5, pady=2
        )
        self.path_entry = Entry(master, text="", width=40)
        self.path_entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=5)
        Button(master, text="Procurar...", command=self._select_path).grid(
            row=1, column=3, padx=5
        )

        # --- Calibration ---
        Label(master, text="Número de Aquários:").grid(
            row=2, column=0, sticky="w", padx=5, pady=2
        )
        Entry(master, textvariable=self.num_aquariums_var, width=10).grid(
            row=2, column=1, sticky="w", padx=5
        )

        Label(master, text="Animais por Aquário:").grid(
            row=3, column=0, sticky="w", padx=5, pady=2
        )
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

        # --- Project Type & Videos ---
        Label(master, text="Tipo de Projeto:").grid(
            row=6, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Radiobutton(
            master,
            text="Pré-gravado",
            variable=self.project_type_var,
            value="pre-recorded",
            command=self._update_project_type_options,
        ).grid(row=6, column=1, sticky="w", padx=5)
        ttk.Radiobutton(
            master,
            text="Ao Vivo",
            variable=self.project_type_var,
            value="live",
            command=self._update_project_type_options,
        ).grid(row=6, column=2, sticky="w", padx=5)

        self.video_button = Button(
            master, text="Selecionar Vídeos...", command=self._select_videos
        )
        self.video_button.grid(row=7, column=0, padx=5, pady=5)
        Label(master, textvariable=self.video_list_var, wraplength=300).grid(
            row=7, column=1, columnspan=3, sticky="w", padx=5
        )

        # --- Live Recording Options ---
        self.live_options_frame = Frame(master)
        self.live_options_frame.grid(
            row=8, column=0, columnspan=4, sticky="ew", padx=5
        )
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
        self.live_project_frame.grid(
            row=9, column=0, columnspan=4, sticky="ew", padx=5, pady=5
        )
        # Widgets inside live_project_frame
        ttk.Label(self.live_project_frame, text="Total de Dias do Experimento:").grid(
            row=0, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(
            self.live_project_frame, textvariable=self.total_days_var, width=10
        ).grid(row=0, column=1, sticky="w", padx=5)
        ttk.Label(self.live_project_frame, text="Cobaias por Grupo:").grid(
            row=1, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(
            self.live_project_frame, textvariable=self.subjects_per_group_var, width=10
        ).grid(row=1, column=1, sticky="w", padx=5)
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
        self.group_names_frame.grid(
            row=3, column=0, columnspan=4, sticky="ew", padx=5, pady=5
        )
        self.group_name_entries = []
        for i in range(6):
            row, col = divmod(i, 2)
            ttk.Label(self.group_names_frame, text=f"Grupo {i+1}:").grid(
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
        path = filedialog.askdirectory(
            title="Selecione uma Pasta Principal para o Projeto"
        )
        if path:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, path)

    def _select_videos(self):
        files = filedialog.askopenfilenames(
            title="Selecione os Arquivos de Vídeo",
            filetypes=[("Arquivos de vídeo", "*.mp4 *.avi")],
        )
        if files:
            self.video_files = files
            self.video_list_var.set(f"{len(files)} vídeo(s) selecionado(s).")
        else:
            self.video_files = []
            self.video_list_var.set("Nenhum vídeo selecionado.")

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
            self.video_button.config(state="normal")
            self.live_options_frame.grid_remove()
            self.live_project_frame.grid_remove()
        else:  # Live
            self.video_button.config(state="disabled")
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
        base_path = self.path_entry.get()
        if not base_path or not os.path.isdir(base_path):
            messagebox.showerror(
                "Erro", "Por favor, selecione uma pasta principal válida."
            )
            return 0

        project_name = self.project_name_var.get()
        if not project_name.strip():
            messagebox.showerror("Erro", "O nome do projeto não pode estar vazio.")
            return 0

        self.project_path = os.path.join(base_path, project_name)
        if os.path.exists(self.project_path) and os.listdir(self.project_path):
            messagebox.showerror(
                "Erro",
                "Uma pasta de projeto com este nome já existe e não está vazia.",
            )
            return 0

        if self.project_type_var.get() == "pre-recorded" and not self.video_files:
            messagebox.showerror(
                "Erro",
                "Por favor, selecione pelo menos um arquivo de vídeo para "
                "análise pré-gravada.",
            )
            return 0

        try:
            num_aquariums = int(self.num_aquariums_var.get())
            animals_per_aquarium = int(self.animals_per_aquarium_var.get())
            float(self.aquarium_width_var.get())
            float(self.aquarium_height_var.get())
            if num_aquariums <= 0 or animals_per_aquarium <= 0:
                raise ValueError("Os valores devem ser positivos.")
        except ValueError:
            messagebox.showerror(
                "Erro", "Os valores devem ser positivos."
            )
            return 0

        if self.project_type_var.get() == "live":
            try:
                total_days = int(self.total_days_var.get())
                subjects_per_group = int(self.subjects_per_group_var.get())
                num_groups = int(self.num_groups_var.get())
                if total_days <= 0 or subjects_per_group <= 0 or num_groups <= 0:
                    raise ValueError("Os valores devem ser positivos.")
                if not 1 <= num_groups <= 6:
                    messagebox.showerror(
                        "Erro", "O número de grupos deve ser entre 1 e 6."
                    )
                    return 0
                # Check that required group names are not empty
                for i in range(num_groups):
                    if not self.group_name_vars[i].get().strip():
                        messagebox.showerror(
                            "Erro", f"O nome do Grupo {i + 1} não pode estar vazio."
                        )
                        return 0
            except (ValueError, TypeError):
                messagebox.showerror(
                    "Erro",
                    "Os parâmetros do design experimental devem ser números "
                    "positivos válidos.",
                )
                return 0
            if self.use_timed_recording_var.get():
                try:
                    duration = float(self.recording_duration_var.get())
                    if duration <= 0:
                        raise ValueError("A duração deve ser positiva.")
                except ValueError:
                    messagebox.showerror(
                        "Erro", "A duração da gravação deve ser um número positivo."
                    )
                    return 0
            if self.use_countdown_var.get():
                try:
                    countdown = int(self.countdown_duration_var.get())
                    if countdown <= 0:
                        raise ValueError(
                            "A contagem regressiva deve ser um inteiro positivo."
                        )
                except ValueError:
                    messagebox.showerror(
                        "Erro",
                        "A duração da contagem regressiva deve ser um inteiro "
                        "positivo.",
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

        countdown_duration = 0
        if self.use_countdown_var.get():
            try:
                countdown_duration = int(self.countdown_duration_var.get())
            except ValueError:
                pass

        self.result = {
            "project_path": self.project_path,
            "project_type": self.project_type_var.get(),
            "video_files": self.video_files,
            "num_aquariums": int(self.num_aquariums_var.get()),
            "animals_per_aquarium": int(self.animals_per_aquarium_var.get()),
            "aquarium_width_cm": float(self.aquarium_width_var.get()),
            "aquarium_height_cm": float(self.aquarium_height_var.get()),
            "use_timed_recording": self.use_timed_recording_var.get(),
            "recording_duration_s": duration,
            "use_countdown": self.use_countdown_var.get(),
            "countdown_duration_s": countdown_duration,
            # Initialize new keys to None
            "experiment_days": None,
            "subjects_per_group": None,
            "num_groups": None,
            "group_names": None,
        }

        if self.project_type_var.get() == "live":
            num_groups = int(self.num_groups_var.get())
            self.result["experiment_days"] = int(self.total_days_var.get())
            self.result["subjects_per_group"] = int(
                self.subjects_per_group_var.get()
            )
            self.result["num_groups"] = num_groups
            self.result["group_names"] = [
                self.group_name_vars[i].get().strip() for i in range(num_groups)
            ]


class LiveConfigDialog(simpledialog.Dialog):
    """A dialog to configure live analysis settings (camera and Arduino)."""

    def __init__(self, parent):
        self.result = None
        self.available_cameras = {}
        self.available_ports = {}
        super().__init__(parent, "Configuração da Análise ao Vivo")

    def body(self, master):
        # --- Detect devices first ---
        self._detect_devices()

        # --- Tkinter Variables ---
        self.camera_var = StringVar()
        self.use_arduino_var = BooleanVar(value=True)
        self.arduino_port_var = StringVar()

        # --- Camera Selection ---
        Label(master, text="Selecionar Câmera:").grid(
            row=0, column=0, sticky="w", padx=5, pady=5
        )
        camera_names = list(self.available_cameras.keys())
        if not camera_names:
            camera_names = ["Nenhuma câmera encontrada"]
        self.camera_menu = OptionMenu(master, self.camera_var, *camera_names)
        self.camera_menu.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        if self.available_cameras:
            self.camera_var.set(list(self.available_cameras.keys())[0])
        else:
            self.camera_menu.config(state="disabled")

        # --- Arduino Selection ---
        self.arduino_check = Checkbutton(
            master,
            text="Usar Arduino",
            variable=self.use_arduino_var,
            command=self._toggle_arduino_menu,
        )
        self.arduino_check.grid(
            row=1, column=0, columnspan=2, sticky="w", padx=5, pady=5
        )

        Label(master, text="Porta Arduino:").grid(
            row=2, column=0, sticky="w", padx=5, pady=5
        )
        port_names = list(self.available_ports.keys())
        if not port_names:
            port_names = ["Nenhuma porta encontrada"]
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
                self.available_cameras[f"Câmera {i}"] = i
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
                "Erro",
                "Nenhuma câmera detectada. Não é possível iniciar uma sessão "
                "ao vivo.",
            )
            return 0
        if self.use_arduino_var.get() and not self.available_ports:
            messagebox.showerror(
                "Erro",
                "O Arduino está ativado, mas nenhuma porta serial foi "
                "encontrada. Por favor, verifique a conexão ou desative a "
                "opção 'Usar Arduino'.",
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
    DEFAULT_CANVAS_WIDTH = 800
    DEFAULT_CANVAS_HEIGHT = 600

    def __init__(self, root, controller):
        """
        Inicializa a ApplicationGUI.
        """
        self.root = root
        self.controller = controller
        self.root.title("Controlador Zebtrack")
        self.root.protocol("WM_DELETE_WINDOW", self.controller.on_close)

        # Debug mode para visualizar fluxo de salvamento
        self.DEBUG_ZONES = True  # Ative para debug

        # Dynamic widgets / state variables
        self.welcome_frame = None
        self.notebook = None
        self.main_controls_frame = None
        self.zone_tab_frame = None
        self.drawing_instruction_label = None
        self.current_drawing_type = None
        self.status_var = StringVar()
        self.pending_single_video_path = None
        self.pending_single_video_config = None
        self.start_single_analysis_btn = None

        # ROI Tab Widgets
        self.roi_listbox = None
        self.run_analysis_btn = None
        self.zone_prop_name_var = StringVar()
        self.zone_prop_color_var = StringVar()
        self.zone_prop_enter_cmd_var = StringVar()
        self.zone_prop_exit_cmd_var = StringVar()
        
        # ROI Inclusion Rule Variables
        self.roi_inclusion_rule_var = StringVar(value=settings.roi_inclusion_rule if settings else "bbox_intersects")
        self.roi_buffer_radius_var = StringVar(value=str(settings.roi_buffer_radius_value if settings else 0.5))
        self.roi_overlap_ratio_var = StringVar(value=str(settings.roi_min_bbox_overlap_ratio if settings else 0.10))

        # Progress + stats (created later)
        self.progress_frame: Frame | None = None
        self.progress_bar = None
        self.cancel_proc_btn: Button | None = None
        self.progress_labels: dict[str, StringVar] = {}
        self.video_label: Label | None = None

        # User options
        self.processing_interval_var = StringVar(
            value=str(settings.video_processing.processing_interval)
        )
        self.show_preview_var = BooleanVar(value=True)

        # New frame interval controls (defaults to 10 as per requirements)
        self.analysis_interval_var = StringVar(value="10")
        self.display_interval_var = StringVar(value="10")

        # Interactive arena editing state
        self.stabilization_frames_var = StringVar(value="10")
        self.interactive_polygon_item = None
        self.polygon_handles = []
        self.edited_polygon_points = []
        self._dragged_handle_index = None
        self.save_arena_btn = None
        self.discard_arena_btn = None
        self.interactive_buttons_frame = None

        self._create_welcome_frame()

    def _cleanup_single_analysis_button(self):
        """Destroys the single analysis button if it exists."""
        if (
            hasattr(self, "start_single_analysis_btn")
            and self.start_single_analysis_btn is not None
        ):
            if self.start_single_analysis_btn.winfo_exists():
                self.start_single_analysis_btn.destroy()
            self.start_single_analysis_btn = None

    def _create_welcome_frame(self):
        """Creates the initial UI for project selection and model configuration."""
        self._cleanup_single_analysis_button()
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
            text="Bem-vindo ao Controlador Zebtrack",
            font=("Helvetica", 16),
        ).pack(pady=(0, 15))

        # --- Project Actions ---
        project_actions_frame = ttk.LabelFrame(
            self.welcome_frame, text="Ações do Projeto", padding=10
        )
        project_actions_frame.pack(fill="x", pady=10, expand=True)

        ttk.Button(
            project_actions_frame,
            text="Calibrar Pesos e Detecções",
            command=self._open_calibration_window,  # Novo método handler
        ).pack(fill="x", padx=10, pady=5)
        ttk.Button(
            project_actions_frame,
            text="Analisar Vídeo Único",
            command=self._on_analyze_single_video_clicked,
        ).pack(fill="x", padx=10, pady=5)
        ttk.Button(
            project_actions_frame,
            text="Criar Novo Projeto",
            command=self._create_project_workflow,
        ).pack(fill="x", padx=10, pady=5)
        ttk.Button(
            project_actions_frame,
            text="Abrir Projeto Existente",
            command=self._open_project_workflow,
        ).pack(fill="x", padx=10, pady=5)

    def _open_calibration_window(self):
        CalibrationDialog(self.root, self.controller)

    def _create_main_control_frame(self):
        """Creates the main UI with tabs for controlling the app."""
        if self.welcome_frame:
            self.welcome_frame.destroy()
        self.root.geometry("")  # Let it resize

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both", padx=5, pady=5)

        # Create the tabs
        self._create_main_controls_tab()
        if self.controller.project_manager.get_project_type() == "live":
            self._create_progress_grid_tab()
        self._create_roi_analysis_tab()
        self._create_reports_tab()

        # Status frame below the notebook
        project_type_str = self.controller.project_manager.get_project_type()
        if project_type_str == "live":
            project_type_display = "Ao Vivo"
        elif project_type_str == "pre-recorded":
            project_type_display = "Pré-gravado"
        else:
            project_type_display = project_type_str

        status_text = (
            f"Projeto: {self.controller.project_manager.get_project_name()} "
            f"({project_type_display})"
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
        self.notebook.add(self.main_controls_frame, text="Controle Principal")

        project_type = self.controller.project_manager.get_project_type()

        if project_type == "live":
            self.start_rec_btn = Button(
                self.main_controls_frame,
                text="Iniciar Gravação",
                command=self.controller.start_recording,
            )
            self.start_rec_btn.pack(side="left", padx=5)
            self.stop_rec_btn = Button(
                self.main_controls_frame,
                text="Parar Gravação",
                command=self.controller.stop_recording,
                state="disabled",
            )
            self.stop_rec_btn.pack(side="left", padx=5)
        elif project_type == "pre-recorded":
            # The main action in a pre-recorded project is to add more videos
            ttk.Button(
                self.main_controls_frame,
                text="Adicionar e Processar Novos Vídeos/Pastas...",
                command=self.controller.start_project_processing_workflow,
            ).pack(pady=10, padx=10, fill="x")

            # Project-wide interval settings
            intervals_frame = ttk.LabelFrame(
                self.main_controls_frame, text="Intervalos de Processamento", padding=10
            )
            intervals_frame.pack(fill="x", pady=10, padx=10)

            # Analysis interval
            analysis_label_frame = ttk.Frame(intervals_frame)
            analysis_label_frame.pack(fill="x", pady=2)
            ttk.Label(analysis_label_frame, text="Intervalo de Análise (frames):").pack(side="left")
            ttk.Entry(
                analysis_label_frame, textvariable=self.analysis_interval_var, width=10
            ).pack(side="right")

            # Display interval
            display_label_frame = ttk.Frame(intervals_frame)
            display_label_frame.pack(fill="x", pady=2)
            ttk.Label(display_label_frame, text="Intervalo de Exibição (frames):").pack(side="left")
            ttk.Entry(
                display_label_frame, textvariable=self.display_interval_var, width=10
            ).pack(side="right")

        Button(
            self.main_controls_frame,
            text="Fechar Projeto",
            command=self.controller.close_project,
        ).pack(side="left", padx=5)

    def _create_roi_analysis_tab(self):
        """Creates the tab for ROI and detection zone configuration."""
        # This tab is now for defining detection zones (main polygon, ROI polygons)
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

        # --- Single Analysis Options ---
        self.single_analysis_options_frame = ttk.LabelFrame(
            self.zone_controls_frame,
            text="Opções de Análise de Vídeo Único",
            padding=10,
        )
        # This frame is packed on demand by setup_zone_configuration_for_video

        # ROI options
        self.roi_choice_var = StringVar(value="none")
        ttk.Label(
            self.single_analysis_options_frame, text="Opções de ROI:"
        ).pack(anchor="w")
        ttk.Radiobutton(
            self.single_analysis_options_frame, text="Não usar ROIs",
            variable=self.roi_choice_var, value="none"
        ).pack(anchor="w", padx=10)
        ttk.Radiobutton(
            self.single_analysis_options_frame, text="Desenhar ROIs manualmente",
            variable=self.roi_choice_var, value="manual"
        ).pack(anchor="w", padx=10)
        ttk.Radiobutton(
            self.single_analysis_options_frame, text="Usar ROIs de template",
            variable=self.roi_choice_var, value="template"
        ).pack(anchor="w", padx=10)

        # Frame intervals for analysis and display
        ttk.Label(
            self.single_analysis_options_frame, text="Intervalo de Análise (frames):"
        ).pack(anchor="w", pady=(10, 0))
        ttk.Entry(
            self.single_analysis_options_frame,
            textvariable=self.analysis_interval_var,
            width=10,
        ).pack(anchor="w", padx=10)

        ttk.Label(
            self.single_analysis_options_frame, text="Intervalo de Exibição (frames):"
        ).pack(anchor="w", pady=(5, 0))
        ttk.Entry(
            self.single_analysis_options_frame,
            textvariable=self.display_interval_var,
            width=10,
        ).pack(anchor="w", padx=10)

        # Button for automatic detection
        ttk.Button(
            actions_frame,
            text="Detectar Aquário (Auto)",
            command=self._on_auto_detect_clicked,
        ).pack(fill="x", pady=2)

        # New Entry for stabilization frames
        stabilization_frame = ttk.Frame(actions_frame)
        ttk.Label(stabilization_frame, text="Frames para Análise:").pack(
            side="left", padx=(0, 5)
        )
        ttk.Entry(
            stabilization_frame, textvariable=self.stabilization_frames_var, width=5
        ).pack(side="left")
        stabilization_frame.pack(fill="x", pady=2, anchor="w")

        # Manual drawing buttons
        ttk.Button(
            actions_frame,
            text="Desenhar Polígono Principal",
            command=self._start_main_arena_drawing,
        ).pack(fill="x", pady=2)
        ttk.Button(
            actions_frame,
            text="Desenhar Área de Interesse",
            command=self._start_roi_drawing,
        ).pack(fill="x", pady=2)

        # Zone validation button
        ttk.Button(
            actions_frame,
            text="Validar Configuração",
            command=self._validate_zone_configuration,
        ).pack(fill="x", pady=2)

        # --- Zone List ---
        zone_list_frame = ttk.LabelFrame(
            self.zone_controls_frame, text="Zonas Definidas", padding=10
        )
        zone_list_frame.pack(fill="both", expand=True, pady=5)

        self.zone_listbox = ttk.Treeview(
            zone_list_frame, columns=("name", "type", "color"), show="headings"
        )
        self.zone_listbox.heading("name", text="Nome")
        self.zone_listbox.heading("type", text="Tipo")
        self.zone_listbox.heading("color", text="Cor")
        self.zone_listbox.column("type", width=80)
        self.zone_listbox.column("color", width=60)
        self.zone_listbox.pack(side="left", fill="both", expand=True)

        # Scrollbar for the listbox
        scrollbar = ttk.Scrollbar(
            zone_list_frame, orient="vertical", command=self.zone_listbox.yview
        )
        self.zone_listbox.configure(yscrollcommand=scrollbar.set)
        self.zone_listbox.bind("<<TreeviewSelect>>", self._on_zone_select)

        # Menu de contexto para ROIs
        self.roi_context_menu = None
        self._create_roi_context_menu()

        # Bind click direito na listbox
        self.zone_listbox.bind("<Button-3>", self._on_zone_right_click)

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

        # --- ROI Inclusion Rule Panel ---
        self.roi_inclusion_frame = ttk.LabelFrame(
            self.zone_controls_frame, text="Regra de Inclusão em ROI", padding=10
        )
        self.roi_inclusion_frame.pack(fill="x", pady=5)
        
        # Rule selection combobox
        rule_frame = ttk.Frame(self.roi_inclusion_frame)
        rule_frame.pack(fill="x", pady=2)
        ttk.Label(rule_frame, text="Regra:").pack(side="left", padx=(0, 5))
        self.roi_rule_combo = ttk.Combobox(
            rule_frame,
            textvariable=self.roi_inclusion_rule_var,
            values=["centroid_in", "centroid_in_on_buffered_roi", "bbox_intersects", "seg_overlap"],
            state="readonly",
            width=30
        )
        self.roi_rule_combo.pack(side="left", fill="x", expand=True)
        self.roi_rule_combo.bind("<<ComboboxSelected>>", self._on_roi_rule_change)
        
        # Parameter fields (shown/hidden based on rule)
        self.radius_frame = ttk.Frame(self.roi_inclusion_frame)
        ttk.Label(self.radius_frame, text="Raio de buffer (r):").pack(side="left", padx=(0, 5))
        self.radius_entry = ttk.Entry(self.radius_frame, textvariable=self.roi_buffer_radius_var, width=10)
        self.radius_entry.pack(side="left", padx=(0, 10))
        ttk.Label(self.radius_frame, text="Usado para dilatar a ROI. Interpretado em cm quando houver calibração (px/cm); caso contrário, em pixels.", font=("TkDefaultFont", 8)).pack(side="left")
        
        self.overlap_frame = ttk.Frame(self.roi_inclusion_frame)
        ttk.Label(self.overlap_frame, text="Mín. fração de sobreposição (0–1):").pack(side="left", padx=(0, 5))
        self.overlap_entry = ttk.Entry(self.overlap_frame, textvariable=self.roi_overlap_ratio_var, width=10)
        self.overlap_entry.pack(side="left", padx=(0, 10))
        self.overlap_help_label = ttk.Label(self.overlap_frame, text="A detecção é considerada dentro da ROI quando a fração de área do bbox contida na ROI atinge este valor.", font=("TkDefaultFont", 8))
        self.overlap_help_label.pack(side="left")
        
        # Help text that changes based on rule
        self.rule_help_label = ttk.Label(
            self.roi_inclusion_frame, 
            text="",
            font=("TkDefaultFont", 8),
            wraplength=400,
            justify="left"
        )
        self.rule_help_label.pack(fill="x", pady=(5, 0))
        
        # Save settings button
        save_settings_frame = ttk.Frame(self.roi_inclusion_frame)
        save_settings_frame.pack(fill="x", pady=(5, 0))
        ttk.Button(
            save_settings_frame,
            text="Aplicar Configurações",
            command=self._on_apply_roi_settings
        ).pack(side="right")
        
        # Initialize display based on current rule
        self._on_roi_rule_change()

    def _on_roi_rule_change(self, event=None):
        """Handle ROI inclusion rule change and update UI accordingly."""
        rule = self.roi_inclusion_rule_var.get()
        
        # Hide all parameter frames first
        self.radius_frame.pack_forget()
        self.overlap_frame.pack_forget()
        
        # Show appropriate parameters and help text based on rule
        if rule == "centroid_in":
            help_text = "Considera dentro quando o centróide do animal está dentro do polígono da ROI. Simples e rápido; pode perder entradas parciais (ex.: cabeça entra primeiro)."
            
        elif rule == "centroid_in_on_buffered_roi":
            self.radius_frame.pack(fill="x", pady=2)
            help_text = "Igual ao centróide, porém com ROI dilatada por r para capturar entradas parciais (ex.: cabeça). r em cm se houver calibração; senão em px."
            
        elif rule == "bbox_intersects":
            self.overlap_frame.pack(fill="x", pady=2)
            self.overlap_help_label.config(text="A detecção é considerada dentro da ROI quando a fração de área do bbox contida na ROI atinge este valor.")
            help_text = "Considera dentro quando o retângulo do animal (bbox) sobrepõe a ROI ao menos pela fração definida. Captura entradas parciais; pode superestimar em bordas."
            
        elif rule == "seg_overlap":
            self.overlap_frame.pack(fill="x", pady=2)
            self.overlap_help_label.config(text="Requer dados de máscara. Se não houver, selecione outra regra.")
            help_text = "Considera dentro com base na sobreposição da máscara do animal com a ROI. Requer segmentação; mais preciso e mais custoso."
            
        else:
            help_text = ""
            
        self.rule_help_label.config(text=help_text)

    def _on_apply_roi_settings(self):
        """Apply ROI inclusion rule settings to the global settings."""
        from zebtrack import settings
        
        try:
            # Validate and convert parameters
            buffer_radius = float(self.roi_buffer_radius_var.get())
            overlap_ratio = float(self.roi_overlap_ratio_var.get())
            
            # Validate ranges
            if buffer_radius < 0:
                raise ValueError("Raio de buffer deve ser >= 0")
            if not (0 <= overlap_ratio <= 1):
                raise ValueError("Fração de sobreposição deve estar entre 0 e 1")
            
            # Update settings if available
            if settings:
                settings.roi_inclusion_rule = self.roi_inclusion_rule_var.get()
                settings.roi_buffer_radius_value = buffer_radius
                settings.roi_min_bbox_overlap_ratio = overlap_ratio
                
                # Save to project if available
                if self.controller.project_manager.project_path:
                    self.controller.project_manager._save_settings_snapshot()
                
                self.show_info(
                    "Sucesso",
                    f"Configurações de ROI aplicadas:\n"
                    f"Regra: {settings.roi_inclusion_rule}\n"
                    f"Raio buffer: {settings.roi_buffer_radius_value}\n"
                    f"Sobreposição mínima: {settings.roi_min_bbox_overlap_ratio}"
                )
            else:
                self.show_warning("Aviso", "Settings não disponível. Configurações não foram salvas.")
                
        except ValueError as e:
            self.show_error("Erro de Validação", str(e))
        except Exception as e:
            self.show_error("Erro", f"Erro ao aplicar configurações: {str(e)}")

        # --- Interactive Buttons (initially hidden) ---
        self.interactive_buttons_frame = ttk.Frame(self.zone_controls_frame)
        self.save_arena_btn = ttk.Button(
            self.interactive_buttons_frame,
            text="✅ Salvar Arena",
            command=self._on_save_arena,
        )
        self.save_arena_btn.pack(side="left", fill="x", expand=True, padx=2)
        self.discard_arena_btn = ttk.Button(
            self.interactive_buttons_frame,
            text="❌ Descartar",
            command=self._on_discard_arena,
        )
        self.discard_arena_btn.pack(side="left", fill="x", expand=True, padx=2)
        # This frame is packed later when needed

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

    def setup_interactive_polygon(self, polygon: np.ndarray):
        """Draws a suggested polygon that the user can interactively edit."""
        # Garante que há frame no canvas antes de desenhar
        if self._canvas_bg_image is None:
            if not self.load_video_frame_to_canvas():
                self.show_error(
                    "Erro",
                    "Não foi possível carregar um frame para mostrar o polígono detectado."
                )
                return

        self._clear_interactive_polygon()  # Clear any previous one
        self.edited_polygon_points = [list(p) for p in polygon]

        self._draw_interactive_polygon()

        # Show the save/discard buttons
        if self.interactive_buttons_frame:
            self.interactive_buttons_frame.pack(
                after=self.zone_properties_frame, fill="x", padx=5, pady=5
            )

        self.set_status(
            "Ajuste o polígono arrastando os vértices. Salve ou descarte."
        )

    def _draw_interactive_polygon(self):
        """Helper to (re)draw the polygon and its handles based on current points."""
        # Clear previous drawings
        self.roi_canvas.delete("interactive_polygon", "handle")

        # Draw the polygon itself
        flat_points = [coord for point in self.edited_polygon_points for coord in point]
        self.interactive_polygon_item = self.roi_canvas.create_polygon(
            flat_points,
            fill="",
            outline="yellow",
            width=2,
            tags="interactive_polygon",
        )

        # Draw the handles
        self.polygon_handles = []
        for i, (x, y) in enumerate(self.edited_polygon_points):
            handle = self.roi_canvas.create_rectangle(
                x - 4,
                y - 4,
                x + 4,
                y + 4,
                fill="darkgoldenrod",
                outline="yellow",
                tags=("handle", f"handle-{i}"),
            )
            self.polygon_handles.append(handle)
            # Bind events to each handle
            self.roi_canvas.tag_bind(
                handle, "<ButtonPress-1>", lambda e, i=i: self._on_handle_press(e, i)
            )
            self.roi_canvas.tag_bind(handle, "<B1-Motion>", self._on_handle_drag)
            self.roi_canvas.tag_bind(
                handle, "<ButtonRelease-1>", self._on_handle_release
            )

    def _on_handle_press(self, event, handle_index):
        """Records which handle is being dragged."""
        self._dragged_handle_index = handle_index

    def _on_handle_drag(self, event):
        """Updates the polygon point and redraws as the handle is dragged."""
        if self._dragged_handle_index is None:
            return

        # Update the point coordinates
        self.edited_polygon_points[self._dragged_handle_index] = [event.x, event.y]

        # Redraw the entire interactive polygon and its handles
        self._draw_interactive_polygon()

    def _on_handle_release(self, event):
        """Finalizes the drag operation."""
        self._dragged_handle_index = None

    def _on_save_arena(self):
        """Saves the edited polygon and makes it static."""
        self.controller.save_manual_arena(self.edited_polygon_points)
        self.set_status("Arena salva com sucesso.")

        # Make the polygon static (non-interactive)
        self.roi_canvas.delete("interactive_polygon", "handle")
        flat_points = [coord for point in self.edited_polygon_points for coord in point]
        self.roi_canvas.create_polygon(
            flat_points,
            fill="",
            outline="cyan",  # Change color to indicate it's saved
            width=2,
            tags="main_arena",
        )
        self._clear_interactive_polygon()

    def _on_discard_arena(self):
        """Discards the interactive polygon."""
        self._clear_interactive_polygon()
        self.set_status("Sugestão de arena descartada.")

    def _clear_interactive_polygon(self):
        """Clears all interactive elements from the canvas and hides buttons."""
        self.roi_canvas.delete("interactive_polygon", "handle", "suggested_polygon")
        try:
            if (
                self.interactive_buttons_frame
                and self.interactive_buttons_frame.winfo_exists()
            ):
                self.interactive_buttons_frame.pack_forget()
        except Exception:
            # This can fail if the root window is already being destroyed.
            # It's safe to ignore in that case.
            pass

        self.interactive_polygon_item = None
        self.polygon_handles = []
        self.edited_polygon_points = []
        self._dragged_handle_index = None

    def display_roi_video_frame(self, video_path):
        """
        Loads the first frame of a video, displays it on the canvas,
        and adjusts the window size.
        """
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                self.show_error("Erro", "Não foi possível abrir o vídeo.")
                return
            ret, frame = cap.read()
            cap.release()
            if not ret:
                self.show_error("Erro", "Não foi possível ler um frame do vídeo.")
                return

            # Logic to display on the canvas
            h, w, _ = frame.shape
            # Adjust the main window to a proportional size
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            win_w = min(int(screen_w * 0.8), w + 350) # Add space for controls
            win_h = min(int(screen_h * 0.8), h + 100)
            self.root.geometry(f"{win_w}x{win_h}")
            self.root.update_idletasks()

            # Convert and display the image
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            self._canvas_bg_image = ImageTk.PhotoImage(img)
            self.roi_canvas.config(width=w, height=h)
            self.roi_canvas.create_image(0, 0, anchor="nw", image=self._canvas_bg_image, tags="background_image")

        except Exception as e:
            self.show_error("Erro ao Exibir Frame", str(e))

    def load_video_frame_to_canvas(self, video_path: str = None, frame_number: int = 0):
        """Carrega um frame do vídeo no canvas"""
        if video_path is None:
            # Tenta usar o vídeo pendente ou do projeto
            if hasattr(self, 'pending_single_video_path') and self.pending_single_video_path:
                video_path = self.pending_single_video_path
            elif self.controller.project_manager.project_path:
                videos = self.controller.project_manager.get_all_videos()
                if videos:
                    video_path = videos[0].get('path')

        if not video_path or not os.path.exists(video_path):
            log.error("gui.load_frame.no_video")
            return False

        try:
            cap = cv2.VideoCapture(video_path)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = cap.read()
            cap.release()

            if not ret:
                return False

            # Converte e redimensiona
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(frame_rgb)

            # Ajusta ao canvas
            canvas_width = self.roi_canvas.winfo_width() or 800
            canvas_height = self.roi_canvas.winfo_height() or 600

            # Calcula nova escala mantendo aspecto
            img_w, img_h = image.size
            scale = min(canvas_width / img_w, canvas_height / img_h)
            new_width = int(img_w * scale)
            new_height = int(img_h * scale)

            # Redimensiona a imagem
            image = image.resize((new_width, new_height), Image.LANCZOS)

            # Atualiza o tamanho do canvas para corresponder à imagem
            self.roi_canvas.config(width=new_width, height=new_height)

            self._canvas_bg_image = ImageTk.PhotoImage(image)
            self.roi_canvas.delete("all")
            self.roi_canvas.create_image(0, 0, anchor="nw", image=self._canvas_bg_image, tags="background_image")

            log.info("gui.canvas.frame_loaded", video=video_path)
            return True

        except Exception as e:
            log.error("gui.load_frame.error", error=str(e))
            return False

    def _create_reports_tab(self):
        """Creates the tab for viewing processed data and generating reports."""
        reports_tab_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(reports_tab_frame, text="Relatórios")

        # --- Video List (Master View) ---
        list_frame = ttk.LabelFrame(
            reports_tab_frame, text="Vídeos Processados", padding=10
        )
        list_frame.pack(fill="both", expand=True, pady=5)

        self.reports_tree = ttk.Treeview(
            list_frame, columns=("name", "batch", "status"), show="headings"
        )
        self.reports_tree.heading("name", text="Nome do Vídeo")
        self.reports_tree.heading("batch", text="Lote")
        self.reports_tree.heading("status", text="Status")
        self.reports_tree.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.reports_tree.yview
        )
        self.reports_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        self.reports_tree.bind("<<TreeviewSelect>>", self._on_report_item_select)

        # --- Actions Panel ---
        actions_frame = ttk.LabelFrame(reports_tab_frame, text="Ações", padding=10)
        actions_frame.pack(fill="x", pady=5)

        self.generate_partial_report_btn = ttk.Button(
            actions_frame,
            text="Gerar Relatório para Selecionados",
            command=self._generate_partial_report,
            state="disabled",
        )
        self.generate_partial_report_btn.pack(side="left", padx=10)

        self.generate_unified_report_btn = ttk.Button(
            actions_frame,
            text="Gerar Relatório Unificado (Todos)",
            command=self._generate_unified_report,
        )
        self.generate_unified_report_btn.pack(side="left", padx=10)

    def update_reports_tree(self):
        """Populates the reports Treeview with processed videos from the project."""
        for item in self.reports_tree.get_children():
            self.reports_tree.delete(item)

        if not self.controller.project_manager.project_path:
            return

        batches = self.controller.project_manager.project_data.get("batches", [])
        for i, batch in enumerate(batches):
            batch_ts = batch.get("timestamp", f"Lote {i+1}")
            # Insert parent item for the batch
            batch_id = self.reports_tree.insert(
                "", "end", text=batch_ts, open=True
            )
            for video in batch.get("videos", []):
                video_name = os.path.basename(video.get("path", "Vídeo Desconhecido"))
                self.reports_tree.insert(
                    batch_id,
                    "end",
                    values=(
                        video_name,
                        batch_ts,
                        video.get("status", "N/A"),
                    ),
                    # Store the full video info in the item using tags
                    tags=(video.get("path"),)
                )

    def _on_report_item_select(self, event=None):
        """Enables or disables the partial report button based on selection."""
        if self.reports_tree.selection():
            self.generate_partial_report_btn.config(state="normal")
        else:
            self.generate_partial_report_btn.config(state="disabled")

    def _generate_partial_report(self):
        """
        Gathers selected videos and tells the controller to generate a partial report.
        """
        selected_items = self.reports_tree.selection()
        if not selected_items:
            return

        selected_videos = []
        all_videos = self.controller.project_manager.get_all_videos()

        for item_id in selected_items:
            # The video path is stored as the first tag
            if not self.reports_tree.exists(item_id):
                continue
            item_tags = self.reports_tree.item(item_id)["tags"]
            if not item_tags:
                continue
            video_path = item_tags[0]
            for video_data in all_videos:
                if video_data["path"] == video_path:
                    selected_videos.append(video_data)
                    break

        if selected_videos:
            self.controller.generate_report(selected_videos, report_type="partial")

    def _generate_unified_report(self):
        """Tells the controller to generate a unified report of all project videos."""
        all_videos = self.controller.project_manager.get_all_videos()
        if not all_videos:
            self.show_warning(
                "Sem Dados",
                "Não há vídeos processados neste projeto para gerar um relatório.",
            )
            return
        self.controller.generate_report(all_videos, report_type="unified")

    def _start_main_arena_drawing(self):
        """Starts drawing the main arena polygon."""
        if self.DEBUG_ZONES:
            print("\n=== DEBUG BOTÃO ARENA ===")
            print("1. Definindo current_drawing_type = 'arena'")

        self.current_drawing_type = "arena"

        if self.DEBUG_ZONES:
            print("2. Chamando _start_polygon_drawing()")

        self._start_polygon_drawing()

    def _start_roi_drawing(self):
        """Starts drawing an ROI polygon, checking if an arena exists first."""
        main_arena = self.controller.project_manager.get_zone_data().polygon
        if not main_arena:
            self.show_error(
                "Erro",
                "Por favor, defina o 'Polígono Principal' primeiro antes de "
                "adicionar Áreas de Interesse.",
            )
            return
        self.current_drawing_type = "roi"
        self._start_polygon_drawing()

    def _validate_zone_configuration(self):
        """Validates the current zone configuration and shows detailed feedback."""
        is_valid, summary, recommendations = self.controller.validate_zone_configuration_comprehensive()

        if is_valid:
            title = "✅ Configuração Validada"
        else:
            title = "⚠️ Problemas na Configuração"

        self.show_info(title, summary)

    def _start_polygon_drawing(self):
        """Activates polygon drawing mode."""
        if self.DEBUG_ZONES:
            print("3. _start_polygon_drawing iniciado")
            print(f"4. current_drawing_type antes de _stop_drawing: {self.current_drawing_type}")

        # Garante que há frame no canvas
        if self._canvas_bg_image is None:
            self.set_status("Carregando frame para desenho...")
            if not self.load_video_frame_to_canvas():
                self.show_error(
                    "Erro",
                    "Não foi possível carregar um frame. "
                    "Por favor, carregue um vídeo ou use 'Detectar Aquário (Auto)' primeiro."
                )
                return False

        # Preserve drawing type before cleaning
        preserved_drawing_type = self.current_drawing_type
        self._stop_drawing()  # Ensure clean state
        self.current_drawing_type = preserved_drawing_type  # Restore

        if self.DEBUG_ZONES:
            print(f"5. current_drawing_type após _stop_drawing: {self.current_drawing_type}")
        self.drawing_mode = "polygon"
        self.current_polygon_points = []
        self.roi_canvas.config(cursor="crosshair")
        self.roi_canvas.bind("<Button-1>", self._on_canvas_click)
        self.roi_canvas.bind("<Double-Button-1>", self._on_canvas_double_click)
        self.roi_canvas.bind("<Motion>", self._on_canvas_motion)

        # Add a persistent instruction label
        if not self.drawing_instruction_label:
            self.drawing_instruction_label = ttk.Label(
                self.zone_controls_frame,
                text="Clique para adicionar pontos.\nClique duplo para finalizar.",
                justify="center",
                relief="solid",
                padding=5,
            )
            self.drawing_instruction_label.pack(pady=5, before=self.zone_listbox.master)

        self.set_status(
            "Modo de Desenho (Polígono): Clique para adicionar pontos, clique "
            "duplo para finalizar."
        )

    def _stop_drawing(self):
        """Deactivates any drawing mode and unbinds all associated events."""
        # Destroy the instruction label if it exists
        if self.drawing_instruction_label:
            self.drawing_instruction_label.destroy()
            self.drawing_instruction_label = None

        self.drawing_mode = None
        self.current_drawing_type = None
        self.roi_canvas.config(cursor="")
        # Unbind all possible drawing events
        self.roi_canvas.unbind("<Button-1>")
        self.roi_canvas.unbind("<Double-Button-1>")
        self.roi_canvas.unbind("<Motion>")
        self.roi_canvas.unbind("<ButtonPress-1>")
        self.roi_canvas.unbind("<B1-Motion>")
        self.roi_canvas.unbind("<ButtonRelease-1>")

        self.roi_canvas.delete("elastic_line")
        self.roi_canvas.delete("drawing_aid") # Deletes both vertices and fixed lines
        self.set_status("Pronto.")

    def _on_canvas_click(self, event):
        """Handles single clicks on the canvas during polygon drawing."""
        if self.drawing_mode != "polygon":
            return

        # If drawing an ROI, check if the point is inside the main arena
        if self.current_drawing_type == "roi":
            main_arena_poly = self.controller.project_manager.get_zone_data().polygon
            if cv2.pointPolygonTest(
                np.array(main_arena_poly), (event.x, event.y), False
            ) < 0:
                self.show_warning(
                    "Ponto Inválido",
                    "As Áreas de Interesse devem ser desenhadas dentro do "
                    "Polígono Principal.",
                )
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
            tags=("temp_vertex", "drawing_aid"),
        )
        # Draw the fixed line segment if it's not the first point
        if len(self.current_polygon_points) > 1:
            p1 = self.current_polygon_points[-2]
            p2 = self.current_polygon_points[-1]
            self.roi_canvas.create_line(
                p1[0], p1[1], p2[0], p2[1], fill="cyan", width=2, tags="drawing_aid"
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
        """Finaliza o desenho do polígono e o envia para o controlador."""
        if self.DEBUG_ZONES:
            print("\n=== DEBUG ZONE SAVE ===")
            print(f"1. Pontos a salvar: {len(self.current_polygon_points) if self.current_polygon_points else 0}")
            print(f"2. Tipo: {self.current_drawing_type}")
            print(f"3. Modo de desenho: {self.drawing_mode}")

        # Fix: Auto-detect drawing type if not set (for single video workflow)
        if self.current_drawing_type is None and self.drawing_mode == "polygon":
            # If no main arena exists, assume we're drawing it
            zone_data = self.controller.project_manager.get_zone_data()
            if not zone_data.polygon:
                self.current_drawing_type = "arena"
                if self.DEBUG_ZONES:
                    print("3.1. Auto-detectado como arena (não existe polygon principal)")
            else:
                self.current_drawing_type = "roi"
                if self.DEBUG_ZONES:
                    print("3.1. Auto-detectado como ROI (polygon principal já existe)")

        if self.drawing_mode != "polygon" or len(self.current_polygon_points) < 3:
            if self.current_polygon_points:
                self.show_warning(
                    "Polígono Incompleto",
                    f"Um polígono precisa de pelo menos 3 pontos. Você tem {len(self.current_polygon_points)} pontos."
                )
            self._stop_drawing()
            return

        try:
            # Limpa elementos temporários de desenho ANTES de salvar
            self.roi_canvas.delete("elastic_line")
            self.roi_canvas.delete("drawing_aid")

            if self.current_drawing_type == "arena":
                if self.DEBUG_ZONES:
                    print("4. Iniciando salvamento da arena...")

                self.set_status("Salvando arena principal...")

                # Salva o polígono no projeto
                if self.DEBUG_ZONES:
                    print("5. Chamando controller.set_main_arena_polygon...")
                success = self.controller.set_main_arena_polygon(self.current_polygon_points)

                if self.DEBUG_ZONES:
                    print(f"6. Resultado do salvamento: {success}")

                if success:
                    # Agora redesenha tudo do zero com os dados salvos
                    # Não chame _stop_drawing() ainda, pois ele limpa o canvas
                    self.drawing_mode = None
                    self.current_drawing_type = None
                    self.roi_canvas.config(cursor="")

                    # Unbind eventos
                    self.roi_canvas.unbind("<Button-1>")
                    self.roi_canvas.unbind("<Double-Button-1>")
                    self.roi_canvas.unbind("<Motion>")

                    # Limpa label de instrução
                    if self.drawing_instruction_label:
                        self.drawing_instruction_label.destroy()
                        self.drawing_instruction_label = None

                    # Força redesenho com dados salvos
                    if self.DEBUG_ZONES:
                        print("7. Iniciando redesenho das zonas...")
                    self.redraw_zones_from_project_data()
                    self.update_zone_listbox()

                    self.set_status("✓ Arena principal definida com sucesso!")
                    self.show_info(
                        "Sucesso",
                        f"Arena principal criada com {len(self.current_polygon_points)} pontos."
                    )
                else:
                    self.set_status("❌ Erro ao salvar arena principal.")
                    self.show_error(
                        "Erro",
                        "Não foi possível salvar a arena principal."
                    )
                    self._stop_drawing()

            elif self.current_drawing_type == "roi":
                roi_name = self.ask_string(
                    "Nome da ROI", "Digite um nome para esta nova Área de Interesse:"
                )
                if not roi_name:
                    self.current_polygon_points = []
                    self._stop_drawing()
                    return

                # Selecionar cor da área
                color_dialog = ColorSelectionDialog(self.root)
                if not color_dialog.result:
                    self.current_polygon_points = []
                    self._stop_drawing()
                    return

                selected_color = color_dialog.result
                roi_color = selected_color["rgb"]
                color_name = selected_color["name"]

                self.set_status(f"Salvando área de interesse '{roi_name}' ({color_name})...")
                success = self.controller.add_roi_polygon(
                    self.current_polygon_points, roi_name, roi_color
                )

                if success:
                    # Limpa o estado de desenho manualmente para ROI também
                    self.drawing_mode = None
                    self.current_drawing_type = None
                    self.roi_canvas.config(cursor="")

                    # Unbind eventos
                    self.roi_canvas.unbind("<Button-1>")
                    self.roi_canvas.unbind("<Double-Button-1>")
                    self.roi_canvas.unbind("<Motion>")

                    # Limpa label de instrução
                    if self.drawing_instruction_label:
                        self.drawing_instruction_label.destroy()
                        self.drawing_instruction_label = None

                    # Força redesenho com dados salvos
                    self.redraw_zones_from_project_data()
                    self.update_zone_listbox()

                    self.set_status(f"✓ Área de Interesse '{roi_name}' ({color_name}) adicionada com sucesso!")
                    self.show_info(
                        "Sucesso",
                        f"Área de interesse '{roi_name}' ({color_name}) criada com {len(self.current_polygon_points)} pontos."
                    )
                else:
                    self.set_status(f"❌ Erro ao salvar área de interesse '{roi_name}'.")
                    self.show_error("Erro", f"Não foi possível salvar a área de interesse '{roi_name}'.")
                    self._stop_drawing()

        except Exception as e:
            self.set_status("❌ Erro durante salvamento.")
            self.show_error("Erro", str(e))
            self._stop_drawing()

        finally:
            # Limpa pontos temporários
            self.current_polygon_points = []

    def update_zone_listbox(self):
        """Atualiza lista com indicadores visuais de cor"""
        # Limpa lista
        for item in self.zone_listbox.get_children():
            self.zone_listbox.delete(item)

        zone_data = self.controller.project_manager.get_zone_data()

        # Arena principal com emoji e cor
        if zone_data.polygon:
            arena_item = self.zone_listbox.insert(
                "", "end",
                values=("🏠 Arena Principal", "Polígono", "Ciano"),
                tags=("arena",)
            )
            # Configura cor do texto para arena
            self.zone_listbox.tag_configure("arena", foreground="darkcyan")

        # Mapear cores RGB para nomes e hex
        color_map = {
            (0, 255, 0): ("Verde", "#00AA00"),
            (0, 0, 255): ("Azul", "#0000AA"),
            (255, 0, 0): ("Vermelho", "#AA0000"),
            (255, 255, 0): ("Amarelo", "#AAAA00"),
            (255, 0, 255): ("Magenta", "#AA00AA"),
            (0, 255, 255): ("Ciano", "#00AAAA"),
        }

        # ROIs com emojis, cores e tags
        for i, name in enumerate(zone_data.roi_names):
            # Obter cor da ROI se disponível
            color_name = "Verde"
            color_hex = "#00AA00"

            if i < len(zone_data.roi_colors):
                roi_color = tuple(zone_data.roi_colors[i])
                color_info = color_map.get(roi_color, ("Verde", "#00AA00"))
                color_name = color_info[0]
                color_hex = color_info[1]

            # Insere ROI com emoji
            roi_item = self.zone_listbox.insert(
                "", "end",
                values=(f"📍 {name}", "Área de Interesse", color_name),
                tags=(f"roi_{i}",)
            )

            # Configura cor do texto para ROI
            try:
                self.zone_listbox.tag_configure(f"roi_{i}", foreground=color_hex)
            except Exception:
                pass  # Fallback silencioso se a cor não for suportada

    def redraw_zones_from_project_data(self):
        """Redesenha zonas preservando o background"""
        log.info("gui.redraw_zones.start")

        if self.DEBUG_ZONES:
            zone_data = self.controller.project_manager.get_zone_data()
            print("\n=== DEBUG REDRAW ===")
            print(f"1. Tem polygon? {bool(zone_data.polygon)}")
            if zone_data.polygon:
                print(f"2. Pontos no polygon: {len(zone_data.polygon)}")
                print(f"3. Primeiros 3 pontos: {zone_data.polygon[:3]}")
            print(f"4. Canvas items antes: {len(self.roi_canvas.find_all())}")

        # Apaga apenas elementos de zona, preserva background
        for tag in ["main_polygon", "roi_polygon", "roi_label", "roi_label_bg", "elastic_line", "drawing_aid", "temp_vertex"]:
            self.roi_canvas.delete(tag)

        # Background já deve estar presente, se não, tenta restaurar
        if self._canvas_bg_image:
            # Verifica se a imagem ainda está no canvas
            bg_items = self.roi_canvas.find_withtag("background_image")
            if not bg_items:
                self.roi_canvas.create_image(
                    0, 0,
                    anchor="nw",
                    image=self._canvas_bg_image,
                    tags="background_image"
                )
                self.roi_canvas.tag_lower("background_image")  # Envia para trás
                log.info("gui.redraw_zones.background_restored")
        else:
            log.warning("gui.redraw_zones.no_background_image")
            # Tenta carregar um frame se não há imagem de fundo
            self.load_video_frame_to_canvas()

        zone_data = self.controller.project_manager.get_zone_data()
        log.info("gui.redraw_zones.zone_data_loaded",
                 has_main_polygon=bool(zone_data.polygon),
                 roi_count=len(zone_data.roi_polygons))

        # Desenha polígono principal
        if zone_data.polygon and len(zone_data.polygon) >= 3:
            try:
                self.roi_canvas.create_polygon(
                    zone_data.polygon,
                    fill="",
                    outline="cyan",
                    width=2,
                    tags="main_polygon"
                )
                log.info("gui.main_polygon.drawn", points=len(zone_data.polygon))
            except Exception as e:
                log.error("gui.main_polygon.draw_error", error=str(e))

        # Desenha ROI polygons com melhorias visuais
        for i, polygon in enumerate(zone_data.roi_polygons):
            if len(polygon) < 3:
                continue

            # Cor da ROI
            color_tuple = zone_data.roi_colors[i] if i < len(zone_data.roi_colors) else (0, 255, 0)
            color_hex = f"#{color_tuple[0]:02x}{color_tuple[1]:02x}{color_tuple[2]:02x}"

            # Nome da ROI
            name = zone_data.roi_names[i] if i < len(zone_data.roi_names) else f"ROI_{i+1}"

            # Desenha polígono com tags específicas
            try:
                # Cria o polígono
                poly_id = self.roi_canvas.create_polygon(
                    polygon,
                    fill="",  # Sem preenchimento para manter transparência
                    outline=color_hex,
                    width=2,
                    tags=("roi_polygon", f"roi_{i}")
                )

                # Adiciona label com o nome no centro do polígono
                import numpy as np
                poly_array = np.array(polygon)
                center_x = int(poly_array[:, 0].mean())
                center_y = int(poly_array[:, 1].mean())

                # Cria fundo semi-transparente para melhor legibilidade
                self.roi_canvas.create_oval(
                    center_x - 25, center_y - 10,
                    center_x + 25, center_y + 10,
                    fill="white",
                    outline=color_hex,
                    width=1,
                    tags=("roi_label_bg", f"roi_label_bg_{i}")
                )

                # Cria o texto do nome
                self.roi_canvas.create_text(
                    center_x, center_y,
                    text=name,
                    fill=color_hex,
                    font=("Arial", 9, "bold"),
                    tags=("roi_label", f"roi_label_{i}")
                )

                log.info("gui.roi_drawn", name=name, color=color_hex, points=len(polygon))

            except Exception as e:
                log.error("gui.roi_draw_error", name=name, error=str(e), index=i)

        # Atualiza listbox
        self.update_zone_listbox()

        if self.DEBUG_ZONES:
            print(f"5. Canvas items depois: {len(self.roi_canvas.find_all())}")
            print(f"6. Items com tag 'main_polygon': {len(self.roi_canvas.find_withtag('main_polygon'))}")
            print(f"7. Items com tag 'background_image': {len(self.roi_canvas.find_withtag('background_image'))}")
            print("=== FIM DEBUG REDRAW ===\n")

        log.info("gui.redraw_zones.complete")

    def _remove_selected_roi(self):
        """Removes the ROI selected in the listbox."""
        selected_items = self.roi_listbox.selection()
        if not selected_items:
            self.show_warning(
                "Nenhuma Seleção", "Por favor, selecione uma ROI da lista para remover."
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
                "Erro", "Selecione um aquário ativo e carregue os dados primeiro."
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
            self.show_error("Erro", "Selecione um aquário ativo primeiro.")
            return

        # Get the arena polygon bounds from the controller
        arena_data = self.controller.get_arena_data(current_arena_id)
        if not arena_data or "polygon_px" not in arena_data:
            self.show_error(
                "Erro", "Não foi possível obter os dados do polígono do aquário."
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
            "Modo de Desenho (Círculo): Clique e arraste para definir o raio."
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
            "Nome da ROI",
            "Digite um nome para esta nova Região de Interesse (Círculo):",
        )
        if not roi_name:
            self._stop_drawing()
            return

        current_arena_id = self.arena_selector_var.get()
        if not current_arena_id:
            self.show_error("Erro", "Nenhum aquário ativo selecionado.")
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
        # Video preview area
        self.video_label = Label(self.progress_frame)
        self.video_label.pack(pady=3)
        # Progress bar
        self.progress_bar = ttk.Progressbar(
            self.progress_frame, orient="horizontal", length=400, mode="determinate"
        )
        self.progress_bar.pack(pady=3, fill="x", expand=True)
        # Stats container
        stats_container = Frame(self.progress_frame)
        stats_container.pack(fill="x")
        for key, label_text in [
            ("total", "Total de Frames:"),
            ("processed", "Processados:"),
            ("detected", "Frames Detectados:"),
            ("percent", "Concluído:"),
            ("elapsed", "Tempo Decorrido:"),
            ("eta", "Tempo Estimado:"),
        ]:
            f = Frame(stats_container)
            f.pack(side="left", padx=5)
            Label(f, text=label_text).pack(anchor="w")
            var = StringVar(value="-")
            Label(f, textvariable=var).pack(anchor="w")
            self.progress_labels[key] = var

        # Cancel Button
        self.cancel_proc_btn = ttk.Button(
            self.progress_frame,
            text="Cancelar Análise",
            command=self.controller.cancel_current_analysis,
        )
        self.cancel_proc_btn.pack(pady=5)
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

            # Restore analysis and display intervals
            if pm.project_data.get("analysis_interval_frames") is not None:
                try:
                    self.analysis_interval_var.set(
                        str(int(pm.project_data["analysis_interval_frames"]))
                    )
                except (ValueError, TypeError):
                    pass
            if pm.project_data.get("display_interval_frames") is not None:
                try:
                    self.display_interval_var.set(
                        str(int(pm.project_data["display_interval_frames"]))
                    )
                except (ValueError, TypeError):
                    pass

        self._create_main_control_frame()

        project_type = pm.get_project_type()
        if project_type == "live":
            # Initial rendering of the progress grid
            self.root.after(100, self._render_progress_grid)

            # Only attempt to connect if a port is configured from the dialog
            if settings.arduino.port:
                if not self.controller.arduino.connect():
                    self.show_warning(
                        "Aviso do Arduino",
                        f"Não foi possível conectar ao Arduino na porta "
                        f"{settings.arduino.port}. Executando em modo offline.",
                    )
            try:
                self.controller.camera = Camera()
                self.controller.active_frame_source = self.controller.camera
                self.controller.detector.update_scaling(
                    self.controller.camera.actual_width,
                    self.controller.camera.actual_height,
                )
            except IOError as e:
                self.show_error("Erro na Câmera", str(e))
                self._create_welcome_frame()
                return
        elif project_type == "pre-recorded":
            self.update_reports_tree()
            self.set_status(
                f"Projeto: {pm.get_project_name()} - Pronto."
            )

        if project_type == "live":
            self.controller.capture_thread = threading.Thread(
                target=self._live_frame_capture_loop, name="CaptureThread", daemon=False
            )
            self.controller.processing_thread = threading.Thread(
                target=self._live_processing_loop, name="ProcessingThread", daemon=False
            )
            self.controller.capture_thread.start()
            self.controller.processing_thread.start()

            # Auto-calibration for Live projects when no zones are defined
            self.root.after(1000, self._check_live_project_calibration)

    def _create_progress_grid_tab(self):
        """Creates the tab for viewing the experimental progress grid."""
        self.progress_grid_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.progress_grid_frame, text="Progresso do Experimento")

        # This frame will hold the actual grid of buttons, which is rendered later
        self.grid_container = ttk.Frame(self.progress_grid_frame)
        self.grid_container.pack(expand=True, fill="both")

        # Add a refresh button
        refresh_button = ttk.Button(
            self.progress_grid_frame,
            text="Atualizar Grade",
            command=self._render_progress_grid,
        )
        refresh_button.pack(side="bottom", pady=10)

    def _check_live_project_calibration(self):
        """Checks if Live project needs calibration and prompts user automatically."""
        if self.controller.project_manager.get_project_type() != "live":
            return

        zone_data = self.controller.project_manager.get_zone_data()
        if not zone_data or not zone_data.polygon:
            log.info("ui.live_calibration.auto_prompt")

            response = self.ask_ok_cancel(
                "Calibração Automática",
                "Nenhuma arena principal foi definida para este projeto ao vivo.\n\n"
                "Deseja configurar a calibração automaticamente agora?\n\n"
                "• Será aberta a aba de Configuração de Zonas\n"
                "• Você pode usar 'Detectar Aquário (Auto)' ou desenhar manualmente\n"
                "• A configuração será salva automaticamente"
            )

            if response:
                log.info("ui.live_calibration.auto_accepted")
                # Switch to zone configuration tab
                if hasattr(self, 'notebook') and hasattr(self, 'zone_tab_frame'):
                    self.notebook.select(self.zone_tab_frame)

                # Show guidance message
                self.show_info(
                    "Configuração de Arena Principal",
                    "Configure a arena principal usando:\n\n"
                    "1. 'Detectar Aquário (Auto)' - Para detecção automática\n"
                    "2. 'Desenhar Polígono Principal' - Para desenho manual\n\n"
                    "A configuração será salva automaticamente."
                )
            else:
                log.info("ui.live_calibration.auto_declined")

    def _render_progress_grid(self):
        """Clears and redraws the experimental progress grid based on project data."""
        # 1. Clear existing widgets
        for widget in self.grid_container.winfo_children():
            widget.destroy()

        # 2. Get project data from controller/project_manager
        pm = self.controller.project_manager
        if not pm or pm.get_project_type() != "live":
            return

        days = pm.project_data.get("experiment_days", 0)
        groups = pm.project_data.get("groups", [])
        subjects_per_group = pm.project_data.get("subjects_per_group", 0)

        if not all([days, groups, subjects_per_group]):
            ttk.Label(
                self.grid_container,
                text="O design experimental não está totalmente configurado.",
            ).pack()
            return

        completed_sessions = pm.get_completed_sessions()

        # 3. Create headers
        ttk.Label(
            self.grid_container, text="Dia/Grupo", font=("Helvetica", 10, "bold")
        ).grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        for j, group_name in enumerate(groups):
            ttk.Label(
                self.grid_container,
                text=group_name,
                font=("Helvetica", 10, "bold"),
                anchor="center",
            ).grid(row=0, column=j + 1, padx=5, pady=5, sticky="nsew")

        # 4. Create grid cells
        for i in range(days):
            day = i + 1
            ttk.Label(
                self.grid_container, text=f"Dia {day}", font=("Helvetica", 10, "bold")
            ).grid(row=i + 1, column=0, padx=5, pady=5, sticky="nsew")

            for j, group_name in enumerate(groups):
                completed_count = sum(
                    1
                    for (d, g, s) in completed_sessions
                    if d == day and g == group_name
                )

                status_text = f"{completed_count}/{subjects_per_group}"

                if completed_count == 0:
                    color = "#E0E0E0"  # Grey - Pending
                elif completed_count < subjects_per_group:
                    color = "#FFFACD"  # LemonChiffon - In progress
                else:
                    color = "#90EE90"  # LightGreen - Completed

                cell_btn = Button(
                    self.grid_container,
                    text=status_text,
                    background=color,
                    width=15,
                    height=3,
                    command=lambda d=day, g=group_name: self._on_grid_cell_clicked(
                        d, g
                    ),
                )
                cell_btn.grid(row=i + 1, column=j + 1, padx=2, pady=2, sticky="nsew")

        for col_index in range(len(groups) + 1):
            self.grid_container.columnconfigure(col_index, weight=1)
        for row_index in range(days + 1):
            self.grid_container.rowconfigure(row_index, weight=1)

    def _on_grid_cell_clicked(self, day, group_name):
        pm = self.controller.project_manager
        subjects_per_group = pm.project_data.get("subjects_per_group", 0)
        completed_sessions = pm.get_completed_sessions()

        completed_subjects = {
            s for (d, g, s) in completed_sessions if d == day and g == group_name
        }

        dialog = SubjectSelectionDialog(
            self.root, day, group_name, subjects_per_group, completed_subjects
        )

        if dialog.result:
            subject_id = dialog.result
            self.controller.start_recording(
                day=day, group=group_name, cobaia=str(subject_id)
            )
            self._render_progress_grid()  # Refresh grid after starting a recording

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



    def _load_new_weight_clicked(self):
        """Handles the 'Load New Weight' button click."""
        filepath = filedialog.askopenfilename(
            title="Selecione um arquivo de peso .pt",
            filetypes=[("Pesos PyTorch", "*.pt")],
        )
        if not filepath:
            return

        # Ask user what to do with the new weight
        # The 'type' option creates custom buttons
        choice = messagebox.askquestion(
            "Adicionar Peso",
            "Deseja definir este novo peso como padrão para todos os projetos?",
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
            animals_per_aquarium=dialog.result["animals_per_aquarium"],
            aquarium_width_cm=dialog.result["aquarium_width_cm"],
            aquarium_height_cm=dialog.result["aquarium_height_cm"],
        )

    def _open_project_workflow(self):
        """Handles the UI part of opening a project, then calls the controller."""
        project_path = self.ask_directory(
            title="Selecione uma Pasta de Projeto Existente"
        )
        if not project_path:
            return

        self.controller.open_project_workflow(project_path)

    def _on_analyze_single_video_clicked(self):
        """Handles the UI part of the single video workflow."""
        dialog = SingleVideoConfigDialog(self.root)
        if not dialog.result:
            return  # User cancelled

        video_path = self.ask_open_filenames(
            "Selecione um Único Arquivo de Vídeo",
            [("Arquivos de vídeo", "*.mp4 *.avi *.mov")],
        )
        if not video_path:
            return

        # Pass both config and video path to the controller
        self.controller.start_single_video_workflow(
            video_path=video_path[0],
            config=dialog.result,
        )

    def setup_zone_definition_for_single_video(self, video_path: str, config: dict):
        """Prepares and displays the zone configuration tab for a single video."""
        self.pending_single_video_path = video_path
        self.pending_single_video_config = config

        # Open the main project view if it is not already open
        if not self.notebook:
            self._create_main_control_frame()

        self.display_roi_video_frame(video_path)
        self.notebook.select(self.zone_tab_frame)

        # Add a "Start Analysis" button specific to this flow
        if not self.start_single_analysis_btn:
            self.start_single_analysis_btn = ttk.Button(
                self.zone_controls_frame, # Add to the left control panel
                text="Iniciar Análise de Vídeo Único",
                command=self._on_start_single_video_processing_clicked,
            )
            self.start_single_analysis_btn.pack(
                side="bottom", fill="x", pady=10, padx=5
            )
        self.start_single_analysis_btn.config(state="normal")

        self.show_info(
            "Configuração Necessária",
            "Defina a arena do aquário usando a detecção automática ou o "
            "desenho manual.\n\n"
            "Após definir a arena principal, clique em 'Iniciar Análise de "
            "Vídeo Único'.",
        )

    def _on_auto_detect_clicked(self):
        """Handler for the auto-detect button."""
        try:
            stabilization_frames = int(self.stabilization_frames_var.get())
            if stabilization_frames <= 0:
                self.show_warning(
                    "Entrada Inválida", "O número de frames deve ser positivo."
                )
                return
        except (ValueError, TypeError):
            self.show_warning(
                "Entrada Inválida",
                "O número de frames para análise deve ser um número inteiro.",
            )
            return

        # Clear any old interactive polygon before starting a new detection
        self._clear_interactive_polygon()

        if self.pending_single_video_path:
            # Single video flow
            self.controller.run_aquarium_detection(
                video_path=self.pending_single_video_path,
                stabilization_frames=stabilization_frames,
            )
        else:
            # Project flow
            self.controller.run_aquarium_detection(
                stabilization_frames=stabilization_frames
            )

    def _on_start_single_video_processing_clicked(self):
        """Handler for the 'Start Analysis' button in the single video flow."""
        # If the user was editing a polygon, prompt for confirmation before saving.
        if self.edited_polygon_points:
            response = messagebox.askyesnocancel(
                "Salvar Polígono?",
                "Você deseja salvar as alterações no polígono antes de iniciar a "
                "análise?\n\n"
                "Sim: Salvar e iniciar análise\n"
                "Não: Descartar alterações e iniciar análise\n"
                "Cancelar: Voltar para edição",
            )
            if response is None:
                # Cancel pressed, abort analysis
                return
            elif response:
                # Yes pressed, save polygon
                self.controller.save_manual_arena(self.edited_polygon_points)
                self._clear_interactive_polygon()
            else:
                # No pressed, discard changes
                self._clear_interactive_polygon()

        # 1. Get the zone data that the user drew
        zone_data = self.controller.project_manager.get_zone_data()
        if not zone_data.polygon:
            self.show_error(
                "Erro", "A área principal do aquário (polígono) não foi definida."
            )
            return

        # 2. Add interval settings to config and disable the button
        if self.pending_single_video_config is not None:
            try:
                analysis_interval = int(self.analysis_interval_var.get())
                display_interval = int(self.display_interval_var.get())
                self.pending_single_video_config['analysis_interval_frames'] = analysis_interval
                self.pending_single_video_config['display_interval_frames'] = display_interval
            except (ValueError, AttributeError) as e:
                log.warning("gui.single_video.intervals_parse_failed", error=str(e))
                # Use defaults
                self.pending_single_video_config['analysis_interval_frames'] = 10
                self.pending_single_video_config['display_interval_frames'] = 10

        self.start_single_analysis_btn.config(state="disabled")
        self.controller.start_single_video_processing(
            self.pending_single_video_path,
            self.pending_single_video_config,
            zone_data,
        )
        # Clear the pending state
        self.pending_single_video_path = None
        self.pending_single_video_config = None

    def _on_close(self):
        """Delegates the close action to the controller."""
        self.controller.on_close()

    def _join_threads(self):
        """Delegates thread joining to the controller."""
        self.controller.join_threads()

    def set_status(self, text):
        """Updates the UI status bar."""
        self.status_var.set(text)

    def show_progress_bar(self):
        """Shows the progress bar frame and cancel button."""
        if self.progress_frame and not self.progress_frame.winfo_viewable():
            self.progress_frame.pack(pady=5, fill="x", padx=10)
            self.progress_bar["value"] = 0
        if self.cancel_proc_btn:
            self.cancel_proc_btn.config(state="normal")

    def update_progress(self, value):
        """Updates the progress bar."""
        if self.progress_bar:
            self.progress_bar["value"] = value * 100  # Convert fraction to percentage
            self.update_idletasks()

    def update_idletasks(self):
        """Force the GUI to update, processing pending events."""
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
        """Hides the progress bar and cancel button, and resets its value."""
        if self.progress_frame and self.progress_frame.winfo_viewable():
            self.progress_frame.pack_forget()
            self.progress_bar["value"] = 0
        if self.cancel_proc_btn:
            self.cancel_proc_btn.config(state="disabled")

    def _draw_zones_on_frame(self, frame):
        """Desenha a arena e as ROIs salvas no frame de vídeo."""
        zone_data = self.controller.project_manager.get_zone_data()
        if zone_data.polygon:
            pts = np.array(zone_data.polygon, np.int32)
            pts = pts.reshape((-1, 1, 2))
            cv2.polylines(
                frame, [pts], isClosed=True, color=(0, 255, 255), thickness=2
            )  # Yellow for the main arena

        for i, polygon in enumerate(zone_data.roi_polygons):
            color = (
                zone_data.roi_colors[i]
                if i < len(zone_data.roi_colors)
                else (0, 255, 0)
            )  # Default to green
            pts = np.array(polygon, np.int32)
            pts = pts.reshape((-1, 1, 2))
            cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)
        return frame

    def display_frame(self, frame):
        """Display a video frame inside the GUI, with overlays."""
        try:
            # Desenha as zonas antes de exibir
            frame_with_zones = self._draw_zones_on_frame(frame.copy())

            # Converte e embute
            frame_rgb = cv2.cvtColor(frame_with_zones, cv2.COLOR_BGR2RGB)
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

    def ask_string(self, title, prompt, initialvalue=None):
        """Shows a dialog for string input."""
        return simpledialog.askstring(title, prompt, initialvalue=initialvalue)

    def ask_directory(self, title):
        """Shows a dialog to select a directory."""
        return filedialog.askdirectory(title=title)

    def ask_open_filenames(self, title, filetypes):
        """Shows a dialog to select one or more files."""
        return filedialog.askopenfilenames(title=title, filetypes=filetypes)

    def _create_roi_context_menu(self):
        """Cria menu de contexto para ROIs"""
        from tkinter import Menu

        self.roi_context_menu = Menu(self.root, tearoff=0)
        self.roi_context_menu.add_command(
            label="✏️ Renomear",
            command=self._rename_selected_roi
        )
        self.roi_context_menu.add_command(
            label="🎨 Mudar Cor",
            command=self._change_roi_color
        )
        self.roi_context_menu.add_separator()
        self.roi_context_menu.add_command(
            label="🗑️ Remover",
            command=self._remove_selected_roi_confirm
        )

    def _on_zone_right_click(self, event):
        """Mostra menu de contexto"""
        # Seleciona item sob o cursor
        item = self.zone_listbox.identify_row(event.y)
        if item:
            self.zone_listbox.selection_set(item)

            # Verifica se é ROI (não arena principal)
            values = self.zone_listbox.item(item)['values']
            if values and "Arena Principal" not in values[0]:
                self.roi_context_menu.post(event.x_root, event.y_root)

    def _rename_selected_roi(self):
        """Renomeia ROI selecionada"""
        selected = self.zone_listbox.selection()
        if not selected:
            return

        item = self.zone_listbox.item(selected[0])
        old_name = item['values'][0].replace("📍 ", "")

        new_name = self.ask_string(
            "Renomear ROI",
            f"Novo nome para '{old_name}':",
            initialvalue=old_name
        )

        if new_name and new_name != old_name:
            # Atualiza no projeto
            zone_data = self.controller.project_manager.get_zone_data()
            try:
                idx = zone_data.roi_names.index(old_name)
                zone_data.roi_names[idx] = new_name

                # Salva
                from dataclasses import asdict
                self.controller.project_manager.project_data["detection_zones"] = asdict(zone_data)
                self.controller.project_manager.save_project()

                # Atualiza visualização
                self.redraw_zones_from_project_data()
                self.show_info("Sucesso", f"ROI renomeada para '{new_name}'")

            except ValueError:
                self.show_error("Erro", "ROI não encontrada")

    def _change_roi_color(self):
        """Muda cor da ROI selecionada"""
        selected = self.zone_listbox.selection()
        if not selected:
            return

        item = self.zone_listbox.item(selected[0])
        old_name = item['values'][0].replace("📍 ", "")

        # Usa o diálogo de cores personalizado
        color_dialog = ColorSelectionDialog(self.root, "Mudar Cor da ROI")
        if not color_dialog.result:
            return

        selected_color = color_dialog.result
        new_color = selected_color["rgb"]
        color_name = selected_color["name"]

        # Atualiza no projeto
        zone_data = self.controller.project_manager.get_zone_data()
        try:
            idx = zone_data.roi_names.index(old_name)
            zone_data.roi_colors[idx] = new_color

            # Salva
            from dataclasses import asdict
            self.controller.project_manager.project_data["detection_zones"] = asdict(zone_data)
            self.controller.project_manager.save_project()

            # Atualiza visualização
            self.redraw_zones_from_project_data()
            self.show_info("Sucesso", f"Cor da ROI '{old_name}' alterada para {color_name}")

        except ValueError:
            self.show_error("Erro", "ROI não encontrada")
        except IndexError:
            self.show_error("Erro", "Dados de cor da ROI não encontrados")

    def _remove_selected_roi_confirm(self):
        """Remove ROI selecionada com confirmação"""
        selected = self.zone_listbox.selection()
        if not selected:
            return

        item = self.zone_listbox.item(selected[0])
        roi_name = item['values'][0].replace("📍 ", "")

        # Confirmação
        from tkinter import messagebox
        confirm = messagebox.askyesno(
            "Confirmar Remoção",
            f"Tem certeza que deseja remover a ROI '{roi_name}'?\n\nEsta ação não pode ser desfeita.",
            icon="warning"
        )

        if confirm:
            # Remove do projeto
            zone_data = self.controller.project_manager.get_zone_data()
            try:
                idx = zone_data.roi_names.index(roi_name)

                # Remove da lista de nomes
                zone_data.roi_names.pop(idx)

                # Remove da lista de polígonos
                if idx < len(zone_data.roi_polygons):
                    zone_data.roi_polygons.pop(idx)

                # Remove da lista de cores
                if idx < len(zone_data.roi_colors):
                    zone_data.roi_colors.pop(idx)

                # Salva
                from dataclasses import asdict
                self.controller.project_manager.project_data["detection_zones"] = asdict(zone_data)
                self.controller.project_manager.save_project()

                # Atualiza visualização
                self.redraw_zones_from_project_data()
                self.show_info("Sucesso", f"ROI '{roi_name}' removida com sucesso")

            except ValueError:
                self.show_error("Erro", "ROI não encontrada")

    def ask_save_filename(self, **options):
        """Shows a dialog to select a save file path."""
        return filedialog.asksaveasfilename(**options)

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

    def ask_recording_details_unified(self):
        """Shows a unified dialog to get day, group, and subject."""
        # Check if it's a live project with the necessary config
        pm = self.controller.project_manager
        if not pm.project_data.get("experiment_days"):
            self.show_error(
                "Error",
                "This project is not configured for live experimental tracking.",
            )
            return None

        dialog = StartRecordingDialog(self.root, pm)
        return dialog.result

    def ask_missing_metadata(self, experiment_id):
        """Shows a dialog to get missing metadata from the user."""
        dialog = MissingMetadataDialog(self.root, experiment_id)
        return dialog.result


class SingleVideoConfigDialog(simpledialog.Dialog):
    """A simplified dialog to get configuration for a single video analysis."""

    def __init__(self, parent):
        self.result = None
        super().__init__(parent, "Configuração de Análise de Vídeo Único")

    def body(self, master):
        # --- Tkinter Variables ---
        self.num_aquariums_var = StringVar(value="1")
        self.animals_per_aquarium_var = StringVar(value="1")
        self.aquarium_width_var = StringVar(value="10.0")
        self.aquarium_height_var = StringVar(value="10.0")

        # Pre-fill with defaults from settings
        self.sharp_turn_var = StringVar(
            value=str(settings.video_processing.sharp_turn_threshold_deg_s)
        )
        self.freeze_thresh_var = StringVar(
            value=str(settings.video_processing.freezing_velocity_threshold)
        )
        self.freeze_dur_var = StringVar(
            value=str(settings.video_processing.freezing_min_duration_s)
        )

        # --- Layout ---
        main_frame = ttk.Frame(master, padding=10)
        main_frame.pack(expand=True, fill="both")

        # --- Aquarium Dimensions ---
        dim_frame = ttk.LabelFrame(main_frame, text="Calibração", padding=10)
        dim_frame.pack(fill="x", pady=5)
        dim_frame.columnconfigure(1, weight=1)

        ttk.Label(dim_frame, text="Número de Aquários:").grid(
            row=0, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(dim_frame, textvariable=self.num_aquariums_var, width=10).grid(
            row=0, column=1, sticky="w", padx=5
        )

        ttk.Label(dim_frame, text="Animais por Aquário:").grid(
            row=1, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(dim_frame, textvariable=self.animals_per_aquarium_var, width=10).grid(
            row=1, column=1, sticky="w", padx=5
        )

        ttk.Label(dim_frame, text="Largura do Aquário (cm):").grid(
            row=2, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(dim_frame, textvariable=self.aquarium_width_var, width=10).grid(
            row=2, column=1, sticky="w", padx=5
        )

        ttk.Label(dim_frame, text="Altura do Aquário (cm):").grid(
            row=3, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(dim_frame, textvariable=self.aquarium_height_var, width=10).grid(
            row=3, column=1, sticky="w", padx=5
        )

        # --- Behavior Analysis Parameters ---
        behavior_frame = ttk.LabelFrame(
            main_frame, text="Parâmetros de Análise", padding=10
        )
        behavior_frame.pack(fill="x", pady=5)
        behavior_frame.columnconfigure(1, weight=1)

        ttk.Label(behavior_frame, text="Limiar de Curva Acentuada (graus/s):").grid(
            row=0, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(behavior_frame, textvariable=self.sharp_turn_var, width=10).grid(
            row=0, column=1, sticky="w", padx=5
        )

        ttk.Label(behavior_frame, text="Limiar de Congelamento (cm/s):").grid(
            row=1, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(behavior_frame, textvariable=self.freeze_thresh_var, width=10).grid(
            row=1, column=1, sticky="w", padx=5
        )

        ttk.Label(behavior_frame, text="Duração Mín. de Congelamento (s):").grid(
            row=2, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(behavior_frame, textvariable=self.freeze_dur_var, width=10).grid(
            row=2, column=1, sticky="w", padx=5
        )

        return main_frame

    def validate(self):
        try:
            num_aquariums = int(self.num_aquariums_var.get())
            animals_per_aquarium = int(self.animals_per_aquarium_var.get())
            float(self.aquarium_width_var.get())
            float(self.aquarium_height_var.get())
            float(self.sharp_turn_var.get())
            float(self.freeze_thresh_var.get())
            float(self.freeze_dur_var.get())
            if num_aquariums <= 0 or animals_per_aquarium <= 0:
                raise ValueError("Os valores devem ser positivos.")
        except ValueError:
            messagebox.showerror(
                "Erro", "Todos os campos de configuração devem ser números válidos e positivos."
            )
            return 0
        return 1

    def apply(self):
        self.result = {
            "num_aquariums": int(self.num_aquariums_var.get()),
            "animals_per_aquarium": int(self.animals_per_aquarium_var.get()),
            "aquarium_width_cm": float(self.aquarium_width_var.get()),
            "aquarium_height_cm": float(self.aquarium_height_var.get()),
            "sharp_turn_threshold_deg_s": float(self.sharp_turn_var.get()),
            "freezing_velocity_threshold": float(self.freeze_thresh_var.get()),
            "freezing_min_duration_s": float(self.freeze_dur_var.get()),
        }


class StartRecordingDialog(simpledialog.Dialog):
    def __init__(self, parent, project_manager):
        self.pm = project_manager
        self.result = None
        super().__init__(parent, "Iniciar Nova Sessão de Gravação")

    def body(self, master):
        # Get data from project manager
        days = self.pm.project_data.get("experiment_days", 1)
        groups = self.pm.project_data.get("groups", [])
        subjects = self.pm.project_data.get("subjects_per_group", 1)
        last_day, last_group = self.pm.get_last_session_details()

        # Create variables
        self.day_var = StringVar()
        self.group_var = StringVar()
        self.subject_var = StringVar()

        # Set initial values for smart state retention
        day_opts = [str(d) for d in range(1, days + 1)]
        if last_day and str(last_day) in day_opts:
            self.day_var.set(str(last_day))
        elif day_opts:
            self.day_var.set(day_opts[0])

        if last_group and last_group in groups:
            self.group_var.set(last_group)
        elif groups:
            self.group_var.set(groups[0])

        # --- Layout ---
        # Day Dropdown
        Label(master, text="Selecione o Dia:").grid(
            row=0, column=0, sticky="w", padx=5, pady=5
        )
        day_menu = OptionMenu(master, self.day_var, *day_opts)
        day_menu.grid(row=0, column=1, sticky="ew", padx=5)

        # Group Dropdown
        Label(master, text="Selecione o Grupo:").grid(
            row=1, column=0, sticky="w", padx=5, pady=5
        )
        group_menu = OptionMenu(master, self.group_var, *groups)
        group_menu.grid(row=1, column=1, sticky="ew", padx=5)

        # Subject Dropdown
        Label(master, text="Selecione a Cobaia:").grid(
            row=2, column=0, sticky="w", padx=5, pady=5
        )
        subject_opts = [str(s) for s in range(1, subjects + 1)]
        subject_menu = OptionMenu(master, self.subject_var, *subject_opts)
        subject_menu.grid(row=2, column=1, sticky="ew", padx=5)
        if subject_opts:
            self.subject_var.set(subject_opts[0])

        return subject_menu  # Initial focus

    def validate(self):
        if not all([self.day_var.get(), self.group_var.get(), self.subject_var.get()]):
            messagebox.showerror("Erro", "Todos os campos são obrigatórios.")
            return 0
        return 1

    def apply(self):
        self.result = {
            "day": int(self.day_var.get()),
            "group": self.group_var.get(),
            "cobaia": self.subject_var.get(),
        }


class MissingMetadataDialog(simpledialog.Dialog):
    def __init__(self, parent, experiment_id):
        self.experiment_id = experiment_id
        self.result = None
        super().__init__(parent, "Metadados Ausentes")

    def body(self, master):
        Label(
            master, text="Não foi possível encontrar metadados automaticamente para:"
        ).pack(pady=5)
        Label(master, text=self.experiment_id, font=("Helvetica", 10, "bold")).pack(
            pady=(0, 10)
        )
        Label(master, text="Por favor, insira os detalhes manualmente:").pack(pady=5)

        self.day_var = StringVar()
        self.group_var = StringVar()
        self.cobaia_var = StringVar()

        form_frame = Frame(master)
        form_frame.pack(padx=10, pady=10)

        Label(form_frame, text="Dia:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        Entry(form_frame, textvariable=self.day_var).grid(
            row=0, column=1, sticky="ew", padx=5
        )

        Label(form_frame, text="Grupo:").grid(
            row=1, column=0, sticky="w", padx=5, pady=2
        )
        Entry(form_frame, textvariable=self.group_var).grid(
            row=1, column=1, sticky="ew", padx=5
        )

        Label(form_frame, text="Cobaia (ID):").grid(
            row=2, column=0, sticky="w", padx=5, pady=2
        )
        Entry(form_frame, textvariable=self.cobaia_var).grid(
            row=2, column=1, sticky="ew", padx=5
        )

        return form_frame

    def validate(self):
        try:
            int(self.day_var.get())
            int(self.cobaia_var.get())
        except ValueError:
            messagebox.showerror(
                "Erro de Validação", "Dia e Cobaia (ID) devem ser números inteiros."
            )
            return 0

        if not self.group_var.get().strip():
            messagebox.showerror(
                "Erro de Validação", "O nome do grupo não pode estar vazio."
            )
            return 0

        return 1

    def apply(self):
        self.result = {
            "day": int(self.day_var.get()),
            "group": self.group_var.get().strip(),
            "cobaia": int(self.cobaia_var.get()),
        }


class SubjectSelectionDialog(simpledialog.Dialog):
    def __init__(self, parent, day, group_name, subjects_per_group, completed_subjects):
        self.day = day
        self.group_name = group_name
        self.subjects_per_group = subjects_per_group
        self.completed_subjects = completed_subjects
        self.result = None  # This will be the selected subject_id
        super().__init__(parent, f"Selecionar Cobaia para o Dia {day} - {group_name}")

    def body(self, master):
        master.config(padx=10, pady=10)
        for i in range(self.subjects_per_group):
            subject_id = i + 1
            is_completed = subject_id in self.completed_subjects

            status_text = (
                f"Cobaia {subject_id}: {'Concluído' if is_completed else 'Pendente'}"
            )
            status_color = "darkgreen" if is_completed else "black"

            label = ttk.Label(
                master,
                text=status_text,
                foreground=status_color,
                font=("Helvetica", 10),
            )
            label.pack(anchor="w", pady=3)

            if not is_completed:
                label.config(cursor="hand2")
                label.bind("<Button-1>", lambda e, s=subject_id: self.select_subject(s))
        return None  # No initial focus

    def select_subject(self, subject_id):
        self.result = subject_id
        self.ok()  # Close the dialog

    def buttonbox(self):
        # Override to have only a cancel button, since selection closes the dialog
        box = ttk.Frame(self)
        w = ttk.Button(box, text="Cancelar", width=10, command=self.cancel)
        w.pack(side="left", padx=5, pady=5)
        self.bind("<Escape>", self.cancel)
        box.pack()


class TemplateDialog(simpledialog.Dialog):
    """Dialog to create ROI templates."""

    def body(self, master):
        self.template_type = StringVar(value="vertical")
        self.num_lanes = StringVar(value="3")
        self.num_rows = StringVar(value="2")
        self.num_cols = StringVar(value="2")

        ttk.Radiobutton(
            master,
            text="Faixas Verticais",
            variable=self.template_type,
            value="vertical",
        ).pack(anchor="w")
        ttk.Radiobutton(
            master,
            text="Faixas Horizontais",
            variable=self.template_type,
            value="horizontal",
        ).pack(anchor="w")
        ttk.Radiobutton(
            master, text="Grade", variable=self.template_type, value="grid"
        ).pack(anchor="w")

        ttk.Label(master, text="Nº de Faixas:").pack(anchor="w", pady=(5, 0))
        ttk.Entry(master, textvariable=self.num_lanes).pack(anchor="w")

        ttk.Label(master, text="Grade (Linhas x Colunas):").pack(
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

        ttk.Label(master, text="Método:").pack(anchor="w")
        ttk.Radiobutton(
            master,
            text="Distância da Borda (cm)",
            variable=self.method,
            value="distance",
        ).pack(anchor="w")
        ttk.Radiobutton(
            master,
            text="Razão da Área (0.0-1.0)",
            variable=self.method,
            value="area_ratio",
        ).pack(anchor="w")

        ttk.Label(master, text="Valor:").pack(anchor="w", pady=(5, 0))
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


class ColorSelectionDialog(simpledialog.Dialog):
    """Diálogo para seleção de cor de áreas de interesse."""

    def __init__(self, parent, title="Selecionar Cor da Área"):
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        """Cria o corpo do diálogo com opções de cores."""
        self.selected_color = StringVar(value="green")

        # Cores disponíveis: (nome, valor_rgb, cor_hex)
        self.colors = [
            ("Verde", (0, 255, 0), "#00FF00"),
            ("Azul", (0, 0, 255), "#0000FF"),
            ("Vermelho", (255, 0, 0), "#FF0000"),
            ("Amarelo", (255, 255, 0), "#FFFF00"),
            ("Magenta", (255, 0, 255), "#FF00FF"),
            ("Ciano", (0, 255, 255), "#00FFFF"),
        ]

        ttk.Label(master, text="Escolha a cor para esta área de interesse:").pack(pady=5)

        # Frame para os botões de cor
        colors_frame = ttk.Frame(master)
        colors_frame.pack(pady=10)

        # Criar botões de cor em duas fileiras
        for i, (name, rgb, hex_color) in enumerate(self.colors):
            row = i // 3
            col = i % 3

            color_frame = ttk.Frame(colors_frame)
            color_frame.grid(row=row, column=col, padx=5, pady=5)

            # Radiobutton para seleção
            ttk.Radiobutton(
                color_frame,
                text=name,
                variable=self.selected_color,
                value=name.lower(),
            ).pack()

            # Quadrado colorido para visualização
            color_canvas = Canvas(color_frame, width=30, height=20, highlightthickness=1)
            color_canvas.pack()
            color_canvas.create_rectangle(0, 0, 30, 20, fill=hex_color, outline="black")

        return master

    def apply(self):
        """Aplica a seleção de cor."""
        selected_name = self.selected_color.get()
        for name, rgb, hex_color in self.colors:
            if name.lower() == selected_name:
                self.result = {
                    "name": name,
                    "rgb": rgb,
                    "hex": hex_color
                }
                break


if __name__ == "__main__":
    # Using print is fine here as it's for direct execution feedback
    print("Este arquivo deve ser importado, não executado diretamente.")
    print("Execute o script principal da aplicação para iniciar o Zebtrack.")
