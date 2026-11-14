"""Tests for BehavioralConfigWidget static helpers."""

import pytest

from zebtrack.settings import DEFAULT_MAX_PLAUSIBLE_SPEED_CM_S
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


# ---------------------------------------------------------------------------
# #695: the speed ceiling field
# ---------------------------------------------------------------------------


@pytest.fixture
def widget(tkinter_root):
    built = BehavioralConfigWidget(tkinter_root, default_max_speed_cm_s=80.0)
    built.pack()
    tkinter_root.update()
    return built


@pytest.mark.gui
class TestSpeedCeilingField:
    def test_the_field_starts_at_the_caller_default(self, widget):
        assert widget.get_values()["max_plausible_speed_cm_s"] == 80.0
        assert widget.max_speed_spinbox is not None

    def test_without_a_default_it_is_the_zebrafish_ceiling(self, tkinter_root):
        built = BehavioralConfigWidget(tkinter_root)

        assert built.get_values()["max_plausible_speed_cm_s"] == DEFAULT_MAX_PLAUSIBLE_SPEED_CM_S

    def test_set_values_round_trips(self, widget):
        widget.set_values({"max_plausible_speed_cm_s": 120.0})

        assert widget.get_values()["max_plausible_speed_cm_s"] == 120.0

    def test_a_config_without_the_key_leaves_the_field_alone(self, widget):
        widget.set_values({"thigmotaxis_distance_cm": 2.0})

        assert widget.get_values()["max_plausible_speed_cm_s"] == 80.0

    def test_reset_restores_the_default(self, widget):
        widget.set_values({"max_plausible_speed_cm_s": 300.0})
        widget.reset_to_defaults()

        assert widget.get_values()["max_plausible_speed_cm_s"] == 80.0

    @pytest.mark.parametrize("speed", [0.0, -1.0, 1000.5])
    def test_an_out_of_range_ceiling_is_refused(self, widget, speed):
        widget.max_speed_var.set(speed)

        is_valid, errors = widget.validate()

        assert not is_valid
        assert any("1000" in error for error in errors)

    @pytest.mark.parametrize("speed", [0.5, 1000.0])
    def test_the_bounds_themselves_are_accepted(self, widget, speed):
        widget.max_speed_var.set(speed)

        assert widget.validate() == (True, [])
