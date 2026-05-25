"""
CenterPeripheryDialog.

Extracted from gui.py for better modularity.
"""

from tkinter import (
    StringVar,
    simpledialog,
    ttk,
)


class CenterPeripheryDialog(simpledialog.Dialog):
    """Dialog for center-periphery analysis settings."""

    result: dict[str, str | float] | None

    def body(self, master):
        """Create dialog body with center/periphery configuration options.

        Args:
            master: Parent widget for dialog body.

        Returns:
            The initial focus widget.
        """
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
        """Apply the selected center/periphery settings to result."""
        try:
            self.result = {
                "method": self.method.get(),
                "value": float(self.value.get()),
            }
        except (ValueError, TypeError):
            self.result = None
