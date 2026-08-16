"""
Extended unit tests for AquariumRetryOutcome and outcome normalizer.
"""

from __future__ import annotations

import numpy as np

from zebtrack.core.detection.aquarium_retry import (
    RETRY_REASON_NO_CAMERA,
    RETRY_REASON_NO_FRAMES,
    RETRY_REASON_NO_POLYGON,
    RETRY_REASON_OK,
    AquariumRetryOutcome,
    normalize_retry_outcome,
)


class TestAquariumRetryExtended:
    """Test AquariumRetryOutcome attributes and normalization helper."""

    def test_outcome_properties(self):
        poly = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
        frame = np.zeros((100, 100, 3), dtype=np.uint8)

        success = AquariumRetryOutcome(polygon=poly, frame=frame, reason=RETRY_REASON_OK)
        assert success.succeeded is True
        assert success.reason == RETRY_REASON_OK
        assert success.polygon == poly

        failure = AquariumRetryOutcome(polygon=None, reason=RETRY_REASON_NO_CAMERA)
        assert failure.succeeded is False
        assert failure.reason == RETRY_REASON_NO_CAMERA
        assert failure.frame is None

    def test_normalize_from_outcome_instance(self):
        original = AquariumRetryOutcome(reason=RETRY_REASON_NO_FRAMES)
        normalized = normalize_retry_outcome(original)
        assert normalized is original

    def test_normalize_from_none(self):
        normalized = normalize_retry_outcome(None)
        assert isinstance(normalized, AquariumRetryOutcome)
        assert normalized.succeeded is False
        assert normalized.reason == RETRY_REASON_NO_POLYGON

    def test_normalize_from_legacy_tuple(self):
        poly = [[10.0, 10.0]]
        frame = np.zeros((10, 10), dtype=np.uint8)

        normalized = normalize_retry_outcome((frame, poly))
        assert isinstance(normalized, AquariumRetryOutcome)
        assert normalized.succeeded is True
        assert normalized.reason == RETRY_REASON_OK
        assert normalized.polygon == poly
