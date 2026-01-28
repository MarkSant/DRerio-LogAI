"""
Tooltip utility for wizard steps.

Simple tooltip implementation for providing contextual help.
"""

import tkinter as tk
from tkinter import Label


class ToolTip:
    """
    Simple tooltip that appears on hover.

    Usage:
        button = Button(root, text="Click me")
        ToolTip(button, "This button does something helpful!")
    """

    def __init__(self, widget, text: str, delay: int = 500):
        """
        Create tooltip for widget.

        Args:
            widget: Tkinter widget to attach tooltip to
            text: Tooltip text to display
            delay: Delay in ms before showing tooltip (default: 500)
        """
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tooltip_window: tk.Toplevel | None = None
        self.scheduled_id: str | None = None

        # Bind hover events
        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)
        widget.bind("<Button>", self._on_leave)  # Hide on click

    def _on_enter(self, event=None):
        """Handle mouse enter - schedule tooltip display."""
        # Cancel any previous scheduled display
        if self.scheduled_id:
            self.widget.after_cancel(self.scheduled_id)

        # Schedule tooltip display after delay
        self.scheduled_id = self.widget.after(self.delay, self._show_tooltip)

    def _on_leave(self, event=None):
        """Handle mouse leave - hide tooltip."""
        # Cancel scheduled display
        if self.scheduled_id:
            self.widget.after_cancel(self.scheduled_id)
            self.scheduled_id = None

        # Hide tooltip if visible
        self._hide_tooltip()

    def _show_tooltip(self):
        """Display tooltip window."""
        if self.tooltip_window or not self.text:
            return

        # Get widget position
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        # Create tooltip window
        self.tooltip_window = tk.Toplevel(self.widget)
        assert self.tooltip_window is not None  # For mypy
        self.tooltip_window.wm_overrideredirect(True)  # No window decorations
        self.tooltip_window.wm_geometry(f"+{x}+{y}")

        # Create label with text
        label = Label(
            self.tooltip_window,
            text=self.text,
            background="#FFFACD",  # Light yellow
            relief="solid",
            borderwidth=1,
            font=("Segoe UI", 9),
            justify="left",
            padx=5,
            pady=3,
            wraplength=300,  # Wrap long text
        )
        label.pack()

    def _hide_tooltip(self):
        """Hide tooltip window."""
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None


def create_help_label(parent, text: str) -> Label:
    """
    Create a help label with question mark icon and tooltip.

    Args:
        parent: Parent widget
        text: Help text to display in tooltip

    Returns:
        Label: Help label widget (add to layout with pack/grid)

    Usage:
        help_label = create_help_label(frame, "This is helpful information")
        help_label.pack(side="left", padx=2)
    """
    help_label = Label(
        parent,
        text="ⓘ",  # Information icon
        fg="#0066CC",  # Blue
        cursor="question_arrow",
        font=("Segoe UI", 10, "bold"),
    )

    # Add tooltip
    ToolTip(help_label, text)

    return help_label
