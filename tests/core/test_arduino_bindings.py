"""Tests for the Arduino per-zone binding config (parsing/serialization)."""

from __future__ import annotations

import pytest

from zebtrack.core.services.arduino_bindings import (
    ArduinoBinding,
    ArduinoBindingConfig,
)


def test_from_project_data_list_form():
    pd = {
        "arduino_bindings": [
            {"roi": "Direita", "on_enter": 1, "on_exit": 2},
            {"roi": "Esquerda", "on_enter": 3, "on_exit": 4},
        ]
    }
    cfg = ArduinoBindingConfig.from_project_data(pd)
    assert [b.roi for b in cfg.bindings] == ["Direita", "Esquerda"]
    assert cfg.bindings[0].on_enter == 1
    assert cfg.bindings[1].on_exit == 4


def test_from_project_data_dict_wrapper_form():
    pd = {"arduino_bindings": {"bindings": [{"roi": "A", "on_enter": 7}]}}
    cfg = ArduinoBindingConfig.from_project_data(pd)
    assert len(cfg.bindings) == 1
    assert cfg.bindings[0].roi == "A"
    assert cfg.bindings[0].on_enter == 7
    assert cfg.bindings[0].on_exit is None


def test_from_project_data_missing_or_empty():
    assert ArduinoBindingConfig.from_project_data(None).is_empty()
    assert ArduinoBindingConfig.from_project_data({}).is_empty()
    assert ArduinoBindingConfig.from_project_data({"arduino_bindings": None}).is_empty()


def test_from_project_data_skips_invalid_entries():
    pd = {
        "arduino_bindings": [
            {"roi": "Good", "on_enter": 1},
            {"on_enter": 9},  # missing roi -> dropped
            {"roi": "", "on_enter": 2},  # empty roi -> dropped
            "garbage",  # not a dict -> dropped
        ]
    }
    cfg = ArduinoBindingConfig.from_project_data(pd)
    assert [b.roi for b in cfg.bindings] == ["Good"]


def test_session_end_tokens_dedup_and_order():
    cfg = ArduinoBindingConfig(
        bindings=[
            ArduinoBinding(roi="A", on_enter=1, on_exit=2),
            ArduinoBinding(roi="B", on_enter=3, on_exit=2),  # duplicate exit token
            ArduinoBinding(roi="C", on_enter=5, on_exit=6),
            ArduinoBinding(roi="D", on_enter=7),  # no exit -> not in sweep
        ]
    )
    assert cfg.session_end_tokens() == [2, 6]


def test_roi_names_dedup_preserves_order():
    cfg = ArduinoBindingConfig(
        bindings=[
            ArduinoBinding(roi="A", on_enter=1),
            ArduinoBinding(roi="B", on_enter=2),
            ArduinoBinding(roi="A", on_exit=3),
        ]
    )
    assert cfg.roi_names() == ["A", "B"]


def test_to_storage_roundtrip():
    cfg = ArduinoBindingConfig(bindings=[ArduinoBinding(roi="A", on_enter=1, on_exit=2)])
    stored = cfg.to_storage()
    # ``label`` is persisted alongside the tokens, like on_enter/on_exit, so an
    # absent one round-trips as an explicit null rather than a missing key.
    assert stored == [{"roi": "A", "on_enter": 1, "on_exit": 2, "label": None}]
    again = ArduinoBindingConfig.from_project_data({"arduino_bindings": stored})
    assert again.bindings == cfg.bindings


def test_label_roundtrips():
    cfg = ArduinoBindingConfig(
        bindings=[ArduinoBinding(roi="Z1", on_enter=1, on_exit=2, label="Choque")]
    )
    stored = cfg.to_storage()
    assert stored[0]["label"] == "Choque"
    again = ArduinoBindingConfig.from_project_data({"arduino_bindings": stored})
    assert again.bindings[0].label == "Choque"


def test_legacy_bindings_without_label_still_load():
    """Projects created before the label field must keep working."""
    pd = {"arduino_bindings": [{"roi": "Z1", "on_enter": 1, "on_exit": 2}]}
    cfg = ArduinoBindingConfig.from_project_data(pd)
    assert cfg.bindings[0].label is None
    assert cfg.bindings[0].display_name() == "Z1"


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_blank_label_normalizes_to_none(blank):
    """The entry widget yields '' when cleared; that must not become a label."""
    binding = ArduinoBinding(roi="Z1", on_enter=1, label=blank)
    assert binding.label is None
    assert binding.display_name() == "Z1"


def test_display_name_prefers_the_label():
    binding = ArduinoBinding(roi="Z1", on_enter=1, label="Bomba")
    assert binding.display_name() == "Bomba"


def test_negative_token_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ArduinoBinding(roi="A", on_enter=-1)


def test_token_conflicts_empty_for_disjoint_pairs():
    """The canonical 4-zone layout (1/2, 3/4, 5/6, 7/8) has no ambiguity."""
    cfg = ArduinoBindingConfig(
        bindings=[
            ArduinoBinding(roi="Z1", on_enter=1, on_exit=2),
            ArduinoBinding(roi="Z2", on_enter=3, on_exit=4),
            ArduinoBinding(roi="Z3", on_enter=5, on_exit=6),
            ArduinoBinding(roi="Z4", on_enter=7, on_exit=8),
        ]
    )
    assert cfg.token_conflicts() == []


def test_token_conflicts_detects_off_by_one_layout():
    """Regression: the 2026-08-04 live session that latched a LED on.

    ``Z3`` was filled as 4/5 instead of 5/6, so token 4 was Z2's "off" and Z3's
    "enter", and token 5 was Z3's "exit" and Z4's "enter" — the exit of Z3 turned
    Z4's device ON and nothing ever cleared it.
    """
    cfg = ArduinoBindingConfig(
        bindings=[
            ArduinoBinding(roi="Z1", on_enter=1, on_exit=2),
            ArduinoBinding(roi="Z2", on_enter=3, on_exit=4),
            ArduinoBinding(roi="Z3", on_enter=4, on_exit=5),
            ArduinoBinding(roi="Z4", on_enter=5, on_exit=6),
        ]
    )
    conflicts = cfg.token_conflicts()
    assert [c.token for c in conflicts] == [4, 5]
    assert conflicts[0].enter_rois == ["Z3"]
    assert conflicts[0].exit_rois == ["Z2"]
    assert conflicts[1].enter_rois == ["Z4"]
    assert conflicts[1].exit_rois == ["Z3"]
    # The sweep still emits every exit token — including the one that turns a
    # device on. Detecting it is the panel's/log's job, not a silent drop.
    assert cfg.session_end_tokens() == [2, 4, 5, 6]


def test_token_conflict_describe_names_both_sides():
    cfg = ArduinoBindingConfig(
        bindings=[
            ArduinoBinding(roi="A", on_exit=9),
            ArduinoBinding(roi="B", on_enter=9),
        ]
    )
    (conflict,) = cfg.token_conflicts()
    text = conflict.describe()
    assert "9" in text
    assert "A" in text
    assert "B" in text


def test_token_conflicts_ignores_same_token_on_same_edge():
    """Two ROIs driving the same device on enter is unusual but unambiguous."""
    cfg = ArduinoBindingConfig(
        bindings=[
            ArduinoBinding(roi="A", on_enter=1, on_exit=2),
            ArduinoBinding(roi="B", on_enter=1, on_exit=2),
        ]
    )
    assert cfg.token_conflicts() == []
