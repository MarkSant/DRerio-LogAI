"""Calibration dialog for global model tools and project fallbacks."""

from __future__ import annotations

import tkinter as tk
from tkinter import StringVar, filedialog, messagebox, simpledialog, ttk
from typing import Any

import structlog

from zebtrack.ui.collapsible_frame import CollapsibleFrame
from zebtrack.ui.components.global_model_configuration_panel import (
    GlobalModelConfigurationPanel,
)
from zebtrack.ui.components.model_diagnostics_panel import ModelDiagnosticsPanel
from zebtrack.ui.components.project_model_configuration_panel import (
    ProjectModelConfigurationPanel,
)
from zebtrack.ui.icon_utils import set_window_icon
from zebtrack.ui.window_utils import schedule_maximize

log = structlog.get_logger()


class CalibrationDialog(simpledialog.Dialog):
    """Dialog for global model configuration and project fallback tools."""

    def __init__(self, parent, controller, *, show_diagnostics: bool = True) -> None:
        self.controller = controller
        self.show_diagnostics = show_diagnostics

        self.scope_info = controller.project_vm.get_calibration_scope_info()
        self.scope = self.scope_info.get("scope", "global")
        self.scope_label_var = StringVar(value=self.scope_info.get("label", ""))
        self.scope_detail_var = StringVar(value=self.scope_info.get("detail", ""))

        self.calibration_card: CollapsibleFrame | None = None
        self.calibration_section: ttk.Frame | None = None
        self.scope_action_button: ttk.Button | None = None
        self.global_configuration_panel: GlobalModelConfigurationPanel | None = None
        self.global_diagnostics_panel: ModelDiagnosticsPanel | None = None

        super().__init__(parent, self._get_dialog_title())

        try:
            set_window_icon(self)
        except Exception:
            log.warning("icon.set.failed", exc_info=True)

    def body(self, master):
        master.pack_configure(fill="both", expand=True)
        schedule_maximize(self)

        container = self._make_scrollable_container(master)
        self.calibration_card = CollapsibleFrame(
            container,
            title=self._get_calibration_section_title(),
        )
        self.calibration_card.pack(fill="both", expand=True, padx=5, pady=5)

        self.calibration_section = self.calibration_card.get_content_frame()
        self._build_calibration_section()
        return self.calibration_section

    def _make_scrollable_container(self, master) -> ttk.Frame:
        outer = ttk.Frame(master)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y", pady=5)

        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_event: object) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event: Any) -> None:
            canvas.itemconfigure(inner_id, width=event.width)

        def _on_mousewheel(event: Any) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _on_button_scroll(event: Any) -> None:
            canvas.yview_scroll(-1 if event.num == 4 else 1, "units")

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.bind(
            "<Enter>",
            lambda _event: (
                canvas.bind_all("<MouseWheel>", _on_mousewheel),
                canvas.bind_all("<Button-4>", _on_button_scroll),
                canvas.bind_all("<Button-5>", _on_button_scroll),
            ),
        )
        canvas.bind(
            "<Leave>",
            lambda _event: (
                canvas.unbind_all("<MouseWheel>"),  # type: ignore[func-returns-value]
                canvas.unbind_all("<Button-4>"),  # type: ignore[func-returns-value]
                canvas.unbind_all("<Button-5>"),  # type: ignore[func-returns-value]
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
            log.debug("calibration_dialog.clear_frame.suppressed", exc_info=True)

    def _get_dialog_title(self) -> str:
        if self.scope_info.get("scope") == "project":
            return "Ferramentas de Modelos do Projeto"
        if self.show_diagnostics:
            return "Calibração e Diagnóstico"
        return "Configuração Global de Modelos"

    def _get_calibration_section_title(self) -> str:
        if self.scope == "project":
            return "📐 Ferramentas de Modelos do Projeto"
        if self.show_diagnostics:
            return "📐 Calibração e Diagnóstico"
        return "📐 Configuração Global de Modelos"

    def _build_calibration_section(self) -> None:
        if self.calibration_section is None:
            return

        self.global_configuration_panel = None
        self.global_diagnostics_panel = None
        self._clear_frame(self.calibration_section)

        if self.calibration_card is not None:
            self.calibration_card.title_label.config(text=self._get_calibration_section_title())

        scope_frame = ttk.Frame(self.calibration_section)
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
        else:
            self.scope_action_button = None

        if self.scope == "global":
            self._build_global_calibration_ui(self.calibration_section)
        else:
            self._build_project_tools_ui(self.calibration_section)

    def _build_project_tools_ui(self, master) -> None:
        ttk.Label(
            master,
            text=(
                "As ferramentas de configuração e diagnóstico deste projeto foram separadas "
                "em duas abas dedicadas. Este fallback reutiliza a mesma divisão quando a "
                "janela principal ainda não está disponível."
            ),
            wraplength=760,
            justify="left",
            foreground="#555555",
        ).pack(fill="x", padx=5, pady=(10, 8))

        notebook = ttk.Notebook(master)
        notebook.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        configuration_tab = ttk.Frame(notebook, padding=10)
        diagnostics_tab = ttk.Frame(notebook, padding=10)
        notebook.add(configuration_tab, text="Config. Modelo IA")
        notebook.add(diagnostics_tab, text="Diagnóstico Modelo IA")

        ProjectModelConfigurationPanel(configuration_tab, self.controller).pack(
            fill="both", expand=True
        )
        ModelDiagnosticsPanel(diagnostics_tab, self.controller, scope="project").pack(
            fill="both", expand=True
        )

    def _build_global_calibration_ui(self, master):
        self.global_configuration_panel = GlobalModelConfigurationPanel(master, self.controller)
        self.global_configuration_panel.pack(fill="both", expand=True, pady=5, padx=5)

        if not self.show_diagnostics:
            self.global_diagnostics_panel = None
            return

        diag_frame = ttk.LabelFrame(
            master,
            text="Diagnóstico de Desempenho do Modelo",
            padding=10,
        )
        diag_frame.pack(fill="x", pady=10, padx=5)

        self.global_diagnostics_panel = ModelDiagnosticsPanel(
            diag_frame,
            self.controller,
            scope="global",
            parent_dialog=self,
        )
        self.global_diagnostics_panel.pack(fill="both", expand=True)
        self.global_configuration_panel.set_weight_refresh_callback(
            self.global_diagnostics_panel.refresh_weight_options
        )

    def buttonbox(self):
        box = ttk.Frame(self)
        button = ttk.Button(box, text="Fechar", width=10, command=self.ok, default="active")
        button.pack(side="right", padx=5, pady=5)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack(fill="x", padx=5, pady=(0, 5))

    def _get_scope_action_text(self, scope_info: dict) -> str | None:
        if not scope_info.get("project_loaded"):
            return None
        if scope_info.get("scope") == "global":
            return "Copiar globais para o projeto"
        return None

    def _refresh_scope_context(self) -> None:
        self.scope_info = self.controller.project_vm.get_calibration_scope_info()
        self.scope = self.scope_info.get("scope", self.scope)
        self.scope_label_var.set(self.scope_info.get("label", ""))
        self.scope_detail_var.set(self.scope_info.get("detail", ""))

        if self.calibration_card is not None:
            self.calibration_card.title_label.config(text=self._get_calibration_section_title())

        if self.calibration_section is not None:
            self._build_calibration_section()

    def _ask_copy_target(self, project_name: str) -> str | None:
        """Pergunta a qual projeto aplicar os padrões globais.

        Returns:
            "current" para o projeto aberto, "other" para escolher outra
            pasta de projeto, None se cancelado.
        """
        result: dict[str, str | None] = {"choice": None}

        win = tk.Toplevel(self)
        win.title("Aplicar padrões globais")
        win.transient(self)
        win.resizable(False, False)

        ttk.Label(
            win,
            text=(
                "Aplicar os padrões globais de modelo a qual projeto?\n\n"
                f"Projeto aberto: {project_name}"
            ),
            justify="left",
            wraplength=440,
            padding=12,
        ).pack(fill="x")

        btn_row = ttk.Frame(win, padding=(12, 0, 12, 12))
        btn_row.pack(fill="x")

        def _choose(choice: str | None) -> None:
            result["choice"] = choice
            win.destroy()

        ttk.Button(
            btn_row,
            text=f"Projeto atual ({project_name})",
            command=lambda: _choose("current"),
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            btn_row,
            text="Escolher outra pasta…",
            command=lambda: _choose("other"),
        ).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="Cancelar", command=lambda: _choose(None)).pack(side="right")

        win.protocol("WM_DELETE_WINDOW", lambda: _choose(None))
        win.grab_set()
        win.wait_window()
        return result["choice"]

    def _on_scope_primary_action(self) -> None:
        if not self.scope_info.get("project_loaded"):
            return
        if self.scope_info.get("scope") != "global":
            return

        project_name = self.scope_info.get("project_name") or "projeto"
        choice = self._ask_copy_target(project_name)
        if choice is None:
            return

        if choice == "current":
            result = self.controller.project_vm.handle_calibration_copy_to_project()
            if result is not None:
                messagebox.showinfo(
                    "Projeto atualizado",
                    f"Os padrões globais foram copiados para o projeto {project_name}.",
                    parent=self,
                )
            else:
                messagebox.showerror(
                    "Falha ao copiar",
                    "Não foi possível aplicar os padrões globais ao projeto. "
                    "Verifique o log para detalhes.",
                    parent=self,
                )
        else:
            initial_dir = self.scope_info.get("project_path") or None
            target = filedialog.askdirectory(
                title="Selecione a pasta do projeto de destino",
                initialdir=initial_dir,
                parent=self,
            )
            if not target:
                return
            result = self.controller.project_vm.handle_calibration_copy_to_project_path(target)
            if result is not None:
                messagebox.showinfo(
                    "Projeto atualizado",
                    f"Os padrões globais foram copiados para o projeto em:\n{target}",
                    parent=self,
                )
            else:
                messagebox.showerror(
                    "Falha ao copiar",
                    "Não foi possível aplicar os padrões globais ao projeto "
                    "selecionado.\nVerifique se a pasta contém um projeto "
                    "ZebTrack válido (project_config.json).",
                    parent=self,
                )

        self._refresh_scope_context()
