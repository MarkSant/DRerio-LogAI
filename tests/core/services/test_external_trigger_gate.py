"""Testes da regra única do modo de gatilho externo.

Os dois caminhos de gravação ao vivo (legado e grade de Progresso) consultam
este gate; divergir entre eles era exatamente o bug que ele existe para fechar.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from zebtrack.core.services.external_trigger_gate import (
    ExternalTriggerDecision,
    decide_external_trigger,
    normalize_arduino_port,
)


class TestDecideExternalTrigger:
    def test_none_project_data_proceeds(self):
        assert decide_external_trigger(None) is ExternalTriggerDecision.PROCEED

    def test_empty_project_data_proceeds(self):
        assert decide_external_trigger({}) is ExternalTriggerDecision.PROCEED

    def test_trigger_off_proceeds_even_with_arduino(self):
        data = {"external_trigger_mode": False, "use_arduino": True, "arduino_port": "COM3"}
        assert decide_external_trigger(data) is ExternalTriggerDecision.PROCEED

    def test_trigger_on_with_arduino_arms(self):
        data = {"external_trigger_mode": True, "use_arduino": True, "arduino_port": "COM3"}
        assert decide_external_trigger(data) is ExternalTriggerDecision.ARM_AND_WAIT

    def test_trigger_on_without_arduino_rejects(self):
        """Gravar às cegas seria pior que recusar: o protocolo espera sincronia."""
        data = {"external_trigger_mode": True, "use_arduino": False}
        assert decide_external_trigger(data) is ExternalTriggerDecision.REJECT_NO_ARDUINO

    def test_saved_port_without_use_arduino_still_rejects(self):
        """``use_arduino`` é a fonte de verdade — uma porta órfã não vale."""
        data = {"external_trigger_mode": True, "use_arduino": False, "arduino_port": "COM3"}
        assert decide_external_trigger(data) is ExternalTriggerDecision.REJECT_NO_ARDUINO

    def test_arming_does_not_require_a_port_string(self):
        """A porta é resolvida pelo ArduinoManager; o gate não a valida."""
        data = {"external_trigger_mode": True, "use_arduino": True}
        assert decide_external_trigger(data) is ExternalTriggerDecision.ARM_AND_WAIT

    @pytest.mark.parametrize("truthy", [1, "yes", ["x"]])
    def test_truthy_flags_are_honored(self, truthy):
        data = {"external_trigger_mode": truthy, "use_arduino": truthy}
        assert decide_external_trigger(data) is ExternalTriggerDecision.ARM_AND_WAIT


class TestConnectivityCheck:
    """O gate checava INTENÇÃO, não conectividade. Se o connect falha no load do
    projeto, o app avisa "modo offline" e segue com ``use_arduino=True`` — armar
    nesse estado deixaria a sessão esperando para sempre."""

    @staticmethod
    def _armed_data():
        return {"external_trigger_mode": True, "use_arduino": True, "arduino_port": "COM3"}

    def test_connected_manager_arms(self):
        manager = SimpleNamespace(is_connected=lambda: True)
        assert (
            decide_external_trigger(self._armed_data(), manager)
            is ExternalTriggerDecision.ARM_AND_WAIT
        )

    def test_disconnected_manager_rejects_as_offline(self):
        manager = SimpleNamespace(is_connected=lambda: False)
        assert (
            decide_external_trigger(self._armed_data(), manager)
            is ExternalTriggerDecision.REJECT_ARDUINO_OFFLINE
        )

    def test_offline_is_distinct_from_not_configured(self):
        """Ações do usuário diferentes: conectar o cabo vs. configurar o projeto."""
        offline = decide_external_trigger(
            self._armed_data(), SimpleNamespace(is_connected=lambda: False)
        )
        unconfigured = decide_external_trigger(
            {"external_trigger_mode": True, "use_arduino": False}, None
        )
        assert offline is not unconfigured

    def test_no_manager_falls_back_to_config_only(self):
        """Sem manager, o gate degrada para a decisão histórica."""
        assert (
            decide_external_trigger(self._armed_data(), None)
            is ExternalTriggerDecision.ARM_AND_WAIT
        )

    def test_manager_without_is_connected_is_ignored(self):
        assert (
            decide_external_trigger(self._armed_data(), SimpleNamespace())
            is ExternalTriggerDecision.ARM_AND_WAIT
        )

    def test_probe_failure_does_not_block_recording(self):
        """Sondar a serial não pode impedir uma gravação."""

        def _boom():
            raise OSError("porta sumiu")

        manager = SimpleNamespace(is_connected=_boom)
        assert (
            decide_external_trigger(self._armed_data(), manager)
            is ExternalTriggerDecision.ARM_AND_WAIT
        )

    def test_connectivity_is_not_checked_when_trigger_is_off(self):
        """Sem gatilho, um Arduino desconectado é irrelevante — não trava nada."""
        manager = SimpleNamespace(is_connected=lambda: False)
        data = {"external_trigger_mode": False, "use_arduino": True}
        assert decide_external_trigger(data, manager) is ExternalTriggerDecision.PROCEED


class TestPortNormalization:
    """``(x or "").strip()`` parece seguro e não é: um JSON com
    ``"arduino_port": 3`` faz ``3 or ""`` devolver o int, e ``.strip()``
    levanta AttributeError — no caminho de INICIAR gravação."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("COM3", "COM3"),
            ("  COM3  ", "COM3"),
            ("", ""),
            (None, ""),
            (3, "3"),
            (3.0, "3.0"),
            (["COM3"], "['COM3']"),
        ],
    )
    def test_normalize_never_raises(self, raw, expected):
        assert normalize_arduino_port(raw) == expected

    def test_gate_survives_non_string_port(self):
        """O gate deve ARMAR normalmente, não explodir, com porta numérica."""
        data = {"external_trigger_mode": True, "use_arduino": True, "arduino_port": 3}
        assert decide_external_trigger(data) is ExternalTriggerDecision.ARM_AND_WAIT
