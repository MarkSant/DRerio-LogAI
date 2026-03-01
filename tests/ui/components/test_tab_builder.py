from tkinter import StringVar, ttk
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.ui.components.tab_builder import TabBuilder
from zebtrack.ui.gui import ApplicationGUI

pytestmark = pytest.mark.gui


@pytest.fixture
def mock_app(tkinter_root):
    """Create a mock ApplicationGUI."""
    app = MagicMock(spec=ApplicationGUI)
    app.root = tkinter_root
    app.controller = MagicMock()
    app.event_dispatcher = MagicMock()
    app.widget_factory = MagicMock()
    app.event_bus = MagicMock()  # Added missing mock
    app.event_bus_v2 = MagicMock()
    app.project_manager = MagicMock()
    app.menu_manager = MagicMock()
    app.canvas_manager = MagicMock()
    app._subscribe_zone_component_events = MagicMock()
    app._on_canvas_configure = MagicMock()

    # Use a real notebook because ttkbootstrap inspects parent widget class hierarchy
    app.notebook = ttk.Notebook(tkinter_root)

    # Mock variables with master=tkinter_root
    app.analysis_interval_var = StringVar(master=tkinter_root, value="10")
    app.display_interval_var = StringVar(master=tkinter_root, value="10")
    app._active_weight_display_var = StringVar(master=tkinter_root, value="")
    app._openvino_display_var = StringVar(master=tkinter_root, value="")
    app.external_trigger_notice_var = StringVar(master=tkinter_root, value="")

    # Mock frames that will be created
    app.main_controls_frame = None
    app.external_trigger_notice_label = None

    return app


def test_init(mock_app):
    """Test TabBuilder initialization."""
    builder = TabBuilder(mock_app)
    assert builder.gui == mock_app


def test_build_main_controls_tab_pre_recorded(mock_app):
    """Test creating main controls tab for pre-recorded project."""
    # Setup
    mock_app.project_manager.get_project_type.return_value = "pre-recorded"
    mock_app.project_manager.project_path = "/tmp/project"

    # Create builder
    builder = TabBuilder(mock_app)

    # Act
    builder.build_main_controls_tab()

    # Assert
    # Verify frame creation
    assert mock_app.main_controls_frame is not None
    assert isinstance(mock_app.main_controls_frame, ttk.Frame)

    # Verify delegation calls on the GUI object (since GUI is mocked)
    mock_app._create_project_overview_panel.assert_called_once()
    # mock_app._request_overview_refresh.assert_called_once() # Removed in Phase 3.2


def test_build_main_controls_tab_live(mock_app):
    """Test creating main controls tab for live project."""
    # Setup
    mock_app.project_manager.get_project_type.return_value = "live"
    mock_app.project_manager.project_path = "/tmp/project"

    # Create builder
    builder = TabBuilder(mock_app)

    # Act
    with patch("zebtrack.ui.components.tab_builder.ArduinoDashboardWidget"):
        builder.build_main_controls_tab()

    # Assert
    # Verify frame creation
    assert mock_app.main_controls_frame is not None

    # Verify external trigger notice label was created
    assert mock_app.external_trigger_notice_label is not None


def test_build_zone_tab_sets_up_components(mock_app):
    """Test that build_zone_tab wires controls and subscriptions."""
    builder = TabBuilder(mock_app)

    with (
        patch("zebtrack.ui.components.tab_builder.ZoneControlsWidget") as mock_zone_controls,
        patch("zebtrack.ui.components.tab_builder.VideoDisplayWidget") as mock_video_display,
    ):
        mock_zone_instance = MagicMock()
        mock_zone_instance.stabilization_frames_var = MagicMock()
        mock_zone_instance.zone_controls_frame = MagicMock()
        mock_zone_instance.fixed_button_frame = MagicMock()
        mock_zone_instance.controls_canvas = MagicMock()
        mock_zone_instance.controls_canvas_window = MagicMock()
        mock_zone_controls.return_value = mock_zone_instance

        mock_video_instance = MagicMock()
        mock_video_instance.canvas = MagicMock()
        mock_video_display.return_value = mock_video_instance

        builder.build_zone_tab()

    mock_app.menu_manager.create_roi_context_menu.assert_called_once()
    mock_app.event_dispatcher.subscribe_zone_component_events.assert_called_once()
    assert mock_app.zone_controls is mock_zone_instance
    assert mock_app.video_display is mock_video_instance
