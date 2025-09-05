import random


class BehavioralAnalyzer:
    """
    Analyzes the general behavior of an animal from trajectory data.
    This implementation returns random data to simulate a real analysis.
    """

    METRIC_KEYS = [
        "distancia_total_cm",
        "velocidade_media_cm_s",
        "velocidade_maxima_cm_s",
        "tempo_total_congelamento_s",
        "contagem_congelamentos",
        "tortuosidade_total",
        "indice_thigmotaxis_percentual",
        "distancia_media_parede_cm",
    ]

    def analyze(self, video_path: str) -> dict:
        """
        Executes a simulated behavioral analysis.

        Args:
            video_path: The path to the video file, used to seed variability.

        Returns:
            A dictionary containing the calculated behavioral metrics.
        """
        # Seeding based on the filename ensures some consistency, yet is random.
        seed = hash(video_path)
        random.seed(seed)

        return {
            "distancia_total_cm": random.uniform(100, 300),
            "velocidade_media_cm_s": random.uniform(2, 6),
            "velocidade_maxima_cm_s": random.uniform(5, 12),
            "tempo_total_congelamento_s": random.uniform(10, 90),
            "contagem_congelamentos": random.randint(5, 20),
            "tortuosidade_total": random.uniform(1.2, 3.5),
            "indice_thigmotaxis_percentual": random.uniform(40, 90),
            "distancia_media_parede_cm": random.uniform(1, 5),
        }
