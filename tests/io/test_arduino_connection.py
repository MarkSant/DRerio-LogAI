"""Testes de conexão e envio numérico do ``Arduino`` (degradação graciosa).

Complementa ``tests/test_arduino.py`` (probe/scan) e
``tests/io/test_arduino_security.py`` (send_string_command) cobrindo
``connect``, ``send_command`` numérico, o context manager e ``close``.
"""

from __future__ import annotations

from typing import Any, cast

import serial

from zebtrack.io import arduino
from zebtrack.io.arduino import Arduino


class FakeSerial:
    """Serial configurável: fila de respostas + flag de erro na escrita."""

    def __init__(self, *, lines=None, raise_on_write=False, is_open=True):
        self._lines = list(lines or [])
        self.raise_on_write = raise_on_write
        self.is_open = is_open
        self.written: list[bytes] = []

    def readline(self):
        return self._lines.pop(0) if self._lines else b""

    def write(self, data):
        if self.raise_on_write:
            raise serial.SerialException("write failed")
        self.written.append(data)
        return len(data)

    def flush(self):
        pass

    def close(self):
        self.is_open = False


def _patch_serial(monkeypatch, fake):
    monkeypatch.setattr(arduino.serial, "Serial", lambda *a, **k: fake)


class TestConnect:
    def test_connect_success_on_ready_signal(self, monkeypatch):
        fake = FakeSerial(lines=[b"Arduino is ready.\n"])
        _patch_serial(monkeypatch, fake)
        ard = Arduino("COM1", 9600)
        assert ard.connect() is True
        assert ard.ser is fake

    def test_connect_fails_without_ready_signal(self, monkeypatch):
        fake = FakeSerial(lines=[b"garbage\n"])
        _patch_serial(monkeypatch, fake)
        ard = Arduino("COM1", 9600)
        assert ard.connect() is False
        assert ard.ser is None
        assert fake.is_open is False  # porta fechada após falha de handshake

    def test_connect_returns_true_if_already_open(self, monkeypatch):
        fake = FakeSerial(lines=[b"Arduino is ready.\n"])
        ard = Arduino("COM1", 9600)
        ard.ser = cast(Any, fake)  # já conectado
        assert ard.connect() is True

    def test_connect_handles_serial_exception(self, monkeypatch):
        def boom(*a, **k):
            raise serial.SerialException("no device")

        monkeypatch.setattr(arduino.serial, "Serial", boom)
        ard = Arduino("COM_X", 9600)
        assert ard.connect() is False
        assert ard.ser is None


class TestSendCommandNumeric:
    def test_send_command_ack(self, monkeypatch):
        fake = FakeSerial(lines=[b"OK\n"])
        ard = Arduino("COM1", 9600)
        ard.ser = cast(Any, fake)
        assert ard.send_command(3) is True
        assert fake.written == [b"3\n"]

    def test_send_command_nack(self, monkeypatch):
        fake = FakeSerial(lines=[b"ERR\n"])
        ard = Arduino("COM1", 9600)
        ard.ser = cast(Any, fake)
        assert ard.send_command(3) is False

    def test_send_command_invalid_number_returns_false(self):
        ard = Arduino("COM1", 9600)
        ard.ser = cast(Any, FakeSerial(lines=[b"OK\n"]))
        # Tipo inválido de propósito: o contrato promete False, não exceção.
        assert ard.send_command(cast(Any, "nao_numero")) is False

    def test_send_command_offline_returns_false(self):
        ard = Arduino("COM1", 9600)
        ard.ser = None
        assert ard.send_command(1) is False

    def test_send_command_serial_error_returns_false(self):
        ard = Arduino("COM1", 9600)
        ard.ser = cast(Any, FakeSerial(raise_on_write=True))
        assert ard.send_command(2) is False


class TestContextManagerAndClose:
    def test_context_manager_success(self, monkeypatch):
        fake = FakeSerial(lines=[b"Arduino is ready.\n"])
        _patch_serial(monkeypatch, fake)
        with Arduino("COM1", 9600) as ard:
            assert ard.ser is fake
        # __exit__ chama close()
        assert fake.is_open is False

    def test_context_manager_raises_on_connect_failure(self, monkeypatch):
        def boom(*a, **k):
            raise serial.SerialException("no device")

        monkeypatch.setattr(arduino.serial, "Serial", boom)
        try:
            with Arduino("COM_X", 9600):
                raise AssertionError("não deveria conectar")
        except RuntimeError as exc:
            assert "COM_X" in str(exc)

    def test_close_is_idempotent(self):
        fake = FakeSerial()
        ard = Arduino("COM1", 9600)
        ard.ser = cast(Any, fake)
        ard.close()
        assert ard.ser is None
        ard.close()  # segunda chamada não deve quebrar
        assert ard.ser is None
