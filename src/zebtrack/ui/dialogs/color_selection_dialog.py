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


class ColorSelectionDialog(simpledialog.Dialog):
    """Diálogo para seleção de cor de áreas de interesse."""

    def __init__(self, parent, title="Selecionar Cor da Área"):
        """Initialize the color selection dialog.

        Args:
            parent: Parent widget.
            title: Dialog window title (default: "Selecionar Cor da Área").
        """
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        """Cria o corpo do diálogo com opções de cores."""
        # Default to first color (Verde)
        self.selected_color = StringVar(value="verde")

        # Cores disponíveis: (nome, valor_bgr para OpenCV, cor_hex para visualização)
        self.colors = [
            ("Verde", (0, 255, 0), "#00FF00"),
            ("Azul", (255, 0, 0), "#0000FF"),  # BGR: (255, 0, 0) = Blue
            ("Vermelho", (0, 0, 255), "#FF0000"),  # BGR: (0, 0, 255) = Red
            ("Amarelo", (0, 255, 255), "#FFFF00"),  # BGR: (0, 255, 255) = Yellow
            ("Magenta", (255, 0, 255), "#FF00FF"),  # BGR: (255, 0, 255) = Magenta
            ("Ciano", (255, 255, 0), "#00FFFF"),  # BGR: (255, 255, 0) = Cyan
        ]

        ttk.Label(master, text="Escolha a cor para esta área de interesse:").pack(pady=5)

        # Frame para os botões de cor
        colors_frame = ttk.Frame(master)
        colors_frame.pack(pady=10)

        # Criar botões de cor em duas fileiras
        for i, (name, rgb, hex_color) in enumerate(self.colors):
            row = i // 3
            col = i % 3

            color_frame = ttk.Frame(colors_frame)
            color_frame.grid(row=row, column=col, padx=5, pady=5)

            # Radiobutton para seleção
            ttk.Radiobutton(
                color_frame,
                text=name,
                variable=self.selected_color,
                value=name.lower(),
            ).pack()

            # Quadrado colorido para visualização
            color_canvas = Canvas(color_frame, width=30, height=20, highlightthickness=1)
            color_canvas.pack()
            color_canvas.create_rectangle(0, 0, 30, 20, fill=hex_color, outline="black")

        return master

    def apply(self):
        """Aplica a seleção de cor."""
        selected_name = self.selected_color.get()
        for name, rgb, hex_color in self.colors:
            if name.lower() == selected_name:
                self.result = {"name": name, "rgb": rgb, "hex": hex_color}
                break
