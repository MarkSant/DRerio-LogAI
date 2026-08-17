"""Extended unit tests for ui/components/zone_controls.py (Part 6)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.zone_controls import ZoneControlsWidget


class TestZoneControlsExtended6:
    """Test ZoneControlsWidget initial tree state and pending payload tracking."""

    def test_zone_controls_tree_and_payload_defaults(self):
        zc = object.__new__(ZoneControlsWidget)
        zc._video_tree_expanded = True
        zc._pending_session_payload = None
        zc._context_menu_video_path = None

        assert zc._video_tree_expanded is True
        assert zc._pending_session_payload is None
        assert zc._context_menu_video_path is None

    def test_zone_controls_widget_references_none(self):
        zc = object.__new__(ZoneControlsWidget)
        zc.draw_roi_button = None
        zc.toggle_view_btn = None
        zc.save_arena_btn = None
        zc.discard_arena_btn = None

        assert zc.draw_roi_button is None
        assert zc.toggle_view_btn is None
        assert zc.save_arena_btn is None
        assert zc.discard_arena_btn is None

    def test_zone_controls_variables_defaults(self):
        zc = object.__new__(ZoneControlsWidget)
        zc.aquarium_count_var = MagicMock()
        zc.aquarium_count_var.get.return_value = 1
        zc.active_aquarium_var = MagicMock()
        zc.active_aquarium_var.get.return_value = 0
        zc.sequential_processing_var = MagicMock()
        zc.sequential_processing_var.get.return_value = True

        assert zc.aquarium_count_var.get() == 1
        assert zc.active_aquarium_var.get() == 0
        assert zc.sequential_processing_var.get() is True
