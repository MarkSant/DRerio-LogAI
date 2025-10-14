from types import SimpleNamespace
from typing import Any, cast

from zebtrack.ui import gui


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
    inst_any.analysis_metadata_var = DummyVar(gui.ApplicationGUI._default_analysis_metadata_text())
    inst_any.analysis_task_var = DummyVar(gui.ApplicationGUI._default_analysis_task_text())
    inst_any.analysis_status_var = DummyVar()
    inst_any.progress_labels = {}
    inst_any.root = SimpleNamespace(after=lambda *args, **kwargs: None)
    inst_any.controller = SimpleNamespace()
    return instance


def test_update_analysis_metadata_formats_values() -> None:
    gui_instance = _make_gui_instance()
    gui_instance.update_analysis_metadata(
        metadata={
            "group_display_name": "Tratamento A",
            "day": 3,
            "subject": 7,
        }
    )

    assert (
        gui_instance.analysis_metadata_var.get()
        == "Grupo: Tratamento A | Dia: Dia 03 | Indivíduo: 07"
    )


def test_update_analysis_metadata_handles_missing_values() -> None:
    gui_instance = _make_gui_instance()
    gui_instance.update_analysis_metadata(metadata={})

    assert (
        gui_instance.analysis_metadata_var.get()
        == gui.ApplicationGUI._default_analysis_metadata_text()
    )


def test_update_analysis_task_status_formats_step() -> None:
    gui_instance = _make_gui_instance()
    gui_instance.update_analysis_task_status(
        index=1,
        total=4,
        experiment_id="EXP123",
        step="Etapa: Rastreamento",
    )

    assert gui_instance.analysis_task_var.get() == "Vídeo 2 de 4 — EXP123 • Rastreamento"


def test_update_analysis_task_status_without_step() -> None:
    gui_instance = _make_gui_instance()
    gui_instance.update_analysis_task_status(index=0, total=0, experiment_id="")

    assert gui_instance.analysis_task_var.get() == "Vídeo 1 de 1"
