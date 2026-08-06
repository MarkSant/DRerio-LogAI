"""Property-based tests for ROI flutter filter and presence logic.

Tests the flutter filter's idempotency, output type/length invariants,
and edge behavior using Hypothesis strategies.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from zebtrack.analysis.roi import ROIAnalyzer

# ---------------------------------------------------------------------------
# Helper to test _apply_flutter_filter in isolation
# ---------------------------------------------------------------------------


def _apply_flutter(raw: pd.Series, n: int, exit_n: int | None = None) -> pd.Series:
    """Call _apply_flutter_filter without full ROIAnalyzer construction.

    Creates a minimal mock that exposes only the fields the method needs.
    O debounce é assimétrico; ``n`` sozinho configura os dois lados, que é o
    contrato da entrada legada ``flutter_n_frames``.
    """
    analyzer = object.__new__(ROIAnalyzer)
    analyzer._flutter_enter = n
    analyzer._flutter_exit = n if exit_n is None else exit_n
    return analyzer._apply_flutter_filter(raw)


# Strategies
_bool_series = st.lists(st.booleans(), min_size=1, max_size=200).map(
    lambda bools: pd.Series(bools, dtype=bool)
)

_flutter_n = st.integers(min_value=1, max_value=10)


# ---------------------------------------------------------------------------
# Output shape and type
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestFlutterFilterOutputProperties:
    """Output of flutter filter always has correct shape and dtype."""

    @given(raw=_bool_series, n=_flutter_n)
    @settings(max_examples=50, database=None)
    def test_output_length_matches_input(self, raw: pd.Series, n: int) -> None:
        """Filtered series has the same length as input."""
        result = _apply_flutter(raw, n)
        assert len(result) == len(raw)

    @given(raw=_bool_series, n=_flutter_n)
    @settings(max_examples=50, database=None)
    def test_output_dtype_is_bool(self, raw: pd.Series, n: int) -> None:
        """Filtered series is always boolean dtype."""
        result = _apply_flutter(raw, n)
        assert result.dtype == bool


# ---------------------------------------------------------------------------
# Stable runs preserved
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestFlutterFilterStableRuns:
    """A confirmed run of n consecutive True values produces True output."""

    @given(
        prefix_len=st.integers(min_value=0, max_value=20),
        run_len=st.integers(min_value=2, max_value=20),
        suffix_len=st.integers(min_value=0, max_value=20),
    )
    @settings(max_examples=50, database=None)
    def test_long_true_run_confirmed(self, prefix_len: int, run_len: int, suffix_len: int) -> None:
        """After n consecutive Trues, the last position is True in output."""
        n = 2
        # prefix of False, then run of True
        raw_list = [False] * prefix_len + [True] * run_len + [False] * suffix_len
        if not raw_list:
            return
        raw = pd.Series(raw_list, dtype=bool)
        result = _apply_flutter(raw, n)
        # The last True in the run should be confirmed True
        if run_len >= n:
            last_true_idx = prefix_len + run_len - 1
            if last_true_idx < len(result):
                assert result.iloc[last_true_idx] is np.bool_(True)

    @given(
        prefix_len=st.integers(min_value=3, max_value=20),
        suffix_len=st.integers(min_value=3, max_value=20),
    )
    @settings(max_examples=30, database=None)
    def test_single_true_flutter_suppressed(self, prefix_len: int, suffix_len: int) -> None:
        """A single True surrounded by many Falses is suppressed with n>=2."""
        n = 3
        raw_list = [False] * prefix_len + [True] + [False] * suffix_len
        raw = pd.Series(raw_list, dtype=bool)
        result = _apply_flutter(raw, n)
        # The single True should not survive the filter
        assert result.iloc[prefix_len] is np.bool_(False)


# ---------------------------------------------------------------------------
# Trivial cases
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestFlutterFilterTrivialCases:
    """Edge cases: n=1 is identity, all-True stays True, all-False stays False."""

    @given(raw=_bool_series)
    @settings(max_examples=30, database=None)
    def test_n_equals_one_is_identity(self, raw: pd.Series) -> None:
        """With n=1, the filter returns the original series unchanged."""
        result = _apply_flutter(raw, n=1)
        pd.testing.assert_series_equal(result, raw, check_names=False)

    @given(length=st.integers(min_value=1, max_value=100), n=_flutter_n)
    @settings(max_examples=30, database=None)
    def test_all_true_stays_true(self, length: int, n: int) -> None:
        """All-True stays all-True — provided the run can be confirmed at all.

        The confirmed entry is backdated to the first frame of the run, so a
        series that is long enough to confirm comes back untouched.
        """
        raw = pd.Series([True] * max(length, n), dtype=bool)
        result = _apply_flutter(raw, n)
        assert result.all()

    @given(n=st.integers(min_value=2, max_value=10))
    @settings(max_examples=20, database=None)
    def test_run_shorter_than_the_window_never_confirms(self, n: int) -> None:
        """A run too short to confirm stays outside — including at frame 0.

        The old filter used ``min_periods=1``, so the very first frame set the
        state with no confirmation at all. The border is now explicit: the
        state starts outside and only a full run of ``n`` frames moves it.
        """
        raw = pd.Series([True] * (n - 1), dtype=bool)
        assert not _apply_flutter(raw, n).any()

    @given(length=st.integers(min_value=1, max_value=100), n=_flutter_n)
    @settings(max_examples=30, database=None)
    def test_all_false_stays_false(self, length: int, n: int) -> None:
        """A series of all False values stays all False after filtering."""
        raw = pd.Series([False] * length, dtype=bool)
        result = _apply_flutter(raw, n)
        assert not result.any()
