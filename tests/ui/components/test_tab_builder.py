from tkinter import StringVar, ttk
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.ui.components.tab_builder import TabBuilder
from zebtrack.ui.gui import ApplicationGUI


@pytest.fixture
def mock_app(tkinter_root):
    """Create a mock ApplicationGUI."""
    app = MagicMock(spec=ApplicationGUI)
    app.root = tkinter_root
    app.controller = MagicMock()
    app.event_dispatcher = MagicMock()
    app.widget_factory = MagicMock()
    app.event_bus = MagicMock() # Added missing mock

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

    return app

def test_init(mock_app):
    """Test TabBuilder initialization."""
    builder = TabBuilder(mock_app)
    assert builder.gui == mock_app

def test_build_main_controls_tab_pre_recorded(mock_app):
    """Test creating main controls tab for pre-recorded project."""
    # Setup
    mock_app.controller.project_manager.get_project_type.return_value = "pre-recorded"
    mock_app.controller.project_manager.project_path = "/tmp/project"

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
    mock_app._request_overview_refresh.assert_called_once()

def test_build_main_controls_tab_live(mock_app):
    """Test creating main controls tab for live project."""
    # Setup
    mock_app.controller.project_manager.get_project_type.return_value = "live"
    mock_app.controller.project_manager.project_path = "/tmp/project"

    # Create builder
    builder = TabBuilder(mock_app)

    # Act
    with patch("zebtrack.ui.components.tab_builder.ArduinoDashboardWidget") as MockArduino:
        builder.build_main_controls_tab()

    # Assert
    # Verify frame creation
    assert mock_app.main_controls_frame is not None

    # Verify external trigger notice label was created
    assert mock_app.external_trigger_notice_label is not None
