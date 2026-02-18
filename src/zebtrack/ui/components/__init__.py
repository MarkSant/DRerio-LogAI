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
from zebtrack.ui.components.analysis_view_controller import AnalysisViewController
from zebtrack.ui.components.arduino_dashboard import ArduinoDashboardWidget
from zebtrack.ui.components.base import BaseWidget
from zebtrack.ui.components.base_component import BaseUIComponent, UIComponentError
from zebtrack.ui.components.behavioral_config_widget import BehavioralConfigWidget
from zebtrack.ui.components.canvas.multi_aquarium_overlay import MultiAquariumOverlayManager
from zebtrack.ui.components.canvas.video_frame_manager import VideoFrameManager
from zebtrack.ui.components.canvas.zone_editor import ZoneEditor
from zebtrack.ui.components.canvas_manager import CanvasManager
from zebtrack.ui.components.config_editor import ConfigEditorWidget
from zebtrack.ui.components.control_panel import ControlPanelWidget
from zebtrack.ui.components.dialog_manager import DialogManager
from zebtrack.ui.components.drawing_state_manager import DrawingStateManager
from zebtrack.ui.components.event_dispatcher import EventDispatcher
from zebtrack.ui.components.menu_manager import MenuManager
from zebtrack.ui.components.polygon_drawing_service import PolygonDrawingService
from zebtrack.ui.components.project_initializer import ProjectInitializer
from zebtrack.ui.components.project_overview import ProjectOverviewWidget
from zebtrack.ui.components.project_views import (
    ReportsTreeManager,
    VideoSelectorTreeManager,
)
from zebtrack.ui.components.roi_template_manager import ROITemplateManager
from zebtrack.ui.components.single_video_workflow import SingleVideoWorkflow
from zebtrack.ui.components.state_synchronizer import StateSynchronizer
from zebtrack.ui.components.tab_builder import TabBuilder
from zebtrack.ui.components.validation_manager import ValidationManager
from zebtrack.ui.components.video_display import VideoDisplayWidget
from zebtrack.ui.components.weight_hardware_manager import WeightHardwareManager
from zebtrack.ui.components.widget_factory import WidgetFactory
from zebtrack.ui.components.zone_controls import ZoneControlsWidget
from zebtrack.ui.components.zone_edit_guard import ZoneEditGuard

__all__ = [
    "AnalysisControlsWidget",
    "AnalysisDisplayWidget",
    "AnalysisViewController",
    "ArduinoDashboardWidget",
    "BaseUIComponent",
    "BaseWidget",
    "BehavioralConfigWidget",
    "CanvasManager",
    "ConfigEditorWidget",
    "ControlPanelWidget",
    "DialogManager",
    "DrawingStateManager",
    "EventDispatcher",
    "MenuManager",
    "MultiAquariumOverlayManager",
    "PolygonDrawingService",
    "ProjectInitializer",
    "ProjectOverviewWidget",
    "ROITemplateManager",
    "ReportsTreeManager",
    "SingleVideoWorkflow",
    "StateSynchronizer",
    "TabBuilder",
    "UIComponentError",
    "ValidationManager",
    "VideoDisplayWidget",
    "VideoFrameManager",
    "VideoSelectorTreeManager",
    "WeightHardwareManager",
    "WidgetFactory",
    "ZoneControlsWidget",
    "ZoneEditGuard",
    "ZoneEditor",
]
