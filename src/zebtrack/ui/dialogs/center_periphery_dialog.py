"""
CenterPeripheryDialog.

Extracted from gui.py for better modularity.
"""

from tkinter import (
    StringVar,
    simpledialog,
    ttk,
)

from zebtrack.i18n import _


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

        ttk.Label(master, text=_("Method:")).pack(anchor="w")
        ttk.Radiobutton(
            master,
            text=_("Distance from the edge (cm)"),
            variable=self.method,
            value="distance",
        ).pack(anchor="w")
        ttk.Radiobutton(
            master,
            text=_("Area ratio (0.0-1.0)"),
            variable=self.method,
            value="area_ratio",
        ).pack(anchor="w")

        ttk.Label(master, text=_("Value:")).pack(anchor="w", pady=(5, 0))
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
