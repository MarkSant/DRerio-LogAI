"""
Tests for ZoneControlBuilder.
"""

from types import SimpleNamespace
from unittest.mock import Mock

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


def test_conclude_video_pending_live_skips_guidance_dialog():
    """When a live session is pending, the banner already covers next steps."""
    gui = _conclude_gui_with_pending(True)
    gui.dialog_manager = Mock()
    builder = ZoneControlBuilder(gui, event_bus_v2=Mock())

    builder._on_conclude_video()

    gui.dialog_manager.show_info.assert_not_called()


def test_conclude_video_live_project_no_pending_shows_guidance_dialog():
    """Live project, no pending session: point the user at Controle Principal."""
    gui = _conclude_gui_with_pending(False)
    gui.controller.project_manager.get_project_type.return_value = "live"
    gui.dialog_manager = Mock()
    builder = ZoneControlBuilder(gui, event_bus_v2=Mock())

    builder._on_conclude_video()

    gui.dialog_manager.show_info.assert_called_once()
    title, message = gui.dialog_manager.show_info.call_args.args
    assert "Completed" in title
    assert "Main Control" in message
    assert "Start Recording" in message


def test_conclude_video_pre_recorded_project_skips_guidance_dialog():
    """Pre-recorded projects have their own explicit analysis buttons."""
    gui = _conclude_gui_with_pending(False)
    gui.controller.project_manager.get_project_type.return_value = "pre-recorded"
    gui.dialog_manager = Mock()
    builder = ZoneControlBuilder(gui, event_bus_v2=Mock())

    builder._on_conclude_video()

    gui.dialog_manager.show_info.assert_not_called()
