"""Tests for EventDispatcher component."""

from unittest.mock import Mock, patch

import numpy as np
import pytest

from zebtrack.ui.components.event_dispatcher import EventDispatcher
from zebtrack.ui.event_bus import CallableEvent, EventBus, EventType, NamedEvent, UIEvent
from zebtrack.ui.events import Events


@pytest.fixture(autouse=True)
def block_all_dialogs():
    """Automatically block ALL dialog windows for all tests in this file."""
    with patch("tkinter.messagebox.showerror"), \
         patch("tkinter.messagebox.showwarning"), \
         patch("tkinter.messagebox.showinfo"), \
         patch("tkinter.messagebox.askyesno", return_value=False), \
         patch("tkinter.messagebox.askokcancel", return_value=False), \
         patch("tkinter.messagebox.askyesnocancel", return_value=None):
        yield


@pytest.fixture
def mock_event_bus():
    """Create a mock EventBus instance."""
    bus = Mock(spec=EventBus)
    bus.subscribe = Mock()
    bus.publish = Mock()
    bus.publish_event = Mock(return_value=True)
    bus.drain = Mock(return_value=[])
    bus.size = Mock(return_value=0)
    bus.dispatch_named_event = Mock()
    return bus


@pytest.fixture
def mock_gui(tkinter_root, mock_event_bus):
    """Create a mock ApplicationGUI instance."""
    gui = Mock()
    gui.root = tkinter_root
    # Mock the Tkinter after() method to prevent real callbacks
    gui.root.after = Mock(return_value="after#0")
    gui.root.after_cancel = Mock()
    gui.event_bus = mock_event_bus
    gui.controller = Mock()
    gui._event_bus_after_id = None
    gui._event_bus_poll_interval_ms = 100

    # Mock GUI methods
    gui.set_status = Mock()
    gui.update_idletasks = Mock()
    gui._create_welcome_frame = Mock()
    gui._load_project_view = Mock()
    gui.start_analysis_view_mode = Mock()
    gui._switch_to_analysis_view = Mock()
    gui.update_weights_dropdown = Mock()
    gui.set_active_weight_in_dropdown = Mock()
    gui.update_openvino_checkbox = Mock()
    gui.redraw_zones_from_project_data = Mock()
    gui.update_zone_listbox = Mock()
    gui.display_frame = Mock()
    gui.update_detection_overlay = Mock()
    gui.show_external_trigger_notice = Mock()
    gui.clear_external_trigger_notice = Mock()
    gui.update_progress_stats = Mock()
    gui.update_analysis_metadata = Mock()
    gui.update_analysis_task_status = Mock()
    gui.update_social_summary = Mock()
    gui.show_error = Mock()
    gui.show_warning = Mock()
    gui.show_info = Mock()
    gui.update_button_state = Mock()
    gui.refresh_project_views = Mock()
    gui.update_openvino_status_display = Mock()
    gui.setup_interactive_polygon = Mock()
    gui.display_roi_video_frame = Mock()
    gui.update_processing_mode = Mock()
    gui._prompt_for_weight_type = Mock(return_value="yolo11n")
    gui._request_overview_refresh = Mock()
    gui._on_project_overview_tree_double_click_impl = Mock()
    gui._show_project_overview_context_menu = Mock()
    gui._on_auto_detect_clicked = Mock()

    # Zone component methods
    gui._toggle_canvas_view = Mock()
    gui._start_main_arena_drawing = Mock()
    gui._start_roi_drawing = Mock()
    gui._on_save_arena = Mock()
    gui._on_discard_arena = Mock()
    gui._on_apply_roi_template = Mock()
    gui._on_save_roi_template = Mock()
    gui._on_import_roi_template = Mock()
    gui._edit_selected_zone_vertices = Mock()
    gui._on_zone_right_click = Mock()
    gui._load_selected_video_frame = Mock()
    gui._refresh_video_selector_tree = Mock()

    # Widgets
    gui.arduino_dashboard_widget = Mock()
    gui.zone_listbox = Mock()
    gui.zone_listbox.winfo_rootx = Mock(return_value=100)
    gui.zone_listbox.winfo_rooty = Mock(return_value=200)
    gui.notebook = Mock()
    gui.zone_tab_frame = Mock()

    return gui


@pytest.fixture
def event_dispatcher(mock_gui):
    """Create an EventDispatcher instance for testing."""
    return EventDispatcher(mock_gui)


@pytest.mark.gui
class TestEventDispatcher:
    """Tests for EventDispatcher component."""

    # =========================================================================
    # Subscription Tests
    # =========================================================================

    def test_subscribe_to_ui_events_registers_all_handlers(self, event_dispatcher, mock_event_bus):
        """Test that subscribe_to_ui_events registers all 33 UI event handlers."""
        event_dispatcher.subscribe_to_ui_events()

        # Verify subscribe was called 33 times (one for each UI event handler)
        assert mock_event_bus.subscribe.call_count == 33

        # Verify key events are registered
        event_names = [c[0][0] for c in mock_event_bus.subscribe.call_args_list]
        assert Events.UI_SET_STATUS in event_names
        assert Events.UI_SHOW_ERROR in event_names
        assert Events.UI_NAVIGATE_TO_WELCOME in event_names
        assert Events.UI_UPDATE_WEIGHTS_LIST in event_names
        assert Events.UI_REDRAW_ZONES in event_names
        assert Events.UI_UPDATE_ARDUINO_STATUS in event_names

    def test_subscribe_to_ui_events_no_event_bus(self, event_dispatcher):
        """Test that subscribe_to_ui_events returns early if no event bus."""
        event_dispatcher.gui.event_bus = None
        event_dispatcher.subscribe_to_ui_events()
        # Should not raise any exception

    def test_subscribe_zone_component_events_registers_handlers(
        self, event_dispatcher, mock_event_bus
    ):
        """Test that subscribe_zone_component_events registers zone handlers."""
        event_dispatcher.subscribe_zone_component_events()

        # Should subscribe to zone events
        assert mock_event_bus.subscribe.call_count > 0

        # Verify key zone events are registered
        event_names = [c[0][0] for c in mock_event_bus.subscribe.call_args_list]
        assert "zone.toggle_view" in event_names
        assert "zone.draw_arena" in event_names
        assert "zone.draw_roi" in event_names
        assert "zone.auto_detect_clicked" in event_names

    def test_subscribe_zone_component_events_no_event_bus(self, event_dispatcher):
        """Test that subscribe_zone_component_events returns early if no event bus."""
        event_dispatcher.gui.event_bus = None
        event_dispatcher.subscribe_zone_component_events()
        # Should not raise any exception

    # =========================================================================
    # UI Feedback Event Handlers
    # =========================================================================

    def test_handle_set_status(self, event_dispatcher, mock_gui):
        """Test _handle_set_status updates status bar."""
        event_dispatcher._handle_set_status({"message": "Test status"})

        mock_gui.set_status.assert_called_once_with("Test status")
        mock_gui.update_idletasks.assert_called_once()

    def test_handle_set_status_no_message(self, event_dispatcher, mock_gui):
        """Test _handle_set_status with empty data."""
        event_dispatcher._handle_set_status({})

        mock_gui.set_status.assert_called_once_with("")

    @pytest.mark.parametrize(
        "handler_name,event_method,expected_title,expected_message",
        [
            ("_handle_show_error", "show_error", "Erro", "Error message"),
            ("_handle_show_warning", "show_warning", "Aviso", "Warning message"),
            ("_handle_show_info", "show_info", "Informação", "Info message"),
        ],
    )
    def test_handle_show_messages(
        self,
        event_dispatcher,
        mock_gui,
        handler_name,
        event_method,
        expected_title,
        expected_message,
    ):
        """Test message display handlers."""
        handler = getattr(event_dispatcher, handler_name)
        gui_method = getattr(mock_gui, event_method)

        handler({"title": expected_title, "message": expected_message})

        gui_method.assert_called_once_with(expected_title, expected_message)

    def test_handle_show_error_defaults(self, event_dispatcher, mock_gui):
        """Test _handle_show_error with default values."""
        event_dispatcher._handle_show_error({})

        mock_gui.show_error.assert_called_once_with("Erro", "")

    def test_handle_update_button_state(self, event_dispatcher, mock_gui):
        """Test _handle_update_button_state."""
        event_dispatcher._handle_update_button_state(
            {"button_name": "start_btn", "state": "disabled"}
        )

        mock_gui.update_button_state.assert_called_once_with("start_btn", "disabled")

    # =========================================================================
    # Navigation Event Handlers
    # =========================================================================

    def test_handle_navigate_to_welcome(self, event_dispatcher, mock_gui):
        """Test _handle_navigate_to_welcome."""
        event_dispatcher._handle_navigate_to_welcome({})

        mock_gui._create_welcome_frame.assert_called_once()

    def test_handle_navigate_to_project_view(self, event_dispatcher, mock_gui):
        """Test _handle_navigate_to_project_view."""
        event_dispatcher._handle_navigate_to_project_view({})

        mock_gui._load_project_view.assert_called_once()

    def test_handle_navigate_to_analysis_view_activate(self, event_dispatcher, mock_gui):
        """Test _handle_navigate_to_analysis_view with activate_mode=True."""
        event_dispatcher._handle_navigate_to_analysis_view({"activate_mode": True})

        mock_gui.start_analysis_view_mode.assert_called_once()
        mock_gui._switch_to_analysis_view.assert_not_called()

    def test_handle_navigate_to_analysis_view_no_activate(self, event_dispatcher, mock_gui):
        """Test _handle_navigate_to_analysis_view with activate_mode=False."""
        event_dispatcher._handle_navigate_to_analysis_view({"activate_mode": False})

        mock_gui._switch_to_analysis_view.assert_called_once()
        mock_gui.start_analysis_view_mode.assert_not_called()

    def test_handle_navigate_to_analysis_view_default(self, event_dispatcher, mock_gui):
        """Test _handle_navigate_to_analysis_view with default activate_mode."""
        event_dispatcher._handle_navigate_to_analysis_view({})

        mock_gui.start_analysis_view_mode.assert_called_once()

    def test_handle_select_tab_zone(self, event_dispatcher, mock_gui):
        """Test _handle_select_tab selects zone tab."""
        event_dispatcher._handle_select_tab({"tab_name": "zone_tab"})

        mock_gui.notebook.select.assert_called_once_with(mock_gui.zone_tab_frame)

    def test_handle_select_tab_other(self, event_dispatcher, mock_gui):
        """Test _handle_select_tab with non-zone tab."""
        event_dispatcher._handle_select_tab({"tab_name": "other_tab"})

        mock_gui.notebook.select.assert_not_called()

    def test_handle_refresh_project_views(self, event_dispatcher, mock_gui):
        """Test _handle_refresh_project_views with all parameters."""
        event_dispatcher._handle_refresh_project_views(
            {"reason": "test_reason", "append_summary": True, "immediate": True}
        )

        mock_gui.refresh_project_views.assert_called_once_with(
            reason="test_reason", append_summary=True, immediate=True
        )

    def test_handle_refresh_project_views_defaults(self, event_dispatcher, mock_gui):
        """Test _handle_refresh_project_views with default values."""
        event_dispatcher._handle_refresh_project_views({})

        mock_gui.refresh_project_views.assert_called_once_with(
            reason=None, append_summary=False, immediate=False
        )

    # =========================================================================
    # Weight/Model Event Handlers
    # =========================================================================

    def test_handle_update_weights_list(self, event_dispatcher, mock_gui):
        """Test _handle_update_weights_list."""
        weights = ["yolo11n.pt", "yolo11s.pt"]
        event_dispatcher._handle_update_weights_list({"weights": weights})

        mock_gui.update_weights_dropdown.assert_called_once_with(weights)

    def test_handle_update_weights_list_empty(self, event_dispatcher, mock_gui):
        """Test _handle_update_weights_list with no weights."""
        event_dispatcher._handle_update_weights_list({})

        mock_gui.update_weights_dropdown.assert_called_once_with([])

    def test_handle_set_active_weight(self, event_dispatcher, mock_gui):
        """Test _handle_set_active_weight."""
        event_dispatcher._handle_set_active_weight({"weight_name": "yolo11n.pt"})

        mock_gui.set_active_weight_in_dropdown.assert_called_once_with("yolo11n.pt")

    def test_handle_update_openvino_checkbox(self, event_dispatcher, mock_gui):
        """Test _handle_update_openvino_checkbox."""
        event_dispatcher._handle_update_openvino_checkbox({"is_checked": True})

        mock_gui.update_openvino_checkbox.assert_called_once_with(True)

    def test_handle_update_openvino_checkbox_default(self, event_dispatcher, mock_gui):
        """Test _handle_update_openvino_checkbox with default value."""
        event_dispatcher._handle_update_openvino_checkbox({})

        mock_gui.update_openvino_checkbox.assert_called_once_with(False)

    def test_handle_update_openvino_status(self, event_dispatcher, mock_gui):
        """Test _handle_update_openvino_status."""
        event_dispatcher._handle_update_openvino_status({"status": "enabled"})

        mock_gui.update_openvino_status_display.assert_called_once_with("enabled")

    def test_handle_update_openvino_status_default(self, event_dispatcher, mock_gui):
        """Test _handle_update_openvino_status with default value."""
        event_dispatcher._handle_update_openvino_status({})

        mock_gui.update_openvino_status_display.assert_called_once_with("")

    @patch("zebtrack.ui.components.event_dispatcher.filedialog")
    def test_handle_request_weight_file_selected(self, mock_filedialog, event_dispatcher):
        """Test _handle_request_weight_file when file is selected."""
        mock_filedialog.askopenfilename.return_value = "/path/to/weight.pt"

        event_dispatcher._handle_request_weight_file({})

        mock_filedialog.askopenfilename.assert_called_once()
        event_dispatcher.gui.event_bus.publish_event.assert_called_once_with(
            Events.MODEL_LOAD_NEW_WEIGHT, {"filepath": "/path/to/weight.pt"}
        )

    @patch("zebtrack.ui.components.event_dispatcher.filedialog")
    def test_handle_request_weight_file_cancelled(self, mock_filedialog, event_dispatcher):
        """Test _handle_request_weight_file when user cancels."""
        mock_filedialog.askopenfilename.return_value = ""

        event_dispatcher._handle_request_weight_file({})

        event_dispatcher.gui.event_bus.publish_event.assert_not_called()

    def test_handle_request_weight_type_selected(self, event_dispatcher, mock_gui):
        """Test _handle_request_weight_type when type is selected."""
        mock_gui._prompt_for_weight_type.return_value = "yolo11n"

        event_dispatcher._handle_request_weight_type({})

        event_dispatcher.gui.event_bus.publish_event.assert_called_once_with(
            Events.MODEL_LOAD_NEW_WEIGHT, {"weight_type": "yolo11n"}
        )

    def test_handle_request_weight_type_cancelled(self, event_dispatcher, mock_gui):
        """Test _handle_request_weight_type when user cancels."""
        mock_gui._prompt_for_weight_type.return_value = None

        event_dispatcher._handle_request_weight_type({})

        event_dispatcher.gui.event_bus.publish_event.assert_not_called()

    @patch("zebtrack.ui.components.event_dispatcher.messagebox")
    def test_handle_request_weight_action_yes(self, mock_messagebox, event_dispatcher):
        """Test _handle_request_weight_action when user chooses Yes."""
        mock_messagebox.askyesnocancel.return_value = True

        event_dispatcher._handle_request_weight_action({"weight_type": "yolo11n"})

        event_dispatcher.gui.event_bus.publish_event.assert_called_once_with(
            Events.MODEL_LOAD_NEW_WEIGHT, {"choice": "yes"}
        )

    @patch("zebtrack.ui.components.event_dispatcher.messagebox")
    def test_handle_request_weight_action_no(self, mock_messagebox, event_dispatcher):
        """Test _handle_request_weight_action when user chooses No."""
        mock_messagebox.askyesnocancel.return_value = False

        event_dispatcher._handle_request_weight_action({"weight_type": "yolo11n"})

        event_dispatcher.gui.event_bus.publish_event.assert_called_once_with(
            Events.MODEL_LOAD_NEW_WEIGHT, {"choice": "no"}
        )

    @patch("zebtrack.ui.components.event_dispatcher.messagebox")
    def test_handle_request_weight_action_cancel(self, mock_messagebox, event_dispatcher):
        """Test _handle_request_weight_action when user cancels."""
        mock_messagebox.askyesnocancel.return_value = None

        event_dispatcher._handle_request_weight_action({"weight_type": "yolo11n"})

        event_dispatcher.gui.event_bus.publish_event.assert_called_once_with(
            Events.MODEL_LOAD_NEW_WEIGHT, {"choice": "cancel"}
        )

    @patch("zebtrack.ui.components.event_dispatcher.ManageWeightsDialog")
    def test_handle_open_manage_weights_dialog(self, mock_dialog, event_dispatcher, mock_gui):
        """Test _handle_open_manage_weights_dialog."""
        event_dispatcher._handle_open_manage_weights_dialog({})

        mock_dialog.assert_called_once_with(mock_gui.root, mock_gui.controller)

    # =========================================================================
    # Zone/Drawing Event Handlers
    # =========================================================================

    def test_handle_redraw_zones(self, event_dispatcher, mock_gui):
        """Test _handle_redraw_zones."""
        zone_data = {"arena": [], "rois": []}
        event_dispatcher._handle_redraw_zones({"zone_data": zone_data})

        mock_gui.redraw_zones_from_project_data.assert_called_once_with(zone_data)

    def test_handle_redraw_zones_no_data(self, event_dispatcher, mock_gui):
        """Test _handle_redraw_zones with no zone data."""
        event_dispatcher._handle_redraw_zones({})

        mock_gui.redraw_zones_from_project_data.assert_called_once_with(None)

    def test_handle_update_zone_list(self, event_dispatcher, mock_gui):
        """Test _handle_update_zone_list."""
        zone_data = {"arena": [], "rois": []}
        event_dispatcher._handle_update_zone_list({"zone_data": zone_data})

        mock_gui.update_zone_listbox.assert_called_once_with(zone_data)

    def test_handle_setup_interactive_polygon(self, event_dispatcher, mock_gui):
        """Test _handle_setup_interactive_polygon with valid polygon."""
        polygon = [[0, 0], [100, 0], [100, 100], [0, 100]]
        event_dispatcher._handle_setup_interactive_polygon({"polygon": polygon})

        # Should convert to numpy array and call setup_interactive_polygon
        assert mock_gui.setup_interactive_polygon.call_count == 1
        np.testing.assert_array_equal(
            mock_gui.setup_interactive_polygon.call_args[0][0], np.array(polygon)
        )

    def test_handle_setup_interactive_polygon_none(self, event_dispatcher, mock_gui):
        """Test _handle_setup_interactive_polygon with None polygon."""
        event_dispatcher._handle_setup_interactive_polygon({"polygon": None})

        mock_gui.setup_interactive_polygon.assert_not_called()

    # =========================================================================
    # Frame/Display Event Handlers
    # =========================================================================

    def test_handle_display_frame(self, event_dispatcher, mock_gui):
        """Test _handle_display_frame."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        event_dispatcher._handle_display_frame({"frame": frame})

        mock_gui.display_frame.assert_called_once()
        np.testing.assert_array_equal(mock_gui.display_frame.call_args[0][0], frame)

    def test_handle_update_detection_overlay(self, event_dispatcher, mock_gui):
        """Test _handle_update_detection_overlay."""
        detections = [{"track_id": 1, "bbox": [10, 20, 30, 40]}]
        report = Mock()

        event_dispatcher._handle_update_detection_overlay(
            {"detections": detections, "report": report}
        )

        mock_gui.update_detection_overlay.assert_called_once_with(detections, report)

    def test_handle_display_video_frame(self, event_dispatcher, mock_gui):
        """Test _handle_display_video_frame."""
        event_dispatcher._handle_display_video_frame({"video_path": "/path/to/video.mp4"})

        mock_gui.display_roi_video_frame.assert_called_once_with("/path/to/video.mp4")

    # =========================================================================
    # Arduino Event Handlers
    # =========================================================================

    def test_handle_update_arduino_status_connected(self, event_dispatcher, mock_gui):
        """Test _handle_update_arduino_status when connected."""
        event_dispatcher._handle_update_arduino_status({"connected": True, "port": "COM3"})

        mock_gui.arduino_dashboard_widget.update_status.assert_called_once_with(True, "COM3")

    def test_handle_update_arduino_status_no_widget(self, event_dispatcher, mock_gui):
        """Test _handle_update_arduino_status when widget doesn't exist."""
        mock_gui.arduino_dashboard_widget = None

        event_dispatcher._handle_update_arduino_status({"connected": False, "port": None})
        # Should not raise exception

    def test_handle_append_arduino_log(self, event_dispatcher, mock_gui):
        """Test _handle_append_arduino_log."""
        event_dispatcher._handle_append_arduino_log({"message": "Test log message"})

        mock_gui.arduino_dashboard_widget.append_log.assert_called_once_with("Test log message")

    def test_handle_append_arduino_log_no_widget(self, event_dispatcher, mock_gui):
        """Test _handle_append_arduino_log when widget doesn't exist."""
        mock_gui.arduino_dashboard_widget = None

        event_dispatcher._handle_append_arduino_log({"message": "Test"})
        # Should not raise exception

    def test_handle_show_external_trigger_notice(self, event_dispatcher, mock_gui):
        """Test _handle_show_external_trigger_notice."""
        data = {"context": "recording", "info": "trigger active"}
        event_dispatcher._handle_show_external_trigger_notice(data)

        mock_gui.show_external_trigger_notice.assert_called_once_with(
            context="recording", info="trigger active"
        )

    def test_handle_clear_external_trigger_notice(self, event_dispatcher, mock_gui):
        """Test _handle_clear_external_trigger_notice."""
        event_dispatcher._handle_clear_external_trigger_notice({})

        mock_gui.clear_external_trigger_notice.assert_called_once()

    # =========================================================================
    # Processing Event Handlers
    # =========================================================================

    def test_handle_update_processing_stats(self, event_dispatcher, mock_gui):
        """Test _handle_update_processing_stats with all stats."""
        event_dispatcher._handle_update_processing_stats(
            {
                "stats": {
                    "total_frames": 1000,
                    "processed_frames": 500,
                    "detected_frames": 450,
                    "percent": 50.0,
                    "elapsed": "00:05:00",
                    "eta": "00:05:00",
                }
            }
        )

        mock_gui.update_progress_stats.assert_called_once_with(
            total=1000,
            processed=500,
            detected=450,
            percent=50.0,
            elapsed="00:05:00",
            eta="00:05:00",
        )

    def test_handle_update_processing_stats_empty(self, event_dispatcher, mock_gui):
        """Test _handle_update_processing_stats with empty stats."""
        event_dispatcher._handle_update_processing_stats({})

        mock_gui.update_progress_stats.assert_called_once_with(
            total=None, processed=None, detected=None, percent=None, elapsed=None, eta=None
        )

    def test_handle_update_analysis_metadata(self, event_dispatcher, mock_gui):
        """Test _handle_update_analysis_metadata."""
        metadata = {"video": "test.mp4", "fps": 30}
        event_dispatcher._handle_update_analysis_metadata(metadata)

        mock_gui.update_analysis_metadata.assert_called_once_with(video="test.mp4", fps=30)

    def test_handle_update_analysis_task_status(self, event_dispatcher, mock_gui):
        """Test _handle_update_analysis_task_status."""
        event_dispatcher._handle_update_analysis_task_status(
            {"payload": {"task": "detection", "status": "running"}}
        )

        mock_gui.update_analysis_task_status.assert_called_once_with(
            task="detection", status="running"
        )

    def test_handle_update_social_summary(self, event_dispatcher, mock_gui):
        """Test _handle_update_social_summary."""
        summary = {"total_interactions": 42}
        event_dispatcher._handle_update_social_summary(summary)

        mock_gui.update_social_summary.assert_called_once_with(total_interactions=42)

    def test_handle_update_processing_mode(self, event_dispatcher, mock_gui):
        """Test _handle_update_processing_mode."""
        report = Mock()
        event_dispatcher._handle_update_processing_mode({"report": report})

        mock_gui.update_processing_mode.assert_called_once_with(report)

    # =========================================================================
    # Project/Zone Component Event Handlers
    # =========================================================================

    def test_handle_project_refresh_requested(self, event_dispatcher, mock_gui):
        """Test _handle_project_refresh_requested."""
        event_dispatcher._handle_project_refresh_requested({})

        mock_gui._request_overview_refresh.assert_called_once_with(immediate=True)

    def test_handle_project_video_double_click(self, event_dispatcher, mock_gui):
        """Test _handle_project_video_double_click."""
        event_dispatcher._handle_project_video_double_click({"item_id": "video_123"})

        mock_gui._on_project_overview_tree_double_click_impl.assert_called_once_with("video_123")

    def test_handle_project_video_double_click_no_item_id(self, event_dispatcher, mock_gui):
        """Test _handle_project_video_double_click without item_id."""
        event_dispatcher._handle_project_video_double_click({})

        mock_gui._on_project_overview_tree_double_click_impl.assert_not_called()

    def test_handle_project_video_right_click(self, event_dispatcher, mock_gui):
        """Test _handle_project_video_right_click."""
        event_dispatcher._handle_project_video_right_click(
            {"item_id": "video_123", "x": 100, "y": 200}
        )

        mock_gui._show_project_overview_context_menu.assert_called_once_with("video_123", 100, 200)

    def test_handle_project_video_right_click_missing_data(self, event_dispatcher, mock_gui):
        """Test _handle_project_video_right_click with missing data."""
        event_dispatcher._handle_project_video_right_click({"item_id": "video_123"})

        mock_gui._show_project_overview_context_menu.assert_not_called()

    def test_handle_zone_auto_detect_event_with_frames(self, event_dispatcher, mock_gui):
        """Test _handle_zone_auto_detect_event with stabilization_frames."""
        event_dispatcher._handle_zone_auto_detect_event({"stabilization_frames": 30})

        mock_gui._on_auto_detect_clicked.assert_called_once_with(stabilization_frames=30)

    def test_handle_zone_auto_detect_event_no_data(self, event_dispatcher, mock_gui):
        """Test _handle_zone_auto_detect_event without data."""
        event_dispatcher._handle_zone_auto_detect_event(None)

        mock_gui._on_auto_detect_clicked.assert_called_once_with(stabilization_frames=None)

    # =========================================================================
    # Event Bus Coordination
    # =========================================================================

    def test_register_event_bus_handlers(self, event_dispatcher):
        """Test register_event_bus_handlers registers CALLABLE and NAMED handlers."""
        event_dispatcher.register_event_bus_handlers()

        assert EventType.CALLABLE in event_dispatcher._event_bus_handlers
        assert EventType.NAMED in event_dispatcher._event_bus_handlers
        assert (
            event_dispatcher._event_bus_handlers[EventType.CALLABLE]
            == event_dispatcher._handle_callable_event
        )
        assert (
            event_dispatcher._event_bus_handlers[EventType.NAMED]
            == event_dispatcher._handle_named_event
        )

    def test_handle_callable_event_success(self, event_dispatcher):
        """Test _handle_callable_event executes callback successfully."""
        mock_callback = Mock()
        payload = CallableEvent(callback=mock_callback, args=(1, 2), kwargs={"key": "value"})

        event_dispatcher._handle_callable_event(payload)

        mock_callback.assert_called_once_with(1, 2, key="value")

    def test_handle_callable_event_exception(self, event_dispatcher):
        """Test _handle_callable_event handles exceptions gracefully."""
        mock_callback = Mock(side_effect=ValueError("Test error"))
        payload = CallableEvent(callback=mock_callback, args=(), kwargs={})

        # Should not raise, just log warning
        event_dispatcher._handle_callable_event(payload)

        mock_callback.assert_called_once()

    def test_handle_named_event_success(self, event_dispatcher, mock_event_bus):
        """Test _handle_named_event dispatches event successfully."""
        payload = NamedEvent(event_name="test:event", data={"key": "value"})

        event_dispatcher._handle_named_event(payload)

        mock_event_bus.dispatch_named_event.assert_called_once_with(payload)

    def test_handle_named_event_no_event_bus(self, event_dispatcher):
        """Test _handle_named_event when event bus is None."""
        event_dispatcher.gui.event_bus = None
        payload = NamedEvent(event_name="test:event", data={})

        # Should not raise exception
        event_dispatcher._handle_named_event(payload)

    def test_handle_named_event_exception(self, event_dispatcher, mock_event_bus):
        """Test _handle_named_event handles exceptions gracefully."""
        mock_event_bus.dispatch_named_event.side_effect = ValueError("Test error")
        payload = NamedEvent(event_name="test:event", data={})

        # Should not raise, just log warning
        event_dispatcher._handle_named_event(payload)

    def test_publish_event_with_event_bus(self, event_dispatcher, mock_event_bus):
        """Test publish_event publishes via event bus."""
        event_dispatcher.publish_event("test:event", {"key": "value"})

        mock_event_bus.publish_event.assert_called_once_with("test:event", {"key": "value"})

    def test_publish_event_no_data(self, event_dispatcher, mock_event_bus):
        """Test publish_event with no data."""
        event_dispatcher.publish_event("test:event")

        mock_event_bus.publish_event.assert_called_once_with("test:event", {})

    def test_publish_event_no_event_bus(self, event_dispatcher):
        """Test publish_event falls back gracefully when no event bus."""
        event_dispatcher.gui.event_bus = None

        # Should not raise exception, just log debug
        event_dispatcher.publish_event("test:event", {"key": "value"})

    def test_schedule_event_bus_poll_initial(self, event_dispatcher, mock_gui):
        """Test schedule_event_bus_poll schedules first poll."""
        event_dispatcher.schedule_event_bus_poll()

        # Should have scheduled a poll
        assert mock_gui._event_bus_after_id is not None
        mock_gui.root.after.assert_called_once()

    def test_schedule_event_bus_poll_already_scheduled(self, event_dispatcher, mock_gui):
        """Test schedule_event_bus_poll when already scheduled."""
        mock_gui._event_bus_after_id = "existing_id"

        event_dispatcher.schedule_event_bus_poll()

        # Should not schedule again
        mock_gui.root.after.assert_not_called()

    def test_schedule_event_bus_poll_no_event_bus(self, event_dispatcher, mock_gui):
        """Test schedule_event_bus_poll when no event bus."""
        mock_gui.event_bus = None

        event_dispatcher.schedule_event_bus_poll()

        # Should not schedule
        mock_gui.root.after.assert_not_called()
        assert mock_gui._event_bus_after_id is None

    def test_poll_event_bus_processes_events(self, event_dispatcher, mock_event_bus, mock_gui):
        """Test poll_event_bus processes events from the bus."""
        # Setup handlers
        event_dispatcher.register_event_bus_handlers()

        # Create mock events
        callable_event = UIEvent(
            type=EventType.CALLABLE, payload=CallableEvent(callback=Mock(), args=(), kwargs={})
        )
        named_event = UIEvent(
            type=EventType.NAMED, payload=NamedEvent(event_name="test:event", data={})
        )

        mock_event_bus.drain.return_value = [callable_event, named_event]

        event_dispatcher.poll_event_bus()

        # Should have processed both events
        mock_event_bus.drain.assert_called_once_with(max_items=50)
        callable_event.payload.callback.assert_called_once()
        mock_event_bus.dispatch_named_event.assert_called_once()

        # Should reschedule
        assert mock_gui.root.after.call_count > 0

    def test_poll_event_bus_no_events(self, event_dispatcher, mock_event_bus, mock_gui):
        """Test poll_event_bus when no events in queue."""
        mock_event_bus.drain.return_value = []

        event_dispatcher.poll_event_bus()

        # Should still reschedule
        assert mock_gui.root.after.call_count > 0

    def test_poll_event_bus_no_event_bus(self, event_dispatcher, mock_gui):
        """Test poll_event_bus when event bus is None."""
        mock_gui.event_bus = None

        event_dispatcher.poll_event_bus()

        # Should not schedule another poll
        mock_gui.root.after.assert_not_called()

    def test_poll_event_bus_unknown_event_type(self, event_dispatcher, mock_event_bus, mock_gui):
        """Test poll_event_bus with unknown event type."""
        event_dispatcher.register_event_bus_handlers()

        # Create event with unknown type (should never happen in practice)
        unknown_event = UIEvent(type=Mock(), payload=Mock())
        mock_event_bus.drain.return_value = [unknown_event]

        # Should handle gracefully
        event_dispatcher.poll_event_bus()

        # Should still reschedule
        assert mock_gui.root.after.call_count > 0

    def test_poll_event_bus_handler_exception(self, event_dispatcher, mock_event_bus, mock_gui):
        """Test poll_event_bus when handler raises exception."""
        event_dispatcher.register_event_bus_handlers()

        # Create event that will cause exception
        bad_callback = Mock(side_effect=ValueError("Test error"))
        error_event = UIEvent(
            type=EventType.CALLABLE,
            payload=CallableEvent(callback=bad_callback, args=(), kwargs={}),
        )
        mock_event_bus.drain.return_value = [error_event]

        # Should handle exception gracefully
        event_dispatcher.poll_event_bus()

        # Should still reschedule
        assert mock_gui.root.after.call_count > 0

    def test_stop_event_bus_polling(self, event_dispatcher, mock_gui):
        """Test stop_event_bus_polling cancels scheduled poll."""
        mock_gui._event_bus_after_id = "test_id"

        event_dispatcher.stop_event_bus_polling()

        mock_gui.root.after_cancel.assert_called_once_with("test_id")
        assert mock_gui._event_bus_after_id is None

    def test_stop_event_bus_polling_not_scheduled(self, event_dispatcher, mock_gui):
        """Test stop_event_bus_polling when nothing is scheduled."""
        mock_gui._event_bus_after_id = None

        event_dispatcher.stop_event_bus_polling()

        mock_gui.root.after_cancel.assert_not_called()

    def test_stop_event_bus_polling_exception(self, event_dispatcher, mock_gui):
        """Test stop_event_bus_polling handles exception gracefully."""
        mock_gui._event_bus_after_id = "test_id"
        mock_gui.root.after_cancel.side_effect = ValueError("Test error")

        # Should handle exception and still clear the ID
        event_dispatcher.stop_event_bus_polling()

        assert mock_gui._event_bus_after_id is None

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def test_create_mock_event_with_coordinates(self, event_dispatcher, mock_gui):
        """Test _create_mock_event creates proper event object."""
        mock_gui.zone_listbox.winfo_rootx.return_value = 100
        mock_gui.zone_listbox.winfo_rooty.return_value = 200

        data = {"x": 150, "y": 250}
        event = event_dispatcher._create_mock_event(data)

        assert event.x_root == 150
        assert event.y_root == 250
        assert event.x == 50  # 150 - 100
        assert event.y == 50  # 250 - 200

    def test_create_mock_event_no_coordinates(self, event_dispatcher, mock_gui):
        """Test _create_mock_event with missing coordinates."""
        data = {}
        event = event_dispatcher._create_mock_event(data)

        assert event.x_root == 0
        assert event.y_root == 0
        assert event.x == 0
        assert event.y == 0

    def test_create_mock_event_no_zone_listbox(self, event_dispatcher, mock_gui):
        """Test _create_mock_event when zone_listbox is None."""
        mock_gui.zone_listbox = None
        data = {"x": 150, "y": 250}

        event = event_dispatcher._create_mock_event(data)

        assert event.x_root == 150
        assert event.y_root == 250
        assert event.x == 0
        assert event.y == 0

    # =========================================================================
    # Integration Tests - Zone Component Events
    # =========================================================================

    def test_zone_component_events_integration(self, event_dispatcher, mock_event_bus, mock_gui):
        """Test integration of zone component event subscriptions."""
        event_dispatcher.subscribe_zone_component_events()

        # Extract subscribed handlers
        subscriptions = {c[0][0]: c[0][1] for c in mock_event_bus.subscribe.call_args_list}

        # Test zone.toggle_view
        if "zone.toggle_view" in subscriptions:
            subscriptions["zone.toggle_view"]({})
            mock_gui._toggle_canvas_view.assert_called_once()

        # Test zone.draw_arena
        if "zone.draw_arena" in subscriptions:
            subscriptions["zone.draw_arena"]({})
            mock_gui._start_main_arena_drawing.assert_called_once()

    def test_zone_list_item_right_click_integration(
        self, event_dispatcher, mock_event_bus, mock_gui
    ):
        """Test zone list right-click creates proper mock event."""
        event_dispatcher.subscribe_zone_component_events()

        # Find the handler for zone.list_item_right_click
        subscriptions = {c[0][0]: c[0][1] for c in mock_event_bus.subscribe.call_args_list}

        if "zone.list_item_right_click" in subscriptions:
            handler = subscriptions["zone.list_item_right_click"]
            handler({"x": 150, "y": 250})

            # Should have called _on_zone_right_click with mock event
            assert mock_gui._on_zone_right_click.call_count == 1
            event_arg = mock_gui._on_zone_right_click.call_args[0][0]
            assert event_arg.x_root == 150
            assert event_arg.y_root == 250

    # =========================================================================
    # Edge Cases
    # =========================================================================

    def test_handle_methods_with_none_data(self, event_dispatcher, mock_gui):
        """Test that handlers handle None in data dict gracefully."""
        # Test a few representative handlers
        event_dispatcher._handle_update_weights_list({"weights": None})
        event_dispatcher._handle_set_active_weight({"weight_name": None})
        event_dispatcher._handle_update_arduino_status({"connected": None, "port": None})

        # Should not raise exceptions

    def test_multiple_poll_cycles(self, event_dispatcher, mock_event_bus, mock_gui):
        """Test multiple event bus poll cycles."""
        event_dispatcher.register_event_bus_handlers()
        mock_event_bus.drain.return_value = []

        # First poll
        event_dispatcher.poll_event_bus()
        assert mock_gui.root.after.call_count >= 1

        # Reset and poll again
        mock_gui._event_bus_after_id = None
        event_dispatcher.poll_event_bus()
        assert mock_gui.root.after.call_count >= 2

    def test_large_event_queue(self, event_dispatcher, mock_event_bus, mock_gui):
        """Test processing large number of events."""
        event_dispatcher.register_event_bus_handlers()

        # Create 100 callable events
        events = [
            UIEvent(
                type=EventType.CALLABLE, payload=CallableEvent(callback=Mock(), args=(), kwargs={})
            )
            for _ in range(100)
        ]

        # drain returns max 50 items
        mock_event_bus.drain.return_value = events[:50]

        event_dispatcher.poll_event_bus()

        # Should have processed 50 events (the limit)
        mock_event_bus.drain.assert_called_once_with(max_items=50)
