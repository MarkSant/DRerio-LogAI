"""
Wizard-based project creation system.

This package implements a 5-step wizard for intelligent project creation
with automatic design detection, parquet import, and progressive disclosure.

Architecture:
    - WizardDialog: Main orchestrator for 5 steps
    - WizardStep: Base class for individual steps
    - WizardCache: Session cache for performance
    - Enums: Formal type definitions (ProjectType, ImportAction, etc.)

Steps:
    1. Discovery: Understand user context (project type, parquets, folders)
    2. File Selection: Select videos and folders
    3. Detection & Validation: Auto-detect design, show parquet analysis
    4. Import Configuration: Configure per-video import strategy
    5. Confirmation: Final review and project creation

Version: 1.5 (wizard_schema_version: 1)
"""

from zebtrack.ui.wizard.confirmation_step import ConfirmationStep
from zebtrack.ui.wizard.detection_step import DetectionStep
from zebtrack.ui.wizard.enums import (
    ImportAction,
    ProjectType,
    ROIMergeStrategy,
    WizardStepID,
)
from zebtrack.ui.wizard.file_selection_step import FileSelectionStep
from zebtrack.ui.wizard.import_config_step import ImportConfigStep
from zebtrack.ui.wizard.wizard_dialog import WizardDialog

__all__ = [
    "WizardDialog",
    "ConfirmationStep",
    "DetectionStep",
    "FileSelectionStep",
    "ImportConfigStep",
    "ProjectType",
    "ImportAction",
    "ROIMergeStrategy",
    "WizardStepID",
]
