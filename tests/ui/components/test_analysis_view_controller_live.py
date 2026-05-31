from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from zebtrack.core.video.processing_mode import ProcessingMode
from zebtrack.ui.components.analysis_view_controller import AnalysisViewController


def _make_gui(*, is_live_session_active: bool):
    analysis_display = Mock()
    analysis_display.track_selector_var = Mock()
    analysis_display.track_selector_widget = Mock()

    state_manager = Mock()
    state_manager.get_processing_state.return_value = SimpleNamespace(
        is_live_session_active=is_live_session_active
    )

    gui = SimpleNamespace(
        notebook=Mock(),
        analysis_tab_frame=object(),
        zone_tab_frame=object(),
        analysis_display_widget=analysis_display,
        canvas_manager=Mock(),
        state_synchronizer=Mock(),
        validation_manager=Mock(),
        widget_factory=Mock(),
        analysis_status_var=Mock(),
        analysis_task_var=Mock(),
        analysis_profile_var=Mock(),
        show_progress_bar=Mock(),
        hide_progress_bar=Mock(),
        project_initializer=Mock(),
        controller=SimpleNamespace(state_manager=state_manager),
        _active_processing_mode=ProcessingMode.MULTI_TRACK,
        _current_detections=[],
        _last_analysis_frame=None,
        _analysis_overlay_image=None,
        analysis_active=False,
        canvas_view_mode="zones",
    )
    return gui


@pytest.mark.gui
def test_start_analysis_view_mode_resets_defaults_for_non_live_processing():
    gui = _make_gui(is_live_session_active=False)
    controller = AnalysisViewController(gui)

    controller.start_analysis_view_mode()

    gui.analysis_status_var.set.assert_called_once_with("Preparando análise...")
    gui.analysis_task_var.set.assert_called_once_with("Preparando fila de análise...")
    gui.state_synchronizer._set_analysis_metadata_defaults.assert_called_once()


@pytest.mark.gui
def test_start_analysis_view_mode_preserves_metadata_for_live_processing():
    gui = _make_gui(is_live_session_active=True)
    controller = AnalysisViewController(gui)

    controller.start_analysis_view_mode()

    gui.analysis_status_var.set.assert_not_called()
    gui.analysis_task_var.set.assert_not_called()
    gui.state_synchronizer._set_analysis_metadata_defaults.assert_not_called()
    gui.show_progress_bar.assert_called_once()
    gui.analysis_display_widget.enable_cancel_button.assert_called_once()
