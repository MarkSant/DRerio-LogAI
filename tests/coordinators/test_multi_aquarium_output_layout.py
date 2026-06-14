"""Regressões do layout de saída multi-aquário por metadados.

Cobre:
- ``VideoCompletionMixin._scan_multi_aquarium_outputs`` agora é RECURSIVO: acha as
  trajetórias de cada aquário tanto no layout antigo ``aquarium_N/`` quanto no novo
  por metadados ``Grupo_X/Dia_YY/Sujeito_Z/`` (sob a pasta-raiz ``<video>_results``).
- ``ReportGenerationCoordinator._build_aquarium_report_base`` nomeia o relatório por
  metadados: ``Grupo_Sujeito_DiaN`` (ex.: ``Controle_S01_Dia1``).
"""

from pathlib import Path

from zebtrack.coordinators._video_completion_mixin import VideoCompletionMixin
from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_scan_finds_metadata_layout(tmp_path):
    """Layout por metadados (``Grupo_X/Dia/Sujeito_Y``) é encontrado recursivamente."""
    root = tmp_path / "exp_results"
    _touch(
        root
        / "Grupo_Controle"
        / "Dia_01"
        / "Sujeito_S01"
        / "3_CoordMovimento_exp_aquarium_1.parquet"
    )
    _touch(
        root
        / "Grupo_Tratamento"
        / "Dia_01"
        / "Sujeito_S02"
        / "3_CoordMovimento_exp_aquarium_2.parquet"
    )

    outputs: dict[int, dict] = {}
    VideoCompletionMixin._scan_multi_aquarium_outputs(str(root), "exp", outputs)

    assert set(outputs.keys()) == {0, 1}
    assert outputs[0]["results_dir"].endswith("Sujeito_S01")
    assert outputs[1]["results_dir"].endswith("Sujeito_S02")
    assert outputs[0]["parquet_files"]["trajectory"].endswith("_aquarium_1.parquet")


def test_scan_still_finds_legacy_aquarium_layout(tmp_path):
    """Layout antigo ``aquarium_N/`` continua sendo encontrado."""
    root = tmp_path / "exp_results"
    _touch(root / "aquarium_1" / "3_CoordMovimento_exp_aquarium_1.parquet")
    _touch(root / "aquarium_2" / "3_CoordMovimento_exp_aquarium_2.parquet")

    outputs: dict[int, dict] = {}
    VideoCompletionMixin._scan_multi_aquarium_outputs(str(root), "exp", outputs)

    assert set(outputs.keys()) == {0, 1}


def test_scan_ignores_single_trajectory(tmp_path):
    """Single (sem sufixo ``_aquarium_N``) não é tratado como multi-aquário."""
    root = tmp_path / "exp_results"
    _touch(root / "3_CoordMovimento_exp.parquet")

    outputs: dict[int, dict] = {}
    VideoCompletionMixin._scan_multi_aquarium_outputs(str(root), "exp", outputs)

    assert outputs == {}


def test_report_base_uses_metadata():
    """Nome do relatório vem dos metadados: ``Grupo_Sujeito_DiaN``."""
    base = ReportGenerationCoordinator._build_aquarium_report_base(
        {"group": "Controle", "subject": "S01", "day": 1}, 0
    )
    assert base == "Controle_S01_Dia1"


def test_report_base_sanitizes_and_extracts_day():
    """Sanitiza espaços/caracteres e extrai dígitos do dia (ex.: 'Dia 3')."""
    base = ReportGenerationCoordinator._build_aquarium_report_base(
        {"group": "Grupo Teste", "subject": "S 02", "day": "Dia 3"}, 1
    )
    assert base == "Grupo_Teste_S_02_Dia3"


def test_report_base_falls_back_when_missing():
    """Sem metadados, cai em ``aquario_{N+1}_S{NN}_Dia1``."""
    base = ReportGenerationCoordinator._build_aquarium_report_base({}, 1)
    assert base == "aquario_2_S02_Dia1"
