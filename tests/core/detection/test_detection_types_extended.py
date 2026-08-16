"""
Extended unit tests for detection types (ZoneData, AquariumData, MultiAquariumZoneData).
"""

from __future__ import annotations

from zebtrack.core.detection.detection_types import (
    AquariumData,
    MultiAquariumZoneData,
    ZoneData,
)


class TestDetectionTypesExtended:
    """Test ZoneData, AquariumData, and MultiAquariumZoneData conversions."""

    def test_zone_data_defaults(self):
        zd = ZoneData()
        assert zd.polygon == []
        assert zd.roi_polygons == []
        assert zd.roi_names == []
        assert zd.roi_colors == []
        assert zd.metadata == {}

    def test_aquarium_data_to_zone_data(self):
        aq = AquariumData(
            id=0,
            polygon=[[0, 0], [10, 0], [10, 10], [0, 10]],
            roi_polygons=[[[1, 1], [5, 1], [5, 5], [1, 5]]],
            roi_names=["ZoneA"],
            roi_colors=[(255, 0, 0)],
            group="Control",
            subject_id="Fish1",
        )

        zd = aq.to_zone_data(metadata={"extra": 123})
        assert zd.polygon == aq.polygon
        assert zd.roi_polygons == aq.roi_polygons
        assert zd.roi_names == aq.roi_names
        assert zd.roi_colors == aq.roi_colors
        assert zd.metadata == {"extra": 123}

    def test_multi_aquarium_zone_data_lookup_and_conversion(self):
        aq0 = AquariumData(id=0, polygon=[[0, 0], [50, 50]], roi_names=["A0"])
        aq1 = AquariumData(id=1, polygon=[[50, 0], [100, 50]], roi_names=["A1"])

        multi = MultiAquariumZoneData(
            aquariums=[aq0, aq1],
            video_width=1280,
            video_height=720,
            sequential_processing=True,
        )

        # get_aquarium
        assert multi.get_aquarium(0) is aq0
        assert multi.get_aquarium(1) is aq1
        assert multi.get_aquarium(2) is None

        # to_zone_data
        zd0 = multi.to_zone_data(0)
        assert zd0.roi_names == ["A0"]

        zd1 = multi.to_zone_data(1)
        assert zd1.roi_names == ["A1"]

        # to_zone_data with invalid ID returns empty ZoneData
        zd_invalid = multi.to_zone_data(99)
        assert zd_invalid.polygon == []
