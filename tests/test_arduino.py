import sys
import time
import types
from typing import ClassVar

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
            time.sleep(0.01)  # intentional delay for mock serial read
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
    monkeypatch.setitem(
        sys.modules,
        "serial.tools.list_ports",
        serial_list_ports_module,
    )
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


# ---------------------------------------------------------------------------
# F2 pragma review: driver quirks degrade the probe, never crash the scan
# ---------------------------------------------------------------------------


class _QuirkySerial:
    """A serial port whose optional calls fail the way some USB drivers do."""

    instances: ClassVar[list["_QuirkySerial"]] = []

    def __init__(self, port, baud_rate, timeout):
        self.port = port
        self.lines = [b"Arduino is ready.\n"]
        self.close_calls = 0
        _QuirkySerial.instances.append(self)

    def reset_input_buffer(self):
        raise OSError("driver does not support flush")

    def readline(self):
        if self.port == "COM_BROKEN":
            raise OSError("device unplugged mid-read")
        return self.lines.pop(0) if self.lines else b""

    def close(self):
        self.close_calls += 1
        raise OSError("handle already gone")


@pytest.fixture
def quirky_serial(monkeypatch):
    _QuirkySerial.instances = []
    monkeypatch.setattr(arduino.serial, "Serial", _QuirkySerial)
    return _QuirkySerial


def test_probe_succeeds_when_flush_and_close_are_unsupported(quirky_serial):
    assert Arduino.probe_port("COM_OK", 9600, timeout=0.5, warmup=0) is True
    assert [s.close_calls for s in quirky_serial.instances] == [1]


def test_probe_gives_up_at_once_when_the_read_fails(quirky_serial):
    started = time.monotonic()

    assert Arduino.probe_port("COM_BROKEN", 9600, timeout=5.0, warmup=0) is False

    assert time.monotonic() - started < 2.0
    assert [s.close_calls for s in quirky_serial.instances] == [1]


def _install_serial_tools(monkeypatch, list_ports_module):
    serial_module = types.ModuleType("serial")
    tools_module = types.ModuleType("serial.tools")
    if list_ports_module is not None:
        tools_module.list_ports = list_ports_module  # type: ignore[attr-defined]
    else:
        tools_module.__path__ = []  # a package that does not ship list_ports
    serial_module.tools = tools_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "serial", serial_module)
    monkeypatch.setitem(sys.modules, "serial.tools", tools_module)
    if list_ports_module is None:
        monkeypatch.delitem(sys.modules, "serial.tools.list_ports", raising=False)
    else:
        monkeypatch.setitem(sys.modules, "serial.tools.list_ports", list_ports_module)


def test_scan_without_list_ports_finds_nothing(monkeypatch):
    _install_serial_tools(monkeypatch, None)
    with pytest.raises(ImportError):
        from serial.tools import list_ports  # noqa: F401

    assert Arduino.scan_available_ports(baud_rate=9600) == ([], [])


def test_scan_survives_a_driver_that_cannot_enumerate(monkeypatch):
    list_ports_module = types.ModuleType("serial.tools.list_ports")

    def comports():
        raise OSError("SetupDiGetClassDevs failed")

    list_ports_module.comports = comports  # type: ignore[attr-defined]
    _install_serial_tools(monkeypatch, list_ports_module)

    assert Arduino.scan_available_ports(baud_rate=9600) == ([], [])
