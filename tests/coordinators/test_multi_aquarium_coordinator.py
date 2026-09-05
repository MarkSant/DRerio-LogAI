from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.coordinators.multi_aquarium_coordinator import MultiAquariumCoordinator
from zebtrack.core.video.processing_mode import ProcessingMode
from zebtrack.ui.event_bus_v2 import UIEvents


@pytest.fixture
def state_manager():
    return MagicMock()


@pytest.fixture
def project_manager():
    return MagicMock()


@pytest.fixture
def detector_service():
    return MagicMock()


@pytest.fixture
def settings_obj():
    settings = MagicMock()
    settings.video_processing.single_animal_per_aquarium = False
    settings.video_processing.processing_interval = 2
    settings.video_processing.display_interval = 2
    settings.tracking.use_single_subject_tracker = False
    return settings


@pytest.fixture
def ui_coordinator():
    return MagicMock()


@pytest.fixture
def ui_state_controller():
    return MagicMock()


@pytest.fixture
def cancel_event():
    return MagicMock()


@pytest.fixture
def video_classification_service():
    return MagicMock()


@pytest.fixture
def weight_manager():
    return MagicMock()


@pytest.fixture
def event_bus():
    return MagicMock()


@pytest.fixture
def coordinator(
    state_manager,
    project_manager,
    detector_service,
    settings_obj,
    ui_coordinator,
    ui_state_controller,
    cancel_event,
    video_classification_service,
    weight_manager,
    event_bus,
):
    coord = MultiAquariumCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        detector_service=detector_service,
        settings_obj=settings_obj,
        ui_coordinator=ui_coordinator,
        ui_state_controller=ui_state_controller,
        cancel_event=cancel_event,
        video_classification_service=video_classification_service,
        weight_manager=weight_manager,
        event_bus=event_bus,
    )
    # Re-assign mocked event bus if needed or let BaseCoordinator handle it
    coord.event_bus = event_bus
    return coord


def test_reset_multi_aquarium_state(coordinator):
    coordinator._auto_assign_aquariums = True
    coordinator._last_assignment_configs = [{"test": "data"}]
    coordinator._assigned_videos.add("test.mp4")

    coordinator.reset_multi_aquarium_state()

    assert coordinator._auto_assign_aquariums is False
    assert coordinator._last_assignment_configs is None
    assert len(coordinator._assigned_videos) == 0


def test_on_processing_mode_changed_specific_video(coordinator):
    payload = {"sequential": True, "video_path": "test.mp4"}

    mock_zone_data = MagicMock()
    coordinator.project_manager.get_multi_aquarium_zone_data.return_value = mock_zone_data

    with patch(
        "zebtrack.core.project.zone_manager.ZoneManager.multi_aquarium_zone_data_to_dict"
    ) as mock_to_dict:
        mock_to_dict.return_value = {"serialized": True}

        mock_entry = {"id": 1}
        coordinator.project_manager.find_video_entry.return_value = mock_entry
        coordinator.project_manager.project_path = "some_path"

        coordinator._on_processing_mode_changed(payload)

        assert mock_zone_data.sequential_processing is True
        assert mock_entry["multi_aquarium_zone_data"] == {"serialized": True}
        coordinator.project_manager.save_project.assert_called_once()


def test_on_processing_mode_changed_all_videos(coordinator):
    payload = {"sequential": True}

    coordinator.project_manager.get_all_videos.return_value = [
        {"path": "vid1.mp4"},
        {"path": "vid2.mp4"},
    ]

    mock_zone_data = MagicMock()
    coordinator.project_manager.get_multi_aquarium_zone_data.return_value = mock_zone_data

    with patch(
        "zebtrack.core.project.zone_manager.ZoneManager.multi_aquarium_zone_data_to_dict"
    ) as mock_to_dict:
        mock_to_dict.return_value = {"serialized": True}
        mock_entry = {"id": 1}
        coordinator.project_manager.find_video_entry.return_value = mock_entry
        coordinator.project_manager.project_path = "some_path"

        coordinator._on_processing_mode_changed(payload)

        assert coordinator.project_manager.save_project.call_count == 2


@patch("zebtrack.core.detection.aquarium_detector.AquariumDetector")
def test_run_aquarium_detection_single_success(mock_detector_class, coordinator):
    mock_detector_instance = MagicMock()
    mock_detector_class.return_value = mock_detector_instance

    coordinator.weight_manager.get_weight_path_by_method.return_value = "model.pt"

    import numpy as np

    mock_polygon = np.array([[0, 0], [10, 0], [10, 10], [0, 10]])
    mock_detector_instance.detect_aquariums.return_value = [mock_polygon]

    with patch.object(coordinator, "set_main_arena_polygon") as mock_set_arena:
        result = coordinator.run_aquarium_detection("test.mp4", multi_aquarium=False)

        assert result is not None
        assert "polygon" in result
        mock_set_arena.assert_called_once()
        called_types = [call[0][0].type for call in coordinator.event_bus.publish.call_args_list]
        assert UIEvents.UI_REDRAW_ZONES in called_types


@patch("zebtrack.core.detection.aquarium_detector.AquariumDetector")
def test_run_aquarium_detection_multi_success(mock_detector_class, coordinator):
    mock_detector_instance = MagicMock()
    mock_detector_class.return_value = mock_detector_instance

    coordinator.weight_manager.get_weight_path_by_method.return_value = "model.pt"

    import numpy as np

    mock_polygon = np.array([[0, 0], [10, 0], [10, 10], [0, 10]])
    mock_detector_instance.detect_multiple_aquariums.return_value = [mock_polygon, mock_polygon]
    mock_detector_instance.get_last_source_dimensions.return_value = (800, 600)

    result = coordinator.run_aquarium_detection("test.mp4", multi_aquarium=True, count=2)

    assert result is not None
    assert result["count"] == 2
    called_types = [call[0][0].type for call in coordinator.event_bus.publish.call_args_list]
    assert UIEvents.ZONE_MULTI_AUTO_DETECT_SUCCESS in called_types
    assert UIEvents.ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG in called_types


def test_handle_multi_auto_detect(coordinator):
    payload = {"video_path": "test.mp4", "expected_count": 4, "method": "contour"}

    with patch.object(coordinator, "run_aquarium_detection") as mock_run:
        coordinator._handle_multi_auto_detect(payload)

        mock_run.assert_called_once_with("test.mp4", count=4, method="contour", multi_aquarium=True)


def test_on_aquarium_assignment_completed(coordinator):
    payload = {
        "configs": [{"aquarium_id": 0, "group": "A", "subject_id": "S1", "day": "1"}],
        "video_path": "test.mp4",
    }

    mock_multi_data = MagicMock()
    mock_aq = MagicMock()
    mock_aq.id = 0
    mock_multi_data.aquariums = [mock_aq]
    coordinator.project_manager.get_multi_aquarium_zone_data.return_value = mock_multi_data

    mock_entry: dict[str, Any] = {"id": 1}
    coordinator.project_manager.find_video_entry.return_value = mock_entry
    coordinator.project_manager.project_path = "project_path"

    with patch(
        "zebtrack.core.project.zone_manager.ZoneManager.multi_aquarium_zone_data_to_dict"
    ) as mock_to_dict:
        mock_to_dict.return_value = {"serialized": True}

        coordinator._on_aquarium_assignment_completed(payload)

        assert mock_aq.group == "A"
        assert mock_aq.subject_id == "S1"
        assert mock_aq.day == "1"

        assert "metadata" in mock_entry
        assert mock_entry["metadata"]["group"] == "A"

        coordinator.project_manager.save_project.assert_called_once()
        called_types = [call[0][0].type for call in coordinator.event_bus.publish.call_args_list]
        assert UIEvents.UI_REFRESH_PROJECT_VIEWS in called_types


def test_set_main_arena_polygon(coordinator):
    points = [(0, 0), (10, 0), (10, 10)]
    coordinator.project_manager.get_zone_data.return_value = None

    with patch.object(coordinator, "_publish_processing_mode") as mock_publish:
        result = coordinator.set_main_arena_polygon(points)

        assert result is True
        coordinator.project_manager.save_zone_data.assert_called_once()
        mock_publish.assert_called_once()


def test_save_manual_arena(coordinator):
    polygon_list = [(0, 0), (10, 0), (10, 10)]
    coordinator.project_manager.get_project_type.return_value = "live"
    coordinator.project_manager.get_last_zone_video.return_value = "test.mp4"

    mock_zone_data = MagicMock()
    coordinator.project_manager.get_zone_data.return_value = mock_zone_data

    with patch.object(coordinator, "_publish_processing_mode"):
        result = coordinator.save_manual_arena(polygon_list)

        assert result is True
        assert mock_zone_data.polygon == polygon_list
        coordinator.project_manager.save_zone_data.assert_called_once_with(
            mock_zone_data, "test.mp4"
        )


def test_add_roi_polygon(coordinator):
    points = [(0, 0), (5, 0), (5, 5)]
    mock_zone_data = MagicMock()
    mock_zone_data.roi_polygons = []
    mock_zone_data.roi_names = []
    mock_zone_data.roi_colors = []
    coordinator.project_manager.get_zone_data.return_value = mock_zone_data

    result = coordinator.add_roi_polygon(points, "ROI1", (255, 0, 0))

    assert result is True
    assert mock_zone_data.roi_polygons == [points]
    assert mock_zone_data.roi_names == ["ROI1"]
    assert mock_zone_data.roi_colors == [(255, 0, 0)]
    coordinator.project_manager.save_zone_data.assert_called_once()


def test_determine_processing_mode(coordinator):
    coordinator._resolve_single_animal_mode = MagicMock(return_value=True)

    mode = coordinator._determine_processing_mode()

    assert mode == ProcessingMode.SINGLE_SUBJECT
    assert coordinator._active_processing_mode == ProcessingMode.SINGLE_SUBJECT


def test_temporary_single_animal_mode(coordinator):
    coordinator._resolve_single_animal_mode = MagicMock(return_value=True)
    coordinator._resolve_single_subject_tracker_preference = MagicMock(return_value=True)

    with patch.object(coordinator, "_publish_processing_mode") as mock_publish:
        with coordinator._temporary_single_animal_mode():
            assert coordinator.settings.video_processing.single_animal_per_aquarium is True
            assert coordinator.settings.tracking.use_single_subject_tracker is True

        assert coordinator.settings.video_processing.single_animal_per_aquarium is False
        assert coordinator.settings.tracking.use_single_subject_tracker is False
        assert mock_publish.call_count == 2


class TestRelocateResultsFolders:
    def test_relocate_no_outputs(self, coordinator):
        coordinator._relocate_multi_aquarium_folders("v.mp4", {}, [])  # Should not raise

    def test_relocate_with_files(self, coordinator, tmp_path):
        video_path = str(tmp_path / "video.mp4")
        old_dir = tmp_path / "old_results"
        old_dir.mkdir()
        dummy_file = old_dir / "3_CoordMovimento_video_aq1.parquet"
        dummy_file.write_text("data")

        new_dir = tmp_path / "new_results"

        coordinator.project_manager.project_path = str(tmp_path)
        coordinator.project_manager.resolve_results_directory.return_value = new_dir

        entry = {
            "multi_aquarium_outputs": {
                "0": {
                    "results_dir": str(old_dir),
                    "parquet_files": {"trajectory": str(dummy_file)},
                }
            }
        }
        configs = [{"aquarium_id": 0, "group": "G_new", "subject_id": "S_new", "day": "1"}]

        coordinator._relocate_multi_aquarium_folders(video_path, entry, configs)

        assert not old_dir.exists()
        assert new_dir.exists()
        assert (new_dir / "3_CoordMovimento_video_aq1.parquet").exists()
        assert entry["multi_aquarium_outputs"]["0"]["results_dir"] == str(new_dir)


class TestResolveSingleAnimalMode:
    def test_from_top_level_flag(self, coordinator):
        coordinator.project_manager.project_data = {"single_animal_per_aquarium": True}
        assert coordinator._resolve_single_animal_mode() is True

        coordinator.project_manager.project_data = {"single_animal_per_aquarium": False}
        assert coordinator._resolve_single_animal_mode() is False

    def test_from_config(self, coordinator):
        assert coordinator._resolve_single_animal_mode({"single_animal_per_aquarium": True}) is True
        assert coordinator._resolve_single_animal_mode({"animals_per_aquarium": 1}) is True
        assert coordinator._resolve_single_animal_mode({"animals_per_aquarium": 3}) is False

    def test_from_calibration_animals_per_aquarium(self, coordinator):
        coordinator.project_manager.project_data = {"calibration": {"animals_per_aquarium": 1}}
        assert coordinator._resolve_single_animal_mode() is True

        coordinator.project_manager.project_data = {"calibration": {"animals_per_aquarium": 4}}
        assert coordinator._resolve_single_animal_mode() is False


# ---------------------------------------------------------------------------
# Arena detection policy — the pre-recorded flow must honour aquarium_method
# ---------------------------------------------------------------------------


def _arena_detection_case(coordinator, *, project_data, settings_method, settings_preserve=False):
    """Drive ``run_aquarium_detection`` and report how the detector was built."""
    import numpy as np

    coordinator.project_manager.project_data = project_data
    coordinator.settings.model_selection.aquarium_method = settings_method
    coordinator.settings.detection_zones.preserve_real_aquarium_shape = settings_preserve
    coordinator.settings.yolo_model.confidence_threshold = 0.33
    coordinator.settings.yolo_model.aquarium_polygon_epsilon = 0.005
    coordinator.weight_manager.get_weight_path_by_method.return_value = "model.pt"

    with patch("zebtrack.core.detection.aquarium_detector.AquariumDetector") as mock_detector_class:
        instance = MagicMock()
        mock_detector_class.return_value = instance
        instance.detect_aquariums.return_value = [np.array([[0, 0], [9, 0], [9, 9], [0, 9]])]
        with patch.object(coordinator, "set_main_arena_polygon"):
            coordinator.run_aquarium_detection("test.mp4", multi_aquarium=False)

    return mock_detector_class.call_args.kwargs, instance.detect_aquariums.call_args.kwargs


def test_project_aquarium_method_seg_is_honoured(coordinator):
    """A project configured for segmentation must not silently run "det".

    ``run_aquarium_detection`` used to compute ``method if method != "auto"
    else "det"``, and every pre-recorded call site passes the ``"auto"``
    default — so ``model_selection.aquarium_method`` had no reader at all here.
    """
    ctor_kwargs, _detect_kwargs = _arena_detection_case(
        coordinator,
        project_data={"model_selection": {"aquarium_method": "seg"}},
        settings_method="det",
    )
    assert ctor_kwargs["mode"] == "seg"


def test_settings_aquarium_method_used_without_a_project(coordinator):
    """The ad-hoc single-video flow has no project_data — settings must win."""
    ctor_kwargs, _detect_kwargs = _arena_detection_case(
        coordinator, project_data={}, settings_method="seg"
    )
    assert ctor_kwargs["mode"] == "seg"


def test_explicit_method_still_overrides_the_project(coordinator):
    import numpy as np

    coordinator.project_manager.project_data = {"model_selection": {"aquarium_method": "seg"}}
    coordinator.settings.model_selection.aquarium_method = "seg"
    coordinator.weight_manager.get_weight_path_by_method.return_value = "model.pt"

    with patch("zebtrack.core.detection.aquarium_detector.AquariumDetector") as mock_detector_class:
        instance = MagicMock()
        mock_detector_class.return_value = instance
        instance.detect_aquariums.return_value = [np.array([[0, 0], [9, 0], [9, 9], [0, 9]])]
        with patch.object(coordinator, "set_main_arena_polygon"):
            coordinator.run_aquarium_detection("test.mp4", multi_aquarium=False, method="det")

    assert mock_detector_class.call_args.kwargs["mode"] == "det"


def test_preserve_real_shape_and_confidence_reach_the_detector(coordinator):
    """Both used to be dropped: the flag had no reader, the threshold no caller.

    ``detect_aquariums`` fell back to its hardcoded 0.05 and ignored
    ``settings.yolo_model.confidence_threshold``, which the live path honours.
    """
    _ctor_kwargs, detect_kwargs = _arena_detection_case(
        coordinator,
        project_data={
            "model_selection": {"aquarium_method": "seg"},
            "preserve_real_aquarium_shape": True,
        },
        settings_method="det",
    )
    assert detect_kwargs["preserve_real_shape"] is True
    assert detect_kwargs["confidence_threshold"] == 0.33


# ---------------------------------------------------------------------------
# The arena policy must reach the TWO-aquarium branch as well
# ---------------------------------------------------------------------------


def _multi_arena_detection_case(coordinator, *, project_data):
    """Drive the multi-aquarium branch and report the detector call."""
    import numpy as np

    coordinator.project_manager.project_data = project_data
    coordinator.settings.model_selection.aquarium_method = "det"
    coordinator.settings.detection_zones.preserve_real_aquarium_shape = False
    coordinator.settings.yolo_model.confidence_threshold = 0.33
    coordinator.settings.yolo_model.aquarium_polygon_epsilon = 0.005
    coordinator.weight_manager.get_weight_path_by_method.return_value = "model.pt"
    coordinator.project_manager.find_video_entry.return_value = None

    polygon = np.array([[0, 0], [9, 0], [9, 9], [0, 9]])
    with patch("zebtrack.core.detection.aquarium_detector.AquariumDetector") as mock_detector_class:
        instance = MagicMock()
        mock_detector_class.return_value = instance
        instance.detect_multiple_aquariums.return_value = [polygon, polygon]
        instance.get_last_source_dimensions.return_value = (1280, 720)
        coordinator.run_aquarium_detection("test.mp4", multi_aquarium=True, count=2)

    return mock_detector_class.call_args.kwargs, instance.detect_multiple_aquariums.call_args.kwargs


def test_multi_aquarium_branch_honours_the_arena_policy(coordinator):
    """Two aquariums used to ignore seg, the shape flag AND the threshold.

    ``detect_multiple_aquariums`` was called with only the path, the count and
    the frame budget, so a two-aquarium project ran at the detector's hardcoded
    0.05 and could never preserve a real outline.
    """
    ctor_kwargs, detect_kwargs = _multi_arena_detection_case(
        coordinator,
        project_data={
            "model_selection": {"aquarium_method": "seg"},
            "preserve_real_aquarium_shape": True,
        },
    )

    assert ctor_kwargs["mode"] == "seg"
    assert detect_kwargs["preserve_real_shape"] is True
    assert detect_kwargs["confidence_threshold"] == 0.33
    assert detect_kwargs["polygon_epsilon_factor"] == 0.005


# ---------------------------------------------------------------------------
# A degraded or absent detection must reach the USER, not only the log
# ---------------------------------------------------------------------------


def _warning_titles(publish_mock):
    """Titles of every UI_SHOW_WARNING published during the run."""
    return [
        call.args[1].title
        for call in publish_mock.call_args_list
        if call.args[0] == UIEvents.UI_SHOW_WARNING
    ]


def _run_single_detection(coordinator, *, project_data, detect_result, provenance):
    coordinator.project_manager.project_data = project_data
    coordinator.settings.model_selection.aquarium_method = "seg"
    coordinator.settings.detection_zones.preserve_real_aquarium_shape = False
    coordinator.settings.yolo_model.confidence_threshold = 0.33
    coordinator.settings.yolo_model.aquarium_polygon_epsilon = 0.005
    coordinator.weight_manager.get_weight_path_by_method.return_value = "model.pt"

    with patch("zebtrack.core.detection.aquarium_detector.AquariumDetector") as mock_detector_class:
        instance = MagicMock()
        mock_detector_class.return_value = instance
        instance.detect_aquariums.return_value = detect_result
        instance.get_last_detection_provenance.return_value = provenance
        with (
            patch.object(coordinator, "set_main_arena_polygon") as set_arena,
            patch.object(coordinator, "_publish_event") as publish,
        ):
            coordinator.run_aquarium_detection("test.mp4", multi_aquarium=False)
    return set_arena, publish


def test_bbox_result_warns_when_the_project_asked_to_preserve_the_shape(coordinator):
    """The exact 2026-08-31 case: seg requested, rectangle delivered, no word said."""
    import numpy as np

    _set_arena, publish = _run_single_detection(
        coordinator,
        project_data={
            "model_selection": {"aquarium_method": "seg"},
            "preserve_real_aquarium_shape": True,
        },
        detect_result=[np.array([[0, 0], [9, 0], [9, 9], [0, 9]])],
        provenance="bbox",
    )

    assert any("shape" in str(title).lower() for title in _warning_titles(publish))


def test_bbox_result_is_silent_when_no_shape_was_requested(coordinator):
    """Nobody asked for an outline, so a rectangle is the expected answer."""
    import numpy as np

    _set_arena, publish = _run_single_detection(
        coordinator,
        project_data={"model_selection": {"aquarium_method": "det"}},
        detect_result=[np.array([[0, 0], [9, 0], [9, 9], [0, 9]])],
        provenance="bbox",
    )

    assert _warning_titles(publish) == []


def test_synthetic_placeholder_warns_but_still_saves_the_arena(coordinator):
    """Degrade AND tell: losing the polygon would only add a second problem."""
    import numpy as np

    set_arena, publish = _run_single_detection(
        coordinator,
        project_data={"model_selection": {"aquarium_method": "seg"}},
        detect_result=[np.array([[0, 0], [9, 0], [9, 9], [0, 9]])],
        provenance="synthetic_default",
    )

    assert _warning_titles(publish), "a fabricated arena must never pass as a detection"
    set_arena.assert_called_once()


def test_empty_detection_warns_instead_of_failing_in_silence(coordinator):
    """Clicking auto-detect and seeing nothing change was the whole symptom."""
    _set_arena, publish = _run_single_detection(
        coordinator,
        project_data={"model_selection": {"aquarium_method": "seg"}},
        detect_result=[],
        provenance="none",
    )

    assert _warning_titles(publish)
