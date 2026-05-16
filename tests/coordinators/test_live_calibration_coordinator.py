"""Tests for LiveCalibrationCoordinator — segmentation polygon path.

Covers Etapa 2 (Issue #2): the ``_detect_polygon_on_burst`` helper must
preserve the real aquarium shape (N-vertex mask polygon) when the underlying
YOLO model is a segmentation model AND the ``preserve_real_shape`` flag is
set. Otherwise the historical 4-corner bbox fallback is kept.

Etapa 3 (Issue #3): ``run_live_calibration`` must read the ``source`` field
returned by ``PreviewPolygonDialog`` and persist it on
``_last_polygon_source`` so downstream consumers (the live recording
session coordinator) know whether the polygon was auto-detected or
manually adjusted by the user before approval.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

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


# ---------------------------------------------------------------------------
# Etapa 3 — polygon source persistence (auto vs manual)
# ---------------------------------------------------------------------------


def _make_calibration_coordinator_with_camera() -> LiveCalibrationCoordinator:
    """Build a coordinator wired with mocks that satisfy run_live_calibration."""
    state_manager = MagicMock()
    project_manager = MagicMock()
    project_manager.project_data = {}
    project_manager.project_path = "/tmp/zebtrack_project"
    weight_manager = MagicMock()
    weight_manager.get_weight_path_by_method.return_value = "fake_weights.pt"

    settings_obj = MagicMock()
    settings_obj.camera = SimpleNamespace(index=0)
    settings_obj.yolo_model = SimpleNamespace(confidence_threshold=0.05)
    settings_obj.model_selection = SimpleNamespace(aquarium_method="det")

    coordinator = LiveCalibrationCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        detector_service=MagicMock(),
        weight_manager=weight_manager,
        settings_obj=settings_obj,
        event_bus=MagicMock(),
        root=MagicMock(),
        view=None,
    )
    return coordinator


def _run_live_calibration_with_dialog_source(dialog_source: str | None) -> str | None:
    """Drive ``run_live_calibration`` with a stubbed PreviewPolygonDialog."""
    coordinator = _make_calibration_coordinator_with_camera()

    # Stub the camera so we get N frames out of it.
    fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    fake_camera = MagicMock()
    fake_camera.is_open = True
    fake_camera.get_frame.return_value = (True, fake_frame)

    # Stub _detect_polygon_on_burst to return a deterministic polygon (skips
    # the entire YOLO predict path, including model.predict).
    fake_polygon = [[100, 100], [200, 100], [200, 200], [100, 200]]

    dialog_result: dict = {"approved": True, "polygon": fake_polygon, "frame": None}
    if dialog_source is not None:
        dialog_result["source"] = dialog_source

    fake_dialog_instance = MagicMock()
    fake_dialog_instance.show.return_value = dialog_result

    with (
        patch.object(
            LiveCalibrationCoordinator,
            "_detect_polygon_on_burst",
            return_value=[fake_polygon],
        ),
        patch(
            "zebtrack.coordinators.live_calibration_coordinator.AquariumDetector"
        ) as fake_detector_cls,
        patch(
            "zebtrack.coordinators.live_calibration_coordinator.Camera",
            return_value=fake_camera,
        ),
        patch(
            "zebtrack.coordinators.live_calibration_coordinator.cv2.imwrite",
            return_value=True,
        ),
        patch(
            "zebtrack.ui.dialogs.preview_polygon_dialog.PreviewPolygonDialog",
            return_value=fake_dialog_instance,
        ),
        patch(
            "zebtrack.coordinators.live_calibration_coordinator.time.sleep",
            return_value=None,
        ),
    ):
        fake_detector_cls.return_value = MagicMock()
        success = coordinator.run_live_calibration(stabilization_frames=4, show_preview=True)

    assert success is True, "calibration should succeed when dialog approves"
    return coordinator.last_polygon_source


def test_run_live_calibration_persists_manual_source_from_dialog():
    """Dialog reporting source='manual' must set last_polygon_source='manual'."""
    assert _run_live_calibration_with_dialog_source("manual") == "manual"


def test_run_live_calibration_persists_auto_source_from_dialog():
    """Dialog reporting source='auto' must set last_polygon_source='auto'."""
    assert _run_live_calibration_with_dialog_source("auto") == "auto"


def test_run_live_calibration_defaults_to_auto_when_dialog_omits_source():
    """Legacy dialogs without ``source`` default to 'auto' (back-compat)."""
    assert _run_live_calibration_with_dialog_source(None) == "auto"


# ---------------------------------------------------------------------------
# Etapa 4 — LIVE_POLYGON_SOURCE_CHANGED event publishing
# ---------------------------------------------------------------------------


def _last_polygon_source_event_sources(event_bus_mock: MagicMock) -> list[str | None]:
    """Extract the ``source`` field from every LIVE_POLYGON_SOURCE_CHANGED publish."""
    from zebtrack.ui.event_bus_v2 import UIEvents

    sources: list[str | None] = []
    for call in event_bus_mock.publish.call_args_list:
        event = call.args[0]
        if getattr(event, "type", None) is UIEvents.LIVE_POLYGON_SOURCE_CHANGED:
            sources.append(getattr(event.data, "source", "__missing__"))
    return sources


def test_set_last_polygon_source_publishes_event_with_value():
    """Setting the polygon source must publish LIVE_POLYGON_SOURCE_CHANGED(source=...)."""
    coordinator = _make_coordinator()
    bus = cast(MagicMock, coordinator.event_bus)
    bus.reset_mock()

    coordinator._set_last_polygon_source("auto")

    assert coordinator.last_polygon_source == "auto"
    sources = _last_polygon_source_event_sources(bus)
    assert sources == ["auto"], f"expected one auto-event, got {sources}"


def test_clear_last_polygon_source_publishes_none():
    """clear_last_polygon_source must publish source=None for badge reset."""
    coordinator = _make_coordinator()
    bus = cast(MagicMock, coordinator.event_bus)
    bus.reset_mock()

    coordinator.clear_last_polygon_source()

    assert coordinator.last_polygon_source is None
    sources = _last_polygon_source_event_sources(bus)
    assert sources == [None]


def test_run_live_calibration_publishes_polygon_source_event():
    """The full run_live_calibration flow must emit the event when persisting."""
    from zebtrack.ui.event_bus_v2 import UIEvents

    coordinator = _make_calibration_coordinator_with_camera()
    bus = cast(MagicMock, coordinator.event_bus)
    bus.reset_mock()

    fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    fake_camera = MagicMock()
    fake_camera.is_open = True
    fake_camera.get_frame.return_value = (True, fake_frame)
    fake_polygon = [[100, 100], [200, 100], [200, 200], [100, 200]]
    fake_dialog_instance = MagicMock()
    fake_dialog_instance.show.return_value = {
        "approved": True,
        "polygon": fake_polygon,
        "frame": None,
        "source": "manual",
    }

    with (
        patch.object(
            LiveCalibrationCoordinator,
            "_detect_polygon_on_burst",
            return_value=[fake_polygon],
        ),
        patch(
            "zebtrack.coordinators.live_calibration_coordinator.AquariumDetector"
        ) as fake_detector_cls,
        patch(
            "zebtrack.coordinators.live_calibration_coordinator.Camera",
            return_value=fake_camera,
        ),
        patch(
            "zebtrack.coordinators.live_calibration_coordinator.cv2.imwrite",
            return_value=True,
        ),
        patch(
            "zebtrack.ui.dialogs.preview_polygon_dialog.PreviewPolygonDialog",
            return_value=fake_dialog_instance,
        ),
        patch(
            "zebtrack.coordinators.live_calibration_coordinator.time.sleep",
            return_value=None,
        ),
    ):
        fake_detector_cls.return_value = MagicMock()
        assert coordinator.run_live_calibration(stabilization_frames=4, show_preview=True)

    events = [
        call.args[0]
        for call in bus.publish.call_args_list
        if getattr(call.args[0], "type", None) is UIEvents.LIVE_POLYGON_SOURCE_CHANGED
    ]
    assert events, "LIVE_POLYGON_SOURCE_CHANGED must be emitted at least once"
    assert events[-1].data.source == "manual"


def test_set_last_polygon_source_swallows_publish_failures():
    """A bus that raises must not propagate — calibration must keep running."""
    coordinator = _make_coordinator()
    bus = cast(MagicMock, coordinator.event_bus)
    bus.publish.side_effect = RuntimeError("bus is on fire")

    # Must not raise
    coordinator._set_last_polygon_source("auto")
    assert coordinator.last_polygon_source == "auto"
