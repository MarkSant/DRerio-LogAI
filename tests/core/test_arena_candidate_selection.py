"""Tests for the shared arena-candidate selection rule.

This module is the single place that answers "which detection in this frame is
the arena, and is this outline usable at all". Both auto-detection flows depend
on it, so the behaviours pinned here are contracts, not implementation details.
"""

from typing import cast

import numpy as np
import pytest

from zebtrack.core.detection.arena_candidate_selection import (
    DEFAULT_MAX_AREA_RATIO,
    DEFAULT_MIN_AREA_RATIO,
    is_degenerate_outline,
    rank_box_indices,
    select_best_box_index,
)

FRAME_W, FRAME_H = 1280, 720
FRAME_AREA = FRAME_W * FRAME_H


def _box_of_ratio(ratio: float) -> list[float]:
    """Axis-aligned box occupying ``ratio`` of the frame, anchored at the origin."""
    side = (FRAME_AREA * ratio) ** 0.5
    return [0.0, 0.0, side, side]


class TestRankBoxIndices:
    def test_orders_by_confidence_not_by_area(self):
        """The big box loses to the confident one — the whole point of the rule."""
        boxes = [_box_of_ratio(0.45), _box_of_ratio(0.20)]
        ranked = rank_box_indices([0.30, 0.95], boxes, FRAME_W, FRAME_H)

        assert ranked == [1, 0]

    def test_returns_every_qualifying_box_so_callers_can_walk_down(self):
        boxes = [_box_of_ratio(0.40), _box_of_ratio(0.30), _box_of_ratio(0.20)]
        ranked = rank_box_indices([0.9, 0.8, 0.7], boxes, FRAME_W, FRAME_H)

        assert ranked == [0, 1, 2]

    def test_drops_boxes_below_the_area_floor(self):
        boxes = [_box_of_ratio(0.02), _box_of_ratio(0.30)]
        ranked = rank_box_indices([0.99, 0.10], boxes, FRAME_W, FRAME_H)

        assert ranked == [1], "a 2% box is a fish, not a tank, however confident"

    def test_drops_boxes_above_the_area_ceiling(self):
        """A box covering the field of view is a false positive, not an arena."""
        boxes = [_box_of_ratio(0.995), _box_of_ratio(0.30)]
        ranked = rank_box_indices([0.99, 0.10], boxes, FRAME_W, FRAME_H)

        assert ranked == [1]

    def test_falls_back_to_area_order_when_confidences_are_missing(self):
        boxes = [_box_of_ratio(0.20), _box_of_ratio(0.45)]
        ranked = rank_box_indices(None, boxes, FRAME_W, FRAME_H)

        assert ranked == [1, 0]

    def test_falls_back_to_area_order_when_confidences_do_not_line_up(self):
        """A mismatched conf list must not silently mis-attribute scores to boxes."""
        boxes = [_box_of_ratio(0.20), _box_of_ratio(0.45)]
        ranked = rank_box_indices([0.9], boxes, FRAME_W, FRAME_H)

        assert ranked == [1, 0]

    def test_unreadable_box_is_ranked_last_instead_of_raising(self):
        # Deliberately mistyped: a model or stub can hand back anything, and the
        # ranking must degrade rather than take the whole detection down.
        garbage = cast(list[float], ["x", "y", "z", "w"])
        ranked = rank_box_indices(None, [garbage, _box_of_ratio(0.30)], FRAME_W, FRAME_H)

        assert ranked == [1]

    @pytest.mark.parametrize(("width", "height"), [(0, 720), (1280, 0), (0, 0)])
    def test_zero_area_frame_yields_nothing(self, width, height):
        assert rank_box_indices([0.9], [_box_of_ratio(0.3)], width, height) == []

    def test_no_boxes_yields_nothing(self):
        assert rank_box_indices([], [], FRAME_W, FRAME_H) == []

    def test_custom_gate_overrides_the_defaults(self):
        boxes = [_box_of_ratio(0.05)]

        assert rank_box_indices([0.9], boxes, FRAME_W, FRAME_H) == []
        assert rank_box_indices([0.9], boxes, FRAME_W, FRAME_H, min_area_ratio=0.01) == [0]


class TestSelectBestBoxIndex:
    def test_returns_the_top_ranked_index(self):
        boxes = [_box_of_ratio(0.45), _box_of_ratio(0.20)]

        assert select_best_box_index([0.30, 0.95], boxes, FRAME_W, FRAME_H) == 1

    def test_returns_none_when_nothing_passes_the_gate(self):
        assert select_best_box_index([0.99], [_box_of_ratio(0.01)], FRAME_W, FRAME_H) is None

    def test_defaults_match_the_documented_gate(self):
        """The two flows shared these numbers by copy; they are now one constant."""
        assert DEFAULT_MIN_AREA_RATIO == 0.1
        assert DEFAULT_MAX_AREA_RATIO == 0.98


class TestIsDegenerateOutline:
    def test_zero_height_sliver_is_degenerate(self):
        """The exact mask that broke the 2026-08-31 run: bbox [76,720,1042,720]."""
        sliver = np.array([[76, 720], [1042, 720], [1042, 720], [76, 720]], dtype=np.int32)

        assert is_degenerate_outline(sliver) is True

    def test_zero_width_sliver_is_degenerate(self):
        sliver = np.array([[400, 10], [400, 300], [400, 500], [400, 10]], dtype=np.int32)

        assert is_degenerate_outline(sliver) is True

    @pytest.mark.parametrize("points", [[], [[1, 1]], [[1, 1], [2, 2]]])
    def test_fewer_than_three_vertices_is_degenerate(self, points):
        assert is_degenerate_outline(np.array(points, dtype=np.int32)) is True

    def test_none_is_degenerate(self):
        assert is_degenerate_outline(None) is True

    def test_a_real_outline_is_not_degenerate(self):
        tank = np.array([[4, 0], [1194, 0], [1194, 720], [4, 720]], dtype=np.int32)

        assert is_degenerate_outline(tank) is False

    def test_unreadable_outline_is_kept_rather_than_discarded(self):
        """Ambiguity must never cost a detection — downstream validation still runs."""
        assert is_degenerate_outline([object(), object(), object()]) is False
