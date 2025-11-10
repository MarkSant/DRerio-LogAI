"""
StartRecordingDialog.

Extracted from gui.py for better modularity.
"""

from tkinter import (
    Label,
    OptionMenu,
    StringVar,
    messagebox,
    simpledialog,
)


class StartRecordingDialog(simpledialog.Dialog):
    """Dialog for initiating a new recording session.

    Allows users to select day, group, and subject for starting a new
    live camera recording session with smart state retention.
    """

    def __init__(self, parent, project_manager):
        """Initialize the start recording dialog.

        Args:
            parent: Parent widget.
            project_manager: Project manager instance for accessing project data.
        """
        self.pm = project_manager
        self.result = None
        super().__init__(parent, "Iniciar Nova Sessão de Gravação")

    def body(self, master):
        """Create dialog body with recording session selection options.

        Args:
            master: Parent widget for dialog body.

        Returns:
            The initial focus widget.
        """
        # Get data from project manager
        days = self.pm.project_data.get("experiment_days", 1)
        groups = self.pm.project_data.get("groups", [])
        subjects = self.pm.project_data.get("subjects_per_group", 1)
        last_day, last_group = self.pm.get_last_session_details()

        # Create variables
        self.day_var = StringVar()
        self.group_var = StringVar()
        self.subject_var = StringVar()

        # Set initial values for smart state retention
        day_opts = [str(d) for d in range(1, days + 1)]
        if last_day and str(last_day) in day_opts:
            self.day_var.set(str(last_day))
        elif day_opts:
            self.day_var.set(day_opts[0])

        if last_group and last_group in groups:
            self.group_var.set(last_group)
        elif groups:
            self.group_var.set(groups[0])

        # --- Layout ---
        # Day Dropdown
        Label(master, text="Selecione o Dia:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        day_menu = OptionMenu(master, self.day_var, *day_opts)
        day_menu.grid(row=0, column=1, sticky="ew", padx=5)

        # Group Dropdown
        Label(master, text="Selecione o Grupo:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        group_menu = OptionMenu(master, self.group_var, *groups)
        group_menu.grid(row=1, column=1, sticky="ew", padx=5)

        # Subject Dropdown
        Label(master, text="Selecione a Cobaia:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        subject_opts = [str(s) for s in range(1, subjects + 1)]
        subject_menu = OptionMenu(master, self.subject_var, *subject_opts)
        subject_menu.grid(row=2, column=1, sticky="ew", padx=5)
        if subject_opts:
            self.subject_var.set(subject_opts[0])

        return subject_menu  # Initial focus

    def validate(self):
        """Validate that day, group, and subject are selected.

        Returns:
            True if all selections are valid, False otherwise.
        """
        if not all([self.day_var.get(), self.group_var.get(), self.subject_var.get()]):
            messagebox.showerror("Erro", "Todos os campos são obrigatórios.")
            return False
        return True

    def apply(self):
        """Apply the selected recording session parameters to result."""
        self.result = {
            "day": int(self.day_var.get()),
            "group": self.group_var.get(),
            "cobaia": self.subject_var.get(),
        }
