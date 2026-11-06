"""Testes unitários para ``HtmlReporter`` (relatório interativo Plotly).

Este módulo não tinha cobertura direta. O teste de caminho feliz exercita o
render completo do Plotly e revelou um bug: o código chamava
``fig.update_xaxis``/``fig.update_yaxis`` (singular), métodos inexistentes no
Plotly 6 — o correto é ``update_xaxes``/``update_yaxes``.
"""

from __future__ import annotations

import sys
from unittest.mock import PropertyMock, patch

import numpy as np
import pandas as pd
import pytest

from zebtrack.analysis.analysis_window_service import WindowBound, WindowResolution
from zebtrack.analysis.reporters import HtmlReporter


@pytest.mark.unit
class TestHtmlReporterHappyPath:
    """Geração bem-sucedida do relatório HTML interativo."""

    def test_export_generates_html_file(self, reporter_ctx, tmp_path):
        """Caminho feliz: gera arquivo .html contendo o experiment_id e plotly."""
        output = tmp_path / "report.html"

        HtmlReporter(reporter_ctx).export_interactive_html_report(output)

        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert "test_001" in content
        assert "plotly" in content.lower()

    def test_export_without_rois_still_generates(self, reporter_ctx_no_rois, tmp_path):
        """Sem r_analyzer (nenhuma ROI), o relatório gera pulando o gráfico de ROI."""
        output = tmp_path / "no_rois.html"

        HtmlReporter(reporter_ctx_no_rois).export_interactive_html_report(output)

        assert output.exists()
        assert output.stat().st_size > 0


@pytest.mark.unit
class TestHtmlReporterPathHandling:
    """Normalização do caminho de saída."""

    def test_path_without_html_extension_gets_suffix(self, reporter_ctx, tmp_path):
        """Caminho sem .html recebe o sufixo sem duplicar a extensão."""
        output = tmp_path / "relatorio_sem_extensao"

        HtmlReporter(reporter_ctx).export_interactive_html_report(output)

        generated = tmp_path / "relatorio_sem_extensao.html"
        assert generated.exists()
        assert not (tmp_path / "relatorio_sem_extensao.html.html").exists()

    def test_string_path_accepted(self, reporter_ctx, tmp_path):
        """Aceita caminho como str, não apenas Path."""
        output = str(tmp_path / "como_string.html")

        HtmlReporter(reporter_ctx).export_interactive_html_report(output)

        assert (tmp_path / "como_string.html").exists()


@pytest.mark.unit
class TestHtmlReporterErrorHandling:
    """Tratamento de erros e dependências."""

    def test_raises_value_error_without_behavior_analyzer(self, reporter_ctx, tmp_path):
        """b_analyzer ausente -> ValueError explícito."""
        reporter_ctx.b_analyzer = None

        with pytest.raises(ValueError, match="BehaviorAnalyzer"):
            HtmlReporter(reporter_ctx).export_interactive_html_report(tmp_path / "x.html")

    def test_raises_import_error_when_plotly_missing(self, reporter_ctx, tmp_path, monkeypatch):
        """Plotly ausente -> ImportError com mensagem de instalação."""
        # Força ImportError ao importar plotly dentro do método.
        monkeypatch.setitem(sys.modules, "plotly", None)
        monkeypatch.setitem(sys.modules, "plotly.graph_objects", None)
        monkeypatch.setitem(sys.modules, "plotly.subplots", None)

        with pytest.raises(ImportError, match="[Pp]lotly"):
            HtmlReporter(reporter_ctx).export_interactive_html_report(tmp_path / "x.html")


@pytest.mark.unit
class TestHtmlReporterEdgeCases:
    """Casos de borda científicos."""

    def test_time_axis_ignores_metadata_fps(self, reporter_ctx):
        """The index is the clock: no ``fps`` in the metadata, any ``fps`` there."""
        reporter_ctx.metadata = {"experiment_id": "no_fps"}
        without = _trace(HtmlReporter(reporter_ctx).build_figure(), "Velocity")
        reporter_ctx.metadata = {"experiment_id": "fps", "fps": 7.0}
        with_fps = _trace(HtmlReporter(reporter_ctx).build_figure(), "Velocity")

        assert list(without.x) == pytest.approx(list(with_fps.x))

    def test_no_freezing_episodes_skips_panel(self, reporter_ctx, tmp_path, monkeypatch):
        """Lista de freezing vazia -> painel pulado, sem crash."""
        monkeypatch.setattr(
            reporter_ctx.b_analyzer, "detect_freezing_episodes", lambda **kwargs: []
        )

        HtmlReporter(reporter_ctx).export_interactive_html_report(tmp_path / "no_freeze.html")

        assert (tmp_path / "no_freeze.html").exists()

    def test_roi_bar_chart_rendered_when_roi_time_present(self, reporter_ctx, tmp_path):
        """Com tempo de ROI não-vazio, o painel de barras de ROI é renderizado."""
        reporter_ctx.r_analyzer.get_time_spent_in_rois = lambda: {"ROI1": 5.0, "ROI2": 2.0}

        HtmlReporter(reporter_ctx).export_interactive_html_report(tmp_path / "roi.html")

        content = (tmp_path / "roi.html").read_text(encoding="utf-8")
        assert "ROI1" in content

    def test_missing_cm_columns_skips_trajectory_panel(self, reporter_ctx, tmp_path):
        """Sem colunas x_cm/y_cm -> painel de trajetória pulado, relatório gera."""
        df = reporter_ctx.b_analyzer.trajectory_data
        df_no_cm = df.drop(columns=[c for c in ("x_cm", "y_cm") if c in df.columns])

        # ``trajectory_data`` é uma property somente-leitura; sobrescrevemos no tipo.
        with patch.object(
            type(reporter_ctx.b_analyzer),
            "trajectory_data",
            new_callable=PropertyMock,
            return_value=df_no_cm,
        ):
            HtmlReporter(reporter_ctx).export_interactive_html_report(tmp_path / "no_cm.html")

        assert (tmp_path / "no_cm.html").exists()


def _trace(fig, name: str):
    matches = [trace for trace in fig.data if trace.name == name]
    assert len(matches) == 1, [trace.name for trace in fig.data]
    return matches[0]


def _moves_then_freezes() -> pd.DataFrame:
    """10 Hz from t = 5 s (a cut video's PTS): 1 s moving, then 5 s still."""
    t = 5.0 + np.arange(60) / 10
    x = np.where(t < 6.0, 10 + (t - 5.0) * 200, 210.0)
    return pd.DataFrame(
        {
            "timestamp": t,
            "frame": np.arange(50, 110),
            "track_id": 1,
            "x1": x - 10,
            "y1": 90.0,
            "x2": x + 10,
            "y2": 110.0,
            "confidence": 0.9,
        }
    )


@pytest.mark.unit
class TestHtmlReporterTimeAndFreezing:
    """#639: seconds from the recording clock and the real ``Episode`` keys."""

    def test_freezing_panel_reads_the_real_episode_keys(
        self, build_reporter_context, reporter_mock_settings, tmp_path
    ):
        ctx = build_reporter_context(reporter_mock_settings, _moves_then_freezes(), [])
        episodes = ctx.b_analyzer.detect_freezing_episodes(
            min_duration=ctx.freezing_duration, vel_threshold=ctx.freezing_threshold
        )
        assert episodes, "the fixture must freeze for the panel to be drawn"

        fig = HtmlReporter(ctx).build_figure()
        HtmlReporter(ctx).export_interactive_html_report(tmp_path / "freeze.html")

        freezing = _trace(fig, "Freezing Episodes")
        assert list(freezing.x) == pytest.approx(
            [ep["start_time"].total_seconds() - 5.0 for ep in episodes]
        )
        assert list(freezing.y) == pytest.approx([ep["duration"] for ep in episodes])
        assert (tmp_path / "freeze.html").exists()

    def test_velocity_time_is_seconds_since_the_first_sample(
        self, build_reporter_context, reporter_mock_settings
    ):
        ctx = build_reporter_context(reporter_mock_settings, _moves_then_freezes(), [])

        velocity = _trace(HtmlReporter(ctx).build_figure(), "Velocity")

        assert list(velocity.x) == pytest.approx([i / 10 for i in range(60)])

    def test_window_axis_starts_at_start(self, build_reporter_context, reporter_mock_settings):
        window = WindowResolution(
            status="complete",
            spec_hash="sha256:" + "a" * 64,
            # Between two samples, so START and the first sample differ.
            start=WindowBound(60, 6.05, "persist"),
            stop=WindowBound(100, 10.0, "delay"),
        )
        ctx = build_reporter_context(
            reporter_mock_settings, _moves_then_freezes(), [], window=window
        )

        fig = HtmlReporter(ctx).build_figure()

        velocity = _trace(fig, "Velocity")
        assert velocity.x[0] == pytest.approx(0.05)
        assert velocity.x[-1] == pytest.approx(3.95)
        assert fig.layout.xaxis2.title.text == "Time since window START (s)"
