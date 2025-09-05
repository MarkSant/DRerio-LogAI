import random


class BehavioralAnalyzer:
    """
    A class to analyze the general behavior of an animal from trajectory data.
    This implementation returns random data to simulate a real analysis.
    """

    def analyze(self, video_path: str) -> dict:
        """
        Runs a simulated behavioral analysis.

        Args:
            video_path: The path to the video file, used to add variability.

        Returns:
            A dictionary containing the calculated behavioral metrics.
        """
        # Seeding based on the filename ensures some consistency, while still
        # being random
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
