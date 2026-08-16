"""Tests for report_generation_coordinator.py."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
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


class TestGenerateStandardReport:
    def test_missing_trajectory(self, coordinator, mock_project_manager):
        mock_project_manager.resolve_results_directory.return_value = "nonexistent_dir"
        with patch("os.path.exists", return_value=False):
            coordinator._generate_standard_report("video.mp4", "exp1", {}, {})
            mock_project_manager.register_processing_outputs.assert_not_called()

    @patch("os.path.exists", return_value=True)
    @patch("os.makedirs")
    def test_standard_report_success(
        self, mock_mkdirs, mock_exists, coordinator, mock_project_manager
    ):
        coordinator._read_trajectory = MagicMock(
            return_value=pd.DataFrame({"x": [10.0], "y": [20.0]})
        )
        mock_zone = MagicMock(
            polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            roi_polygons=[],
            roi_names=[],
            roi_colors=[],
        )
        mock_project_manager.get_zone_data.return_value = mock_zone
        mock_project_manager.resolve_results_directory.return_value = "/results"
        coordinator._probe_video_dimensions = MagicMock(return_value=(100, 100))
        coordinator._compute_local_space_geometry = MagicMock(return_value=(0, 0, 100, 100))
        coordinator._collect_rois_for_standard = MagicMock(return_value=({}, {}))
        coordinator._normalize_df_to_local_space = MagicMock(
            return_value=pd.DataFrame({"x": [10.0], "y": [20.0]})
        )
        coordinator._resolve_pixel_cm = MagicMock(return_value=(10.0, 10.0))
        coordinator._prepare_background_image = MagicMock(return_value="bg.png")

        mock_analysis_service = MagicMock()
        mock_analysis_service.run_full_analysis_as_dto.return_value = MagicMock()
        coordinator.analysis_service = mock_analysis_service

        coordinator._export_individual_outputs = MagicMock(
            return_value={"docx": "rep.docx", "xlsx": "rep.xlsx"}
        )

        coordinator._generate_standard_report("video.mp4", "exp1", {}, {"group": "G1"})

        mock_analysis_service.run_full_analysis_as_dto.assert_called_once()
        mock_project_manager.register_processing_outputs.assert_called_once_with(
            video_path="video.mp4",
            report_path="rep.docx",
            summary_excel="rep.xlsx",
        )


class TestGeometryAndMetadataHelpers:
    def test_extract_metadata_from_config(self, coordinator):
        config = {
            "group": "Control",
            "group_display_name": "Control Group",
            "day": "1",
            "subject": "Fish1",
            "aquarium_width_cm": 30.0,
            "aquarium_height_cm": 15.0,
        }
        meta = coordinator._extract_metadata_from_config(config)
        assert meta["group"] == "Control"
        assert meta["group_display_name"] == "Control Group"
        assert meta["day"] == "1"
        assert meta["subject"] == "Fish1"
        assert meta["aquarium_width_cm"] == 30.0
        assert meta["aquarium_height_cm"] == 15.0

    def test_compute_local_space_geometry(self, coordinator):
        poly = [[10, 20], [110, 20], [110, 120], [10, 120]]
        off_x, off_y, loc_w, loc_h = coordinator._compute_local_space_geometry(poly, 200, 200)
        assert off_x == 10
        assert off_y == 20
        assert loc_w == 100
        assert loc_h == 100

    def test_normalize_df_to_local_space(self, coordinator):
        df = pd.DataFrame(
            {
                "x_center_px": [15.0, 5.0, 150.0],
                "y_center_px": [25.0, 5.0, 150.0],
                "x_cm": [1.0, 2.0, 3.0],
            }
        )
        res_df = coordinator._normalize_df_to_local_space(
            df, offset_x=10.0, offset_y=20.0, w=100.0, h=100.0
        )
        # x_cm should be dropped
        assert "x_cm" not in res_df.columns
        # Shifted by (10, 20) and clamped to [0, 100]
        assert res_df["x_center_px"].iloc[0] == 5.0
        assert res_df["x_center_px"].iloc[1] == 0.0
        assert res_df["x_center_px"].iloc[2] == 100.0
        assert res_df["y_center_px"].iloc[0] == 5.0
        assert res_df["y_center_px"].iloc[1] == 0.0
        assert res_df["y_center_px"].iloc[2] == 100.0


class TestMultiSummaryProcessing:
    def test_process_multi_summary_video_no_zone_data(self, coordinator, mock_project_manager):
        mock_project_manager.get_multi_aquarium_zone_data.return_value = None
        status, msg, path, changed = coordinator._process_multi_summary_video(
            {}, "exp1", "video.mp4", {"0": {}}, coordinator.settings, []
        )
        assert status == "skipped"
        assert "multi-aquarium data missing" in msg

    def test_process_multi_summary_video_completed(self, coordinator, mock_project_manager):
        mock_project_manager.get_multi_aquarium_zone_data.return_value = MagicMock()
        coordinator._process_one_aquarium_summary = MagicMock(return_value="/results/sum.parquet")
        video_entry: dict[str, Any] = {}
        status, msg, path, changed = coordinator._process_multi_summary_video(
            video_entry, "exp1", "video.mp4", {"0": {}}, coordinator.settings, []
        )
        assert status == "completed"
        assert path == "/results/sum.parquet"
        assert changed is True
        assert video_entry["has_complete_data"] is True

    def test_process_multi_summary_video_exception(self, coordinator, mock_project_manager):
        mock_project_manager.get_multi_aquarium_zone_data.side_effect = RuntimeError("DB error")
        status, msg, path, changed = coordinator._process_multi_summary_video(
            {}, "exp1", "video.mp4", {"0": {}}, coordinator.settings, []
        )
        assert status == "failed"
        assert "DB error" in msg


class TestProcessOneAquariumSummary:
    def test_trajectory_file_missing_returns_none(self, coordinator):
        res = coordinator._process_one_aquarium_summary(
            {}, "exp1", "v.mp4", 0, {"parquet_files": {}}, MagicMock(), coordinator.settings, []
        )
        assert res is None

    def test_aquarium_not_in_multi_zone(self, coordinator, tmp_path):
        traj_p = tmp_path / "traj.parquet"
        traj_p.write_text("data")
        multi_zone = MagicMock(aquariums=[])

        res = coordinator._process_one_aquarium_summary(
            {},
            "exp1",
            "v.mp4",
            0,
            {"parquet_files": {"trajectory": str(traj_p)}},
            multi_zone,
            coordinator.settings,
            [],
        )
        assert res is None

    def test_empty_dataframe_returns_none(self, coordinator, tmp_path):
        traj_p = tmp_path / "traj.parquet"
        traj_p.write_text("data")
        mock_aq = MagicMock(id=0)
        multi_zone = MagicMock(aquariums=[mock_aq])
        coordinator._read_trajectory = MagicMock(return_value=pd.DataFrame())

        res = coordinator._process_one_aquarium_summary(
            {},
            "exp1",
            "v.mp4",
            0,
            {"parquet_files": {"trajectory": str(traj_p)}},
            multi_zone,
            coordinator.settings,
            [],
        )
        assert res is None

    def test_process_one_aquarium_summary_success(self, coordinator, tmp_path):
        traj_p = tmp_path / "traj.parquet"
        traj_p.write_text("data")
        mock_aq = MagicMock(
            id=0,
            polygon=[[0, 0], [10, 0], [10, 10], [0, 10]],
            roi_polygons=[],
            roi_names=[],
            roi_colors=[],
        )
        multi_zone = MagicMock(aquariums=[mock_aq])
        df = pd.DataFrame({"x": [1, 2], "y": [3, 4], "time": [0.1, 0.2]})
        coordinator.project_manager.project_data = {"calibration": {}}
        coordinator._read_trajectory = MagicMock(return_value=df)
        coordinator._prepare_summary_geometry = MagicMock(
            return_value=(10.0, 10.0, [[0, 0], [10, 10]], 480, [], [], {})
        )

        mock_reporter = MagicMock()
        mock_reporter.generate_reports.return_value = {
            "summary_parquet": str(tmp_path / "sum.parquet")
        }

        with (
            patch("zebtrack.analysis.reporters.ReporterContext", return_value=MagicMock()),
            patch("zebtrack.analysis.reporters.ParquetSummaryReporter", return_value=mock_reporter),
        ):
            out_info = {
                "results_dir": str(tmp_path),
                "parquet_files": {"trajectory": str(traj_p)},
                "group": "G1",
                "subject_id": "S1",
                "day": "1",
            }
            video_entry: dict[str, Any] = {"multi_aquarium_outputs": {"0": {"parquet_files": {}}}}
            res = coordinator._process_one_aquarium_summary(
                video_entry, "exp1", "v.mp4", 0, out_info, multi_zone, coordinator.settings, []
            )
            expected_summary_path = str(tmp_path / "exp1_aq1_summary.parquet")
            assert res == expected_summary_path
            assert (
                video_entry["multi_aquarium_outputs"]["0"]["parquet_files"]["summary"]
                == expected_summary_path
            )


class TestReportHelpersAndOutputs:
    def test_collect_rois_for_aquarium(self, coordinator):
        mock_aq = MagicMock(
            id=0,
            roi_polygons=[[[10, 20], [30, 20], [30, 40], [10, 40]]],
            roi_names=["ZoneA"],
            roi_colors=["#ff0000"],
        )
        mock_zone_data = MagicMock(aquariums=[mock_aq])

        rois, colors = coordinator._collect_rois_for_aquarium(mock_zone_data, 0, 10.0, 20.0)

        assert len(rois) == 1
        assert rois[0].name == "ZoneA"
        assert colors["ZoneA"] == "#ff0000"

    def test_collect_rois_for_standard(self, coordinator):
        mock_zone_data = MagicMock(
            roi_polygons=[[[15, 25], [35, 25], [35, 45], [15, 45]]],
            roi_names=["StandardZone"],
            roi_colors=["#00ff00"],
        )

        rois, colors = coordinator._collect_rois_for_standard(mock_zone_data, 5.0, 5.0)

        assert len(rois) == 1
        assert rois[0].name == "StandardZone"
        assert colors["StandardZone"] == "#00ff00"

    def test_resolve_pixel_cm(self, coordinator):
        meta = {"aquarium_width_cm": 20.0, "aquarium_height_cm": 10.0}
        calib: dict[str, Any] = {}
        px_x, px_y = coordinator._resolve_pixel_cm(meta, calib, loc_w=200.0, loc_h=100.0)

        assert px_x == 10.0
        assert px_y == 10.0

    def test_prepare_background_image_success(self, coordinator, tmp_path):
        dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        coordinator._extract_cropped_background_frame = MagicMock(return_value=dummy_frame)
        coordinator._frame_extractor = MagicMock()

        bg_path = coordinator._prepare_background_image(
            "video.mp4", "exp1", str(tmp_path), crop_box=(0, 0, 100, 100)
        )

        assert bg_path == str(tmp_path / "exp1_bg.png")
        coordinator._frame_extractor.save_frame.assert_called_once()

    def test_prepare_background_image_oserror_fallback(self, coordinator, tmp_path):
        dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        coordinator._extract_cropped_background_frame = MagicMock(return_value=dummy_frame)
        coordinator._frame_extractor = MagicMock()
        coordinator._frame_extractor.save_frame.side_effect = OSError("Disk full")

        bg_path = coordinator._prepare_background_image(
            "video.mp4", "exp1", str(tmp_path), crop_box=(0, 0, 100, 100)
        )

        assert bg_path == "video.mp4"

    def test_export_individual_outputs(self, coordinator, tmp_path):
        mock_analysis = MagicMock()
        mock_word = MagicMock()
        mock_excel = MagicMock()

        with (
            patch(
                "zebtrack.analysis.reporters.ReporterContext.from_analysis",
                return_value=MagicMock(),
            ),
            patch("zebtrack.analysis.reporters.WordReporter", return_value=mock_word),
            patch("zebtrack.analysis.reporters.ExcelReporter", return_value=mock_excel),
        ):
            out = coordinator._export_individual_outputs(mock_analysis, str(tmp_path), "exp1")
            assert "docx" in out
            assert "xlsx" in out
            mock_word.export_individual_report.assert_called_once()
            mock_excel.export_summary.assert_called_once()

    def test_probe_video_dimensions(self, coordinator):
        coordinator._video_metadata_service = MagicMock()
        coordinator._video_metadata_service.get_video_dimensions.return_value = (1920, 1080)

        assert coordinator._probe_video_dimensions("v.mp4") == (1920, 1080)

        coordinator._video_metadata_service.get_video_dimensions.return_value = None
        assert coordinator._probe_video_dimensions("v.mp4") == (0, 0)
