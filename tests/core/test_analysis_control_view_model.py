"""Tests for AnalysisControlViewModel."""

from __future__ import annotations

from pathlib import Path
from threading import Event
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock, patch

import pytest

from zebtrack.core.viewmodels.analysis_control_view_model import AnalysisControlViewModel
from zebtrack.ui.events import Events


@pytest.fixture
def view_model():
    """Create a view model with minimal dependencies."""
    settings = SimpleNamespace(
        model_selection=SimpleNamespace(animal_method="seg", use_openvino=False)
    )
    state_manager = Mock()
    state_manager.get_processing_state.return_value = SimpleNamespace(is_processing=False)

    processing_coordinator = Mock()
    processing_coordinator.processing_worker = None
    processing_coordinator.processing_thread = Mock()
    processing_coordinator.processing_thread.is_alive.return_value = False

    # Phase 4.7: Use live_camera_session_coordinator instead of session_coordinator
    live_camera_session_coordinator = Mock()
    live_camera_session_coordinator.live_camera_service = Mock()
    live_camera_session_coordinator.live_camera_service.camera = None

    dependencies = SimpleNamespace(
        video_processing_service=Mock(),
        processing_coordinator=processing_coordinator,
        live_camera_session_coordinator=live_camera_session_coordinator,
        state_manager=state_manager,
        project_manager=Mock(),
        settings_obj=settings,
    )
    bootstrap_result = SimpleNamespace(
        analysis_service=Mock(),
        ui_state_controller=Mock(),
        recorder=Mock(),
        cancel_event=Event(),
    )
    event_bus = Mock()
    return AnalysisControlViewModel(
        cast(Any, dependencies),
        cast(Any, bootstrap_result),
        event_bus,
    )


def test_is_processing_reads_state(view_model):
    """Reads processing state from StateManager."""
    view_model.state_manager.get_processing_state.return_value = SimpleNamespace(is_processing=True)

    assert view_model.is_processing is True


def test_start_single_video_workflow_invalid_det_config(view_model):
    """Publish error when det mode has multiple animals."""
    config = {"animal_method": "det", "animals_per_aquarium": 2}

    view_model.start_single_video_workflow("/video.mp4", config)

    view_model.ui_event_bus.publish_event.assert_called_once()
    event_name, payload = view_model.ui_event_bus.publish_event.call_args[0]
    assert event_name == Events.UI_SHOW_ERROR
    assert payload["title"] == "Configuração Inválida"


def test_start_single_video_workflow_detector_setup_failure(view_model):
    """Early return when detector setup fails."""
    detector_vm = Mock()
    detector_vm.detector = None
    detector_vm.setup_detector.return_value = False

    view_model.start_single_video_workflow("/video.mp4", {"animal_method": "seg"}, detector_vm)

    view_model.ui_event_bus.publish_event.assert_not_called()
    view_model.project_manager.set_active_zone_video.assert_called_once_with(
        str(Path("/video.mp4"))
    )


def test_start_single_video_workflow_detector_setup_success(view_model):
    """Publish setup event when detector is ready."""
    detector_vm = Mock()
    detector_vm.detector = None
    detector_vm.setup_detector.return_value = True

    config = {"animal_method": "seg", "use_openvino": True}
    view_model.start_single_video_workflow("/video.mp4", config, detector_vm)

    assert detector_vm.use_openvino is True
    view_model.project_manager.set_active_zone_video.assert_called_once_with(
        str(Path("/video.mp4"))
    )
    view_model.ui_event_bus.publish_event.assert_called_once_with(
        "ui:setup_zone_definition_for_single_video",
        {"video_path": Path("/video.mp4"), "config": config},
    )


def test_start_single_video_workflow_without_detector_vm(view_model):
    """Publish setup event even without detector VM."""
    config = {"animal_method": "seg"}

    view_model.start_single_video_workflow("/video.mp4", config)

    view_model.ui_event_bus.publish_event.assert_called_once()
    event_name, payload = view_model.ui_event_bus.publish_event.call_args[0]
    assert event_name == "ui:setup_zone_definition_for_single_video"
    assert payload["config"] == config


def test_start_single_video_processing_delegates(view_model):
    """Delegate to ProcessingCoordinator."""
    view_model.start_single_video_processing(
        video_path="/video.mp4", config={"x": 1}, zone_data="zone"
    )

    view_model.processing_coordinator.start_single_video_processing.assert_called_once_with(
        video_path="/video.mp4", config={"x": 1}, zone_data="zone"
    )


def test_auto_detect_zones_publishes_event(view_model):
    """Publish auto detect event payload."""
    view_model.auto_detect_zones(video_path="/video.mp4", stabilization_frames=15)

    view_model.ui_event_bus.publish_event.assert_called_once_with(
        Events.ZONE_AUTO_DETECT,
        {"video_path": "/video.mp4", "stabilization_frames": 15},
    )


def test_cancel_current_analysis_no_active_processing(view_model):
    """No-op when nothing is running."""
    view_model.cancel_current_analysis()

    assert view_model.cancel_event.is_set() is False
    view_model.state_manager.update_processing_state.assert_not_called()
    view_model.ui_event_bus.publish_event.assert_not_called()
    view_model.ui_state_controller._show_cancel_feedback.assert_not_called()


def test_cancel_current_analysis_stops_live_session(view_model):
    """Stops live session and requests cancel."""
    view_model.live_camera_session_coordinator.live_camera_service.camera = object()

    with patch("zebtrack.core.viewmodels.analysis_control_view_model.threading.Thread") as tmock:
        view_model.cancel_current_analysis()

    assert view_model.cancel_event.is_set() is True
    view_model.live_camera_session_coordinator.live_camera_service.stop_session.assert_called_once()
    view_model.processing_coordinator.cancel_processing.assert_called_once()
    view_model.state_manager.update_processing_state.assert_called_once()
    view_model.ui_event_bus.publish_event.assert_called_once_with(
        Events.UI_SET_STATUS, {"message": "Cancelando análise em andamento..."}
    )
    view_model.ui_state_controller._show_cancel_feedback.assert_called_once()
    tmock.assert_called_once()


def test_generate_parquet_summaries_starts_thread(view_model):
    """Starts background thread for summaries."""
    with patch("zebtrack.core.viewmodels.analysis_control_view_model.threading.Thread") as tmock:
        view_model.generate_parquet_summaries(["/v1.mp4", "/v2.mp4"])

    tmock.assert_called_once()
    tmock.return_value.start.assert_called_once()
