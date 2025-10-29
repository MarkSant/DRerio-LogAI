"""
Collapsible Frame Widget

Provides a frame with a clickable header that can expand/collapse its content.
"""

from tkinter import Frame, Label, ttk


class CollapsibleFrame(Frame):
    """
    A frame that can be collapsed/expanded by clicking its header.

    The header shows an indicator (▼/▶) and the content frame can be
    hidden or shown by clicking anywhere on the header.
    """

    def __init__(self, parent, title: str, start_collapsed: bool = False, **kwargs):
        """
        Initialize collapsible frame.

        Args:
            parent: Parent widget
            title: Title text for the header
            start_collapsed: If True, starts in collapsed state
            **kwargs: Additional Frame options
        """
        super().__init__(parent, **kwargs)

        self.is_collapsed = start_collapsed

        # Header frame (clickable)
        self.header = Frame(self, relief="raised", borderwidth=1)
        self.header.pack(fill="x", padx=0, pady=(0, 1))

        # Indicator label (▼ = expanded, ▶ = collapsed)
        self.indicator = Label(
            self.header,
            text="▶" if start_collapsed else "▼",
            width=2,
            font=("Segoe UI", 10),
        )
        self.indicator.pack(side="left", padx=(5, 0))

        # Title label
        self.title_label = Label(
            self.header,
            text=title,
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self.title_label.pack(side="left", fill="x", expand=True, padx=5, pady=5)

        # Content frame (collapsible)
        self.content = ttk.Frame(self)
        if not start_collapsed:
            self.content.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        # Make header clickable
        self.header.bind("<Button-1>", lambda e: self.toggle())
        self.indicator.bind("<Button-1>", lambda e: self.toggle())
        self.title_label.bind("<Button-1>", lambda e: self.toggle())

        # Make header highlight on hover
        self.header.bind("<Enter>", lambda e: self.header.config(background="#e8e8e8"))
        self.header.bind("<Leave>", lambda e: self.header.config(background="SystemButtonFace"))

    def toggle(self):
        """Toggle between collapsed and expanded states."""
        if self.is_collapsed:
            self.expand()
        else:
            self.collapse()

    def collapse(self):
        """Collapse the frame (hide content)."""
        if not self.is_collapsed:
            self.content.pack_forget()
            self.indicator.config(text="▶")
            self.is_collapsed = True

    def expand(self):
        """Expand the frame (show content)."""
        if self.is_collapsed:
            self.content.pack(fill="both", expand=True, padx=5, pady=(0, 5))
            self.indicator.config(text="▼")
            self.is_collapsed = False

    def get_content_frame(self) -> ttk.Frame:
        """
        Get the content frame where widgets should be added.

        Returns:
            The content frame widget
        """
        return self.content
