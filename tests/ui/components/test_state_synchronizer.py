"""Tests for StateSynchronizer helpers."""

from types import SimpleNamespace
from unittest.mock import Mock

from zebtrack.core.processing_mode import ProcessingMode
from zebtrack.ui.components.state_synchronizer import StateSynchronizer


def _make_gui():
    analysis_display_widget = Mock()
    analysis_display_widget.track_selector_var = Mock()
    analysis_display_widget.track_selector_widget = Mock()
    analysis_display_widget.update_track_options = Mock()
    analysis_display_widget.set_social_summary = Mock()
    analysis_display_widget.update_progress_stats = Mock()

    gui = SimpleNamespace(
        analysis_display_widget=analysis_display_widget,
        _available_track_options=(),
        _active_processing_mode=ProcessingMode.MULTI_TRACK,
        _current_detections=[],
        _last_analysis_frame=None,
        _analysis_overlay_image=None,
    )
    return gui


def test_format_time():
    assert StateSynchronizer._format_time(-1) == "-"
    assert StateSynchronizer._format_time(0) == "0s"
    assert StateSynchronizer._format_time(59) == "59s"
    assert StateSynchronizer._format_time(61) == "1m 01s"
    assert StateSynchronizer._format_time(3661) == "1h 01m 01s"


def test_update_track_options_deduplicates():
    gui = _make_gui()
    synchronizer = StateSynchronizer(gui)

    synchronizer._update_track_options(["Todos", "1", "", "1", "2"])

    assert gui._available_track_options == ("Todos", "1", "2")
    gui.analysis_display_widget.update_track_options.assert_called_once_with(["Todos", "1", "2"])


def test_update_processing_stats_updates_percent():
    gui = _make_gui()
    synchronizer = StateSynchronizer(gui)

    synchronizer.update_processing_stats(total_frames=100, current_frame=50)

    gui.analysis_display_widget.update_progress_stats.assert_called_once()
    _, kwargs = gui.analysis_display_widget.update_progress_stats.call_args
    assert kwargs["percent"] == "50.0%"
    assert kwargs["total_frames"] == 100


def test_update_social_summary_formats_and_updates_tracks():
    gui = _make_gui()
    synchronizer = StateSynchronizer(gui)

    stats = {"social_time_percentage": {2: 12.34, 1: 50}}
    synchronizer.update_social_summary(profile="default", stats=stats, tracks=["1", "2"])

    gui.analysis_display_widget.set_social_summary.assert_called_once_with(
        "Interações sociais: ID 1: 50.0%, ID 2: 12.3%"
    )
    gui.analysis_display_widget.update_track_options.assert_called_once_with(["Todos", "1", "2"])


def test_update_social_summary_no_stats():
    gui = _make_gui()
    synchronizer = StateSynchronizer(gui)

    synchronizer.update_social_summary(profile="default", stats=None, tracks=None)

    gui.analysis_display_widget.set_social_summary.assert_called_once_with(
        "Interações sociais: perfil atual não gera métricas sociais."
    )


def test_update_social_summary_no_stats_social_profile_waiting_data():
    gui = _make_gui()
    synchronizer = StateSynchronizer(gui)

    synchronizer.update_social_summary(profile="social_interaction", stats=None, tracks=None)

    gui.analysis_display_widget.set_social_summary.assert_called_once_with(
        "Interações sociais: aguardando dados."
    )


def test_update_processing_mode_single_sets_social_summary_not_applicable():
    gui = _make_gui()
    synchronizer = StateSynchronizer(gui)

    synchronizer.update_processing_mode({"mode": ProcessingMode.SINGLE_SUBJECT})

    gui.analysis_display_widget.set_social_summary.assert_called_once_with(
        "Interações sociais: não aplicável no modo de sujeito único."
    )


def test_update_processing_mode_accepts_string_mode_name():
    gui = _make_gui()
    synchronizer = StateSynchronizer(gui)

    synchronizer.update_processing_mode({"mode": "SINGLE_SUBJECT"})

    gui.analysis_display_widget.set_tracking_mode.assert_called_once_with(
        ProcessingMode.SINGLE_SUBJECT.display_name
    )


def test_analysis_metadata_defaults():
    assert StateSynchronizer._analysis_metadata_defaults() == (
        "Sem Grupo",
        "Sem Dia",
        "Não informado",
    )


def test_default_analysis_metadata_text():
    assert (
        StateSynchronizer._default_analysis_metadata_text()
        == "Grupo: Sem Grupo | Dia: Sem Dia | Indivíduo: Não informado"
    )


def test_apply_analysis_metadata_strings_updates_widget_vars():
    analysis_display_widget = SimpleNamespace(
        group_var=Mock(),
        day_var=Mock(),
        subject_var=Mock(),
    )
    gui = SimpleNamespace(
        analysis_display_widget=analysis_display_widget,
        analysis_metadata_var=Mock(),
    )
    synchronizer = StateSynchronizer(gui)

    synchronizer._apply_analysis_metadata_strings("G1", "D2", "S3")

    gui.analysis_metadata_var.set.assert_called_once_with("Grupo: G1 | Dia: D2 | Indivíduo: S3")
    analysis_display_widget.group_var.set.assert_called_once_with("Grupo: G1")
    analysis_display_widget.day_var.set.assert_called_once_with("Dia: D2")
    analysis_display_widget.subject_var.set.assert_called_once_with("Indivíduo: S3")


def test_apply_analysis_metadata_strings_falls_back_to_gui_vars():
    gui = SimpleNamespace(
        analysis_display_widget=None,
        analysis_metadata_var=None,
        analysis_group_var=Mock(),
        analysis_day_var=Mock(),
        analysis_subject_var=Mock(),
    )
    synchronizer = StateSynchronizer(gui)

    synchronizer._apply_analysis_metadata_strings("G1", "D2", "S3")

    gui.analysis_group_var.set.assert_called_once_with("Grupo: G1")
    gui.analysis_day_var.set.assert_called_once_with("Dia: D2")
    gui.analysis_subject_var.set.assert_called_once_with("Indivíduo: S3")


def test_update_recording_ui_updates_buttons():
    gui = SimpleNamespace(
        start_rec_btn=Mock(),
        stop_rec_btn=Mock(),
    )
    synchronizer = StateSynchronizer(gui)

    synchronizer._update_recording_ui(True)

    gui.start_rec_btn.config.assert_called_with(state="disabled")
    gui.stop_rec_btn.config.assert_called_with(state="normal")

    gui.start_rec_btn.config.reset_mock()
    gui.stop_rec_btn.config.reset_mock()

    synchronizer._update_recording_ui(False)

    gui.start_rec_btn.config.assert_called_with(state="normal")
    gui.stop_rec_btn.config.assert_called_with(state="disabled")


def test_update_processing_ui_toggles_buttons_and_view_mode():
    gui = SimpleNamespace(
        process_video_btn=Mock(),
        start_analysis_view_mode=Mock(),
        stop_analysis_view_mode=Mock(),
    )
    synchronizer = StateSynchronizer(gui)

    synchronizer._update_processing_ui(True)

    gui.process_video_btn.config.assert_called_with(state="disabled")
    gui.start_analysis_view_mode.assert_called_once()

    gui.process_video_btn.config.reset_mock()
    gui.start_analysis_view_mode.reset_mock()

    synchronizer._update_processing_ui(False)

    gui.process_video_btn.config.assert_called_with(state="normal")
    gui.stop_analysis_view_mode.assert_called_once()


def test_update_arduino_ui_delegates_to_dashboard():
    dashboard = Mock()
    gui = SimpleNamespace(arduino_dashboard_widget=dashboard)
    synchronizer = StateSynchronizer(gui)

    synchronizer._update_arduino_ui(True)

    dashboard.update_status.assert_called_once_with(True, None)
