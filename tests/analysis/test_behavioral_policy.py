"""The species-neutral behavioural rules (#631).

Geotaxis is depth, so only a side view has it; the plausible-speed ceiling is a
per-species number with a zebrafish default.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from zebtrack.analysis.behavioral_policy import (
    geotaxis_applies,
    resolve_behavioral_config,
    resolve_max_plausible_speed,
)


class TestGeotaxisApplies:
    @pytest.mark.parametrize("perspective", ["top_down", "Top-Down", "topdown", "top"])
    def test_any_top_down_spelling_disables_it_even_when_enabled(self, perspective):
        config = {"aquarium_perspective": perspective, "geotaxis_enabled": True}

        assert geotaxis_applies(config) is False

    def test_side_view_without_the_flag_keeps_zebrafish_geotaxis(self):
        assert geotaxis_applies({"aquarium_perspective": "lateral"}) is True

    def test_side_view_that_turned_it_off_is_respected(self):
        config = {"aquarium_perspective": "lateral", "geotaxis_enabled": False}

        assert geotaxis_applies(config) is False

    @pytest.mark.parametrize("config", [None, {}])
    def test_no_configuration_is_the_legacy_side_view(self, config):
        assert geotaxis_applies(config) is True


def _settings(speed):
    return SimpleNamespace(behavioral_analysis=SimpleNamespace(max_plausible_speed_cm_s=speed))


class TestResolveMaxPlausibleSpeed:
    def test_explicit_argument_wins(self):
        assert (
            resolve_max_plausible_speed(70.0, {"max_plausible_speed_cm_s": 150.0}, _settings(90.0))
            == 70.0
        )

    def test_project_beats_settings(self):
        assert (
            resolve_max_plausible_speed(None, {"max_plausible_speed_cm_s": 150.0}, _settings(90.0))
            == 150.0
        )

    def test_settings_beat_the_default(self):
        assert resolve_max_plausible_speed(None, {}, _settings(90.0)) == 90.0

    def test_nothing_configured_is_the_zebrafish_ceiling(self):
        assert resolve_max_plausible_speed(None, None, object()) == 50.0

    @pytest.mark.parametrize("bad", [0, -5, "fast", float("nan"), float("inf"), True])
    def test_an_unusable_project_value_falls_through_instead_of_disabling(self, bad):
        assert (
            resolve_max_plausible_speed(None, {"max_plausible_speed_cm_s": bad}, _settings(90.0))
            == 90.0
        )

    def test_numeric_text_from_a_hand_edited_project_is_read(self):
        assert resolve_max_plausible_speed(None, {"max_plausible_speed_cm_s": "120"}, None) == 120.0


def _settings_with(perspective: str = "lateral") -> SimpleNamespace:
    return SimpleNamespace(
        behavioral_analysis=SimpleNamespace(
            default_thigmotaxis_distance_cm=1.5,
            default_geotaxis_distance_cm=2.0,
            default_geotaxis_num_zones=3,
            default_geotaxis_bottom_zones=1,
            aquarium_perspective=perspective,
        )
    )


class TestResolveBehavioralConfig:
    """#695: the ONE behavioural config every report path hands the reporters."""

    def test_settings_defaults_use_the_project_key_names(self):
        config = resolve_behavioral_config(None, _settings_with("lateral"))

        assert config == {
            "thigmotaxis_distance_cm": 1.5,
            "geotaxis_distance_cm": 2.0,
            "geotaxis_num_zones": 3,
            "geotaxis_bottom_zones": 1,
            "aquarium_perspective": "lateral",
            "geotaxis_enabled": True,
        }

    def test_the_project_overrides_the_settings(self):
        project = {"behavioral_config": {"thigmotaxis_distance_cm": 15.0, "geotaxis_num_zones": 4}}
        config = resolve_behavioral_config(project, _settings_with())

        assert config["thigmotaxis_distance_cm"] == 15.0
        assert config["geotaxis_num_zones"] == 4
        assert config["geotaxis_distance_cm"] == 2.0

    def test_a_top_down_project_drops_the_inherited_geotaxis(self):
        project = {"behavioral_config": {"aquarium_perspective": "Top-Down"}}
        config = resolve_behavioral_config(project, _settings_with("lateral"))

        assert config["aquarium_perspective"] == "top_down"
        assert config["geotaxis_enabled"] is False

    def test_the_legacy_behavioral_analysis_key_is_read(self):
        project = {"behavioral_analysis": {"thigmotaxis_distance_cm": 9.0}}

        assert (
            resolve_behavioral_config(project, _settings_with())["thigmotaxis_distance_cm"] == 9.0
        )

    def test_behavioral_config_wins_over_the_legacy_key(self):
        project = {
            "behavioral_config": {"thigmotaxis_distance_cm": 4.0},
            "behavioral_analysis": {"thigmotaxis_distance_cm": 9.0},
        }

        assert (
            resolve_behavioral_config(project, _settings_with())["thigmotaxis_distance_cm"] == 4.0
        )

    def test_without_settings_or_project_it_is_empty(self):
        assert resolve_behavioral_config(None, None) == {}

    def test_settings_without_a_behavioural_block_still_read_the_project(self):
        project = {"behavioral_config": {"aquarium_perspective": "lateral"}}

        assert resolve_behavioral_config(project, SimpleNamespace()) == {
            "aquarium_perspective": "lateral",
            "geotaxis_enabled": True,
        }

    def test_the_project_block_is_not_mutated(self):
        block = {"aquarium_perspective": "top"}
        resolve_behavioral_config({"behavioral_config": block}, _settings_with())

        assert block == {"aquarium_perspective": "top"}
