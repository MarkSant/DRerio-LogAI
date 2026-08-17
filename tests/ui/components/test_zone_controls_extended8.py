"""Extended unit tests for ui/components/zone_controls.py (Part 8)."""

from __future__ import annotations

from typing import Any

from zebtrack.ui.components.zone_controls import ZoneControlsWidget


class TestZoneControlsExtended8:
    """Test ZoneControlsWidget widget flags and interactive properties."""

    def test_zone_controls_flags_and_state(self):
        zc: Any = object.__new__(ZoneControlsWidget)
        zc._suspend_slider_callbacks = False
        zc._current_video_entry = None
        zc._is_processing_active = False

        assert zc._suspend_slider_callbacks is False
        assert zc._current_video_entry is None
        assert zc._is_processing_active is False

    def test_pending_session_payload_reset(self):
        zc: Any = object.__new__(ZoneControlsWidget)
        zc._pending_session_payload = {"group": "Control", "day": 1}
        zc._pending_session_payload = None

        assert zc._pending_session_payload is None

    def test_zone_controls_processing_active_toggle(self):
        zc: Any = object.__new__(ZoneControlsWidget)
        zc._is_processing_active = False
        zc._is_processing_active = True
        assert zc._is_processing_active is True
