"""Integration tests for the live per-zone Arduino dispatch hook.

Exercises ``FrameProcessingMixin``'s Arduino glue in isolation by subclassing
the mixin with the minimal attributes its Arduino methods touch.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import numpy as np

from zebtrack.core.recording.frame_processing_pipeline import FrameProcessingMixin

SQUARE_A = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.int32)
SQUARE_B = np.array([[100, 100], [110, 100], [110, 110], [100, 110]], dtype=np.int32)


class FakeManager:
    def __init__(self, connected: bool = True) -> None:
        self._connected = connected
        self.sent: list[int] = []

    def is_connected(self) -> bool:
        return self._connected

    def enqueue(self, token: int) -> bool:
        self.sent.append(token)
        return True


class FakeDetector:
    def __init__(self, names, polygons) -> None:
        self.roi_names = names
        self.scaled_roi_polygons = polygons


class _Harness(FrameProcessingMixin):
    """Minimal carrier exposing only what the Arduino methods need."""

    def __init__(self, project_data, manager, detector) -> None:
        self.controller = cast(Any, SimpleNamespace(arduino_manager=manager))
        self.project_manager = cast(Any, SimpleNamespace(project_data=project_data))
        self.detector_service = cast(Any, SimpleNamespace(detector=detector))


def _bbox_at(cx, cy, half=2):
    # detection tuple: (x1, y1, x2, y2, conf, track_id, class_id)
    return (cx - half, cy - half, cx + half, cy + half, 0.9, 1, 0)


def _make(project_data, *, connected=True, detector=None):
    manager = FakeManager(connected=connected)
    if detector is None:
        detector = FakeDetector(["A", "B"], [SQUARE_A, SQUARE_B])
    return _Harness(project_data, manager, detector), manager


PROJECT_WITH_BINDINGS = {
    "use_arduino": True,
    "arduino_bindings": [
        {"roi": "A", "on_enter": 1, "on_exit": 2},
        {"roi": "B", "on_enter": 3, "on_exit": 4},
    ],
}


def test_enter_then_exit_emits_tokens():
    h, mgr = _make(PROJECT_WITH_BINDINGS)
    h._reset_arduino_zone_state()
    assert h._arduino_zone_enabled is True

    # Animal enters A
    h._dispatch_arduino_zone_commands([_bbox_at(5, 5)])
    assert mgr.sent == [1]

    # Stays in A -> no new token
    h._dispatch_arduino_zone_commands([_bbox_at(6, 6)])
    assert mgr.sent == [1]

    # Leaves the arena entirely -> exit A
    h._dispatch_arduino_zone_commands([_bbox_at(50, 50)])
    assert mgr.sent == [1, 2]


def test_move_between_rois():
    h, mgr = _make(PROJECT_WITH_BINDINGS)
    h._reset_arduino_zone_state()
    h._dispatch_arduino_zone_commands([_bbox_at(5, 5)])  # enter A -> 1
    h._dispatch_arduino_zone_commands([_bbox_at(105, 105)])  # A->B: exit 2, enter 3
    assert mgr.sent == [1, 2, 3]


def test_session_end_sweep_emits_exit_tokens():
    h, mgr = _make(PROJECT_WITH_BINDINGS)
    h._reset_arduino_zone_state()
    h._dispatch_arduino_zone_commands([_bbox_at(5, 5)])
    mgr.sent.clear()
    h._arduino_zone_session_end_sweep()
    assert mgr.sent == [2, 4]


def test_disabled_when_use_arduino_false():
    pd = {"use_arduino": False, "arduino_bindings": PROJECT_WITH_BINDINGS["arduino_bindings"]}
    h, mgr = _make(pd)
    h._reset_arduino_zone_state()
    assert h._arduino_zone_enabled is False
    h._dispatch_arduino_zone_commands([_bbox_at(5, 5)])
    assert mgr.sent == []


def test_disabled_when_no_bindings():
    h, mgr = _make({"use_arduino": True})
    h._reset_arduino_zone_state()
    assert h._arduino_zone_enabled is False
    h._dispatch_arduino_zone_commands([_bbox_at(5, 5)])
    assert mgr.sent == []


def test_no_dispatch_when_disconnected():
    h, mgr = _make(PROJECT_WITH_BINDINGS, connected=False)
    h._reset_arduino_zone_state()
    h._dispatch_arduino_zone_commands([_bbox_at(5, 5)])
    assert mgr.sent == []


def test_evaluator_retries_until_detector_rois_ready():
    # Detector has no ROI polygons yet -> dispatch is a no-op but stays enabled.
    empty_detector = FakeDetector([], [])
    h, mgr = _make(PROJECT_WITH_BINDINGS, detector=empty_detector)
    h._reset_arduino_zone_state()
    h._dispatch_arduino_zone_commands([_bbox_at(5, 5)])
    assert mgr.sent == []
    assert h._arduino_evaluator is None  # not built yet

    # ROIs become available later -> evaluator builds and tokens flow.
    h.detector_service.detector = FakeDetector(["A", "B"], [SQUARE_A, SQUARE_B])
    h._dispatch_arduino_zone_commands([_bbox_at(5, 5)])
    assert mgr.sent == [1]
