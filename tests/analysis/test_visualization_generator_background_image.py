import numpy as np


class _FakeBehavioralAnalyzer:
    def __init__(self):
        # Minimal fields used by VisualizationGenerator.generate_trajectory_plot
        self.trajectory_data = {
            "x_cm_smoothed": np.array([0.0, 1.0, 2.0], dtype=float),
            "y_cm_smoothed": np.array([0.0, 1.0, 0.0], dtype=float),
        }

        # Shapely is an optional dependency in many environments, but ZebTrack-AI uses it.
        from shapely.geometry import Polygon

        self.arena_polygon_cm = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        self._pixelcm_x = 10.0
        self._pixelcm_y = 10.0


def test_generate_trajectory_plot_uses_imread_for_png_background(monkeypatch, tmp_path):
    # Create a dummy existing .png path (content doesn't matter because we monkeypatch imread).
    png_path = tmp_path / "bg.png"
    png_path.write_bytes(b"not-a-real-png")

    import cv2

    # If VideoCapture is called for a .png, this is a regression.
    def _video_capture_fail(*args, **kwargs):
        raise AssertionError("cv2.VideoCapture should not be used for image backgrounds")

    monkeypatch.setattr(cv2, "VideoCapture", _video_capture_fail)

    # Ensure imread is used and returns a synthetic frame.
    def _imread_ok(_path):
        return np.zeros((20, 30, 3), dtype=np.uint8)

    monkeypatch.setattr(cv2, "imread", _imread_ok)

    from zebtrack.analysis.visualization_generator import VisualizationGenerator

    vg = VisualizationGenerator(
        b_analyzer=_FakeBehavioralAnalyzer(),
        metadata={"experiment_id": "exp_test"},
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=200,
    )

    fig = vg.generate_trajectory_plot(video_path=str(png_path))
    assert fig is not None
