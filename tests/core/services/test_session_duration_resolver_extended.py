"""Extended unit tests for core/services/session_duration_resolver.py."""

from __future__ import annotations

from typing import Any

from zebtrack.core.services.session_duration_resolver import (
    DEFAULT_RECORDING_DURATION_S,
    SUBJECT_WILDCARD,
    _coerce_positive_duration,
    _normalize_day,
    block_override_key,
    collect_block_durations,
    duration_override_key,
    resolve_session_duration,
    set_duration_override,
)


class TestSessionDurationResolverExtended:
    """Test normalization, key generation, coercion, resolution hierarchy, and mutation."""

    def test_normalize_day_variants(self):
        assert _normalize_day(1) == "Dia_1"
        assert _normalize_day("1") == "Dia_1"
        assert _normalize_day("Dia_1") == "Dia_1"
        assert _normalize_day("Dia_01") == "Dia_1"
        assert _normalize_day("Dia 1") == "Dia_1"
        assert _normalize_day("D1") == "Dia_1"
        assert _normalize_day("D05") == "Dia_5"
        assert _normalize_day("") == ""
        assert _normalize_day("CustomDay") == "CustomDay"

    def test_keys_generation(self):
        key = duration_override_key(1, "Control", 3)
        assert key == "Dia_1|Control|3"

        block_key = block_override_key("Dia_02", "Treated")
        assert block_key == "Dia_2|Treated|*"

    def test_coerce_positive_duration(self):
        assert _coerce_positive_duration(120) == 120.0
        assert _coerce_positive_duration("300.5") == 300.5
        assert _coerce_positive_duration(0) is None
        assert _coerce_positive_duration(-10) is None
        assert _coerce_positive_duration("invalid") is None
        assert _coerce_positive_duration(float("nan")) is None
        assert _coerce_positive_duration(None) is None

    def test_resolve_session_duration_hierarchy(self):
        # 1. Fallback to default 300.0
        assert resolve_session_duration(None, 1, "Control", 1) == DEFAULT_RECORDING_DURATION_S

        # 2. Project-level default
        proj: dict[str, Any] = {"recording_duration_s": 600.0}
        assert resolve_session_duration(proj, 1, "Control", 1) == 600.0

        # 3. Block-level override
        set_duration_override(proj, 1, "Control", SUBJECT_WILDCARD, 450.0)
        assert resolve_session_duration(proj, 1, "Control", 1) == 450.0
        assert resolve_session_duration(proj, 1, "Control", 2) == 450.0
        # Other block still gets project default
        assert resolve_session_duration(proj, 2, "Control", 1) == 600.0

        # 4. Subject-level override
        set_duration_override(proj, 1, "Control", 2, 180.0)
        assert resolve_session_duration(proj, 1, "Control", 1) == 450.0  # inherits block
        assert resolve_session_duration(proj, 1, "Control", 2) == 180.0  # specific subject

    def test_clear_duration_override(self):
        proj: dict[str, Any] = {}
        set_duration_override(proj, 1, "Control", 1, 150.0)
        assert resolve_session_duration(proj, 1, "Control", 1) == 150.0

        # Setting None removes override
        set_duration_override(proj, 1, "Control", 1, None)
        assert resolve_session_duration(proj, 1, "Control", 1) == DEFAULT_RECORDING_DURATION_S

    def test_collect_block_durations(self):
        proj: dict[str, Any] = {"recording_duration_s": 300.0}
        set_duration_override(proj, 1, "Control", SUBJECT_WILDCARD, 200.0)
        set_duration_override(proj, 1, "Control", 3, 100.0)

        durations = collect_block_durations(proj, 1, "Control", ["1", "2", "3", "4"])
        assert durations["1"] == 200.0
        assert durations["2"] == 200.0
        assert durations["3"] == 100.0
        assert durations["4"] == 200.0
