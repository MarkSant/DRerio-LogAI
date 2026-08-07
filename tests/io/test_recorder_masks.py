"""Sidecar de máscaras de segmentação (``3b_Mascaras_<base>.parquet``).

O sidecar existe porque o schema de ``3_CoordMovimento`` é IMUTÁVEL por
contrato de projeto (CLAUDE.md) e uma coluna binária de geometria não cabe lá.
Os testes cobrem as quatro promessas do arquivo:

1. Schema exato ``frame:int64, track_id:int64, mask_wkb:binary``.
2. ``persist_masks=False`` NÃO cria arquivo nenhum (o custo zero prometido).
3. O WKB faz round-trip preservando a geometria.
4. A calibração é aplicada aos pontos da máscara — sem isso a interseção com a
   ROI seria calculada entre espaços de coordenadas diferentes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from shapely import wkb as shapely_wkb
from shapely.geometry import Polygon

from zebtrack.core.detection import ZoneData
from zebtrack.io.recorder import Recorder

# Quadrado 10x10 na origem — área conhecida (100) para conferir o round-trip.
SQUARE = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]])


class _ShiftCalibration:
    """Calibração de mentira que só translada — o efeito é fácil de conferir.

    O contrato usado pelo recorder é ``transform_points``/``transform_bbox``,
    e é só isso que precisa existir aqui.
    """

    def __init__(self, dx: float = 100.0, dy: float = 50.0) -> None:
        self.dx = dx
        self.dy = dy
        self.homography_matrix = object()  # só para parecer configurada

    def transform_points(self, points: list) -> list:
        return [[float(x) + self.dx, float(y) + self.dy] for x, y in points]

    def transform_bbox(self, x1, y1, x2, y2) -> tuple:
        return (x1 + self.dx, y1 + self.dy, x2 + self.dx, y2 + self.dy)


def _make_recorder(persist: bool) -> Recorder:
    recorder = Recorder()
    recorder._persist_masks = persist
    recorder._flush_row_threshold = 1
    recorder._flush_interval_seconds = 0.05
    return recorder


@pytest.fixture
def output_dir(tmp_path: Path) -> str:
    folder = tmp_path / "sessao"
    folder.mkdir()
    return str(folder)


def _sidecar(output_dir: str, base: str = "sessao") -> Path:
    return Path(output_dir) / f"3b_Mascaras_{base}.parquet"


def _record(
    recorder: Recorder,
    output_dir: str,
    masks_by_frame: dict[int, dict[int, Any]],
    calibration: Any = None,
) -> None:
    # A calibração entra POR AQUI: ``start_recording`` reatribui
    # ``self.calibration`` a partir do argumento, então defini-la antes no
    # objeto seria apagado silenciosamente.
    recorder.start_recording(
        output_dir,
        640,
        480,
        zones=ZoneData(),
        is_video_file=True,
        base_name="sessao",
        calibration=calibration,
    )
    for frame_no, masks in masks_by_frame.items():
        recorder.write_detection_data(
            timestamp=float(frame_no) / 30.0,
            frame_number=frame_no,
            detections=[(0, 0, 10, 10, 0.9, track_id, 1) for track_id in masks],
        )
        recorder.write_mask_data(frame_no, masks)
    recorder.stop_recording()


def test_sidecar_has_the_exact_schema(output_dir: str) -> None:
    """As três colunas, nos tipos que o consumo espera para o join."""
    recorder = _make_recorder(persist=True)
    _record(recorder, output_dir, {0: {1: SQUARE}, 1: {1: SQUARE}})

    path = _sidecar(output_dir)
    assert path.exists()

    frame = pd.read_parquet(path)
    assert list(frame.columns) == ["frame", "track_id", "mask_wkb"]
    assert frame["frame"].dtype == np.int64
    assert frame["track_id"].dtype == np.int64
    assert len(frame) == 2
    assert isinstance(frame["mask_wkb"].iloc[0], bytes)


def test_persist_masks_disabled_creates_no_file(output_dir: str) -> None:
    """Custo ZERO: sem a flag não há arquivo, mesmo recebendo máscaras.

    É a regressão que protege quem não usa ``seg_overlap`` — a esmagadora
    maioria das sessões — de pagar um arquivo a mais por vídeo.
    """
    recorder = _make_recorder(persist=False)
    _record(recorder, output_dir, {0: {1: SQUARE}})

    assert not _sidecar(output_dir).exists()
    assert list(Path(output_dir).glob("3b_Mascaras_*.parquet")) == []
    # E a trajetória segue sendo gravada normalmente.
    assert (Path(output_dir) / "3_CoordMovimento_sessao.parquet").exists()


def test_wkb_round_trip_preserves_geometry(output_dir: str) -> None:
    """O que sai do parquet é o MESMO polígono que entrou."""
    recorder = _make_recorder(persist=True)
    _record(recorder, output_dir, {7: {3: SQUARE}})

    frame = pd.read_parquet(_sidecar(output_dir))
    row = frame.iloc[0]
    assert int(row["frame"]) == 7
    assert int(row["track_id"]) == 3

    geometry = shapely_wkb.loads(bytes(row["mask_wkb"]))
    assert geometry.is_valid
    assert geometry.area == pytest.approx(100.0)
    assert geometry.equals(Polygon(SQUARE))


def test_calibration_is_applied_to_mask_points(output_dir: str) -> None:
    """A máscara sofre a MESMA transformação que a bbox.

    As máscaras chegam em pixels do vídeo ORIGINAL enquanto
    ``write_detection_data`` já leva as bboxes para o espaço warped. Sem esta
    transformação, a interseção máscara ∩ ROI compararia geometrias de espaços
    diferentes — o número sairia, e estaria errado.
    """
    recorder = _make_recorder(persist=True)
    _record(recorder, output_dir, {0: {1: SQUARE}}, calibration=_ShiftCalibration(100.0, 50.0))

    geometry = shapely_wkb.loads(bytes(pd.read_parquet(_sidecar(output_dir))["mask_wkb"].iloc[0]))
    min_x, min_y, max_x, max_y = geometry.bounds
    assert (min_x, min_y, max_x, max_y) == pytest.approx((100.0, 50.0, 110.0, 60.0))
    # Translação preserva a área: o teste falha se a transformação for aplicada
    # duas vezes ou com escala indevida.
    assert geometry.area == pytest.approx(100.0)


def test_degenerate_contours_are_dropped_not_raised(output_dir: str) -> None:
    """Menos de 3 pontos não fecha polígono; a linha é descartada em silêncio.

    Descartar aqui é o que mantém a promessa do consumo: toda geometria no
    sidecar é válida, então ``_calculate_seg_overlap`` não precisa validar
    linha a linha no caminho quente.
    """
    recorder = _make_recorder(persist=True)
    _record(
        recorder,
        output_dir,
        {0: {1: np.array([[0.0, 0.0], [1.0, 1.0]]), 2: SQUARE}},
    )

    frame = pd.read_parquet(_sidecar(output_dir))
    assert len(frame) == 1
    assert int(frame["track_id"].iloc[0]) == 2


def test_no_file_when_no_masks_are_written(output_dir: str) -> None:
    """Flag ligada + modelo sem máscara = nenhum parquet vazio no disco."""
    recorder = _make_recorder(persist=True)
    _record(recorder, output_dir, {})

    assert not _sidecar(output_dir).exists()


def test_mask_rows_join_the_trajectory_on_frame_and_track(output_dir: str) -> None:
    """A chave ``(frame, track_id)`` casa com as linhas da trajetória.

    É o contrato de consumo inteiro: sem esse casamento a regra degrada.
    """
    recorder = _make_recorder(persist=True)
    _record(recorder, output_dir, {0: {1: SQUARE}, 1: {1: SQUARE}})

    trajectory = pd.read_parquet(Path(output_dir) / "3_CoordMovimento_sessao.parquet")
    masks = pd.read_parquet(_sidecar(output_dir))

    merged = trajectory.merge(masks, on=["frame", "track_id"], how="inner")
    assert len(merged) == len(masks)
