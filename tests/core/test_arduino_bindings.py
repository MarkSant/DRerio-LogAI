"""Tests for the Arduino per-zone binding config (parsing/serialization)."""

from __future__ import annotations

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
    assert stored == [{"roi": "A", "on_enter": 1, "on_exit": 2}]
    again = ArduinoBindingConfig.from_project_data({"arduino_bindings": stored})
    assert again.bindings == cfg.bindings


def test_negative_token_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ArduinoBinding(roi="A", on_enter=-1)
