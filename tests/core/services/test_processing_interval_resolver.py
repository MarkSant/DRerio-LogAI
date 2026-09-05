"""Tests for the canonical analysis/display interval rule.

The contract is deliberately narrow: the researcher sets ONE number, and the
preview redraws on exactly the frames that were analysed. Three call sites used
to resolve the pair independently, and two UI inputs offered a second number
that could only ever make the overlay disagree with the data.
"""

from types import SimpleNamespace

import pytest

from zebtrack.core.services.processing_interval_resolver import (
    DEFAULT_ANALYSIS_INTERVAL,
    ProcessingIntervals,
    resolve_processing_intervals,
)


def _settings(interval):
    return SimpleNamespace(video_processing=SimpleNamespace(processing_interval=interval))


class TestDisplayFollowsAnalysis:
    def test_display_always_equals_analysis(self):
        intervals = resolve_processing_intervals(config={"analysis_interval_frames": 7})

        assert intervals.analysis == 7
        assert intervals.display == 7

    def test_stored_display_value_is_ignored(self):
        """Old projects carry a divergent value; it must not change the outcome."""
        intervals = resolve_processing_intervals(
            config={"analysis_interval_frames": 2, "display_interval_frames": 9}
        )

        assert intervals.display == 2

    def test_display_cannot_be_set_independently(self):
        """``display`` is a property, so no caller can build a disagreeing pair."""
        with pytest.raises(TypeError):
            ProcessingIntervals(analysis=5, display=9)  # type: ignore[call-arg]


class TestPrecedence:
    def test_config_beats_project_data(self):
        intervals = resolve_processing_intervals(
            config={"analysis_interval_frames": 1},
            project_data={"analysis_interval_frames": 3},
            settings_obj=_settings(5),
        )

        assert intervals.analysis == 1

    def test_project_data_beats_settings(self):
        intervals = resolve_processing_intervals(
            config=None,
            project_data={"analysis_interval_frames": 3},
            settings_obj=_settings(5),
        )

        assert intervals.analysis == 3

    def test_settings_beat_the_hardcoded_default(self):
        intervals = resolve_processing_intervals(settings_obj=_settings(5))

        assert intervals.analysis == 5

    def test_nothing_supplied_falls_back_to_the_default(self):
        assert resolve_processing_intervals().analysis == DEFAULT_ANALYSIS_INTERVAL


class TestDegradation:
    """A bad interval must fall through, never raise: analysis must still run."""

    @pytest.mark.parametrize("bad", [0, -1, "abc", None, object(), True])
    def test_unusable_config_value_falls_through_to_project_data(self, bad):
        intervals = resolve_processing_intervals(
            config={"analysis_interval_frames": bad},
            project_data={"analysis_interval_frames": 4},
        )

        assert intervals.analysis == 4

    def test_unusable_everywhere_reaches_the_default(self):
        intervals = resolve_processing_intervals(
            config={"analysis_interval_frames": 0},
            project_data={"analysis_interval_frames": -3},
            settings_obj=_settings("nonsense"),
        )

        assert intervals.analysis == DEFAULT_ANALYSIS_INTERVAL

    def test_numeric_string_is_accepted(self):
        """``project_config.json`` is hand-edited by researchers."""
        assert resolve_processing_intervals(config={"analysis_interval_frames": "6"}).analysis == 6

    def test_missing_settings_object_is_not_an_error(self):
        assert resolve_processing_intervals(settings_obj=None).analysis == DEFAULT_ANALYSIS_INTERVAL
