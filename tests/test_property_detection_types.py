"""Property-based tests for detection_types data classes.

Tests ZoneData, AquariumData, and MultiAquariumZoneData invariants
using Hypothesis to verify data class contracts.

Marker: @pytest.mark.property
Run with: poetry run pytest -m property tests/test_property_detection_types.py
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from zebtrack.core.detection.detection_types import (
    AquariumData,
    MultiAquariumZoneData,
    ZoneData,
)

# =============================================================================
# STRATEGIES
# =============================================================================

# Points for polygons (integer coords in image space)
int_point = st.tuples(st.integers(0, 1920), st.integers(0, 1080))
polygon = st.lists(int_point, min_size=3, max_size=8)
roi_polygon = st.lists(int_point, min_size=3, max_size=6)
roi_list = st.lists(roi_polygon, min_size=0, max_size=3)

aquarium_id = st.integers(min_value=0, max_value=9)

# Build AquariumData from components
aquarium_data_strategy = st.builds(
    AquariumData,
    id=aquarium_id,
    polygon=polygon,
    roi_mode=st.just("centroid_in"),
    roi_data=st.just(None),
    group=st.one_of(st.none(), st.text(min_size=1, max_size=10)),
    subject_id=st.one_of(st.none(), st.text(min_size=1, max_size=10)),
)


# =============================================================================
# ZONE DATA
# =============================================================================


@pytest.mark.property
class TestZoneDataProperties:
    """Property tests for ZoneData invariants."""

    @given(poly=polygon)
    @settings(max_examples=50, database=None)
    def test_polygon_stored_as_given(self, poly: list) -> None:
        """ZoneData should store the polygon as provided."""
        zd = ZoneData(polygon=poly)
        assert zd.polygon == poly

    @given(poly=polygon, rois=roi_list)
    @settings(max_examples=30, database=None)
    def test_roi_polygons_stored(self, poly: list, rois: list) -> None:
        """ROI polygons should be preserved."""
        zd = ZoneData(polygon=poly, roi_polygons=rois)
        assert zd.roi_polygons == rois

    @given(poly=polygon)
    @settings(max_examples=30, database=None)
    def test_default_metadata_empty(self, poly: list) -> None:
        """Default metadata should be an empty dict."""
        zd = ZoneData(polygon=poly)
        assert zd.metadata == {}


# =============================================================================
# AQUARIUM DATA → ZONE DATA CONVERSION
# =============================================================================


@pytest.mark.property
class TestAquariumDataConversion:
    """Property tests for AquariumData.to_zone_data() round-trip."""

    @given(aq=aquarium_data_strategy)
    @settings(max_examples=50, database=None)
    def test_to_zone_data_preserves_polygon(self, aq: AquariumData) -> None:
        """Conversion to ZoneData must preserve the polygon geometry."""
        zd = aq.to_zone_data()
        assert isinstance(zd, ZoneData)
        assert zd.polygon == aq.polygon

    @given(aq=aquarium_data_strategy)
    @settings(max_examples=50, database=None)
    def test_to_zone_data_preserves_roi_names(self, aq: AquariumData) -> None:
        """Conversion to ZoneData must preserve ROI names."""
        zd = aq.to_zone_data()
        assert zd.roi_names == aq.roi_names

    @given(
        id_val=aquarium_id,
        poly=polygon,
    )
    @settings(max_examples=30, database=None)
    def test_to_zone_data_drops_metadata(self, id_val: int, poly: list) -> None:
        """ZoneData should not contain aquarium-specific metadata (id, group)."""
        aq = AquariumData(id=id_val, polygon=poly, group="test_group", subject_id="S1")
        zd = aq.to_zone_data()
        # ZoneData doesn't have 'id', 'group', or 'subject_id' attributes
        assert not hasattr(zd, "id") and not hasattr(zd, "group")


# =============================================================================
# MULTI AQUARIUM ZONE DATA
# =============================================================================


@pytest.mark.property
class TestMultiAquariumZoneDataProperties:
    """Property tests for MultiAquariumZoneData container."""

    @given(aquariums=st.lists(aquarium_data_strategy, min_size=0, max_size=4))
    @settings(max_examples=50, database=None)
    def test_aquarium_count_matches_list_length(self, aquariums: list[AquariumData]) -> None:
        """aquarium_count must equal len(aquariums)."""
        mz = MultiAquariumZoneData(aquariums=aquariums)
        assert mz.aquarium_count == len(aquariums)

    @given(aquariums=st.lists(aquarium_data_strategy, min_size=0, max_size=4))
    @settings(max_examples=50, database=None)
    def test_is_multi_aquarium_threshold(self, aquariums: list[AquariumData]) -> None:
        """is_multi_aquarium should be True only when > 1 aquarium."""
        mz = MultiAquariumZoneData(aquariums=aquariums)
        assert mz.is_multi_aquarium == (len(aquariums) > 1)

    @given(aquariums=st.lists(aquarium_data_strategy, min_size=1, max_size=4))
    @settings(max_examples=50, database=None)
    def test_get_aquarium_returns_correct_id(self, aquariums: list[AquariumData]) -> None:
        """get_aquarium should return the aquarium with the matching id."""
        mz = MultiAquariumZoneData(aquariums=aquariums)
        for aq in aquariums:
            result = mz.get_aquarium(aq.id)
            assert result is not None
            assert result.id == aq.id

    @given(
        aquariums=st.lists(aquarium_data_strategy, min_size=1, max_size=3),
        bad_id=st.integers(min_value=100, max_value=999),
    )
    @settings(max_examples=30, database=None)
    def test_get_aquarium_returns_none_for_missing(
        self, aquariums: list[AquariumData], bad_id: int
    ) -> None:
        """get_aquarium should return None for non-existent id."""
        mz = MultiAquariumZoneData(aquariums=aquariums)
        result = mz.get_aquarium(bad_id)
        assert result is None

    @given(aquariums=st.lists(aquarium_data_strategy, min_size=1, max_size=3))
    @settings(max_examples=30, database=None)
    def test_get_aquarium_idempotent(self, aquariums: list[AquariumData]) -> None:
        """Calling get_aquarium twice should return the same result."""
        mz = MultiAquariumZoneData(aquariums=aquariums)
        aq_id = aquariums[0].id
        first = mz.get_aquarium(aq_id)
        second = mz.get_aquarium(aq_id)
        assert first is second

    @given(aquariums=st.lists(aquarium_data_strategy, min_size=1, max_size=3))
    @settings(max_examples=30, database=None)
    def test_to_zone_data_with_valid_id(self, aquariums: list[AquariumData]) -> None:
        """to_zone_data should compose get_aquarium + AquariumData.to_zone_data."""
        mz = MultiAquariumZoneData(aquariums=aquariums)
        aq_id = aquariums[0].id
        result = mz.to_zone_data(aq_id)
        assert isinstance(result, ZoneData)
        assert result.polygon == aquariums[0].polygon

    @given(
        aquariums=st.lists(aquarium_data_strategy, min_size=1, max_size=2),
        bad_id=st.integers(min_value=100, max_value=999),
    )
    @settings(max_examples=20, database=None)
    def test_to_zone_data_with_invalid_id_returns_empty(
        self, aquariums: list[AquariumData], bad_id: int
    ) -> None:
        """to_zone_data with invalid id should return empty ZoneData."""
        mz = MultiAquariumZoneData(aquariums=aquariums)
        result = mz.to_zone_data(bad_id)
        assert isinstance(result, ZoneData)
        # Empty ZoneData has no polygon or empty polygon
        assert result.polygon is None or result.polygon == []
