"""
MultiAquariumConfirmDialog - Dialog for confirming aquarium count.

Displays when user clicks "Detectar Aquário (Auto)" to ask how many
aquariums are in the video.
"""

import tkinter as tk
from tkinter import simpledialog, ttk
from typing import Callable

import structlog

log = structlog.get_logger()


class MultiAquariumConfirmDialog(simpledialog.Dialog):
    """Dialog to confirm the number of aquariums in a video.

    Asks user: "Quantos aquários existem neste vídeo?"
    Options:
    - "1 aquário (padrão)"
    - "2 aquários"

    If 2: Triggers multi-aquarium auto-detection
    If 1: Continues with standard detection
    """

    def __init__(
        self,
        parent: tk.Toplevel | tk.Tk,
        video_path: str | None = None,
        on_single: Callable[[], None] | None = None,
        on_multi: Callable[[], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
    ):
        """Initialize the multi-aquarium confirmation dialog.

        Args:
            parent: Parent widget.
            video_path: Path to the video being configured.
            on_single: Callback when user selects 1 aquarium.
            on_multi: Callback when user selects 2 aquariums.
            on_cancel: Callback when user cancels.
        """
        self.video_path = video_path
        self._on_single = on_single
        self._on_multi = on_multi
        self._on_cancel = on_cancel
        self.result: int | None = None  # 1, 2, or None if cancelled

        log.debug("multi_aquarium_confirm.dialog.init", video_path=video_path)

        super().__init__(parent, "Configuração de Aquários")

    def body(self, master: tk.Frame) -> tk.Widget | None:
        """Create dialog body with aquarium count selection.

        Args:
            master: Parent widget for dialog body.

        Returns:
            The initial focus widget.
        """
        master.config(padx=20, pady=15)

        # Header
        header_label = ttk.Label(
            master,
            text="Quantos aquários existem neste vídeo?",
            font=("Helvetica", 12, "bold"),
        )
        header_label.pack(pady=(0, 15))

        # Description
        desc_label = ttk.Label(
            master,
            text="Selecione a quantidade de aquários para configurar\na detecção automática corretamente.",
            justify=tk.CENTER,
            foreground="gray",
        )
        desc_label.pack(pady=(0, 20))

        # Radio buttons frame
        self._aquarium_count = tk.IntVar(value=1)

        radio_frame = ttk.Frame(master)
        radio_frame.pack(fill=tk.X, pady=5)

        # Option 1: Single aquarium
        single_radio = ttk.Radiobutton(
            radio_frame,
            text="1 aquário (padrão)",
            variable=self._aquarium_count,
            value=1,
        )
        single_radio.pack(anchor=tk.W, pady=5, padx=10)

        single_desc = ttk.Label(
            radio_frame,
            text="    Detecção padrão para vídeos com 1 aquário",
            foreground="gray",
            font=("Helvetica", 9),
        )
        single_desc.pack(anchor=tk.W, padx=10)

        # Separator
        ttk.Separator(radio_frame, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=10, padx=10
        )

        # Option 2: Multi aquarium
        multi_radio = ttk.Radiobutton(
            radio_frame,
            text="2 aquários",
            variable=self._aquarium_count,
            value=2,
        )
        multi_radio.pack(anchor=tk.W, pady=5, padx=10)

        multi_desc = ttk.Label(
            radio_frame,
            text="    Detecta 2 aquários separados no mesmo vídeo\n"
            "    (cada aquário pode pertencer a grupos diferentes)",
            foreground="gray",
            font=("Helvetica", 9),
            justify=tk.LEFT,
        )
        multi_desc.pack(anchor=tk.W, padx=10)

        return single_radio  # Initial focus

    def buttonbox(self) -> None:
        """Create custom button box with Confirm and Cancel buttons."""
        box = ttk.Frame(self)
        box.pack(pady=(15, 0))

        confirm_btn = ttk.Button(
            box,
            text="Confirmar",
            width=12,
            command=self._on_confirm,
        )
        confirm_btn.pack(side=tk.LEFT, padx=5)

        cancel_btn = ttk.Button(
            box,
            text="Cancelar",
            width=12,
            command=self.cancel,
        )
        cancel_btn.pack(side=tk.LEFT, padx=5)

        self.bind("<Return>", lambda e: self._on_confirm())
        self.bind("<Escape>", lambda e: self.cancel())

    def _on_confirm(self) -> None:
        """Handle confirmation of aquarium count selection."""
        self.result = self._aquarium_count.get()

        log.info(
            "multi_aquarium_confirm.dialog.confirmed",
            aquarium_count=self.result,
        )

        if self.result == 1 and self._on_single:
            self._on_single()
        elif self.result == 2 and self._on_multi:
            self._on_multi()

        self.ok()

    def cancel(self, event=None) -> None:
        """Handle dialog cancellation."""
        log.debug("multi_aquarium_confirm.dialog.cancelled")
        self.result = None

        if self._on_cancel:
            self._on_cancel()

        super().cancel()

    def get_result(self) -> int | None:
        """Return the selected aquarium count.

        Returns:
            1 for single aquarium, 2 for multi-aquarium, None if cancelled.
        """
        return self.result
