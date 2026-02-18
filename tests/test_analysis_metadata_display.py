from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

from zebtrack.ui import gui
from zebtrack.ui.components.state_synchronizer import StateSynchronizer


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

    # Mock validation_manager with resolve methods
    inst_any.validation_manager = Mock()
    inst_any.validation_manager.resolve_group_display.side_effect = lambda metadata: metadata.get(
        "group_display_name", "Sem Grupo"
    )
    inst_any.validation_manager.resolve_day_display.side_effect = (
        lambda metadata: f"Dia {metadata['day']:02d}" if "day" in metadata else "Sem Dia"
    )
    inst_any.validation_manager.resolve_subject_display.side_effect = (
        lambda metadata: f"{metadata['subject']:02d}" if "subject" in metadata else "Não informado"
    )

    # Mock state_synchronizer with actual StateSynchronizer implementation
    inst_any.state_synchronizer = Mock()

    # Phase 4.4: analysis_view_controller delegates back to gui methods;
    # wire it so the delegation chain works in unit tests.
    from zebtrack.ui.components.analysis_view_controller import AnalysisViewController

    avc = AnalysisViewController.__new__(AnalysisViewController)
    avc.gui = instance
    inst_any.analysis_view_controller = avc

    def apply_metadata_strings(group: str, day: str, subject: str) -> None:
        combined = f"Grupo: {group} | Dia: {day} | Indivíduo: {subject}"
        inst_any.analysis_metadata_var.set(combined)

    inst_any.state_synchronizer._apply_analysis_metadata_strings.side_effect = (
        apply_metadata_strings
    )

    def update_task_status(
        index: int,
        total: int,
        experiment_id: str | None = None,
        step: str | None = None,
    ) -> None:
        total_videos = max(int(total) if total is not None else 0, 1)
        current_index = max(int(index) if index is not None else 0, 0) + 1

        parts: list[str] = [f"Vídeo {current_index} de {total_videos}"]

        if experiment_id:
            exp_text = str(experiment_id).strip()
            if exp_text:
                parts.append(f"— {exp_text}")

        if step:
            step_text = str(step).strip()
            if step_text:
                if step_text.lower().startswith("etapa:"):
                    step_text = step_text[6:].strip()
                if step_text:
                    parts.append(f"• {step_text}")

        inst_any.analysis_task_var.set(" ".join(parts))

    inst_any.state_synchronizer.update_analysis_task_status.side_effect = update_task_status

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

    assert gui_instance.analysis_metadata_var is not None
    assert (
        gui_instance.analysis_metadata_var.get()
        == "Grupo: Tratamento A | Dia: Dia 03 | Indivíduo: 07"
    )


def test_update_analysis_metadata_handles_missing_values() -> None:
    gui_instance = _make_gui_instance()
    gui_instance.update_analysis_metadata(metadata={})

    assert gui_instance.analysis_metadata_var is not None
    assert (
        gui_instance.analysis_metadata_var.get()
        == StateSynchronizer._default_analysis_metadata_text()
    )


def test_update_analysis_task_status_formats_step() -> None:
    gui_instance = _make_gui_instance()
    gui_instance.update_analysis_task_status(
        index=1,
        total=4,
        experiment_id="EXP123",
        step="Etapa: Rastreamento",
    )

    assert gui_instance.analysis_task_var is not None
    assert gui_instance.analysis_task_var.get() == "Vídeo 2 de 4 — EXP123 • Rastreamento"


def test_update_analysis_task_status_without_step() -> None:
    gui_instance = _make_gui_instance()
    gui_instance.update_analysis_task_status(index=0, total=0, experiment_id="")

    assert gui_instance.analysis_task_var.get() == "Vídeo 1 de 1"
