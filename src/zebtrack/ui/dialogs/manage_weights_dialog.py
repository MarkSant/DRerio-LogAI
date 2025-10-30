"""
ManageWeightsDialog

Extracted from gui.py for better modularity.
"""

from tkinter import (
    messagebox,
    simpledialog,
    ttk,
)
from typing import Any, Callable

from zebtrack.ui.events import Events
from zebtrack.ui.window_utils import schedule_maximize


class ManageWeightsDialog(simpledialog.Dialog):
    """Dialog to manage the available weights."""

    def __init__(
        self,
        parent,
        controller,
        refresh_callback: Callable[..., Any] | None = None,
    ):
        self.controller = controller
        self.refresh_callback = refresh_callback
        super().__init__(parent, "Gerenciar Pesos de Detecção")

    def body(self, master):
        schedule_maximize(self)

        # Treeview com colunas expandidas para mostrar tipo e padrões por tipo
        self.listbox = ttk.Treeview(
            master,
            columns=("name", "type", "default_seg", "default_det"),
            show="headings",
            height=8,
        )
        self.listbox.heading("name", text="Nome do Peso")
        self.listbox.heading("type", text="Tipo")
        self.listbox.heading("default_seg", text="Padrão Segmentação")
        self.listbox.heading("default_det", text="Padrão Detecção")

        self.listbox.column("name", width=200, stretch=True)
        self.listbox.column("type", width=120, anchor="center")
        self.listbox.column("default_seg", width=140, anchor="center")
        self.listbox.column("default_det", width=130, anchor="center")

        self.listbox.pack(padx=5, pady=5, fill="both", expand=True)

        self.populate_list()

        # Frame de informação
        info_frame = ttk.LabelFrame(master, text="Informações", padding=10)
        info_frame.pack(padx=5, pady=5, fill="x")

        ttk.Label(
            info_frame,
            text="• Segmentação: Para detectar peixes individuais (zebrafish)\n"
            "• Detecção: Para detectar aquários/arenas\n"
            "• Você pode ter um peso padrão diferente para cada tipo",
            justify="left",
            foreground="gray",
        ).pack(anchor="w")

        button_frame = ttk.Frame(master)
        button_frame.pack(pady=10)

        ttk.Button(
            button_frame, text="Padrão para Segmentação", command=self.set_default_seg, width=22
        ).pack(side="left", padx=5)

        ttk.Button(
            button_frame, text="Padrão para Detecção", command=self.set_default_det, width=22
        ).pack(side="left", padx=5)

        ttk.Button(button_frame, text="Excluir Selecionado", command=self.delete, width=18).pack(
            side="left", padx=5
        )

    def populate_list(self):
        for item in self.listbox.get_children():
            self.listbox.delete(item)

        weights = self.controller.get_all_weight_names()
        default_seg_name, _ = self.controller.weight_manager.get_default_seg_weight()
        default_det_name, _ = self.controller.weight_manager.get_default_det_weight()

        for name in sorted(weights):
            details = self.controller.weight_manager.get_weight_details(name)
            if not details:
                continue

            weight_type = details.get("type", "seg")
            type_label = "Segmentação" if weight_type == "seg" else "Detecção"

            is_default_seg = "✓ Sim" if name == default_seg_name else ""
            is_default_det = "✓ Sim" if name == default_det_name else ""

            self.listbox.insert(
                "", "end", values=(name, type_label, is_default_seg, is_default_det)
            )

    def get_selected_item_name(self):
        selected = self.listbox.selection()
        if not selected:
            messagebox.showwarning("Nenhuma Seleção", "Por favor, selecione um peso primeiro.")
            return None
        return self.listbox.item(selected[0])["values"][0]

    def set_default_seg(self):
        """Define o peso selecionado como padrão para Segmentação."""
        name = self.get_selected_item_name()
        if not name:
            return

        details = self.controller.weight_manager.get_weight_details(name)
        if not details:
            return

        weight_type = details.get("type", "seg")
        if weight_type != "seg":
            messagebox.showwarning(
                "Tipo Incompatível",
                f"O peso '{name}' é do tipo Detecção e não pode ser padrão para Segmentação.\n\n"
                "Selecione um peso do tipo Segmentação.",
            )
            return

        self.controller.weight_manager.set_default_weight_by_type(name, "seg")
        self.populate_list()
        messagebox.showinfo(
            "Padrão Atualizado", f"'{name}' agora é o peso padrão para Segmentação (zebrafish)."
        )

    def set_default_det(self):
        """Define o peso selecionado como padrão para Detecção."""
        name = self.get_selected_item_name()
        if not name:
            return

        details = self.controller.weight_manager.get_weight_details(name)
        if not details:
            return

        weight_type = details.get("type", "seg")
        if weight_type != "det":
            messagebox.showwarning(
                "Tipo Incompatível",
                f"O peso '{name}' é do tipo Segmentação e não pode ser padrão para Detecção.\n\n"
                "Selecione um peso do tipo Detecção.",
            )
            return

        self.controller.weight_manager.set_default_weight_by_type(name, "det")
        self.populate_list()
        messagebox.showinfo(
            "Padrão Atualizado", f"'{name}' agora é o peso padrão para Detecção (aquário)."
        )

    def set_default(self):
        """Método legado mantido para compatibilidade."""
        name = self.get_selected_item_name()
        if name:
            self.controller.weight_manager.set_default_weight(name)
            self.populate_list()

    def delete(self):
        name = self.get_selected_item_name()
        if name:
            if messagebox.askyesno(
                "Confirmar Exclusão", f"Tem certeza que deseja excluir '{name}'?"
            ):
                self.controller.ui_event_bus.publish_event(
                    Events.MODEL_DELETE_WEIGHT, {"name": name}
                )
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
