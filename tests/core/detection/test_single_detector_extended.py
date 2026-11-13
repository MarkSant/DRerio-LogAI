"""
Extended unit tests for SingleDetector in core/detection/single_detector.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from zebtrack.core.detection.class_roles import resolve_class_role_map
from zebtrack.core.detection.detection_types import AquariumData, MultiAquariumZoneData, ZoneData
from zebtrack.core.detection.single_detector import SingleDetector
from zebtrack.core.detection.zone_scaler import ZoneScaler
from zebtrack.plugins.base import DetectorPlugin
from zebtrack.settings import load_settings


class TestSingleDetectorExtended:
    """Test SingleDetector initialization, zones, modes, and tracking."""

    @pytest.fixture
    def mock_plugin(self) -> MagicMock:
        plugin = MagicMock(spec=DetectorPlugin)
        plugin.get_name.return_value = "MockDetector"
        plugin.detect.return_value = []
        return plugin

    def test_init_none_plugin_raises_value_error(self):
        with pytest.raises(ValueError, match="must be initialized with a valid plugin"):
            SingleDetector(plugin=None)  # type: ignore[arg-type]

    def test_init_custom_dimensions_and_dependencies(self, mock_plugin: MagicMock):
        settings_obj = load_settings()
        scaler = ZoneScaler(base_width=1920, base_height=1080)

        detector = SingleDetector(
            plugin=mock_plugin,
            zone_scaler=scaler,
            base_width=1920,
            base_height=1080,
            settings_obj=settings_obj,
        )

        assert detector.plugin is mock_plugin
        assert detector.zone_scaler is scaler
        assert detector.base_width == 1920
        assert detector.base_height == 1080
        assert detector.settings is settings_obj
        assert detector._zones_configured is False

    def test_set_zones_invalid_dimensions_raises(self, mock_plugin: MagicMock):
        detector = SingleDetector(plugin=mock_plugin)
        zone_data = ZoneData()
        with pytest.raises(ValueError, match="Actual dimensions must be positive"):
            detector.set_zones(zone_data, actual_width=0, actual_height=720)

    def test_set_zones_with_zone_data(self, mock_plugin: MagicMock):
        detector = SingleDetector(plugin=mock_plugin)
        zone_data = ZoneData(
            polygon=[[10, 10], [100, 10], [100, 100], [10, 100]],
            roi_polygons=[[[20, 20], [50, 20], [50, 50], [20, 50]]],
            roi_names=["Center"],
            roi_colors=[(255, 0, 0)],
        )

        detector.set_zones(zone_data, actual_width=1280, actual_height=720)

        assert detector.zones == zone_data
        assert detector._zones_configured is True
        assert detector._last_width == 1280
        assert detector._last_height == 720

    def test_set_zones_with_multi_aquarium_zone_data(self, mock_plugin: MagicMock):
        detector = SingleDetector(plugin=mock_plugin)
        aq0 = AquariumData(id=0, polygon=[[0, 0], [50, 50]])
        multi_data = MultiAquariumZoneData(aquariums=[aq0])

        detector.set_zones(multi_data, actual_width=1280, actual_height=720)

        assert detector.zones == multi_data
        assert detector._zones_configured is True

    def test_set_context_and_aquarium_region(self, mock_plugin: MagicMock):
        detector = SingleDetector(plugin=mock_plugin)
        detector.set_context("diagnostic")
        assert detector._context == "diagnostic"

        detector.set_aquarium_region_defined(True)
        assert detector._aquarium_region_defined is True

    def test_set_single_subject_mode(self, mock_plugin: MagicMock):
        detector = SingleDetector(plugin=mock_plugin)
        assert detector._single_subject_mode is False

        detector.set_single_subject_mode(True)
        assert detector._single_subject_mode is True

        detector.set_single_subject_mode(False)
        assert detector._single_subject_mode is False


# ---------------------------------------------------------------------------
# Class roles (ADR-009): subject filter, context crop, observations.
# ---------------------------------------------------------------------------

_BARNES = {0: "arena", 1: "experimenter", 2: "rat", 3: "start_box"}
_BARNES_ROLES = {
    "arena": "arena",
    "experimenter": "context",
    "rat": "subject",
    "start_box": "context",
}
_ARENA_SQUARE = [[100, 100], [200, 100], [200, 200], [100, 200]]


class _CropRecordingPlugin(DetectorPlugin):
    """Records what the detector hands to inference; returns crop-space boxes."""

    def __init__(self, class_names, detections_full_frame=(), conf_threshold=0.5):
        self.class_names = dict(class_names)
        self.conf_threshold = conf_threshold
        self._full_frame = list(detections_full_frame)
        self.crops: list[np.ndarray] = []
        self.confs: list[float | None] = []
        self.offsets: list[tuple[int, int]] = []
        self._next_offset = (0, 0)

    def detect(self, frame, conf_threshold=None):
        self.crops.append(frame.copy())
        self.confs.append(conf_threshold)
        dx, dy = self._next_offset
        return [
            (x1 - dx, y1 - dy, x2 - dx, y2 - dy, conf, None, cid)
            for (x1, y1, x2, y2, conf, cid) in self._full_frame
        ]

    @staticmethod
    def get_name() -> str:
        return "CropRecording"

    @property
    def model_input_shape(self) -> tuple[int, int]:
        return (640, 640)


def _frame() -> np.ndarray:
    rng = np.random.default_rng(7)
    return rng.integers(0, 255, size=(300, 400, 3), dtype=np.uint8)


def _detector(plugin, role_map=None, settings_obj=None) -> SingleDetector:
    detector = SingleDetector(
        plugin=plugin,
        base_width=400,
        base_height=300,
        settings_obj=settings_obj,
        class_role_map=role_map,
    )
    detector.set_zones(ZoneData(polygon=_ARENA_SQUARE), actual_width=400, actual_height=300)
    return detector


def _context_settings(scope="arena_crop_margin", margin=0.15, floor=None):
    from types import SimpleNamespace

    return SimpleNamespace(
        model_selection=SimpleNamespace(
            context_inference_scope=scope,
            context_crop_margin_frac=margin,
            context_min_confidence=floor,
            class_aliases=None,
        )
    )


class TestClassRolesInTheSingleDetector:
    def test_without_context_the_crop_and_threshold_are_the_legacy_ones(self):
        frame = _frame()
        plugin = _CropRecordingPlugin(_BARNES)
        detector = _detector(plugin)  # aliases: no context
        crop_info = detector.zone_scaler.get_crop_info(frame, detector.zone_scaler.scaled_polygon)
        assert crop_info is not None
        expected_crop = crop_info[0]

        detector.detect(frame, "pre-recorded")

        assert detector.class_role_map.has_context is False
        assert plugin.crops[0].tobytes() == expected_crop.tobytes()
        assert plugin.crops[0].shape == expected_crop.shape
        assert plugin.confs == [None]

    def test_context_map_widens_the_crop_by_the_margin(self):
        role_map = resolve_class_role_map(_BARNES, weight_entry={"class_roles": _BARNES_ROLES})
        plugin = _CropRecordingPlugin(_BARNES)
        detector = _detector(plugin, role_map, _context_settings(margin=0.15))

        detector.detect(_frame(), "pre-recorded")

        # boundingRect of the square is 101x101 at (100, 100); 15% = 15 px.
        assert plugin.crops[0].shape[:2] == (131, 131)

    @pytest.mark.parametrize(
        ("scope", "shape"), [("full_frame", (300, 400)), ("arena_crop", (101, 101))]
    )
    def test_context_scope_selects_the_window(self, scope, shape):
        role_map = resolve_class_role_map(_BARNES, weight_entry={"class_roles": _BARNES_ROLES})
        plugin = _CropRecordingPlugin(_BARNES)
        detector = _detector(plugin, role_map, _context_settings(scope=scope))

        detector.detect(_frame(), "pre-recorded")

        assert plugin.crops[0].shape[:2] == shape

    def test_context_infers_with_the_lower_floor_and_filters_by_role(self):
        role_map = resolve_class_role_map(_BARNES, weight_entry={"class_roles": _BARNES_ROLES})
        plugin = _CropRecordingPlugin(
            _BARNES,
            detections_full_frame=[
                (140, 140, 150, 150, 0.9, 2),  # rat, confident
                (160, 160, 170, 170, 0.3, 2),  # rat below the subject floor
                (90, 90, 120, 120, 0.2, 1),  # experimenter above the context floor
                (95, 150, 105, 160, 0.05, 3),  # start box below the context floor
            ],
            conf_threshold=0.5,
        )
        detector = _detector(plugin, role_map, _context_settings(floor=0.1, margin=0.15))
        plugin._next_offset = (85, 85)

        detector.detect(_frame(), "pre-recorded")
        observations = detector.pop_class_observations()

        assert plugin.confs == [pytest.approx(0.1)]
        assert [(o["class_name"], o["role"]) for o in observations] == [
            ("rat", "subject"),
            ("experimenter", "context"),
        ]
        assert observations[1]["bbox"] == (90.0, 90.0, 120.0, 120.0)
        assert observations[0]["aquarium_id"] is None
        assert detector.pop_class_observations() == []

    def test_every_subject_class_is_tracked(self):
        names = {0: "arena", 1: "mouse", 2: "rat"}
        roles = {"arena": "arena", "mouse": "subject", "rat": "subject"}
        role_map = resolve_class_role_map(names, weight_entry={"class_roles": roles})
        plugin = _CropRecordingPlugin(
            names,
            detections_full_frame=[
                (110, 110, 120, 120, 0.9, 1),
                (150, 150, 160, 160, 0.9, 2),
            ],
        )
        detector = _detector(plugin, role_map)
        plugin._next_offset = (100, 100)

        tracked, _error = detector.detect(_frame(), "pre-recorded")

        assert sorted(det[6] for det in tracked) == [1, 2]

    def test_alias_path_tracks_only_the_lowest_animal_class(self):
        names = {0: "arena", 1: "mouse", 2: "rat"}
        plugin = _CropRecordingPlugin(
            names,
            detections_full_frame=[
                (110, 110, 120, 120, 0.9, 1),
                (150, 150, 160, 160, 0.9, 2),
            ],
        )
        detector = _detector(plugin)
        plugin._next_offset = (100, 100)

        tracked, _error = detector.detect(_frame(), "pre-recorded")

        assert [det[6] for det in tracked] == [1]

    def test_small_arena_box_becomes_the_animal_only_without_an_explicit_map(self):
        names = {0: "arena", 1: "rat"}
        small_arena_box = [(140, 140, 150, 150, 0.9, 0)]

        legacy_plugin = _CropRecordingPlugin(names, detections_full_frame=small_arena_box)
        legacy = _detector(legacy_plugin)
        legacy_plugin._next_offset = (100, 100)
        legacy_tracked, _ = legacy.detect(_frame(), "pre-recorded")

        explicit_map = resolve_class_role_map(
            names, weight_entry={"class_roles": {"arena": "arena", "rat": "subject"}}
        )
        explicit_plugin = _CropRecordingPlugin(names, detections_full_frame=small_arena_box)
        explicit = _detector(explicit_plugin, explicit_map)
        explicit_plugin._next_offset = (100, 100)
        explicit_tracked, _ = explicit.detect(_frame(), "pre-recorded")

        assert [det[6] for det in legacy_tracked] == [1]
        assert explicit_tracked == []

    def test_legacy_ids_come_from_the_map(self):
        role_map = resolve_class_role_map(_BARNES, weight_entry={"class_roles": _BARNES_ROLES})
        detector = _detector(_CropRecordingPlugin(_BARNES), role_map)

        assert (detector.aquarium_class_id, detector.animal_class_id) == (0, 2)
        assert detector.class_role_map is role_map


# ---------------------------------------------------------------------------
# Issue #630: ByteTrack's lost-track buffer follows the SOURCE frame rate.
# ---------------------------------------------------------------------------


def _fps_settings(*, settings_fps: int = 30, track_buffer: int = 30):
    """Settings with a nominal 30 fps, interval 1 and a short ByteTrack buffer."""
    settings_obj = load_settings()
    settings_obj.video_processing.fps = settings_fps
    settings_obj.video_processing.processing_interval = 1
    settings_obj.bytetrack.track_buffer = track_buffer
    settings_obj.tracking.use_bytetrack = True
    return settings_obj


def _fps_detector(settings_obj) -> SingleDetector:
    plugin = MagicMock(spec=DetectorPlugin)
    plugin.get_name.return_value = "MockDetector"
    plugin.detect.return_value = []
    return SingleDetector(plugin=plugin, settings_obj=settings_obj)


def _seconds_until_removed(tracker, fps: float) -> float:
    """Feed one detection, then nothing; real seconds until the track is removed."""
    box = np.array([[100.0, 100.0, 140.0, 140.0, 0.95]])
    tracker.update(box, (480, 640), (480, 640))
    tracker.update(box, (480, 640), (480, 640))  # second hit confirms the track
    empty = np.empty((0, 5))
    for frames_without_detection in range(1, 10_000):
        tracker.update(empty, (480, 640), (480, 640))
        if tracker.removed_stracks:
            return frames_without_detection / fps
    raise AssertionError("the lost track was never removed")


class TestByteTrackFollowsTheSourceFps:
    """A 10 fps video with settings at 30 must keep the configured buffer in SECONDS."""

    def test_buffer_in_seconds_matches_the_configured_one_on_a_10_fps_video(self):
        settings_obj = _fps_settings(settings_fps=30, track_buffer=30)
        detector = _fps_detector(settings_obj)
        detector.set_source_fps(10.0)

        tracker = detector._ensure_byte_tracker()

        assert tracker is not None
        # 30 frames at the 30 fps reference == 1 s; at 10 fps that is 10 frames.
        assert tracker.max_time_lost == 10
        # Behaviour, not just the attribute: the lost track dies after ~1 s of
        # REAL time (one frame of slack: removal happens on the first frame past
        # the limit). With the settings fps it lived 3 s (30 frames at 10 fps).
        assert _seconds_until_removed(tracker, fps=10.0) == pytest.approx(1.1)

    def test_a_30_fps_source_is_unchanged(self):
        settings_obj = _fps_settings(settings_fps=30, track_buffer=30)
        detector = _fps_detector(settings_obj)
        detector.set_source_fps(30.0)

        tracker = detector._ensure_byte_tracker()

        assert tracker is not None
        assert tracker.max_time_lost == 30

    def test_unknown_source_falls_back_to_settings_with_a_warning(self, monkeypatch):
        from zebtrack.core.detection import single_detector as module

        warnings: list[tuple[str, dict]] = []
        monkeypatch.setattr(module.log, "warning", lambda event, **kw: warnings.append((event, kw)))
        settings_obj = _fps_settings(settings_fps=30, track_buffer=30)
        detector = _fps_detector(settings_obj)

        tracker = detector._ensure_byte_tracker()

        assert tracker is not None
        assert tracker.max_time_lost == 30
        assert detector.source_fps is None
        assert (
            "single_detector.bytetrack.fps_fallback_to_settings",
            {"frame_rate": 30.0, "reason": "source_fps_unknown"},
        ) in warnings

    def test_known_source_does_not_warn(self, monkeypatch):
        from zebtrack.core.detection import single_detector as module

        warnings: list[str] = []
        monkeypatch.setattr(module.log, "warning", lambda event, **kw: warnings.append(event))
        detector = _fps_detector(_fps_settings())
        detector.set_source_fps(10.0)

        detector._ensure_byte_tracker()

        assert "single_detector.bytetrack.fps_fallback_to_settings" not in warnings

    def test_a_new_source_rate_rebuilds_the_tracker(self):
        detector = _fps_detector(_fps_settings(track_buffer=30))
        detector.set_source_fps(30.0)
        first = detector._ensure_byte_tracker()

        assert detector._ensure_byte_tracker() is first  # same rate: reused
        detector.set_source_fps(10.0)
        second = detector._ensure_byte_tracker()

        assert second is not first
        assert second is not None
        assert second.max_time_lost == 10


# ---------------------------------------------------------------------------
# Issue #654: lost tracks age on the frame clock declared by the caller.
# ---------------------------------------------------------------------------

_BOX = (100, 100, 140, 140, 0.95, None, 1)


class TestByteTrackFrameClock:
    """``set_frame_time`` reaches ByteTrack, once per frame."""

    @staticmethod
    def _confirmed_then_lost():
        detector = _fps_detector(_fps_settings(track_buffer=30))  # 1 s buffer
        detector.set_source_fps(30.0)
        for i in range(3):
            detector.set_frame_time(i / 30)
            detector._apply_byte_tracking([_BOX], (480, 640, 3))
        detector.set_frame_time(3 / 30)
        detector._apply_byte_tracking([], (480, 640, 3))
        tracker = detector._ensure_byte_tracker()
        assert tracker is not None
        assert len(tracker.lost_stracks) == 1
        return detector, tracker, tracker.lost_stracks[0]

    def test_the_declared_instant_ages_the_lost_track_in_seconds(self):
        detector, tracker, lost = self._confirmed_then_lost()

        # One update, 5 s later (frames dropped): far past the 1 s buffer.
        detector.set_frame_time(5.0)
        detector._apply_byte_tracking([], (480, 640, 3))

        assert lost in tracker.removed_stracks

    def test_without_an_instant_the_age_is_counted_in_updates(self):
        detector, tracker, lost = self._confirmed_then_lost()

        detector._apply_byte_tracking([], (480, 640, 3))

        assert lost not in tracker.removed_stracks

    def test_the_instant_is_used_once_so_a_stale_one_never_freezes_the_age(self):
        detector, tracker, lost = self._confirmed_then_lost()
        detector.set_frame_time(4 / 30)
        detector._apply_byte_tracking([], (480, 640, 3))

        # The caller stops declaring. A reused 4/30 instant would keep the age
        # at 2/30 s forever; the count fallback removes it past 30 updates.
        removed_after = None
        for n in range(1, 100):
            detector._apply_byte_tracking([], (480, 640, 3))
            if lost in tracker.removed_stracks:
                removed_after = n
                break

        assert removed_after is not None
        assert removed_after <= tracker.max_time_lost + 1


# ---------------------------------------------------------------------------
# Issue #649: a box ByteTrack does not emit never re-ids the tracked animal.
# ---------------------------------------------------------------------------


class TestUnemittedDetectionsKeepTheTrackedIds:
    """Multi-subject mode: one rat tracked as 1, then a spurious faint box.

    ByteTrack emits only the rat (the faint box is below ``track_thresh`` and
    nothing is lost for it to re-find). The detector used to answer "fewer
    tracks than detections" by giving EVERY detection of the frame a fresh id:
    the rat became id 2 for one row and the box id 3 -- the two one-row tracks
    that made the Barnes ``Exemp_2`` report count three animals.
    """

    RAT = (100, 100, 140, 140, 0.95, None, 1)
    FAINT = (400, 300, 420, 320, 0.3, None, 1)

    @pytest.fixture(autouse=True)
    def _fresh_ids(self):
        from zebtrack.tracker.basetrack import BaseTrack

        BaseTrack.reset_id_counter()

    def _tracked_rat(self):
        detector = _fps_detector(_fps_settings())
        detector.set_source_fps(30.0)
        out: list[tuple] = []
        for _ in range(3):
            out = detector._apply_byte_tracking([self.RAT], (480, 640, 3))
        assert [d[5] for d in out] == [1]
        return detector

    def test_the_rat_keeps_its_id_and_no_new_id_appears(self):
        detector = self._tracked_rat()

        out = detector._apply_byte_tracking([self.RAT, self.FAINT], (480, 640, 3))

        assert [d[5] for d in out] == [1]
        assert out[0][:4] == self.RAT[:4]

    def test_over_a_whole_run_only_the_rat_id_is_ever_written(self):
        detector = self._tracked_rat()
        ids: set = set()
        for frame in range(30):
            dets = [self.RAT, self.FAINT] if frame % 7 == 3 else [self.RAT]
            ids.update(d[5] for d in detector._apply_byte_tracking(dets, (480, 640, 3)))

        assert ids == {1}


# ---------------------------------------------------------------------------
# Issue #666: the CONFIGURED track_buffer reaches ByteTrack, whatever the plugin.
# ---------------------------------------------------------------------------


def _production_ultralytics_plugin(settings_obj):
    """The real Ultralytics plugin, with only the YOLO weights stubbed out."""
    from unittest.mock import patch

    from zebtrack.plugins.ultralytics_detector import UltralyticsDetectorPlugin

    with (
        patch("zebtrack.plugins.ultralytics_detector.YOLO") as yolo_cls,
        patch("zebtrack.plugins.ultralytics_detector.is_cuda_available", return_value=False),
    ):
        yolo_cls.return_value.names = {0: "aquarium", 1: "zebrafish"}
        return UltralyticsDetectorPlugin("weights.pt", settings_obj=settings_obj)


class TestConfiguredTrackBufferReachesByteTrack:
    """Until #666 both plugins pinned ``track_buffer = 60`` and won: 2 s, always."""

    def test_lost_track_lives_the_configured_seconds_with_the_real_plugin(self):
        settings_obj = _fps_settings(settings_fps=30, track_buffer=90)  # 3 s
        detector = SingleDetector(
            plugin=_production_ultralytics_plugin(settings_obj), settings_obj=settings_obj
        )
        detector.set_source_fps(30.0)

        tracker = detector._ensure_byte_tracker()

        assert tracker is not None
        # One frame of slack, as in the #630 tests: removal is on the first frame
        # past the limit. With the plugin's 60 it died after 61 / 30 s.
        assert _seconds_until_removed(tracker, fps=30.0) == pytest.approx(91 / 30)

    def test_a_value_changed_after_the_plugin_was_built_rebuilds_the_tracker(self):
        """``DetectorService`` writes the UI value into the settings at runtime."""
        settings_obj = _fps_settings(settings_fps=30, track_buffer=90)
        detector = SingleDetector(
            plugin=_production_ultralytics_plugin(settings_obj), settings_obj=settings_obj
        )
        detector.set_source_fps(30.0)
        first = detector._ensure_byte_tracker()

        settings_obj.bytetrack.track_buffer = 150  # 5 s
        second = detector._ensure_byte_tracker()

        assert second is not None
        assert second is not first
        assert _seconds_until_removed(second, fps=30.0) == pytest.approx(151 / 30)
