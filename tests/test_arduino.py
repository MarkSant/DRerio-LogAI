import sys
import time
import types

import pytest

from zebtrack.io import arduino
from zebtrack.io.arduino import Arduino


@pytest.fixture
def fake_serial(monkeypatch):
    """Provide a controllable Serial replacement."""

    messages_by_port = {
        "COM_OK": [b"Arduino is ready.\n"],
        "COM_EMPTY": [b""],
    }

    class FakeSerial:
        def __init__(self, port, baud_rate, timeout):
            self.port = port
            self.timeout = timeout
            self._messages = list(messages_by_port.get(port, []))
            self.is_open = True

        def reset_input_buffer(self):
            self._messages = list(messages_by_port.get(self.port, []))

        def readline(self):
            if self._messages:
                return self._messages.pop(0)
            time.sleep(0.01)
            return b""

        def close(self):
            self.is_open = False

    monkeypatch.setattr(arduino.serial, "Serial", FakeSerial)
    return FakeSerial


def test_probe_port_detects_ready_signal(fake_serial):
    assert Arduino.probe_port("COM_OK", 9600, timeout=0.05, warmup=0)
    assert not Arduino.probe_port("COM_EMPTY", 9600, timeout=0.05, warmup=0)
    assert not Arduino.probe_port("COM_UNKNOWN", 9600, timeout=0.05, warmup=0)


def test_scan_available_ports_prefers_handshake(monkeypatch):
    class DummyPort:
        def __init__(self, device, description):
            self.device = device
            self.description = description

    ports = [
        DummyPort("COM_OK", "Arduino Uno"),
        DummyPort("COM_ALT", "USB Serial"),
    ]

    serial_module = types.ModuleType("serial")
    serial_tools_module = types.ModuleType("serial.tools")
    serial_list_ports_module = types.ModuleType("serial.tools.list_ports")
    serial_list_ports_module.comports = lambda: ports  # type: ignore[attr-defined]
    serial_tools_module.list_ports = serial_list_ports_module  # type: ignore[attr-defined]
    serial_module.tools = serial_tools_module  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "serial", serial_module)
    monkeypatch.setitem(sys.modules, "serial.tools", serial_tools_module)
    monkeypatch.setitem(sys.modules, "serial.tools.list_ports", serial_list_ports_module)
    monkeypatch.setattr(arduino, "serial", serial_module, raising=False)

    def fake_probe(cls, port, baud_rate, timeout=1.5):
        return port == "COM_OK"

    monkeypatch.setattr(
        Arduino,
        "probe_port",
        classmethod(fake_probe),
    )

    handshake_ports, fallback_ports = Arduino.scan_available_ports(baud_rate=9600)

    assert [p.device for p in handshake_ports] == ["COM_OK"]
    assert [p.device for p in fallback_ports] == ["COM_ALT"]
