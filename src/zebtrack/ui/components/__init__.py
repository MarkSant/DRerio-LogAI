"""
UI components package - reusable, testable Tkinter composite widgets.

This package contains modular UI components extracted from the monolithic
ApplicationGUI class. Each component is a ttk.Frame subclass that:
- Contains only UI logic
- Emits events via the event bus for user actions
- Is testable in isolation
- Can be reused across different parts of the application
"""

from zebtrack.ui.components.analysis_controls import AnalysisControlsWidget
from zebtrack.ui.components.analysis_display import AnalysisDisplayWidget
from zebtrack.ui.components.arduino_dashboard import ArduinoDashboardWidget
from zebtrack.ui.components.base import BaseWidget
from zebtrack.ui.components.base_component import BaseUIComponent, UIComponentError
from zebtrack.ui.components.canvas_manager import CanvasManager
from zebtrack.ui.components.config_editor import ConfigEditorWidget
from zebtrack.ui.components.control_panel import ControlPanelWidget
from zebtrack.ui.components.dialog_manager import DialogManager
from zebtrack.ui.components.drawing_state_manager import DrawingStateManager
from zebtrack.ui.components.event_dispatcher import EventDispatcher
from zebtrack.ui.components.menu_manager import MenuManager
from zebtrack.ui.components.polygon_drawing_service import PolygonDrawingService
from zebtrack.ui.components.project_overview import ProjectOverviewWidget
from zebtrack.ui.components.project_view_manager import ProjectViewManager
from zebtrack.ui.components.state_synchronizer import StateSynchronizer
from zebtrack.ui.components.validation_manager import ValidationManager
from zebtrack.ui.components.video_display import VideoDisplayWidget
from zebtrack.ui.components.widget_factory import WidgetFactory
from zebtrack.ui.components.zone_controls import ZoneControlsWidget

__all__ = [
    "AnalysisControlsWidget",
    "AnalysisDisplayWidget",
    "ArduinoDashboardWidget",
    "BaseUIComponent",
    "BaseWidget",
    "CanvasManager",
    "ConfigEditorWidget",
    "ControlPanelWidget",
    "DialogManager",
    "DrawingStateManager",
    "EventDispatcher",
    "MenuManager",
    "PolygonDrawingService",
    "ProjectOverviewWidget",
    "ProjectViewManager",
    "StateSynchronizer",
    "UIComponentError",
    "ValidationManager",
    "VideoDisplayWidget",
    "WidgetFactory",
    "ZoneControlsWidget",
]
