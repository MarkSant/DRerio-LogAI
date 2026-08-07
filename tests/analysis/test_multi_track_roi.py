"""Análise de ROI com mais de um animal na mesma trajetória.

O defeito corrigido tinha duas metades somadas:

1. ``behavior.py`` fundia animais distintos num centroide de grupo (uma
   trajetória FANTASMA), e
2. ``roi.py`` calculava presença e transições com ``.diff()`` sobre linhas de
   animais intercalados.

Os testes deste módulo fixam a semântica escolhida: cálculo primário POR ANIMAL,
com o bloco publicado sendo a agregação ``any_track`` (ROI ocupada enquanto
qualquer animal estiver dentro) — a mesma leitura que o ``ArduinoEventMapper``
usa ao vivo.
"""

import math

import pandas as pd
import pytest
from shapely.geometry import Point, box

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer
from zebtrack.analysis.roi import ROI, ROIAnalyzer

# Arena 100x100 px = 100x100 cm (calibração 1:1). A ROI ocupa o terço ESQUERDO.
ARENA = [(0, 0), (100, 0), (100, 100), (0, 100)]
ROI_NAME = "Esquerda"
LEFT_ROI_PX = box(0, 0, 30, 100)

INSIDE_X = 15.0  # dentro da ROI
OUTSIDE_X = 85.0  # fora da ROI
MIDPOINT_X = (INSIDE_X + OUTSIDE_X) / 2  # 50.0 — o fantasma, fora de ambas


def _frame(rows: list[dict]) -> pd.DataFrame:
    """Monta o DataFrame de trajetória com bboxes de 2x2 px em torno do centro."""
    df = pd.DataFrame(rows)
    df["x1"] = df["x_center_px"] - 1.0
    df["x2"] = df["x_center_px"] + 1.0
    df["y1"] = df["y_center_px"] - 1.0
    df["y2"] = df["y_center_px"] + 1.0
    return df


def _build(rows: list[dict]) -> ROIAnalyzer:
    """ROIAnalyzer em modo NEUTRO: sem debounce, sem filtro de duração, sem teto.

    A camada temporal é neutralizada de propósito — aqui se mede o eixo de
    SUJEITO, e um ``min_visit_s`` ativo mataria visitas de poucos frames antes
    de a contagem por animal dizer qualquer coisa.
    """
    b_analyzer = ConcreteBehavioralAnalyzer(
        trajectory_df=_frame(rows),
        pixelcm_x=1.0,
        pixelcm_y=1.0,
        video_height_px=100,
        arena_polygon_px=ARENA,
        fps=10.0,
        window_length=1,
        polyorder=0,
    )
    return ROIAnalyzer(
        behavior_analyzer=b_analyzer,
        rois=[ROI(name=ROI_NAME, geometry=LEFT_ROI_PX, coordinate_space="px")],
        inclusion_rule="centroid_in",
        flutter_enter_frames=1,
        flutter_exit_frames=1,
        min_visit_s=0.0,
        min_gap_s=0.0,
        max_gap_s=math.inf,
    )


class TestGhostTrajectory:
    """Dois animais em posições OPOSTAS: o ponto médio cai fora de ambos."""

    @staticmethod
    def _opposed_rows(n_steps: int = 6) -> list[dict]:
        rows = []
        for step in range(n_steps):
            timestamp = step * 0.1
            rows.append(
                {
                    "timestamp": timestamp,
                    "track_id": 1,
                    "x_center_px": INSIDE_X,
                    "y_center_px": 50.0,
                }
            )
            rows.append(
                {
                    "timestamp": timestamp,
                    "track_id": 2,
                    "x_center_px": OUTSIDE_X,
                    "y_center_px": 50.0,
                }
            )
        return rows

    def test_midpoint_would_be_outside_the_roi(self):
        """Sanidade do cenário: o fantasma cai FORA — era esse o número antigo."""
        assert LEFT_ROI_PX.contains(Point(INSIDE_X, 50.0))
        assert not LEFT_ROI_PX.contains(Point(OUTSIDE_X, 50.0))
        assert not LEFT_ROI_PX.contains(Point(MIDPOINT_X, 50.0))

    def test_each_animal_is_accounted_for_separately(self):
        analyzer = _build(self._opposed_rows())

        by_track = analyzer.get_metrics_by_track()

        assert set(by_track) == {"1", "2"}
        # O peixe 1 passou a sessão INTEIRA dentro da ROI; o peixe 2, fora.
        assert by_track["1"]["tempo_gasto_por_roi"][ROI_NAME]["percentage"] == pytest.approx(100.0)
        assert by_track["2"]["tempo_gasto_por_roi"][ROI_NAME]["percentage"] == pytest.approx(0.0)

    def test_group_occupancy_is_total_because_one_animal_is_always_inside(self):
        """Semântica any_track: a ROI ficou ocupada o tempo todo."""
        analyzer = _build(self._opposed_rows())

        time_spent = analyzer.get_time_spent_in_rois()

        assert time_spent[ROI_NAME]["percentage"] == pytest.approx(100.0)

    def test_old_ghost_result_would_have_reported_zero(self):
        """Prova de que o resultado ANTIGO era errado, não apenas diferente.

        A média por timestamp punha o animal em x=50 (fora da ROI) e o
        relatório dizia 0% — apesar de um peixe nunca ter saído de lá.
        """
        analyzer = _build(self._opposed_rows())
        ghost_rows = [
            {"timestamp": step * 0.1, "track_id": 1, "x_center_px": MIDPOINT_X, "y_center_px": 50.0}
            for step in range(6)
        ]
        ghost = _build(ghost_rows)

        assert ghost.get_time_spent_in_rois()[ROI_NAME]["percentage"] == pytest.approx(0.0)
        assert analyzer.get_time_spent_in_rois()[ROI_NAME]["percentage"] == pytest.approx(100.0)


class TestPerTrackTransitions:
    """Entradas e saídas são independentes por animal."""

    @staticmethod
    def _interleaved_rows() -> list[dict]:
        """Peixe 1 entra e sai uma vez; peixe 2 fica sempre fora.

        As linhas são intercaladas por frame — exatamente o arranjo em que um
        ``.diff()`` global alterna entre sujeitos.
        """
        track1_x = [OUTSIDE_X, INSIDE_X, INSIDE_X, OUTSIDE_X, OUTSIDE_X]
        rows = []
        for step, x1 in enumerate(track1_x):
            timestamp = step * 0.1
            rows.append(
                {"timestamp": timestamp, "track_id": 1, "x_center_px": x1, "y_center_px": 50.0}
            )
            rows.append(
                {
                    "timestamp": timestamp,
                    "track_id": 2,
                    "x_center_px": OUTSIDE_X,
                    "y_center_px": 50.0,
                }
            )
        return rows

    def test_entries_and_exits_are_counted_per_animal(self):
        by_track = _build(self._interleaved_rows()).get_metrics_by_track()

        assert by_track["1"]["contagem_entradas"][ROI_NAME] == 1
        assert by_track["1"]["contagem_saidas"][ROI_NAME] == 1
        assert by_track["2"]["contagem_entradas"][ROI_NAME] == 0
        assert by_track["2"]["contagem_saidas"][ROI_NAME] == 0

    def test_interleaving_does_not_create_phantom_transitions(self):
        """O peixe 2 nunca entrou: intercalar linhas não pode inventar eventos."""
        analyzer = _build(self._interleaved_rows())

        # Ocupação de grupo: uma entrada e uma saída, as do peixe 1.
        assert analyzer.get_entry_counts()[ROI_NAME] == 1
        assert analyzer.get_exit_counts()[ROI_NAME] == 1

    def test_both_animals_visiting_separately_are_counted_separately(self):
        """Duas visitas em janelas diferentes: 2 por animal, 2 de ocupação."""
        rows = []
        track1_x = [INSIDE_X, INSIDE_X, OUTSIDE_X, OUTSIDE_X, OUTSIDE_X, OUTSIDE_X]
        track2_x = [OUTSIDE_X, OUTSIDE_X, OUTSIDE_X, OUTSIDE_X, INSIDE_X, INSIDE_X]
        for step, (x1, x2) in enumerate(zip(track1_x, track2_x, strict=True)):
            timestamp = step * 0.1
            rows.append(
                {"timestamp": timestamp, "track_id": 1, "x_center_px": x1, "y_center_px": 50.0}
            )
            rows.append(
                {"timestamp": timestamp, "track_id": 2, "x_center_px": x2, "y_center_px": 50.0}
            )

        analyzer = _build(rows)
        by_track = analyzer.get_metrics_by_track()

        assert by_track["1"]["contagem_saidas"][ROI_NAME] == 1
        assert by_track["2"]["contagem_entradas"][ROI_NAME] == 1
        # Ocupação: entra no início (peixe 1), esvazia, volta a encher (peixe 2).
        assert analyzer.get_entry_counts()[ROI_NAME] == 1
        assert analyzer.get_exit_counts()[ROI_NAME] == 1

    def test_simultaneous_entry_is_one_occupancy_but_two_animal_entries(self):
        """A diferença entre as duas semânticas, num único cenário."""
        rows = []
        pattern = [OUTSIDE_X, INSIDE_X, INSIDE_X, OUTSIDE_X]
        for step, x in enumerate(pattern):
            timestamp = step * 0.1
            for track in (1, 2):
                rows.append(
                    {
                        "timestamp": timestamp,
                        "track_id": track,
                        "x_center_px": x,
                        "y_center_px": 50.0,
                    }
                )

        analyzer = _build(rows)

        assert analyzer.get_entry_counts()[ROI_NAME] == 1, "a ROI foi ocupada uma vez"
        by_track = analyzer.get_metrics_by_track()
        assert by_track["1"]["contagem_entradas"][ROI_NAME] == 1
        assert by_track["2"]["contagem_entradas"][ROI_NAME] == 1


class TestSingleTrackRegression:
    """Caso majoritário: um animal. Nada pode mudar."""

    @staticmethod
    def _single_rows(with_track_column: bool = True) -> list[dict]:
        xs = [OUTSIDE_X, OUTSIDE_X, INSIDE_X, INSIDE_X, INSIDE_X, OUTSIDE_X, INSIDE_X]
        rows = []
        for step, x in enumerate(xs):
            row = {"timestamp": step * 0.1, "x_center_px": x, "y_center_px": 50.0}
            if with_track_column:
                row["track_id"] = 3
            rows.append(row)
        return rows

    def test_single_track_is_not_flagged_as_multi(self):
        analyzer = _build(self._single_rows())

        assert analyzer.is_multi_track is False
        assert analyzer.track_keys == []

    @pytest.mark.parametrize("with_track_column", [True, False])
    def test_group_metrics_match_the_direct_frame_calculation(self, with_track_column):
        """Com um sujeito a visão de grupo É a trajetória — mesmos números."""
        analyzer = _build(self._single_rows(with_track_column))

        # 2 entradas (frames 2 e 6) e 1 saída (frame 5).
        assert analyzer.get_entry_counts()[ROI_NAME] == 2
        assert analyzer.get_exit_counts()[ROI_NAME] == 1
        assert analyzer.get_latency_to_first_entry()[ROI_NAME] == pytest.approx(0.2)

    def test_per_track_block_matches_the_group_block(self):
        """Com um animal, as duas semânticas coincidem — e o teste prova."""
        analyzer = _build(self._single_rows())

        by_track = analyzer.get_metrics_by_track()
        assert len(by_track) == 1
        only = next(iter(by_track.values()))

        assert only["contagem_entradas"] == analyzer.get_entry_counts()
        assert only["contagem_saidas"] == analyzer.get_exit_counts()
        assert only["tempo_gasto_por_roi"] == analyzer.get_time_spent_in_rois()
        assert only["latencia_primeira_entrada"] == analyzer.get_latency_to_first_entry()
        assert only["distancia_por_roi"] == analyzer.get_distance_in_rois()


class TestGroupDistanceAndTime:
    """As agregações que NÃO são um simples OR de presença."""

    @staticmethod
    def _moving_rows() -> list[dict]:
        """Os dois peixes andam 1 cm por frame dentro da ROI."""
        rows = []
        for step in range(4):
            timestamp = step * 0.1
            rows.append(
                {
                    "timestamp": timestamp,
                    "track_id": 1,
                    "x_center_px": 10.0 + step,
                    "y_center_px": 50.0,
                }
            )
            rows.append(
                {
                    "timestamp": timestamp,
                    "track_id": 2,
                    "x_center_px": 20.0 + step,
                    "y_center_px": 50.0,
                }
            )
        return rows

    def test_distance_is_the_sum_of_the_individual_paths(self):
        analyzer = _build(self._moving_rows())

        # Cada peixe percorre 3 cm (4 frames, 3 segmentos) dentro da ROI.
        assert analyzer.get_distance_in_rois()[ROI_NAME] == pytest.approx(6.0)
        by_track = analyzer.get_metrics_by_track()
        assert by_track["1"]["distancia_por_roi"][ROI_NAME] == pytest.approx(3.0)
        assert by_track["2"]["distancia_por_roi"][ROI_NAME] == pytest.approx(3.0)

    def test_group_time_is_session_duration_not_animal_seconds(self):
        """A soma dos ``dt`` por linha daria 2x a sessão. A de grupo, não."""
        analyzer = _build(self._moving_rows())

        seconds = analyzer.get_time_spent_in_rois()[ROI_NAME]["seconds"]

        # 4 instantes espaçados de 0.1 s: 0.3 s de sessão observada.
        assert seconds == pytest.approx(0.3)
