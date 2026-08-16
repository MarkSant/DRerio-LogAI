"""Unit tests for BehavioralAnalyzer."""

from pathlib import Path

from zebtrack.analysis.behavioral_analyzer import BehavioralAnalyzer


def test_behavioral_analyzer_returns_expected_keys() -> None:
    analyzer = BehavioralAnalyzer()
    metrics = analyzer.analyze("video_sample.mp4")

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

    assert expected_keys.issubset(metrics.keys())
    assert isinstance(metrics["distancia_total_cm"], float)
    assert isinstance(metrics["contagem_congelamentos"], int)


def test_behavioral_analyzer_deterministic_seed_with_path_object() -> None:
    analyzer = BehavioralAnalyzer()
    path = Path("path/to/my_video.mp4")

    res1 = analyzer.analyze(path)
    res2 = analyzer.analyze(path)

    assert res1 == res2
