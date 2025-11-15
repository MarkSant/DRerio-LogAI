"""Unit tests for :mod:`zebtrack.orchestrators.model_diagnostics_orchestrator`."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import zebtrack.orchestrators.model_diagnostics_orchestrator as diag_module
from zebtrack.orchestrators.model_diagnostics_orchestrator import (
    DiagnosticAbortError,
    ModelDiagnosticsOrchestrator,
    _is_valid_openvino_directory,
)
from zebtrack.ui.events import Events


class DummyEventBus:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def publish_event(self, event: str, payload: dict):
        self.events.append((event, payload))


class DummyView:
    def __init__(self):
        self.status_updates: list[str] = []

    def set_status(self, message: str):
        self.status_updates.append(message)

    def update_idletasks(self):
        return None

    def ask_ok_cancel(self, title: str, message: str) -> bool:
        return False


class DummyRoot:
    def __init__(self):
        self.after_calls: list[tuple[int, object, tuple, dict]] = []

    def after(self, delay: int, callback, *args, **kwargs):
        self.after_calls.append((delay, callback, args, kwargs))


def make_main_view_model():
    controller = SimpleNamespace(
        _update_diagnostic_progress=MagicMock(),
        _finish_progress_dialog=MagicMock(),
    )
    return SimpleNamespace(
        view=DummyView(),
        root=DummyRoot(),
        settings=SimpleNamespace(),
        weight_manager=MagicMock(),
        model_service=MagicMock(),
        ui_event_bus=DummyEventBus(),
        ui_state_controller=controller,
        cancel_event=MagicMock(),
        active_weight_name="active",
    )


@pytest.fixture()
def diagnostics_orchestrator():
    main_vm = make_main_view_model()
    orchestrator = ModelDiagnosticsOrchestrator(main_vm)
    return orchestrator, main_vm


def test_is_valid_openvino_directory(tmp_path):
    assert _is_valid_openvino_directory(None) is False
    missing = tmp_path / "missing"
    assert _is_valid_openvino_directory(str(missing)) is False
    ov_dir = tmp_path / "ov_model"
    ov_dir.mkdir()
    (ov_dir / "model.xml").write_text("<xml />", encoding="utf-8")
    assert _is_valid_openvino_directory(str(ov_dir)) is True


def test_initialize_openvino_model_invalid_dir_raises(diagnostics_orchestrator, tmp_path):
    orchestrator, main_vm = diagnostics_orchestrator
    weight_details = {"openvino_path": str(tmp_path / "invalid")}
    results: dict[str, list] = {}

    with pytest.raises(DiagnosticAbortError):
        orchestrator._initialize_diagnostic_openvino_model(
            "OpenVINO",
            weight_details,
            results,
            progress_dialog=object(),
        )

    error_events = [evt for evt in main_vm.ui_event_bus.events if evt[0] == Events.UI_SHOW_ERROR]
    assert error_events


def test_initialize_openvino_model_missing_plugin(diagnostics_orchestrator, tmp_path, monkeypatch):
    orchestrator, main_vm = diagnostics_orchestrator
    ov_dir = tmp_path / "ov_model"
    ov_dir.mkdir()
    (ov_dir / "model.xml").write_text("<xml />", encoding="utf-8")
    monkeypatch.setattr(diag_module, "DETECTOR_PLUGINS", {"OpenVINO": None})

    with pytest.raises(DiagnosticAbortError):
        orchestrator._initialize_diagnostic_openvino_model(
            "OpenVINO",
            {"openvino_path": str(ov_dir)},
            {},
            progress_dialog=object(),
        )

    error_events = [evt for evt in main_vm.ui_event_bus.events if evt[0] == Events.UI_SHOW_ERROR]
    assert error_events


def test_initialize_openvino_model_requires_predict_method(diagnostics_orchestrator, tmp_path, monkeypatch):
    orchestrator, main_vm = diagnostics_orchestrator
    ov_dir = tmp_path / "ov_model"
    ov_dir.mkdir()
    (ov_dir / "model.xml").write_text("<xml />", encoding="utf-8")

    class MissingPredict:
        def __init__(self, _path: str):
            self.context = None

    monkeypatch.setattr(diag_module, "DETECTOR_PLUGINS", {"OpenVINO": MissingPredict})

    with pytest.raises(DiagnosticAbortError):
        orchestrator._initialize_diagnostic_openvino_model(
            "OpenVINO",
            {"openvino_path": str(ov_dir)},
            {},
            progress_dialog=object(),
        )

    error_events = [evt for evt in main_vm.ui_event_bus.events if evt[0] == Events.UI_SHOW_ERROR]
    assert error_events


def test_initialize_openvino_model_success_populates_results(
    diagnostics_orchestrator, tmp_path, monkeypatch
):
    orchestrator, _ = diagnostics_orchestrator
    ov_dir = tmp_path / "ov_model"
    ov_dir.mkdir()
    (ov_dir / "model.xml").write_text("<xml />", encoding="utf-8")

    class DummyPlugin:
        def __init__(self, _path: str):
            self.context = None

        def predict(self, frame):
            return []

        def set_context(self, value: str):
            self.context = value

    monkeypatch.setattr(diag_module, "DETECTOR_PLUGINS", {"OpenVINO": DummyPlugin})
    results: dict[str, list] = {}

    instance = orchestrator._initialize_diagnostic_openvino_model(
        "OpenVINO",
        {"openvino_path": str(ov_dir)},
        results,
        progress_dialog=object(),
    )

    assert isinstance(instance, DummyPlugin)
    assert results["OpenVINO"] == []
    assert instance.context == "diagnostic"


def test_initialize_yolo_model_requires_ultralytics(diagnostics_orchestrator, monkeypatch):
    orchestrator, main_vm = diagnostics_orchestrator
    monkeypatch.setattr(diag_module, "ULTRALYTICS_AVAILABLE", False)
    monkeypatch.setattr(diag_module, "YOLO", None)

    with pytest.raises(DiagnosticAbortError):
        orchestrator._initialize_diagnostic_yolo_model(
            "YOLO (PyTorch)",
            {"path": "weights.pt"},
            {},
            progress_dialog=object(),
        )

    error_events = [evt for evt in main_vm.ui_event_bus.events if evt[0] == Events.UI_SHOW_ERROR]
    assert error_events


def test_initialize_yolo_model_success_sets_context(diagnostics_orchestrator, monkeypatch):
    orchestrator, _ = diagnostics_orchestrator

    class DummyYOLO:
        def __init__(self, _path: str):
            self.context = None

        def set_context(self, value: str):
            self.context = value

    monkeypatch.setattr(diag_module, "ULTRALYTICS_AVAILABLE", True)
    monkeypatch.setattr(diag_module, "YOLO", DummyYOLO)
    results: dict[str, list] = {}

    instance = orchestrator._initialize_diagnostic_yolo_model(
        "YOLO (PyTorch)",
        {"path": "weights.pt"},
        results,
        progress_dialog=object(),
    )

    assert isinstance(instance, DummyYOLO)
    assert results["YOLO (PyTorch)"] == []
    assert instance.context == "diagnostic"
