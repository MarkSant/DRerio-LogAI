import os
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from zebtrack.coordinators.processing_coordinator import ProcessingCoordinator


@pytest.fixture
def coordinator_with_view(tmp_path):
    state_manager = MagicMock()
    state_manager.get_state.return_value = {}
    state_manager.update_processing_state = MagicMock()

    project_manager = MagicMock()
    project_manager.project_path = str(tmp_path)
    project_manager.project_data = {"name": "Test"}
    project_manager.register_processing_outputs = MagicMock()

    detector_service = MagicMock()
    weight_manager = MagicMock()
    settings = SimpleNamespace(
        processing=SimpleNamespace(enable_parallel_analysis=False, max_parallel_videos=1),
        video_processing=SimpleNamespace(batch_retry_strategy="retry_all"),
    )
    ui_coordinator = MagicMock()
    ui_state_controller = MagicMock()
    cancel_event = Event()
    video_selection_service = MagicMock()
    video_validation_service = MagicMock()
    video_classification_service = MagicMock()
    analysis_service = MagicMock()
    recorder_factory = MagicMock()
    event_bus = MagicMock()

    view = MagicMock()
    root = MagicMock()

    coordinator = ProcessingCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        detector_service=detector_service,
        weight_manager=weight_manager,
        settings_obj=settings,
        ui_coordinator=ui_coordinator,
        ui_state_controller=ui_state_controller,
        cancel_event=cancel_event,
        video_selection_service=video_selection_service,
        video_validation_service=video_validation_service,
        video_classification_service=video_classification_service,
        analysis_service=analysis_service,
        recorder_factory=recorder_factory,
        event_bus=event_bus,
        view=view,
        root=root,
    )

    return coordinator


def test_callbacks_progress_updates_ui_and_state(coordinator_with_view):
    videos = [{"path": "vid1.mp4", "metadata": {"group": "G", "day": 1, "subject": "S"}}]
    callbacks = coordinator_with_view.create_processing_callbacks(videos)

    callbacks.on_progress(
        index=0,
        total=1,
        experiment_id="exp1",
        fraction=0.5,
        message="tracking",
        stats={"current_frame": 10, "total_frames": 20},
    )

    coordinator_with_view.ui_coordinator.set_status.assert_called()
    coordinator_with_view.ui_coordinator.update_progress.assert_called()
    coordinator_with_view.state_manager.update_processing_state.assert_called_with(
        source="controller.processing_progress", current_frame=10, total_frames=20
    )
    assert coordinator_with_view.event_bus.publish_event.call_count >= 2


def test_on_video_completed_registers_outputs(coordinator_with_view, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"test")
    results_dir = tmp_path / "video_results"
    results_dir.mkdir()
    traj_path = results_dir / "3_CoordMovimento_video.parquet"
    traj_path.write_bytes(b"data")

    coordinator_with_view.generate_project_reports = MagicMock()

    videos = [{"path": str(video_path), "results_dir": str(results_dir)}]
    callbacks = coordinator_with_view.create_processing_callbacks(videos)

    callbacks.on_video_completed(0, 1, "video", True)

    coordinator_with_view.project_manager.register_processing_outputs.assert_called_once()
    coordinator_with_view.generate_project_reports.assert_called_once_with([str(video_path)])
