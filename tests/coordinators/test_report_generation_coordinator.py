"""Tests for report_generation_coordinator.py."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator
from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.core.state_manager import StateManager
from zebtrack.settings import Settings
from zebtrack.ui.event_bus_v2 import EventBusV2


@pytest.fixture
def mock_state_manager():
    return MagicMock(spec=StateManager)


@pytest.fixture
def mock_project_manager():
    pm = MagicMock(spec=ProjectManager)
    pm.project_path = "some/path"
    return pm


@pytest.fixture
def mock_settings():
    settings = MagicMock(spec=Settings)
    settings.video_processing = MagicMock()
    settings.video_processing.fps = 30.0
    return settings


@pytest.fixture
def mock_event_bus():
    return MagicMock(spec=EventBusV2)


@pytest.fixture
def coordinator(mock_state_manager, mock_project_manager, mock_settings, mock_event_bus):
    coord = ReportGenerationCoordinator(
        state_manager=mock_state_manager,
        project_manager=mock_project_manager,
        settings_obj=mock_settings,
        event_bus=mock_event_bus,
    )
    return coord


def test_init(coordinator):
    """Test initialization."""
    assert coordinator is not None


def test_read_trajectory_service_injected(
    mock_state_manager, mock_project_manager, mock_settings, mock_event_bus
):
    mock_traj_service = MagicMock()
    mock_traj_service.load_trajectory.return_value = pd.DataFrame({"x": [1, 2]})

    coord = ReportGenerationCoordinator(
        state_manager=mock_state_manager,
        project_manager=mock_project_manager,
        settings_obj=mock_settings,
        event_bus=mock_event_bus,
        trajectory_data_service=mock_traj_service,
    )

    df = coord._read_trajectory(Path("test.parquet"))
    mock_traj_service.load_trajectory.assert_called_once_with("test.parquet")
    assert not df.empty


def test_generate_project_reports_empty(coordinator):
    coordinator.generate_project_reports([])
    coordinator.event_bus.publish.assert_not_called()


@patch(
    "zebtrack.coordinators.report_generation_coordinator.ReportGenerationCoordinator.generate_parquet_summaries"
)
def test_generate_project_reports_success(mock_gen_summaries, coordinator, mock_project_manager):
    mock_project_manager.find_video_entry.return_value = {"path": "test.mp4"}

    with patch.object(coordinator, "_generate_single_video_reports") as mock_gen_single:
        with patch.object(coordinator, "_ensure_analysis_service_ready") as mock_ensure:
            with patch.object(coordinator, "_finalize_report_generation") as mock_finalize:
                coordinator.generate_project_reports(["test.mp4"])

                mock_gen_summaries.assert_called_once()
                mock_ensure.assert_called_once()
                mock_gen_single.assert_called_once_with("test.mp4")
                mock_finalize.assert_called_once_with(1, [])


@patch(
    "zebtrack.coordinators.report_generation_coordinator.ReportGenerationCoordinator.generate_parquet_summaries"
)
def test_generate_project_reports_error(mock_gen_summaries, coordinator, mock_project_manager):
    mock_project_manager.find_video_entry.return_value = {"path": "test.mp4"}

    with patch.object(
        coordinator, "_generate_single_video_reports", side_effect=ValueError("Test error")
    ):
        with patch.object(coordinator, "_ensure_analysis_service_ready"):
            with patch.object(coordinator, "_finalize_report_generation") as mock_finalize:
                coordinator.generate_project_reports(["test.mp4"])
                mock_finalize.assert_called_once()
                assert len(mock_finalize.call_args[0][1]) == 1
                assert "Test error" in mock_finalize.call_args[0][1][0]


def test_generate_single_video_reports_no_entry(coordinator, mock_project_manager):
    mock_project_manager.find_video_entry.return_value = None
    coordinator._generate_single_video_reports("test.mp4")
    # Should just return without doing anything


@patch(
    "zebtrack.coordinators.report_generation_coordinator.ReportGenerationCoordinator._generate_multi_aquarium_reports"
)
def test_generate_single_video_reports_multi(mock_multi, coordinator, mock_project_manager):
    entry: dict[str, Any] = {"metadata": {}, "multi_aquarium_outputs": {"0": {}}}
    mock_project_manager.find_video_entry.return_value = entry

    coordinator._generate_single_video_reports("test.mp4")
    mock_multi.assert_called_once_with("test.mp4", "test", entry, entry["multi_aquarium_outputs"])


@patch(
    "zebtrack.coordinators.report_generation_coordinator.ReportGenerationCoordinator._generate_standard_report"
)
def test_generate_single_video_reports_standard(mock_std, coordinator, mock_project_manager):
    entry: dict[str, Any] = {"metadata": {}}
    mock_project_manager.find_video_entry.return_value = entry

    coordinator._generate_single_video_reports("test.mp4")
    mock_std.assert_called_once_with("test.mp4", "test", entry, entry["metadata"])


def test_finalize_report_generation_success(coordinator):
    coordinator._progress_coordinator = MagicMock()
    coordinator._progress_coordinator._is_batch_processing.return_value = False

    coordinator._finalize_report_generation(1, [])
    # _publish_event calls UI_SHOW_INFO
    assert coordinator.event_bus.publish.call_count == 2


def test_finalize_report_generation_errors(coordinator):
    coordinator._progress_coordinator = MagicMock()
    coordinator._progress_coordinator._is_batch_processing.return_value = False

    coordinator._finalize_report_generation(1, ["Error1"])
    # _publish_event calls UI_SHOW_WARNING
    assert coordinator.event_bus.publish.call_count == 2


@patch(
    "zebtrack.coordinators.report_generation_coordinator.ReportGenerationCoordinator._process_summary_video"
)
def test_generate_parquet_summaries(mock_process, coordinator):
    mock_process.side_effect = [
        ("completed", "msg", "path", True),
        ("failed", "msg", "path", False),
        ("skipped", "msg", "path", False),
    ]
    entries = [{"path": "1.mp4"}, {"path": "2.mp4"}, {"path": "3.mp4"}]
    with patch.object(coordinator, "_find_project_roi_names") as mock_find:
        mock_find.return_value = ["ROI1"]
        coordinator.generate_parquet_summaries(entries, coordinator.settings)
        assert mock_process.call_count == 3
        coordinator.project_manager.save_project.assert_called_once()


def test_process_summary_video_no_path(coordinator):
    with patch.object(coordinator, "_ensure_analysis_service_ready"):
        status, msg, path, changed = coordinator._process_summary_video({}, coordinator.settings)
        assert status == "skipped"
        assert path is None


@patch(
    "zebtrack.coordinators.report_generation_coordinator.ReportGenerationCoordinator._process_multi_summary_video"
)
def test_process_summary_video_multi(mock_multi, coordinator):
    video = {"path": "test.mp4", "multi_aquarium_outputs": {"0": {}}}
    mock_multi.return_value = ("completed", "msg", "path", True)
    with patch.object(coordinator, "_create_project_settings_snapshot"):
        with patch.object(coordinator, "_ensure_analysis_service_ready"):
            status, msg, path, changed = coordinator._process_summary_video(
                video, coordinator.settings
            )
            assert status == "completed"
            mock_multi.assert_called_once()


@patch(
    "zebtrack.coordinators.report_generation_coordinator.ReportGenerationCoordinator._process_standard_summary_video"
)
def test_process_summary_video_standard(mock_std, coordinator):
    video = {"path": "test.mp4"}
    mock_std.return_value = ("completed", "msg", "path", True)
    with patch.object(coordinator, "_create_project_settings_snapshot"):
        with patch.object(coordinator, "_ensure_analysis_service_ready"):
            status, msg, path, changed = coordinator._process_summary_video(
                video, coordinator.settings
            )
            assert status == "completed"
            mock_std.assert_called_once()


@patch(
    "zebtrack.coordinators.report_generation_coordinator.ReportGenerationCoordinator._process_single_aquarium_in_multi"
)
def test_generate_multi_aquarium_reports(mock_single, coordinator, mock_project_manager):
    coordinator._ensure_analysis_service_ready = MagicMock()
    coordinator.analysis_service = MagicMock()
    mock_project_manager.get_multi_aquarium_zone_data.return_value = MagicMock()
    coordinator._generate_multi_aquarium_reports("path", "exp_id", {}, {"0": {}, "1": {}})
    assert mock_single.call_count == 2


def test_process_single_aquarium_in_multi_no_traj(coordinator):
    coordinator._process_single_aquarium_in_multi(
        "path", "exp_id", {}, 0, {}, None, {}, 30.0, 100, 100, {}
    )


@patch("os.path.exists", return_value=True)
@patch(
    "zebtrack.coordinators.report_generation_coordinator.ReportGenerationCoordinator._read_trajectory"
)
@patch(
    "zebtrack.coordinators.report_generation_coordinator.ReportGenerationCoordinator._build_aquarium_report_base"
)
@patch(
    "zebtrack.coordinators.report_generation_coordinator.ReportGenerationCoordinator._export_individual_outputs"
)
def test_process_single_aquarium_in_multi_success(
    mock_export, mock_build, mock_read, mock_exists, coordinator
):
    import pandas as pd

    out_info = {"results_dir": "dir", "parquet_files": {"trajectory": "traj.parquet"}}
    mock_read.return_value = pd.DataFrame(
        {"x": [1, 2], "y": [3, 4], "width": [100, 100], "height": [100, 100]}
    )
    coordinator.analysis_service = MagicMock()
    coordinator._process_single_aquarium_in_multi(
        "path", "exp_id", {}, 0, out_info, None, {}, 30.0, 100, 100, {}
    )
    mock_read.assert_called_once()
    mock_build.assert_called_once()
    coordinator.analysis_service.run_full_analysis_as_dto.assert_called_once()
    mock_export.assert_called_once()
