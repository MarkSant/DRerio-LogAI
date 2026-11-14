"""Tests for ArduinoEventMapper (edge-triggered ROI transition -> tokens)."""

from __future__ import annotations

from zebtrack.core.services.arduino_bindings import ArduinoBinding
from zebtrack.core.services.arduino_event_mapper import ArduinoEventMapper, RoiTokenEvent

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


def test_update_detailed_reports_roi_and_edge():
    m = ArduinoEventMapper(BINDINGS)
    assert m.update_detailed({"A"}) == [RoiTokenEvent(roi="A", edge="enter", token=1)]
    assert m.update_detailed(set()) == [RoiTokenEvent(roi="A", edge="exit", token=2)]


def test_update_detailed_exit_before_enter_on_move():
    m = ArduinoEventMapper(BINDINGS)
    m.update_detailed({"A"})
    # A -> B in one frame: exit A before enter B, edges attributed correctly.
    assert m.update_detailed({"B"}) == [
        RoiTokenEvent(roi="A", edge="exit", token=2),
        RoiTokenEvent(roi="B", edge="enter", token=3),
    ]


def test_update_and_update_detailed_agree_on_tokens():
    m1 = ArduinoEventMapper(BINDINGS)
    m2 = ArduinoEventMapper(BINDINGS)
    assert m1.update({"B", "A"}) == [e.token for e in m2.update_detailed({"B", "A"})]


# -- #656: per-aquarium occupancy ---------------------------------------------

SCOPED = [
    ArduinoBinding(roi="A", on_enter=1, on_exit=2, aquarium_id=0),
    ArduinoBinding(roi="A", on_enter=11, on_exit=12, aquarium_id=1),
]


def test_scoped_bindings_on_the_same_roi_name_do_not_collide():
    """Keyed by ``(aquarium, roi)``: the second "A" no longer replaces the first."""
    m = ArduinoEventMapper(SCOPED)
    assert m.update_scoped({1: {"A"}}) == [
        RoiTokenEvent(roi="A", edge="enter", token=11, aquarium_id=1)
    ]
    assert m.update_scoped({0: {"A"}, 1: {"A"}}) == [
        RoiTokenEvent(roi="A", edge="enter", token=1, aquarium_id=0)
    ]
    assert [e.token for e in m.update_scoped({0: set(), 1: {"A"}})] == [2]


def test_unscoped_binding_is_occupied_while_any_aquarium_occupies_it():
    m = ArduinoEventMapper([ArduinoBinding(roi="A", on_enter=1, on_exit=2)])
    assert [e.token for e in m.update_scoped({0: {"A"}})] == [1]
    assert m.update_scoped({0: {"A"}, 1: {"A"}}) == []
    assert m.update_scoped({0: set(), 1: {"A"}}) == []  # aquarium 1 still inside
    assert [e.token for e in m.update_scoped({0: set(), 1: set()})] == [2]


def test_scoped_binding_ignores_the_other_aquarium():
    m = ArduinoEventMapper([ArduinoBinding(roi="A", on_enter=1, on_exit=2, aquarium_id=1)])
    assert m.update_scoped({0: {"A"}}) == []


def test_single_aquarium_occupancy_is_aquarium_zero():
    m = ArduinoEventMapper(SCOPED)
    assert m.update({"A"}) == [1]


def test_forget_aquarium_drops_its_state_without_tokens():
    m = ArduinoEventMapper([*SCOPED, ArduinoBinding(roi="B", on_enter=5, on_exit=6)])
    m.update_scoped({0: {"A", "B"}, 1: {"A"}})
    m.forget_aquarium(0)
    # Aquarium 0's "A" was forgotten (swept by the caller): no exit for it.
    # The unscoped "B" is not aquarium 0's alone, so it is kept.
    assert [e.token for e in m.update_scoped({1: {"A"}})] == [6]
