"""
SubjectSelectionDialog.

Extracted from gui.py for better modularity.
"""

from tkinter import (
    simpledialog,
    ttk,
)

from zebtrack.ui.format_utils import format_day_display


class SubjectSelectionDialog(simpledialog.Dialog):
    """Dialog for selecting a subject within an experimental group.

    Displays available subjects for a given day and group, showing completion
    status and allowing selection for video processing or analysis.
    """

    def __init__(self, parent, day, group_name, subjects_per_group, completed_subjects):
        """Initialize the subject selection dialog.

        Args:
            parent: Parent widget.
            day: Experiment day number.
            group_name: Name of the experimental group.
            subjects_per_group: Total number of subjects in the group.
            completed_subjects: Set of subject IDs already completed.
        """
        self.day = day
        self.group_name = group_name
        self.subjects_per_group = subjects_per_group
        self.completed_subjects = completed_subjects
        self.result = None  # This will be the selected subject_id

        day_display = format_day_display(day) or day
        day_title = (
            f"Dia {day_display}" if str(day_display).strip().lower() != "sem dia" else "Sem Dia"
        )

        super().__init__(parent, f"Selecionar Cobaia para o {day_title} - {group_name}")

    def body(self, master):
        """Create dialog body with subject selection buttons.

        Args:
            master: Parent widget for dialog body.

        Returns:
            The initial focus widget.
        """
        master.config(padx=10, pady=10)
        for i in range(self.subjects_per_group):
            subject_id = i + 1
            is_completed = subject_id in self.completed_subjects

            status_text = f"Cobaia {subject_id}: {'Concluído' if is_completed else 'Pendente'}"
            status_color = "darkgreen" if is_completed else "black"

            label = ttk.Label(
                master,
                text=status_text,
                foreground=status_color,
                font=("Helvetica", 10),
            )
            label.pack(anchor="w", pady=3)

            if not is_completed:
                label.config(cursor="hand2")

                label.bind(
                    "<Button-1>",
                    lambda e, s=subject_id: self.select_subject(s),  # type: ignore[misc]
                )
        return None  # No initial focus

    def select_subject(self, subject_id):
        """Handle subject selection.

        Args:
            subject_id: ID of the selected subject.
        """
        self.result = subject_id
        self.ok()  # Close the dialog

    def buttonbox(self):
        """Create custom button box with Cancel button."""
        # Override to have only a cancel button, since selection closes the dialog
        box = ttk.Frame(self)
        w = ttk.Button(box, text="Cancelar", width=10, command=self.cancel)
        w.pack(side="left", padx=5, pady=5)
        self.bind("<Escape>", self.cancel)
        box.pack()
