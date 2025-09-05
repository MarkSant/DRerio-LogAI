import random

class ROIAnalyzer:
    """
    A classe para analisar o comportamento em relação a Regiões de Interesse (ROIs).
    Esta implementação retorna dados aleatórios para simular uma análise real.
    """

    def analyze(self, video_path: str, rois: dict = None) -> dict:
        """
        Executa uma análise de ROI simulada.

        Args:
            video_path: O caminho para o arquivo de vídeo (usado para adicionar variabilidade).
            rois: Definições de ROI (não utilizado na simulação).

        Returns:
            Um dicionário aninhado com métricas para cada ROI.
        """
        # A semente baseada no nome do arquivo garante alguma consistência, mas ainda aleatória
        seed = hash(video_path)
        random.seed(seed)

        mock_results = {}
        # Simula resultados para um conjunto padrão de ROIs
        for roi_name in ["zona_superior", "zona_media", "zona_inferior"]:
            mock_results[roi_name] = {
                "tempo_roi_s": random.uniform(10, 120),
                "latencia_roi_s": random.uniform(5, 60),
                "entradas_roi_n": random.randint(0, 15),
            }

        return mock_results
