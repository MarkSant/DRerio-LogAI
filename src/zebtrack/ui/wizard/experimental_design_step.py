"""
Experimental Design Step - Live Projects.

Collects experimental structure for live recording projects:
- Number of groups
- Group names
- Number of days
- Number of subjects per group
"""

from __future__ import annotations

from tkinter import Button, Entry, Frame, IntVar, Label, LabelFrame, StringVar

import structlog

from zebtrack.core.services.wizard_service import WizardService
from zebtrack.i18n import _
from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import WizardStepID
from zebtrack.ui.wizard.tooltip import ToolTip

log = structlog.get_logger()


class NumberInput(Frame):
    """
    Entry field with +/- buttons for numeric input.

    Provides an intuitive way to input numbers with both direct typing
    and increment/decrement buttons.
    """

    def __init__(
        self,
        parent,
        variable: IntVar,
        min_val: int = 1,
        max_val: int = 100,
        width: int = 5,
        **kwargs,
    ):
        """
        Initialize NumberInput widget.

        Args:
            parent: Parent widget
            variable: IntVar to bind to
            min_val: Minimum allowed value
            max_val: Maximum allowed value
            width: Width of entry field in characters
            **kwargs: Additional Frame options
        """
        super().__init__(parent, **kwargs)
        self.variable = variable
        self.min_val = min_val
        self.max_val = max_val

        # Decrease button
        self.btn_decrease = Button(
            self,
            text="−",
            width=2,
            command=self._decrease,
        )
        self.btn_decrease.pack(side="left", padx=(0, 2))

        # Entry field
        self.entry = Entry(
            self,
            textvariable=self.variable,
            width=width,
            justify="center",
        )
        self.entry.pack(side="left", padx=2)

        # Increase button
        self.btn_increase = Button(
            self,
            text="+",
            width=2,
            command=self._increase,
        )
        self.btn_increase.pack(side="left", padx=(2, 0))

        # Validation
        self.variable.trace_add("write", self._validate)

        # Initial validation
        self._validate()

    def _decrease(self):
        """Decrease value by 1."""
        current = self.variable.get()
        if current > self.min_val:
            self.variable.set(current - 1)

    def _increase(self):
        """Increase value by 1."""
        current = self.variable.get()
        if current < self.max_val:
            self.variable.set(current + 1)

    def _validate(self, *args):
        """Validate and clamp value to allowed range."""
        try:
            value = self.variable.get()
            # Clamp to valid range
            if value < self.min_val:
                self.variable.set(self.min_val)
            elif value > self.max_val:
                self.variable.set(self.max_val)

            # Update button states
            self.btn_decrease.config(state="normal" if value > self.min_val else "disabled")
            self.btn_increase.config(state="normal" if value < self.max_val else "disabled")

        except Exception:
            # If conversion fails, reset to min value
            self.variable.set(self.min_val)


class ExperimentalDesignStep(WizardStep):
    """
    Experimental Design configuration step for live projects.

    Allows users to define experimental structure:
    - Duration in days
    - Number of experimental groups
    - Number of subjects per group
    - Custom names for each group
    """

    def __init__(self, parent, wizard_data: dict):
        """Initialize experimental design step."""
        super().__init__(parent, wizard_data)
        self.step_id = WizardStepID.EXPERIMENTAL_DESIGN

        # UI variables
        self.num_groups_var = IntVar(value=2)
        self.num_days_var = IntVar(value=1)
        self.subjects_per_group_var = IntVar(value=1)
        self.group_name_vars: list[StringVar] = []
        self.group_name_entries: list[Entry] = []

        # Container for dynamic group name entries
        self.group_names_container: Frame | None = None

    def build_ui(self):
        """Build experimental design step UI."""
        # Header
        title = Label(
            self,
            text=_("Experimental Design Configuration"),
            font=("TkDefaultFont", 13, "bold"),
        )
        title.pack(pady=(0, 10))

        subtitle = Label(
            self,
            text=_("Set up the structure of your live experiment"),
            fg="gray",
            font=("TkDefaultFont", 10),
        )
        subtitle.pack(pady=(0, 20))

        # 2-column layout
        config_container = Frame(self)
        config_container.pack(fill="both", expand=True, padx=10, pady=5)

        # Left column: Basic config
        left_col = LabelFrame(
            config_container,
            text=_("Basic Configuration"),
            padx=15,
            pady=10,
        )
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 5))

        # Days
        Label(
            left_col,
            text=_("Experiment Duration (days):"),
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w", pady=(0, 2))

        days_frame = Frame(left_col)
        days_frame.pack(fill="x", pady=(0, 15))

        days_input = NumberInput(
            days_frame,
            variable=self.num_days_var,
            min_val=1,
            max_val=30,
            width=5,
        )
        days_input.pack(side="left")

        Label(days_frame, text=_("days"), fg="gray").pack(side="left", padx=5)

        ToolTip(
            days_frame,
            _(
                "Experiment Duration\n\n"
                "How many days your full experiment will last.\n\n"
                "Examples:\n"
                "• 1 day: acute test\n"
                "• 7 days: 1-week treatment\n"
                "• 21 days: chronic treatment\n\n"
                "You can type directly or use the +/- buttons.\n"
                "This affects how the output files are organised."
            ),
        )

        # Subjects per group
        Label(
            left_col,
            text=_("Animals per Group:"),
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w", pady=(0, 2))

        subjects_frame = Frame(left_col)
        subjects_frame.pack(fill="x", pady=(0, 15))

        subjects_input = NumberInput(
            subjects_frame,
            variable=self.subjects_per_group_var,
            min_val=1,
            max_val=20,
            width=5,
        )
        subjects_input.pack(side="left")

        Label(subjects_frame, text=_("animals/group"), fg="gray").pack(side="left", padx=5)

        ToolTip(
            subjects_frame,
            _(
                "Animals per Group\n\n"
                "How many animals in each experimental group.\n\n"
                "Example: 5 animals/group\n"
                "• Control Group: 5 animals\n"
                "• Treatment Group: 5 animals\n"
                "Total: 10 animals\n\n"
                "You can type directly or use the +/- buttons."
            ),
        )

        # Number of groups
        Label(
            left_col,
            text=_("Number of Groups:"),
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w", pady=(0, 2))

        groups_frame = Frame(left_col)
        groups_frame.pack(fill="x", pady=(0, 15))

        groups_input = NumberInput(
            groups_frame,
            variable=self.num_groups_var,
            min_val=1,
            max_val=6,
            width=5,
        )
        groups_input.pack(side="left")

        # Register callback for groups change
        self.num_groups_var.trace_add("write", lambda *args: self._on_num_groups_change())

        Label(groups_frame, text=_("groups"), fg="gray").pack(side="left", padx=5)

        ToolTip(
            groups_frame,
            _(
                "Number of Experimental Groups\n\n"
                "How many different groups you will have.\n\n"
                "Examples:\n"
                "• 1 group: A single treatment\n"
                "• 2 groups: Control vs. Treatment\n"
                "• 3+ groups: Multiple treatments or doses\n\n"
                "You can type directly or use the +/- buttons."
            ),
        )

        # Summary label
        self.summary_var = StringVar()
        summary_label = Label(
            left_col,
            textvariable=self.summary_var,
            fg="#2E7D32",
            font=("TkDefaultFont", 9, "bold"),
            wraplength=280,
            justify="left",
        )
        summary_label.pack(anchor="w", pady=(10, 0))

        self._update_summary()

        # Bind updates
        self.num_days_var.trace_add("write", lambda *_: self._update_summary())
        self.num_groups_var.trace_add("write", lambda *_: self._update_summary())
        self.subjects_per_group_var.trace_add("write", lambda *_: self._update_summary())

        # Right column: Group names
        right_col = LabelFrame(
            config_container,
            text=_("Group Names"),
            padx=15,
            pady=10,
        )
        right_col.pack(side="left", fill="both", expand=True, padx=(5, 0))

        Label(
            right_col,
            text=_("Give each group a descriptive name:"),
            fg="gray",
            font=("TkDefaultFont", 9),
        ).pack(anchor="w", pady=(0, 10))

        # Dynamic group name entries
        self.group_names_container = Frame(right_col)
        self.group_names_container.pack(fill="both", expand=True)

        self._rebuild_group_name_entries()

        # Info box
        info_frame = LabelFrame(
            self,
            text=_("ℹ️  How will this be used?"),
            padx=15,
            pady=10,
        )
        info_frame.pack(fill="x", padx=10, pady=(15, 0))

        info_text = Label(
            info_frame,
            text=_(
                "The structure you configure will be used to:\n\n"
                "• Organise recordings by Day → Group → Animal\n"
                "• Build a visual grid of experiment progress\n"
                "• Make comparative analysis between groups easier\n\n"
                "Example: 2 groups x 5 days x 3 animals = 30 organised recordings"
            ),
            justify="left",
            fg="#555",
            font=("TkDefaultFont", 9),
        )
        info_text.pack(anchor="w")

    def _on_num_groups_change(self, *_args):
        """Rebuild group name entries when number changes."""
        self._rebuild_group_name_entries()
        self._update_summary()

    def _rebuild_group_name_entries(self):
        """Dynamically create entry fields for group names."""
        if not self.group_names_container:
            return

        # Clear existing widgets
        for widget in self.group_names_container.winfo_children():
            widget.destroy()

        self.group_name_vars = []
        self.group_name_entries = []
        num_groups = self.num_groups_var.get()

        default_names = [
            "Controle",
            "Tratamento 1",
            "Tratamento 2",
            "Tratamento 3",
            "Grupo 5",
            "Grupo 6",
        ]

        for i in range(num_groups):
            frame = Frame(self.group_names_container)
            frame.pack(fill="x", pady=3)

            Label(
                frame,
                text=f"Grupo {i + 1}:",
                width=10,
                anchor="w",
            ).pack(side="left")

            # Pre-fill with existing data or default
            existing_names = self.wizard_data.get("group_names", [])
            if i < len(existing_names):
                default_value = existing_names[i]
            elif i < len(default_names):
                default_value = default_names[i]
            else:
                default_value = f"Grupo {i + 1}"

            var = StringVar(value=default_value)
            self.group_name_vars.append(var)

            entry = Entry(frame, textvariable=var, width=30)
            entry.pack(side="left", padx=5)
            self.group_name_entries.append(entry)

    def _update_summary(self):
        """Update summary label with experiment size calculation."""
        num_groups = self.num_groups_var.get()
        num_days = self.num_days_var.get()
        subjects = self.subjects_per_group_var.get()

        total_sessions = num_groups * num_days * subjects
        total_animals = num_groups * subjects

        self.summary_var.set(
            _("📊 Total: {sessions} recordings ({animals} animals x {days} days)").format(
                sessions=total_sessions, animals=total_animals, days=num_days
            )
        )

    def validate(self) -> tuple[bool, str]:
        """Validate experimental design using WizardService."""
        num_groups = self.num_groups_var.get()

        # Trim all group names first
        for _i, var in enumerate(self.group_name_vars[:num_groups]):
            name = var.get().strip()
            var.set(name)

        # Get data and use WizardService for validation
        data = self.get_data()
        is_valid, error_msg = WizardService.validate_experimental_design(data)

        return (is_valid, error_msg)

    def get_data(self) -> dict:
        """Extract experimental design data."""
        num_groups = self.num_groups_var.get()

        return {
            "experiment_days": self.num_days_var.get(),
            "num_groups": num_groups,
            "subjects_per_group": self.subjects_per_group_var.get(),
            "group_names": [var.get().strip() for var in self.group_name_vars[:num_groups]],
        }

    def on_show(self) -> None:
        """Repopulate the UI from wizard_data when the step becomes visible.

        Mirrors CalibrationStep.on_show: the shared ``wizard_data`` holds the
        latest committed values (including those seeded from a loaded template),
        so replaying ``set_data`` keeps the widgets in sync. Idempotent — re-runs
        on every show without clobbering user edits, since wizard_data already
        reflects them.
        """
        super().on_show()
        if any(
            key in self.wizard_data
            for key in ("experiment_days", "num_groups", "subjects_per_group", "group_names")
        ):
            self.set_data(self.wizard_data)

    def set_data(self, data: dict):
        """Restore UI from data (for back navigation)."""
        if "experiment_days" in data:
            self.num_days_var.set(data["experiment_days"])

        if "num_groups" in data:
            self.num_groups_var.set(data["num_groups"])
            # Rebuild will use data from wizard_data

        if "subjects_per_group" in data:
            self.subjects_per_group_var.set(data["subjects_per_group"])

        # Store in wizard_data for _rebuild_group_name_entries to use
        if "group_names" in data:
            self.wizard_data["group_names"] = data["group_names"]

        # Rebuild with new data
        self._rebuild_group_name_entries()
        self._update_summary()
