"""Testes do resolver canônico de duração de sessão ao vivo.

Precedência: cobaia > bloco (dia x grupo) > projeto > default.
"""

from __future__ import annotations

import pytest

from zebtrack.core.services.session_duration_resolver import (
    DEFAULT_RECORDING_DURATION_S,
    OVERRIDES_KEY,
    SUBJECT_WILDCARD,
    block_override_key,
    collect_block_durations,
    duration_override_key,
    resolve_session_duration,
    set_duration_override,
)


class TestKeyBuilding:
    @pytest.mark.parametrize(
        "day",
        [1, "1", "Dia_1", "D1", "Dia_01", "Dia 1", "dia_1", "D01", " Dia_1 "],
    )
    def test_day_formats_normalize_to_same_key(self, day):
        r"""O codebase carrega TODAS estas variantes; a chave tem de ser uma só.

        O zero à esquerda não é hipotético: ``OutputRegistrationManager
        ._format_day_component`` monta pastas com ``f"{day_number:02d}"`` (daí
        ``Dia_01``), e ``metadata_manager`` já precisa de ``^Dia_0*(\d+)$`` para
        desfazer. Sem a mesma tolerância aqui, um override gravado pela UI
        (``Dia_1``) nunca casaria com uma consulta vinda do registro de saída.
        """
        assert duration_override_key(day, "Controle", "3") == "Dia_1|Controle|3"

    def test_zero_padded_day_resolves_the_same_override(self):
        """O caso que realmente importa: gravar com um formato e ler com outro."""
        data = {"recording_duration_s": 300.0}
        set_duration_override(data, 1, "Controle", "3", 900.0)

        assert resolve_session_duration(data, "Dia_01", "Controle", "3") == 900.0
        assert resolve_session_duration(data, "Dia_1", "Controle", "3") == 900.0
        assert resolve_session_duration(data, 1, "Controle", "3") == 900.0

    def test_canonical_wire_format_is_pinned(self):
        """A chave é formato de PERSISTÊNCIA: mudá-la invalida projetos salvos."""
        assert duration_override_key(1, "Controle", "3") == "Dia_1|Controle|3"
        assert block_override_key(1, "Controle") == "Dia_1|Controle|*"

    def test_unrecognisable_day_does_not_raise(self):
        """Cai no default em vez de explodir no meio de uma gravação."""
        key = duration_override_key("semana que vem", "Controle", "3")
        assert key == "semana que vem|Controle|3"
        assert resolve_session_duration({}, "semana que vem", "Controle", "3") == 300.0

    def test_block_key_uses_wildcard_subject(self):
        assert block_override_key(2, "Tratado") == f"Dia_2|Tratado|{SUBJECT_WILDCARD}"

    def test_whitespace_is_stripped(self):
        assert duration_override_key(1, "  Controle  ", " 3 ") == "Dia_1|Controle|3"


class TestPrecedence:
    def test_default_when_project_data_is_empty(self):
        assert resolve_session_duration({}, 1, "Controle", "1") == DEFAULT_RECORDING_DURATION_S

    def test_default_when_project_data_is_none(self):
        assert resolve_session_duration(None, 1, "Controle", "1") == DEFAULT_RECORDING_DURATION_S

    def test_project_default_is_used(self):
        data = {"recording_duration_s": 600.0}
        assert resolve_session_duration(data, 1, "Controle", "1") == 600.0

    def test_block_override_beats_project_default(self):
        data = {
            "recording_duration_s": 600.0,
            OVERRIDES_KEY: {block_override_key(1, "Controle"): 900.0},
        }
        assert resolve_session_duration(data, 1, "Controle", "1") == 900.0

    def test_subject_override_beats_block_and_project(self):
        data = {
            "recording_duration_s": 600.0,
            OVERRIDES_KEY: {
                block_override_key(1, "Controle"): 900.0,
                duration_override_key(1, "Controle", "3"): 120.0,
            },
        }
        assert resolve_session_duration(data, 1, "Controle", "3") == 120.0
        # Outras cobaias do mesmo bloco seguem o padrão do bloco.
        assert resolve_session_duration(data, 1, "Controle", "1") == 900.0

    def test_overrides_do_not_leak_across_groups_or_days(self):
        data = {
            "recording_duration_s": 300.0,
            OVERRIDES_KEY: {block_override_key(1, "Controle"): 900.0},
        }
        assert resolve_session_duration(data, 1, "Tratado", "1") == 300.0
        assert resolve_session_duration(data, 2, "Controle", "1") == 300.0

    def test_day_format_mismatch_still_resolves(self):
        """Override gravado com dia int deve casar com consulta usando "Dia_N"."""
        data = {OVERRIDES_KEY: {duration_override_key(1, "Controle", "3"): 120.0}}
        assert resolve_session_duration(data, "Dia_1", "Controle", "3") == 120.0


class TestCorruptValues:
    """Um override inutilizável NÃO pode virar exceção nem duração zero —
    os dois perdem a gravação. Cai para o próximo nível."""

    @pytest.mark.parametrize("bad", ["abc", None, 0, -5, float("nan")])
    def test_bad_subject_override_falls_through_to_block(self, bad):
        data = {
            "recording_duration_s": 300.0,
            OVERRIDES_KEY: {
                duration_override_key(1, "Controle", "3"): bad,
                block_override_key(1, "Controle"): 900.0,
            },
        }
        assert resolve_session_duration(data, 1, "Controle", "3") == 900.0

    def test_bad_project_default_falls_through_to_module_default(self):
        data = {"recording_duration_s": -1}
        assert resolve_session_duration(data, 1, "Controle", "1") == DEFAULT_RECORDING_DURATION_S

    def test_non_dict_overrides_are_ignored(self):
        data = {"recording_duration_s": 300.0, OVERRIDES_KEY: "corrompido"}
        assert resolve_session_duration(data, 1, "Controle", "1") == 300.0


class TestSetOverride:
    def test_set_creates_the_container(self):
        data: dict = {}
        set_duration_override(data, 1, "Controle", "3", 480.0)
        assert data[OVERRIDES_KEY] == {"Dia_1|Controle|3": 480.0}

    def test_none_removes_the_override(self):
        data = {OVERRIDES_KEY: {"Dia_1|Controle|3": 480.0}}
        set_duration_override(data, 1, "Controle", "3", None)
        assert data[OVERRIDES_KEY] == {}

    @pytest.mark.parametrize("value", [0, -10])
    def test_non_positive_removes_the_override(self, value):
        data = {OVERRIDES_KEY: {"Dia_1|Controle|3": 480.0}}
        set_duration_override(data, 1, "Controle", "3", value)
        assert data[OVERRIDES_KEY] == {}

    def test_removing_a_missing_override_is_a_noop(self):
        data: dict = {}
        set_duration_override(data, 1, "Controle", "3", None)
        assert data[OVERRIDES_KEY] == {}

    def test_set_then_resolve_roundtrip(self):
        data = {"recording_duration_s": 300.0}
        set_duration_override(data, 1, "Controle", SUBJECT_WILDCARD, 600.0)
        set_duration_override(data, 1, "Controle", "2", 900.0)

        assert resolve_session_duration(data, 1, "Controle", "1") == 600.0
        assert resolve_session_duration(data, 1, "Controle", "2") == 900.0


class TestCollectBlockDurations:
    def test_uniform_block_yields_one_distinct_value(self):
        data = {"recording_duration_s": 300.0}
        durations = collect_block_durations(data, 1, "Controle", ["1", "2", "3"])
        assert set(durations.values()) == {300.0}

    def test_heterogeneous_block_is_detectable(self):
        data = {
            "recording_duration_s": 300.0,
            OVERRIDES_KEY: {duration_override_key(1, "Controle", "2"): 900.0},
        }
        durations = collect_block_durations(data, 1, "Controle", ["1", "2", "3"])
        assert durations == {"1": 300.0, "2": 900.0, "3": 300.0}
        assert len(set(durations.values())) == 2

    def test_empty_subject_list(self):
        assert collect_block_durations({}, 1, "Controle", []) == {}
