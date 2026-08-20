"""Tests for the canonical arena/ROI readiness probe."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from zebtrack.core.detection.detection_types import (
    AquariumData,
    MultiAquariumZoneData,
    ZoneData,
)
from zebtrack.core.services.zone_readiness import (
    ZoneReadiness,
    resolve_zone_readiness,
    zone_data_readiness,
)

SQUARE = [[0, 0], [10, 0], [10, 10], [0, 10]]


class _FakeProjectManager:
    """Minimal stand-in exposing the two accessors the probe consults."""

    def __init__(self, zone_data=None, multi_data=None, *, zone_raises=False):
        self._zone_data = zone_data
        self._multi_data = multi_data
        self._zone_raises = zone_raises
        self.zone_calls: list = []

    def get_multi_aquarium_zone_data(self, video_path):
        return self._multi_data

    def get_zone_data(self, video_path=None, **kwargs):
        self.zone_calls.append(video_path)
        if self._zone_raises:
            raise ValueError("corrupt zone entry")
        return self._zone_data


class TestZoneDataReadiness:
    def test_single_aquarium_reports_arena_and_rois_independently(self):
        assert zone_data_readiness(ZoneData(polygon=SQUARE)) == (True, False)
        assert zone_data_readiness(ZoneData(polygon=SQUARE, roi_polygons=[SQUARE])) == (True, True)

    def test_empty_zone_data_has_neither(self):
        assert zone_data_readiness(ZoneData()) == (False, False)

    def test_none_degrades_instead_of_raising(self):
        assert zone_data_readiness(None) == (False, False)

    def test_multi_aquarium_counts_rois_from_any_aquarium(self):
        multi = MultiAquariumZoneData(
            aquariums=[
                AquariumData(id=0, polygon=SQUARE),
                AquariumData(id=1, polygon=SQUARE, roi_polygons=[SQUARE]),
            ]
        )
        assert zone_data_readiness(multi) == (True, True)

    def test_multi_aquarium_without_any_roi(self):
        multi = MultiAquariumZoneData(aquariums=[AquariumData(id=0, polygon=SQUARE)])
        assert zone_data_readiness(multi) == (True, False)

    def test_multi_aquarium_with_no_aquariums_has_no_arena(self):
        assert zone_data_readiness(MultiAquariumZoneData(aquariums=[])) == (False, False)


class TestResolveZoneReadiness:
    def test_reads_per_video_zone_data(self):
        pm = _FakeProjectManager(zone_data=ZoneData(polygon=SQUARE, roi_polygons=[SQUARE]))

        readiness = resolve_zone_readiness(pm, "a.mp4")

        assert readiness == ZoneReadiness(video_path="a.mp4", has_arena=True, has_rois=True)
        assert readiness.can_analyse is True
        assert pm.zone_calls == ["a.mp4"]

    def test_multi_aquarium_wins_over_the_legacy_single_shim(self):
        """A project whose aquarium 0 is empty must not read as "no arena".

        ``get_zone_data`` returns aquarium 0 only, so consulting it first would
        report no arena for a project configured on aquarium 1 alone.
        """
        multi = MultiAquariumZoneData(
            aquariums=[AquariumData(id=1, polygon=SQUARE, roi_polygons=[SQUARE])]
        )
        pm = _FakeProjectManager(zone_data=ZoneData(), multi_data=multi)

        readiness = resolve_zone_readiness(pm, "a.mp4")

        assert readiness.has_arena is True
        assert readiness.has_rois is True
        assert pm.zone_calls == []

    def test_falls_through_to_single_when_multi_has_no_arena(self):
        pm = _FakeProjectManager(
            zone_data=ZoneData(polygon=SQUARE),
            multi_data=MultiAquariumZoneData(aquariums=[]),
        )

        readiness = resolve_zone_readiness(pm, "a.mp4")

        assert readiness.has_arena is True
        assert pm.zone_calls == ["a.mp4"]

    def test_no_project_manager_reports_nothing_ready(self):
        readiness = resolve_zone_readiness(None, "a.mp4")

        assert readiness == ZoneReadiness(video_path="a.mp4", has_arena=False, has_rois=False)
        assert readiness.can_analyse is False

    def test_empty_path_reports_nothing_ready(self):
        pm = _FakeProjectManager(zone_data=ZoneData(polygon=SQUARE))

        assert resolve_zone_readiness(pm, "").can_analyse is False

    def test_broken_zone_entry_degrades_instead_of_raising(self):
        """A readiness probe that raises would turn a disabled button into a crash."""
        pm = _FakeProjectManager(zone_raises=True)

        readiness = resolve_zone_readiness(pm, "a.mp4")

        assert readiness.can_analyse is False

    def test_project_manager_without_multi_accessor_still_works(self):
        pm = SimpleNamespace(get_zone_data=lambda video_path=None, **kw: ZoneData(polygon=SQUARE))

        assert resolve_zone_readiness(pm, "a.mp4").has_arena is True

    @pytest.mark.parametrize("has_rois", [True, False])
    def test_missing_rois_never_blocks_analysis(self, has_rois):
        """ROIs only gate ROI metrics; the arena is what gates detection."""
        zone_data = ZoneData(polygon=SQUARE, roi_polygons=[SQUARE] if has_rois else [])
        pm = _FakeProjectManager(zone_data=zone_data)

        readiness = resolve_zone_readiness(pm, "a.mp4")

        assert readiness.can_analyse is True
        assert readiness.has_rois is has_rois
