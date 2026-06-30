"""Tests for ArduinoEventMapper (edge-triggered ROI transition -> tokens)."""

from __future__ import annotations

from zebtrack.core.services.arduino_bindings import ArduinoBinding
from zebtrack.core.services.arduino_event_mapper import ArduinoEventMapper

BINDINGS = [
    ArduinoBinding(roi="A", on_enter=1, on_exit=2),
    ArduinoBinding(roi="B", on_enter=3, on_exit=4),
]


def test_enter_emits_enter_token():
    m = ArduinoEventMapper(BINDINGS)
    assert m.update(set()) == []
    assert m.update({"A"}) == [1]


def test_no_transition_emits_nothing():
    m = ArduinoEventMapper(BINDINGS)
    m.update({"A"})
    assert m.update({"A"}) == []  # still inside -> silent (Arduino holds state)


def test_exit_emits_exit_token():
    m = ArduinoEventMapper(BINDINGS)
    m.update({"A"})
    assert m.update(set()) == [2]


def test_move_between_rois_exits_before_enters():
    m = ArduinoEventMapper(BINDINGS)
    m.update({"A"})
    # A -> B in one frame: exit A (2) before enter B (3)
    assert m.update({"B"}) == [2, 3]


def test_unknown_roi_ignored():
    m = ArduinoEventMapper(BINDINGS)
    assert m.update({"Unmapped"}) == []


def test_binding_without_enter_token_silent_on_enter():
    m = ArduinoEventMapper([ArduinoBinding(roi="A", on_exit=2)])
    assert m.update({"A"}) == []  # no on_enter -> nothing
    assert m.update(set()) == [2]


def test_reset_clears_previous_occupancy():
    m = ArduinoEventMapper(BINDINGS)
    m.update({"A"})
    m.reset()
    # After reset, A counts as a fresh enter again.
    assert m.update({"A"}) == [1]


def test_deterministic_order_multiple_simultaneous():
    m = ArduinoEventMapper(BINDINGS)
    # Both enter same frame -> sorted by ROI name: A(1) then B(3)
    assert m.update({"B", "A"}) == [1, 3]
