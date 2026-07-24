"""
Tests for ZoneControlBuilder.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from zebtrack.ui.builders.zone_control_builder import ZoneControlBuilder
from zebtrack.ui.event_bus_v2 import UIEvents


def _conclude_gui(*, editing_zone, edited_points):
    """Minimal gui stub for _on_conclude_video tests."""
    controller = SimpleNamespace(project_manager=Mock())
    return SimpleNamespace(
        controller=controller,
        _zones_dirty=True,
        event_bus=Mock(),
        canvas_manager=SimpleNamespace(current_editing_zone=editing_zone),
        edited_polygon_points=list(edited_points),
        set_status=Mock(),
        current_editing_zone=editing_zone,
    )


def _published_types(gui):
    return [call.args[0].type for call in gui.event_bus.publish.call_args_list]


def test_conclude_video_only_saves_without_active_edit():
    """Concluir persists zone editing without starting recording or analysis."""
    gui = _conclude_gui(editing_zone=None, edited_points=[])
    builder = ZoneControlBuilder(gui, event_bus_v2=Mock())

    builder._on_conclude_video()

    types = _published_types(gui)
    assert UIEvents.ZONE_SAVE_ARENA not in types
    assert UIEvents.LIVE_RECORDING_RESUME_REQUESTED not in types
    assert gui._zones_dirty is False


def test_conclude_video_saves_arena_when_editing_active():
    """When an interactive edit is in progress, Concluir also commits it."""
    gui = _conclude_gui(editing_zone="arena", edited_points=[[0, 0], [1, 1], [2, 2]])
    builder = ZoneControlBuilder(gui, event_bus_v2=Mock())

    builder._on_conclude_video()

    types = _published_types(gui)
    assert UIEvents.ZONE_SAVE_ARENA in types
    assert UIEvents.LIVE_RECORDING_RESUME_REQUESTED not in types


def test_conclude_video_single_video_mode_does_not_start_analysis():
    """Concluir never starts analysis, even in the legacy single-video mode."""
    gui = _conclude_gui(editing_zone=None, edited_points=[])
    gui.pending_single_video_path = "C:/videos/exp_2aq.mp4"
    gui.single_video_workflow = Mock()
    builder = ZoneControlBuilder(gui, event_bus_v2=Mock())

    builder._on_conclude_video()

    gui.single_video_workflow._on_start_single_video_processing_clicked.assert_not_called()
    assert UIEvents.LIVE_RECORDING_RESUME_REQUESTED not in _published_types(gui)


def test_conclude_video_project_mode_does_not_start_single_analysis():
    """Concluir keeps the project mode free from implicit analysis actions."""
    gui = _conclude_gui(editing_zone=None, edited_points=[])
    gui.pending_single_video_path = None
    gui.single_video_workflow = Mock()
    builder = ZoneControlBuilder(gui, event_bus_v2=Mock())

    builder._on_conclude_video()

    gui.single_video_workflow._on_start_single_video_processing_clicked.assert_not_called()
    assert UIEvents.LIVE_RECORDING_RESUME_REQUESTED not in _published_types(gui)


def _conclude_gui_with_pending(pending: bool):
    """gui stub whose zone_controls reports a pending live session."""
    gui = _conclude_gui(editing_zone=None, edited_points=[])
    gui.zone_controls = SimpleNamespace(has_pending_live_session=lambda: pending)
    return gui


def test_conclude_video_pending_live_keeps_recording_pending():
    """Concluir leaves live recording pending for its explicit banner action."""
    gui = _conclude_gui_with_pending(True)
    builder = ZoneControlBuilder(gui, event_bus_v2=Mock())

    builder._on_conclude_video()

    types = _published_types(gui)
    assert UIEvents.UI_NAVIGATE_TO_ANALYSIS_VIEW not in types
    assert UIEvents.LIVE_RECORDING_RESUME_REQUESTED not in types


def test_send_selected_video_to_analysis_uses_selected_file(tmp_path):
    """The explicit action sends the selected recorded file to the config dialog."""
    video_path = tmp_path / "recorded.mp4"
    video_path.touch()
    tree = Mock()
    tree.selection.return_value = ("video-item",)
    tree.item.return_value = (str(video_path),)
    gui = _conclude_gui(editing_zone=None, edited_points=[])
    gui.video_selector_tree = tree
    gui.zone_controls = SimpleNamespace(has_pending_live_session=lambda: False)
    gui.event_dispatcher = Mock()
    gui.dialog_manager = Mock()
    builder = ZoneControlBuilder(gui, event_bus_v2=Mock())

    builder._on_send_selected_video_to_analysis()

    gui.event_dispatcher.handle_analyze_single_video_clicked.assert_called_once_with(
        video_path=str(video_path)
    )


class TestZoneControlBuilder:
    """Tests for ZoneControlBuilder methods."""

    @pytest.fixture
    def mock_gui(self):
        gui = Mock()
        gui.zone_controls_frame = Mock()
        gui.single_analysis_options_frame = None
        gui.roi_choice_var = None
        gui.analysis_interval_var = Mock()
        gui.display_interval_var = Mock()
        gui.stabilization_frames_var = Mock()
        gui.video_search_var = None
        gui.roi_template_var = Mock()
        gui.roi_inclusion_rule_var = Mock()
        gui.roi_buffer_radius_var = Mock()
        gui.roi_overlap_ratio_var = Mock()
        gui.zone_listbox = None
        gui.video_selector_tree = None
        return gui

    @patch("zebtrack.ui.components.zone_context_panel.ZoneContextPanel")
    @patch("zebtrack.ui.builders.zone_control_builder.create_scrollbar")
    @patch("zebtrack.ui.builders.zone_control_builder.ttk")
    @patch("zebtrack.ui.builders.zone_control_builder.StringVar")
    def test_create_zone_control_widgets(
        self,
        mock_stringvar,
        mock_ttk,
        mock_create_scrollbar,
        mock_zone_context_panel,
        mock_gui,
    ):
        """Test creating all zone control widgets."""
        # Setup mocks
        mock_frame = Mock()
        mock_ttk.LabelFrame.return_value = mock_frame
        mock_ttk.Frame.return_value = mock_frame
        mock_entry = Mock()
        mock_ttk.Entry.return_value = mock_entry
        from unittest.mock import MagicMock

        mock_button = MagicMock()
        mock_button.__getitem__.return_value = "disabled"
        mock_ttk.Button.return_value = mock_button
        mock_label = Mock()
        mock_ttk.Label.return_value = mock_label
        mock_combobox = Mock()
        mock_ttk.Combobox.return_value = mock_combobox
        mock_radio = Mock()
        mock_ttk.Radiobutton.return_value = mock_radio
        mock_tree = Mock()
        mock_ttk.Treeview.return_value = mock_tree
        mock_scrollbar = Mock()
        mock_ttk.Scrollbar.return_value = mock_scrollbar
        mock_create_scrollbar.return_value = mock_scrollbar

        mock_stringvar.return_value = Mock()

        # Panel.build() must return a mock frame supporting .pack(...)
        panel_instance = Mock()
        panel_instance.build.return_value = Mock()
        mock_zone_context_panel.return_value = panel_instance

        builder = ZoneControlBuilder(mock_gui)
        builder.create_zone_control_widgets()

        # Verify calls - redirected from gui shim to widget_factory
        mock_gui.widget_factory.create_zone_summary_cards_section.assert_called_once()

        # Verify major sections created (by checking LabelFrame creation)
        # We expect LabelFrames for: Drawing Actions, Single Analysis, Templates,
        # Video Selector, Zone List, Inclusion Rule
        assert mock_ttk.LabelFrame.call_count >= 6

        # Verify variables initialized
        assert mock_gui.roi_choice_var is not None
        assert mock_gui.video_search_var is not None

        # Verify population calls - redirected to components
        mock_gui.roi_template_manager.refresh_templates.assert_called_once()
        # mock_gui._populate_video_selector_tree.assert_called_once() # Replaced by event
        # _on_roi_rule_change is now a method on ZoneControlBuilder itself
        # (no longer a gui shim), so we can't assert on mock_gui
