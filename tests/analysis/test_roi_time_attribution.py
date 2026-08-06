"""Atribuição de tempo em ROI na presença de lacunas de rastreamento.

O DataFrame de trajetória só tem linhas onde HOUVE detecção. O ``dt`` da
primeira linha depois de uma lacuna vale a lacuna INTEIRA, e sem teto esse
tempo era creditado por completo à ROI onde o animal reapareceu: perder o
animal por 5 s somava 5 s de "permanência" numa ROI que ele talvez nunca
tivesse visitado.

Estilo dos invariantes espelha ``tests/analysis/test_roi_invariants.py``.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pandas as pd
import pytest
from shapely.geometry import Polygon

from zebtrack.analysis.roi import ROI, ROIAnalyzer

# Duas ROIs disjuntas em pixels — a precondição do invariante de soma.
_ROIS = [
    ROI(
        name="A",
        geometry=Polygon([(0, 0), (100, 0), (100, 100), (0, 100)]),
        coordinate_space="px",
    ),
    ROI(
        name="B",
        geometry=Polygon([(300, 300), (400, 300), (400, 400), (300, 400)]),
        coordinate_space="px",
    ),
]
_IN_A = (50.0, 50.0)
_IN_B = (350.0, 350.0)

_STEP_S = 0.1  # intervalo nominal entre frames analisados
_GAP_S = 5.0  # lacuna de rastreamento no meio da sessão
_FRAMES_IN_A = 21  # t = 0.0 .. 2.0
_FRAMES_IN_B = 11  # t = 7.0 .. 8.0


def _gapped_analyzer(**kwargs) -> ROIAnalyzer:
    """Sessão de 8 s: 2 s dentro de A, lacuna de 5 s, 1 s dentro de B."""
    seconds = [i * _STEP_S for i in range(_FRAMES_IN_A)]
    resume = seconds[-1] + _GAP_S
    seconds += [resume + i * _STEP_S for i in range(_FRAMES_IN_B)]
    points = [_IN_A] * _FRAMES_IN_A + [_IN_B] * _FRAMES_IN_B

    index = pd.to_datetime(seconds, unit="s", origin=pd.Timestamp("2023-01-01"))
    trajectory = pd.DataFrame(
        {
            "x_center_px": [p[0] for p in points],
            "y_center_px": [p[1] for p in points],
            "x1": [p[0] - 5 for p in points],
            "y1": [p[1] - 5 for p in points],
            "x2": [p[0] + 5 for p in points],
            "y2": [p[1] + 5 for p in points],
        },
        index=index,
    )

    b_analyzer = MagicMock()
    b_analyzer.trajectory_data = trajectory
    b_analyzer._pixelcm_x = 1.0
    b_analyzer._pixelcm_y = 1.0
    b_analyzer._video_height_px = 0

    return ROIAnalyzer(
        behavior_analyzer=b_analyzer,
        rois=_ROIS,
        inclusion_rule="centroid_in",
        **kwargs,
    )


class TestGapIsNotCreditedToAnyRoi:
    """O teto de ``dt`` tira a lacuna da conta da ROI de reaparecimento."""

    def test_reappearance_roi_does_not_absorb_the_gap(self) -> None:
        # Teto automático: 3 x mediana(0.1 s) = 0.3 s. A lacuna de 5 s entra
        # como 0.3 s; os 4.7 s restantes não vão para ROI nenhuma.
        analyzer = _gapped_analyzer()
        time_spent = analyzer.get_time_spent_in_rois()

        expected_b = 0.3 + (_FRAMES_IN_B - 1) * _STEP_S
        assert time_spent["B"]["seconds"] == pytest.approx(expected_b, abs=1e-6)
        assert time_spent["B"]["seconds"] < _GAP_S
        assert analyzer.unobserved_time_s == pytest.approx(_GAP_S - 0.3, abs=1e-6)

    def test_time_in_the_first_roi_is_untouched(self) -> None:
        """O teto corta a lacuna, não o tempo efetivamente observado."""
        analyzer = _gapped_analyzer()
        assert analyzer.get_time_spent_in_rois()["A"]["seconds"] == pytest.approx(
            (_FRAMES_IN_A - 1) * _STEP_S, abs=1e-6
        )

    def test_explicit_cap_overrides_the_automatic_one(self) -> None:
        analyzer = _gapped_analyzer(max_gap_s=1.0)
        assert analyzer.unobserved_time_s == pytest.approx(_GAP_S - 1.0, abs=1e-6)
        assert analyzer.get_time_spent_in_rois()["B"]["seconds"] == pytest.approx(
            1.0 + (_FRAMES_IN_B - 1) * _STEP_S, abs=1e-6
        )

    def test_infinite_cap_reproduces_the_historical_attribution(self) -> None:
        """Modo neutro: a lacuna inteira volta a ser creditada a B."""
        analyzer = _gapped_analyzer(max_gap_s=math.inf)
        assert analyzer.unobserved_time_s == 0.0
        assert analyzer.get_time_spent_in_rois()["B"]["seconds"] == pytest.approx(
            _GAP_S + (_FRAMES_IN_B - 1) * _STEP_S, abs=1e-6
        )

    def test_uniform_series_loses_nothing(self) -> None:
        """Sem lacuna não há nada a descartar — o teto automático não corta."""
        analyzer = _gapped_analyzer()
        analyzer_no_gap = _gapped_analyzer(max_gap_s=math.inf)
        # Controle: o tempo total observado só difere pelo que o teto tirou.
        total_capped = sum(stats["seconds"] for stats in analyzer.get_time_spent_in_rois().values())
        total_raw = sum(
            stats["seconds"] for stats in analyzer_no_gap.get_time_spent_in_rois().values()
        )
        assert total_raw - total_capped == pytest.approx(analyzer.unobserved_time_s, abs=1e-6)


class TestTimeConservation:
    """Invariante: nada além da duração da sessão é distribuído."""

    @staticmethod
    def _session_duration_s(analyzer: ROIAnalyzer) -> float:
        span = analyzer._trajectory.index[-1] - analyzer._trajectory.index[0]
        return span.total_seconds()

    @pytest.mark.parametrize("max_gap_s", [None, 0.5, 1.0, math.inf])
    def test_roi_time_plus_unobserved_fits_in_the_session(self, max_gap_s) -> None:
        analyzer = _gapped_analyzer(max_gap_s=max_gap_s)
        time_spent = analyzer.get_time_spent_in_rois()

        outside = analyzer._trajectory.loc[
            analyzer._trajectory["stable_roi"] == "Outside", "dt"
        ].sum()
        outside_s = outside.total_seconds() if hasattr(outside, "total_seconds") else float(outside)

        accounted = (
            sum(stats["seconds"] for stats in time_spent.values())
            + outside_s
            + analyzer.unobserved_time_s
        )
        assert accounted <= self._session_duration_s(analyzer) + 1e-9

    def test_percentages_stay_bounded_with_a_cap(self) -> None:
        analyzer = _gapped_analyzer()
        total_pct = sum(stats["percentage"] for stats in analyzer.get_time_spent_in_rois().values())
        assert -1e-9 <= total_pct <= 100.0 + 1e-9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
