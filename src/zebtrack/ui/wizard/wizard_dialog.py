"""
Main wizard dialog orchestrator.

Manages 5-step wizard flow, navigation, and data accumulation.
"""

from datetime import datetime, timezone
from tkinter import Frame, messagebox
from tkinter.simpledialog import Dialog

import structlog

from zebtrack.ui.wizard.cache import WizardCache
from zebtrack.ui.wizard.confirmation_step import ConfirmationStep
from zebtrack.ui.wizard.detection_step import DetectionStep
from zebtrack.ui.wizard.discovery_step import DiscoveryStep
from zebtrack.ui.wizard.enums import WizardStepID
from zebtrack.ui.wizard.file_selection_step import FileSelectionStep
from zebtrack.ui.wizard.import_config_step import ImportConfigStep

log = structlog.get_logger()


class WizardDialog(Dialog):
    """
    Main wizard orchestrator for 5-step project creation.

    Architecture:
        - Each step is a WizardStep instance
        - wizard_data dict accumulates data across all steps
        - cache provides session-level caching for performance
        - Navigation via Back/Next buttons (validated transitions)

    Steps:
        1. Discovery: Project type, folder structure, parquet import scope
        2. File Selection: Select videos and folders (Phase W2)
        3. Detection: Auto-detect design, analyze parquets (Phase W3)
        4. Import Config: Configure per-video import strategy (Phase W4)
        5. Confirmation: Final review and project creation (Phase W5)

    Usage:
        >>> wizard = WizardDialog(root)
        >>> if wizard.result:
        ...     controller.create_new_project(**wizard.result)

    Attributes:
        steps (list[WizardStep]): All wizard steps
        current_step_index (int): Currently visible step (0-4)
        wizard_data (dict): Accumulated data from all steps
        cache (WizardCache): Session cache for performance
        result (dict | None): Final wizard output or None if cancelled
    """

    def __init__(self, parent):
        """
        Initialize wizard dialog.

        Args:
            parent: Parent Tkinter widget (usually root window)
        """
        self.steps = []
        self.current_step_index = 0
        self.wizard_data = {
            "wizard_schema_version": 1,  # For future migrations
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.cache = WizardCache()
        self.result = None  # Will be set on successful completion

        log.info("wizard.opened")

        # Call parent constructor (will call body())
        super().__init__(parent, title="Novo Projeto - Wizard")

    def body(self, master):
        """
        Build wizard UI (called by Dialog.__init__).

        Args:
            master: Parent widget for body content

        Returns:
            Widget: Widget to receive initial focus (or None)
        """
        # Create container for steps
        self.steps_container = Frame(master)
        self.steps_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Initialize all steps (Phase W1-W5: All steps complete!)
        self.steps = [
            DiscoveryStep(self.steps_container, self.wizard_data),
            FileSelectionStep(self.steps_container, self.wizard_data),  # Phase W2 ✅
            DetectionStep(self.steps_container, self.wizard_data),       # Phase W3 ✅
            ImportConfigStep(self.steps_container, self.wizard_data),    # Phase W4 ✅
            ConfirmationStep(self.steps_container, self.wizard_data),    # Phase W5 ✅
        ]

        # Build UI for all steps
        for step in self.steps:
            step.build_ui()

        # Show first step
        self._show_step(0)

        # Return None (no specific focus)
        return None

    def buttonbox(self):
        """
        Create navigation buttons (overrides Dialog.buttonbox).

        Creates: [< Voltar] [Próximo >] [Cancelar]
        """
        from tkinter import Button

        box = Frame(self)
        box.pack(side="bottom", fill="x", padx=5, pady=5)

        # Back button (disabled on first step)
        self.back_button = Button(
            box, text="< Voltar", width=10, command=self._on_back
        )
        self.back_button.pack(side="left", padx=5)

        # Next / Create Project button (text changes on last step)
        self.next_button = Button(
            box, text="Próximo >", width=15, command=self._on_next
        )
        self.next_button.pack(side="left", padx=5)

        # Cancel button
        cancel_button = Button(box, text="Cancelar", width=10, command=self._on_cancel)
        cancel_button.pack(side="right", padx=5)

        self._update_navigation_buttons()

    def _show_step(self, step_index: int):
        """
        Show specific step and hide others.

        Args:
            step_index: Index of step to show (0-4)
        """
        # Hide all steps
        for step in self.steps:
            step.pack_forget()

        # Show selected step
        if 0 <= step_index < len(self.steps):
            self.current_step_index = step_index
            current_step = self.steps[step_index]
            current_step.pack(fill="both", expand=True)
            current_step.on_show()  # Lifecycle hook

            log.info(
                "wizard.step_shown",
                step=step_index + 1,
                step_id=current_step.step_id.value if current_step.step_id else None,
            )

        self._update_navigation_buttons()

    def _update_navigation_buttons(self):
        """Update navigation button states based on current step."""
        # Buttons are created in buttonbox() which is called after body()
        # So we need to check if they exist first
        if not hasattr(self, 'back_button') or not hasattr(self, 'next_button'):
            return

        # Back button: disabled on first step
        if self.current_step_index == 0:
            self.back_button.config(state="disabled")
        else:
            self.back_button.config(state="normal")

        # Next button: changes to "Criar Projeto" on last step
        if self.current_step_index == len(self.steps) - 1:
            self.next_button.config(text="Criar Projeto")
        else:
            self.next_button.config(text="Próximo >")

    def _on_back(self):
        """Handle Back button click."""
        if self.current_step_index > 0:
            # Hide current step
            self.steps[self.current_step_index].on_hide()

            # Restore previous step with data
            prev_step = self.steps[self.current_step_index - 1]
            prev_data = self.wizard_data.get(prev_step.step_id.name.lower(), {})
            prev_step.set_data(prev_data)

            # Show previous step
            self._show_step(self.current_step_index - 1)

            log.info("wizard.step_back", from_step=self.current_step_index + 2)

    def _on_next(self):
        """Handle Next button click (or Create Project on last step)."""
        current_step = self.steps[self.current_step_index]

        # Validate current step
        is_valid, error_message = current_step.validate()
        if not is_valid:
            messagebox.showerror("Validação", error_message, parent=self)
            log.warning(
                "wizard.validation_failed",
                step=self.current_step_index + 1,
                error=error_message,
            )
            return

        # Extract and store step data
        step_data = current_step.get_data()
        self.wizard_data.update(step_data)

        log.info(
            "wizard.step_completed",
            step=self.current_step_index + 1,
            data_keys=list(step_data.keys()),
        )

        # Hide current step
        current_step.on_hide()

        # Last step? Finish wizard
        if self.current_step_index == len(self.steps) - 1:
            self._finish()
        else:
            # Advance to next step
            self._show_step(self.current_step_index + 1)

    def _on_cancel(self):
        """Handle Cancel button click."""
        # Ask for confirmation if user has entered data
        if self.current_step_index > 0:
            confirm = messagebox.askyesno(
                "Cancelar",
                "Descartar rascunho do projeto?",
                parent=self,
                icon="warning",
            )
            if not confirm:
                return

        log.info("wizard.cancelled", step=self.current_step_index + 1)
        self.result = None
        self.destroy()

    def _finish(self):
        """
        Finish wizard and return result.

        Called when user clicks "Criar Projeto" on last step.
        Sets self.result and closes dialog.
        """
        log.info(
            "wizard.finished",
            total_steps=len(self.steps),
            data_size=len(str(self.wizard_data)),
        )

        self.result = self.wizard_data
        self.destroy()
