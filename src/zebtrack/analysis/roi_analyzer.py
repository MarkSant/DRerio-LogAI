import random


class ROIAnalyzer:
    """
    A class for analyzing behavior in relation to Regions of Interest (ROIs).
    This implementation returns random data to simulate a real analysis.
    """

    def analyze(self, video_path: str, rois: dict = None) -> dict:
        """
        Runs a simulated ROI analysis.

        Args:
            video_path: The path to the video file (used to add variability).
            rois: ROI definitions (not used in the simulation).

        Returns:
            A nested dictionary with metrics for each ROI.
        """
        # Seeding based on the filename ensures some consistency, while still
        # being random
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
