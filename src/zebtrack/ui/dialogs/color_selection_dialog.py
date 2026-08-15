"""
ColorSelectionDialog.

Extracted from gui.py for better modularity.
"""

from tkinter import (
    Canvas,
    StringVar,
    simpledialog,
    ttk,
)

from zebtrack.i18n import _


class ColorSelectionDialog(simpledialog.Dialog):
    """Diálogo para seleção de cor de áreas de interesse."""

    def __init__(self, parent, title=None):
        """Initialize the color selection dialog.

        Args:
            parent: Parent widget.
            title: Dialog window title. Defaults to the translated
                "Select Area Colour" when omitted.
        """
        self.result = None
        super().__init__(parent, title if title is not None else _("Select Area Colour"))

    def body(self, master):
        """Cria o corpo do diálogo com opções de cores."""
        # Default to the first colour. The radio VALUE is the stable key, never
        # the label: the label is translated, and a translated value would stop
        # matching this default (and apply()'s lookup) the moment the language
        # changes.
        self.selected_color = StringVar(value="green")

        # (key, translated label, BGR value for OpenCV, hex colour for display)
        self.colors = [
            ("green", _("Green"), (0, 128, 0), "#008000"),
            ("blue", _("Blue"), (255, 0, 0), "#0000FF"),  # BGR: (255, 0, 0) = Blue
            ("red", _("Red"), (0, 0, 255), "#FF0000"),  # BGR: (0, 0, 255) = Red
            ("yellow", _("Yellow"), (0, 204, 204), "#CCCC00"),  # Darker Yellow
            ("magenta", _("Magenta"), (255, 0, 255), "#FF00FF"),  # BGR = Magenta
            ("cyan", _("Cyan"), (255, 255, 0), "#00FFFF"),  # BGR: (255, 255, 0) = Cyan
        ]

        ttk.Label(master, text=_("Choose the colour for this region of interest:")).pack(pady=5)

        # Frame for color buttons
        colors_frame = ttk.Frame(master)
        colors_frame.pack(pady=10)

        # Create color buttons in two rows
        for i, (key, label, _rgb, hex_color) in enumerate(self.colors):
            row = i // 3
            col = i % 3

            color_frame = ttk.Frame(colors_frame)
            color_frame.grid(row=row, column=col, padx=5, pady=5)

            # Radiobutton para seleção
            ttk.Radiobutton(
                color_frame,
                text=label,
                variable=self.selected_color,
                value=key,
            ).pack()

            # Quadrado colorido para visualização
            color_canvas = Canvas(color_frame, width=30, height=20, highlightthickness=1)
            color_canvas.pack()
            color_canvas.create_rectangle(0, 0, 30, 20, fill=hex_color, outline="black")

        return master

    def apply(self):
        """Apply the color selection."""
        selected_key = self.selected_color.get()
        for key, label, rgb, hex_color in self.colors:
            if key == selected_key:
                self.result = {"key": key, "name": label, "rgb": rgb, "hex": hex_color}
                break
