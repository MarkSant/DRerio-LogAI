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


@patch("zebtrack.core.detection.aquarium_detector.AquariumDetector")
def test_wizard_regex_reaches_the_assignment_dialog(mock_detector_class, coordinator):
    # F2-P-003: the fallback config was built enabled=True with no aquarium configs,
    # failed validation, and the dialog got None (no group/day/subject prefill).
    import numpy as np

    detector = mock_detector_class.return_value
    square = np.array([[0, 0], [10, 0], [10, 10], [0, 10]])
    detector.detect_multiple_aquariums.return_value = [square, square]
    detector.get_last_source_dimensions.return_value = (800, 600)
    coordinator.weight_manager.get_weight_path_by_method.return_value = "model.pt"
    coordinator.project_manager.find_video_entry.return_value = None
    coordinator.project_manager.get_available_groups.return_value = ["Grupo_A", "Grupo_B"]
    coordinator.project_manager.project_data = {
        "_wizard_metadata": {
            "custom_regex_patterns": {
                "group_pattern": r"G(\d+)",
                "day_pattern": r"D(\d+)",
                "subject_pattern": r"S(\d+)",
            }
        }
    }

    coordinator.run_aquarium_detection("G2_D3_S4--G5_D3_S6.mp4", multi_aquarium=True, count=2)

    dialog_payloads = [
        call[0][0].data
        for call in coordinator.event_bus.publish.call_args_list
        if call[0][0].type == UIEvents.ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG
    ]
    assert len(dialog_payloads) == 1
    # The project's groups reach the dialog; without them it offered placeholders.
    assert dialog_payloads[0].available_groups == ("Grupo_A", "Grupo_B")
    config = dialog_payloads[0].multi_aquarium_config
    assert config.extract_metadata("G2_D3_S4--G5_D3_S6.mp4") == [
        {"group": "2", "subject": "4", "day": "3"},
        {"group": "5", "subject": "6", "day": "3"},
    ]


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

    def test_the_animal_count_beats_a_stale_tracking_flag(self, coordinator):
        """#649: a one-rat project whose ``tracking`` flag a migration filled with
        the global default (False) must still track ONE subject."""
        coordinator.project_manager.project_data = {
            "tracking": {"use_single_subject_tracker": False},
            "calibration": {"animals_per_aquarium": 1},
        }
        assert coordinator._resolve_single_animal_mode() is True

        coordinator.project_manager.project_data = {
            "tracking": {"use_single_subject_tracker": True},
            "calibration": {"animals_per_aquarium": 3},
        }
        assert coordinator._resolve_single_animal_mode() is False

    def test_the_flag_decides_only_without_a_count(self, coordinator):
        coordinator.project_manager.project_data = {
            "tracking": {"use_single_subject_tracker": True},
        }
        assert coordinator._resolve_single_animal_mode() is True


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


def test_multi_aquarium_branch_honours_the_area_bounds(coordinator):
    """``detection_zones.{min,max}_aquarium_area_ratio`` reach the detector (#726).

    ``max_aquarium_area_ratio`` had no reader (A7-01) and the detector ignored its
    own ``max_area_ratio``: the setting changed nothing.
    """
    coordinator.settings.detection_zones.min_aquarium_area_ratio = 0.12
    coordinator.settings.detection_zones.max_aquarium_area_ratio = 0.4

    _ctor, detect_kwargs = _multi_arena_detection_case(coordinator, project_data={})

    assert detect_kwargs["min_area_ratio"] == 0.12
    assert detect_kwargs["max_area_ratio"] == 0.4


@pytest.mark.parametrize("value", [None, "0.4", True, MagicMock()])
def test_unusable_area_bounds_fall_back_to_the_defaults(value):
    from types import SimpleNamespace

    from zebtrack.coordinators.multi_aquarium_coordinator import _aquarium_area_bounds

    zones = SimpleNamespace(min_aquarium_area_ratio=value, max_aquarium_area_ratio=value)

    assert _aquarium_area_bounds(SimpleNamespace(detection_zones=zones)) == (0.10, 0.98)
    assert _aquarium_area_bounds(None) == (0.10, 0.98)


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


@pytest.mark.parametrize("outcome", ["nothing_found", "raises"])
@patch("zebtrack.core.detection.aquarium_detector.AquariumDetector")
def test_a_failed_multi_detection_tells_the_user(mock_detector_class, coordinator, outcome):
    # A1-02: only an unsubscribed event went out, so Auto-detect looked dead
    # whenever the two-aquarium detection failed.
    detector = mock_detector_class.return_value
    if outcome == "raises":
        detector.detect_multiple_aquariums.side_effect = RuntimeError("model crashed")
    else:
        detector.detect_multiple_aquariums.return_value = []
    coordinator.weight_manager.get_weight_path_by_method.return_value = "model.pt"

    result = coordinator.run_aquarium_detection("test.mp4", multi_aquarium=True, count=2)

    assert result is None
    warnings = [
        call[0][0].data
        for call in coordinator.event_bus.publish.call_args_list
        if call[0][0].type == UIEvents.UI_SHOW_WARNING
    ]
    assert len(warnings) == 1
    assert "Draw each arena by hand" in warnings[0].message


# ---------------------------------------------------------------------------
# Barnes arena assistant writes (#633, CONTRACTS section 4)
# ---------------------------------------------------------------------------


class _BarnesProjectManager:
    """Real ``ZoneManager`` storage behind the ProjectManager calls the coordinator makes."""

    def __init__(self, videos: list[str], *, protocol: str = "barnes") -> None:
        from zebtrack.core.project.zone_manager import ZoneManager

        self.zone_manager = ZoneManager()
        self.project_data: dict[str, Any] = {
            "project_type": "batch",
            "behavioral_config": {"protocol": protocol},
            "videos": [{"path": path, "metadata": {}} for path in videos],
        }
        self.saves: list[tuple[str | None, bool]] = []

    def get_zone_data(self, video_path=None, *, fallback_to_global=True):
        return self.zone_manager.get_zone_data(
            self.project_data, video_path=video_path, fallback_to_global=fallback_to_global
        )

    def save_zone_data(self, zone_data, video_path=None, *, persist=True):
        self.zone_manager.save_zone_data(self.project_data, zone_data, video_path=video_path)
        self.saves.append((None if video_path is None else str(video_path), persist))

    def find_video_entry(self, *, path=None, experiment_id=None):
        for entry in self.project_data["videos"]:
            if entry["path"] == str(path):
                return entry
        return None

    def stored(self, video_path: str):
        return self.get_zone_data(video_path, fallback_to_global=False)


def _barnes_write(n_holes: int = 20, target_click=(470.0, 240.0)):
    """A real assistant write: arena, ROIs and layout cache from the geometry module."""
    from zebtrack.analysis.protocols.barnes.contract import BarnesEllipse, BarnesParams
    from zebtrack.core.detection import barnes_geometry as geometry

    table = BarnesEllipse(center_px=(320.0, 240.0), semi_axes_px=(200.0, 170.0), angle_deg=0.0)
    layout, _model = geometry.layout_from_click(table, target_click, n_holes)
    arena, rois = geometry.build_barnes_rois(layout, BarnesParams(n_holes=n_holes))
    return arena, rois, layout.to_metadata()


@pytest.fixture
def barnes_coordinator(coordinator):
    pm = _BarnesProjectManager(["C:/exp/Dia_1/rat_3/trial.mp4", "C:/exp/Dia_2/rat_3/trial.mp4"])
    coordinator.project_manager = pm
    return coordinator


class TestBarnesLayoutApply:
    VIDEO = "C:/exp/Dia_1/rat_3/trial.mp4"
    SAME_STEM = "C:/exp/Dia_2/rat_3/trial.mp4"

    def test_the_coordinator_listens_for_the_assistant(self, coordinator, event_bus):
        event_bus.subscribe.assert_any_call(
            UIEvents.ZONE_BARNES_LAYOUT_APPLY, coordinator._on_barnes_layout_apply
        )

    def test_without_a_bus_nothing_is_subscribed(
        self,
        state_manager,
        project_manager,
        detector_service,
        settings_obj,
        ui_coordinator,
        ui_state_controller,
        cancel_event,
        video_classification_service,
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
            event_bus=None,
        )
        assert coord.event_bus is None

    def test_arena_and_rois_land_in_the_contract_order(self, barnes_coordinator):
        from zebtrack.analysis.protocols.barnes.contract import expected_roi_names

        arena, rois, metadata = _barnes_write()
        assert barnes_coordinator.apply_barnes_layout(self.VIDEO, arena, rois, metadata)

        stored = barnes_coordinator.project_manager.stored(self.VIDEO)
        assert list(stored.roi_names) == list(expected_roi_names(20))
        assert [list(map(tuple, p)) for p in stored.roi_polygons] == [p for _n, p in rois]
        assert len(stored.roi_colors) == len(stored.roi_polygons)
        assert tuple(stored.roi_colors[1]) == (255, 0, 0)  # toca
        assert len(stored.polygon) == 64
        assert [tuple(p) for p in stored.polygon] == [(int(x), int(y)) for x, y in arena]
        assert stored.metadata["barnes_layout"] == metadata

    def test_only_the_video_at_that_path_changes(self, barnes_coordinator):
        arena, rois, metadata = _barnes_write()
        barnes_coordinator.apply_barnes_layout(self.VIDEO, arena, rois, metadata)

        other = barnes_coordinator.project_manager.stored(self.SAME_STEM)
        assert list(other.roi_names) == []
        assert list(other.polygon) == []

    def test_the_project_is_persisted_once_at_the_end(self, barnes_coordinator):
        arena, rois, metadata = _barnes_write()
        barnes_coordinator.apply_barnes_layout(self.VIDEO, arena, rois, metadata)

        saves = barnes_coordinator.project_manager.saves
        assert [persist for _video, persist in saves] == [False] * (len(saves) - 1) + [True]
        assert {video for video, _persist in saves} == {self.VIDEO}

    def test_old_barnes_rois_are_replaced_and_user_rois_kept_after(self, barnes_coordinator):
        from zebtrack.core.detection import ZoneData

        pm = barnes_coordinator.project_manager
        pm.save_zone_data(
            ZoneData(
                polygon=[(0, 0), (10, 0), (10, 10)],
                roi_polygons=[
                    [(1, 1), (2, 1), (2, 2)],
                    [(5, 5), (6, 5), (6, 6)],
                    [(7, 7), (8, 7), (8, 8)],
                ],
                roi_names=["toca", "start_area", "buraco_+09"],
                roi_colors=[(1, 2, 3), (9, 9, 9)],
                metadata={"other": 1},
            ),
            self.VIDEO,
        )
        arena, rois, metadata = _barnes_write()
        barnes_coordinator.apply_barnes_layout(self.VIDEO, arena, rois, metadata)

        stored = pm.stored(self.VIDEO)
        names = list(stored.roi_names)
        assert names.count("toca") == 1 and names.count("buraco_+09") == 1
        assert names[-1] == "start_area"
        assert names.index("start_area") == len(rois)
        assert tuple(stored.roi_colors[-1]) == (9, 9, 9)
        assert [tuple(p) for p in stored.roi_polygons[-1]] == [(5.0, 5.0), (6.0, 5.0), (6.0, 6.0)]
        assert stored.metadata["other"] == 1

    def test_a_kept_roi_without_a_colour_gets_the_default(self, barnes_coordinator):
        from zebtrack.core.detection import ZoneData

        pm = barnes_coordinator.project_manager
        pm.save_zone_data(
            ZoneData(roi_polygons=[[(5, 5), (6, 5), (6, 6)]], roi_names=["door"]), self.VIDEO
        )
        arena, rois, metadata = _barnes_write()
        barnes_coordinator.apply_barnes_layout(self.VIDEO, arena, rois, metadata)

        stored = pm.stored(self.VIDEO)
        assert tuple(stored.roi_colors[-1]) == (255, 0, 0)
        assert len(stored.roi_colors) == len(stored.roi_names)

    def test_trial_type_is_written_as_a_protocol_input(self, barnes_coordinator):
        from zebtrack.analysis.protocols.base import protocol_inputs_of_entry

        arena, rois, metadata = _barnes_write()
        barnes_coordinator.apply_barnes_layout(
            self.VIDEO, arena, rois, metadata, trial_type="probe"
        )

        entry = barnes_coordinator.project_manager.find_video_entry(path=self.VIDEO)
        assert protocol_inputs_of_entry(entry)["barnes"]["trial_type"] == "probe"
        other = barnes_coordinator.project_manager.find_video_entry(path=self.SAME_STEM)
        assert "protocol_inputs" not in other

    def test_no_trial_type_leaves_the_declaration_alone(self, barnes_coordinator):
        arena, rois, metadata = _barnes_write()
        barnes_coordinator.apply_barnes_layout(self.VIDEO, arena, rois, metadata)

        entry = barnes_coordinator.project_manager.find_video_entry(path=self.VIDEO)
        assert "protocol_inputs" not in entry

    def test_a_snapshot_without_an_entry_still_gets_its_zones(self, barnes_coordinator):
        arena, rois, metadata = _barnes_write()
        snapshot = "C:/exp/live/reference_frame.png"
        assert barnes_coordinator.apply_barnes_layout(
            snapshot, arena, rois, metadata, trial_type="training"
        )
        assert len(barnes_coordinator.project_manager.stored(snapshot).roi_names) == len(rois)

    @pytest.mark.parametrize(
        ("video", "arena_ok", "rois_ok", "metadata_ok"),
        [
            ("", True, True, True),
            (VIDEO, False, True, True),
            (VIDEO, True, False, True),
            (VIDEO, True, True, False),
        ],
        ids=["no-video", "no-arena", "no-rois", "bad-layout"],
    )
    def test_unusable_input_writes_nothing(
        self, barnes_coordinator, video, arena_ok, rois_ok, metadata_ok
    ):
        arena, rois, metadata = _barnes_write()
        written = barnes_coordinator.apply_barnes_layout(
            video,
            arena if arena_ok else arena[:2],
            rois if rois_ok else [],
            metadata if metadata_ok else {"schema": 99},
        )
        assert written is False
        assert barnes_coordinator.project_manager.saves == []

    def test_an_unknown_trial_type_writes_nothing(self, barnes_coordinator):
        arena, rois, metadata = _barnes_write()
        assert not barnes_coordinator.apply_barnes_layout(
            self.VIDEO, arena, rois, metadata, trial_type="habituation"
        )
        assert barnes_coordinator.project_manager.saves == []

    def test_the_event_handler_writes_and_redraws(self, barnes_coordinator):
        from zebtrack.ui.event_bus_v2 import BarnesLayoutApplyPayload

        arena, rois, metadata = _barnes_write()
        payload = BarnesLayoutApplyPayload(
            video_path=self.VIDEO,
            arena_polygon=tuple(arena),
            rois=tuple((name, tuple(points)) for name, points in rois),
            layout_metadata=metadata,
            trial_type="training",
        )
        with patch.object(barnes_coordinator, "_publish_event") as publish:
            barnes_coordinator._on_barnes_layout_apply(payload)

        published = [call.args[0] for call in publish.call_args_list]
        assert UIEvents.UI_REDRAW_ZONES in published
        assert UIEvents.UI_UPDATE_ZONE_LIST in published
        assert UIEvents.UI_SHOW_WARNING not in published
        stored = barnes_coordinator.project_manager.stored(self.VIDEO)
        assert len(stored.roi_names) == len(rois)

    def test_the_event_handler_warns_when_nothing_could_be_written(self, barnes_coordinator):
        from zebtrack.ui.event_bus_v2 import BarnesLayoutApplyPayload

        payload = BarnesLayoutApplyPayload(
            video_path=self.VIDEO, arena_polygon=(), rois=(), layout_metadata={}
        )
        with patch.object(barnes_coordinator, "_publish_event") as publish:
            barnes_coordinator._on_barnes_layout_apply(payload)

        events = [call.args[0] for call in publish.call_args_list]
        assert events == [UIEvents.UI_SHOW_WARNING]
        assert "trial.mp4" in publish.call_args.args[1].message


def test_arena_and_roi_writers_target_an_explicit_video(coordinator):
    zone_data = MagicMock()
    zone_data.roi_polygons = []
    zone_data.roi_names = []
    zone_data.roi_colors = []
    coordinator.project_manager.get_zone_data.return_value = zone_data

    with patch.object(coordinator, "_publish_processing_mode"):
        coordinator.set_main_arena_polygon(
            [(0.4, 0.6), (10.0, 0.0), (10.0, 10.0)], video_path="v.mp4", persist=False
        )
    coordinator.add_roi_polygon(
        [(0, 0), (5, 0), (5, 5)], "toca", (1, 2, 3), video_path="v.mp4", persist=False
    )

    for call in coordinator.project_manager.get_zone_data.call_args_list:
        assert call.args == ("v.mp4",)
    for call in coordinator.project_manager.save_zone_data.call_args_list:
        assert call.args == (zone_data, "v.mp4")
        assert call.kwargs == {"persist": False}
    assert zone_data.polygon == [(0, 0), (10, 0), (10, 10)]


def test_writers_default_to_the_active_video_and_persist(coordinator):
    zone_data = MagicMock()
    zone_data.roi_polygons = []
    zone_data.roi_names = []
    zone_data.roi_colors = []
    coordinator.project_manager.get_zone_data.return_value = zone_data

    coordinator.add_roi_polygon([(0, 0), (5, 0), (5, 5)], "ROI1")

    coordinator.project_manager.get_zone_data.assert_called_once_with()
    coordinator.project_manager.save_zone_data.assert_called_once_with(
        zone_data, None, persist=True
    )
