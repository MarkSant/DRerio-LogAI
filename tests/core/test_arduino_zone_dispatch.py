"""Integration tests for the live per-zone Arduino dispatch hook.

Exercises ``FrameProcessingMixin``'s Arduino glue in isolation by subclassing
the mixin with the minimal attributes its Arduino methods touch.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import numpy as np

from zebtrack.core.recording import frame_processing_pipeline as pipeline_module
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


def _conflict_warnings(mock_log):
    """Warning calls whose event name is the token-conflict one."""
    return [
        call
        for call in mock_log.warning.call_args_list
        if call.args and str(call.args[0]).endswith("arduino_zone_commands.token_conflict")
    ]


def test_conflicting_tokens_warn_at_session_start():
    """Regression: the off-by-one layout that latched a LED on must not start silently.

    Token 2 is A's exit and B's enter — the firmware cannot both set and clear a
    state with one command, and the session-end sweep (built from the exit
    tokens) would turn B's device on. The app only transports integers, so it
    warns; it must NOT refuse to start the session.
    """
    project_data = {
        "use_arduino": True,
        "arduino_bindings": [
            {"roi": "A", "on_enter": 1, "on_exit": 2},
            {"roi": "B", "on_enter": 2, "on_exit": 3},
        ],
    }
    h, _mgr = _make(project_data)

    with patch.object(pipeline_module, "log") as mock_log:
        h._reset_arduino_zone_state()

    assert h._arduino_zone_enabled is True
    warnings = _conflict_warnings(mock_log)
    assert warnings, "conflicting bindings must raise a warning"
    described = warnings[0].kwargs["conflicts"]
    assert any("token 2" in text for text in described)


def test_unambiguous_tokens_do_not_warn():
    h, _mgr = _make(PROJECT_WITH_BINDINGS)

    with patch.object(pipeline_module, "log") as mock_log:
        h._reset_arduino_zone_state()

    assert not _conflict_warnings(mock_log)


def _ack_inverted_warnings(mock_log):
    return [
        call
        for call in mock_log.warning.call_args_list
        if call.args and str(call.args[0]).endswith("arduino_zone_commands.ack_inverted")
    ]


def _sample(harness, *, roi, edge, token, ack):
    """Feed one latency sample through the pipeline's sink, as the reader would."""
    harness._on_arduino_latency_sample({"roi": roi, "edge": edge, "token": token}, 1.0, 1.02, ack)


def test_enter_answered_with_off_warns_once():
    """Regression: Z4 enter answered 'Blue LED OFF' — the binding is inverted.

    The firmware's own reply is the evidence; the app cannot know token semantics
    on its own. A ROI is crossed many times per session, so the warning must not
    repeat for the same (roi, edge).
    """
    h, _mgr = _make(PROJECT_WITH_BINDINGS)
    h._reset_arduino_zone_state()
    h._closed_loop_log = None

    with patch.object(pipeline_module, "log") as mock_log:
        for _ in range(5):
            _sample(h, roi="Z4", edge="enter", token=4, ack="Blue LED OFF")

    warnings = _ack_inverted_warnings(mock_log)
    assert len(warnings) == 1
    assert warnings[0].kwargs["roi"] == "Z4"
    assert warnings[0].kwargs["ack_text"] == "Blue LED OFF"


def test_exit_answered_with_on_warns():
    h, _mgr = _make(PROJECT_WITH_BINDINGS)
    h._reset_arduino_zone_state()
    h._closed_loop_log = None

    with patch.object(pipeline_module, "log") as mock_log:
        _sample(h, roi="Z1", edge="exit", token=5, ack="Green LED ON")

    assert len(_ack_inverted_warnings(mock_log)) == 1


def test_distinct_rois_each_warn():
    h, _mgr = _make(PROJECT_WITH_BINDINGS)
    h._reset_arduino_zone_state()
    h._closed_loop_log = None

    with patch.object(pipeline_module, "log") as mock_log:
        _sample(h, roi="Z2", edge="enter", token=2, ack="Red LED 1 OFF")
        _sample(h, roi="Z4", edge="enter", token=4, ack="Blue LED OFF")

    assert len(_ack_inverted_warnings(mock_log)) == 2


def test_correct_pairing_never_warns():
    """The layout verified live on 2026-08-04: every enter ON, every exit OFF."""
    h, _mgr = _make(PROJECT_WITH_BINDINGS)
    h._reset_arduino_zone_state()
    h._closed_loop_log = None

    with patch.object(pipeline_module, "log") as mock_log:
        _sample(h, roi="Z2", edge="enter", token=3, ack="Blue LED ON")
        _sample(h, roi="Z2", edge="exit", token=4, ack="Blue LED OFF")
        _sample(h, roi="Z4", edge="enter", token=7, ack="Red LED 2 ON")
        _sample(h, roi="Z4", edge="exit", token=8, ack="Red LED 2 OFF")

    assert not _ack_inverted_warnings(mock_log)


def test_unclassifiable_ack_never_warns():
    h, _mgr = _make(PROJECT_WITH_BINDINGS)
    h._reset_arduino_zone_state()
    h._closed_loop_log = None

    with patch.object(pipeline_module, "log") as mock_log:
        _sample(h, roi="Z1", edge="enter", token=1, ack="Unknown command")
        _sample(h, roi="Z1", edge="exit", token=2, ack=None)

    assert not _ack_inverted_warnings(mock_log)


def test_sample_still_reaches_the_closed_loop_log():
    """Wrapping the sink must not stop the latency row from being written."""
    rows = []
    h, _mgr = _make(PROJECT_WITH_BINDINGS)
    h._reset_arduino_zone_state()
    h._closed_loop_log = cast(Any, SimpleNamespace(on_sample=lambda *args: rows.append(args)))

    _sample(h, roi="Z4", edge="enter", token=4, ack="Blue LED OFF")

    assert len(rows) == 1
    assert rows[0][3] == "Blue LED OFF"


def test_empty_frame_within_grace_does_not_emit_exit():
    """Regression: a tracker miss used to fire exit + re-enter (device flicker).

    The 2026-08-04 live session logged a Z3 exit at frame 1980 and a Z3 enter at
    frame 2020 while the animal never left — the detector simply dropped a few
    low-confidence frames.
    """
    h, mgr = _make(PROJECT_WITH_BINDINGS)
    h._reset_arduino_zone_state()
    h._dispatch_arduino_zone_commands([_bbox_at(5, 5)])
    assert mgr.sent == [1]

    # Two empty frames are absorbed (default grace = 2).
    h._dispatch_arduino_zone_commands([])
    h._dispatch_arduino_zone_commands([])
    assert mgr.sent == [1]

    # Detection returns inside the same ROI -> still no spurious transition.
    h._dispatch_arduino_zone_commands([_bbox_at(6, 6)])
    assert mgr.sent == [1]


def test_exit_emitted_once_grace_is_exhausted():
    h, mgr = _make(PROJECT_WITH_BINDINGS)
    h._reset_arduino_zone_state()
    h._dispatch_arduino_zone_commands([_bbox_at(5, 5)])
    for _ in range(2):
        h._dispatch_arduino_zone_commands([])
    assert mgr.sent == [1]

    # Third consecutive empty frame exceeds the grace -> the animal is gone.
    h._dispatch_arduino_zone_commands([])
    assert mgr.sent == [1, 2]


def test_grace_counter_resets_between_misses():
    """Isolated misses must not accumulate into a false exit."""
    h, mgr = _make(PROJECT_WITH_BINDINGS)
    h._reset_arduino_zone_state()
    h._dispatch_arduino_zone_commands([_bbox_at(5, 5)])
    for _ in range(5):
        h._dispatch_arduino_zone_commands([])
        h._dispatch_arduino_zone_commands([_bbox_at(5, 5)])
    assert mgr.sent == [1]


def test_grace_zero_restores_immediate_exit():
    h, mgr = _make(PROJECT_WITH_BINDINGS)
    h.settings = cast(Any, SimpleNamespace(arduino=SimpleNamespace(roi_exit_grace_frames=0)))
    h._reset_arduino_zone_state()
    h._dispatch_arduino_zone_commands([_bbox_at(5, 5)])
    h._dispatch_arduino_zone_commands([])
    assert mgr.sent == [1, 2]


def test_grace_read_from_settings():
    h, mgr = _make(PROJECT_WITH_BINDINGS)
    h.settings = cast(Any, SimpleNamespace(arduino=SimpleNamespace(roi_exit_grace_frames=4)))
    h._reset_arduino_zone_state()
    h._dispatch_arduino_zone_commands([_bbox_at(5, 5)])
    for _ in range(4):
        h._dispatch_arduino_zone_commands([])
    assert mgr.sent == [1]
    h._dispatch_arduino_zone_commands([])
    assert mgr.sent == [1, 2]


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
