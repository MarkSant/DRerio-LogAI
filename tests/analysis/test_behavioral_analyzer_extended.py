"""
Extended unit tests for mock BehavioralAnalyzer simulation in analysis/behavioral_analyzer.py.
"""

from __future__ import annotations

from pathlib import Path

from zebtrack.analysis.behavioral_analyzer import BehavioralAnalyzer


class TestBehavioralAnalyzerExtended:
    """Test simulated BehavioralAnalyzer output consistency and key coverage."""

    def test_analyze_output_keys(self):
        analyzer = BehavioralAnalyzer()
        metrics = analyzer.analyze("sample_video.mp4")

        expected_keys = {
            "distancia_total_cm",
            "velocidade_media_cm_s",
            "velocidade_maxima_cm_s",
            "tempo_total_congelamento_s",
            "contagem_congelamentos",
            "tortuosidade_total",
            "indice_thigmotaxis_percentual",
            "distancia_media_parede_cm",
        }
        assert set(metrics.keys()) == expected_keys
        for v in metrics.values():
            assert isinstance(v, int | float)
            assert v >= 0

    def test_analyze_deterministic_for_same_path(self):
        analyzer = BehavioralAnalyzer()
        res1 = analyzer.analyze("/path/to/test_video.mp4")
        res2 = analyzer.analyze(Path("/path/to/test_video.mp4"))
        assert res1 == res2

    def test_analyze_variability_with_different_paths(self):
        analyzer = BehavioralAnalyzer()
        res1 = analyzer.analyze("video_alpha.mp4")
        res2 = analyzer.analyze("video_beta.mp4")
        # Different paths yield different random seed values
        assert res1["distancia_total_cm"] != res2["distancia_total_cm"]
