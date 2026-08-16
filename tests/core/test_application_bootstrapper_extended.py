"""
Extended unit tests for ApplicationBootstrapper in core/application_bootstrapper.py.
"""

from __future__ import annotations

import queue
import threading
from typing import Any
from unittest.mock import MagicMock

import pytest

from zebtrack.core.application_bootstrapper import (
    ApplicationBootstrapper,
    BootstrapResult,
    HardwareBootstrap,
    RuntimeBootstrap,
)
from zebtrack.core.dependency_container import MainViewModelDependencies
from zebtrack.settings import load_settings


class TestBootstrapDTOsExtended:
    """Test HardwareBootstrap, RuntimeBootstrap, and BootstrapResult dataclasses."""

    def test_hardware_bootstrap_fields(self):
        hw = HardwareBootstrap(
            active_weight_name="yolov8n.pt",
            use_openvino=False,
            hardware_summary={"cpu": "Intel"},
            recommended_backend="cpu",
            recorder=MagicMock(),
            arduino_manager=None,
        )
        assert hw.active_weight_name == "yolov8n.pt"
        assert hw.use_openvino is False
        assert hw.hardware_summary == {"cpu": "Intel"}
        assert hw.recommended_backend == "cpu"
        assert hw.arduino_manager is None

    def test_runtime_bootstrap_fields(self):
        fq: queue.Queue[Any] = queue.Queue()
        vq: queue.Queue[Any] = queue.Queue()
        exit_ev = threading.Event()
        cancel_ev = threading.Event()

        rt = RuntimeBootstrap(
            frame_queue=fq,
            video_queue=vq,
            program_exit_event=exit_ev,
            cancel_event=cancel_ev,
        )
        assert rt.frame_queue is fq
        assert rt.video_queue is vq
        assert rt.program_exit_event is exit_ev
        assert rt.cancel_event is cancel_ev

    def test_bootstrap_result_fields(self):
        hw = HardwareBootstrap(
            active_weight_name="model.pt",
            use_openvino=True,
            hardware_summary={},
            recommended_backend="openvino",
            recorder=MagicMock(),
            arduino_manager=None,
        )
        rt = RuntimeBootstrap(
            frame_queue=queue.Queue(),
            video_queue=queue.Queue(),
            program_exit_event=threading.Event(),
            cancel_event=threading.Event(),
        )
        res = BootstrapResult(
            project_service=MagicMock(),
            analysis_service=MagicMock(),
            video_classification_service=MagicMock(),
            video_selection_service=MagicMock(),
            video_validation_service=MagicMock(),
            batch_configuration_service=MagicMock(),
            dialog_coordinator=MagicMock(),
            event_dispatcher=MagicMock(),
            hardware=hw,
            runtime=rt,
            view=MagicMock(),
            ui_state_controller=MagicMock(),
            project_workflow_adapter=MagicMock(),
        )
        assert res.hardware is hw
        assert res.runtime is rt
        assert res.legacy_coordinators == {}


class TestApplicationBootstrapperExtended:
    """Test ApplicationBootstrapper service initialization and weight resolution."""

    @pytest.fixture
    def mock_deps(self) -> MagicMock:
        deps = MagicMock(spec=MainViewModelDependencies)
        deps.settings_obj = load_settings()
        deps.state_manager = MagicMock()
        deps.event_bus = MagicMock()
        deps.ui_coordinator = MagicMock()
        deps.project_manager = MagicMock()
        deps.analysis_service = None
        deps.dialog_coordinator = None
        return deps

    def test_init_services_populates_internal_services(self, mock_deps: MagicMock):
        bootstrapper = ApplicationBootstrapper(dependencies=mock_deps)
        bootstrapper._init_services()

        assert "project_service" in bootstrapper._services
        assert "analysis_service" in bootstrapper._services
        assert "video_classification_service" in bootstrapper._services
        assert "video_selection_service" in bootstrapper._services
        assert "video_validation_service" in bootstrapper._services
        assert "batch_configuration_service" in bootstrapper._services
        assert "dialog_coordinator" in bootstrapper._services
        assert "event_dispatcher" in bootstrapper._services

    def test_init_services_with_injected_services(self, mock_deps: MagicMock):
        custom_analysis = MagicMock()
        custom_dialog = MagicMock()
        mock_deps.analysis_service = custom_analysis
        mock_deps.dialog_coordinator = custom_dialog

        bootstrapper = ApplicationBootstrapper(dependencies=mock_deps)
        bootstrapper._init_services()

        assert bootstrapper._services["analysis_service"] is custom_analysis
        assert bootstrapper._services["dialog_coordinator"] is custom_dialog
