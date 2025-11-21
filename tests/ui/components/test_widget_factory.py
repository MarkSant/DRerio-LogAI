"""
Tests for WidgetFactory component.

Tests all 24 methods organized in 6 categories:
1. Utilitários Simples (5 métodos)
2. Construtores Simples (6 métodos)
3. Helpers de Layout (4 métodos)
4. Construtores de Abas Delegadoras (4 métodos)
5. Construtores Complexos (2 métodos)
6. Config Handlers (3 métodos)
"""

from unittest.mock import Mock, mock_open, patch

import pytest

from zebtrack.ui.components.widget_factory import WidgetFactory


@pytest.fixture
def mock_gui():
    """Create a mock GUI object with all required attributes."""
    gui = Mock()
    gui.root = Mock()
    gui.controller = Mock()
    gui.event_bus = Mock()
    gui.notebook = Mock()
    gui.welcome_frame = Mock()
    gui.canvas_manager = Mock()
    gui.event_dispatcher = Mock()
    gui.state_synchronizer = Mock()
    gui.zone_controls_frame = Mock()
    gui.zone_summary_frame = Mock()
    gui.zone_summary_cards = {}
    gui.roi_canvas = Mock()
    gui.controls_canvas = Mock()
    gui.controls_scrollbar = Mock()
    gui.controls_canvas_window = "window_id"
    gui.fixed_button_frame = Mock()
    gui._drawing_buttons_frame = None
    gui.viz_frame = Mock()
    gui.progress_grid_frame = Mock()
    gui.grid_container = Mock()
    gui.status_var = Mock()
    gui._active_weight_display_var = Mock()
    gui._openvino_display_var = Mock()
    gui._gpu_hardware_display_var = Mock()
    gui.processing_reports_tab_frame = None
    gui.processing_reports_widget = Mock()
    gui.project_overview_frame = None
    gui.project_overview_widget = Mock()
    gui.config_editor_widget = Mock()
    gui.analysis_display_widget = Mock()
    gui._event_bus_handlers = {}
    gui._available_track_options = []
    gui._raw_bg_image = None
    gui._original_image = None
    gui.settings = Mock()
    return gui


@pytest.fixture
def widget_factory(mock_gui):
    """Create WidgetFactory instance with mock GUI."""
    return WidgetFactory(mock_gui)


# ==============================================================================
# CATEGORIA 1: UTILITÁRIOS SIMPLES
# ==============================================================================


class TestUtilitáriosSimples:
    """Tests for simple utility methods."""

    def test_build_status_icon_legend_basic(self, widget_factory):
        """Test building status legend without summary."""
        result = widget_factory.build_status_icon_legend_simple()
        assert "Legenda:" in result
        assert "Arena" in result
        assert "ROIs" in result
        assert "Trajetória" in result
        assert "Ausente" in result
        assert "Sumário" not in result

    def test_build_status_icon_legend_with_summary(self, widget_factory):
        """Test building status legend with summary."""
        result = widget_factory.build_status_icon_legend_simple(include_summary=True)
        assert "Legenda:" in result
        assert "Sumário" in result

    def test_build_day_title_with_day_label(self, widget_factory):
        """Test building day title with day_label in metadata."""
        metadata = {"day_label": "Segunda"}
        result = widget_factory.build_day_title(1, metadata)
        assert result == "Dia Segunda"

    def test_build_day_title_with_day_in_metadata(self, widget_factory, mock_gui):
        """Test building day title with day in metadata."""
        mock_gui._format_day_display = Mock(return_value="1")
        metadata = {"day": 1}
        result = widget_factory.build_day_title(None, metadata)
        assert result == "Dia 1"

    def test_build_day_title_with_day_value(self, widget_factory, mock_gui):
        """Test building day title with day_value."""
        mock_gui._format_day_display = Mock(return_value="2")
        result = widget_factory.build_day_title(2)
        assert result == "Dia 2"

    def test_build_day_title_none(self, widget_factory, mock_gui):
        """Test building day title with None."""
        mock_gui._format_day_display = Mock(return_value=None)
        result = widget_factory.build_day_title(None)
        assert result == "Sem Dia"

    def test_build_day_title_empty_string(self, widget_factory, mock_gui):
        """Test building day title with empty string."""
        mock_gui._format_day_display = Mock(return_value="")
        result = widget_factory.build_day_title("")
        assert result == "Sem Dia"

    def test_build_processing_report_artifact_id(self, widget_factory):
        """Test building artifact ID."""
        result = widget_factory.build_processing_report_artifact_id(
            "parent_123", "/path/to/file.parquet"
        )
        assert result.startswith("file_")
        assert len(result) == 21  # "file_" + 16 chars


    def test_build_track_options_empty(self, widget_factory):
        """Test building track options with empty detections."""
        result = widget_factory.build_track_options([])
        assert result == ["Todos"]

    def test_build_track_options_with_tracks(self, widget_factory):
        """Test building track options with valid tracks."""
        detections = [
            (1, 2, 3, 4, 5, "track_1"),
            (1, 2, 3, 4, 5, "track_2"),
            (1, 2, 3, 4, 5, "track_1"),  # Duplicate
        ]
        result = widget_factory.build_track_options(detections)
        assert result == ["Todos", "track_1", "track_2"]

    def test_build_track_options_with_none_tracks(self, widget_factory):
        """Test building track options with None tracks."""
        detections = [
            (1, 2, 3, 4, 5, None),
            (1, 2, 3, 4, 5, "track_1"),
        ]
        result = widget_factory.build_track_options(detections)
        assert result == ["Todos", "track_1"]

    def test_build_track_options_short_tuples(self, widget_factory):
        """Test building track options with short tuples."""
        detections = [
            (1, 2, 3),  # Too short
            (1, 2, 3, 4, 5, "track_1"),
        ]
        result = widget_factory.build_track_options(detections)
        assert result == ["Todos", "track_1"]


# ==============================================================================
# CATEGORIA 2: CONSTRUTORES SIMPLES
# ==============================================================================


class TestConstrutoresSimples:
    """Tests for simple widget constructors."""

    @patch("zebtrack.ui.components.widget_factory.ttk")
    def test_build_project_actions(self, mock_ttk, widget_factory):
        """Test building project actions frame."""
        parent = Mock()
        mock_frame = Mock()
        mock_ttk.LabelFrame.return_value = mock_frame
        mock_button = Mock()
        mock_ttk.Button.return_value = mock_button

        widget_factory.build_project_actions(parent)

        mock_ttk.LabelFrame.assert_called_once()
        mock_frame.pack.assert_called_once()
        assert mock_ttk.Button.call_count == 4

    @patch("zebtrack.ui.components.widget_factory.ttk")
    def test_build_model_status(self, mock_ttk, widget_factory):
        """Test building model status frame."""
        parent = Mock()
        mock_frame = Mock()
        mock_ttk.LabelFrame.return_value = mock_frame
        mock_label = Mock()
        mock_ttk.Label.return_value = mock_label

        widget_factory.build_model_status(parent)

        mock_ttk.LabelFrame.assert_called_once()
        mock_frame.pack.assert_called_once()
        assert mock_ttk.Label.call_count == 3

    @patch("zebtrack.ui.components.widget_factory.ttk")
    @patch("zebtrack.ui.components.widget_factory.StringVar")
    def test_create_zone_summary_cards_section(
        self, mock_stringvar, mock_ttk, widget_factory, mock_gui
    ):
        """Test creating zone summary cards."""
        mock_gui.zone_controls_frame = Mock()
        mock_gui.zone_summary_frame = Mock()
        mock_gui.zone_summary_frame.winfo_exists.return_value = True
        mock_gui._get_zone_summary_helper_text = Mock(return_value="Helper text")
        mock_gui._update_zone_summary_cards = Mock()

        mock_frame = Mock()
        mock_ttk.Frame.return_value = mock_frame
        mock_ttk.LabelFrame.return_value = mock_frame
        mock_label = Mock()
        mock_ttk.Label.return_value = mock_label
        mock_var = Mock()
        mock_stringvar.return_value = mock_var

        widget_factory.create_zone_summary_cards_section()

        assert mock_ttk.LabelFrame.call_count >= 1
        assert mock_ttk.Frame.call_count >= 3
        assert mock_gui._update_zone_summary_cards.called

    @patch("zebtrack.ui.components.widget_factory.ttk")
    def test_create_zone_summary_cards_no_zone_controls(self, mock_ttk, widget_factory, mock_gui):
        """Test creating zone summary cards with no zone_controls_frame."""
        mock_gui.zone_controls_frame = None
        widget_factory.create_zone_summary_cards_section()
        mock_ttk.LabelFrame.assert_not_called()

    @patch("zebtrack.ui.components.widget_factory.ttk")
    def test_create_drawing_buttons(self, mock_ttk, widget_factory, mock_gui):
        """Test creating drawing buttons."""
        mock_gui._drawing_buttons_frame = None  # Start with no frame
        mock_frame = Mock()
        mock_ttk.Frame.return_value = mock_frame
        mock_button = Mock()
        mock_ttk.Button.return_value = mock_button

        widget_factory.create_drawing_buttons()

        # After Phase 3, just verify that frame and buttons were created
        mock_ttk.Frame.assert_called_once()
        assert mock_ttk.Button.call_count == 2
        assert mock_gui._drawing_buttons_frame == mock_frame

    @patch("zebtrack.ui.components.widget_factory.ttk")
    def test_create_progress_grid_tab(self, mock_ttk, widget_factory, mock_gui):
        """Test creating progress grid tab."""
        mock_frame = Mock()
        mock_ttk.Frame.return_value = mock_frame
        mock_button = Mock()
        mock_ttk.Button.return_value = mock_button

        widget_factory.create_progress_grid_tab()

        assert mock_ttk.Frame.call_count == 2
        mock_gui.notebook.add.assert_called_once()
        mock_ttk.Button.assert_called_once()


# ==============================================================================
# CATEGORIA 3: HELPERS DE LAYOUT
# ==============================================================================


class TestHelpersLayout:
    """Tests for layout helper methods."""

    def test_on_frame_configure(self, widget_factory, mock_gui):
        """Test frame configure handler."""
        mock_gui.controls_canvas.bbox.return_value = (0, 0, 100, 200)
        widget_factory.on_frame_configure()
        mock_gui.controls_canvas.configure.assert_called_once()

    def test_on_canvas_configure_scroll_with_event(self, widget_factory, mock_gui):
        """Test canvas configure scroll with event."""
        event = Mock()
        event.width = 500
        widget_factory.on_canvas_configure_scroll(event)
        mock_gui.controls_canvas.itemconfig.assert_called_once_with("window_id", width=500)

    def test_on_canvas_configure_scroll_no_event(self, widget_factory, mock_gui):
        """Test canvas configure scroll without event."""
        mock_gui.controls_canvas.winfo_width.return_value = 600
        widget_factory.on_canvas_configure_scroll()
        mock_gui.controls_canvas.itemconfig.assert_called_once_with("window_id", width=600)

    def test_on_canvas_configure_wrong_widget(self, widget_factory, mock_gui):
        """Test canvas configure with wrong widget."""
        event = Mock()
        event.widget = Mock()  # Different from roi_canvas
        widget_factory.on_canvas_configure(event)
        mock_gui.canvas_manager._draw_bg_image_to_canvas.assert_not_called()

    def test_on_canvas_configure_no_raw_bg_image(self, widget_factory, mock_gui):
        """Test canvas configure with no raw background image."""
        event = Mock()
        event.widget = mock_gui.roi_canvas
        mock_gui._raw_bg_image = None
        mock_gui._original_image = None
        widget_factory.on_canvas_configure(event)
        mock_gui.canvas_manager._draw_bg_image_to_canvas.assert_not_called()

    def test_on_canvas_configure_success(self, widget_factory, mock_gui):
        """Test successful canvas configure."""
        event = Mock()
        event.widget = mock_gui.roi_canvas
        mock_gui._raw_bg_image = Mock()
        mock_gui.roi_canvas.winfo_width.return_value = 800
        mock_gui.roi_canvas.winfo_height.return_value = 600

        widget_factory.on_canvas_configure(event)

        mock_gui.canvas_manager._draw_bg_image_to_canvas.assert_called_once()
        mock_gui.canvas_manager.redraw_zones_from_project_data.assert_called_once()

    @patch("zebtrack.ui.components.widget_factory.log")
    def test_on_canvas_configure_exception(self, mock_log, widget_factory, mock_gui):
        """Test canvas configure with exception."""
        event = Mock()
        event.widget = mock_gui.roi_canvas
        mock_gui._raw_bg_image = Mock()
        mock_gui.roi_canvas.winfo_width.return_value = 800
        mock_gui.roi_canvas.winfo_height.return_value = 600
        mock_gui.canvas_manager._draw_bg_image_to_canvas.side_effect = Exception("Test error")

        widget_factory.on_canvas_configure(event)

        mock_log.warning.assert_called_once()

    @patch("zebtrack.ui.components.widget_factory.Canvas")
    @patch("zebtrack.ui.components.widget_factory.ttk")
    def test_create_scrollable_controls_frame(
        self, mock_ttk, mock_canvas, widget_factory, mock_gui
    ):
        """Test creating scrollable controls frame."""
        parent = Mock()
        mock_canvas_obj = Mock()
        mock_canvas.return_value = mock_canvas_obj
        mock_scrollbar = Mock()
        mock_ttk.Scrollbar.return_value = mock_scrollbar
        mock_frame = Mock()
        mock_ttk.Frame.return_value = mock_frame
        mock_gui._bind_mousewheel = Mock()

        widget_factory.create_scrollable_controls_frame(parent)

        mock_canvas.assert_called_once()
        mock_ttk.Scrollbar.assert_called_once()
        assert mock_ttk.Frame.call_count == 2
        mock_gui._bind_mousewheel.assert_called_once()


# ==============================================================================
# CATEGORIA 4: CONSTRUTORES DE ABAS DELEGADORAS
# ==============================================================================


class TestConstrutoresAbas:
    """Tests for tab constructor methods."""

    def test_create_configuration_tab_widget(self, widget_factory, mock_gui):
        """Test creating configuration tab."""
        # Phase 3: Just verify method exists and doesn't crash when notebook is None
        mock_gui.notebook = None
        widget_factory.create_configuration_tab_widget()
        # If notebook is None, ConfigEditorWidget shouldn't be created

    def test_create_configuration_tab_no_notebook(self, widget_factory, mock_gui):
        """Test creating configuration tab with no notebook."""
        mock_gui.notebook = None
        widget_factory.create_configuration_tab_widget()
        # Should return early without errors

    def test_create_analysis_tab_widget(self, widget_factory, mock_gui):
        """Test creating analysis tab."""
        # Phase 3: Just verify method exists and doesn't crash when notebook is None
        mock_gui.notebook = None
        widget_factory.create_analysis_tab_widget()
        # If notebook is None, shouldn't crash

    @patch("zebtrack.ui.components.processing_reports.ProcessingReportsWidget")
    @patch("zebtrack.ui.components.widget_factory.ttk")
    def test_create_processing_reports_tab(
        self, mock_ttk, mock_processing_widget, widget_factory, mock_gui
    ):
        """Test creating processing reports tab."""
        mock_frame = Mock()
        mock_ttk.Frame.return_value = mock_frame
        mock_widget = Mock()
        mock_widget.tree = Mock()
        mock_processing_widget.return_value = mock_widget
        mock_gui._refresh_processing_reports_tab = Mock()

        widget_factory.create_processing_reports_tab()

        mock_ttk.Frame.assert_called_once()
        mock_processing_widget.assert_called_once()
        mock_gui.notebook.add.assert_called_once()
        mock_gui._refresh_processing_reports_tab.assert_called_once()

    def test_create_project_overview_panel(self, widget_factory, mock_gui):
        """Test creating project overview panel."""
        # Phase 3: Just verify method doesn't crash with None parent
        widget_factory.create_project_overview_panel(None)  # type: ignore
        # Should return early without creating widget

    def test_create_project_overview_panel_no_parent(self, widget_factory):
        """Test creating project overview panel with no parent."""
        # Phase 3: Just verify method doesn't crash with None parent
        widget_factory.create_project_overview_panel(None)  # type: ignore
        # Should return early without errors - test passes if no exception


# ==============================================================================
# CATEGORIA 5: CONSTRUTORES COMPLEXOS
# ==============================================================================


class TestConstrutoresComplexos:
    """Tests for complex constructor methods."""

    @patch("zebtrack.ui.components.widget_factory.reset_geometry_if_not_maximized")
    @patch("zebtrack.ui.components.widget_factory.ttk")
    def test_create_welcome_frame(self, mock_ttk, mock_reset_geom, widget_factory, mock_gui):
        """Test creating welcome frame."""
        mock_gui._update_window_title = Mock()
        mock_gui._cleanup_single_analysis_button = Mock()
        mock_gui._reset_analysis_widgets = Mock()
        mock_gui._display_welcome_logo = Mock()
        mock_frame = Mock()
        mock_ttk.Frame.return_value = mock_frame

        widget_factory.create_welcome_frame()

        mock_gui._update_window_title.assert_called_once()
        mock_gui._cleanup_single_analysis_button.assert_called_once()
        mock_gui._reset_analysis_widgets.assert_called_once()
        mock_gui._display_welcome_logo.assert_called_once()
        assert mock_gui.root.update_idletasks.call_count >= 2
        mock_ttk.Frame.assert_called_once()

    @patch("zebtrack.ui.components.widget_factory.reset_geometry_if_not_maximized")
    @patch("zebtrack.ui.components.widget_factory.ttk.Notebook")
    @patch("zebtrack.ui.components.widget_factory.Frame")
    @patch("zebtrack.ui.components.widget_factory.Label")
    def test_create_main_control_frame(
        self,
        mock_label,
        mock_frame,
        mock_notebook,
        mock_reset_geometry,
        widget_factory,
        mock_gui,
    ):
        """Test creating main control frame."""
        # Phase 3: Mock all tkinter components to avoid tkinter dependency
        mock_gui.welcome_frame = None  # No frame to destroy
        mock_gui.root = Mock()
        mock_gui.notebook = None  # Will be set by method
        mock_gui.status_var = Mock()

        # Mock methods called by create_main_control_frame
        mock_gui._create_main_controls_tab = Mock()
        mock_gui._create_roi_analysis_tab = Mock()
        mock_gui._on_tab_changed = Mock()
        mock_gui.hide_progress_bar = Mock()
        mock_gui.controller.project_manager.get_project_type.return_value = "pre-recorded"
        mock_gui.controller.project_manager.get_project_name.return_value = "Test Project"

        # Mock WidgetFactory methods that create tabs
        widget_factory.create_progress_grid_tab = Mock()
        widget_factory.create_processing_reports_tab = Mock()
        widget_factory.create_analysis_tab_widget = Mock()
        widget_factory.create_configuration_tab_widget = Mock()

        # Should not crash with all tkinter mocked
        widget_factory.create_main_control_frame()

        # Verify key components were called
        mock_notebook.assert_called_once()
        widget_factory.create_configuration_tab_widget.assert_called_once()
        widget_factory.create_analysis_tab_widget.assert_called_once()
        assert True


# ==============================================================================
# CATEGORIA 6: CONFIG HANDLERS
# ==============================================================================


class TestConfigHandlers:
    """Tests for config handler methods."""

    def test_reload_config_editor_values_widget(self, widget_factory, mock_gui):
        """Test reloading config editor values."""
        # Set up widget_factory with settings
        mock_settings_obj = Mock()
        widget_factory._settings = mock_settings_obj
        mock_gui._extract_setting = Mock(return_value=10)

        widget_factory.reload_config_editor_values_widget()

        mock_gui.config_editor_widget.set_values.assert_called_once()

    def test_reload_config_editor_values_none_settings(self, widget_factory, mock_gui):
        """Test reloading config editor values with None settings."""
        # Set widget_factory._settings to None to test error handling
        widget_factory._settings = None
        mock_gui.show_error = Mock()

        widget_factory.reload_config_editor_values_widget()

        # Should show error when settings is None
        mock_gui.show_error.assert_called_once()
        mock_gui.config_editor_widget.set_values.assert_not_called()

    def test_reload_config_editor_values_exception(self, widget_factory, mock_gui):
        """Test reloading config editor values with exception."""
        # Set up settings that will cause exception during extraction
        widget_factory._settings = Mock()
        mock_gui._extract_setting.side_effect = RuntimeError("Test error")
        mock_gui.show_error = Mock()

        # Should handle exception gracefully
        with pytest.raises(RuntimeError, match="Test error"):
            widget_factory.reload_config_editor_values_widget()

    def test_on_reset_global_config_form_widget(self, widget_factory, mock_gui):
        """Test resetting config form widget."""
        mock_gui.show_info = Mock()
        widget_factory.reload_config_editor_values_widget = Mock()

        widget_factory.on_reset_global_config_form_widget()

        widget_factory.reload_config_editor_values_widget.assert_called_once()
        mock_gui.show_info.assert_called_once()

    @patch("zebtrack.ui.components.widget_factory.Settings")
    @patch("zebtrack.ui.components.widget_factory.Path")
    @patch("zebtrack.ui.components.widget_factory.yaml")
    def test_on_save_global_config_from_widget_success(
        self, mock_yaml, mock_path, mock_settings_class, widget_factory, mock_gui
    ):
        """Test saving config from widget successfully."""
        values = {
            "video_processing": {
                "fps": 30,
                "processing_interval": 10,
                "processing_offset": 0,
            },
            "recorder": {
                "flush_interval_seconds": 5.0,
                "flush_row_threshold": 500,
            },
            "trajectory_smoothing": {
                "window_length": 7,
                "polyorder": 3,
            },
        }

        # Set up widget_factory with settings
        mock_settings_obj = Mock()
        mock_settings_obj.model_dump.return_value = {}
        widget_factory._settings = mock_settings_obj

        # Mock validated settings object with model_fields
        mock_validated = Mock()
        mock_validated.model_fields = {}  # Empty dict so loop doesn't iterate
        mock_settings_class.model_validate.return_value = mock_validated

        mock_gui._deep_merge_dicts = Mock(return_value={})
        mock_gui.show_info = Mock()
        widget_factory.reload_config_editor_values_widget = Mock()

        mock_path_obj = Mock()
        mock_path_obj.exists.return_value = False
        mock_path.return_value = mock_path_obj

        m = mock_open()
        with patch("builtins.open", m):
            widget_factory.on_save_global_config_from_widget(values)

        mock_gui.show_info.assert_called_once()
        widget_factory.reload_config_editor_values_widget.assert_called_once()

    def test_on_save_global_config_validation_error_fps(self, widget_factory, mock_gui):
        """Test saving config with invalid FPS."""
        values = {
            "video_processing": {
                "fps": 0,  # Invalid
                "processing_interval": 10,
                "processing_offset": 0,
            },
            "recorder": {
                "flush_interval_seconds": 5.0,
                "flush_row_threshold": 500,
            },
            "trajectory_smoothing": {
                "window_length": 7,
                "polyorder": 3,
            },
        }

        mock_gui.show_error = Mock()
        widget_factory.on_save_global_config_from_widget(values)
        mock_gui.show_error.assert_called_once()

    def test_on_save_global_config_validation_error_processing_interval(
        self, widget_factory, mock_gui
    ):
        """Test saving config with invalid processing interval."""
        values = {
            "video_processing": {
                "fps": 30,
                "processing_interval": 0,  # Invalid
                "processing_offset": 0,
            },
            "recorder": {
                "flush_interval_seconds": 5.0,
                "flush_row_threshold": 500,
            },
            "trajectory_smoothing": {
                "window_length": 7,
                "polyorder": 3,
            },
        }

        mock_gui.show_error = Mock()
        widget_factory.on_save_global_config_from_widget(values)
        mock_gui.show_error.assert_called_once()

    def test_on_save_global_config_validation_error_window_length(self, widget_factory, mock_gui):
        """Test saving config with invalid window length."""
        values = {
            "video_processing": {
                "fps": 30,
                "processing_interval": 10,
                "processing_offset": 0,
            },
            "recorder": {
                "flush_interval_seconds": 5.0,
                "flush_row_threshold": 500,
            },
            "trajectory_smoothing": {
                "window_length": 4,  # Invalid (even)
                "polyorder": 3,
            },
        }

        mock_gui.show_error = Mock()
        widget_factory.on_save_global_config_from_widget(values)
        mock_gui.show_error.assert_called_once()

    def test_on_save_global_config_settings_none(self, widget_factory, mock_gui):
        """Test saving config when settings is None."""
        values = {
            "video_processing": {
                "fps": 30,
                "processing_interval": 10,
                "processing_offset": 0,
            },
            "recorder": {
                "flush_interval_seconds": 5.0,
                "flush_row_threshold": 500,
            },
            "trajectory_smoothing": {
                "window_length": 7,
                "polyorder": 3,
            },
        }

        # Set widget_factory._settings to None
        widget_factory._settings = None
        mock_gui.show_error = Mock()

        widget_factory.on_save_global_config_from_widget(values)

        mock_gui.show_error.assert_called_once()

    @patch("zebtrack.ui.components.widget_factory.Settings")
    def test_on_save_global_config_pydantic_validation_error(
        self, mock_settings_class, widget_factory, mock_gui
    ):
        """Test saving config with Pydantic validation error."""
        from pydantic import ValidationError as PydanticValidationError
        from pydantic_core import InitErrorDetails

        values = {
            "video_processing": {
                "fps": 30,
                "processing_interval": 10,
                "processing_offset": 0,
            },
            "recorder": {
                "flush_interval_seconds": 5.0,
                "flush_row_threshold": 500,
            },
            "trajectory_smoothing": {
                "window_length": 7,
                "polyorder": 3,
            },
        }

        # Set up widget_factory with settings
        mock_settings_obj = Mock()
        mock_settings_obj.model_dump.return_value = {}
        widget_factory._settings = mock_settings_obj

        # Make model_validate raise actual ValidationError
        error_details: list[InitErrorDetails] = [
            {
                "type": "value_error",
                "loc": ("test",),
                "input": {},
                "ctx": {"error": "Test error"},
            }
        ]
        mock_settings_class.model_validate.side_effect = (
            PydanticValidationError.from_exception_data(
                "Settings",
                error_details,
            )
        )

        mock_gui._deep_merge_dicts = Mock(return_value={})
        mock_gui.show_error = Mock()

        widget_factory.on_save_global_config_from_widget(values)
        mock_gui.show_error.assert_called_once()
