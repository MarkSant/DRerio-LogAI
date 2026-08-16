"""
Extended unit tests for external_trigger_gate.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.services.external_trigger_gate import (
    ExternalTriggerDecision,
    decide_external_trigger,
    normalize_arduino_port,
)


def test_normalize_arduino_port():
    assert normalize_arduino_port(None) == ""
    assert normalize_arduino_port("") == ""
    assert normalize_arduino_port("COM3") == "COM3"
    assert normalize_arduino_port("  COM4  ") == "COM4"
    assert normalize_arduino_port(3) == "3"
    assert normalize_arduino_port(115200) == "115200"


class TestDecideExternalTriggerExtended:
    """Test all branches of decide_external_trigger."""

    def test_trigger_disabled_proceeds(self):
        data = {"external_trigger_mode": False, "use_arduino": True}
        assert decide_external_trigger(data) == ExternalTriggerDecision.PROCEED
        assert decide_external_trigger(None) == ExternalTriggerDecision.PROCEED
        assert decide_external_trigger({}) == ExternalTriggerDecision.PROCEED

    def test_trigger_enabled_without_arduino_intent_rejected(self):
        data = {"external_trigger_mode": True, "use_arduino": False}
        assert decide_external_trigger(data) == ExternalTriggerDecision.REJECT_NO_ARDUINO

    def test_trigger_enabled_with_port_no_manager_arms_and_waits(self):
        data = {"external_trigger_mode": True, "use_arduino": True, "arduino_port": "COM3"}
        assert (
            decide_external_trigger(data, arduino_manager=None)
            == ExternalTriggerDecision.ARM_AND_WAIT
        )

    def test_trigger_enabled_manager_disconnected_rejected_offline(self):
        data = {"external_trigger_mode": True, "use_arduino": True, "arduino_port": "COM3"}
        mock_manager = MagicMock()
        mock_manager.is_connected.return_value = False
        assert (
            decide_external_trigger(data, arduino_manager=mock_manager)
            == ExternalTriggerDecision.REJECT_ARDUINO_OFFLINE
        )

    def test_trigger_enabled_manager_probe_exception_falls_back_to_arm(self):
        data = {"external_trigger_mode": True, "use_arduino": True, "arduino_port": "COM3"}
        mock_manager = MagicMock()
        mock_manager.is_connected.side_effect = RuntimeError("Serial error")
        assert (
            decide_external_trigger(data, arduino_manager=mock_manager)
            == ExternalTriggerDecision.ARM_AND_WAIT
        )

    def test_trigger_enabled_manager_connected_arms_and_waits(self):
        data = {"external_trigger_mode": True, "use_arduino": True, "arduino_port": "COM3"}
        mock_manager = MagicMock()
        mock_manager.is_connected.return_value = True
        assert (
            decide_external_trigger(data, arduino_manager=mock_manager)
            == ExternalTriggerDecision.ARM_AND_WAIT
        )
