"""Redetectar a arena nao pode apagar as ROIs do projeto.

O defeito
---------
Sessao real de 2026-09-06, projeto ao vivo: 2 ROIs desenhadas (``Z1``, ``Z2``),
comandos do Arduino associados e testados com sucesso pelo painel. Ao iniciar a
analise ao vivo, as ROIs nao apareciam e nenhum comando era enviado.

O log fecha o caso em duas linhas::

    zone_manager.load_zones.rois_loaded        <- as ROIs existem no projeto
    single_detector.zones.set  roi_count=0  polygon_points=17

A arena chegava ao detector; as ROIs, nao. Sem ROIs no detector nao ha o que
desenhar nem o que disparar: o envio ao Arduino e por BORDA de entrada/saida de
ROI, entao zero ROIs significa zero comandos -- e nada no log dizia que elas
tinham sido descartadas.

A causa
-------
``run_live_calibration`` montava ``ZoneData(polygon=..., metadata=...)`` com a
arena recem-detectada. Os campos ``roi_polygons``/``roi_names``/``roi_colors``
ficam VAZIOS por default, e ``save_zone_data`` SUBSTITUI a chave inteira -- entao
a gravacao trocava "arena + 2 ROIs" por "arena, sem ROIs".

A arena e o que a deteccao acabou de calcular. As ROIs nao sao dela para
redefinir.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.detection.detection_types import ZoneData


def _saved_zone_data(existing: ZoneData, new_polygon: list[list[int]]) -> ZoneData:
    """Reproduz a montagem que a calibracao faz antes de salvar.

    Espelha o trecho de ``run_live_calibration``: exercitar o metodo inteiro
    exigiria camera, detector e dialogo de preview, enquanto a propriedade em
    teste e o CONTEUDO do ``ZoneData`` que vai para ``save_zone_data``.
    """
    project_manager = MagicMock()
    project_manager.get_zone_data.return_value = existing

    found = project_manager.get_zone_data("ref.png")
    return ZoneData(
        polygon=new_polygon,
        roi_polygons=list(getattr(found, "roi_polygons", []) or []),
        roi_names=list(getattr(found, "roi_names", []) or []),
        roi_colors=list(getattr(found, "roi_colors", []) or []),
        metadata={},
    )


def _project_with_two_rois() -> ZoneData:
    return ZoneData(
        polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
        roi_polygons=[[[10, 10], [40, 10], [40, 40], [10, 40]], [[60, 60], [90, 60], [90, 90]]],
        roi_names=["Z1", "Z2"],
        roi_colors=[(255, 0, 0), (0, 255, 0)],
    )


def test_rois_survive_a_new_arena_detection() -> None:
    """O caso reportado: 2 ROIs antes, 2 ROIs depois."""
    saved = _saved_zone_data(_project_with_two_rois(), [[5, 5], [95, 5], [95, 95]])

    assert len(saved.roi_polygons) == 2
    assert list(saved.roi_names) == ["Z1", "Z2"]
    assert list(saved.roi_colors) == [(255, 0, 0), (0, 255, 0)]


def test_the_new_arena_still_replaces_the_old_one() -> None:
    """Preservar ROIs nao pode congelar a arena.

    A re-deteccao existe para corrigir a arena quando a camera se move; manter o
    poligono antigo derrotaria o proposito.
    """
    new_polygon = [[5, 5], [95, 5], [95, 95]]

    saved = _saved_zone_data(_project_with_two_rois(), new_polygon)

    assert list(saved.polygon) == new_polygon


def test_a_project_without_rois_stays_without_them() -> None:
    """Nada e inventado quando nao havia ROI nenhuma."""
    saved = _saved_zone_data(
        ZoneData(polygon=[[0, 0], [10, 0], [10, 10]]), [[1, 1], [9, 1], [9, 9]]
    )

    assert list(saved.roi_polygons) == []
    assert list(saved.roi_names) == []


def test_the_names_stay_aligned_with_the_polygons() -> None:
    """Nomes e poligonos sao listas PARALELAS.

    Copiar uma sem a outra desalinha o rotulo de cada ROI -- e o relatorio
    passaria a atribuir a ``Z1`` o tempo que o animal passou em ``Z2``.
    """
    existing = _project_with_two_rois()

    saved = _saved_zone_data(existing, [[1, 1], [9, 1], [9, 9]])

    assert len(saved.roi_names) == len(saved.roi_polygons)
    assert list(saved.roi_names) == list(existing.roi_names)


def test_the_preserved_lists_are_copies() -> None:
    """Copias, nao referencias.

    Guardar a mesma lista faria uma edicao posterior numa chave de zonas mudar a
    outra em silencio.
    """
    existing = _project_with_two_rois()

    saved = _saved_zone_data(existing, [[1, 1], [9, 1], [9, 9]])

    assert saved.roi_polygons is not existing.roi_polygons
    assert saved.roi_names is not existing.roi_names


def test_the_calibration_reads_the_rois_before_building_the_zone_data() -> None:
    """Varredura no fonte: a leitura tem de acontecer, e antes da montagem.

    O ``ZoneData`` sem ROIs voltaria a passar despercebido -- os campos tem
    default vazio, entao a construcao nunca falha. O que garante o conserto e a
    consulta ao estado atual existir.
    """
    import inspect

    from zebtrack.coordinators import live_calibration_coordinator as module

    source = inspect.getsource(module)
    build_at = source.index("zone_data = ZoneData(\n                polygon=int_polygon,")
    before = source[:build_at]

    assert "existing = self.project_manager.get_zone_data(reference_frame_path)" in before, (
        "a calibracao voltou a montar o ZoneData sem ler as ROIs existentes; "
        "redetectar a arena apaga as ROIs e o Arduino para de disparar"
    )
    assert "roi_polygons=preserved_rois" in source
