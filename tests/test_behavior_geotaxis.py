import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock
from zebtrack.analysis.behavior import BehavioralAnalyzer


@pytest.fixture
def sample_trajectory_df():
    """Create a sample trajectory dataframe."""
    frames = 100
    df = pd.DataFrame(
        {
            "timestamp": np.linspace(0, 10, frames),
            "frame_idx": range(frames),
            # Simulated movement in pixels (0-100)
            "x_center_px": np.linspace(10, 90, frames),
            "y_center_px": np.linspace(10, 90, frames),  # Moving from top (0) to bottom (100)
            "x1": np.zeros(frames),
            "y1": np.zeros(frames),
            "x2": np.zeros(frames),
            "y2": np.zeros(frames),
        }
    )
    return df


class MockBehavioralAnalyzer(BehavioralAnalyzer):
    """Concrete implementation for testing ABC."""

    def calculate_thigmotaxis_index(self, *args, **kwargs):
        pass

    def calculate_immobility_ratio(self, *args, **kwargs):
        pass

    def calculate_mean_speed(self, *args, **kwargs):
        pass

    def calculate_total_distance(self, *args, **kwargs):
        pass

    def calculate_angular_velocity(self, *args, **kwargs):
        pass

    def detect_sharp_turns(self, *args, **kwargs):
        pass

    def detect_speed_bursts(self, *args, **kwargs):
        pass


@pytest.fixture
def analyzer(sample_trajectory_df):
    """Create a mock analyzer instance."""
    # Scale: 10px = 1cm.
    # Video height: 100px -> 10cm.
    # Arena polygon: 100x100 box.
    pixelcm_x = 0.1
    pixelcm_y = 0.1
    video_height_px = 100
    arena_polygon = [(0, 0), (100, 0), (100, 100), (0, 100)]

    return MockBehavioralAnalyzer(
        trajectory_df=sample_trajectory_df,
        pixelcm_x=pixelcm_x,
        pixelcm_y=pixelcm_y,
        video_height_px=video_height_px,
        arena_polygon_px=arena_polygon,
        fps=10.0,
    )


def test_geotaxis_average_distance(analyzer):
    """Test average distance from bottom."""
    # Data moves from y=10 to y=90.
    # Bottom is at y=100 (in pixel coords if Y increases downwards).
    # Wait, behavior.py logic: default is Y increases downwards?
    # Usually OpenCV coords: 0,0 is top-left.
    # Analyzer converts to cm.
    # If video_height_px=100.
    # point y=90 -> distance from bottom (100) is 10px = 1cm.
    # point y=10 -> distance from bottom (100) is 90px = 9cm.
    # Average should be around 5cm.

    result = analyzer.calculate_geotaxis_index(method="average_distance")
    assert result == pytest.approx(5.0, abs=0.5)


def test_geotaxis_time_near_bottom(analyzer):
    """Test time spent near bottom."""
    # Threshold 2cm = 20px.
    # Bottom is 100px. Region: 80-100px.
    # Data moves linearly 10->90.
    # It enters 80px at frame 87 (approx).
    # So roughly 12-13% of time near bottom?
    # Wait, max y is 90. So it is in [80, 90] range for the last segment.
    # 10->90 range is 80px span. 80->90 is 10px span.
    # That is 1/8th of the travel. 12.5%.

    result = analyzer.calculate_geotaxis_index(method="time_near_bottom", distance_threshold=2.0)
    assert result == pytest.approx(12.5, abs=5.0)


def test_geotaxis_zone_time(analyzer):
    """Test normalized time in vertical zones."""
    # 3 zones (Top, Middle, Bottom).
    # 0-33, 33-66, 66-100.
    # Data 10-90.
    # Zone 1 (Top): 10-33. (23 range)
    # Zone 2 (Mid): 33-66. (33 range)
    # Zone 3 (Bot): 66-90. (24 range)
    # Roughly even distribution but slightly less in top/bot due to start/end points.

    result = analyzer.calculate_geotaxis_index(method="zone_time", num_zones=3, bottom_zones=1)

    assert "zone_1_pct" in result
    assert "zone_2_pct" in result
    assert "zone_3_pct" in result
    assert "bottom_zones_pct" in result

    total = sum(result[k] for k in ["zone_1_pct", "zone_2_pct", "zone_3_pct"])
    assert total == pytest.approx(100.0, abs=1.0)
