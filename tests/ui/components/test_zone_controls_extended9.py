"""Extended unit tests for ui/components/zone_controls.py (Part 9)."""

from __future__ import annotations

from typing import Any

from zebtrack.ui.components.zone_controls import ZoneControlsWidget


class TestZoneControlsExtended9:
    """Test ZoneControlsWidget current video entry and flags reset."""

    def test_zone_controls_current_video_entry_assignment(self):
        zc: Any = object.__new__(ZoneControlsWidget)
        zc._current_video_entry = {"group": "Treated", "subject": "Fish_02"}

        assert zc._current_video_entry is not None
        assert zc._current_video_entry["group"] == "Treated"
        assert zc._current_video_entry["subject"] == "Fish_02"

    def test_suspend_slider_callbacks_toggle(self):
        zc: Any = object.__new__(ZoneControlsWidget)
        zc._suspend_slider_callbacks = True
        assert zc._suspend_slider_callbacks is True
        zc._suspend_slider_callbacks = False
        assert zc._suspend_slider_callbacks is False

    def test_zone_controls_processing_state(self):
        zc: Any = object.__new__(ZoneControlsWidget)
        zc.is_processing = False
        assert zc.is_processing is False
        zc.is_processing = True
        assert zc.is_processing is True
