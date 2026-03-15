"""Tests for AnalysisControlsWidget."""

from unittest.mock import Mock

import pytest

from zebtrack.ui.components.analysis_controls import AnalysisControlsWidget
from zebtrack.ui.event_bus_v2 import UIEvents


@pytest.fixture
def widget(tkinter_root):
    event_bus = Mock()
    return AnalysisControlsWidget(parent=tkinter_root, event_bus=event_bus)


@pytest.mark.gui
def test_set_status_and_metadata(widget):
    widget.set_status("Running")
    assert widget.analysis_status_var.get() == "Running"

    widget.set_metadata("G1", "D1", "S1", task="Task")
    assert widget.analysis_group_var.get() == "Grupo: G1"
    assert widget.analysis_day_var.get() == "Dia: D1"
    assert widget.analysis_subject_var.get() == "Indivíduo: S1"
    assert widget.analysis_task_var.get() == "Tarefa: Task"


@pytest.mark.gui
def test_set_tracking_profile_social(widget):
    widget.set_tracking_mode("Single")
    widget.set_profile("ProfileA")
    widget.set_social_summary("Summary")

    assert widget.tracking_mode_var.get() == "Modo de rastreamento: Single"
    assert widget.analysis_profile_var.get() == "Perfil de análise: ProfileA"
    assert widget.social_summary_var.get() == "Summary"


@pytest.mark.gui
def test_update_track_options_and_emit(widget):
    widget.update_track_options(["Todos", "1", "2"])
    assert widget.track_selector_widget.cget("values") == ("Todos", "1", "2")

    widget.track_selector_var.set("2")
    widget._on_track_selection_changed(None)

    widget.event_bus.publish.assert_called_once_with(
        UIEvents.ANALYSIS_TRACK_SELECTED,
        {"track_id": "2"},
    )


@pytest.mark.gui
def test_clear_frame(widget):
    widget.clear_frame()
    assert widget.analysis_video_label.image is None
