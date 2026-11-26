"""Tests for BehavioralConfigWidget static helpers."""

import pytest

from zebtrack.core.services.experiment_profile import AnimalModel, ProtocolId
from zebtrack.settings import DEFAULT_MAX_PLAUSIBLE_SPEED_CM_S
from zebtrack.ui.components.behavioral_config_widget import (
    BehavioralConfigWidget,
    animal_model_choices,
    protocol_choices,
    trial_type_choices,
)


def _need(value):
    """A widget the test just built must exist; narrows ``X | None`` for mypy."""
    assert value is not None
    return value


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


# ---------------------------------------------------------------------------
# ADR-014: the experiment profile (animal model + protocol)
# ---------------------------------------------------------------------------


def _pick(combo, choices, token) -> None:
    """Choose ``token`` in ``combo`` the way a click does (label shown, event fired)."""
    label = next(text for text, value in choices if value == token)
    combo.set(label)
    combo.event_generate("<<ComboboxSelected>>")


@pytest.fixture
def profile_widget(tkinter_root):
    seen: list = []
    built = BehavioralConfigWidget(
        tkinter_root,
        default_max_speed_cm_s=80.0,
        default_thigmotaxis_cm=2.5,
        default_perspective="lateral",
        show_profile=True,
        show_trial_type=True,
        on_profile_changed=seen.append,
    )
    built.pack()
    tkinter_root.update()
    built.seen_profiles = seen  # type: ignore[attr-defined]
    return built


@pytest.mark.gui
class TestProfileCombosHiddenByDefault:
    def test_without_the_flag_there_are_no_combos_and_the_profile_is_the_legacy_one(
        self, tkinter_root
    ):
        built = BehavioralConfigWidget(tkinter_root)

        assert built.animal_model_combo is None
        assert built.protocol_combo is None
        values = built.get_values()
        assert values["animal_model"] == "zebrafish"
        assert values["protocol"] == "generic"
        assert "protocol_params" not in values

    def test_a_saved_barnes_profile_still_locks_the_view_when_the_combos_are_hidden(
        self, tkinter_root
    ):
        built = BehavioralConfigWidget(tkinter_root, default_perspective="lateral")

        built.set_values({"protocol": "barnes", "aquarium_perspective": "lateral"})

        values = built.get_values()
        assert values["animal_model"] == "rodent"
        assert values["aquarium_perspective"] == "top_down"
        assert str(_need(built.perspective_combo).cget("state")) == "disabled"


@pytest.mark.gui
class TestProfileCombos:
    def test_the_combos_start_on_the_legacy_profile(self, profile_widget):
        assert _need(profile_widget.animal_model_combo).get() == "Zebrafish (aquarium)"
        assert _need(profile_widget.protocol_combo).get() == "Generic (no protocol)"
        assert str(_need(profile_widget.animal_model_combo).cget("state")) == "readonly"

    def test_choosing_barnes_locks_rodent_top_down_and_the_rodent_numbers(self, profile_widget):
        _pick(profile_widget.protocol_combo, protocol_choices(), "barnes")

        values = profile_widget.get_values()
        assert values["protocol"] == "barnes"
        assert values["animal_model"] == "rodent"
        assert values["aquarium_perspective"] == "top_down"
        assert values["geotaxis_enabled"] is False
        assert values["max_plausible_speed_cm_s"] == 100.0
        assert values["thigmotaxis_distance_cm"] == 15.0
        assert str(_need(profile_widget.animal_model_combo).cget("state")) == "disabled"
        assert str(_need(profile_widget.perspective_combo).cget("state")) == "disabled"

    def test_choosing_barnes_tells_the_owner_the_resolved_profile(self, profile_widget):
        _pick(profile_widget.protocol_combo, protocol_choices(), "barnes")

        profile = profile_widget.seen_profiles[-1]
        assert profile.protocol is ProtocolId.BARNES
        assert profile.animal_model is AnimalModel.RODENT

    def test_going_back_to_generic_unlocks_the_fields(self, profile_widget):
        _pick(profile_widget.protocol_combo, protocol_choices(), "barnes")

        _pick(profile_widget.protocol_combo, protocol_choices(), "generic")

        assert str(_need(profile_widget.animal_model_combo).cget("state")) == "readonly"
        assert str(_need(profile_widget.perspective_combo).cget("state")) == "readonly"
        assert profile_widget.get_values()["protocol"] == "generic"
        assert "protocol_params" not in profile_widget.get_values()

    def test_picking_a_rodent_resets_the_speed_and_wall_band_to_the_rodent_defaults(
        self, profile_widget
    ):
        _pick(profile_widget.animal_model_combo, animal_model_choices(), "rodent")

        values = profile_widget.get_values()
        assert values["animal_model"] == "rodent"
        assert values["max_plausible_speed_cm_s"] == 100.0
        assert values["thigmotaxis_distance_cm"] == 15.0
        assert profile_widget.get_values()["protocol"] == "generic"

    def test_going_back_to_zebrafish_restores_the_callers_defaults(self, profile_widget):
        _pick(profile_widget.animal_model_combo, animal_model_choices(), "rodent")

        _pick(profile_widget.animal_model_combo, animal_model_choices(), "zebrafish")

        values = profile_widget.get_values()
        assert values["max_plausible_speed_cm_s"] == 80.0
        assert values["thigmotaxis_distance_cm"] == 2.5

    def test_the_trial_type_row_exists_only_for_barnes(self, profile_widget, tkinter_root):
        assert not profile_widget._trial_type_row.winfo_manager()

        _pick(profile_widget.protocol_combo, protocol_choices(), "barnes")
        tkinter_root.update()

        assert profile_widget._trial_type_row.winfo_manager()

    def test_the_trial_type_is_the_sessions_default_in_the_protocol_params(self, profile_widget):
        _pick(profile_widget.protocol_combo, protocol_choices(), "barnes")
        assert profile_widget.get_values()["protocol_params"] == {
            "barnes": {"default_trial_type": "training"}
        }

        _pick(profile_widget.trial_type_combo, trial_type_choices(), "probe")

        assert profile_widget.get_values()["protocol_params"] == {
            "barnes": {"default_trial_type": "probe"}
        }

    def test_without_the_trial_type_row_the_params_are_left_alone(self, tkinter_root):
        built = BehavioralConfigWidget(tkinter_root, show_profile=True)
        _pick(built.protocol_combo, protocol_choices(), "barnes")

        assert "protocol_params" not in built.get_values()

    def test_picking_another_protocol_drops_the_previous_ones_parameters(self, profile_widget):
        _pick(profile_widget.protocol_combo, protocol_choices(), "barnes")
        profile_widget.set_protocol_param("table_diameter_cm", 150.0)

        _pick(profile_widget.protocol_combo, protocol_choices(), "generic")
        _pick(profile_widget.protocol_combo, protocol_choices(), "barnes")

        assert "table_diameter_cm" not in profile_widget.get_values()["protocol_params"]["barnes"]


@pytest.mark.gui
class TestProfileRoundTrip:
    def test_set_values_restores_the_profile_and_the_saved_numbers_win(self, profile_widget):
        profile_widget.set_values(
            {
                "animal_model": "rodent",
                "protocol": "barnes",
                "protocol_params": {"barnes": {"default_trial_type": "probe", "max_trial_s": 120}},
                "max_plausible_speed_cm_s": 130.0,
            }
        )

        values = profile_widget.get_values()
        assert values["animal_model"] == "rodent"
        assert values["protocol"] == "barnes"
        assert values["max_plausible_speed_cm_s"] == 130.0
        assert _need(profile_widget.trial_type_combo).get() == "Probe trial"
        assert values["protocol_params"] == {
            "barnes": {"default_trial_type": "probe", "max_trial_s": 120}
        }

    def test_a_config_without_profile_keys_leaves_the_profile_alone(self, profile_widget):
        profile_widget.set_values({"protocol": "barnes"})

        profile_widget.set_values({"thigmotaxis_distance_cm": 3.0})

        assert profile_widget.get_values()["protocol"] == "barnes"

    def test_an_unknown_token_degrades_like_every_other_reader(self, profile_widget):
        profile_widget.set_values({"animal_model": "dragon", "protocol": "stroop"})

        values = profile_widget.get_values()
        assert values["animal_model"] == "other"
        assert values["protocol"] == "generic"

    def test_restoring_another_animal_without_saved_numbers_follows_its_defaults(
        self, profile_widget
    ):
        profile_widget.set_values({"animal_model": "rodent"})

        values = profile_widget.get_values()
        assert values["max_plausible_speed_cm_s"] == 100.0
        assert values["thigmotaxis_distance_cm"] == 15.0

    def test_restoring_another_animal_keeps_the_numbers_the_config_declares(self, profile_widget):
        profile_widget.set_values(
            {
                "animal_model": "rodent",
                "max_plausible_speed_cm_s": 130.0,
                "thigmotaxis_distance_cm": 4.0,
            }
        )

        values = profile_widget.get_values()
        assert values["max_plausible_speed_cm_s"] == 130.0
        assert values["thigmotaxis_distance_cm"] == 4.0

    def test_restoring_the_same_animal_does_not_touch_hand_edited_numbers(self, profile_widget):
        profile_widget.set_values({"animal_model": "rodent"})
        profile_widget.max_speed_var.set(120.0)

        profile_widget.set_values({"animal_model": "rodent"})

        assert profile_widget.get_values()["max_plausible_speed_cm_s"] == 120.0

    def test_restoring_zebrafish_after_a_rodent_takes_the_callers_defaults_back(
        self, profile_widget
    ):
        profile_widget.set_values({"animal_model": "rodent"})

        profile_widget.set_values({"animal_model": "zebrafish"})

        values = profile_widget.get_values()
        assert values["max_plausible_speed_cm_s"] == 80.0
        assert values["thigmotaxis_distance_cm"] == 2.5

    def test_restoring_barnes_then_zebrafish_never_leaves_the_rodent_numbers(self, profile_widget):
        profile_widget.set_values({"protocol": "barnes"})
        assert profile_widget.get_values()["thigmotaxis_distance_cm"] == 15.0

        profile_widget.set_values({"animal_model": "zebrafish", "protocol": "generic"})

        assert profile_widget.get_values()["thigmotaxis_distance_cm"] == 2.5

    def test_reset_to_defaults_goes_back_to_the_legacy_profile(self, profile_widget):
        profile_widget.set_values({"protocol": "barnes"})

        profile_widget.reset_to_defaults()

        values = profile_widget.get_values()
        assert values["protocol"] == "generic"
        assert values["animal_model"] == "zebrafish"
        assert _need(profile_widget.protocol_combo).get() == "Generic (no protocol)"

    def test_set_protocol_param_travels_with_the_values(self, tkinter_root):
        built = BehavioralConfigWidget(tkinter_root)
        built.set_values({"protocol": "barnes"})

        built.set_protocol_param("table_diameter_cm", 150.0)

        assert built.get_values()["protocol_params"] == {"barnes": {"table_diameter_cm": 150.0}}
        assert built.get_protocol_params() == {"table_diameter_cm": 150.0}

    def test_a_generic_profile_has_no_protocol_params(self, tkinter_root):
        built = BehavioralConfigWidget(tkinter_root)
        built.set_protocol_param("table_diameter_cm", 150.0)

        assert built.get_protocol_params() == {}
