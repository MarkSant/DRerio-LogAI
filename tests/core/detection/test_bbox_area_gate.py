"""Tests for the runaway-bbox gate.

Guards the failure this exists for: after the tracker loses the animal, YOLO
keeps emitting a box that swells over reflections/shadows/the whole tank. That
box used to reach the trajectory parquet AND the edge-triggered Arduino ROI
dispatch, so it both corrupts kinematics and can fire a stimulus for an animal
that is not there.
"""

import pytest

from zebtrack.core.detection.bbox_area_gate import BboxAreaGate


def _box(side: float) -> tuple:
    """Square detection of ``side`` px at the origin: area == side**2."""
    return (0.0, 0.0, side, side, 0.9, None, 0)


def _feed(gate: BboxAreaGate, side: float, times: int) -> None:
    for _ in range(times):
        gate.filter([_box(side)])


class TestWarmup:
    def test_passes_everything_before_warmup(self):
        """A cold median must never discard real data."""
        gate = BboxAreaGate(ratio_max=3.0, window=30, warmup=10)

        # Even an absurd box survives while the gate has no baseline.
        assert gate.filter([_box(1000.0)]) == [_box(1000.0)]
        assert gate.rejections == 0

    def test_gate_activates_once_warmup_is_reached(self):
        gate = BboxAreaGate(ratio_max=3.0, window=30, warmup=10)
        _feed(gate, 10.0, 10)  # area 100, ten samples

        assert gate.sample_count == 10
        # 10x the median area -> rejected.
        assert gate.filter([_box(31.7)]) == []
        assert gate.rejections == 1


class TestRunawayRejection:
    def test_rejects_the_exploded_box_and_keeps_the_real_one(self):
        gate = BboxAreaGate(ratio_max=3.0, window=30, warmup=10)
        _feed(gate, 10.0, 12)  # stable baseline: area 100

        real = _box(11.0)  # area 121 -> 1.21x median, fine
        runaway = _box(60.0)  # area 3600 -> 36x median

        assert gate.filter([real, runaway]) == [real]
        assert gate.rejections == 1

    def test_runaway_burst_cannot_inflate_its_own_baseline(self):
        """Rejected areas must not enter the history.

        Otherwise a sustained runaway would drag the median upward until the
        gate silently stopped rejecting -- the exact failure mode this design
        avoids by remembering only ACCEPTED areas.
        """
        gate = BboxAreaGate(ratio_max=3.0, window=30, warmup=10)
        _feed(gate, 10.0, 12)

        for _ in range(200):
            assert gate.filter([_box(60.0)]) == []

        # Baseline untouched: a normal box still passes afterwards.
        assert gate.filter([_box(10.0)]) == [_box(10.0)]
        assert gate.rejections == 200

    def test_median_survives_outliers_already_in_the_window(self):
        """Median, not mean: a few huge accepted samples must not move the bar."""
        gate = BboxAreaGate(ratio_max=3.0, window=30, warmup=3)
        # Three big boxes get in during warmup, then many normal ones.
        _feed(gate, 100.0, 3)
        _feed(gate, 10.0, 20)

        # Median is now dominated by the area-100 boxes, so a 3600 box is out.
        assert gate.filter([_box(60.0)]) == []


class TestTolerance:
    def test_gradual_growth_within_ratio_is_allowed(self):
        """An animal approaching the camera is not a runaway."""
        gate = BboxAreaGate(ratio_max=3.0, window=30, warmup=10)
        _feed(gate, 10.0, 10)

        # area 250 == 2.5x the median of 100 -> under the 3.0 ceiling.
        assert gate.filter([_box(15.8)]) != []

    def test_small_boxes_are_never_rejected(self):
        """Upper bound only -- a small box is a missed detection, not a corrupt one."""
        gate = BboxAreaGate(ratio_max=3.0, window=30, warmup=10)
        _feed(gate, 10.0, 10)

        tiny = _box(1.0)
        assert gate.filter([tiny]) == [tiny]
        assert gate.rejections == 0

    def test_degenerate_box_is_dropped_without_polluting_history(self):
        gate = BboxAreaGate(ratio_max=3.0, window=30, warmup=10)
        _feed(gate, 10.0, 10)

        assert gate.filter([(5.0, 5.0, 5.0, 20.0, 0.9, None, 0)]) == []
        # Zero-area box must not enter the median (it would drag it to 0 and
        # then reject everything).
        assert gate.sample_count == 10


class TestLifecycle:
    def test_disabled_gate_is_a_passthrough(self):
        gate = BboxAreaGate(enabled=False, ratio_max=3.0, window=30, warmup=1)
        _feed(gate, 10.0, 10)

        huge = _box(10000.0)
        assert gate.filter([huge]) == [huge]
        assert gate.rejections == 0

    def test_reset_clears_history_between_videos(self):
        """Areas from a previous framing must not gate the next video."""
        gate = BboxAreaGate(ratio_max=3.0, window=30, warmup=10)
        _feed(gate, 10.0, 12)
        gate.filter([_box(60.0)])
        assert gate.rejections == 1

        gate.reset()

        assert gate.sample_count == 0
        assert gate.rejections == 0
        # A larger scale is now accepted from scratch.
        assert gate.filter([_box(60.0)]) != []

    def test_window_bounds_the_history(self):
        gate = BboxAreaGate(ratio_max=3.0, window=5, warmup=2)
        _feed(gate, 10.0, 50)
        assert gate.sample_count == 5

    def test_empty_input_is_returned_unchanged(self):
        gate = BboxAreaGate()
        assert gate.filter([]) == []


class TestFromSettings:
    def test_reads_yolo_model_section(self):
        class _Yolo:
            bbox_area_gate_enabled = False
            bbox_area_median_ratio_max = 7.5
            bbox_area_history_window = 12
            bbox_area_gate_warmup = 4

        class _Settings:
            yolo_model = _Yolo()

        gate = BboxAreaGate.from_settings(_Settings())

        assert gate.enabled is False
        assert gate.ratio_max == pytest.approx(7.5)
        assert gate.warmup == 4

    def test_defaults_when_settings_absent(self):
        """``settings_obj`` is optional on both detectors; an old config lacks the keys."""
        gate = BboxAreaGate.from_settings(None)

        assert gate.enabled is True
        assert gate.ratio_max == pytest.approx(3.0)
        assert gate.warmup == 10
