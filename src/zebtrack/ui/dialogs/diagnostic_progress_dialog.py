"""
Diagnostic Progress Dialog.

Non-modal progress dialog for diagnostic test execution.
Shows real-time progress and allows user cancellation.
"""

from tkinter import Button, Frame, Label, StringVar, Toplevel, ttk


class DiagnosticProgressDialog(Toplevel):
    """Non-modal progress dialog for diagnostic test execution."""

    def __init__(self, parent, title="Diagnóstico em Progresso"):
        """Initialize the diagnostic progress dialog.

        Args:
            parent: Parent widget.
            title: Dialog window title (default: "Diagnóstico em Progresso").
        """
        super().__init__(parent)
        self.title(title)
        self.parent = parent
        self.user_cancelled = False
        self.progress_var = StringVar(value="Iniciando...")
        self.status_var = StringVar(value="Aguarde...")

        # Make dialog always on top and prevent closing via X button
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        # Create UI elements
        self._create_widgets()

        # Center dialog on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        """Create dialog body with progress indicators."""
        # Main frame with padding
        main_frame = Frame(self, padx=20, pady=10)
        main_frame.pack(fill="both", expand=True)

        # Title
        title_label = Label(
            main_frame,
            text="Executando Diagnóstico do Modelo",
            font=("Arial", 12, "bold"),
        )
        title_label.grid(row=0, column=0, columnspan=2, pady=(10, 20), sticky="w")

        # Progress message
        Label(main_frame, text="Status:").grid(row=1, column=0, sticky="w", padx=(10, 5))
        progress_label = Label(
            main_frame,
            textvariable=self.progress_var,
            width=50,
            anchor="w",
        )
        progress_label.grid(row=1, column=1, sticky="w", pady=5)

        # Detailed status
        Label(main_frame, text="Detalhes:").grid(row=2, column=0, sticky="w", padx=(10, 5))
        status_label = Label(
            main_frame,
            textvariable=self.status_var,
            width=50,
            anchor="w",
            fg="gray",
        )
        status_label.grid(row=2, column=1, sticky="w", pady=5)

        # Progress bar (indeterminate mode initially)
        self.progress_bar = ttk.Progressbar(
            main_frame,
            mode="determinate",
            maximum=100,
            length=400,
        )
        self.progress_bar.grid(row=3, column=0, columnspan=2, pady=(10, 20), padx=10)

        # Button box
        self._create_buttonbox(main_frame)

    def update_progress(self, message: str, current: int | None = None, total: int | None = None):
        """
        Update progress display.

        Args:
            message: Progress message to display
            current: Current frame number (optional)
            total: Total frames (optional)
        """
        self.progress_var.set(message)

        if current is not None and total is not None and total > 0:
            percentage = int((current / total) * 100)
            self.progress_bar["value"] = percentage
            self.status_var.set(f"Frame {current}/{total} ({percentage}%)")
        else:
            self.status_var.set("Processando...")

        self.update_idletasks()

    def update_status(self, status: str):
        """Update detailed status message."""
        self.status_var.set(status)
        self.update_idletasks()

    def _create_buttonbox(self, master):
        """Create button box with Cancel button."""
        box = Frame(master)

        cancel_btn = Button(
            box,
            text="Cancelar",
            width=10,
            command=self.cancel,
        )
        cancel_btn.pack(side="left", padx=5, pady=5)

        self.bind("<Escape>", self.cancel)
        box.grid(row=4, column=0, columnspan=2, pady=(0, 10))

    def cancel(self, event=None):
        """Handle cancel action."""
        self.user_cancelled = True
        self.progress_var.set("Cancelando...")
        self.status_var.set("Aguarde o processamento atual terminar...")
        # Don't destroy immediately - let the worker thread finish current frame
        # The controller will destroy this dialog when it detects cancellation

    def finish(self):
        """Close dialog normally when processing is complete."""
        self.destroy()
