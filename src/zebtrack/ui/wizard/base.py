"""
Base classes for wizard step implementation.

Each wizard step inherits from WizardStep and implements the required
interface methods for UI building, validation, and data management.
"""

from tkinter import Frame


class WizardStep(Frame):
    """
    Base class for all wizard steps.

    Each step is a Tkinter Frame that manages its own UI and data.
    The WizardDialog orchestrator calls lifecycle methods at appropriate times.

    Lifecycle:
        1. __init__() - Create frame
        2. build_ui() - Build widgets (called once)
        3. on_show() - Called when step becomes visible
        4. validate() - Check if can advance (called on Next)
        5. get_data() - Extract step data
        6. on_hide() - Called when leaving step

    Subclasses must implement:
        - build_ui()
        - validate()
        - get_data()

    Attributes:
        wizard_data (dict): Shared data dictionary from WizardDialog
        step_id (WizardStepID): This step's identifier
    """

    def __init__(self, parent, wizard_data: dict):
        """
        Initialize wizard step.

        Args:
            parent: Parent widget (usually WizardDialog)
            wizard_data: Shared data dictionary across all steps
        """
        super().__init__(parent)
        self.wizard_data = wizard_data
        self.step_id = None  # Set by subclass

    def build_ui(self):
        """
        Build UI widgets for this step.

        Called once after __init__. Should create all widgets and
        configure layout using grid/pack.

        This method must be implemented by subclasses.
        """
        raise NotImplementedError

    def validate(self) -> tuple[bool, str]:
        """
        Validate step data before allowing advancement.

        Called when user clicks Next. Should check all required fields
        and return validation result.

        Returns:
            tuple[bool, str]: (is_valid, error_message)
                - is_valid: True if can advance, False otherwise
                - error_message: Human-readable error if invalid, empty string if valid

        Examples:
            >>> return (True, "")  # Valid, can advance
            >>> return (False, "Por favor, selecione pelo menos um vídeo")  # Invalid

        This method must be implemented by subclasses.
        """
        raise NotImplementedError

    def get_data(self) -> dict:
        """
        Extract step's data for inclusion in wizard_data.

        Called before advancing to next step. Should return a dictionary
        with all data collected in this step.

        Returns:
            dict: Step data to merge into wizard_data

        Example:
            >>> return {
            ...     "project_type": "experimental",
            ...     "has_folder_structure": True,
            ...     "parquet_import_scope": "zones"
            ... }

        This method must be implemented by subclasses.
        """
        raise NotImplementedError

    def set_data(self, data: dict):
        """
        Populate UI from data (for Back navigation).

        Called when user navigates back to this step. Should restore
        UI state from previously collected data.

        Default implementation does nothing. Override if step supports
        back navigation with data restoration.

        Args:
            data: Previously collected data from get_data()
        """
        pass  # Default: no-op (override if needed)

    def on_show(self):
        """
        Execute actions when step becomes visible.

        Use this to:
        - Refresh data from previous steps
        - Run expensive operations (e.g., file scanning)
        - Update UI based on wizard_data

        Default implementation does nothing. Override if needed.
        """
        pass  # Default: no-op (override if needed)

    def on_hide(self):
        """
        Execute actions when leaving this step.

        Use this to:
        - Clean up resources
        - Cancel background operations
        - Persist temporary state

        Default implementation does nothing. Override if needed.
        """
        pass  # Default: no-op (override if needed)
