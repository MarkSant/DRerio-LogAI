"""Tests for _SingleVideoMixin helper methods - calibration, metadata, zones."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, Mock

import pytest

from zebtrack.coordinators.video_processing_coordinator import VideoProcessingCoordinator
from zebtrack.core.detection import AquariumData, MultiAquariumZoneData, ZoneData


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
    )
    coord.view = MagicMock()
    coord.root = MagicMock()
    coord.detector = MagicMock()
    return coord


# =====================================================================
# _extract_calibration_from_config
# =====================================================================


class TestExtractCalibration:
    def test_basic_config(self, coordinator):
        config = {
            "num_aquariums": "3",
            "aquarium_width_cm": "15.5",
            "aquarium_height_cm": "10.0",
        }
        result = coordinator._extract_calibration_from_config(config)
        assert result["n"] == 3
        assert result["w"] == 15.5
        assert result["h"] == 10.0

    def test_missing_dimensions(self, coordinator):
        config = {"num_aquariums": "1"}
        result = coordinator._extract_calibration_from_config(config)
        assert result["n"] == 1
        assert result["w"] is None
        assert result["h"] is None

    def test_invalid_num_aquariums(self, coordinator):
        config = {"num_aquariums": "abc"}
        result = coordinator._extract_calibration_from_config(config)
        assert result["n"] == 1  # falls back to default

    def test_empty_dimension_values(self, coordinator):
        config = {"aquarium_width_cm": "", "aquarium_height_cm": "  "}
        result = coordinator._extract_calibration_from_config(config)
        assert result["w"] is None
        assert result["h"] is None

    def test_none_config(self, coordinator):
        result = coordinator._extract_calibration_from_config(None)
        assert result == {"w": None, "h": None, "n": 1}


# =====================================================================
# _extract_metadata_from_config
# =====================================================================


class TestExtractMetadata:
    def test_basic_metadata(self, coordinator):
        config = {"group": "Treatment", "day": "3", "subject": "S1"}
        result = coordinator._extract_metadata_from_config(config)
        assert result["group"] == "Treatment"
        assert result["day"] == "3"
        assert result["subject"] == "S1"

    def test_defaults_applied(self, coordinator):
        result = coordinator._extract_metadata_from_config({})
        assert result["group"] == "single_video"
        assert result["day"] == "1"
        assert result["subject"] == "1"

    def test_dimension_metadata(self, coordinator):
        config = {"aquarium_width_cm": "15.0", "aquarium_height_cm": "10.0"}
        result = coordinator._extract_metadata_from_config(config)
        assert result["aquarium_width_cm"] == 15.0
        assert result["aquarium_height_cm"] == 10.0

    def test_invalid_dimension(self, coordinator):
        config = {"aquarium_width_cm": "abc"}
        result = coordinator._extract_metadata_from_config(config)
        assert "aquarium_width_cm" not in result

    def test_none_config(self, coordinator):
        result = coordinator._extract_metadata_from_config(None)
        assert result["group"] == "single_video"

    def test_group_display_name(self, coordinator):
        config = {"group_display_name": "Control Group"}
        result = coordinator._extract_metadata_from_config(config)
        assert result["group_display_name"] == "Control Group"


# =====================================================================
# _ensure_single_video_zones_saved
# =====================================================================


class TestEnsureSingleVideoZonesSaved:
    def test_zone_data_with_polygon(self, coordinator):
        zd = ZoneData(polygon=[(0, 0), (10, 0), (10, 10)])
        coordinator._ensure_single_video_zones_saved("/path/video.mp4", zd)
        coordinator.project_manager.save_zone_data.assert_called_once()

    def test_zone_data_with_roi_only(self, coordinator):
        zd = ZoneData(polygon=[], roi_polygons=[[(0, 0), (5, 0), (5, 5)]])
        coordinator._ensure_single_video_zones_saved("/path/video.mp4", zd)
        coordinator.project_manager.save_zone_data.assert_called_once()

    def test_multi_aquarium_zone_data(self, coordinator):
        mzd = MultiAquariumZoneData(
            aquariums=[AquariumData(id=0, polygon=[(0, 0), (10, 0), (10, 10)])]
        )
        coordinator._ensure_single_video_zones_saved("/path/video.mp4", mzd)
        coordinator.project_manager.save_zone_data.assert_called_once()

    def test_empty_zone_data(self, coordinator):
        zd = ZoneData(polygon=[], roi_polygons=[])
        coordinator._ensure_single_video_zones_saved("/path/video.mp4", zd)
        coordinator.project_manager.save_zone_data.assert_not_called()

    def test_none_zone_data(self, coordinator):
        coordinator._ensure_single_video_zones_saved("/path/video.mp4", None)
        coordinator.project_manager.save_zone_data.assert_not_called()


# =====================================================================
# _setup_detector_for_single_video
# =====================================================================


class TestSetupDetectorForSingleVideo:
    def test_no_detector(self, coordinator):
        coordinator.detector = None
        result = coordinator._setup_detector_for_single_video("/path/video.mp4", ZoneData())
        assert result is True

    def test_success(self, coordinator):
        coordinator._get_video_dimensions = Mock(return_value=(640, 480))
        zd = ZoneData(polygon=[(0, 0), (10, 0), (10, 10)])
        result = coordinator._setup_detector_for_single_video("/path/video.mp4", zd)
        assert result is True
        coordinator.detector.set_zones.assert_called_once_with(zd, 640, 480)
        coordinator.detector.set_aquarium_region_defined.assert_called_once_with(True)

    def test_cannot_get_dimensions(self, coordinator):
        coordinator._get_video_dimensions = Mock(return_value=None)
        zd = ZoneData()
        result = coordinator._setup_detector_for_single_video("/path/video.mp4", zd)
        assert result is False
        coordinator.event_bus.publish.assert_called_once()


# =====================================================================
# _sync_multi_aquarium_setup
# =====================================================================


class TestSyncMultiAquariumSetup:
    def test_single_aquarium(self, coordinator):
        zd = ZoneData(polygon=[(0, 0), (10, 0), (10, 10)])
        result = coordinator._sync_multi_aquarium_setup("/path/video.mp4", 1, zd)
        assert result is zd

    def test_multi_aquarium_existing_data(self, coordinator):
        existing = MultiAquariumZoneData(aquariums=[AquariumData(id=0), AquariumData(id=1)])
        coordinator.project_manager.get_multi_aquarium_zone_data.return_value = existing
        zd = ZoneData()
        result = coordinator._sync_multi_aquarium_setup("/path/video.mp4", 2, zd)
        assert result is zd  # Not replaced when data already exists

    def test_multi_aquarium_no_existing(self, coordinator):
        coordinator.project_manager.get_multi_aquarium_zone_data.return_value = None
        zd = ZoneData()
        result = coordinator._sync_multi_aquarium_setup("/path/video.mp4", 2, zd)
        coordinator.project_manager.save_multi_aquarium_zone_data.assert_called_once()
        assert hasattr(result, "aquariums")


# =====================================================================
# _persist_single_video_calibration
# =====================================================================


class TestPersistSingleVideoCalibration:
    def test_no_dimensions(self, coordinator):
        coordinator._persist_single_video_calibration({}, {"w": None, "h": None, "n": 1})
        coordinator.project_manager.save_project.assert_not_called()

    def test_with_dimensions(self, coordinator):
        mac = MagicMock()
        mac._determine_processing_intervals.return_value = (5, 5)
        coordinator._multi_aquarium_coordinator = mac
        coordinator._persist_single_video_calibration(
            {"behavioral_analysis": {"threshold": 0.5}},
            {"w": 15.0, "h": 10.0, "n": 1},
        )
        coordinator.project_manager.save_project.assert_called_once()
        assert coordinator.project_manager.project_data["calibration"]["aquarium_width_cm"] == 15.0


# =====================================================================
# _ensure_single_video_registered
# =====================================================================


class TestEnsureSingleVideoRegistered:
    def test_video_already_registered(self, coordinator):
        coordinator.project_manager.find_video_entry.return_value = {"path": "v.mp4"}
        coordinator._ensure_single_video_registered(
            "/path/v.mp4", {}, ZoneData(), {"w": None, "h": None, "n": 1}
        )
        coordinator.project_manager.add_video_batch.assert_not_called()

    def test_new_video_basic(self, coordinator):
        coordinator.project_manager.find_video_entry.return_value = None
        zd = ZoneData(polygon=[(0, 0), (10, 0), (10, 10)])
        coordinator._ensure_single_video_registered(
            "/path/v.mp4", {"group": "A"}, zd, {"w": 15.0, "h": 10.0, "n": 1}
        )
        coordinator.project_manager.add_video_batch.assert_called_once()

    def test_new_video_multi_aq(self, coordinator):
        coordinator.project_manager.find_video_entry.return_value = None
        mzd = MultiAquariumZoneData(
            aquariums=[
                AquariumData(
                    id=0,
                    polygon=[(0, 0), (10, 0), (10, 10)],
                    roi_polygons=[[(1, 1), (2, 2), (3, 3)]],
                )
            ]
        )
        coordinator._ensure_single_video_registered(
            "/path/v.mp4", {}, mzd, {"w": None, "h": None, "n": 2}
        )
        coordinator.project_manager.add_video_batch.assert_called_once()


# =====================================================================
# _execute_single_video_analysis — the task must state its output folder
# =====================================================================


class TestExecuteSingleVideoAnalysis:
    """``scan_input_paths`` returns bare descriptors; the run dir must be added.

    Without it the worker rebuilt the path from scratch as
    ``<video_dir>/<experiment_id>_results`` and only *happened* to land where
    ``resolve_results_directory`` had pointed — a coincidence documented in a
    comment and enforced nowhere. The report step resolves the directory a third
    time; if any of the three ever drifts, the trajectory is written to one
    folder and looked for in another, and the run silently produces no report.
    """

    @staticmethod
    def _prepare(coordinator, out_dir, scanned):
        coordinator.project_manager.resolve_results_directory.return_value = out_dir
        coordinator.process_videos = MagicMock()
        return scanned

    def test_task_carries_the_resolved_results_dir(self, coordinator, monkeypatch, tmp_path):
        from zebtrack.core.project.project_manager import ProjectManager

        out_dir = tmp_path / "exp_results"
        scanned = [{"path": "C:/videos/exp.mp4", "has_arena": True}]
        self._prepare(coordinator, out_dir, scanned)
        monkeypatch.setattr(
            ProjectManager, "scan_input_paths", staticmethod(lambda _paths: scanned)
        )

        coordinator._execute_single_video_analysis("C:/videos/exp.mp4")

        tasks, passed_out_dir = coordinator.process_videos.call_args.args[:2]
        assert tasks[0]["results_dir"] == str(out_dir)
        assert str(passed_out_dir) == str(out_dir), (
            "the task and the context must name the SAME directory"
        )

    def test_the_dialog_config_travels_to_process_videos(self, coordinator, monkeypatch, tmp_path):
        """The user's choices must reach the worker, not stop at the coordinator.

        ``single_video_config`` was never forwarded, so
        ``create_processing_context`` resolved the single-subject preference to
        ``None`` and the WORKER ran in multi-animal mode while the main-process
        detector had been configured for one animal. On a real run (2026-09-05)
        one fish came out as 517 track ids.
        """
        from zebtrack.core.project.project_manager import ProjectManager

        out_dir = tmp_path / "exp_results"
        scanned = [{"path": "C:/videos/exp.mp4", "has_arena": True}]
        self._prepare(coordinator, out_dir, scanned)
        monkeypatch.setattr(
            ProjectManager, "scan_input_paths", staticmethod(lambda _paths: scanned)
        )
        config = {"use_single_subject_tracker": True, "analysis_interval_frames": 3}

        coordinator._execute_single_video_analysis("C:/videos/exp.mp4", config=config)

        assert coordinator.process_videos.call_args.kwargs["single_video_config"] is config

    def test_results_dir_matches_the_worker_fallback_without_a_project(
        self, coordinator, monkeypatch, tmp_path
    ):
        """Explicit value must equal what the worker would have guessed.

        Locks the equivalence that used to be load-bearing but implicit, so a
        change to either side is caught here instead of in a silent no-report run.
        """
        import os

        from zebtrack.core.project.project_manager import ProjectManager

        video = tmp_path / "exp.mp4"
        video.write_bytes(b"")
        worker_fallback = os.path.join(os.path.dirname(str(video)), "exp_results")

        scanned = [{"path": str(video)}]
        self._prepare(coordinator, worker_fallback, scanned)
        monkeypatch.setattr(
            ProjectManager, "scan_input_paths", staticmethod(lambda _paths: scanned)
        )

        coordinator._execute_single_video_analysis(str(video))

        tasks = coordinator.process_videos.call_args.args[0]
        assert tasks[0]["results_dir"] == worker_fallback

    def test_aborts_when_no_video_is_identified(self, coordinator, monkeypatch):
        from zebtrack.core.project.project_manager import ProjectManager

        coordinator.process_videos = MagicMock()
        monkeypatch.setattr(ProjectManager, "scan_input_paths", staticmethod(lambda _paths: []))

        coordinator._execute_single_video_analysis("C:/videos/missing.mp4")

        coordinator.process_videos.assert_not_called()
        coordinator.view.dialog_manager.show_error.assert_called_once()


# =====================================================================
# _ensure_single_video_registered — re-running the same video
# =====================================================================


class TestReRegisterExistingVideo:
    """Re-analysing one video is routine now that "Analyse Another Video" exists.

    The report reads the cm scale from the entry's metadata
    (``ReportGenerationCoordinator._resolve_pixel_cm``), so a stale width or
    height there silently rescales every distance, speed and freezing decision.
    """

    @staticmethod
    def _existing(entry):
        return {"w": 20.0, "h": 12.0, "n": 1}, entry

    def test_corrected_dimensions_overwrite_the_stored_ones(self, coordinator):
        entry: dict[str, Any] = {
            "path": "C:/videos/exp.mp4",
            "metadata": {"aquarium_width_cm": 10.0, "aquarium_height_cm": 8.0},
        }
        coordinator.project_manager.find_video_entry.return_value = entry

        coordinator._ensure_single_video_registered(
            "C:/videos/exp.mp4", {}, None, {"w": 20.0, "h": 12.0, "n": 1}
        )

        assert entry["metadata"]["aquarium_width_cm"] == 20.0
        assert entry["metadata"]["aquarium_height_cm"] == 12.0

    def test_animal_identity_metadata_is_not_touched(self, coordinator):
        """Group/day/subject identify the animal; this dialog does not edit them."""
        entry: dict[str, Any] = {
            "path": "C:/videos/exp.mp4",
            "metadata": {
                "aquarium_width_cm": 10.0,
                "group": "Controle",
                "day": "3",
                "subject": "7",
            },
        }
        coordinator.project_manager.find_video_entry.return_value = entry

        coordinator._ensure_single_video_registered(
            "C:/videos/exp.mp4", {}, None, {"w": 20.0, "h": 12.0, "n": 1}
        )

        assert entry["metadata"]["group"] == "Controle"
        assert entry["metadata"]["day"] == "3"
        assert entry["metadata"]["subject"] == "7"

    def test_a_run_without_dimensions_keeps_the_previous_measurement(self, coordinator):
        """No new numbers must not blank the old ones — stale beats absent."""
        entry: dict[str, Any] = {
            "path": "C:/videos/exp.mp4",
            "metadata": {"aquarium_width_cm": 10.0, "aquarium_height_cm": 8.0},
        }
        coordinator.project_manager.find_video_entry.return_value = entry

        coordinator._ensure_single_video_registered(
            "C:/videos/exp.mp4", {}, None, {"w": None, "h": None, "n": 1}
        )

        assert entry["metadata"]["aquarium_width_cm"] == 10.0
        assert entry["metadata"]["aquarium_height_cm"] == 8.0

    def test_existing_entry_is_never_re_added(self, coordinator):
        entry: dict[str, Any] = {"path": "C:/videos/exp.mp4", "metadata": {}}
        coordinator.project_manager.find_video_entry.return_value = entry

        coordinator._ensure_single_video_registered(
            "C:/videos/exp.mp4", {}, None, {"w": 20.0, "h": 12.0, "n": 1}
        )

        coordinator.project_manager.add_video_batch.assert_not_called()

    def test_entry_without_metadata_dict_gains_one(self, coordinator):
        entry: dict[str, Any] = {"path": "C:/videos/exp.mp4"}
        coordinator.project_manager.find_video_entry.return_value = entry

        coordinator._ensure_single_video_registered(
            "C:/videos/exp.mp4", {}, None, {"w": 20.0, "h": 12.0, "n": 1}
        )

        assert entry["metadata"]["aquarium_width_cm"] == 20.0
