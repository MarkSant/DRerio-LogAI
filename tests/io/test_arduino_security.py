"""Testes de segurança para comandos Arduino."""

import pytest
from unittest.mock import Mock, patch

from zebtrack.io.arduino import ALLOWED_ARDUINO_COMMANDS, Arduino, ArduinoCommandError


class TestArduinoCommandSecurity:
    """Testes de validação de comandos Arduino."""

    @pytest.fixture
    def mock_serial(self):
        """Cria mock de serial."""
        mock = Mock()
        mock.is_open = True
        mock.write = Mock()
        mock.flush = Mock()
        return mock

    @pytest.fixture
    def arduino(self, mock_serial):
        """Cria Arduino conectado com serial mockado."""
        with patch("zebtrack.io.arduino.serial.Serial", return_value=mock_serial):
            ard = Arduino(port="COM3", baud_rate=9600)
            # Manually set the serial object since we're mocking
            ard.ser = mock_serial
            return ard

    def test_valid_commands_accepted(self, arduino, mock_serial):
        """Comandos válidos devem ser aceitos."""
        for cmd in ALLOWED_ARDUINO_COMMANDS:
            arduino.send_string_command(cmd)
            mock_serial.write.assert_called()
            mock_serial.reset_mock()

    def test_invalid_command_rejected(self, arduino, mock_serial):
        """Comandos inválidos devem ser rejeitados."""
        with pytest.raises(ArduinoCommandError, match="Comando inválido"):
            arduino.send_string_command("INVALID_COMMAND")

        # Serial não deve ter sido chamado
        mock_serial.write.assert_not_called()

    def test_command_injection_attempt_blocked(self, arduino, mock_serial):
        """Tentativa de injeção de comando deve ser bloqueada."""
        injection_attempts = [
            "START; rm -rf /",
            "STOP && cat /etc/passwd",
            "STATUS\nSTART",
            "TRIGGER | ls -la",
            "../../../etc/passwd",
        ]

        for malicious_cmd in injection_attempts:
            with pytest.raises(ArduinoCommandError, match="Comando inválido"):
                arduino.send_string_command(malicious_cmd)

            mock_serial.write.assert_not_called()
            mock_serial.reset_mock()

    def test_case_insensitive_matching(self, arduino, mock_serial):
        """Comandos devem ser case-insensitive."""
        arduino.send_string_command("start")  # lowercase

        assert mock_serial.write.called

        call_args = mock_serial.write.call_args[0][0]
        assert b"START\n" == call_args  # Normalizado para uppercase

    def test_whitespace_trimmed(self, arduino, mock_serial):
        """Espaços em branco devem ser removidos."""
        arduino.send_string_command("  START  ")

        call_args = mock_serial.write.call_args[0][0]
        assert b"START\n" == call_args

    def test_error_message_includes_allowed_commands(self, arduino):
        """Mensagem de erro deve listar comandos permitidos."""
        with pytest.raises(ArduinoCommandError) as exc_info:
            arduino.send_string_command("HACK")

        error_msg = str(exc_info.value)
        assert "Comandos permitidos:" in error_msg

        # Deve listar pelo menos alguns comandos
        for cmd in ["START", "STOP", "STATUS"]:
            assert cmd in error_msg

    def test_empty_command_rejected(self, arduino, mock_serial):
        """Comando vazio deve ser rejeitado."""
        with pytest.raises(ArduinoCommandError):
            arduino.send_string_command("")

        with pytest.raises(ArduinoCommandError):
            arduino.send_string_command("   ")  # Apenas espaços

    def test_offline_arduino_returns_false(self):
        """Arduino desconectado deve retornar False sem exception."""
        ard = Arduino(port="COM3", baud_rate=9600)
        # Don't connect - ser is None

        result = ard.send_string_command("START")
        assert result is False
