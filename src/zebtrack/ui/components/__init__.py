"""
UI components package - reusable, testable Tkinter composite widgets.

This package contains modular UI components extracted from the monolithic
ApplicationGUI class. Each component is a ttk.Frame subclass that:
- Contains only UI logic
- Emits events via the event bus for user actions
- Is testable in isolation
- Can be reused across different parts of the application
"""

from zebtrack.ui.components.base import BaseWidget
from zebtrack.ui.components.video_display import VideoDisplayWidget
from zebtrack.ui.components.zone_controls import ZoneControlsWidget
from zebtrack.ui.components.control_panel import ControlPanelWidget
from zebtrack.ui.components.project_overview import ProjectOverviewWidget
from zebtrack.ui.components.analysis_controls import AnalysisControlsWidget

__all__ = [
    "BaseWidget",
    "VideoDisplayWidget",
    "ZoneControlsWidget",
    "ControlPanelWidget",
    "ProjectOverviewWidget",
    "AnalysisControlsWidget",
]
