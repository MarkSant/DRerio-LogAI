"""Tests for LiveCalibrationCoordinator — segmentation polygon path.

Covers Etapa 2 (Issue #2): the ``_detect_polygon_on_burst`` helper must
preserve the real aquarium shape (N-vertex mask polygon) when the underlying
YOLO model is a segmentation model AND the ``preserve_real_shape`` flag is
set. Otherwise the historical 4-corner bbox fallback is kept.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from zebtrack.coordinators.live_calibration_coordinator import (
    LiveCalibrationCoordinator,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coordinator() -> LiveCalibrationCoordinator:
    """Build a LiveCalibrationCoordinator with minimal mocks.

    The unit under test (``_detect_polygon_on_burst``) does not exercise any
    coordinator collaborator besides the detector mock passed in directly,
    so all dependencies can be lightweight MagicMocks.
    """
    return LiveCalibrationCoordinator(
        state_manager=MagicMock(),
        project_manager=MagicMock(),
        detector_service=MagicMock(),
        weight_manager=MagicMock(),
        settings_obj=MagicMock(),
        event_bus=MagicMock(),
        root=None,
        view=None,
    )


def _make_seg_detector(
    *,
    boxes_xyxy: np.ndarray,
    masks_xy: list[np.ndarray] | None,
) -> MagicMock:
    """Build a mock detector whose ``model.predict`` returns a single result."""
    detector = MagicMock()
    detector.model = MagicMock()
    detector.model.task = "segment"

    boxes_obj = MagicMock()
    boxes_obj.xyxy = MagicMock()
    boxes_obj.xyxy.cpu.return_value.numpy.return_value = boxes_xyxy
    # `if not results[0].boxes` and `len(results[0].boxes)` rely on __len__/__bool__
    boxes_obj.__len__ = lambda self: len(boxes_xyxy)
    boxes_obj.__bool__ = lambda self: len(boxes_xyxy) > 0

    result = SimpleNamespace(
        boxes=boxes_obj,
        masks=SimpleNamespace(xy=masks_xy) if masks_xy is not None else None,
    )
    detector.model.predict = MagicMock(return_value=[result])
    return detector


def _make_det_detector(*, boxes_xyxy: np.ndarray) -> MagicMock:
    """Build a mock detector whose model is a detection model (no masks)."""
    detector = MagicMock()
    detector.model = MagicMock()
    detector.model.task = "detect"

    boxes_obj = MagicMock()
    boxes_obj.xyxy = MagicMock()
    boxes_obj.xyxy.cpu.return_value.numpy.return_value = boxes_xyxy
    boxes_obj.__len__ = lambda self: len(boxes_xyxy)
    boxes_obj.__bool__ = lambda self: len(boxes_xyxy) > 0

    result = SimpleNamespace(boxes=boxes_obj, masks=None)
    detector.model.predict = MagicMock(return_value=[result])
    return detector


def _hexagon_polygon(cx: int, cy: int, r: int) -> np.ndarray:
    """Build a 6-vertex polygon approximating a circle, as numpy float array."""
    angles = np.linspace(0.0, 2.0 * np.pi, 6, endpoint=False)
    pts = np.stack([cx + r * np.cos(angles), cy + r * np.sin(angles)], axis=1)
    return pts.astype(np.float32)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_frame() -> np.ndarray:
    """A blank 640x480 BGR frame (matches typical live camera output)."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


def test_detect_polygon_on_burst_uses_masks_when_seg_and_preserve_real_shape(
    sample_frame,
):
    """Seg model + flag set → polygon has all mask vertices (not 4 bbox corners)."""
    coordinator = _make_coordinator()

    hex_mask = _hexagon_polygon(cx=320, cy=240, r=180)
    # bbox encompassing the hexagon (passes 10%-98% area gate against the 640x480 frame)
    bbox = np.array([[140.0, 60.0, 500.0, 420.0]], dtype=np.float32)
    detector = _make_seg_detector(boxes_xyxy=bbox, masks_xy=[hex_mask])

    polygons = coordinator._detect_polygon_on_burst(
        detector=detector,
        frames=[sample_frame],
        confidence=0.25,
        preserve_real_shape=True,
    )

    assert len(polygons) == 1, "expected one approved polygon"
    poly = polygons[0]
    assert len(poly) == 6, f"expected 6-vertex hexagon, got {len(poly)}"
    # All points should be ints (ZoneData contract)
    assert all(isinstance(p[0], int) and isinstance(p[1], int) for p in poly)


def test_detect_polygon_on_burst_uses_bbox_when_seg_but_flag_disabled(sample_frame):
    """Seg model + flag disabled → falls back to 4-corner bbox (legacy behavior)."""
    coordinator = _make_coordinator()

    hex_mask = _hexagon_polygon(cx=320, cy=240, r=180)
    bbox = np.array([[140.0, 60.0, 500.0, 420.0]], dtype=np.float32)
    detector = _make_seg_detector(boxes_xyxy=bbox, masks_xy=[hex_mask])

    polygons = coordinator._detect_polygon_on_burst(
        detector=detector,
        frames=[sample_frame],
        confidence=0.25,
        preserve_real_shape=False,
    )

    assert len(polygons) == 1
    poly = polygons[0]
    assert len(poly) == 4, "preserve_real_shape=False must yield a 4-corner bbox"
    assert poly == [[140, 60], [500, 60], [500, 420], [140, 420]]


def test_detect_polygon_on_burst_uses_bbox_when_det_model(sample_frame):
    """Detection model (no masks) → always returns 4-corner bbox even with flag on."""
    coordinator = _make_coordinator()

    bbox = np.array([[140.0, 60.0, 500.0, 420.0]], dtype=np.float32)
    detector = _make_det_detector(boxes_xyxy=bbox)

    polygons = coordinator._detect_polygon_on_burst(
        detector=detector,
        frames=[sample_frame],
        confidence=0.25,
        preserve_real_shape=True,
    )

    assert len(polygons) == 1
    assert len(polygons[0]) == 4


def test_detect_polygon_on_burst_falls_back_to_bbox_when_mask_missing(sample_frame):
    """Flag on + seg model BUT mask polygon is unusable → bbox fallback used."""
    coordinator = _make_coordinator()

    bbox = np.array([[140.0, 60.0, 500.0, 420.0]], dtype=np.float32)
    # Mask container present but empty (e.g. mask post-processing yielded nothing)
    detector = _make_seg_detector(boxes_xyxy=bbox, masks_xy=[])

    polygons = coordinator._detect_polygon_on_burst(
        detector=detector,
        frames=[sample_frame],
        confidence=0.25,
        preserve_real_shape=True,
    )

    assert len(polygons) == 1
    assert len(polygons[0]) == 4, "fallback to bbox when mask data is missing"


def test_detect_polygon_on_burst_empty_frames_returns_empty_list():
    coordinator = _make_coordinator()
    detector = _make_seg_detector(boxes_xyxy=np.empty((0, 4), dtype=np.float32), masks_xy=[])

    assert (
        coordinator._detect_polygon_on_burst(
            detector=detector,
            frames=[],
            confidence=0.25,
            preserve_real_shape=True,
        )
        == []
    )


def test_detect_polygon_on_burst_rejects_polygon_outside_area_gates(sample_frame):
    """A bbox covering <10% of the frame is rejected (no polygon returned)."""
    coordinator = _make_coordinator()

    # 50x50 bbox → ~0.8% of a 640x480 frame, well below the 10% min
    tiny_bbox = np.array([[100.0, 100.0, 150.0, 150.0]], dtype=np.float32)
    detector = _make_seg_detector(
        boxes_xyxy=tiny_bbox,
        masks_xy=[_hexagon_polygon(cx=125, cy=125, r=20)],
    )

    polygons = coordinator._detect_polygon_on_burst(
        detector=detector,
        frames=[sample_frame],
        confidence=0.25,
        preserve_real_shape=True,
    )

    assert polygons == []
