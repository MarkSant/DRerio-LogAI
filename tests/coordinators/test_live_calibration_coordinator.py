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
from typing import Any, cast
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


# ---------------------------------------------------------------------------
# Bug fix — UI_DISPLAY_VIDEO_FRAME after approved auto-detection
# ---------------------------------------------------------------------------


def test_run_live_calibration_publishes_display_video_frame_on_success():
    """After the user approves the detected polygon, the zone tab must receive
    the captured reference frame via ``UI_DISPLAY_VIDEO_FRAME``. Without this,
    the canvas paints the polygon over a blank white background instead of
    over the actual camera image.
    """
    from zebtrack.ui.event_bus_v2 import UIEvents
    from zebtrack.ui.payloads import VideoPathPayload

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
        "source": "auto",
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

    display_events = [
        call.args[0]
        for call in bus.publish.call_args_list
        if getattr(call.args[0], "type", None) is UIEvents.UI_DISPLAY_VIDEO_FRAME
    ]
    assert display_events, (
        "approved auto-detect must publish UI_DISPLAY_VIDEO_FRAME so the zone "
        "tab paints the polygon over the camera frame instead of a white canvas"
    )

    # The payload must carry the reference frame path so display_roi_video_frame
    # can load it via Image.open.
    last_payload = display_events[-1].data
    assert isinstance(last_payload, VideoPathPayload)
    assert last_payload.video_path.endswith("live_camera_reference_frame.png")


# ---------------------------------------------------------------------------
# Bug fix — camera leak on cancellation + cancel-vs-failure distinction
# ---------------------------------------------------------------------------


def _run_live_calibration_with_dialog_result(dialog_result: dict | None):
    """Drive run_live_calibration end-to-end with a stubbed dialog return value.

    Returns ``(coordinator, success, fake_camera)`` so individual tests can
    assert on coordinator state, the bool return, and whether the camera was
    released (``self.camera`` set to None + ``_stopped.set()`` called).
    """
    coordinator = _make_calibration_coordinator_with_camera()

    fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    fake_camera = MagicMock()
    fake_camera.is_open = True
    fake_camera.get_frame.return_value = (True, fake_frame)
    # Track shutdown signal calls — the helper must always call this BEFORE release.
    stopped_event = MagicMock()
    stopped_event.set = MagicMock()
    fake_camera._stopped = stopped_event

    fake_polygon = [[100, 100], [200, 100], [200, 200], [100, 200]]

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

    return coordinator, success, fake_camera


def test_run_live_calibration_releases_camera_when_dialog_rejected():
    """Bug: closing/cancelling the preview dialog left ``self.camera`` alive,
    so the Camera background thread kept spamming frame_read.failed and
    disconnected warnings until app shutdown. The fix releases the camera in
    the user-rejected branch via ``_release_calibration_camera``.
    """
    coordinator, success, fake_camera = _run_live_calibration_with_dialog_result(
        {"approved": False}
    )

    assert success is False
    assert coordinator.camera is None, "rejected dialog must drop self.camera"
    # Shutdown signal must fire BEFORE release so the background thread does
    # not race to reconnect against a torn-down device.
    fake_camera._stopped.set.assert_called()
    fake_camera.release.assert_called()


def test_run_live_calibration_releases_camera_when_dialog_closed_via_X():
    """Closing the preview window via the X button returns ``None`` (no
    ``approved`` key set). Must hit the same release path as explicit cancel.
    """
    coordinator, success, fake_camera = _run_live_calibration_with_dialog_result(None)

    assert success is False
    assert coordinator.camera is None
    fake_camera._stopped.set.assert_called()
    fake_camera.release.assert_called()


def test_run_live_calibration_marks_cancellation_flag_on_reject():
    """``_last_calibration_cancelled`` must be True after a rejected dialog so
    the caller can distinguish "user cancelled" from "detection failed"."""
    coordinator, success, _ = _run_live_calibration_with_dialog_result({"approved": False})

    assert success is False
    assert coordinator._last_calibration_cancelled is True


def test_run_live_calibration_clears_cancellation_flag_on_success():
    """The flag must reset between runs so a prior cancel doesn't poison the
    next attempt."""
    # First run: cancel
    coordinator, _, _ = _run_live_calibration_with_dialog_result({"approved": False})
    assert coordinator._last_calibration_cancelled is True

    # Second run: approved → flag must reset to False
    fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    fake_camera = MagicMock()
    fake_camera.is_open = True
    fake_camera.get_frame.return_value = (True, fake_frame)
    fake_camera._stopped = MagicMock()
    fake_polygon = [[100, 100], [200, 100], [200, 200], [100, 200]]
    fake_dialog = MagicMock()
    fake_dialog.show.return_value = {
        "approved": True,
        "polygon": fake_polygon,
        "frame": None,
        "source": "auto",
    }

    with (
        patch.object(
            LiveCalibrationCoordinator,
            "_detect_polygon_on_burst",
            return_value=[fake_polygon],
        ),
        patch("zebtrack.coordinators.live_calibration_coordinator.AquariumDetector"),
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
            return_value=fake_dialog,
        ),
        patch(
            "zebtrack.coordinators.live_calibration_coordinator.time.sleep",
            return_value=None,
        ),
    ):
        success = coordinator.run_live_calibration(stabilization_frames=4, show_preview=True)

    assert success is True
    assert coordinator._last_calibration_cancelled is False


def test_release_calibration_camera_is_idempotent_on_none():
    """Calling the helper with no camera attached must be a no-op (no AttributeError)."""
    coordinator = _make_coordinator()
    coordinator.camera = None
    # Must not raise
    coordinator._release_calibration_camera(reason="test")
    assert coordinator.camera is None


def test_release_calibration_camera_swallows_release_exceptions():
    """If the device handle is already gone, release_fn() can raise — the
    helper must swallow it so calibration shutdown stays robust."""
    coordinator = _make_coordinator()
    flaky_camera = MagicMock()
    flaky_camera._stopped = MagicMock()
    flaky_camera.release.side_effect = RuntimeError("device already released")
    coordinator.camera = flaky_camera

    # Must not raise
    coordinator._release_calibration_camera(reason="test")
    assert coordinator.camera is None
    flaky_camera._stopped.set.assert_called()


# ---------------------------------------------------------------------------
# Bug fix — auto-detect approval must refresh the zone tab so the polygon
# renders and the ROI/Concluir buttons enable.
# ---------------------------------------------------------------------------


def test_run_live_calibration_resolves_perspective_from_behavioral_config(monkeypatch):
    """``ProjectWorkflowService._persist_project_data`` stores the wizard's
    behavioral_analysis under ``project_data["behavioral_config"]``. Without
    this fix, ``run_live_calibration`` was reading
    ``project_data["calibration"]["behavioral_analysis"]`` (legacy nested
    layout) and missing the perspective for new projects — picking the
    wrong perspective-specific weight."""
    coordinator = _make_coordinator()
    coordinator.project_manager.project_data = {
        "model_selection": {"aquarium_method": "seg"},
        "behavioral_config": {"aquarium_perspective": "top_down"},
    }
    coordinator.project_manager.project_path = "/tmp"
    coordinator.weight_manager.get_weight_path_by_method.return_value = None  # type: ignore[attr-defined]

    # Stop the function early: we only care that get_weight_path_by_method
    # is called with the right perspective. Returning None makes
    # run_live_calibration bail at the no_aquarium_model branch.
    fake_camera = MagicMock()
    fake_camera.is_open = True
    fake_camera.get_frame.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
    fake_camera._stopped = MagicMock()

    with (
        patch(
            "zebtrack.coordinators.live_calibration_coordinator.Camera",
            return_value=fake_camera,
        ),
        patch(
            "zebtrack.coordinators.live_calibration_coordinator.time.sleep",
            return_value=None,
        ),
    ):
        coordinator.settings = MagicMock()
        coordinator.settings.camera = SimpleNamespace(index=0)
        coordinator.settings.yolo_model = SimpleNamespace(confidence_threshold=0.05)
        coordinator.run_live_calibration(stabilization_frames=4, show_preview=False)

    coordinator.weight_manager.get_weight_path_by_method.assert_called_once_with(  # type: ignore[attr-defined]
        method="seg", task="aquarium", perspective="top_down"
    )


def test_run_live_calibration_falls_back_to_nested_perspective(monkeypatch):
    """Legacy projects store perspective under
    ``calibration.behavioral_analysis.aquarium_perspective``. The fallback
    keeps them working after the behavioral_config migration."""
    coordinator = _make_coordinator()
    coordinator.project_manager.project_data = {
        "model_selection": {"aquarium_method": "det"},
        "calibration": {"behavioral_analysis": {"aquarium_perspective": "lateral"}},
    }
    coordinator.project_manager.project_path = "/tmp"
    coordinator.weight_manager.get_weight_path_by_method.return_value = None  # type: ignore[attr-defined]

    fake_camera = MagicMock()
    fake_camera.is_open = True
    fake_camera.get_frame.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
    fake_camera._stopped = MagicMock()

    with (
        patch(
            "zebtrack.coordinators.live_calibration_coordinator.Camera",
            return_value=fake_camera,
        ),
        patch(
            "zebtrack.coordinators.live_calibration_coordinator.time.sleep",
            return_value=None,
        ),
    ):
        coordinator.settings = MagicMock()
        coordinator.settings.camera = SimpleNamespace(index=0)
        coordinator.settings.yolo_model = SimpleNamespace(confidence_threshold=0.05)
        coordinator.run_live_calibration(stabilization_frames=4, show_preview=False)

    coordinator.weight_manager.get_weight_path_by_method.assert_called_once_with(  # type: ignore[attr-defined]
        method="det", task="aquarium", perspective="lateral"
    )


def test_run_live_calibration_saves_zones_under_reference_frame_key():
    """The polygon must be saved (in memory only, ``persist=False``) under
    the ``reference_frame_path`` key so the active-video machinery —
    triggered by UI_DISPLAY_VIDEO_FRAME → display_roi_video_frame →
    set_active_zone_video(reference_frame_path) — finds matching zones
    and does NOT reset ``project_data["detection_zones"]`` to empty.

    The original symptom: the canvas showed the reference frame but no
    polygon, and the ROI/Concluir buttons stayed disabled because the
    global zone_data had been silently cleared by set_active_zone_video.

    Audit Erro 4 (2026-05-25): the legacy ``"live_camera"`` template key
    is no longer written here — it would persist across sessions and
    show a ghost polygon on reopen. The user opts into reuse via the
    zone-tab checkbox at Concluir time; see
    ``zone_control_builder._apply_arena_template_choice``.
    """
    coordinator = _make_calibration_coordinator_with_camera()

    fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    fake_camera = MagicMock()
    fake_camera.is_open = True
    fake_camera.get_frame.return_value = (True, fake_frame)
    fake_camera._stopped = MagicMock()
    fake_polygon = [[100, 100], [200, 100], [200, 200], [100, 200]]
    fake_dialog = MagicMock()
    fake_dialog.show.return_value = {
        "approved": True,
        "polygon": fake_polygon,
        "frame": None,
        "source": "auto",
    }

    with (
        patch.object(
            LiveCalibrationCoordinator,
            "_detect_polygon_on_burst",
            return_value=[fake_polygon],
        ),
        patch("zebtrack.coordinators.live_calibration_coordinator.AquariumDetector"),
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
            return_value=fake_dialog,
        ),
        patch(
            "zebtrack.coordinators.live_calibration_coordinator.time.sleep",
            return_value=None,
        ),
    ):
        assert coordinator.run_live_calibration(stabilization_frames=4, show_preview=True)

    save_calls = coordinator.project_manager.save_zone_data.call_args_list  # type: ignore[attr-defined]
    saved_keys: list[Any] = []
    persist_flags: list[bool] = []
    for call in save_calls:
        # save_zone_data(zone_data, video_path[, persist=...]) — positional first two.
        if len(call.args) >= 2:
            saved_keys.append(call.args[1])
        elif "video_path" in call.kwargs:
            saved_keys.append(call.kwargs["video_path"])
        # ``persist`` is keyword-only on ProjectManager.save_zone_data.
        if "persist" in call.kwargs:
            persist_flags.append(bool(call.kwargs["persist"]))
        else:
            persist_flags.append(True)  # default

    # The reference frame path must be among the keys so set_active_zone_video
    # finds the in-memory polygon and preserves the global ``detection_zones``.
    assert any(
        isinstance(k, str) and k.endswith("live_camera_reference_frame.png") for k in saved_keys
    ), f"reference frame key missing from save_zone_data calls: {saved_keys}"
    # Legacy "live_camera" key MUST NOT be written by auto-detect anymore —
    # it is the source of the ghost-polygon bug fixed in audit Erro 4.
    assert "live_camera" not in saved_keys, (
        f'unexpected legacy "live_camera" save during auto-detect: {saved_keys}'
    )
    # All auto-detect saves must be ``persist=False`` (in-memory only) so a
    # cancelled session does not leak the polygon to project.json.
    assert all(not p for p in persist_flags), (
        f"auto-detect must use persist=False; got persist flags: {persist_flags}"
    )


def test_ensure_zones_auto_success_publishes_zone_list_update(monkeypatch):
    """After auto-detect succeeds inside ``ensure_zones_before_recording``,
    the auto branch must publish ``UI_UPDATE_ZONE_LIST`` so the zone tab
    redraws the polygon and the listbox/button refresh fires. Without this,
    the canvas only shows the reference frame and the ROI/Concluir buttons
    stay disabled."""
    from zebtrack.ui.event_bus_v2 import UIEvents

    coordinator = _make_coordinator()
    bus = cast(MagicMock, coordinator.event_bus)
    bus.reset_mock()

    # Force the "no recordings yet, no zones yet" branch so we land in the
    # ZoneCalibrationDialog path with method=auto.
    coordinator.project_manager.project_path = "/tmp/zebtrack"
    coordinator.project_manager.get_project_type.return_value = "live"  # type: ignore[attr-defined]
    coordinator.project_manager.get_zone_data.return_value = None  # type: ignore[attr-defined]
    monkeypatch.setattr(coordinator, "_has_recorded_before", lambda: False)

    # Stub the modal calibration dialog to return method=auto so we exercise
    # the auto branch in ensure_zones_before_recording.
    fake_calib_dialog = MagicMock()
    fake_calib_dialog.show.return_value = {"method": "auto"}
    monkeypatch.setattr(
        "zebtrack.ui.dialogs.zone_calibration_dialog.ZoneCalibrationDialog",
        MagicMock(return_value=fake_calib_dialog),
    )

    # Stub run_live_calibration to return True without touching real hardware.
    monkeypatch.setattr(coordinator, "run_live_calibration", lambda **kwargs: True)
    # Short-circuit the post-success wait so the test doesn't block.
    monkeypatch.setattr(coordinator, "_wait_for_zone_confirmation", lambda: False)

    # Need a root for the dialog flow to proceed.
    coordinator.root = MagicMock()

    coordinator.ensure_zones_before_recording()

    published_types = [getattr(call.args[0], "type", None) for call in bus.publish.call_args_list]
    assert UIEvents.UI_SELECT_TAB in published_types, "must navigate to zone tab"
    assert UIEvents.UI_UPDATE_ZONE_LIST in published_types, (
        "auto-detect approval must trigger zone-list refresh so the polygon "
        "renders and the ROI/Concluir buttons enable"
    )


def test_has_recorded_before_true_when_project_has_videos():
    """Ao reabrir um projeto com gravações registradas em disco,
    ``_has_recorded_before`` deve retornar True mesmo com ``_session_count==0``
    (zerado a cada reabertura). Sem isto, o app "esquecia" o polígono
    pré-existente e reoferecia auto-detecção em vez do diálogo de reutilização.
    """
    coordinator = _make_coordinator()
    coordinator._session_count = 0
    coordinator.project_manager.get_all_videos.return_value = [{"path": "v.mp4"}]  # type: ignore[attr-defined]

    assert coordinator._has_recorded_before() is True


def test_has_recorded_before_false_when_no_videos_and_no_session():
    """Projeto novo (sem gravações, sem sessões nesta execução) → False."""
    coordinator = _make_coordinator()
    coordinator._session_count = 0
    coordinator.project_manager.get_all_videos.return_value = []  # type: ignore[attr-defined]

    assert coordinator._has_recorded_before() is False


def test_has_recorded_before_true_when_session_count_positive():
    """Gravação feita nesta execução → True (sem nem consultar o projeto)."""
    coordinator = _make_coordinator()
    coordinator._session_count = 2
    coordinator.project_manager.get_all_videos.side_effect = AssertionError(  # type: ignore[attr-defined]
        "não deve consultar o projeto quando já há sessões nesta execução"
    )

    assert coordinator._has_recorded_before() is True


def test_ensure_zones_restores_active_zone_video_on_reopen(monkeypatch):
    """Ao reabrir, as zonas do live vivem sob a chave do reference-frame e o
    ``active_zone_video`` (em-memória) é None, então ``get_zone_data()`` vem
    vazio. O coordinator deve restaurar o active a partir do último vídeo com
    zonas para que ``has_zones`` fique True e o diálogo de Reutilizar apareça
    (em vez de re-rodar a auto-detecção)."""
    coordinator = _make_coordinator()
    coordinator.project_manager.project_path = "/tmp/zebtrack"  # type: ignore[attr-defined]
    coordinator.project_manager.get_project_type.return_value = "live"  # type: ignore[attr-defined]

    empty = SimpleNamespace(polygon=[])
    full = SimpleNamespace(polygon=[[1, 1], [2, 2], [3, 3]])
    # 1ª leitura (reopen) vazia → restaura → 2ª leitura preenchida.
    coordinator.project_manager.get_zone_data.side_effect = [empty, full, full, full]  # type: ignore[attr-defined]
    coordinator.project_manager.get_last_zone_video.return_value = "ref.png"  # type: ignore[attr-defined]
    monkeypatch.setattr(coordinator, "_has_recorded_before", lambda: True)
    coordinator.root = MagicMock()

    # Diálogo de reutilização fechado (None) → fluxo encerra sem auto-detectar.
    fake_dialog = MagicMock()
    fake_dialog.show.return_value = None
    with patch(
        "zebtrack.ui.dialogs.zone_reuse_dialog.ZoneReuseDialog",
        MagicMock(return_value=fake_dialog),
    ):
        coordinator.ensure_zones_before_recording()

    # Restaurou o active a partir do último vídeo com zonas.
    coordinator.project_manager.set_active_zone_video.assert_called_once_with("ref.png")  # type: ignore[attr-defined]
    # O diálogo de Reutilizar foi exibido (has_zones ficou True).
    fake_dialog.show.assert_called_once()


def test_ensure_zones_reuse_opens_zone_tab_and_defers(monkeypatch):
    """Ao escolher "Reutilizar", em vez de iniciar a sessão imediatamente, o
    coordinator deve abrir a aba de zonas, agendar a edição do polígono com
    todos os vértices pré-selecionados e DEFERIR o início (retornar False com
    ``pending_zone_confirmation=True``). Isso evita o erro silencioso
    "Falha ao iniciar sessão" e permite ajustar a posição do polígono na nova
    imagem antes de gravar.
    """
    from zebtrack.ui.event_bus_v2 import UIEvents

    coordinator = _make_coordinator()
    bus = cast(MagicMock, coordinator.event_bus)

    coordinator.project_manager.project_path = "/tmp/zebtrack"
    coordinator.project_manager.get_project_type.return_value = "live"  # type: ignore[attr-defined]
    zone_data = SimpleNamespace(polygon=[[10, 10], [20, 10], [20, 20], [10, 20]])
    coordinator.project_manager.get_zone_data.return_value = zone_data  # type: ignore[attr-defined]

    # Já gravou antes → dispara o diálogo de reutilização.
    monkeypatch.setattr(coordinator, "_has_recorded_before", lambda: True)
    # Não tocar hardware na captura do frame de referência.
    monkeypatch.setattr(coordinator, "_capture_reference_frame_for_zones", lambda: True)

    # Root com ``after`` real-mockado para agendar a edição deferida.
    coordinator.root = MagicMock()

    fake_dialog = MagicMock()
    fake_dialog.show.return_value = {"reuse": True}

    bus.reset_mock()
    with patch(
        "zebtrack.ui.dialogs.zone_reuse_dialog.ZoneReuseDialog",
        MagicMock(return_value=fake_dialog),
    ):
        result = coordinator.ensure_zones_before_recording()

    # Deferido: NÃO inicia a sessão agora.
    assert result is False, "reuse deve deferir (não iniciar a sessão imediatamente)"
    assert coordinator.pending_zone_confirmation is True

    published_types = [getattr(call.args[0], "type", None) for call in bus.publish.call_args_list]
    assert UIEvents.UI_SELECT_TAB in published_types, "reuse deve abrir a aba de zonas"
    # Edição do polígono é agendada via root.after (deferida ~150 ms).
    assert coordinator.root.after.called, "deve agendar POLYGON_EDIT_REQUESTED deferido"

    # O evento agendado carrega preselect_all=True.
    scheduled = coordinator.root.after.call_args
    deferred_fn = scheduled.args[1]
    bus.reset_mock()
    deferred_fn()
    edit_calls = [
        call.args[0]
        for call in bus.publish.call_args_list
        if getattr(call.args[0], "type", None) == UIEvents.POLYGON_EDIT_REQUESTED
    ]
    assert edit_calls, "edição deferida deve publicar POLYGON_EDIT_REQUESTED"
    assert edit_calls[0].data.preselect_all is True
