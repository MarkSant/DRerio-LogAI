"""Ground-truth (known-answer) + determinism tests for behavioural metrics.

These pin the *exact* numbers a synthetic, hand-computable trajectory must
produce end-to-end (px -> cm -> distance/velocity/tortuosity), and assert that
the pipeline is deterministic -- the reproducibility guarantee a paper relies
on. Analyzers use ``window_length=1, polyorder=0`` so Savitzky-Golay smoothing
is bypassed and the geometry is exact (see ``_preprocess_data``: an adaptive
window < 3 falls back to identity).

Conventions of the pipeline (verified against ``behavior.py``):
    x_cm = x_center_px / pixelcm_x
    y_cm = (video_height_px - y_center_px) / pixelcm_y      # Y inverted
    total_distance = sum_i sqrt(dx_cm_i^2 + dy_cm_i^2)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer

_ARENA_PX = [[0, 0], [20000, 0], [20000, 20000], [0, 20000]]
_VIDEO_H = 20000


def _analyzer(
    xs: list[float],
    ys: list[float],
    *,
    fps: float = 30.0,
    pixelcm: float = 10.0,
) -> ConcreteBehavioralAnalyzer:
    n = len(xs)
    df = pd.DataFrame(
        {
            "timestamp": [i / fps for i in range(n)],
            "x_center_px": xs,
            "y_center_px": ys,
            "x1": [x - 5 for x in xs],
            "y1": [y - 5 for y in ys],
            "x2": [x + 5 for x in xs],
            "y2": [y + 5 for y in ys],
        }
    )
    return ConcreteBehavioralAnalyzer(
        trajectory_df=df,
        pixelcm_x=pixelcm,
        pixelcm_y=pixelcm,
        video_height_px=_VIDEO_H,
        arena_polygon_px=_ARENA_PX,
        fps=fps,
        window_length=1,
        polyorder=0,
    )


class TestGroundTruthDistance:
    """Exact distances for hand-computed straight and L-shaped paths."""

    def test_horizontal_constant_velocity(self) -> None:
        # 100 px horizontal over 11 frames @ pixelcm=10 -> 10.0 cm; fps=10 -> 1.0 s.
        xs = [100.0 + 10.0 * i for i in range(11)]  # 100..200
        ys = [5000.0] * 11
        analyzer = _analyzer(xs, ys, fps=10.0, pixelcm=10.0)

        assert analyzer.calculate_total_distance() == pytest.approx(10.0)

        vel = analyzer.calculate_velocity_timeseries()
        v_mag = vel["v_mag"].dropna()
        # dx = 1 cm per 0.1 s -> 10 cm/s constant.
        assert np.allclose(v_mag.to_numpy(), 10.0)
        assert v_mag.mean() == pytest.approx(10.0)
        # Average speed == distance / elapsed time.
        elapsed = 10 / 10.0  # (n-1)/fps
        assert analyzer.calculate_total_distance() / elapsed == pytest.approx(10.0)

    def test_diagonal_three_four_five(self) -> None:
        # Straight 30 px x, 40 px y -> 50 px -> 5.0 cm @ pixelcm=10.
        xs = list(np.linspace(1000.0, 1030.0, 5))
        ys = list(np.linspace(5000.0, 5040.0, 5))
        analyzer = _analyzer(xs, ys, pixelcm=10.0)

        assert analyzer.calculate_total_distance() == pytest.approx(5.0)
        # Perfectly straight -> tortuosity exactly 1.0.
        assert analyzer.get_tortuosity() == pytest.approx(1.0)

    def test_l_shaped_path_distance_and_tortuosity(self) -> None:
        # Leg 1: 30 px in +x; Leg 2: 40 px in -y (image up). @ pixelcm=10.
        xs = [1000.0, 1010.0, 1020.0, 1030.0, 1030.0, 1030.0, 1030.0, 1030.0]
        ys = [5000.0, 5000.0, 5000.0, 5000.0, 4990.0, 4980.0, 4970.0, 4960.0]
        analyzer = _analyzer(xs, ys, pixelcm=10.0)

        # Path length = (30 + 40) / 10 = 7.0 cm.
        assert analyzer.calculate_total_distance() == pytest.approx(7.0)
        # Net displacement = sqrt(3^2 + 4^2) = 5.0 cm -> tortuosity = 7/5 = 1.4.
        assert analyzer.get_tortuosity() == pytest.approx(1.4)

    def test_stationary_distance_zero_and_tortuosity_one(self) -> None:
        xs = [3000.0] * 8
        ys = [3000.0] * 8
        analyzer = _analyzer(xs, ys)
        assert analyzer.calculate_total_distance() == pytest.approx(0.0, abs=1e-9)
        # Zero path and zero chord -> defined as 1.0 (perfectly "straight").
        assert analyzer.get_tortuosity() == pytest.approx(1.0)


class TestMetricDeterminism:
    """Same input => same output, with no leakage of global/instance state."""

    @staticmethod
    def _zigzag() -> tuple[list[float], list[float]]:
        xs = [1000.0 + 50.0 * i for i in range(12)]
        ys = [5000.0 + (200.0 if i % 2 else -200.0) for i in range(12)]
        return xs, ys

    def test_two_instances_same_distance_and_tortuosity(self) -> None:
        xs, ys = self._zigzag()
        a = _analyzer(xs, ys)
        b = _analyzer(xs, ys)  # fresh DataFrame, independent instance
        assert a.calculate_total_distance() == b.calculate_total_distance()
        assert a.get_tortuosity() == b.get_tortuosity()

    def test_velocity_series_reproducible_across_instances(self) -> None:
        xs, ys = self._zigzag()
        a = _analyzer(xs, ys)
        b = _analyzer(xs, ys)
        va = a.calculate_velocity_timeseries()["v_mag"].reset_index(drop=True)
        vb = b.calculate_velocity_timeseries()["v_mag"].reset_index(drop=True)
        pd.testing.assert_series_equal(va, vb)

    def test_repeated_calls_same_instance_are_stable(self) -> None:
        xs, ys = self._zigzag()
        analyzer = _analyzer(xs, ys)
        first = analyzer.calculate_total_distance()
        second = analyzer.calculate_total_distance()
        assert first == second
        # Velocity stats are likewise stable on repeated calls.
        assert analyzer.get_velocity_stats() == analyzer.get_velocity_stats()
