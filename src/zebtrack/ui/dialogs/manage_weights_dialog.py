"""
ManageWeightsDialog.

Extracted from gui.py for better modularity.
"""

from collections.abc import Callable
from tkinter import (
    messagebox,
    simpledialog,
    ttk,
)
from typing import Any

from zebtrack.ui.event_bus_v2 import Event, UIEvents
from zebtrack.ui.window_utils import schedule_maximize


class ManageWeightsDialog(simpledialog.Dialog):
    """Dialog to manage the available weights."""

    def __init__(
        self,
        parent,
        controller,
        refresh_callback: Callable[..., Any] | None = None,
    ):
        """Initialize the manage weights dialog.

        Args:
            parent: Parent widget.
            controller: Main view model controller instance.
            refresh_callback: Optional callback to refresh UI after changes.
        """
        self.controller = controller
        self.refresh_callback = refresh_callback
        super().__init__(parent, "Gerenciar Pesos de Detecção")

    def body(self, master):
        """Create dialog body with weight list and management buttons.

        Args:
            master: Parent widget for dialog body.

        Returns:
            The initial focus widget.
        """
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
        """Populate the listbox with available weights from weight manager."""
        for item in self.listbox.get_children():
            self.listbox.delete(item)

        weights = self.controller.hardware_vm.get_all_weight_names()
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
        """Get the name of the currently selected weight.

        Returns:
            Weight name if selected, None otherwise.
        """
        selected = self.listbox.selection()
        if not selected:
            messagebox.showwarning("Nenhuma Seleção", "Por favor, selecione um peso primeiro.")
            return None
        return self.listbox.item(selected[0])["values"][0]

    def set_default_seg(self):
        """Set the selected weight as default for Segmentation."""
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

        try:
            self.controller.weight_manager.set_default_weight_by_type(name, "seg")
            self.populate_list()
            messagebox.showinfo(
                "Padrão Atualizado", f"'{name}' agora é o peso padrão para Segmentação (zebrafish)."
            )
        except OSError as e:
            messagebox.showerror(
                "Erro ao Definir Padrão", f"Não foi possível definir '{name}' como padrão: {e}"
            )

    def set_default_det(self):
        """Set the selected weight as default for Detection."""
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

        try:
            self.controller.weight_manager.set_default_weight_by_type(name, "det")
            self.populate_list()
            messagebox.showinfo(
                "Padrão Atualizado", f"'{name}' agora é o peso padrão para Detecção (aquário)."
            )
        except OSError as e:
            messagebox.showerror(
                "Erro ao Definir Padrão", f"Não foi possível definir '{name}' como padrão: {e}"
            )

    def set_default(self):
        """Legacy method kept for backwards compatibility."""
        name = self.get_selected_item_name()
        if name:
            try:
                self.controller.weight_manager.set_default_weight(name)
                self.populate_list()
            except OSError as e:
                messagebox.showerror(
                    "Erro ao Definir Padrão", f"Não foi possível definir '{name}' como padrão: {e}"
                )

    def delete(self):
        """Delete the currently selected weight after confirmation."""
        name = self.get_selected_item_name()
        if name:
            if messagebox.askyesno(
                "Confirmar Exclusão", f"Tem certeza que deseja excluir '{name}'?"
            ):
                self.controller.ui_event_bus.publish(
                    Event(type=UIEvents.MODEL_DELETE_WEIGHT, data={"name": name})
                )
                self.populate_list()

    def destroy(self):
        """Clean up and destroy the dialog window."""
        # Override destroy to call the callback if it exists
        if self.refresh_callback:
            self.refresh_callback()
        super().destroy()

    def buttonbox(self):
        """Create custom button box with Close button."""
        # Override to have only a close button
        box = ttk.Frame(self)
        w = ttk.Button(box, text="Fechar", width=10, command=self.ok, default="active")
        w.pack(side="left", padx=5, pady=5)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack()
