"""
Extended unit tests for MultiAquariumDetector in core/detection/multi_aquarium_detector.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.core.detection.detection_post_processor import DetectionPostProcessor
from zebtrack.core.detection.detection_types import AquariumData
from zebtrack.core.detection.multi_aquarium_detector import (
    AQUARIUM_TRACK_ID_MULTIPLIER,
    MAX_LOCAL_TRACK_ID,
    MultiAquariumDetector,
)
from zebtrack.core.detection.zone_scaler import ZoneScaler
from zebtrack.plugins.base import DetectorPlugin
from zebtrack.settings import load_settings


class TestMultiAquariumDetectorExtended:
    """Test MultiAquariumDetector initialization, track IDs, and scaling."""

    @pytest.fixture
    def mock_plugin(self) -> MagicMock:
        plugin = MagicMock(spec=DetectorPlugin)
        plugin.get_name.return_value = "MockDetectorPlugin"
        plugin.detect.return_value = []
        return plugin

    def test_constants(self):
        assert AQUARIUM_TRACK_ID_MULTIPLIER == 1000
        assert MAX_LOCAL_TRACK_ID == 999

    def test_init_none_plugin_raises(self):
        scaler = ZoneScaler(1280, 720)
        post_proc = DetectionPostProcessor()
        with pytest.raises(ValueError, match="must be initialized with a valid plugin"):
            MultiAquariumDetector(
                plugin=None,  # type: ignore[arg-type]
                zone_scaler=scaler,
                post_processor=post_proc,
            )

    def test_init_success(self, mock_plugin: MagicMock):
        settings_obj = load_settings()
        scaler = ZoneScaler(1920, 1080)
        post_proc = DetectionPostProcessor()

        detector = MultiAquariumDetector(
            plugin=mock_plugin,
            zone_scaler=scaler,
            post_processor=post_proc,
            base_width=1920,
            base_height=1080,
            settings_obj=settings_obj,
        )

        assert detector.plugin is mock_plugin
        assert detector.zone_scaler is scaler
        assert detector.post_processor is post_proc
        assert detector.base_width == 1920
        assert detector.base_height == 1080
        assert detector.settings is settings_obj
        assert detector._multi_aquarium_mode is False

    def test_set_multi_aquarium_zones_invalid_dimensions_raises(self, mock_plugin: MagicMock):
        scaler = ZoneScaler(1280, 720)
        post_proc = DetectionPostProcessor()
        detector = MultiAquariumDetector(
            plugin=mock_plugin,
            zone_scaler=scaler,
            post_processor=post_proc,
        )
        with pytest.raises(ValueError, match="Invalid dimensions"):
            detector.set_multi_aquarium_zones([], actual_width=0, actual_height=720)

    def test_set_multi_aquarium_zones_more_than_two_raises(self, mock_plugin: MagicMock):
        scaler = ZoneScaler(1280, 720)
        post_proc = DetectionPostProcessor()
        detector = MultiAquariumDetector(
            plugin=mock_plugin,
            zone_scaler=scaler,
            post_processor=post_proc,
        )
        aq = AquariumData(id=0, polygon=[[0, 0], [10, 0], [10, 10]])
        with pytest.raises(ValueError, match="Maximum of 2 aquariums supported"):
            detector.set_multi_aquarium_zones([aq, aq, aq], actual_width=1280, actual_height=720)

    def test_set_multi_aquarium_zones_success(self, mock_plugin: MagicMock):
        scaler = ZoneScaler(1280, 720)
        post_proc = DetectionPostProcessor()
        detector = MultiAquariumDetector(
            plugin=mock_plugin,
            zone_scaler=scaler,
            post_processor=post_proc,
        )

        aq0 = AquariumData(
            id=0,
            polygon=[[10, 10], [500, 10], [500, 500], [10, 500]],
            roi_polygons=[[[50, 50], [150, 50], [150, 150], [50, 150]]],
            roi_names=["TopLeft0"],
        )
        aq1 = AquariumData(
            id=1,
            polygon=[[600, 10], [1100, 10], [1100, 500], [600, 500]],
            roi_polygons=[[[650, 50], [750, 50], [750, 150], [650, 150]]],
            roi_names=["TopLeft1"],
        )

        detector.set_multi_aquarium_zones([aq0, aq1], actual_width=1280, actual_height=720)

        assert detector._multi_aquarium_mode is True
        assert detector._zones_configured is True
        assert len(detector._aquariums) == 2

        # Verify scaled polygon lookups
        assert 0 in detector._scaled_aquarium_polygons
        poly0 = detector._scaled_aquarium_polygons[0]
        assert poly0.shape == (4, 2)

        assert 0 in detector._scaled_aquarium_roi_polygons
        rois0 = detector._scaled_aquarium_roi_polygons[0]
        assert len(rois0) == 1


# ---------------------------------------------------------------------------
# Class roles (ADR-009) in the multi-aquarium detector.
# ---------------------------------------------------------------------------

_NAMES = {0: "arena", 1: "mouse", 2: "rat", 3: "experimenter"}
_TWO_SUBJECTS = {"arena": "arena", "mouse": "subject", "rat": "subject"}
_WITH_CONTEXT = {"arena": "arena", "rat": "subject", "experimenter": "context"}
_AQ0 = [[100, 100], [200, 100], [200, 200], [100, 200]]
_AQ1 = [[300, 100], [400, 100], [400, 200], [300, 200]]


class _FullFramePlugin(DetectorPlugin):
    """Returns fixed FULL-FRAME boxes translated into the crop it receives."""

    def __init__(self, boxes, conf_threshold=0.5):
        self.class_names = dict(_NAMES)
        self.conf_threshold = conf_threshold
        self._boxes = list(boxes)
        self.calls: list[tuple[tuple[int, ...], float | None]] = []
        self.offsets: list[tuple[int, int]] = []

    def detect(self, frame, conf_threshold=None):
        self.calls.append((frame.shape, conf_threshold))
        dx, dy = self.offsets.pop(0) if self.offsets else (0, 0)
        return [
            (x1 - dx, y1 - dy, x2 - dx, y2 - dy, c, None, k) for x1, y1, x2, y2, c, k in self._boxes
        ]

    @staticmethod
    def get_name() -> str:
        return "FullFrame"

    @property
    def model_input_shape(self) -> tuple[int, int]:
        return (640, 640)


def _multi(plugin, roles=None, settings_obj=None) -> MultiAquariumDetector:
    from zebtrack.core.detection.class_roles import resolve_class_role_map

    role_map = (
        resolve_class_role_map(_NAMES, weight_entry={"class_roles": roles}) if roles else None
    )
    detector = MultiAquariumDetector(
        plugin=plugin,
        zone_scaler=ZoneScaler(500, 300),
        post_processor=DetectionPostProcessor(),
        base_width=500,
        base_height=300,
        settings_obj=settings_obj,
        class_role_map=role_map,
    )
    detector.set_multi_aquarium_zones(
        [AquariumData(id=0, polygon=_AQ0), AquariumData(id=1, polygon=_AQ1)],
        actual_width=500,
        actual_height=300,
    )
    # These tests pin which CLASSES reach tracking; the tracker itself (which
    # caps tracks per aquarium) is covered elsewhere.
    detector._track_partitioned = lambda partitioned: partitioned  # type: ignore[method-assign]
    return detector


def _frame():
    import numpy as np

    return np.zeros((300, 500, 3), dtype=np.uint8)


def _context_settings(margin=0.15, floor=0.1):
    from types import SimpleNamespace

    return SimpleNamespace(
        model_selection=SimpleNamespace(
            context_inference_scope="arena_crop_margin",
            context_crop_margin_frac=margin,
            context_min_confidence=floor,
            class_aliases=None,
        )
    )


def _classes(results: dict[int, list[tuple]]) -> dict[int, list[int]]:
    return {aq: sorted(int(det[6]) for det in dets) for aq, dets in results.items()}


_TWO_SUBJECT_BOXES = (
    (140, 140, 150, 150, 0.9, 1),  # mouse in aq0
    (160, 160, 170, 170, 0.9, 2),  # rat in aq0
)


class TestClassRolesInTheMultiAquariumDetector:
    _BOXES = _TWO_SUBJECT_BOXES

    def test_without_context_the_crop_is_the_legacy_padded_one(self):
        plugin = _FullFramePlugin(self._BOXES)
        detector = _multi(plugin)
        plugin.offsets = [(90, 90), (290, 90)]

        detector.detect_partitioned_optimized(_frame())

        # boundingRect 101x101 + 10 px padding on every side, no threshold kwarg.
        assert plugin.calls == [((121, 121, 3), None), ((121, 121, 3), None)]

    def test_alias_path_keeps_only_the_lowest_animal_class(self):
        plugin = _FullFramePlugin(self._BOXES)
        detector = _multi(plugin)
        plugin.offsets = [(90, 90), (290, 90)]

        results = detector.detect_partitioned_optimized(_frame())

        assert _classes(results)[0] == [1]

    def test_optimized_path_tracks_every_subject_class(self):
        plugin = _FullFramePlugin(self._BOXES)
        detector = _multi(plugin, _TWO_SUBJECTS)
        plugin.offsets = [(90, 90), (290, 90)]

        results = detector.detect_partitioned_optimized(_frame())

        assert _classes(results)[0] == [1, 2]

    def test_parallel_path_tracks_every_subject_class(self):
        plugin = _FullFramePlugin(self._BOXES)
        detector = _multi(plugin, _TWO_SUBJECTS)
        detector._apply_byte_tracking_multi = lambda dets, _tracker: [  # type: ignore[method-assign,assignment]
            (d[0], d[1], d[2], d[3], d[4], i + 1, d[6]) for i, d in enumerate(dets)
        ]
        plugin.offsets = [(90, 90), (290, 90)]

        results = detector.detect_partitioned_parallel(_frame(), max_workers=1)

        assert _classes(results)[0] == [1, 2]

    def test_context_widens_the_crop_lowers_the_floor_and_is_observed(self):
        boxes = [
            (150, 150, 160, 160, 0.9, 2),  # rat
            (85, 85, 99, 99, 0.2, 3),  # experimenter, outside the arena
        ]
        plugin = _FullFramePlugin(boxes, conf_threshold=0.5)
        detector = _multi(plugin, _WITH_CONTEXT, _context_settings(margin=0.15, floor=0.1))
        plugin.offsets = [(85, 85), (285, 85)]

        results = detector.detect_partitioned_optimized(_frame())
        observations = detector.pop_class_observations()

        assert plugin.calls[0] == ((131, 131, 3), 0.1)
        assert _classes(results)[0] == [2]
        aq0 = [(o["class_name"], o["role"], o["aquarium_id"]) for o in observations[:2]]
        assert aq0 == [("rat", "subject", 0), ("experimenter", "context", 0)]
        assert detector.pop_class_observations() == []

    def test_full_frame_path_drops_context_only_with_an_explicit_map(self):
        boxes = [(150, 150, 160, 160, 0.9, 2), (170, 170, 180, 180, 0.9, 3)]

        legacy = _multi(_FullFramePlugin(boxes))
        explicit = _multi(_FullFramePlugin(boxes), _WITH_CONTEXT)

        assert _classes(legacy.detect_partitioned(_frame()))[0] == [2, 3]
        assert _classes(explicit.detect_partitioned(_frame()))[0] == [2]
