"""Focused dialog for model diagnostics."""

from __future__ import annotations

from tkinter import simpledialog, ttk

import structlog

from zebtrack.ui.components.model_diagnostics_panel import ModelDiagnosticsPanel
from zebtrack.ui.icon_utils import set_window_icon
from zebtrack.ui.window_utils import schedule_maximize

log = structlog.get_logger()


class ModelDiagnosticsDialog(simpledialog.Dialog):
    """Dialog dedicated to global model diagnostics."""

    def __init__(self, parent, controller) -> None:
        self.controller = controller
        super().__init__(parent, "Diagnóstico Global do Modelo")

        try:
            set_window_icon(self)
        except Exception:
            log.warning("icon.set.failed", exc_info=True)

    def body(self, master):
        master.pack_configure(fill="both", expand=True)
        schedule_maximize(self)

        self.panel = ModelDiagnosticsPanel(
            master,
            self.controller,
            scope="global",
            parent_dialog=self,
        )
        self.panel.pack(fill="both", expand=True, padx=5, pady=5)
        return self.panel

    def buttonbox(self):
        box = ttk.Frame(self)
        ttk.Button(
            box,
            text="Fechar",
            width=10,
            command=self.cancel,
            default="active",
        ).pack(side="right", padx=5, pady=5)
        self.bind("<Escape>", self.cancel)
        box.pack(fill="x", padx=5, pady=(0, 5))
