"""Metadata/task strings shown on the analysis panel.

These assertions cover the REAL ``StateSynchronizer`` formatters. ``state_synchronizer``
used to be a ``Mock`` whose ``side_effect`` re-implemented both format strings, so the
tests asserted that the stub matched the expectation the same stub was written from —
they would have passed with the production methods deleted.
"""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

from zebtrack.ui import gui
from zebtrack.ui.components.state_synchronizer import StateSynchronizer
from zebtrack.ui.sentinels import no_day_label, no_group_label, not_reported_label


class DummyVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def set(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


def _make_gui_instance() -> gui.ApplicationGUI:
    instance = gui.ApplicationGUI.__new__(gui.ApplicationGUI)
    inst_any = cast(Any, instance)
    inst_any.analysis_metadata_var = DummyVar(StateSynchronizer._default_analysis_metadata_text())
    inst_any.analysis_task_var = DummyVar(StateSynchronizer._default_analysis_task_text())
    inst_any.analysis_status_var = DummyVar()
    inst_any.progress_labels = {}
    inst_any.root = SimpleNamespace(after=lambda *args, **kwargs: None)
    inst_any.controller = SimpleNamespace()

    # validation_manager stays a stub: resolving raw metadata into display strings
    # is its own unit's job, tested in tests/ui/components/test_validation_manager.py.
    # Its fallbacks come from the real sentinel helpers so this file holds no second
    # copy of them.
    inst_any.validation_manager = Mock()
    inst_any.validation_manager.resolve_group_display.side_effect = lambda metadata: metadata.get(
        "group_display_name", no_group_label()
    )
    inst_any.validation_manager.resolve_day_display.side_effect = (
        lambda metadata: f"Day {metadata['day']:02d}" if "day" in metadata else no_day_label()
    )
    inst_any.validation_manager.resolve_subject_display.side_effect = (
        lambda metadata: f"{metadata['subject']:02d}"
        if "subject" in metadata
        else not_reported_label()
    )

    # The real formatter under test -- not a stand-in for it.
    inst_any.state_synchronizer = StateSynchronizer(instance)

    # Phase 4.4: analysis_view_controller delegates back to gui methods;
    # wire it so the delegation chain works in unit tests.
    from zebtrack.ui.components.analysis_view_controller import AnalysisViewController

    avc = AnalysisViewController.__new__(AnalysisViewController)
    avc.gui = instance
    inst_any.analysis_view_controller = avc

    return instance


def test_update_analysis_metadata_formats_values() -> None:
    gui_instance = _make_gui_instance()
    gui_instance.analysis_view_controller.update_analysis_metadata(
        metadata={
            "group_display_name": "Tratamento A",
            "day": 3,
            "subject": 7,
        }
    )

    assert gui_instance.analysis_metadata_var is not None
    assert (
        gui_instance.analysis_metadata_var.get()
        == "Group: Tratamento A | Day: Day 03 | Individual: 07"
    )


def test_update_analysis_metadata_handles_missing_values() -> None:
    gui_instance = _make_gui_instance()
    gui_instance.analysis_view_controller.update_analysis_metadata(metadata={})

    assert gui_instance.analysis_metadata_var is not None
    assert (
        gui_instance.analysis_metadata_var.get()
        == StateSynchronizer._default_analysis_metadata_text()
    )


def test_update_analysis_task_status_formats_step() -> None:
    gui_instance = _make_gui_instance()
    gui_instance.analysis_view_controller.update_analysis_task_status(
        index=1,
        total=4,
        experiment_id="EXP123",
        step="Etapa: Rastreamento",
    )

    assert gui_instance.analysis_task_var is not None
    assert gui_instance.analysis_task_var.get() == "Video 2 of 4 — EXP123 • Rastreamento"


def test_update_analysis_task_status_without_step() -> None:
    gui_instance = _make_gui_instance()
    gui_instance.analysis_view_controller.update_analysis_task_status(
        index=0, total=0, experiment_id=""
    )

    assert gui_instance.analysis_task_var.get() == "Video 1 of 1"
