"""
Dialog modules for ZebTrack application.

This package contains all dialog windows extracted from gui.py for better
modularity and maintainability. Each dialog is in its own module.
"""

from zebtrack.ui.dialogs.calibration_dialog import CalibrationDialog
from zebtrack.ui.dialogs.center_periphery_dialog import CenterPeripheryDialog
from zebtrack.ui.dialogs.color_selection_dialog import ColorSelectionDialog
from zebtrack.ui.dialogs.create_project_dialog import CreateProjectDialog
from zebtrack.ui.dialogs.diagnostic_progress_dialog import DiagnosticProgressDialog
from zebtrack.ui.dialogs.manage_weights_dialog import ManageWeightsDialog
from zebtrack.ui.dialogs.missing_metadata_dialog import MissingMetadataDialog
from zebtrack.ui.dialogs.pending_videos_dialog import PendingVideosDialog
from zebtrack.ui.dialogs.save_roi_template_dialog import SaveROITemplateDialog
from zebtrack.ui.dialogs.single_video_config_dialog import SingleVideoConfigDialog
from zebtrack.ui.dialogs.start_recording_dialog import StartRecordingDialog
from zebtrack.ui.dialogs.subject_selection_dialog import SubjectSelectionDialog
from zebtrack.ui.dialogs.template_dialog import TemplateDialog

__all__ = [
    "CalibrationDialog",
    "CenterPeripheryDialog",
    "ColorSelectionDialog",
    "CreateProjectDialog",
    "DiagnosticProgressDialog",
    "ManageWeightsDialog",
    "MissingMetadataDialog",
    "PendingVideosDialog",
    "SaveROITemplateDialog",
    "SingleVideoConfigDialog",
    "StartRecordingDialog",
    "SubjectSelectionDialog",
    "TemplateDialog",
]
