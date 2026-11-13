"""The species-neutral behavioural rules (#631).

Geotaxis is depth, so only a side view has it; the plausible-speed ceiling is a
per-species number with a zebrafish default.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from zebtrack.analysis.behavioral_policy import geotaxis_applies, resolve_max_plausible_speed


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
