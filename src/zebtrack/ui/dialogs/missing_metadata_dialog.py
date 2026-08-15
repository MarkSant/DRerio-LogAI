"""
MissingMetadataDialog.

Extracted from gui.py for better modularity.
"""

from tkinter import (
    Entry,
    Frame,
    Label,
    StringVar,
    messagebox,
    simpledialog,
)

from zebtrack.i18n import _


class MissingMetadataDialog(simpledialog.Dialog):
    """Dialog for manually entering missing experiment metadata.

    Prompts the user to provide day, group, and subject information when
    metadata cannot be automatically extracted from experiment identifiers.
    """

    def __init__(self, parent, experiment_id):
        """Initialize the missing metadata dialog.

        Args:
            parent: Parent widget.
            experiment_id: Experiment identifier needing metadata.
        """
        self.experiment_id = experiment_id
        self.result = None
        super().__init__(parent, _("Missing Metadata"))

    def body(self, master):
        """Create the dialog body with metadata input fields.

        Args:
            master: Parent widget for dialog body.

        Returns:
            The first entry widget as initial focus element.
        """
        Label(master, text=_("Metadata could not be found automatically for:")).pack(pady=5)
        Label(master, text=self.experiment_id, font=("Helvetica", 10, "bold")).pack(pady=(0, 10))
        Label(master, text=_("Please enter the details manually:")).pack(pady=5)

        self.day_var = StringVar()
        self.group_var = StringVar()
        self.cobaia_var = StringVar()

        form_frame = Frame(master)
        form_frame.pack(padx=10, pady=10)

        Label(form_frame, text=_("Day:")).grid(row=0, column=0, sticky="w", padx=5, pady=2)
        Entry(form_frame, textvariable=self.day_var).grid(row=0, column=1, sticky="ew", padx=5)

        Label(form_frame, text=_("Group:")).grid(row=1, column=0, sticky="w", padx=5, pady=2)
        Entry(form_frame, textvariable=self.group_var).grid(row=1, column=1, sticky="ew", padx=5)

        Label(form_frame, text=_("Subject (ID):")).grid(row=2, column=0, sticky="w", padx=5, pady=2)
        Entry(form_frame, textvariable=self.cobaia_var).grid(row=2, column=1, sticky="ew", padx=5)

        return form_frame

    def validate(self):
        """Validate that all required fields are filled.

        Returns:
            True if all fields have values, False otherwise.
        """
        try:
            int(self.day_var.get())
            int(self.cobaia_var.get())
        except ValueError:
            messagebox.showerror(
                _("Validation Error"),
                _("Day and Subject (ID) must be whole numbers."),
            )
            return 0

        if not self.group_var.get().strip():
            messagebox.showerror(_("Validation Error"), _("The group name cannot be empty."))
            return 0

        return 1

    def apply(self):
        """Apply the entered metadata values to result dictionary."""
        self.result = {
            "day": int(self.day_var.get()),
            "group": self.group_var.get().strip(),
            "cobaia": int(self.cobaia_var.get()),
        }
