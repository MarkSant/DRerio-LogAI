"""
Extended unit tests for ArduinoEventMapper.
"""

from __future__ import annotations

from zebtrack.core.services.arduino_bindings import ArduinoBinding
from zebtrack.core.services.arduino_event_mapper import (
    ArduinoEventMapper,
    RoiTokenEvent,
)


class TestArduinoEventMapperExtended:
    """Test ArduinoEventMapper state machine transitions."""

    def test_roi_token_event_attributes(self):
        ev = RoiTokenEvent(roi="Zone1", edge="enter", token=42)
        assert ev.roi == "Zone1"
        assert ev.edge == "enter"
        assert ev.token == 42

    def test_update_and_update_detailed_lifecycle(self):
        bindings = [
            ArduinoBinding(roi="Z1", on_enter=1, on_exit=2),
            ArduinoBinding(roi="Z2", on_enter=3, on_exit=4),
            ArduinoBinding(roi="Z_no_exit", on_enter=5, on_exit=None),
        ]
        mapper = ArduinoEventMapper(bindings)

        # Frame 1: Enter Z1
        events1 = mapper.update_detailed(["Z1", "Unbound_Zone"])
        assert len(events1) == 1
        assert events1[0] == RoiTokenEvent(roi="Z1", edge="enter", token=1)

        # Frame 2: Still in Z1 -> no new events emitted (edge-triggered)
        assert mapper.update(["Z1"]) == []

        # Frame 3: Move from Z1 to Z2 directly (Z1 exit then Z2 enter)
        events3 = mapper.update_detailed(["Z2"])
        assert len(events3) == 2
        assert events3[0] == RoiTokenEvent(roi="Z1", edge="exit", token=2)
        assert events3[1] == RoiTokenEvent(roi="Z2", edge="enter", token=3)

        # Frame 4: Move from Z2 to Z_no_exit (Z2 exit token 4, Z_no_exit enter token 5)
        events4 = mapper.update_detailed(["Z_no_exit"])
        assert len(events4) == 2
        assert events4[0] == RoiTokenEvent(roi="Z2", edge="exit", token=4)
        assert events4[1] == RoiTokenEvent(roi="Z_no_exit", edge="enter", token=5)

        # Frame 5: Leave Z_no_exit -> since on_exit is None, no event emitted
        events5 = mapper.update_detailed([])
        assert events5 == []

        # Reset clears occupancy
        mapper.update(["Z1"])  # Occupy Z1
        mapper.reset()
        # Next frame occupying Z1 emits enter again because mapper was reset
        events_after_reset = mapper.update_detailed(["Z1"])
        assert len(events_after_reset) == 1
        assert events_after_reset[0] == RoiTokenEvent(roi="Z1", edge="enter", token=1)
