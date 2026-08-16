"""Unit tests for _VideoSelectionMixin and _VideoCompletionMixin in VideoProcessingCoordinator."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.coordinators.video_processing_coordinator import VideoProcessingCoordinator
from zebtrack.core.detection import AquariumData, MultiAquariumZoneData, ZoneData
from zebtrack.ui.event_bus_v2 import UIEvents


@pytest.fixture
def coordinator():
    state_manager = MagicMock()
    event_bus = MagicMock()
    settings = MagicMock()
    settings.analysis_config = MagicMock()
    settings.tracking = MagicMock()
    settings.video_processing = MagicMock()
    ui_coordinator = MagicMock()
    project_manager = MagicMock()
    project_manager.project_path = "/fake/project"
    project_manager.project_data = {"calibration": {}}
    weight_manager = MagicMock()
    detector_service = MagicMock()
    cancel_event = MagicMock()
    ui_state_controller = MagicMock()
    video_selection_service = MagicMock()
    video_validation_service = MagicMock()
    video_classification_service = MagicMock()
    dialog_coordinator = MagicMock()

    coord = VideoProcessingCoordinator(
        state_manager=state_manager,
        settings_obj=settings,
        ui_coordinator=ui_coordinator,
        project_manager=project_manager,
        weight_manager=weight_manager,
        detector_service=detector_service,
        cancel_event=cancel_event,
        event_bus=event_bus,
        ui_state_controller=ui_state_controller,
        video_selection_service=video_selection_service,
        video_validation_service=video_validation_service,
        video_classification_service=video_classification_service,
        dialog_coordinator=dialog_coordinator,
    )
    coord.view = MagicMock()
    coord.root = MagicMock()
    coord.detector = MagicMock()
    return coord


class TestLiveCameraSessionActiveCheck:
    def test_live_session_active_true(self, coordinator):
        mock_live = MagicMock()
        mock_live.is_live_session_active.return_value = True
        coordinator.view.controller.live_camera_session_coordinator = mock_live
        processing_state = SimpleNamespace(is_live_session_active=True)
        assert coordinator._is_live_session_currently_active(processing_state) is True

    def test_live_session_active_false_fallback_camera(self, coordinator):
        mock_live = MagicMock()
        mock_live.is_live_session_active.return_value = False
        mock_live.live_camera_service.camera = MagicMock()
        coordinator.view.controller.live_camera_session_coordinator = mock_live
        processing_state = SimpleNamespace(is_live_session_active=True)
        assert coordinator._is_live_session_currently_active(processing_state) is False

    def test_live_session_exception_fallback(self, coordinator):
        mock_live = MagicMock()
        mock_live.is_live_session_active.side_effect = RuntimeError("Disconnected")
        mock_live.live_camera_service.camera = MagicMock()
        coordinator.view.controller.live_camera_session_coordinator = mock_live
        processing_state = SimpleNamespace(is_live_session_active=True)
        assert coordinator._is_live_session_currently_active(processing_state) is True


class TestSelectionErrorHandlers:
    def test_show_validation_error(self, coordinator):
        val = SimpleNamespace(error_message="Zone missing")
        coordinator._show_validation_error(val)
        coordinator.event_bus.publish.assert_called_once()
        assert coordinator.event_bus.publish.call_args[0][0].type == UIEvents.UI_SHOW_WARNING

    def test_handle_targeted_selection_no_paths(self, coordinator):
        res = coordinator._handle_targeted_selection_errors(MagicMock(), [])
        assert res is False
        assert coordinator.event_bus.publish.call_args[0][0].type == UIEvents.UI_SHOW_INFO

    def test_handle_targeted_selection_has_missing_and_zero_candidates(self, coordinator):
        selection_result = SimpleNamespace(
            has_missing=True,
            missing_targets=["v1.mp4", "v2.mp4", "v3.mp4", "v4.mp4", "v5.mp4", "v6.mp4"],
            candidate_count=0,
        )
        res = coordinator._handle_targeted_selection_errors(selection_result, ["v1.mp4"])
        assert res is False
        assert coordinator.event_bus.publish.call_count == 2

    def test_handle_targeted_selection_success(self, coordinator):
        selection_result = SimpleNamespace(
            has_missing=False,
            missing_targets=[],
            candidate_count=2,
        )
        res = coordinator._handle_targeted_selection_errors(selection_result, ["v1.mp4", "v2.mp4"])
        assert res is True

    def test_handle_pending_selection_errors_zero_count(self, coordinator):
        selection_result = SimpleNamespace(candidate_count=0)
        res = coordinator._handle_pending_selection_errors(selection_result)
        assert res is False
        assert coordinator.event_bus.publish.call_args[0][0].type == UIEvents.UI_SHOW_INFO

    def test_handle_pending_selection_errors_success(self, coordinator):
        selection_result = SimpleNamespace(candidate_count=3)
        res = coordinator._handle_pending_selection_errors(selection_result)
        assert res is True

    def test_extract_and_validate_candidate_paths_empty(self, coordinator):
        paths = coordinator._extract_and_validate_candidate_paths([{"path": ""}, {"no_path": 1}])
        assert paths is None
        assert coordinator.event_bus.publish.call_args[0][0].type == UIEvents.UI_SHOW_ERROR

    def test_extract_and_validate_candidate_paths_valid(self, coordinator):
        paths = coordinator._extract_and_validate_candidate_paths(
            [{"path": "1.mp4"}, {"path": "2.mp4"}]
        )
        assert paths == ["1.mp4", "2.mp4"]

    def test_handle_missing_files_warning(self, coordinator):
        scan_result = SimpleNamespace(
            has_missing=True,
            missing_files=["m1.mp4", "m2.mp4", "m3.mp4", "m4.mp4", "m5.mp4", "m6.mp4"],
        )
        coordinator._handle_missing_files_warning(scan_result)
        assert coordinator.event_bus.publish.call_args[0][0].type == UIEvents.UI_SHOW_WARNING


class TestLoadZonesForEligibleVideos:
    def test_load_zones_multi_aquarium_filtered(self, coordinator):
        aq1 = AquariumData(id=0, polygon=[[0, 0], [10, 0], [10, 10], [0, 10]])
        aq2 = AquariumData(id=1, polygon=[[20, 0], [30, 0], [30, 10], [20, 10]])
        multi_data = MultiAquariumZoneData(
            aquariums=[aq1, aq2],
            video_width=640,
            video_height=480,
            sequential_processing=True,
        )
        coordinator.project_manager.get_multi_aquarium_zone_data.return_value = multi_data
        coordinator.project_manager.resolve_results_directory.return_value = Path("/results")

        eligible: list[dict[str, Any]] = [{"path": "video1.mp4", "metadata": {}}]
        coordinator._load_zones_for_eligible_videos(eligible, aquarium_filter={"video1.mp4": [0]})

        assert "zone_data" in eligible[0]
        zd = cast(dict[str, Any], eligible[0]["zone_data"])
        assert len(zd["aquariums"]) == 1
        assert zd["aquariums"][0]["id"] == 0

    def test_load_zones_standard_video_from_parquet(self, coordinator):
        coordinator.project_manager.get_multi_aquarium_zone_data.return_value = None
        coordinator.project_manager.resolve_results_directory.return_value = Path("/results")
        mock_zone = ZoneData(
            polygon=[[0, 0], [100, 100]], roi_polygons=[], roi_names=[], roi_colors=[]
        )

        with patch(
            "zebtrack.core.project.project_manager.ProjectManager.load_zones_from_parquet",
            return_value=mock_zone,
        ):
            eligible: list[dict[str, Any]] = [{"path": "video1.mp4", "has_arena": True}]
            coordinator._load_zones_for_eligible_videos(eligible)

            zd = cast(dict[str, Any], eligible[0]["zone_data"])
            assert zd["polygon"] == [[0, 0], [100, 100]]
            coordinator.project_manager.save_zone_data.assert_called_once()


class TestExplodeSequentialTasks:
    def test_explode_single_aquarium(self, coordinator):
        videos = [{"path": "v1.mp4", "zone_data": {"polygon": [[0, 0]]}}]
        tasks = coordinator._explode_sequential_tasks(videos)
        assert len(tasks) == 1
        assert tasks[0]["path"] == "v1.mp4"

    def test_explode_sequential_multi_aquarium(self, coordinator):
        aq1 = AquariumData(
            id=0, polygon=[[0, 0], [10, 0], [10, 10], [0, 10]], group="G1", subject_id="S1"
        )
        aq2 = AquariumData(
            id=1, polygon=[[20, 0], [30, 0], [30, 10], [20, 10]], group="G2", subject_id="S2"
        )
        multi_data = MultiAquariumZoneData(
            aquariums=[aq1, aq2],
            video_width=640,
            video_height=480,
            sequential_processing=True,
        )
        from zebtrack.core.project.zone_manager import ZoneManager

        zone_dict = ZoneManager.multi_aquarium_zone_data_to_dict(multi_data)

        coordinator.project_manager.resolve_multi_aquarium_results_directories.return_value = {
            0: Path("/results/aq1"),
            1: Path("/results/aq2"),
        }

        videos = [
            {
                "path": "v_multi.mp4",
                "zone_data": zone_dict,
            }
        ]
        tasks = coordinator._explode_sequential_tasks(videos)
        assert len(tasks) == 2
        assert tasks[0]["aquarium_id"] == 0
        assert tasks[1]["aquarium_id"] == 1


class TestSelectEligibleVideos:
    def test_skip_dialog_returns_combined_ready_and_arena(self, coordinator):
        ready_traj = [{"path": "t1.mp4"}]
        ready_zones = [{"path": "z1.mp4"}]
        arena_only = [{"path": "a1.mp4"}]
        without_arena = [{"path": "w1.mp4"}]
        coordinator.view.dialog_manager.ask_ok_cancel.return_value = True

        res = coordinator.select_eligible_videos(
            True,
            ready_traj,
            ready_zones,
            arena_only,
            without_arena,
        )
        assert res == [{"path": "t1.mp4"}, {"path": "z1.mp4"}, {"path": "a1.mp4"}]

    def test_with_dialog_user_cancelled(self, coordinator):
        coordinator.view.dialog_manager.show_pending_videos_dialog.return_value = None
        res = coordinator.select_eligible_videos(
            False,
            [],
            [{"path": "z1.mp4"}],
            [],
            [],
        )
        assert res is None


class TestOnVideoCompleted:
    def test_on_video_completed_unsuccessful(self, coordinator):
        coordinator._on_video_completed([], 0, 1, "exp1", False)  # Should return early

    def test_on_video_completed_index_out_of_bounds(self, coordinator):
        coordinator._on_video_completed([], 5, 1, "exp1", True)  # Should log warning and return

    def test_on_video_completed_single_video(self, coordinator, tmp_path):
        video_file = tmp_path / "vid.mp4"
        video_file.write_text("dummy")
        results_dir = tmp_path / "vid_results"
        results_dir.mkdir()
        traj_file = results_dir / "3_CoordMovimento_vid.parquet"
        traj_file.write_text("data")

        videos = [
            {"path": str(video_file), "results_dir": str(results_dir), "experiment_id": "vid"}
        ]

        coordinator._on_video_completed(videos, 0, 1, "vid", True)

        coordinator.project_manager.update_video_status.assert_called_once_with(
            str(video_file), "complete"
        )
        coordinator.project_manager.register_processing_outputs.assert_called_once_with(
            video_path=str(video_file),
            results_dir=str(results_dir),
            trajectory_path=str(traj_file),
        )

    def test_on_video_completed_exploded_task(self, coordinator, tmp_path):
        video_file = tmp_path / "vid_multi.mp4"
        video_file.write_text("dummy")
        results_dir = tmp_path / "vid_multi_aq1_results"
        results_dir.mkdir()
        traj_file = results_dir / "3_CoordMovimento_vid_multi.parquet"
        traj_file.write_text("data")

        videos = [
            {
                "path": str(video_file),
                "results_dir": str(results_dir),
                "experiment_id": "vid_multi",
                "aquarium_id": 0,
                "group": "G1",
                "subject": "S1",
            }
        ]

        coordinator._on_video_completed(videos, 0, 1, "vid_multi", True)

        coordinator.project_manager.register_multi_aquarium_outputs.assert_called_once()
