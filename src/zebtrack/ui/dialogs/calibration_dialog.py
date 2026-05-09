"""
CalibrationDialog.

Extracted from gui.py for better modularity. As of TASK-065 the dialog also
absorbs the entire former ``ManageWeightsDialog`` (4-slot defaults matrix,
weights catalog Treeview, OpenVINO maintenance, hardware benchmark) so the
former ``Gerenciar Pesos`` button no longer exists.
"""

import contextlib
import os
import tkinter as tk
from pathlib import Path
from tkinter import (
    BooleanVar,
    StringVar,
    filedialog,
    messagebox,
    simpledialog,
    ttk,
)
from typing import Any

import structlog
from pydantic import ValidationError

from zebtrack.ui import payloads
from zebtrack.ui.collapsible_frame import CollapsibleFrame
from zebtrack.ui.event_bus_v2 import Event, UIEvents
from zebtrack.ui.icon_utils import set_window_icon
from zebtrack.ui.window_utils import schedule_maximize
from zebtrack.ui.wizard.tooltip import ToolTip, create_help_label

log = structlog.get_logger()

# Display labels for the inline weights catalog (Portuguese to match the rest
# of the UI). Inlined verbatim from the former ``ManageWeightsDialog``.
_TARGET_LABELS = {"aquarium": "Aquário", "zebrafish": "Zebrafish"}
_TARGET_FROM_LABEL = {v: k for k, v in _TARGET_LABELS.items()}
_METHOD_LABELS = {"seg": "Segmentação", "det": "Detecção"}
_PERSPECTIVE_LABELS = {"lateral": "Lateral", "top_down": "Topo (top-down)"}
_OPENVINO_STATUS_LABELS = {
    "ready": "✓ Pronto",
    "converting": "⏳ Convertendo",
    "failed": "✗ Falhou",
    "not_converted": "—",
}
# Polling cadence for the OpenVINO conversion status column (ms).
_CONVERSION_POLL_INTERVAL_MS = 1500


class CalibrationDialog(simpledialog.Dialog):
    """Dialog for model calibration, diagnostics, and project preferences."""

    WEIGHT_INHERIT_LABEL = "Herdar (padrão global)"
    OPENVINO_INHERIT = "inherit"
    OPENVINO_ON = "on"
    OPENVINO_OFF = "off"

    def __init__(self, parent, controller):
        """Initialize the calibration dialog.

        Args:
            parent: Parent widget.
            controller: Main view model controller instance.
        """
        self.controller = controller
        self.project_manager = controller.project_manager

        self.calibration_section: ttk.Frame | None = None
        self.preferences_section: ttk.Frame | None = None
        self.preferences_separator: ttk.Separator | None = None

        # Local Tkinter variables for calibration tab.
        # ``active_weight_var`` now exclusively drives the *diagnostic* weight
        # combobox in the "Diagnóstico" section — it no longer represents a
        # global "active weight" (the 4-slot matrix replaces that concept).
        self.active_weight_var = StringVar()
        self.use_openvino_var = BooleanVar()
        self.openvino_status_var = StringVar()

        # 4-slot defaults matrix: one StringVar per (method, target).
        self.slot_vars: dict[tuple[str, str], StringVar] = {
            ("det", "aquarium"): StringVar(),
            ("seg", "aquarium"): StringVar(),
            ("det", "zebrafish"): StringVar(),
            ("seg", "zebrafish"): StringVar(),
        }
        self.slot_comboboxes: dict[tuple[str, str], ttk.Combobox] = {}

        # Inline weights catalog (formerly ManageWeightsDialog).
        self.weights_treeview: ttk.Treeview | None = None
        self._weights_validation: dict[str, bool] = {}
        self._conversion_poller_id: str | None = None
        self.scope_info = controller.project_vm.get_calibration_scope_info()
        self.scope = self.scope_info.get("scope", "global")
        self.scope_label_var = StringVar(value=self.scope_info["label"])
        self.scope_detail_var = StringVar(value=self.scope_info["detail"])
        self.scope_action_button: ttk.Button | None = None
        self.weights_dropdown: ttk.Combobox | None = None
        self.openvino_checkbox: ttk.Checkbutton | None = None
        self.openvino_status_label: ttk.Label | None = None
        self.model_test_dropdown: ttk.Combobox | None = None

        # Diagnostic variables
        self.frames_to_analyze_var = StringVar(value="10")
        self.confidence_threshold_var = StringVar(value="0.25")
        self.nms_threshold_var = StringVar(value="0.50")
        self.use_bytetrack_var = BooleanVar(value=True)
        self.track_threshold_var = StringVar(value="0.25")
        self.match_threshold_var = StringVar(value="0.95")
        self.track_buffer_var = StringVar(value="90")
        self.max_center_dist_var = StringVar(value="400.0")
        self.iou_threshold_var = StringVar(value="0.05")

        self.video_path_label_var = StringVar(value="Nenhum vídeo selecionado.")
        self.diagnostic_video_path = ""
        self.model_test_var = StringVar(value="YOLO (PyTorch)")

        # Preferences tab state
        self.weight_choice = StringVar(value=self.WEIGHT_INHERIT_LABEL)
        self.openvino_choice = StringVar(value=self.OPENVINO_INHERIT)
        self.effective_weight_var = StringVar()
        self.effective_openvino_var = StringVar()
        self.preferences_weight_dropdown: ttk.Combobox | None = None

        self._prefill_detector_parameters()

        dialog_title = (
            "Calibração e Preferências do Projeto"
            if self.scope_info.get("scope") == "project"
            else "Calibração e Diagnóstico"
        )

        super().__init__(parent, dialog_title)

        # Set application icon

        try:
            set_window_icon(self)
        except Exception:
            log.warning("icon.set.failed", exc_info=True)

    def body(self, master):
        """Create calibration dialog body with model and detection controls.

        Args:
            master: Parent widget for dialog body.

        Returns:
            The initial focus widget.
        """
        schedule_maximize(self)

        # Wrap everything in a vertical-scrolling canvas so the (now denser)
        # weights catalog + diagnostic controls remain reachable on small
        # displays. Inline catalog absorbs ~10 controls extra vs. v3.3.
        container = self._make_scrollable_container(master)

        # Calibration section with collapsible frame
        calibration_collapsible = CollapsibleFrame(
            container,
            title="📐 Calibração e Diagnóstico",
            start_collapsed=False,
        )
        calibration_collapsible.pack(fill="x", expand=False, pady=(0, 5))
        self.calibration_section = calibration_collapsible.get_content_frame()

        # Preferences section - only show for project scope
        if self.scope == "project":
            preferences_collapsible = CollapsibleFrame(
                container,
                title="⚙️ Preferências do Projeto",
                start_collapsed=False,
            )
            preferences_collapsible.pack(fill="x", expand=False, pady=(0, 5))
            self.preferences_section = preferences_collapsible.get_content_frame()
        else:
            self.preferences_section = None

        # Note: We no longer need the separator as CollapsibleFrames provide visual separation
        self.preferences_separator = None

        self._refresh_scope_context()

        return self.calibration_section

    def _make_scrollable_container(self, master) -> ttk.Frame:
        """Wrap dialog content in a vertical-scrolling canvas.

        Returns the inner ``ttk.Frame`` to which the rest of the body should
        pack/grid its children. Mouse-wheel scroll is bound only while the
        cursor is over the canvas to avoid stealing wheel events from
        comboboxes/treeview inside.
        """
        outer = ttk.Frame(master, padding=0)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)

        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=5)
        scrollbar.pack(side="right", fill="y", pady=5)

        def _on_inner_configure(_e: object) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event: Any) -> None:
            # Stretch the inner frame to the canvas width so child widgets
            # using ``fill="x"`` actually grow with the dialog.
            canvas.itemconfigure(inner_id, width=event.width)

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event: Any) -> None:
            # Windows/macOS: event.delta is +/-120 per notch.
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _on_button_scroll(event: Any) -> None:
            # X11 fallback (Linux): Button-4 = up, Button-5 = down.
            canvas.yview_scroll(-1 if event.num == 4 else 1, "units")

        canvas.bind(
            "<Enter>",
            lambda _e: (
                canvas.bind_all("<MouseWheel>", _on_mousewheel),
                canvas.bind_all("<Button-4>", _on_button_scroll),
                canvas.bind_all("<Button-5>", _on_button_scroll),
            ),
        )
        canvas.bind(
            "<Leave>",
            lambda _e: (
                canvas.unbind_all("<MouseWheel>"),
                canvas.unbind_all("<Button-4>"),
                canvas.unbind_all("<Button-5>"),
            ),
        )

        return inner

    @staticmethod
    def _clear_frame(frame: ttk.Frame) -> None:
        try:
            if not frame.winfo_exists():
                return
            for child in frame.winfo_children():
                child.destroy()
        except tk.TclError:
            # Frame already destroyed
            log.debug("calibration_dialog.clear_frame.suppressed", exc_info=True)

    def _build_calibration_section(self) -> None:
        if not self.calibration_section:
            return

        self._clear_frame(self.calibration_section)
        self.scope_action_button = None

        scope_frame = ttk.LabelFrame(
            self.calibration_section,
            text="Contexto da Calibração",
            padding=10,
        )
        scope_frame.pack(fill="x", pady=(5, 0), padx=5)

        ttk.Label(
            scope_frame,
            textvariable=self.scope_label_var,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            scope_frame,
            textvariable=self.scope_detail_var,
            wraplength=460,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))

        action_text = self._get_scope_action_text(self.scope_info)
        if action_text:
            self.scope_action_button = ttk.Button(
                scope_frame,
                text=action_text,
                command=self._on_scope_primary_action,
            )
            self.scope_action_button.pack(anchor="e", pady=(8, 0))

        if self.scope == "global":
            self._build_global_calibration_ui(self.calibration_section)
        else:
            self._build_project_calibration_ui(self.calibration_section)

    def _build_preferences_section(self) -> None:
        if not self.preferences_section:
            return

        self._clear_frame(self.preferences_section)
        self.preferences_section.columnconfigure(1, weight=1)

        if not self.scope_info.get("project_loaded"):
            ttk.Label(
                self.preferences_section,
                text=(
                    "Abra um projeto para ajustar pesos e OpenVINO específicos. "
                    "As preferências aplicadas aqui não afetam o padrão global."
                ),
                wraplength=440,
                justify="left",
                foreground="#555555",
            ).grid(row=0, column=0, sticky="w", padx=12, pady=12)
            return

        detector_state = self.controller.state_manager.get_detector_state()
        defaults = {
            "active_weight": detector_state.active_weight_name,
            "use_openvino": detector_state.use_openvino,
        }
        overrides = self._get_current_overrides()

        heading = ttk.Label(
            self.preferences_section,
            text="Preferências do Projeto",
            font=("Segoe UI", 11, "bold"),
        )
        heading.grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 4))

        weights = self.controller.hardware_vm.get_all_weight_names()
        display_values = [self.WEIGHT_INHERIT_LABEL, *weights]

        current_weight_override = overrides.get("active_weight")
        if current_weight_override and current_weight_override not in weights:
            display_values.append(current_weight_override)

        if current_weight_override:
            self.weight_choice.set(current_weight_override)
        else:
            self.weight_choice.set(self.WEIGHT_INHERIT_LABEL)

        openvino_override = overrides.get("use_openvino")
        if openvino_override is None:
            self.openvino_choice.set(self.OPENVINO_INHERIT)
        elif bool(openvino_override):
            self.openvino_choice.set(self.OPENVINO_ON)
        else:
            self.openvino_choice.set(self.OPENVINO_OFF)

        row = 1
        ttk.Label(
            self.preferences_section,
            text=("Defina overrides deste projeto. Ao herdar, o estado global é reutilizado."),
            wraplength=440,
            justify="left",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8))
        row += 1

        ttk.Label(
            self.preferences_section,
            text="Peso específico deste projeto:",
        ).grid(row=row, column=0, sticky="w", padx=12)
        self.preferences_weight_dropdown = ttk.Combobox(
            self.preferences_section,
            state="readonly",
            values=display_values,
            textvariable=self.weight_choice,
        )
        self.preferences_weight_dropdown.grid(row=row, column=1, sticky="ew", padx=(0, 12))
        self.preferences_weight_dropdown.bind(
            "<<ComboboxSelected>>", lambda *_: self._update_preferences_preview()
        )
        row += 1

        openvino_frame = ttk.LabelFrame(self.preferences_section, text="OpenVINO", padding=8)
        openvino_frame.grid(row=row, column=0, columnspan=2, padx=12, pady=(12, 4), sticky="ew")
        openvino_frame.columnconfigure(0, weight=1)

        inherit_radio = ttk.Radiobutton(
            openvino_frame,
            text="Herdar configuração global",
            value=self.OPENVINO_INHERIT,
            variable=self.openvino_choice,
            command=self._update_preferences_preview,
        )
        inherit_radio.grid(row=0, column=0, sticky="w")
        ToolTip(
            inherit_radio, "Usa exatamente a configuração global do OpenVINO para este projeto."
        )

        force_on_radio = ttk.Radiobutton(
            openvino_frame,
            text="Forçar ativado",
            value=self.OPENVINO_ON,
            variable=self.openvino_choice,
            command=self._update_preferences_preview,
        )
        force_on_radio.grid(row=1, column=0, sticky="w", pady=(2, 0))
        ToolTip(force_on_radio, "Sempre usa OpenVINO neste projeto, independente do padrão global.")

        force_off_radio = ttk.Radiobutton(
            openvino_frame,
            text="Forçar desativado",
            value=self.OPENVINO_OFF,
            variable=self.openvino_choice,
            command=self._update_preferences_preview,
        )
        force_off_radio.grid(row=2, column=0, sticky="w", pady=(2, 0))
        ToolTip(
            force_off_radio,
            "Impede o uso do OpenVINO neste projeto, mesmo se estiver ativo globalmente.",
        )

        ttk.Label(
            openvino_frame,
            text=(
                "Escolha como aplicar OpenVINO neste projeto:\n"
                "• Herdar: segue o estado global atual.\n"
                "• Forçar ativado: sempre usa OpenVINO aqui.\n"
                "• Forçar desativado: mantém PyTorch mesmo que o global esteja ativo."
            ),
            justify="left",
            font=("TkDefaultFont", 9),
            foreground="#555555",
        ).grid(row=3, column=0, sticky="w", pady=(6, 0))

        row += 1
        preview = ttk.LabelFrame(self.preferences_section, text="Resultado Efetivo", padding=8)
        preview.grid(row=row, column=0, columnspan=2, padx=12, pady=(10, 6), sticky="ew")
        preview.columnconfigure(1, weight=1)

        ttk.Label(preview, text="Peso utilizado:").grid(row=0, column=0, sticky="w")
        ttk.Label(preview, textvariable=self.effective_weight_var).grid(row=0, column=1, sticky="w")
        ttk.Label(preview, text="OpenVINO:").grid(row=1, column=0, sticky="w")
        ttk.Label(preview, textvariable=self.effective_openvino_var).grid(
            row=1, column=1, sticky="w"
        )

        row += 1
        defaults_frame = ttk.LabelFrame(self.preferences_section, text="Padrões Globais", padding=8)
        defaults_frame.grid(row=row, column=0, columnspan=2, padx=12, pady=(6, 4), sticky="ew")
        ttk.Label(
            defaults_frame, text=f"Peso global: {defaults.get('active_weight') or 'Nenhum'}"
        ).pack(anchor="w")
        ttk.Label(
            defaults_frame,
            text=(
                "OpenVINO global: " + ("Ativado" if defaults.get("use_openvino") else "Desativado")
            ),
        ).pack(anchor="w", pady=(4, 0))

        row += 1
        actions = ttk.Frame(self.preferences_section)
        actions.grid(row=row, column=0, columnspan=2, sticky="e", padx=12, pady=(10, 12))
        ttk.Button(
            actions, text="Salvar Preferências", command=self._save_project_preferences
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            actions, text="Recarregar do Projeto", command=self._restore_project_preferences
        ).pack(side="left")

        self._update_preferences_preview()

    def _get_current_overrides(self) -> dict:
        project_data = getattr(self.project_manager, "project_data", {}) or {}
        return project_data.get("model_overrides", {}) or {}

    def _get_preferences_overrides(self) -> tuple[str | None, bool | None]:
        weight_selection = self.weight_choice.get()
        if weight_selection == self.WEIGHT_INHERIT_LABEL:
            weight_override = None
        else:
            weight_override = weight_selection

        openvino_selection = self.openvino_choice.get()
        if openvino_selection == self.OPENVINO_INHERIT:
            openvino_override = None
        elif openvino_selection == self.OPENVINO_ON:
            openvino_override = True
        else:
            openvino_override = False

        return weight_override, openvino_override

    def _update_preferences_preview(self) -> None:
        if not self.scope_info.get("project_loaded"):
            return

        weight_override, openvino_override = self._get_preferences_overrides()
        resolved_weight, resolved_openvino = (
            self.controller.project_vm.resolve_project_model_settings(
                {
                    "active_weight": weight_override,
                    "use_openvino": openvino_override,
                }
            )
        )

        self.effective_weight_var.set(resolved_weight or "Nenhum peso disponível")
        self.effective_openvino_var.set("Ativado" if resolved_openvino else "Desativado")

    def _save_project_preferences(self) -> None:
        if not self.scope_info.get("project_loaded"):
            return

        weight_override, openvino_override = self._get_preferences_overrides()

        try:
            self.controller.project_vm.save_project_model_overrides(
                weight_override, openvino_override
            )
        except ValidationError as exc:  # pragma: no cover - defensive
            messagebox.showerror("Erro", str(exc))
            return

        messagebox.showinfo("Preferências atualizadas", "As preferências do projeto foram salvas.")
        self._refresh_scope_context()

    def _restore_project_preferences(self) -> None:
        overrides = self._get_current_overrides()

        weight_override = overrides.get("active_weight")
        if weight_override:
            self.weight_choice.set(weight_override)
        else:
            self.weight_choice.set(self.WEIGHT_INHERIT_LABEL)

        openvino_override = overrides.get("use_openvino")
        if openvino_override is None:
            self.openvino_choice.set(self.OPENVINO_INHERIT)
        elif bool(openvino_override):
            self.openvino_choice.set(self.OPENVINO_ON)
        else:
            self.openvino_choice.set(self.OPENVINO_OFF)

        if self.preferences_weight_dropdown:
            self.preferences_weight_dropdown.set(self.weight_choice.get())

        self._update_preferences_preview()

    def _build_global_calibration_ui(self, master):
        # ── Section: Configuração do Modelo (formerly two boxes + dialog) ──
        # Layout: 2 columns on top (slots+OpenVINO | weights catalog), then a
        # full-width row split into 2 columns (maintenance | system+hardware).
        model_frame = ttk.LabelFrame(master, text="Configuração do Modelo", padding=10)
        model_frame.pack(fill="both", expand=True, pady=5, padx=5)

        top_row = ttk.Frame(model_frame)
        top_row.pack(fill="both", expand=True)
        top_row.columnconfigure(0, weight=2, minsize=360)
        top_row.columnconfigure(1, weight=3, minsize=520)

        left_col = ttk.Frame(top_row)
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        right_col = ttk.Frame(top_row)
        right_col.grid(row=0, column=1, sticky="nsew")

        self._build_default_slots_section(left_col)
        ttk.Separator(left_col, orient="horizontal").pack(fill="x", pady=10)
        self._build_openvino_section(left_col)

        self._build_weights_catalog_section(right_col)

        ttk.Separator(model_frame, orient="horizontal").pack(fill="x", pady=10)

        bottom_row = ttk.Frame(model_frame)
        bottom_row.pack(fill="x")
        bottom_row.columnconfigure(0, weight=3, minsize=480)
        bottom_row.columnconfigure(1, weight=2, minsize=320)

        maint_col = ttk.Frame(bottom_row)
        maint_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        sys_col = ttk.Frame(bottom_row)
        sys_col.grid(row=0, column=1, sticky="nsew")

        self._build_maintenance_section(maint_col)
        self._build_system_section(sys_col)

        # ── Section: Diagnóstico ──
        diag_frame = ttk.LabelFrame(
            master,
            text="Diagnóstico de Desempenho do Modelo",
            padding=10,
        )
        diag_frame.pack(fill="x", pady=10, padx=5)

        diag_weight_row = ttk.Frame(diag_frame)
        diag_weight_row.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(
            diag_weight_row,
            text="Peso para diagnóstico:",
        ).pack(side="left")
        self.weights_dropdown = ttk.Combobox(
            diag_weight_row,
            textvariable=self.active_weight_var,
            state="readonly",
        )
        self.weights_dropdown.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.weights_dropdown.bind("<<ComboboxSelected>>", self._on_weight_selected_local)
        ttk.Label(
            diag_frame,
            text=(
                "O peso aqui escolhido é usado pelo botão 'Testar Modelo em Vídeo'. "
                "Em produção o detector resolve o peso pelos slots padrão acima "
                "(método × alvo × perspectiva)."
            ),
            font=("Segoe UI", 8),
            foreground="#555555",
            wraplength=820,
            justify="left",
        ).pack(anchor="w", padx=10)

        self._populate_weights_dropdown()

        video_frame = ttk.Frame(diag_frame)
        video_frame.pack(fill="x", padx=10, pady=5)
        ttk.Button(
            video_frame,
            text="Selecionar Vídeo...",
            command=self._select_diagnostic_video,
        ).pack(side="left")
        ttk.Label(video_frame, textvariable=self.video_path_label_var).pack(side="left", padx=5)

        self._create_detector_params_section(
            diag_frame,
            include_model_test=True,
            include_frame_count=True,
        )

        actions_frame = ttk.Frame(diag_frame)
        actions_frame.pack(fill="x", padx=10, pady=(0, 5))
        ttk.Button(
            actions_frame,
            text="Aplicar Parâmetros",
            command=lambda: self._apply_detector_parameters(scope_override="global"),
        ).pack(side="left", expand=True, fill="x")
        ttk.Button(
            actions_frame,
            text="Restaurar Padrões",
            command=lambda: self._restore_detector_defaults(scope_override="global"),
        ).pack(side="left", expand=True, fill="x", padx=(8, 0))

        ttk.Button(
            diag_frame,
            text="Testar Modelo em Vídeo...",
            command=self._run_diagnostic_test,
        ).pack(fill="x", padx=10, pady=5)

    # ------------------------------------------------------------------
    # Sub-section builders for "Configuração do Modelo"
    # ------------------------------------------------------------------

    def _build_default_slots_section(self, parent: ttk.Widget) -> None:
        """Render the 4-slot defaults matrix (method × target)."""
        ttk.Label(
            parent,
            text="Pesos padrão por slot",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            parent,
            text=(
                "Cada combinação (método × alvo) usa um peso padrão. "
                "O detector consulta o slot correto em runtime."
            ),
            font=("Segoe UI", 8),
            foreground="#555555",
            wraplength=340,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))

        grid = ttk.Frame(parent)
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)

        slot_specs = [
            ("🐠 Aquário (Detecção)", "det", "aquarium"),
            ("🐠 Aquário (Segmentação)", "seg", "aquarium"),
            ("🐟 Animal (Detecção)", "det", "zebrafish"),
            ("🐟 Animal (Segmentação)", "seg", "zebrafish"),
        ]
        for row, (label, method, target) in enumerate(slot_specs):
            ttk.Label(grid, text=f"{label}:").grid(row=row, column=0, sticky="w", padx=4, pady=2)
            combo = ttk.Combobox(
                grid,
                textvariable=self.slot_vars[(method, target)],
                state="readonly",
            )
            combo.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
            combo.bind(
                "<<ComboboxSelected>>",
                lambda _e, m=method, t=target: self._on_slot_default_selected(m, t),
            )
            self.slot_comboboxes[(method, target)] = combo

        self._populate_slot_comboboxes()

    def _build_weights_catalog_section(self, parent: ttk.Widget) -> None:
        """Inline catalog of registered weights (replaces ManageWeightsDialog Treeview)."""
        ttk.Label(
            parent,
            text="Catálogo de pesos",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            parent,
            text=(
                "Ctrl/Shift-clique para selecionar múltiplos. Tipo = como o modelo "
                "opera (segmentação ou detecção); Alvo = o que ele identifica "
                "(aquário ou zebrafish)."
            ),
            font=("Segoe UI", 8),
            foreground="#555555",
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(0, 4))

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill="both", expand=True)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        columns = ("name", "type", "target", "perspective", "defaults", "openvino")
        self.weights_treeview = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            height=10,
            selectmode="extended",
        )
        self.weights_treeview.heading("name", text="Nome do Peso")
        self.weights_treeview.heading("type", text="Tipo")
        self.weights_treeview.heading("target", text="Alvo")
        self.weights_treeview.heading("perspective", text="Perspectiva")
        self.weights_treeview.heading("defaults", text="Default?")
        self.weights_treeview.heading("openvino", text="OpenVINO")

        # Trim widths so the catalog fits comfortably in the right column
        # (~520px minimum). ``name`` stretches to fill any extra width.
        self.weights_treeview.column("name", width=180, stretch=True, minwidth=120)
        self.weights_treeview.column("type", width=80, anchor="center", stretch=False)
        self.weights_treeview.column("target", width=70, anchor="center", stretch=False)
        self.weights_treeview.column("perspective", width=90, anchor="center", stretch=False)
        self.weights_treeview.column("defaults", width=110, anchor="center", stretch=False)
        self.weights_treeview.column("openvino", width=90, anchor="center", stretch=False)
        self.weights_treeview.tag_configure("missing", foreground="#b00020")

        scrollbar = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.weights_treeview.yview
        )
        self.weights_treeview.configure(yscrollcommand=scrollbar.set)
        self.weights_treeview.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # Buttons: 2 rows x 3 columns to fit comfortably in the right
        # column of the dialog (the row of 5 wide buttons overflowed).
        button_grid = ttk.Frame(parent)
        button_grid.pack(fill="x", pady=(6, 0))
        for col in range(3):
            button_grid.columnconfigure(col, weight=1, uniform="catalog_btns")

        ttk.Button(button_grid, text="Adicionar Peso...", command=self._on_add_weight).grid(
            row=0, column=0, sticky="ew", padx=2, pady=2
        )
        ttk.Button(button_grid, text="Excluir Selecionado", command=self._on_delete_weight).grid(
            row=0, column=1, sticky="ew", padx=2, pady=2
        )
        ttk.Button(button_grid, text="Alterar Alvo...", command=self._on_change_target).grid(
            row=0, column=2, sticky="ew", padx=2, pady=2
        )
        ttk.Button(button_grid, text="Validar Caminhos", command=self._on_validate_paths).grid(
            row=1, column=0, sticky="ew", padx=2, pady=2
        )
        ttk.Button(
            button_grid,
            text="Converter p/ OpenVINO",
            command=self._on_convert_openvino,
        ).grid(row=1, column=1, columnspan=2, sticky="ew", padx=2, pady=2)

        self._populate_weights_treeview()

    def _build_openvino_section(self, parent: ttk.Widget) -> None:
        """OpenVINO toggle + status + device selector (was inside Configuração)."""
        ttk.Label(
            parent,
            text="OpenVINO",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        self.openvino_checkbox = ttk.Checkbutton(
            parent,
            text="Otimizar com OpenVINO (para hardware Intel)",
            variable=self.use_openvino_var,
            command=self._on_openvino_toggled_local,
        )
        self.openvino_checkbox.pack(anchor="w", padx=4, pady=(2, 2))

        self.openvino_status_label = ttk.Label(
            parent,
            textvariable=self.openvino_status_var,
            font=("Segoe UI", 8),
        )
        self.openvino_status_label.pack(anchor="w", padx=20, pady=(0, 4))

        device_row = ttk.Frame(parent)
        device_row.pack(anchor="w", padx=4, pady=2)
        ttk.Label(device_row, text="Dispositivo OpenVINO:").pack(side="left")
        self.device_var = tk.StringVar(value="AUTO")
        self.device_combobox = ttk.Combobox(
            device_row, textvariable=self.device_var, state="readonly", width=20
        )
        self.device_combobox.pack(side="left", padx=(6, 0))
        self.device_combobox.bind("<<ComboboxSelected>>", self._on_device_selected)
        self._populate_device_combobox()

        self.use_openvino_var.set(self.controller.hardware_vm.use_openvino)
        self.update_openvino_status_label(self.controller.hardware_vm.get_openvino_status())
        if self.use_openvino_var.get():
            self.device_combobox.configure(state="readonly")
        else:
            self.device_combobox.configure(state="disabled")

    def _build_maintenance_section(self, parent: ttk.Widget) -> None:
        """OpenVINO cache + registry maintenance (was Section 2 of dialog)."""
        ttk.Label(
            parent,
            text="Manutenção de caches",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            parent,
            text=(
                "Caches OpenVINO aceleram a detecção mas ficam vinculados ao arquivo "
                ".pt original. Limpe-os ao trocar pesos com o mesmo nome ou após retreino."
            ),
            font=("Segoe UI", 8),
            foreground="#555555",
            wraplength=460,
            justify="left",
        ).pack(anchor="w", pady=(0, 4))

        # 2x2 grid keeps the four maintenance buttons compact in the wide
        # left column of the bottom row. Each cell expands evenly.
        grid = ttk.Frame(parent)
        grid.pack(fill="x")
        for col in range(2):
            grid.columnconfigure(col, weight=1, uniform="maint_btns")

        ttk.Button(
            grid,
            text="Apagar Cache OpenVINO (Selecionado)",
            command=self._on_clear_cache_selected,
        ).grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(
            grid,
            text="Apagar TODOS os Caches OpenVINO",
            command=self._on_clear_cache_all,
        ).grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        ttk.Button(
            grid,
            text="Reescanear Pasta de Pesos",
            command=self._on_rescan_folder,
        ).grid(row=1, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(
            grid,
            text="Resetar Lista de Pesos (fábrica)",
            command=self._on_reset_registry,
        ).grid(row=1, column=1, sticky="ew", padx=2, pady=2)

    def _build_system_section(self, parent: ttk.Widget) -> None:
        """Hardware benchmark + cache folder shortcut (was Section 3 of dialog)."""
        ttk.Label(
            parent,
            text="Sistema & Hardware",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            parent,
            text=(
                "Reexecutar o benchmark recalcula a configuração ótima do OpenVINO "
                "(device, precisão, hint) para o seu hardware atual."
            ),
            font=("Segoe UI", 8),
            foreground="#555555",
            wraplength=300,
            justify="left",
        ).pack(anchor="w", pady=(0, 4))

        # Stretch buttons across the column so the section feels balanced
        # next to the 2x2 maintenance grid on the left.
        grid = ttk.Frame(parent)
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1, uniform="sys_btns")
        grid.columnconfigure(1, weight=1, uniform="sys_btns")
        ttk.Button(
            grid,
            text="Reexecutar Benchmark de Hardware",
            command=self._on_force_benchmark,
        ).grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(
            grid,
            text="Abrir Pasta de Caches",
            command=self._on_open_cache_folder,
        ).grid(row=0, column=1, sticky="ew", padx=2, pady=2)

    def _build_project_calibration_ui(self, master):
        project_frame = ttk.LabelFrame(
            master,
            text="Parâmetros de Detecção do Projeto",
            padding=10,
        )
        project_frame.pack(fill="x", pady=10, padx=5)

        ttk.Label(
            project_frame,
            text=(
                "Os valores abaixo foram calibrados ao criar o projeto. "
                "Qualquer ajuste será aplicado somente a este projeto e aos pesos carregados nele."
            ),
            wraplength=460,
            justify="left",
            foreground="#4a4a4a",
        ).pack(anchor="w", padx=5, pady=(0, 6))

        self._create_detector_params_section(
            project_frame,
            include_model_test=False,
            include_frame_count=False,
        )

        actions_frame = ttk.Frame(project_frame)
        actions_frame.pack(fill="x", padx=10, pady=(8, 0))

        ttk.Button(
            actions_frame,
            text="Salvar no Projeto",
            command=lambda: self._apply_detector_parameters(scope_override="project"),
        ).pack(side="left", expand=True, fill="x")
        ttk.Button(
            actions_frame,
            text="Recarregar Valores Salvos",
            command=self._reload_project_parameters,
        ).pack(side="left", expand=True, fill="x", padx=8)
        ttk.Button(
            actions_frame,
            text="Restaurar Padrões Globais",
            command=lambda: self._restore_detector_defaults(scope_override="project"),
        ).pack(side="left", expand=True, fill="x")

    def _create_detector_params_section(
        self,
        parent,
        *,
        include_model_test: bool,
        include_frame_count: bool,
    ) -> None:
        params_frame = ttk.Frame(parent, padding=5)
        params_frame.pack(fill="x", padx=10, pady=5)

        # Configure columns: Label | Help | Entry
        params_frame.columnconfigure(1, weight=0)  # Help icon column
        params_frame.columnconfigure(2, weight=1)  # Entry column (expands)
        params_frame.columnconfigure(4, weight=0)  # Second column help
        params_frame.columnconfigure(5, weight=1)  # Second column entry

        row_idx = 0
        if include_frame_count:
            ttk.Label(params_frame, text="Nº Frames (Teste):").grid(
                row=row_idx, column=0, sticky="w", padx=(5, 2), pady=2
            )
            create_help_label(
                params_frame,
                "Quantidade de frames do vídeo a serem processados no teste de diagnóstico.\n"
                "Use um valor baixo (ex: 100) para testes rápidos.",
            ).grid(row=row_idx, column=1, padx=2)

            ttk.Entry(params_frame, textvariable=self.frames_to_analyze_var, width=8).grid(
                row=row_idx, column=2, sticky="w", padx=5
            )
            row_idx += 1

        # Confidence Threshold
        ttk.Label(params_frame, text="Limiar Confiança:").grid(
            row=row_idx, column=0, sticky="w", padx=(5, 2), pady=2
        )
        create_help_label(
            params_frame,
            "Limiar de Confiança (Confidence Threshold)\n\n"
            "Probabilidade mínima (0.0 a 1.0) para considerar uma detecção válida.\n"
            "• Aumente (ex: 0.50) se houver muitos 'falsos positivos' (ruído/fantasmas).\n"
            "• Diminua (ex: 0.15) se o peixe não estiver sendo detectado em alguns frames.\n"
            "• Padrão recomendado: 0.25",
        ).grid(row=row_idx, column=1, padx=2)

        ttk.Entry(params_frame, textvariable=self.confidence_threshold_var, width=8).grid(
            row=row_idx, column=2, sticky="w", padx=5
        )

        # NMS Threshold
        ttk.Label(params_frame, text="Limiar NMS:").grid(
            row=row_idx, column=3, sticky="w", padx=(15, 2), pady=2
        )
        create_help_label(
            params_frame,
            "Limiar NMS (Non-Maximum Suppression)\n\n"
            "Controla a remoção de caixas duplicadas para o mesmo objeto.\n"
            "• Valores baixos (ex: 0.4) fundem caixas sobrepostas agressivamente.\n"
            "• Valores altos (ex: 0.7) permitem mais sobreposição.\n"
            "• Padrão recomendado: 0.50",
        ).grid(row=row_idx, column=4, padx=2)

        ttk.Entry(params_frame, textvariable=self.nms_threshold_var, width=8).grid(
            row=row_idx, column=5, sticky="w", padx=5
        )

        row_idx += 1

        # ByteTrack Toggle
        bytetrack_check = ttk.Checkbutton(
            params_frame,
            text="Usar ByteTrack (Rastreamento Avançado)",
            variable=self.use_bytetrack_var,
            command=self._toggle_bytetrack_options,
        )
        bytetrack_check.grid(row=row_idx, column=0, columnspan=6, sticky="w", padx=5, pady=(15, 5))
        row_idx += 1

        self.bytetrack_hint_var = StringVar()
        self.bytetrack_hint_label = ttk.Label(
            params_frame,
            textvariable=self.bytetrack_hint_var,
            font=("Segoe UI", 8, "italic"),
            foreground="#555555",
            wraplength=450,
            justify="left",
        )
        self.bytetrack_hint_label.grid(
            row=row_idx, column=0, columnspan=6, sticky="w", padx=10, pady=(0, 10)
        )
        row_idx += 1

        # Tracking Params (Grouped)
        self.tracking_params_frame = ttk.Frame(params_frame)
        self.tracking_params_frame.grid(row=row_idx, column=0, columnspan=6, sticky="ew")
        self.tracking_params_frame.columnconfigure(1, weight=0)
        self.tracking_params_frame.columnconfigure(2, weight=1)
        self.tracking_params_frame.columnconfigure(4, weight=0)
        self.tracking_params_frame.columnconfigure(5, weight=1)

        # --- Row 1: Track Thresh | Match Thresh ---
        t_row = 0

        # Track Thresh
        ttk.Label(self.tracking_params_frame, text="Track Thresh:").grid(
            row=t_row, column=0, sticky="w", padx=(5, 2)
        )
        create_help_label(
            self.tracking_params_frame,
            "Track Threshold (Rastreamento)\n\n"
            "Confiança mínima para INICIAR ou MANTER um rastro.\n"
            "• Define quão 'certo' o detector deve estar para criar um ID novo.\n"
            "• Aumente para evitar rastros de lixo/ruído.\n"
            "• Diminua para manter o ID de peixes difíceis de detectar.\n"
            "• Padrão recomendado: 0.25",
        ).grid(row=t_row, column=1, padx=2)

        self.track_entry = ttk.Entry(
            self.tracking_params_frame, textvariable=self.track_threshold_var, width=8
        )
        self.track_entry.grid(row=t_row, column=2, sticky="w", padx=5)

        # Match Thresh
        ttk.Label(self.tracking_params_frame, text="Match Thresh:").grid(
            row=t_row, column=3, sticky="w", padx=(15, 2)
        )
        create_help_label(
            self.tracking_params_frame,
            "Match Threshold\n\n"
            "Tolerância para associar uma nova detecção a um rastro existente.\n"
            "• Valores altos (ex: 0.8+) são mais permissivos (bom para movimentos rápidos).\n"
            "• Valores baixos (<0.5) são restritivos "
            "(evita troca de identidade, mas pode perder o rastro).\n"
            "• Padrão recomendado: 0.95",
        ).grid(row=t_row, column=4, padx=2)

        self.match_entry = ttk.Entry(
            self.tracking_params_frame, textvariable=self.match_threshold_var, width=8
        )
        self.match_entry.grid(row=t_row, column=5, sticky="w", padx=5)

        t_row += 1

        # --- Row 2: Track Buffer | Max Dist ---

        # Track Buffer
        ttk.Label(self.tracking_params_frame, text="Track Buffer:").grid(
            row=t_row, column=0, sticky="w", padx=(5, 2), pady=5
        )
        create_help_label(
            self.tracking_params_frame,
            "Track Buffer (Memória)\n\n"
            "Quantos frames o sistema 'lembra' do peixe após ele sumir (oclusão/falha).\n"
            "• Aumente (ex: 120) se o peixe some por muito tempo.\n"
            "• Diminua para deletar rastros perdidos rapidamente.\n"
            "• Padrão: 90 frames (~3s a 30fps)",
        ).grid(row=t_row, column=1, padx=2)

        self.buffer_entry = ttk.Entry(
            self.tracking_params_frame, textvariable=self.track_buffer_var, width=8
        )
        self.buffer_entry.grid(row=t_row, column=2, sticky="w", padx=5)

        # Max Dist
        ttk.Label(self.tracking_params_frame, text="Dist. Máx (px):").grid(
            row=t_row, column=3, sticky="w", padx=(15, 2)
        )
        create_help_label(
            self.tracking_params_frame,
            "Distância Máxima (pixels)\n\n"
            "O quanto o centro do peixe pode se mover entre frames processados.\n"
            "• Impede associações impossíveis (teletransporte).\n"
            "• Aumente se o peixe é rápido ou se a taxa de frames é baixa.\n"
            "• Diminua se houver trocas de ID entre peixes distantes.\n"
            "• Padrão: 400.0 px",
        ).grid(row=t_row, column=4, padx=2)

        self.dist_entry = ttk.Entry(
            self.tracking_params_frame, textvariable=self.max_center_dist_var, width=8
        )
        self.dist_entry.grid(row=t_row, column=5, sticky="w", padx=5)

        t_row += 1

        # --- Row 3: IoU Thresh ---

        # IoU Thresh
        ttk.Label(self.tracking_params_frame, text="IoU Thresh:").grid(
            row=t_row, column=0, sticky="w", padx=(5, 2)
        )
        create_help_label(
            self.tracking_params_frame,
            "IoU Threshold (Rastreamento)\n\n"
            "Sobreposição mínima (Intersection over Union) para associar caixas.\n"
            "• Padrão: 0.05 (baixa exigência).\n"
            "• Aumente (ex: 0.3) para exigir que o peixe mantenha quase a mesma posição.\n"
            "• Diminua para permitir movimentos bruscos que mudam a área da caixa.",
        ).grid(row=t_row, column=1, padx=2)

        self.iou_entry = ttk.Entry(
            self.tracking_params_frame, textvariable=self.iou_threshold_var, width=8
        )
        self.iou_entry.grid(row=t_row, column=2, sticky="w", padx=5)

        row_idx += 1

        if include_model_test:
            ttk.Label(params_frame, text="Modelo(s) a Testar:").grid(
                row=row_idx, column=0, sticky="w", padx=5, pady=(15, 2)
            )
            self.model_test_dropdown = ttk.Combobox(
                params_frame,
                textvariable=self.model_test_var,
                state="readonly",
                values=["YOLO (PyTorch)", "OpenVINO", "Ambos"],
                width=15,
            )
            self.model_test_dropdown.grid(
                row=row_idx, column=1, columnspan=2, sticky="w", padx=5, pady=(15, 2)
            )
        else:
            self.model_test_dropdown = None

        self._toggle_bytetrack_options()

    def _toggle_bytetrack_options(self) -> None:
        """Enable/Disable tracking inputs based on checkbox."""
        # Guard: widgets may not exist during initialization
        if not hasattr(self, "track_entry") or self.track_entry is None:
            return

        enabled = self.use_bytetrack_var.get()
        state = "normal" if enabled else "disabled"
        for widget in [
            self.track_entry,
            self.match_entry,
            self.buffer_entry,
            self.dist_entry,
            self.iou_entry,
        ]:
            try:
                widget.configure(state=state)
            except Exception:
                log.debug("calibration_dialog.widget_state_config.suppressed", exc_info=True)

        if not enabled:
            self.bytetrack_hint_var.set(
                "ℹ️ ByteTrack desativado. Usando rastreamento simples (Híbrido) "
                "que utiliza apenas 'Distância Máxima' e 'IoU Threshold' para manter o ID."
            )
            # Distance and IoU are used by Simple Tracker
            for widget in [self.dist_entry, self.iou_entry]:
                try:
                    widget.configure(state="normal")
                except Exception:
                    log.debug("calibration_dialog.widget_reenable.suppressed", exc_info=True)
        else:
            self.bytetrack_hint_var.set(
                "💡 ByteTrack ativo (Filtro de Kalman). Recomendado para maior estabilidade."
            )

    def _prefill_detector_parameters(self) -> None:
        resolved_params, project_params = self._collect_prefill_detector_params()
        if not resolved_params:
            return

        self._set_parameter_fields(resolved_params)

        if project_params and self.scope_info.get("scope") == "project":
            project_name = self.scope_info.get("project_name")
            label = (
                f"Escopo: Projeto ({project_name}) - Overrides Locais"
                if project_name
                else ("Escopo: Projeto - Overrides Locais")
            )
            self.scope_label_var.set(label)
            self.scope_detail_var.set(
                "Os parâmetros exibidos correspondem às preferências deste projeto. "
                "Ajustes aplicados aqui atualizam apenas este projeto."
            )

    def _collect_prefill_detector_params(self) -> tuple[dict[str, Any], dict[str, Any]]:
        def _extract_params(source: dict | None) -> dict[str, Any]:
            mapping = {
                "confidence_threshold": "confidence_threshold",
                "conf_threshold": "confidence_threshold",
                "nms_threshold": "nms_threshold",
                "track_threshold": "track_threshold",
                "match_threshold": "match_threshold",
                "track_buffer": "track_buffer",
                "max_center_distance": "max_center_distance",
                "iou_threshold": "iou_threshold",
                "use_bytetrack": "use_bytetrack",
            }

            resolved: dict[str, Any] = {}
            if not source:
                return resolved

            for key, target in mapping.items():
                if key not in source:
                    continue
                try:
                    if target == "use_bytetrack":
                        resolved[target] = bool(source[key])
                    elif target == "track_buffer":
                        resolved[target] = int(source[key])
                    else:
                        resolved[target] = float(source[key])
                except (TypeError, ValueError):
                    log.warning(
                        "ui.calibration.prefill.invalid_param",
                        key=key,
                        value=source[key],
                    )
            return resolved

        project_data = getattr(self.controller.project_manager, "project_data", {}) or {}
        overrides = project_data.get("model_overrides") or {}

        project_params = _extract_params(overrides.get("detector_parameters"))
        if not project_params:
            project_params = _extract_params(project_data.get("detector_config"))
        if not project_params:
            project_params = _extract_params(project_data.get("detector_state"))

        try:
            params = self.controller.hardware_vm.get_current_detector_parameters()
        except Exception:
            log.debug("calibration.get_detector_params.fallback")
            params = {}

        resolved_params = _extract_params(params)
        if project_params:
            resolved_params.update(project_params)

        return resolved_params, project_params

    def _set_parameter_fields(self, values: dict[str, Any]) -> None:
        field_map = {
            "confidence_threshold": self.confidence_threshold_var,
            "nms_threshold": self.nms_threshold_var,
            "track_threshold": self.track_threshold_var,
            "match_threshold": self.match_threshold_var,
            "track_buffer": self.track_buffer_var,
            "max_center_distance": self.max_center_dist_var,
            "iou_threshold": self.iou_threshold_var,
        }

        for key, var in field_map.items():
            raw_value = values.get(key)
            if raw_value is None:
                continue
            try:
                if key == "track_buffer":
                    var.set(str(int(raw_value)))
                else:
                    var.set(
                        f"{float(raw_value):.2f}"
                        if isinstance(raw_value, float)
                        else str(raw_value)
                    )
            except (TypeError, ValueError):
                log.warning("ui.calibration.prefill.coerce_failed", key=key, value=raw_value)

        if "use_bytetrack" in values:
            self.use_bytetrack_var.set(bool(values["use_bytetrack"]))
            self._toggle_bytetrack_options()

    def _reload_project_parameters(self) -> None:
        _, project_params = self._collect_prefill_detector_params()
        if not project_params:
            messagebox.showinfo(
                "Sem overrides",
                "Este projeto ainda não possui overrides salvos. "
                "Valores globais atuais serão mantidos.",
            )
            return

        self._set_parameter_fields(project_params)

    def _apply_detector_parameters(self, scope_override: str | None = None) -> None:
        scope = scope_override or self.scope
        try:
            conf = float(self.confidence_threshold_var.get())
            nms = float(self.nms_threshold_var.get())

            use_bytetrack = self.use_bytetrack_var.get()
            track_thresh = float(self.track_threshold_var.get())
            match_thresh = float(self.match_threshold_var.get())
            track_buffer = int(self.track_buffer_var.get())
            max_dist = float(self.max_center_dist_var.get())
            iou_thresh = float(self.iou_threshold_var.get())
        except (TypeError, ValueError):
            messagebox.showerror(
                "Erro",
                "Insira valores numéricos válidos para os parâmetros do detector.",
            )
            return

        for label, value in (
            ("limiar de confiança", conf),
            ("limiar NMS", nms),
            ("track threshold", track_thresh),
            ("match threshold", match_thresh),
            ("IoU threshold", iou_thresh),
        ):
            if not 0.0 < value < 1.0:
                messagebox.showerror(
                    "Erro",
                    f"O {label} deve estar entre 0 e 1.",
                )
                return

        if track_buffer < 1:
            messagebox.showerror("Erro", "Track Buffer deve ser pelo menos 1 frame.")
            return
        if max_dist <= 0:
            messagebox.showerror("Erro", "Distância Máxima deve ser maior que 0.")
            return

        try:
            updated = self.controller.hardware_vm.update_detector_parameters(
                {
                    "confidence_threshold": conf,
                    "nms_threshold": nms,
                    "use_bytetrack": use_bytetrack,
                    "track_threshold": track_thresh,
                    "match_threshold": match_thresh,
                    "track_buffer": track_buffer,
                    "max_center_distance": max_dist,
                    "iou_threshold": iou_thresh,
                    "scope": scope,
                }
            )
        except ValidationError as exc:  # pragma: no cover - defensive
            messagebox.showerror("Erro", str(exc))
            return

        if updated:
            messagebox.showinfo(
                "Parâmetros Atualizados",
                "As configurações do detector foram aplicadas com sucesso.",
            )
        else:
            messagebox.showwarning(
                "Sem alterações",
                "Os parâmetros informados já estavam em uso.",
            )

    def _restore_detector_defaults(self, scope_override: str | None = None) -> None:
        scope = scope_override or self.scope
        try:
            restored = self.controller.hardware_vm.restore_detector_defaults(scope=scope)
        except Exception as exc:  # pragma: no cover - defensive
            messagebox.showerror("Erro", str(exc))
            return

        if restored:
            resolved_params, _ = self._collect_prefill_detector_params()
            self._set_parameter_fields(resolved_params)
            messagebox.showinfo(
                "Parâmetros do Detector",
                "Parâmetros padrão restaurados.",
            )

    def _populate_weights_dropdown(self):
        if not self.weights_dropdown:
            return
        weights_list = self.controller.hardware_vm.get_all_weight_names()
        self.weights_dropdown["values"] = weights_list
        if not weights_list:
            self.active_weight_var.set("Nenhum peso encontrado.")
            self.weights_dropdown.config(state="disabled")
        else:
            self.weights_dropdown.config(state="readonly")
            current_weight = self.controller.hardware_vm.active_weight_name
            if current_weight in weights_list:
                self.active_weight_var.set(current_weight)
            elif weights_list:
                self.active_weight_var.set(weights_list[0])

    def _on_weight_selected_local(self, event=None):
        selected_weight = self.active_weight_var.get()
        from zebtrack.ui.payloads import ModelSetWeightPayload

        self.controller.ui_event_bus.publish(
            Event(
                type=UIEvents.MODEL_SET_WEIGHT,
                data=ModelSetWeightPayload(name=selected_weight, dialog=self),
            )
        )

    def _on_openvino_toggled_local(self):
        from zebtrack.ui.payloads import ModelSetOpenVinoPayload

        self.controller.ui_event_bus.publish(
            Event(
                type=UIEvents.MODEL_SET_OPENVINO,
                data=ModelSetOpenVinoPayload(
                    use_openvino=self.use_openvino_var.get(),
                    dialog=self,
                ),
            )
        )
        # Enable/disable device combobox based on OpenVINO toggle
        if hasattr(self, "device_combobox"):
            if self.use_openvino_var.get():
                self.device_combobox.configure(state="readonly")
            else:
                self.device_combobox.configure(state="disabled")

    def update_openvino_status_label(self, status: str):
        """Update the OpenVINO status label with current status.

        Args:
            status: Status string to display.
        """
        self.openvino_status_var.set(status)
        if not self.openvino_status_label:
            return

    def _populate_device_combobox(self):
        """Populate device combobox with only detected OpenVINO devices."""
        from zebtrack.utils.hardware_detection import get_openvino_devices

        devices = list(get_openvino_devices())
        # Build user-facing options: AUTO always first, then detected devices
        options = ["AUTO"]
        for d in ("CPU", "GPU", "NPU"):
            if any(d in dev for dev in devices):
                options.append(d)
        self.device_combobox["values"] = options

        # Restore current setting
        if hasattr(self.controller, "settings_obj") and self.controller.settings_obj is not None:
            current = self.controller.settings_obj.openvino.device
            if current in options:
                self.device_var.set(current)
            else:
                self.device_var.set("AUTO")
        else:
            self.device_var.set("AUTO")

    def _on_device_selected(self, _event=None):
        """Handle device combobox selection change."""
        selected_device = self.device_var.get()
        log.info("calibration.device_selected", device=selected_device)
        # Publish event so hardware_vm / settings sync picks it up
        from zebtrack.ui.payloads import ModelSetOpenVinoPayload

        self.controller.ui_event_bus.publish(
            Event(
                type=UIEvents.MODEL_SET_OPENVINO,
                data=ModelSetOpenVinoPayload(
                    use_openvino=self.use_openvino_var.get(),
                    device=selected_device,
                    dialog=self,
                ),
            )
        )

    def _load_new_weight_local(self):
        if not self.weights_dropdown:
            return
        self.controller.ui_event_bus.publish(
            Event(type=UIEvents.UI_REQUEST_WEIGHT_FILE, data=payloads.EmptyPayload())
        )
        self._populate_weights_dropdown()

    # ------------------------------------------------------------------
    # Inline weights catalog — selection helpers (formerly ManageWeightsDialog)
    # ------------------------------------------------------------------

    def _publish_model_event(self, event_type: UIEvents, payload) -> None:
        bus = getattr(self.controller, "ui_event_bus", None)
        if bus is None:
            log.error("calibration.no_event_bus", event=event_type.name)
            return
        bus.publish(Event(type=event_type, data=payload))

    def _selected_weight_names(self) -> list[str]:
        if not self.weights_treeview:
            return []
        selection = self.weights_treeview.selection()
        if not selection:
            messagebox.showwarning(
                "Nenhuma Seleção",
                "Por favor, selecione pelo menos um peso primeiro.",
                parent=self,
            )
            return []
        return [self.weights_treeview.item(iid)["values"][0] for iid in selection]

    def _selected_weight_name(self) -> str | None:
        names = self._selected_weight_names()
        return names[0] if names else None

    def _selected_weight_details(self) -> tuple[str, dict] | None:
        name = self._selected_weight_name()
        if not name:
            return None
        wm = self.controller.weight_manager
        details = wm.get_weight_details(name) if wm else None
        if not details:
            messagebox.showerror(
                "Peso não encontrado",
                f"Não foi possível encontrar dados para '{name}'.",
                parent=self,
            )
            return None
        return name, details

    # ------------------------------------------------------------------
    # Inline weights catalog — population
    # ------------------------------------------------------------------

    def _populate_slot_comboboxes(self) -> None:
        """Refresh the 4 slot dropdowns from WeightManager state."""
        wm = self.controller.weight_manager
        if not wm:
            return
        for (method, target), combo in self.slot_comboboxes.items():
            # Each slot can only host weights matching its ``method``.
            options = [
                name for name, details in wm.weights.items() if details.get("type") == method
            ]
            combo["values"] = sorted(options)
            current_name, _ = wm.get_default_weight_for(method, target)
            self.slot_vars[(method, target)].set(current_name or "")

    def _populate_weights_treeview(self) -> None:
        """Re-render the inline weights catalog Treeview from WeightManager."""
        if not self.weights_treeview:
            return
        for item in self.weights_treeview.get_children():
            self.weights_treeview.delete(item)

        wm = self.controller.weight_manager
        if not wm:
            return
        weights = self.controller.hardware_vm.get_all_weight_names()
        self._weights_validation = wm.validate_weight_files()

        for name in sorted(weights):
            details = wm.get_weight_details(name)
            if not details:
                continue

            weight_type = details.get("type", "seg")
            target = details.get("target", "zebrafish" if weight_type == "seg" else "aquarium")
            perspective = details.get("perspective")
            type_label = _METHOD_LABELS.get(weight_type, weight_type)
            target_label = _TARGET_LABELS.get(target, target)
            perspective_label = _PERSPECTIVE_LABELS.get(perspective, "—") if perspective else "—"
            defaults = self._format_default_slots(details, weight_type)
            openvino_status = _OPENVINO_STATUS_LABELS.get(
                details.get("openvino_status", "not_converted"), "—"
            )

            tags: tuple[str, ...] = ()
            if not self._weights_validation.get(name, True):
                tags = ("missing",)
                openvino_status = "⚠ Arquivo ausente"

            self.weights_treeview.insert(
                "",
                "end",
                iid=name,
                values=(
                    name,
                    type_label,
                    target_label,
                    perspective_label,
                    defaults,
                    openvino_status,
                ),
                tags=tags,
            )

    @staticmethod
    def _format_default_slots(details: dict, weight_type: str) -> str:
        slots: list[str] = []
        if details.get("is_default_seg_aquarium"):
            slots.append("Seg-Aq")
        if details.get("is_default_seg_zebrafish"):
            slots.append("Seg-Zb")
        if details.get("is_default_det_aquarium"):
            slots.append("Det-Aq")
        if details.get("is_default_det_zebrafish"):
            slots.append("Det-Zb")
        if not slots:
            if details.get("is_default_seg") and weight_type == "seg":
                slots.append("Seg (legado)")
            if details.get("is_default_det") and weight_type == "det":
                slots.append("Det (legado)")
        return ", ".join(slots) if slots else "—"

    def _refresh_weights_catalog(self) -> None:
        """Convenience: refresh treeview + slot comboboxes + diagnostic dropdown."""
        self._populate_weights_treeview()
        self._populate_slot_comboboxes()
        self._populate_weights_dropdown()
        # Push the change up to the welcome / project status panel as well.
        gui = getattr(getattr(self.controller, "view", None), "gui", None)
        if gui is None:
            gui = getattr(self.controller, "view", None)
        weight_hw = getattr(gui, "weight_hardware_manager", None) if gui else None
        if weight_hw is not None:
            weight_hw.refresh_weights_summary()

    # ------------------------------------------------------------------
    # Inline weights catalog — slot defaults (used by combobox row)
    # ------------------------------------------------------------------

    def _on_slot_default_selected(self, method: str, target: str) -> None:
        chosen_name = self.slot_vars[(method, target)].get()
        if not chosen_name:
            return
        self._publish_model_event(
            UIEvents.MODEL_SET_DEFAULT_FOR,
            payloads.ModelSetDefaultForPayload(name=chosen_name, method=method, target=target),
        )
        # Schedule a refresh after the worker mutates state.
        self.after(150, self._refresh_weights_catalog)

    # ------------------------------------------------------------------
    # Inline weights catalog — actions (port from ManageWeightsDialog)
    # ------------------------------------------------------------------

    def _on_add_weight(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecionar arquivo de peso",
            filetypes=[("Modelos YOLO", "*.pt"), ("Todos os arquivos", "*.*")],
            parent=self,
        )
        if not path:
            return
        self._publish_model_event(
            UIEvents.MODEL_LOAD_NEW_WEIGHT,
            payloads.ModelLoadNewWeightPayload(weight_path=path, weight_type=None),
        )
        self.after(250, self._refresh_weights_catalog)

    def _on_delete_weight(self) -> None:
        name = self._selected_weight_name()
        if not name:
            return
        if not messagebox.askyesno(
            "Confirmar Exclusão",
            f"Excluir o registro do peso '{name}'?\n\n(O arquivo .pt em disco não será apagado.)",
            parent=self,
        ):
            return
        self._publish_model_event(
            UIEvents.MODEL_DELETE_WEIGHT,
            payloads.ModelDeleteWeightPayload(name=name),
        )
        self.after(150, self._refresh_weights_catalog)

    def _on_change_target(self) -> None:
        sel = self._selected_weight_details()
        if not sel:
            return
        name, details = sel
        current = details.get("target", "zebrafish")
        new_label = simpledialog.askstring(
            "Alterar Alvo",
            f"Alvo atual de '{name}': {_TARGET_LABELS.get(current, current)}\n\n"
            "Digite o novo alvo: 'aquario' ou 'zebrafish'",
            parent=self,
        )
        if not new_label:
            return
        normalized = new_label.strip().lower()
        if normalized in ("aquario", "aquário", "aquarium", "tank"):
            new_target = "aquarium"
        elif normalized in ("zebrafish", "fish", "animal", "peixe"):
            new_target = "zebrafish"
        else:
            messagebox.showerror(
                "Alvo inválido",
                f"Alvo '{new_label}' não reconhecido. Use 'aquario' ou 'zebrafish'.",
                parent=self,
            )
            return
        if new_target == current:
            return
        self._publish_model_event(
            UIEvents.MODEL_RECLASSIFY_TARGET,
            payloads.ModelReclassifyTargetPayload(name=name, target=new_target),
        )
        self.after(150, self._refresh_weights_catalog)

    def _on_validate_paths(self) -> None:
        wm = self.controller.weight_manager
        if not wm:
            return
        self._weights_validation = wm.validate_weight_files()
        missing = [n for n, ok in self._weights_validation.items() if not ok]
        self._populate_weights_treeview()
        if missing:
            messagebox.showwarning(
                "Pesos com arquivo ausente",
                "Os seguintes pesos referenciam arquivos .pt que não foram "
                "encontrados em disco:\n\n  • " + "\n  • ".join(missing),
                parent=self,
            )
        else:
            messagebox.showinfo(
                "Validação concluída",
                "Todos os arquivos .pt registrados existem em disco.",
                parent=self,
            )

    def _on_convert_openvino(self) -> None:
        names = self._selected_weight_names()
        if not names:
            return
        wm = self.controller.weight_manager
        candidates: list[str] = []
        already_ready: list[str] = []
        for n in names:
            details = wm.get_weight_details(n) if wm else None
            if not details:
                continue
            if details.get("openvino_status") == "ready":
                already_ready.append(n)
            else:
                candidates.append(n)

        if not candidates:
            messagebox.showinfo(
                "Nada a converter",
                "Os pesos selecionados já estão convertidos para OpenVINO. "
                "Use 'Apagar Cache OpenVINO' antes para forçar reconversão.",
                parent=self,
            )
            return

        plural = len(candidates) > 1
        msg = (
            f"Converter {len(candidates)} pesos para OpenVINO agora?\n\n"
            "  • " + "\n  • ".join(candidates)
            if plural
            else f"Converter '{candidates[0]}' para OpenVINO agora?"
        )
        msg += (
            "\n\nA conversão roda em background; o status na coluna 'OpenVINO' "
            "será atualizado a cada ~1.5s até concluir."
        )
        if already_ready:
            msg += f"\n\n({len(already_ready)} peso(s) já estão prontos e foram ignorados.)"
        if not messagebox.askyesno("Conversão OpenVINO", msg, parent=self):
            return

        for name in candidates:
            self._publish_model_event(
                UIEvents.MODEL_CONVERT_OPENVINO,
                payloads.ModelConvertOpenVinoPayload(weight_name=name),
            )
        self.after(150, self._populate_weights_treeview)
        self._start_conversion_poller()

    def _on_clear_cache_selected(self) -> None:
        name = self._selected_weight_name()
        if not name:
            return
        if not messagebox.askyesno(
            "Apagar cache OpenVINO",
            f"Apagar o cache OpenVINO de '{name}'?",
            parent=self,
        ):
            return
        report = self.controller.hardware_vm.clear_openvino_cache(name)
        self._show_cache_clear_report(report, scope=name)
        self._populate_weights_treeview()

    def _on_clear_cache_all(self) -> None:
        if not messagebox.askyesno(
            "Apagar TODOS os caches",
            "Esta ação remove TODOS os modelos OpenVINO convertidos.\n\n"
            "Eles serão regenerados na próxima detecção. Continuar?",
            parent=self,
            icon="warning",
        ):
            return
        if not messagebox.askyesno(
            "Confirmação adicional",
            "Confirma a remoção de todos os caches OpenVINO?",
            parent=self,
            icon="warning",
        ):
            return
        report = self.controller.hardware_vm.clear_openvino_cache(None)
        self._show_cache_clear_report(report, scope=None)
        self._populate_weights_treeview()

    def _show_cache_clear_report(
        self,
        report: dict[str, list[str]] | None,
        *,
        scope: str | None,
    ) -> None:
        if not report:
            return
        cleared = report.get("cleared", [])
        locked = report.get("locked", [])
        orphans_locked = report.get("orphans_locked", [])

        if not locked and not orphans_locked:
            scope_label = f"do peso '{scope}'" if scope else "de todos os pesos"
            messagebox.showinfo(
                "Caches OpenVINO apagados",
                f"Cache OpenVINO {scope_label} removido com sucesso "
                f"({len(cleared)} entrada(s) processada(s)).\n\n"
                "O status na lista voltou para '—'; a próxima detecção "
                "regenerará o cache.",
                parent=self,
            )
            return

        parts: list[str] = []
        if cleared:
            parts.append(f"✓ {len(cleared)} cache(s) apagado(s) com sucesso.")
        if locked:
            parts.append(
                "⚠ Não foi possível apagar o cache dos seguintes pesos:\n  • "
                + "\n  • ".join(locked)
            )
        if orphans_locked:
            parts.append(
                "⚠ Pastas órfãs que resistiram à remoção:\n  • " + "\n  • ".join(orphans_locked)
            )
        parts.append(
            "\nCausa provável: o detector em execução ainda tem o modelo "
            "carregado em memória (handle aberto), ou o OneDrive está "
            "sincronizando os arquivos.\n\n"
            "Soluções:\n"
            "  1. Feche e reabra o ZebTrack-AI (libera o handle do modelo);\n"
            "  2. Pause o OneDrive temporariamente e tente de novo;\n"
            "  3. Use 'poetry run zebtrack --reset-openvino-cache' antes de "
            "iniciar o app — apaga o cache enquanto nada está carregado."
        )
        messagebox.showwarning("Caches parcialmente apagados", "\n\n".join(parts), parent=self)

    def _on_rescan_folder(self) -> None:
        wm = self.controller.weight_manager
        before = set(wm.weights.keys()) if wm else set()
        self._publish_model_event(UIEvents.MODEL_RESCAN_WEIGHTS, payloads.EmptyPayload())
        self.after(180, self._refresh_weights_catalog)
        if wm:
            after = set(wm.weights.keys())
            new = after - before
            if new:
                messagebox.showinfo(
                    "Reescaneamento",
                    f"{len(new)} novo(s) peso(s) detectado(s):\n  • " + "\n  • ".join(sorted(new)),
                    parent=self,
                )
            else:
                messagebox.showinfo(
                    "Reescaneamento",
                    f"Nenhum peso novo encontrado em '{wm.weights_dir}'.",
                    parent=self,
                )

    def _on_reset_registry(self) -> None:
        if not messagebox.askyesno(
            "Reset de fábrica",
            "Esta ação apaga 'weights_config.json' e refaz o registro a partir das "
            "configurações + scan da pasta 'weights/'.\n\n"
            "Defaults personalizados serão perdidos. Continuar?",
            parent=self,
            icon="warning",
        ):
            return
        if not messagebox.askyesno(
            "Confirmação adicional",
            "Confirma o reset da lista de pesos para o estado de fábrica?",
            parent=self,
            icon="warning",
        ):
            return
        self._publish_model_event(UIEvents.MODEL_RESET_REGISTRY, payloads.EmptyPayload())
        self.after(200, self._refresh_weights_catalog)

    def _on_force_benchmark(self) -> None:
        if not messagebox.askyesno(
            "Reexecutar benchmark",
            "O benchmark levará ~10-30 segundos e atualizará as configurações "
            "ótimas do OpenVINO. Continuar?",
            parent=self,
        ):
            return
        self._publish_model_event(UIEvents.MODEL_FORCE_BENCHMARK, payloads.EmptyPayload())
        messagebox.showinfo(
            "Benchmark em execução",
            "O benchmark está rodando em background. As configurações serão "
            "aplicadas automaticamente ao terminar.",
            parent=self,
        )

    def _on_open_cache_folder(self) -> None:
        wm = self.controller.weight_manager
        if not wm:
            return
        cache_dir = Path(wm.config_dir) / "openvino_model_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(str(cache_dir))  # type: ignore[attr-defined]
            else:
                import subprocess

                opener = "open" if os.uname().sysname == "Darwin" else "xdg-open"  # type: ignore[attr-defined]
                subprocess.Popen([opener, str(cache_dir)])
        # except Exception justified: opening folder is best-effort UX.
        except Exception as e:
            messagebox.showwarning(
                "Falha ao abrir pasta",
                f"Não foi possível abrir o explorador na pasta:\n{cache_dir}\n\n{e}",
                parent=self,
            )

    # ------------------------------------------------------------------
    # OpenVINO conversion poller (was inside ManageWeightsDialog)
    # ------------------------------------------------------------------

    def _start_conversion_poller(self) -> None:
        if self._conversion_poller_id is not None:
            return
        self._conversion_poller_id = self.after(
            _CONVERSION_POLL_INTERVAL_MS, self._poll_conversion_status
        )

    def _poll_conversion_status(self) -> None:
        self._conversion_poller_id = None
        wm = self.controller.weight_manager
        if not wm:
            return
        converting = [
            name
            for name, details in wm.weights.items()
            if details.get("openvino_status") == "converting"
        ]
        try:
            self._populate_weights_treeview()
        # except Exception justified: dialog may be closing — don't crash.
        except Exception as exc:
            log.debug("calibration.poll.populate_failed", error=str(exc))
            return
        if converting:
            self._conversion_poller_id = self.after(
                _CONVERSION_POLL_INTERVAL_MS, self._poll_conversion_status
            )

    def destroy(self):
        # Cancel the conversion poller (if running) so it doesn't fire on a
        # destroyed widget.
        poller_id = self._conversion_poller_id
        if poller_id is not None:
            with contextlib.suppress(Exception):
                self.after_cancel(poller_id)
            self._conversion_poller_id = None
        super().destroy()

    def _select_diagnostic_video(self):
        path = filedialog.askopenfilename(
            title="Selecione o Vídeo para Diagnóstico",
            filetypes=[("Arquivos de vídeo", "*.mp4 *.avi *.mov")],
        )
        if path:
            self.diagnostic_video_path = path
            self.video_path_label_var.set(os.path.basename(path))

    def _run_diagnostic_test(self):
        if not self.diagnostic_video_path:
            messagebox.showerror("Erro", "Por favor, selecione um arquivo de vídeo.")
            return

        try:
            frames = int(self.frames_to_analyze_var.get())
            if frames <= 0:
                messagebox.showerror("Erro", "O número de frames deve ser um inteiro positivo.")
                return
        except ValueError:
            messagebox.showerror("Erro", "O número de frames deve ser um número inteiro.")
            return

        try:
            conf = float(self.confidence_threshold_var.get())
            if not 0.0 <= conf <= 1.0:
                messagebox.showerror(
                    "Erro", "O limiar de confiança deve ser um número entre 0.0 e 1.0."
                )
                return
        except ValueError:
            messagebox.showerror("Erro", "O limiar de confiança deve ser um número válido.")
            return

        config = {
            "video_path": self.diagnostic_video_path,
            "frames_to_analyze": int(self.frames_to_analyze_var.get()),
            "confidence_threshold": float(self.confidence_threshold_var.get()),
            "model_to_test": self.model_test_var.get(),
            "parent_dialog": self,
        }

        from zebtrack.ui.payloads import ModelRunDiagnosticPayload

        self.controller.ui_event_bus.publish(
            Event(
                type=UIEvents.MODEL_RUN_DIAGNOSTIC,
                data=ModelRunDiagnosticPayload(config=config),
            )
        )

    def buttonbox(self):
        """Create custom button box with calibration action buttons."""
        box = ttk.Frame(self)
        w = ttk.Button(box, text="Fechar", width=10, command=self.ok, default="active")
        w.pack(side="left", padx=5, pady=5)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack()

    def _get_scope_action_text(self, scope_info: dict) -> str | None:
        if not scope_info.get("project_loaded"):
            return None
        if scope_info.get("scope") == "global":
            return "Copiar globais para o projeto"
        return "Salvar calibração neste projeto"

    def _refresh_scope_context(self) -> None:
        self.scope_info = self.controller.project_vm.get_calibration_scope_info()
        self.scope = self.scope_info.get("scope", self.scope)
        self.scope_label_var.set(self.scope_info["label"])
        self.scope_detail_var.set(self.scope_info["detail"])

        if self.calibration_section:
            self._build_calibration_section()

        if self.preferences_section:
            project_ready = self.scope == "project" and self.scope_info.get("project_loaded")
            if project_ready:
                # Preferences section is managed by CollapsibleFrame, just rebuild content
                self._build_preferences_section()
            else:
                self._clear_frame(self.preferences_section)

        if self.scope_action_button:
            action_text = self._get_scope_action_text(self.scope_info)
            if action_text:
                self.scope_action_button.config(text=action_text, state="normal")
            else:
                self.scope_action_button.config(state="disabled")

    def _on_scope_primary_action(self) -> None:
        if not self.scope_info.get("project_loaded"):
            return

        project_name = self.scope_info.get("project_name") or "projeto"
        if self.scope_info.get("scope") == "global":
            from zebtrack.ui.payloads import CalibrationCopyToProjectPayload

            self.controller.ui_event_bus.publish(
                Event(
                    type=UIEvents.CALIBRATION_COPY_TO_PROJECT,
                    data=CalibrationCopyToProjectPayload(),
                )
            )
            result = True
            if result:
                messagebox.showinfo(
                    "Projeto atualizado",
                    f"Os padrões globais foram copiados para o projeto {project_name}.",
                )
        else:
            from zebtrack.ui.payloads import CalibrationSaveToProjectPayload

            self.controller.ui_event_bus.publish(
                Event(
                    type=UIEvents.CALIBRATION_SAVE_TO_PROJECT,
                    data=CalibrationSaveToProjectPayload(),
                )
            )
            result = True
            if result:
                messagebox.showinfo(
                    "Overrides salvos",
                    f"A calibração atual foi salva como override para o projeto {project_name}.",
                )

        self._populate_weights_dropdown()
        self.use_openvino_var.set(self.controller.hardware_vm.use_openvino)
        self._refresh_scope_context()
