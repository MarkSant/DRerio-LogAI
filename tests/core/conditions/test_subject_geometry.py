"""Tests for the subject geometry shared by the offline and live builders (#633).

``core/conditions/subject_geometry.py`` is the one place where "how much of the
rat is over the hole" and "how big is the rat" are computed. The numbers here are
exact: a 10 x 10 box half over a ROI covers exactly 0.5.
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from shapely.geometry import Polygon, box

from zebtrack.core.conditions.subject_geometry import (
    SubjectGeometry,
    observe_subject,
    observe_subjects,
    pick_subject_bbox,
    prepare_rois,
)

#: ROI ``toca``: x in [10, 20], y in [0, 10].
TOCA = ("toca", box(10, 0, 20, 10))
#: ROI ``far``: never touched by the boxes below.
FAR = ("far", box(100, 100, 110, 110))


class TestPickSubjectBbox:
    def test_highest_confidence_wins(self) -> None:
        chosen = pick_subject_bbox([(0, 0, 50, 50, 0.4), (5, 5, 10, 10, 0.9)])

        assert chosen == (5.0, 5.0, 10.0, 10.0)

    def test_tie_on_confidence_takes_the_larger_box(self) -> None:
        chosen = pick_subject_bbox([(5, 5, 10, 10, 0.9), (0, 0, 50, 50, 0.9)])

        assert chosen == (0.0, 0.0, 50.0, 50.0)

    def test_tie_on_confidence_larger_box_wins_whatever_the_order(self) -> None:
        chosen = pick_subject_bbox([(0, 0, 50, 50, 0.9), (5, 5, 10, 10, 0.9)])

        assert chosen == (0.0, 0.0, 50.0, 50.0)

    def test_corners_are_normalised(self) -> None:
        assert pick_subject_bbox([(10, 20, 0, 5, 0.5)]) == (0.0, 5.0, 10.0, 20.0)

    def test_no_box_is_none(self) -> None:
        assert pick_subject_bbox([]) is None

    @pytest.mark.parametrize(
        "item",
        [
            (0, 0, 0, 10, 0.9),  # no width
            (0, 0, 10, 0, 0.9),  # no height
            (0, 0, math.nan, 10, 0.9),
            (0, 0, math.inf, 10, 0.9),
            (0, 0, "a", 10, 0.9),
            (0, 0, 10),  # too short
        ],
    )
    def test_unusable_boxes_are_skipped(self, item: tuple) -> None:
        assert pick_subject_bbox([item]) is None
        assert pick_subject_bbox([item, (1, 1, 2, 2, 0.1)]) == (1.0, 1.0, 2.0, 2.0)

    @pytest.mark.parametrize("confidence", [None, "x", math.nan])
    def test_bad_confidence_counts_as_zero(self, confidence: Any) -> None:
        chosen = pick_subject_bbox([(0, 0, 50, 50, confidence), (1, 1, 2, 2, 0.01)])

        assert chosen == (1.0, 1.0, 2.0, 2.0)

    def test_missing_confidence_counts_as_zero(self) -> None:
        chosen = pick_subject_bbox([(0, 0, 50, 50), (1, 1, 2, 2, 0.01)])

        assert chosen == (1.0, 1.0, 2.0, 2.0)

    def test_extra_items_such_as_track_id_are_ignored(self) -> None:
        assert pick_subject_bbox([(0, 0, 4, 4, 0.9, 7, 2)]) == (0.0, 0.0, 4.0, 4.0)


class TestObserveSubject:
    def test_area_and_exact_half_cover(self) -> None:
        geometry = observe_subject((5, 0, 15, 10), [TOCA, FAR])

        assert geometry.area_px == pytest.approx(100.0)
        assert geometry.cover == {"toca": pytest.approx(0.5)}

    def test_box_inside_the_roi_covers_one(self) -> None:
        geometry = observe_subject((12, 2, 18, 8), [TOCA])

        assert geometry.area_px == pytest.approx(36.0)
        assert geometry.cover["toca"] == pytest.approx(1.0)

    def test_cover_is_a_fraction_of_the_box_not_of_the_roi(self) -> None:
        # A box twice the ROI's size, holding the whole ROI: half of the box is over it.
        geometry = observe_subject((10, 0, 30, 10), [TOCA])

        assert geometry.cover["toca"] == pytest.approx(0.5)

    def test_edge_contact_is_not_cover(self) -> None:
        geometry = observe_subject((0, 0, 10, 10), [TOCA])

        assert geometry.area_px == pytest.approx(100.0)
        assert "toca" not in geometry.cover

    def test_no_box_means_no_subject(self) -> None:
        assert observe_subject(None, [TOCA]) == SubjectGeometry(area_px=None, cover={})

    def test_unusable_box_means_no_subject(self) -> None:
        assert observe_subject((0, 0, 0, 0), [TOCA]).area_px is None

    def test_no_rois_still_measures_the_area(self) -> None:
        geometry = observe_subject((0, 0, 4, 5), [])

        assert geometry.area_px == pytest.approx(20.0)
        assert geometry.cover == {}

    def test_duplicate_roi_names_keep_the_larger_cover(self) -> None:
        small = ("toca", box(5, 0, 7, 10))  # 20 % of the box
        geometry = observe_subject((5, 0, 15, 10), [small, TOCA])

        assert geometry.cover["toca"] == pytest.approx(0.5)

    def test_invalid_roi_is_repaired(self) -> None:
        bowtie = ("toca", Polygon([(10, 0), (20, 10), (20, 0), (10, 10)]))

        geometry = observe_subject((10, 0, 20, 10), [bowtie])

        # buffer(0) keeps one lobe of the self-intersecting polygon: a quarter of the box.
        assert geometry.cover["toca"] == pytest.approx(0.25)

    def test_empty_roi_is_ignored(self) -> None:
        geometry = observe_subject((10, 0, 20, 10), [("toca", Polygon())])

        assert geometry.cover == {}


class TestObserveSubjects:
    def test_matches_observe_subject_frame_by_frame(self) -> None:
        boxes = [(5, 0, 15, 10), None, (12, 2, 18, 8), (0, 0, 0, 0), (0, 0, 10, 10)]

        batch = observe_subjects(boxes, [TOCA, FAR])

        assert batch == [observe_subject(b, [TOCA, FAR]) for b in boxes]
        assert [row.area_px for row in batch] == [100.0, None, 36.0, None, 100.0]

    def test_all_missing(self) -> None:
        assert observe_subjects([None, None], [TOCA]) == [
            SubjectGeometry(area_px=None, cover={}),
            SubjectGeometry(area_px=None, cover={}),
        ]


class TestPrepareRois:
    def test_keeps_valid_rois_in_order_and_drops_empty_ones(self) -> None:
        prepared = prepare_rois([TOCA, ("empty", Polygon()), FAR])

        assert [name for name, _shape in prepared] == ["toca", "far"]

    def test_drops_rois_without_area(self) -> None:
        line = ("line", Polygon([(0, 0), (1, 1), (2, 2)]))

        assert prepare_rois([line]) == ()


class TestPreparedRois:
    def test_prepared_rois_are_used_as_given(self, monkeypatch) -> None:
        import zebtrack.core.conditions.subject_geometry as module

        shapes = prepare_rois([TOCA])

        def _boom(_rois):
            raise AssertionError("prepared shapes prepared again")

        monkeypatch.setattr(module, "prepare_rois", _boom)
        geometry = observe_subject((5, 0, 15, 10), shapes, prepared=True)

        assert geometry.cover == {"toca": pytest.approx(0.5)}

    def test_raw_rois_are_prepared(self, monkeypatch) -> None:
        import zebtrack.core.conditions.subject_geometry as module

        calls = []
        real = module.prepare_rois

        def _counting(rois):
            calls.append(1)
            return real(rois)

        monkeypatch.setattr(module, "prepare_rois", _counting)
        observe_subject((5, 0, 15, 10), [TOCA])

        assert calls == [1]
