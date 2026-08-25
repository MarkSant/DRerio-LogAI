"""
TemplateDialog.

Extracted from gui.py for better modularity.
"""

from tkinter import (
    StringVar,
    messagebox,
    simpledialog,
    ttk,
)

from zebtrack.i18n import _


class TemplateDialog(simpledialog.Dialog):
    """Dialog to create ROI templates."""

    def body(self, master):
        """Create template selection dialog body.

        Args:
            master: Parent widget for dialog body.

        Returns:
            The initial focus widget.
        """
        # Declare result attribute for type checking
        self.result: dict[str, object] | None = None

        self.template_type = StringVar(value="vertical")
        self.num_lanes = StringVar(value="3")
        self.num_rows = StringVar(value="2")
        self.num_cols = StringVar(value="2")

        ttk.Radiobutton(
            master,
            text=_("Vertical Lanes"),
            variable=self.template_type,
            value="vertical",
        ).pack(anchor="w")
        ttk.Radiobutton(
            master,
            text=_("Horizontal Lanes"),
            variable=self.template_type,
            value="horizontal",
        ).pack(anchor="w")
        ttk.Radiobutton(master, text=_("Grid"), variable=self.template_type, value="grid").pack(
            anchor="w"
        )

        ttk.Label(master, text=_("No. of Lanes:")).pack(anchor="w", pady=(5, 0))
        ttk.Entry(master, textvariable=self.num_lanes).pack(anchor="w")

        ttk.Label(master, text=_("Grid (Rows x Columns):")).pack(anchor="w", pady=(5, 0))
        grid_frame = ttk.Frame(master)
        grid_frame.pack(anchor="w")
        ttk.Entry(grid_frame, textvariable=self.num_rows, width=5).pack(side="left")
        ttk.Label(grid_frame, text="x").pack(side="left")
        ttk.Entry(grid_frame, textvariable=self.num_cols, width=5).pack(side="left")
        return master

    def validate(self):
        """Recusa números ilegíveis ANTES de fechar o diálogo.

        A conversão vivia só em ``apply()``, e o ``except`` lá fazia
        ``self.result = None``. Quem chama testa ``if not dialog.result:
        return`` — a mesma condição de "o usuário cancelou". Digitar "três" em
        Faixas, ou deixar o campo vazio, fechava a janela e não criava ROI
        nenhuma, sem mensagem. Com zero era ainda mais discreto: o valor
        convertia, ``range(0)`` não iterava, e a operação terminava "com
        sucesso" sem produzir nada.
        """
        fields = (
            (_("Lanes"), self.num_lanes),
            (_("Rows"), self.num_rows),
            (_("Columns"), self.num_cols),
        )
        relevant = {
            "vertical": (fields[0],),
            "horizontal": (fields[0],),
            "grid": (fields[1], fields[2]),
        }.get(self.template_type.get(), fields)

        for label, var in relevant:
            try:
                value = int(var.get())
            except (ValueError, TypeError):
                messagebox.showerror(
                    _("Invalid value"),
                    _("'{field}' must be a whole number.").format(field=label),
                    parent=self,
                )
                return False
            if value < 1:
                messagebox.showerror(
                    _("Invalid value"),
                    _("'{field}' must be at least 1.").format(field=label),
                    parent=self,
                )
                return False
        return True

    def apply(self):
        """Apply the selected template to result.

        Os campos irrelevantes para o tipo escolhido não passam por
        ``validate()`` — deixar "linhas" pela metade ao criar faixas verticais é
        normal — então aqui eles caem no padrão em vez de estourar.
        """
        self.result = {
            "type": self.template_type.get(),
            "lanes": self._as_int(self.num_lanes, default=3),
            "rows": self._as_int(self.num_rows, default=2),
            "cols": self._as_int(self.num_cols, default=2),
        }

    @staticmethod
    def _as_int(var, *, default: int) -> int:
        try:
            value = int(var.get())
        except (ValueError, TypeError):
            return default
        return value if value >= 1 else default
