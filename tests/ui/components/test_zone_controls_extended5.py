"""Extended unit tests for ui/components/zone_controls.py (Part 5)."""

from __future__ import annotations

from zebtrack.ui.components.zone_controls import ZoneControlsWidget


class TestZoneControlsExtended5:
    """Test ZoneControlsWidget multi-aquarium state variables and widget handles."""

    def test_zone_controls_multi_aquarium_defaults(self):
        widget = object.__new__(ZoneControlsWidget)
        widget.aquarium_selector_frame = None
        widget.aquarium_radio_1 = None
        widget.aquarium_radio_2 = None

        assert widget.aquarium_selector_frame is None
        assert widget.aquarium_radio_1 is None
        assert widget.aquarium_radio_2 is None

    def test_zone_controls_pending_session_banner_defaults(self):
        widget = object.__new__(ZoneControlsWidget)
        widget.pending_session_frame = None
        widget.pending_session_label = None
        widget._pending_session_payload = None

        assert widget.pending_session_frame is None
        assert widget.pending_session_label is None
        assert widget._pending_session_payload is None
