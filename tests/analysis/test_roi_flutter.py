"""Debounce com retrodatação e filtros de duração do ``ROIAnalyzer``.

Este módulo cobre a camada TEMPORAL da presença em ROI — quando uma leitura
crua vira uma visita — enquanto ``test_roi_analyzer.py`` cobre a camada
GEOMÉTRICA (a regra de inclusão frame a frame).

A ordem das operações é parte do contrato e está fixada aqui:
presença crua → debounce/retrodatação → filtro de duração → série estável.

Toda série é construída em espaço de pixels com ``centroid_in``, de modo que o
padrão de presença escrito no teste é EXATAMENTE o que o filtro recebe: os
valores esperados são calculados à mão, não observados.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from unittest.mock import MagicMock

import pandas as pd
import pytest
from shapely.geometry import Polygon

from zebtrack.analysis.roi import ROI, ROIAnalyzer

# ROI quadrada em pixels; "dentro" e "fora" são dois pontos fixos.
_ROI_POLY = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
_INSIDE = (50.0, 50.0)
_OUTSIDE = (500.0, 500.0)

#: Um frame = 0.1 s. Toda duração esperada nos testes é múltiplo disto.
_FRAME_MS = 100
_FRAME_S = _FRAME_MS / 1000.0

#: Padrão irregular de propósito para o teste de regressão: 5 entradas e 5
#: saídas, com sequências de 1 a 3 frames dos dois lados.
_NEUTRAL_PATTERN = [bool(int(flag)) for flag in "0101100111010010"]


def _analyzer(pattern: Sequence[bool], frame_ms: int = _FRAME_MS, **kwargs) -> ROIAnalyzer:
    """Analisador cuja presença CRUA é exatamente ``pattern``.

    Os parâmetros temporais nascem NEUTROS (sem debounce, sem limiar de
    duração, sem teto de ``dt``): cada teste liga só o mecanismo que exercita,
    para que uma falha aponte um mecanismo, não a soma deles.

    ``frame_ms`` muda a TAXA da série sem mudar o padrão — é como se testa que
    um limiar em segundos não é um limiar em frames disfarçado.
    """
    points = [_INSIDE if flag else _OUTSIDE for flag in pattern]
    timestamps = pd.date_range(start="2023-01-01", periods=len(points), freq=f"{frame_ms}ms")
    trajectory = pd.DataFrame(
        {
            "x_center_px": [p[0] for p in points],
            "y_center_px": [p[1] for p in points],
            "x1": [p[0] - 5 for p in points],
            "y1": [p[1] - 5 for p in points],
            "x2": [p[0] + 5 for p in points],
            "y2": [p[1] + 5 for p in points],
        },
        index=timestamps,
    )

    b_analyzer = MagicMock()
    b_analyzer.trajectory_data = trajectory
    b_analyzer._pixelcm_x = 1.0
    b_analyzer._pixelcm_y = 1.0
    b_analyzer._video_height_px = 0

    # O neutro só é imposto quando o teste NÃO usa a entrada legada — senão o
    # default do harness venceria justamente o que o teste quer exercitar.
    if "flutter_n_frames" not in kwargs:
        kwargs.setdefault("flutter_enter_frames", 1)
        kwargs.setdefault("flutter_exit_frames", 1)
    kwargs.setdefault("min_visit_s", 0.0)
    kwargs.setdefault("min_gap_s", 0.0)
    kwargs.setdefault("max_gap_s", math.inf)
    return ROIAnalyzer(
        behavior_analyzer=b_analyzer,
        rois=[ROI(name="R", geometry=_ROI_POLY, coordinate_space="px")],
        inclusion_rule="centroid_in",
        **kwargs,
    )


def _stable(analyzer: ROIAnalyzer) -> list[bool]:
    return [bool(value) for value in analyzer._trajectory["in_R_stable"]]


def _timestamp_at(analyzer: ROIAnalyzer, index: int):
    return analyzer._trajectory.index[index]


class TestBackdating:
    """A transição confirmada é registrada no PRIMEIRO frame da sequência."""

    def test_entry_is_recorded_at_the_first_frame_of_the_run(self) -> None:
        # F F T T T F F F -> com enter=3, a confirmação se completa no índice 4
        # mas a entrada vale desde o índice 2.
        pattern = [False, False, True, True, True, False, False, False]
        analyzer = _analyzer(pattern, flutter_enter_frames=3, flutter_exit_frames=1)

        assert _stable(analyzer) == [False, False, True, True, True, False, False, False]

        event_log = analyzer.get_event_log()
        entry = event_log[event_log["event"] == "enter"].iloc[0]
        assert entry["timestamp"] == _timestamp_at(analyzer, 2)
        # A janela retardatária antiga teria registrado aqui — é este atraso,
        # proporcional a N, que enviesava latência e tempo em ROI.
        assert entry["timestamp"] != _timestamp_at(analyzer, 4)

    def test_latency_to_first_entry_is_not_inflated_by_the_window(self) -> None:
        pattern = [False] * 5 + [True] * 5
        with_debounce = _analyzer(pattern, flutter_enter_frames=3, flutter_exit_frames=1)
        without = _analyzer(pattern)

        # Mesma latência com e sem debounce: filtrar ruído não custa viés.
        assert with_debounce.get_latency_to_first_entry()["R"] == pytest.approx(
            without.get_latency_to_first_entry()["R"]
        )
        assert with_debounce.get_latency_to_first_entry()["R"] == pytest.approx(5 * _FRAME_S)

    def test_run_shorter_than_the_window_is_never_confirmed(self) -> None:
        # Duas sequências de 2 frames com enter=3: nenhuma entra.
        pattern = [False, True, True, False, True, True, False]
        analyzer = _analyzer(pattern, flutter_enter_frames=3, flutter_exit_frames=1)
        assert not any(_stable(analyzer))
        assert analyzer.get_entry_counts()["R"] == 0


class TestAsymmetry:
    """Entrada e saída confirmam em janelas distintas."""

    def test_enter_two_exit_three_confirm_in_distinct_windows(self) -> None:
        # Índices:      0  1 | 2  3 | 4  5 | 6  7  8  9 | 10 11 12 | 13 14
        # Cru:          F  F | T  T | F  F | T  T  T  T |  F  F  F |  T  T
        #                      ^entra   ^lacuna de 2 < exit=3: NÃO sai
        #                                                ^3 >= exit=3: sai
        pattern = [False] * 2 + [True] * 2 + [False] * 2 + [True] * 4 + [False] * 3 + [True] * 2
        analyzer = _analyzer(pattern, flutter_enter_frames=2, flutter_exit_frames=3)

        # A entrada vale do índice 2 e a saída do índice 10, ambas retrodatadas.
        assert _stable(analyzer) == [False] * 2 + [True] * 8 + [False] * 3 + [True] * 2
        assert analyzer.get_entry_counts()["R"] == 2
        assert analyzer.get_exit_counts()["R"] == 1

    def test_one_frame_dropout_does_not_produce_an_exit_entry_pair(self) -> None:
        """Ruído T,F,T com exit=2: a saída nunca é confirmada."""
        pattern = [True, True, True, False, True, True, True]
        analyzer = _analyzer(pattern, flutter_enter_frames=2, flutter_exit_frames=2)

        assert all(_stable(analyzer))
        assert analyzer.get_exit_counts()["R"] == 0
        # O log tem só a entrada inicial — nenhum par saída+entrada espúrio.
        event_log = analyzer.get_event_log()
        assert list(event_log["event"]) == ["enter"]


class TestMinVisitDuration:
    """Visitas curtas demais somem das contagens e do log."""

    def test_visit_below_the_threshold_is_discarded(self) -> None:
        # Visita de um frame: do instante de entrada ao instante de saída = 0.1 s.
        pattern = [False, False, True, False, False, False]

        kept = _analyzer(pattern, min_visit_s=0.0)
        assert kept.get_entry_counts()["R"] == 1

        dropped = _analyzer(pattern, min_visit_s=0.2)
        assert dropped.get_entry_counts()["R"] == 0
        assert not any(_stable(dropped))
        assert dropped.get_event_log().empty

    def test_visit_exactly_at_the_threshold_is_kept(self) -> None:
        """O limiar é um mínimo INCLUSIVO: 0.2 s passa em ``min_visit_s=0.2``."""
        pattern = [False, True, True, False, False]
        analyzer = _analyzer(pattern, min_visit_s=0.2)
        assert analyzer.get_entry_counts()["R"] == 1

    def test_threshold_is_a_duration_not_a_frame_count(self) -> None:
        """O MESMO padrão sobrevive ou não conforme a taxa da série.

        É a razão de o limiar ser em segundos: mudar
        ``analysis_interval_frames`` muda a taxa, e um limiar em frames mudaria
        de significado em silêncio.
        """
        pattern = [False, False, True, False, False]
        assert _analyzer(pattern, frame_ms=100, min_visit_s=0.2).get_entry_counts()["R"] == 0
        assert _analyzer(pattern, frame_ms=2000, min_visit_s=0.2).get_entry_counts()["R"] == 1


class TestMinGapDuration:
    """Lacunas curtas demais fundem as visitas adjacentes."""

    def test_short_gap_merges_two_visits_into_one(self) -> None:
        pattern = [True, True, True, False, True, True, True]

        split = _analyzer(pattern, min_gap_s=0.0)
        assert split.get_exit_counts()["R"] == 1
        assert list(split.get_event_log()["event"]) == ["enter", "exit", "enter"]

        merged = _analyzer(pattern, min_gap_s=0.2)
        assert all(_stable(merged))
        assert merged.get_exit_counts()["R"] == 0
        assert list(merged.get_event_log()["event"]) == ["enter"]

    def test_merge_runs_before_the_visit_threshold(self) -> None:
        """Duas visitas curtas separadas por lacuna curta somam e sobrevivem.

        Se o limiar de visita rodasse ANTES da fusão, as duas seriam
        descartadas separadamente e a visita real desapareceria.
        """
        pattern = [False, True, False, True, False, False]
        analyzer = _analyzer(pattern, min_gap_s=0.2, min_visit_s=0.25)
        assert analyzer.get_entry_counts()["R"] == 1
        assert _stable(analyzer) == [False, True, True, True, False, False]


class TestNeutralModeIsBitIdentical:
    """Modo neutro reproduz o comportamento histórico, sem aproximação."""

    PATTERN = _NEUTRAL_PATTERN

    def test_stable_series_equals_raw_presence(self) -> None:
        analyzer = _analyzer(self.PATTERN)
        assert _stable(analyzer) == list(self.PATTERN)

    def test_dt_column_is_untouched(self) -> None:
        analyzer = _analyzer(self.PATTERN)
        expected = analyzer._trajectory.index.to_series().diff()
        pd.testing.assert_series_equal(analyzer._trajectory["dt"], expected, check_names=False)
        assert analyzer.unobserved_time_s == 0.0

    def test_metrics_match_the_hand_computed_values(self) -> None:
        analyzer = _analyzer(self.PATTERN)
        # 8 frames dentro; o primeiro frame da série não tem dt.
        inside_with_dt = sum(1 for i, flag in enumerate(self.PATTERN) if flag and i > 0)
        assert analyzer.get_time_spent_in_rois()["R"]["seconds"] == pytest.approx(
            inside_with_dt * _FRAME_S
        )
        assert analyzer.get_entry_counts()["R"] == 5
        assert analyzer.get_exit_counts()["R"] == 5


class TestLegacyParameter:
    """``flutter_n_frames`` continua aceito e mapeia para os dois lados."""

    def test_legacy_maps_to_both_windows(self) -> None:
        analyzer = _analyzer([False] * 4, flutter_n_frames=4)
        assert analyzer._flutter_enter == 4
        assert analyzer._flutter_exit == 4

    def test_explicit_windows_win_over_the_legacy_value(self) -> None:
        analyzer = _analyzer([False] * 4, flutter_n_frames=4, flutter_exit_frames=7)
        assert analyzer._flutter_enter == 4
        assert analyzer._flutter_exit == 7


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
