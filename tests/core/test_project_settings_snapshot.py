"""The settings a PROJECT run uses: project > baseline > default, never shared.

Two failures this module exists to prevent:

1. An ad-hoc single-video (or live) run writes its freezing thresholds and
   Savitzky-Golay window into the SHARED ``Settings`` and never restores them.
   A project analysed afterwards inherited those numbers, silently changing
   reported freezing time, sharp turns, distance and speed.
2. The snapshot was implemented TWICE, applying different project keys, so
   regenerating a report produced different numbers than processing the video.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from zebtrack.core.services.project_settings_snapshot import (
    build_project_settings_snapshot,
)
from zebtrack.settings import load_settings


@pytest.fixture
def baseline():
    """Pristine settings, as captured at startup."""
    return load_settings()


@pytest.fixture
def polluted(baseline):
    """The shared object AFTER an ad-hoc run rewrote it."""
    settings = load_settings()
    settings.video_processing.freezing_velocity_threshold = 99.0
    settings.video_processing.freezing_min_duration_s = 42.0
    settings.video_processing.sharp_turn_threshold_deg_s = 7.0
    settings.trajectory_smoothing.window_length = 21
    settings.trajectory_smoothing.polyorder = 4
    return settings


class TestAdHocPollutionIsExcluded:
    def test_baseline_wins_over_the_polluted_shared_object(self, polluted, baseline):
        """The regression: a project must not inherit the ad-hoc run's numbers."""
        snapshot = build_project_settings_snapshot(polluted, {}, baseline=baseline)

        assert snapshot.video_processing.freezing_velocity_threshold == (
            baseline.video_processing.freezing_velocity_threshold
        )
        assert snapshot.video_processing.sharp_turn_threshold_deg_s == (
            baseline.video_processing.sharp_turn_threshold_deg_s
        )
        assert snapshot.trajectory_smoothing.window_length == (
            baseline.trajectory_smoothing.window_length
        )

    def test_without_a_baseline_the_live_object_is_used(self, polluted):
        """Ad-hoc runs pass no baseline — their own choices are the right answer."""
        snapshot = build_project_settings_snapshot(polluted, {})
        assert snapshot.video_processing.freezing_velocity_threshold == 99.0

    def test_project_values_beat_the_baseline(self, polluted, baseline):
        snapshot = build_project_settings_snapshot(
            polluted,
            {
                "analysis_parameters": {
                    "freezing_vel_threshold": 3.25,
                    "freezing_min_duration": 2.5,
                    "sharp_turn_threshold": 45.0,
                    "smoothing_window_length": 9,
                    "smoothing_polyorder": 2,
                }
            },
            baseline=baseline,
        )

        assert snapshot.video_processing.freezing_velocity_threshold == 3.25
        assert snapshot.video_processing.freezing_min_duration_s == 2.5
        assert snapshot.video_processing.sharp_turn_threshold_deg_s == 45.0
        assert snapshot.trajectory_smoothing.window_length == 9
        assert snapshot.trajectory_smoothing.polyorder == 2


class TestSharedObjectIsNeverMutated:
    def test_neither_source_is_touched(self, polluted, baseline):
        before_live = polluted.video_processing.freezing_velocity_threshold
        before_baseline = baseline.trajectory_smoothing.window_length

        build_project_settings_snapshot(
            polluted,
            {"analysis_parameters": {"freezing_vel_threshold": 1.0, "smoothing_window_length": 15}},
            baseline=baseline,
        )

        assert polluted.video_processing.freezing_velocity_threshold == before_live
        assert baseline.trajectory_smoothing.window_length == before_baseline

    def test_snapshot_is_a_distinct_object(self, baseline):
        snapshot = build_project_settings_snapshot(baseline, {})
        assert snapshot is not baseline
        assert snapshot.video_processing is not baseline.video_processing


class TestDegradation:
    """A hand-edited project file must not raise mid-analysis."""

    def test_even_window_keeps_the_baseline(self, baseline):
        snapshot = build_project_settings_snapshot(
            baseline, {"analysis_parameters": {"smoothing_window_length": 8}}
        )
        assert snapshot.trajectory_smoothing.window_length == (
            baseline.trajectory_smoothing.window_length
        )

    def test_polyorder_above_window_keeps_the_baseline(self, baseline):
        snapshot = build_project_settings_snapshot(
            baseline,
            {"analysis_parameters": {"smoothing_window_length": 5, "smoothing_polyorder": 99}},
        )
        assert snapshot.trajectory_smoothing.window_length == (
            baseline.trajectory_smoothing.window_length
        )
        assert snapshot.trajectory_smoothing.polyorder == baseline.trajectory_smoothing.polyorder

    def test_a_valid_pair_is_applied_despite_assignment_order(self, baseline):
        """window 5 / polyorder 4 is valid, but only if written as a PAIR.

        Assigning ``polyorder=4`` first would trip the cross-field validator
        against the previous window; the sub-model is replaced atomically.
        """
        snapshot = build_project_settings_snapshot(
            baseline,
            {"analysis_parameters": {"smoothing_window_length": 5, "smoothing_polyorder": 4}},
        )
        assert (
            snapshot.trajectory_smoothing.window_length,
            snapshot.trajectory_smoothing.polyorder,
        ) == (5, 4)

    @pytest.mark.parametrize("garbage", ["abc", None, {}, []])
    def test_uncastable_threshold_keeps_the_baseline(self, baseline, garbage):
        snapshot = build_project_settings_snapshot(
            baseline, {"analysis_parameters": {"freezing_vel_threshold": garbage}}
        )
        assert snapshot.video_processing.freezing_velocity_threshold == (
            baseline.video_processing.freezing_velocity_threshold
        )

    def test_non_dict_analysis_parameters_is_ignored(self, baseline):
        snapshot = build_project_settings_snapshot(baseline, {"analysis_parameters": "nonsense"})
        assert snapshot.video_processing.freezing_velocity_threshold == (
            baseline.video_processing.freezing_velocity_threshold
        )

    def test_a_settings_stub_without_model_copy_still_works(self):
        """Partial stand-ins reach this from tests and half-wired call sites."""
        stub = SimpleNamespace(
            video_processing=SimpleNamespace(freezing_velocity_threshold=1.0),
            roi_inclusion_rule="bbox_intersects",
            roi_buffer_radius_value=0.5,
            roi_min_bbox_overlap_ratio=0.1,
            roi_bbox_overlap_basis="bbox",
        )
        snapshot = build_project_settings_snapshot(
            stub, {"analysis_parameters": {"freezing_vel_threshold": 4.0}}
        )
        assert snapshot.video_processing.freezing_velocity_threshold == 4.0
        assert stub.video_processing.freezing_velocity_threshold == 1.0


class TestUnionOfBothFormerCopies:
    """Keys that only ONE of the two old implementations applied."""

    def test_regeneration_only_keys(self, baseline):
        snapshot = build_project_settings_snapshot(
            baseline,
            {
                "analysis_interval_frames": 17,
                "display_interval_frames": 23,
                "single_animal_per_aquarium": True,
            },
        )
        assert snapshot.video_processing.processing_interval == 17
        assert snapshot.video_processing.display_interval == 23
        assert snapshot.video_processing.single_animal_per_aquarium is True

    def test_processing_only_keys(self, baseline):
        snapshot = build_project_settings_snapshot(
            baseline,
            {
                # Must stay below ``processing_interval`` (a Settings-level
                # cross-field validator), which config.yaml defaults to 10.
                "analysis_offset_frames": 3,
                "behavioral_config": {
                    "aquarium_perspective": "top-down",
                    "thigmotaxis_distance_cm": 2.75,
                    "geotaxis_num_zones": 5,
                },
            },
        )
        assert snapshot.video_processing.processing_offset == 3
        assert snapshot.behavioral_analysis.aquarium_perspective == "top_down"
        assert snapshot.behavioral_analysis.default_thigmotaxis_distance_cm == 2.75
        assert snapshot.behavioral_analysis.default_geotaxis_num_zones == 5

    def test_offset_above_interval_is_refused_without_losing_the_batch(self, baseline):
        """A parent-level invariant must not discard the sibling keys.

        ``processing_offset`` is validated against ``processing_interval`` on
        ``Settings`` itself, not on the sub-model, so writing it in place left
        the parent invalid and blew up later at an unrelated assignment.
        """
        snapshot = build_project_settings_snapshot(
            baseline,
            {"analysis_offset_frames": 9999, "display_interval_frames": 23},
        )
        assert snapshot.video_processing.processing_offset == (
            baseline.video_processing.processing_offset
        )
        assert snapshot.video_processing.display_interval == 23

    def test_roi_rule_still_resolved(self, baseline):
        snapshot = build_project_settings_snapshot(
            baseline, {"roi_settings": {"roi_inclusion_rule": "centroid_in"}}
        )
        assert snapshot.roi_inclusion_rule == "centroid_in"
