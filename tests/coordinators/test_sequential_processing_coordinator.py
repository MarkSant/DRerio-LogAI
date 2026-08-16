from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.coordinators.sequential_processing_coordinator import SequentialProcessingCoordinator


@pytest.fixture
def mock_state_manager():
    return MagicMock()


@pytest.fixture
def mock_project_manager():
    return MagicMock()


@pytest.fixture
def mock_detector_service():
    return MagicMock()


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.video_processing.processing_interval = 1
    s.video_processing.display_interval = 1
    return s


@pytest.fixture
def mock_ui_coordinator():
    return MagicMock()


@pytest.fixture
def mock_cancel_event():
    return MagicMock()


@pytest.fixture
def mock_event_bus():
    return MagicMock()


@pytest.fixture
def coordinator(
    mock_state_manager,
    mock_project_manager,
    mock_detector_service,
    mock_settings,
    mock_ui_coordinator,
    mock_cancel_event,
    mock_event_bus,
):
    coord = SequentialProcessingCoordinator(
        state_manager=mock_state_manager,
        project_manager=mock_project_manager,
        detector_service=mock_detector_service,
        settings_obj=mock_settings,
        ui_coordinator=mock_ui_coordinator,
        cancel_event=mock_cancel_event,
        event_bus=mock_event_bus,
    )
    coord._report_coordinator = MagicMock()
    coord._progress_coordinator = MagicMock()
    coord._video_processing_coordinator = MagicMock()
    return coord


def test_sequential_context_property(coordinator):
    assert coordinator.sequential_context is None
    coordinator.sequential_context = {"test": 1}
    assert coordinator.sequential_context == {"test": 1}


@patch(
    "zebtrack.coordinators.sequential_processing_coordinator.SequentialProcessingCoordinator._process_next_aquarium_in_sequence"
)
def test_start_sequential_multi_aquarium_processing(mock_process_next, coordinator):
    mock_zone_data = MagicMock()
    mock_zone_data.aquariums = [MagicMock(), MagicMock()]

    coordinator._start_sequential_multi_aquarium_processing(
        video_path="test.mp4", multi_zone_data=mock_zone_data, single_video_config={"config": 1}
    )

    assert coordinator._sequential_context is not None
    assert coordinator._sequential_context["video_path"] == "test.mp4"
    assert coordinator._sequential_context["total"] == 2
    mock_process_next.assert_called_once()


@patch(
    "zebtrack.coordinators.sequential_processing_coordinator.SequentialProcessingCoordinator._finalize_sequential_processing"
)
def test_process_next_aquarium_in_sequence_end(mock_finalize, coordinator):
    coordinator._sequential_context = {"current_index": 2, "total": 2}

    coordinator._process_next_aquarium_in_sequence()

    mock_finalize.assert_called_once()


@patch(
    "zebtrack.coordinators.sequential_processing_coordinator.SequentialProcessingCoordinator._start_single_aquarium_for_sequential"
)
def test_process_next_aquarium_in_sequence_next(mock_start_single, coordinator):
    mock_aquarium = MagicMock()
    coordinator._sequential_context = {
        "current_index": 0,
        "total": 2,
        "aquariums": [mock_aquarium, MagicMock()],
        "video_path": "test.mp4",
    }

    coordinator._process_next_aquarium_in_sequence()

    mock_start_single.assert_called_once_with(mock_aquarium, coordinator._sequential_context)


def test_process_next_aquarium_in_sequence_no_context(coordinator):
    coordinator._sequential_context = None
    # Should not crash
    coordinator._process_next_aquarium_in_sequence()


@patch("zebtrack.core.video.processing_worker.ProcessingWorker")
def test_start_single_aquarium_for_sequential(mock_worker_class, coordinator):
    mock_worker_instance = MagicMock()
    mock_worker_class.return_value = mock_worker_instance

    mock_aquarium = MagicMock()
    mock_aquarium.id = 0
    mock_aquarium.polygon = []

    mock_zone_data = MagicMock()
    mock_zone_data.video_width = 100
    mock_zone_data.video_height = 100
    mock_zone_data.to_zone_data.return_value = MagicMock(
        polygon=[], roi_polygons=[], roi_names=[], roi_colors=[], metadata={}
    )

    ctx = {
        "video_path": "test.mp4",
        "multi_zone_data": mock_zone_data,
        "single_video_config": {"analysis_interval_frames": 2, "display_interval_frames": 2},
        "current_index": 0,
    }

    coordinator.project_manager.resolve_results_directory.return_value = "res_dir"

    # We must patch cv2.VideoCapture so it doesn't try to open test.mp4
    with patch("cv2.VideoCapture"):
        coordinator._start_single_aquarium_for_sequential(mock_aquarium, ctx)

    mock_worker_class.assert_called_once()
    mock_worker_instance.start_in_thread.assert_called_once()
    coordinator.detector_service.configure_zones.assert_called_once()


def test_register_sequential_aquarium_output_success(coordinator):
    mock_entry: dict[str, Any] = {"existing": "data"}
    coordinator.project_manager.find_video_entry.return_value = mock_entry
    coordinator.project_manager.project_path = "some_path"

    # We need to mock os.listdir to pretend there are parquet files
    with patch("os.listdir", return_value=["3_CoordMovimento.parquet"]):
        coordinator._register_sequential_aquarium_output(0, "test.mp4", "res_dir", {"group": "g1"})

    assert "multi_aquarium_outputs" in mock_entry
    assert "0" in mock_entry["multi_aquarium_outputs"]
    assert mock_entry["multi_aquarium_outputs"]["0"]["group"] == "g1"
    coordinator.project_manager.save_project.assert_called_once()


def test_register_sequential_aquarium_output_no_entry(coordinator):
    coordinator.project_manager.find_video_entry.return_value = None

    coordinator._register_sequential_aquarium_output(0, "test.mp4", "res_dir", {"group": "g1"})

    coordinator.project_manager.save_project.assert_not_called()


def test_handle_sequential_multi_aquarium(coordinator):
    coordinator._sequential_context = {"video_path": "test.mp4"}

    assert coordinator._handle_sequential_multi_aquarium("test.mp4") is True
    assert coordinator._handle_sequential_multi_aquarium("other.mp4") is False


def test_handle_sequential_single_video_start(coordinator):
    mock_zone_data = MagicMock()
    mock_zone_data.sequential_processing = True

    coordinator._start_sequential_multi_aquarium_processing = MagicMock()

    assert coordinator._handle_sequential_single_video_start("test.mp4", mock_zone_data, {}) is True
    coordinator._start_sequential_multi_aquarium_processing.assert_called_once()


def test_handle_sequential_single_video_start_false(coordinator):
    mock_zone_data = MagicMock()
    mock_zone_data.sequential_processing = False

    assert (
        coordinator._handle_sequential_single_video_start("test.mp4", mock_zone_data, {}) is False
    )


def test_finalize_sequential_processing(coordinator):
    coordinator._sequential_context = {"video_path": "test.mp4", "completed": [0], "failed": []}

    coordinator._finalize_sequential_processing()

    assert coordinator._sequential_context is None
    coordinator.state_manager.update_processing_state.assert_called_once()
    coordinator._report_coordinator.generate_project_reports.assert_called_once_with(["test.mp4"])
