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
    app._gpu_hardware_display_var = StringVar(master=tkinter_root, value="")
    app.external_trigger_notice_var = StringVar(master=tkinter_root, value="")

    # Mock frames that will be created
    app.main_controls_frame = None
    app.model_configuration_tab_frame = None
    app.diagnostics_tab_frame = None
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
    controls_container = mock_app.main_controls_frame.winfo_children()[0]
    button_texts = [child.cget("text") for child in controls_container.winfo_children()]
    assert "Add Videos/Folders to the Project..." in button_texts
    assert "Process Pending Videos..." in button_texts
    assert "AI Model Config." in button_texts
    assert "AI Model Diagnostics" in button_texts
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


def test_build_zone_tab_mounts_the_analysis_window_panel(mock_app):
    """The START/STOP editor sits in the zone tab's left column, wired to the bus."""
    from zebtrack.ui.components.analysis_window_panel import AnalysisWindowPanel

    mock_app.controller.project_manager.project_data = {}
    builder = TabBuilder(mock_app)

    with (
        patch("zebtrack.ui.components.tab_builder.ZoneControlsWidget"),
        patch("zebtrack.ui.components.tab_builder.VideoDisplayWidget"),
    ):
        builder.build_zone_tab()

    panel = mock_app.analysis_window_panel
    assert isinstance(panel, AnalysisWindowPanel)
    assert panel.event_bus is mock_app.event_bus
    assert panel.project_manager is mock_app.controller.project_manager
    assert panel.winfo_manager() == "pack"
    assert panel.pack_info()["side"] == "bottom"


def test_analysis_window_panel_failure_does_not_block_the_zone_tab(mock_app):
    builder = TabBuilder(mock_app)

    with (
        patch("zebtrack.ui.components.tab_builder.ZoneControlsWidget"),
        patch("zebtrack.ui.components.tab_builder.VideoDisplayWidget"),
        patch(
            "zebtrack.ui.components.tab_builder.AnalysisWindowPanel",
            side_effect=RuntimeError("boom"),
        ),
    ):
        builder.build_zone_tab()

    assert mock_app.analysis_window_panel is None
    mock_app.event_dispatcher.subscribe_zone_component_events.assert_called_once()


def test_build_project_model_tabs_adds_notebook_tabs(mock_app):
    builder = TabBuilder(mock_app)

    with (
        patch(
            "zebtrack.ui.components.tab_builder.ProjectModelConfigurationPanel"
        ) as mock_config_panel,
        patch("zebtrack.ui.components.tab_builder.ModelDiagnosticsPanel") as mock_diag_panel,
    ):
        mock_config_panel.return_value = MagicMock()
        mock_diag_panel.return_value = MagicMock()

        builder.build_model_configuration_tab()
        builder.build_diagnostics_tab()

    tab_texts = [mock_app.notebook.tab(tab_id, "text") for tab_id in mock_app.notebook.tabs()]
    assert "AI Model Config." in tab_texts
    assert "AI Model Diagnostics" in tab_texts


# ======================================================================
# Pre-recorded main control: selection-aware start button
# ======================================================================


def _button_texts(frame):
    """Collect the text of every ttk.Button in a frame subtree."""
    texts = []
    for child in frame.winfo_children():
        if isinstance(child, ttk.Button):
            texts.append(str(child.cget("text")))
        texts.extend(_button_texts(child))
    return texts


class TestAnalyseSelectedButton:
    def test_pre_recorded_tab_offers_a_selection_aware_start_button(self, mock_app, tkinter_root):
        """Before this button the tab could only process EVERY pending video."""
        mock_app.project_manager.get_project_type.return_value = "pre-recorded"
        builder = TabBuilder(mock_app)

        frame = builder.build_main_controls_tab()
        tkinter_root.update_idletasks()

        assert any("Selected" in text for text in _button_texts(frame))

    def test_the_button_calls_the_selection_aware_handler(self, mock_app, tkinter_root):
        """Wiring it to PROJECT_PROCESS_VIDEOS directly would ignore the selection."""
        mock_app.project_manager.get_project_type.return_value = "pre-recorded"
        # Not on the ApplicationGUI spec (it is set in __init__), so the
        # MagicMock(spec=...) will not auto-create it.
        mock_app.dialog_manager = MagicMock()
        builder = TabBuilder(mock_app)
        builder.build_main_controls_tab()
        tkinter_root.update_idletasks()

        mock_app.analyze_selected_btn.invoke()

        mock_app.dialog_manager.handle_analyze_selected_videos_click.assert_called_once()

    def test_live_tab_does_not_grow_the_pre_recorded_button(self, mock_app, tkinter_root):
        mock_app.project_manager.get_project_type.return_value = "live"
        builder = TabBuilder(mock_app)

        frame = builder.build_main_controls_tab()
        tkinter_root.update_idletasks()

        assert not any("Selected" in text for text in _button_texts(frame))


def test_zone_tab_wires_the_class_roles_context(mock_app):
    """The window editor reads the project weight's class names through the context."""
    mock_app.controller.project_manager.project_data = {}
    builder = TabBuilder(mock_app)

    with (
        patch("zebtrack.ui.components.tab_builder.ZoneControlsWidget"),
        patch("zebtrack.ui.components.tab_builder.VideoDisplayWidget"),
        patch("zebtrack.ui.components.tab_builder.ProjectClassRolesContext") as context_cls,
    ):
        builder.build_zone_tab()

    context = context_cls.return_value
    kwargs = context_cls.call_args.kwargs
    assert kwargs["weight_manager"] is mock_app.controller.weight_manager
    assert kwargs["settings_obj"] is mock_app.controller.settings
    assert kwargs["project_manager_getter"]() is mock_app.project_manager
    assert mock_app.class_roles_context is context
    assert mock_app.analysis_window_panel._class_names_provider is context.class_names
    context.refresh.assert_called_once_with()

    # Names/roles arrived: overlays get the roles, the editor re-reads the names.
    context.overlay_roles.return_value = {0: "arena", 1: "subject"}
    context.class_names_by_id.return_value = {0: "arena", 1: "rat"}
    mock_app.analysis_window_panel = MagicMock()
    kwargs["on_change"]()
    assert mock_app.overlay_class_roles == {0: "arena", 1: "subject"}
    assert mock_app.overlay_class_names == {0: "arena", 1: "rat"}
    mock_app.analysis_window_panel.refresh_class_names.assert_called_once_with()


def test_zone_tab_without_model_service_keeps_free_text_classes(mock_app):
    mock_app.controller.project_manager.project_data = {}
    mock_app.controller.model_service = None
    builder = TabBuilder(mock_app)

    with (
        patch("zebtrack.ui.components.tab_builder.ZoneControlsWidget"),
        patch("zebtrack.ui.components.tab_builder.VideoDisplayWidget"),
    ):
        builder.build_zone_tab()

    assert mock_app.class_roles_context is None
    assert mock_app.overlay_class_roles is None
    assert mock_app.analysis_window_panel._class_names_provider is None


class TestMarkWindowEventButton:
    """v8 F5: the "Mark start/stop" button of a live project (ADR-011)."""

    def test_live_tab_has_the_button_wired_to_the_coordinator(self, mock_app):
        mock_app.project_manager.get_project_type.return_value = "live"
        mock_app.project_manager.project_path = "/tmp/project"
        builder = TabBuilder(mock_app)
        with patch("zebtrack.ui.components.tab_builder.ArduinoDashboardWidget"):
            builder.build_main_controls_tab()

        buttons = [
            widget
            for widget in _walk(mock_app.main_controls_frame)
            if isinstance(widget, ttk.Button) and widget.cget("text") == "Mark start/stop"
        ]
        assert len(buttons) == 1
        coordinator = mock_app.controller.live_camera_session_coordinator
        coordinator.mark_manual_window_event.return_value = True

        buttons[0].invoke()

        coordinator.mark_manual_window_event.assert_called_once_with()

    def test_without_a_running_window_the_status_bar_says_so(self, mock_app):
        mock_app.status_var = MagicMock()
        builder = TabBuilder(mock_app)
        coordinator = mock_app.controller.live_camera_session_coordinator
        coordinator.mark_manual_window_event.return_value = False

        assert builder._on_mark_window_event() is False
        mock_app.status_var.set.assert_called_once_with(
            "No live session with an analysis window is running."
        )

    def test_accepted_mark_leaves_the_status_bar_alone(self, mock_app):
        mock_app.status_var = MagicMock()
        builder = TabBuilder(mock_app)
        coordinator = mock_app.controller.live_camera_session_coordinator
        coordinator.mark_manual_window_event.return_value = True

        assert builder._on_mark_window_event() is True
        mock_app.status_var.set.assert_not_called()


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)
