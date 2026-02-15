"""Tests for BehavioralConfigWidget static helpers."""

from zebtrack.ui.components.behavioral_config_widget import BehavioralConfigWidget


def test_coerce_float_returns_float_value():
    assert BehavioralConfigWidget._coerce_float("2.5", 1.0) == 2.5


def test_coerce_float_falls_back_on_invalid():
    assert BehavioralConfigWidget._coerce_float("invalid", 1.25) == 1.25
    assert BehavioralConfigWidget._coerce_float(None, 2.0) == 2.0


def test_coerce_int_returns_int_value():
    assert BehavioralConfigWidget._coerce_int("3", 1) == 3


def test_coerce_int_falls_back_on_invalid():
    assert BehavioralConfigWidget._coerce_int("invalid", 4) == 4
    assert BehavioralConfigWidget._coerce_int(None, 2) == 2
