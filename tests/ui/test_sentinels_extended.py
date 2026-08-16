"""Unit tests for ui/sentinels.py display label functions."""

from __future__ import annotations

from zebtrack.ui.sentinels import (
    all_tracks_label,
    both_models_label,
    day_prefix,
    is_main_arena_row,
    main_arena_label,
    main_arena_row_label,
    no_day_label,
    no_group_label,
    not_reported_label,
)


class TestSentinelsExtended:
    """Test sentinel label functions return non-empty strings."""

    def test_all_tracks_label_returns_string(self):
        result = all_tracks_label()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_no_group_label_returns_string(self):
        result = no_group_label()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_no_day_label_returns_string(self):
        result = no_day_label()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_not_reported_label_returns_string(self):
        result = not_reported_label()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_day_prefix_returns_string(self):
        result = day_prefix()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_main_arena_label_returns_string(self):
        result = main_arena_label()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_main_arena_row_label_contains_main_arena(self):
        row = main_arena_row_label()
        arena = main_arena_label()
        assert arena in row

    def test_both_models_label_returns_string(self):
        result = both_models_label()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_is_main_arena_row_true_for_row_label(self):
        label = main_arena_row_label()
        assert is_main_arena_row(label) is True

    def test_is_main_arena_row_true_for_bare_label(self):
        label = main_arena_label()
        assert is_main_arena_row(label) is True

    def test_is_main_arena_row_false_for_other(self):
        assert is_main_arena_row("Zone A") is False
        assert is_main_arena_row("") is False
        assert is_main_arena_row(None) is False
        assert is_main_arena_row(42) is False
