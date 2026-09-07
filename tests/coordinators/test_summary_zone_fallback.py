"""As zonas somiam do sumario -- e com ele, do relatorio unificado.

O defeito
---------
Projeto ao vivo real, 4 ROIs (``Z1``-``Z4``). O ``.xlsx`` INDIVIDUAL da sessao
saia com 85 colunas e as metricas por ROI completas -- tempo, %, entradas,
saidas, latencia, distancia, velocidade, freezing. O ``_summary.parquet`` da
MESMA sessao saia com 43 colunas e NENHUMA. Como o relatorio unificado agrega os
sumarios, as zonas nao apareciam nem no parcial nem no total.

Sem erro, sem aviso: apenas ausentes.

A causa
-------
``generate_parquet_summaries`` resolvia as zonas por
``get_zone_data(video_path=<mp4 da sessao>)``. Mas uma sessao ao vivo e gravada
sob a chave do *reference frame* (``live_camera_reference_frame.png``), nao sob o
caminho do ``.mp4`` que ela produz. O ``.mp4`` nao tem chave propria, entao a
busca caia no ``detection_zones`` global -- que num projeto ao vivo costuma estar
VAZIO. Medido no projeto real::

    zones_by_video[live_camera_reference_frame.png] -> polygon=16  rois=4
    detection_zones (global)                        -> polygon=0   rois=0

Os dados nunca faltaram: o ``2_AreasOfInterest_<exp>.parquet`` na propria pasta
da sessao tinha as 4 ROIs o tempo todo.

Por que ler da pasta da sessao e o certo, nao so o pratico
----------------------------------------------------------
Aquele parquet registra as zonas com que a gravacao REALMENTE rodou. Redesenhar
as ROIs amanha nao deve reescrever o relatorio de hoje.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator
from zebtrack.core.detection.detection_types import ZoneData


def _coordinator(project_zone_data: ZoneData) -> ReportGenerationCoordinator:
    """Coordinator cujo ``get_zone_data`` devolve o que o projeto responderia."""
    coordinator = object.__new__(ReportGenerationCoordinator)
    coordinator.project_manager = MagicMock()
    coordinator.project_manager.get_zone_data.return_value = project_zone_data
    return coordinator


def _session_folder(tmp_path: Path, *, arena: bool = True, rois: bool = True) -> Path:
    """Reproduz a pasta de uma sessao, com os parquets que o recorder grava."""
    folder = tmp_path / "live_20260101_120000"
    folder.mkdir()

    if arena:
        pd.DataFrame({"x": [0, 100, 100, 0], "y": [0, 0, 100, 100]}).to_parquet(
            folder / "1_ProcessingArea_live_20260101_120000.parquet"
        )
    if rois:
        pd.DataFrame(
            {
                "roi_name": ["Z1"] * 3 + ["Z2"] * 3,
                "point_index": [0, 1, 2, 0, 1, 2],
                "x": [10, 40, 40, 60, 90, 90],
                "y": [10, 10, 40, 60, 60, 90],
            }
        ).to_parquet(folder / "2_AreasOfInterest_live_20260101_120000.parquet")

    return folder


def test_the_session_folder_supplies_the_rois_the_project_lacks(tmp_path: Path) -> None:
    """O caso reportado: projeto vazio, sessao com as ROIs no disco."""
    folder = _session_folder(tmp_path)
    coordinator = _coordinator(ZoneData())

    resolved = coordinator._resolve_summary_zone_data(folder / "video.mp4", folder)

    assert len(resolved.roi_polygons) == 2
    assert sorted(resolved.roi_names) == ["Z1", "Z2"]
    assert len(resolved.polygon) == 4


def test_the_project_wins_when_it_has_the_zones(tmp_path: Path) -> None:
    """O fallback e SEGUNDO nivel, nao substituicao.

    O fluxo pre-gravado resolve pelo projeto e continua igual; ler do disco por
    cima trocaria a fonte autoritativa por uma copia.
    """
    folder = _session_folder(tmp_path)
    from_project = ZoneData(
        polygon=[[0, 0], [9, 0], [9, 9]],
        roi_polygons=[[[1, 1], [2, 1], [2, 2]]],
        roi_names=["DoProjeto"],
    )

    resolved = coordinator_resolved = _coordinator(from_project)._resolve_summary_zone_data(
        folder / "video.mp4", folder
    )

    assert resolved is from_project
    assert list(coordinator_resolved.roi_names) == ["DoProjeto"]


def test_an_arena_without_rois_still_counts_as_an_answer(tmp_path: Path) -> None:
    """Projeto com arena e sem ROI nao dispara o fallback.

    Um projeto pode legitimamente nao ter ROI nenhuma. Tratar isso como "resposta
    vazia" faria o disco sobrepor uma configuracao deliberada.
    """
    folder = _session_folder(tmp_path)
    from_project = ZoneData(polygon=[[0, 0], [9, 0], [9, 9]])

    resolved = _coordinator(from_project)._resolve_summary_zone_data(folder / "video.mp4", folder)

    assert resolved is from_project
    assert list(resolved.roi_polygons) == []


def test_a_folder_without_parquets_returns_the_project_answer(tmp_path: Path) -> None:
    """Sem nada em disco, devolve o que o projeto deu -- e nao levanta.

    Uma pasta sem os parquets e o caso de um vídeo cujo tracking nunca rodou;
    quebrar aqui abortaria a geracao do lote inteiro por causa de um item.
    """
    folder = _session_folder(tmp_path, arena=False, rois=False)
    empty = ZoneData()

    resolved = _coordinator(empty)._resolve_summary_zone_data(folder / "video.mp4", folder)

    assert resolved is empty


def test_only_rois_on_disk_is_enough(tmp_path: Path) -> None:
    """Faltar a arena no disco nao pode custar as ROIs."""
    folder = _session_folder(tmp_path, arena=False, rois=True)

    resolved = _coordinator(ZoneData())._resolve_summary_zone_data(folder / "video.mp4", folder)

    assert sorted(resolved.roi_names) == ["Z1", "Z2"]


@pytest.mark.parametrize("missing", ["arena", "rois"])
def test_the_names_stay_paired_with_the_polygons(tmp_path: Path, missing: str) -> None:
    """Nomes e poligonos sao listas PARALELAS.

    Desalinhar aqui faria o sumario -- e depois o unificado -- atribuir a ``Z1`` o
    tempo que o animal passou em ``Z2``.
    """
    folder = _session_folder(tmp_path, arena=(missing != "arena"), rois=True)

    resolved = _coordinator(ZoneData())._resolve_summary_zone_data(folder / "video.mp4", folder)

    assert len(resolved.roi_names) == len(resolved.roi_polygons)


def test_the_summary_generation_uses_the_resolver() -> None:
    """O FIO: os testes acima passam com o fallback desconectado.

    Eles chamam ``_resolve_summary_zone_data`` diretamente, entao nao percebem se
    ``_process_standard_summary_video`` -- quem monta cada linha do sumario --
    voltar a chamar ``get_zone_data`` direto, que e exatamente o defeito.
    Varredura no fonte porque a propriedade e estatica: qual funcao a geracao
    consulta.
    """
    import inspect

    from zebtrack.coordinators import report_generation_coordinator as module

    source = inspect.getsource(module.ReportGenerationCoordinator._process_standard_summary_video)

    assert "_resolve_summary_zone_data(" in source, (
        "a geracao do sumario voltou a resolver zonas sem o fallback de disco; "
        "sessoes ao vivo perdem as ROIs no _summary.parquet e, com ele, no "
        "relatorio unificado"
    )
    assert "get_zone_data(video_path=path)" not in source
