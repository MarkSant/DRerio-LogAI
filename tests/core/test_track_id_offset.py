"""Golden + property tests for multi-aquarium global track-ID integrity.

``MultiAquariumDetector._offset_track_ids`` maps a per-aquarium *local* track id
to a process-global id via ``global_id = aquarium_id * 1000 + local_track_id``.
This mapping is what keeps each fish's trajectory attributable to the right
aquarium in the output Parquet, so an off-by-one or a silent overflow collision
corrupts per-subject data. The existing partitioned tests only cover the
happy-path format; here we pin the **overflow guard** (``local > 999`` wraps via
modulo) and the invariants a consumer relies on: recoverability
(``global // 1000 == aquarium``, ``global % 1000 == local``), cross-aquarium
uniqueness, ``None`` pass-through, and preservation of the bbox/conf/class fields.

Style mirrors ``tests/test_property_zone_scaler.py`` (``.map``-based strategies,
``database=None``, ``@pytest.mark.property``).
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from zebtrack.core.detection.multi_aquarium_detector import (
    AQUARIUM_TRACK_ID_MULTIPLIER,
    MAX_LOCAL_TRACK_ID,
    MultiAquariumDetector,
)

# A detection tuple is (x1, y1, x2, y2, conf, track_id, class_id).
_BBOX = (10.0, 20.0, 30.0, 40.0)
_CONF = 0.87
_CLS = 1


def _det(track_id: int | None) -> tuple:
    return (*_BBOX, _CONF, track_id, _CLS)


def _offset(track_id: int | None, aq_id: int) -> tuple:
    return MultiAquariumDetector._offset_track_ids([_det(track_id)], aq_id)[0]


class TestOffsetGolden:
    """Known-answer cases for the offset formula and its overflow guard."""

    @pytest.mark.parametrize(
        ("track_id", "aq_id", "expected_global"),
        [
            (5, 0, 5),  # aquarium 0 keeps local id
            (5, 1, 1005),  # aquarium 1 offset by 1000
            (0, 1, 1000),  # boundary low
            (MAX_LOCAL_TRACK_ID, 1, 1999),  # boundary high, no overflow
            (1000, 1, 1000),  # overflow -> 1*1000 + (1000 % 1000)
            (1500, 0, 500),  # overflow -> 0*1000 + (1500 % 1000)
            (2345, 1, 1345),  # overflow -> 1*1000 + (2345 % 1000)
        ],
    )
    def test_offset_value(self, track_id: int, aq_id: int, expected_global: int) -> None:
        assert _offset(track_id, aq_id)[5] == expected_global

    def test_none_track_id_passes_through(self) -> None:
        assert _offset(None, 1)[5] is None

    def test_bbox_conf_class_preserved(self) -> None:
        result = _offset(7, 1)
        assert result[:5] == (*_BBOX, _CONF)
        assert result[6] == _CLS

    def test_multiplier_and_max_constants(self) -> None:
        # Guards against accidental drift of the ID scheme.
        assert AQUARIUM_TRACK_ID_MULTIPLIER == 1000
        assert MAX_LOCAL_TRACK_ID == 999

    def test_length_preserved_for_batch(self) -> None:
        tracked = [_det(1), _det(2), _det(None), _det(3)]
        out = MultiAquariumDetector._offset_track_ids(tracked, aq_id=1)
        assert len(out) == len(tracked)


_aq_id = st.integers(min_value=0, max_value=1)
_local_in_range = st.integers(min_value=0, max_value=MAX_LOCAL_TRACK_ID)


@pytest.mark.property
class TestOffsetProperties:
    """Invariants of the global-id mapping."""

    @given(local=_local_in_range, aq=_aq_id)
    @settings(max_examples=100, database=None)
    def test_recoverable_when_in_range(self, local: int, aq: int) -> None:
        """For an in-range local id, aquarium and local id are both recoverable."""
        global_id = _offset(local, aq)[5]
        assert global_id // AQUARIUM_TRACK_ID_MULTIPLIER == aq
        assert global_id % AQUARIUM_TRACK_ID_MULTIPLIER == local

    @given(local=_local_in_range)
    @settings(max_examples=100, database=None)
    def test_cross_aquarium_unique(self, local: int) -> None:
        """The same local id in aquarium 0 vs 1 never collides."""
        g0 = _offset(local, 0)[5]
        g1 = _offset(local, 1)[5]
        assert g0 != g1
        assert g1 - g0 == AQUARIUM_TRACK_ID_MULTIPLIER

    @given(
        track_id=st.integers(min_value=0, max_value=100_000),
        aq=_aq_id,
    )
    @settings(max_examples=100, database=None)
    def test_overflow_stays_in_aquarium_band(self, track_id: int, aq: int) -> None:
        """Even on overflow, the global id stays within its aquarium's 1000-band."""
        global_id = _offset(track_id, aq)[5]
        lower = aq * AQUARIUM_TRACK_ID_MULTIPLIER
        assert lower <= global_id < lower + AQUARIUM_TRACK_ID_MULTIPLIER

    @given(
        track_id=st.one_of(st.none(), st.integers(min_value=0, max_value=100_000)),
        aq=_aq_id,
    )
    @settings(max_examples=60, database=None)
    def test_payload_fields_untouched(self, track_id: int | None, aq: int) -> None:
        """Only the track-id slot changes; geometry/conf/class are preserved."""
        result = _offset(track_id, aq)
        assert result[:5] == (*_BBOX, _CONF)
        assert result[6] == _CLS
