"""Agregação de duplicatas de timestamp em ``BehavioralAnalyzer._preprocess_data``.

A agregação existe para consolidar duplicatas que o rastreador gera para o MESMO
animal. Estes testes fixam a fronteira: duplicata do mesmo track continua sendo
média; animais distintos no mesmo instante NUNCA são fundidos.
"""

import numpy as np
import pandas as pd
import pytest

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer

ARENA = [(0, 0), (100, 0), (100, 100), (0, 100)]


def _analyzer(df: pd.DataFrame) -> ConcreteBehavioralAnalyzer:
    """Analisador com suavização desligada (window_length=1, polyorder=0)."""
    return ConcreteBehavioralAnalyzer(
        trajectory_df=df.copy(),
        pixelcm_x=1.0,
        pixelcm_y=1.0,
        video_height_px=100,
        arena_polygon_px=ARENA,
        fps=10.0,
        window_length=1,
        polyorder=0,
    )


def _frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for col, offset in (("x1", -1.0), ("x2", 1.0)):
        df[col] = df["x_center_px"] + offset
    for col, offset in (("y1", -1.0), ("y2", 1.0)):
        df[col] = df["y_center_px"] + offset
    return df


class TestSameTrackDuplicates:
    """Duplicata do mesmo animal: comportamento histórico preservado."""

    def test_same_track_duplicate_is_averaged(self):
        df = _frame(
            [
                {"timestamp": 0.0, "track_id": 1, "x_center_px": 10.0, "y_center_px": 20.0},
                {"timestamp": 0.0, "track_id": 1, "x_center_px": 30.0, "y_center_px": 40.0},
                {"timestamp": 0.1, "track_id": 1, "x_center_px": 50.0, "y_center_px": 60.0},
            ]
        )

        data = _analyzer(df).trajectory_data

        assert len(data) == 2, "as duas linhas do mesmo track no t=0 deviam virar uma"
        assert data["x_center_px"].iloc[0] == pytest.approx(20.0)
        assert data["y_center_px"].iloc[0] == pytest.approx(30.0)

    def test_duplicates_without_track_id_still_averaged(self):
        """Sem ``track_id`` não há como distinguir sujeitos — média é tudo que resta."""
        df = _frame(
            [
                {"timestamp": 0.0, "x_center_px": 10.0, "y_center_px": 10.0},
                {"timestamp": 0.0, "x_center_px": 30.0, "y_center_px": 30.0},
            ]
        )

        data = _analyzer(df).trajectory_data

        assert len(data) == 1
        assert data["x_center_px"].iloc[0] == pytest.approx(20.0)


class TestDistinctTracksAreNotMerged:
    """O defeito corrigido: dois peixes viravam um fantasma no ponto médio."""

    def test_distinct_tracks_at_same_timestamp_are_kept_apart(self):
        df = _frame(
            [
                {"timestamp": 0.0, "track_id": 1, "x_center_px": 10.0, "y_center_px": 50.0},
                {"timestamp": 0.0, "track_id": 2, "x_center_px": 90.0, "y_center_px": 50.0},
            ]
        )

        analyzer = _analyzer(df)
        data = analyzer.trajectory_data

        assert len(data) == 2, "os dois animais não podem ser fundidos"
        assert analyzer.is_multi_track is True
        assert set(data["track_id"].tolist()) == {1, 2}
        # O ponto médio (50.0) é a posição FANTASMA: ninguém esteve ali.
        assert 50.0 not in set(data["x_center_px"].tolist())

    def test_same_track_duplicates_merge_within_each_animal(self):
        """As duas regras convivem: funde por (timestamp, track), não por timestamp."""
        df = _frame(
            [
                {"timestamp": 0.0, "track_id": 1, "x_center_px": 10.0, "y_center_px": 50.0},
                {"timestamp": 0.0, "track_id": 1, "x_center_px": 20.0, "y_center_px": 50.0},
                {"timestamp": 0.0, "track_id": 2, "x_center_px": 90.0, "y_center_px": 50.0},
            ]
        )

        data = _analyzer(df).trajectory_data

        assert len(data) == 2
        by_track = data.set_index("track_id")["x_center_px"]
        assert by_track.loc[1] == pytest.approx(15.0), "duplicata do track 1 vira média"
        assert by_track.loc[2] == pytest.approx(90.0), "track 2 fica intacto"


class TestDerivedMetricsRespectTrackBoundaries:
    """Distância/velocidade não podem medir o espaço ENTRE dois peixes."""

    def _two_static_animals(self) -> pd.DataFrame:
        rows = []
        for step in range(5):
            rows.append(
                {
                    "timestamp": step * 0.1,
                    "track_id": 1,
                    "x_center_px": 10.0,
                    "y_center_px": 50.0,
                }
            )
            rows.append(
                {
                    "timestamp": step * 0.1,
                    "track_id": 2,
                    "x_center_px": 90.0,
                    "y_center_px": 50.0,
                }
            )
        return _frame(rows)

    def test_static_animals_travel_zero_distance(self):
        """Dois peixes parados: distância total é 0, não 80 cm por frame."""
        analyzer = _analyzer(self._two_static_animals())

        assert analyzer.calculate_total_distance() == pytest.approx(0.0)

    def test_static_animals_have_zero_velocity(self):
        analyzer = _analyzer(self._two_static_animals())

        v_mag = analyzer.calculate_velocity_timeseries()["v_mag"].dropna()

        assert v_mag.to_numpy() == pytest.approx(np.zeros(len(v_mag)))

    def test_single_track_distance_matches_manual_sum(self):
        """Regressão: com um animal o resultado é o cálculo direto de sempre."""
        df = _frame(
            [
                {"timestamp": 0.0, "track_id": 7, "x_center_px": 0.0, "y_center_px": 50.0},
                {"timestamp": 0.1, "track_id": 7, "x_center_px": 3.0, "y_center_px": 50.0},
                {"timestamp": 0.2, "track_id": 7, "x_center_px": 7.0, "y_center_px": 50.0},
            ]
        )

        analyzer = _analyzer(df)

        assert analyzer.is_multi_track is False
        assert analyzer.calculate_total_distance() == pytest.approx(7.0)


class TestMaxTimeGapExcludesTheSegment:
    """``max_time_gap`` tem de zerar o SEGMENTO, não descartar a linha."""

    @staticmethod
    def _rows_with_gap() -> pd.DataFrame:
        """1 cm por frame; entre t=0.2 e t=5.2 há uma lacuna com salto de 50 cm."""
        return _frame(
            [
                {"timestamp": 0.0, "track_id": 1, "x_center_px": 10.0, "y_center_px": 50.0},
                {"timestamp": 0.1, "track_id": 1, "x_center_px": 11.0, "y_center_px": 50.0},
                {"timestamp": 0.2, "track_id": 1, "x_center_px": 12.0, "y_center_px": 50.0},
                {"timestamp": 5.2, "track_id": 1, "x_center_px": 62.0, "y_center_px": 50.0},
                {"timestamp": 5.3, "track_id": 1, "x_center_px": 63.0, "y_center_px": 50.0},
                {"timestamp": 5.4, "track_id": 1, "x_center_px": 64.0, "y_center_px": 50.0},
            ]
        )

    def test_gap_segment_contributes_zero(self):
        """A implementação antiga descartava a LINHA do reaparecimento.

        Com isso o frame seguinte (x=63) virava vizinho do último frame antes
        da lacuna (x=12) e os 50 cm atravessados continuavam sendo somados —
        só que atribuídos a outro par. O total só caía de 54 para 53 cm.
        """
        analyzer = _analyzer(self._rows_with_gap())

        # Sem teto: 2 + 50 + 2 = 54 cm.
        assert analyzer.calculate_total_distance() == pytest.approx(54.0)
        # Com teto: só os 4 segmentos de 1 cm sobrevivem.
        assert analyzer.calculate_total_distance(max_time_gap=1.0) == pytest.approx(4.0)

    def test_gap_is_evaluated_per_track(self):
        """Com dois animais, a lacuna de um não pode cortar o segmento do outro."""
        rows = []
        for step, timestamp in enumerate([0.0, 0.1, 0.2]):
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
                    "x_center_px": 80.0 + step,
                    "y_center_px": 50.0,
                }
            )

        analyzer = _analyzer(_frame(rows))

        # Dois animais, 2 cm cada, nenhum intervalo acima do teto.
        assert analyzer.calculate_total_distance(max_time_gap=1.0) == pytest.approx(4.0)
