import random

class BehavioralAnalyzer:
    """
    A classe para analisar o comportamento geral de um animal a partir de dados de trajetória.
    Esta implementação retorna dados aleatórios para simular uma análise real.
    """

    def analyze(self, video_path: str) -> dict:
        """
        Executa uma análise comportamental simulada.

        Args:
            video_path: O caminho para o arquivo de vídeo (usado para adicionar variabilidade).

        Returns:
            Um dicionário contendo as métricas comportamentais calculadas.
        """
        # A semente baseada no nome do arquivo garante alguma consistência, mas ainda aleatória
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
