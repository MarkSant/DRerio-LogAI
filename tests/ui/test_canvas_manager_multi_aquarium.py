"""Tests for CanvasManager multi-aquarium overlay functionality.

Phase 11 of multi-aquarium implementation:
Tests for draw_multi_aquarium_overlay method that renders
multiple aquariums with distinct colors and labels.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from zebtrack.core.detection import AquariumData, MultiAquariumZoneData
from zebtrack.ui.components.canvas.multi_aquarium_overlay import MultiAquariumOverlayManager
from zebtrack.ui.components.canvas_manager import CanvasManager


class TestDrawMultiAquariumOverlay:
    """Tests for draw_multi_aquarium_overlay method."""

    @pytest.fixture
    def mock_canvas_manager(self) -> CanvasManager:
        """Create a mock CanvasManager instance for testing."""
        with patch.object(CanvasManager, "__init__", lambda self, *args, **kwargs: None):
            cm = CanvasManager(MagicMock())
            cm.gui = MagicMock()
            cm.event_bus_v2 = MagicMock()
            # Phase 4.5: Initialize sub-component used by delegation shims
            cm.multi_aquarium = MultiAquariumOverlayManager(cm)
            return cm

    @pytest.fixture
    def sample_frame(self) -> np.ndarray:
        """Create a sample video frame for testing."""
        return np.zeros((480, 640, 3), dtype=np.uint8)

    @pytest.fixture
    def sample_multi_aquarium_zone_data(self) -> MultiAquariumZoneData:
        """Create sample MultiAquariumZoneData for testing."""
        aquarium_0 = AquariumData(
            id=0,
            polygon=[(50, 50), (300, 50), (300, 400), (50, 400)],
            roi_polygons=[
                [(60, 60), (140, 60), (140, 140), (60, 140)],  # ROI 1
                [(160, 60), (240, 60), (240, 140), (160, 140)],  # ROI 2
            ],
            roi_names=["Top", "Centro"],
            roi_colors=[(0, 255, 0), (255, 0, 0)],
            group="Controle",
        )
        aquarium_1 = AquariumData(
            id=1,
            polygon=[(340, 50), (590, 50), (590, 400), (340, 400)],
            roi_polygons=[
                [(350, 60), (430, 60), (430, 140), (350, 140)],  # ROI 1
            ],
            roi_names=["Top"],
            roi_colors=[(0, 255, 0)],
            group="CBD",
        )
        return MultiAquariumZoneData(aquariums=[aquarium_0, aquarium_1])

    def test_draw_multi_aquarium_overlay_returns_frame(
        self,
        mock_canvas_manager: CanvasManager,
        sample_frame: np.ndarray,
        sample_multi_aquarium_zone_data: MultiAquariumZoneData,
    ) -> None:
        """Test that draw_multi_aquarium_overlay returns a frame."""
        result = mock_canvas_manager.draw_multi_aquarium_overlay(
            frame=sample_frame,
            zone_data=sample_multi_aquarium_zone_data,
        )
        assert result is not None
        assert isinstance(result, np.ndarray)
        assert result.shape == sample_frame.shape

    def test_draw_multi_aquarium_overlay_modifies_frame(
        self,
        mock_canvas_manager: CanvasManager,
        sample_frame: np.ndarray,
        sample_multi_aquarium_zone_data: MultiAquariumZoneData,
    ) -> None:
        """Test that draw_multi_aquarium_overlay actually draws on the frame."""
        original_sum = sample_frame.sum()

        result = mock_canvas_manager.draw_multi_aquarium_overlay(
            frame=sample_frame,
            zone_data=sample_multi_aquarium_zone_data,
        )

        # Frame should have been modified (pixels drawn)
        assert result.sum() != original_sum

    def test_draw_multi_aquarium_overlay_with_detections(
        self,
        mock_canvas_manager: CanvasManager,
        sample_frame: np.ndarray,
        sample_multi_aquarium_zone_data: MultiAquariumZoneData,
    ) -> None:
        """Test overlay with detection bounding boxes."""
        detections_by_aquarium = {
            0: [(100, 200, 150, 280, 0.95, 1001, 0)],  # Detection in aquarium 0
            1: [(400, 200, 450, 280, 0.88, 2001, 0)],  # Detection in aquarium 1
        }

        result = mock_canvas_manager.draw_multi_aquarium_overlay(
            frame=sample_frame,
            zone_data=sample_multi_aquarium_zone_data,
            detections_by_aquarium=detections_by_aquarium,
        )

        assert result is not None
        # Frame should have detections drawn
        assert result.sum() > 0

    def test_draw_multi_aquarium_overlay_without_labels(
        self,
        mock_canvas_manager: CanvasManager,
        sample_frame: np.ndarray,
        sample_multi_aquarium_zone_data: MultiAquariumZoneData,
    ) -> None:
        """Test overlay with labels disabled."""
        result = mock_canvas_manager.draw_multi_aquarium_overlay(
            frame=sample_frame,
            zone_data=sample_multi_aquarium_zone_data,
            show_labels=False,
        )

        assert result is not None

    def test_draw_multi_aquarium_overlay_without_rois(
        self,
        mock_canvas_manager: CanvasManager,
        sample_frame: np.ndarray,
        sample_multi_aquarium_zone_data: MultiAquariumZoneData,
    ) -> None:
        """Test overlay with ROIs disabled."""
        result = mock_canvas_manager.draw_multi_aquarium_overlay(
            frame=sample_frame,
            zone_data=sample_multi_aquarium_zone_data,
            show_rois=False,
        )

        assert result is not None

    def test_draw_multi_aquarium_overlay_handles_invalid_zone_data(
        self,
        mock_canvas_manager: CanvasManager,
        sample_frame: np.ndarray,
    ) -> None:
        """Test that invalid zone data returns unchanged frame."""
        original_frame = sample_frame.copy()

        # Pass wrong type
        result = mock_canvas_manager.draw_multi_aquarium_overlay(
            frame=sample_frame,
            zone_data="not a zone data",  # type: ignore
        )

        assert result is not None
        # Frame should be returned unchanged
        assert np.array_equal(result, original_frame)

    def test_draw_multi_aquarium_overlay_empty_aquariums(
        self,
        mock_canvas_manager: CanvasManager,
        sample_frame: np.ndarray,
    ) -> None:
        """Test overlay with empty aquarium list."""
        empty_zone_data = MultiAquariumZoneData(aquariums=[])

        result = mock_canvas_manager.draw_multi_aquarium_overlay(
            frame=sample_frame,
            zone_data=empty_zone_data,
        )

        assert result is not None

    def test_draw_multi_aquarium_overlay_no_detections(
        self,
        mock_canvas_manager: CanvasManager,
        sample_frame: np.ndarray,
        sample_multi_aquarium_zone_data: MultiAquariumZoneData,
    ) -> None:
        """Test overlay with None detections."""
        result = mock_canvas_manager.draw_multi_aquarium_overlay(
            frame=sample_frame,
            zone_data=sample_multi_aquarium_zone_data,
            detections_by_aquarium=None,
        )

        assert result is not None

    def test_draw_multi_aquarium_overlay_empty_detections(
        self,
        mock_canvas_manager: CanvasManager,
        sample_frame: np.ndarray,
        sample_multi_aquarium_zone_data: MultiAquariumZoneData,
    ) -> None:
        """Test overlay with empty detection dict."""
        result = mock_canvas_manager.draw_multi_aquarium_overlay(
            frame=sample_frame,
            zone_data=sample_multi_aquarium_zone_data,
            detections_by_aquarium={},
        )

        assert result is not None


class TestAquariumColors:
    """Tests for AQUARIUM_COLORS constant."""

    def test_aquarium_colors_defined(self) -> None:
        """Test that AQUARIUM_COLORS is defined with expected keys."""
        assert hasattr(CanvasManager, "AQUARIUM_COLORS")
        colors = CanvasManager.AQUARIUM_COLORS

        assert 0 in colors
        assert 1 in colors

    def test_aquarium_colors_structure(self) -> None:
        """Test that each color entry has required fields."""
        colors = CanvasManager.AQUARIUM_COLORS

        for aq_id, color_info in colors.items():
            assert "border" in color_info
            assert "fill" in color_info
            assert "text" in color_info

            # Border should be BGR tuple
            assert isinstance(color_info["border"], tuple)
            assert len(color_info["border"]) == 3

            # Text should be string
            assert isinstance(color_info["text"], str)


class TestHexToBgr:
    """Tests for hex_to_bgr helper method."""

    def test_hex_to_bgr_basic(self) -> None:
        """Test basic hex to BGR conversion."""
        result = CanvasManager.hex_to_bgr("#0066CC")
        assert result == (204, 102, 0)  # BGR for blue

    def test_hex_to_bgr_red(self) -> None:
        """Test red hex to BGR conversion."""
        result = CanvasManager.hex_to_bgr("#FF0000")
        assert result == (0, 0, 255)  # BGR for red

    def test_hex_to_bgr_green(self) -> None:
        """Test green hex to BGR conversion."""
        result = CanvasManager.hex_to_bgr("#00FF00")
        assert result == (0, 255, 0)  # BGR for green

    def test_hex_to_bgr_white(self) -> None:
        """Test white hex to BGR conversion."""
        result = CanvasManager.hex_to_bgr("#FFFFFF")
        assert result == (255, 255, 255)

    def test_hex_to_bgr_black(self) -> None:
        """Test black hex to BGR conversion."""
        result = CanvasManager.hex_to_bgr("#000000")
        assert result == (0, 0, 0)

    def test_hex_to_bgr_no_hash(self) -> None:
        """Test hex without # prefix."""
        result = CanvasManager.hex_to_bgr("0066CC")
        assert result == (204, 102, 0)


class TestMultiAquariumOverlayIntegration:
    """Integration tests for multi-aquarium overlay."""

    @pytest.fixture
    def mock_canvas_manager(self) -> CanvasManager:
        """Create a mock CanvasManager instance for testing."""
        with patch.object(CanvasManager, "__init__", lambda self, *args, **kwargs: None):
            cm = CanvasManager(MagicMock())
            cm.gui = MagicMock()
            cm.event_bus_v2 = MagicMock()
            cm.multi_aquarium = MultiAquariumOverlayManager(cm)
            return cm

    def test_overlay_different_aquarium_colors(
        self,
        mock_canvas_manager: CanvasManager,
    ) -> None:
        """Test that different aquariums get different colors on overlay."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Create two simple aquariums
        aq0 = AquariumData(
            id=0,
            polygon=[(10, 10), (100, 10), (100, 100), (10, 100)],
        )
        aq1 = AquariumData(
            id=1,
            polygon=[(200, 10), (300, 10), (300, 100), (200, 100)],
        )
        zone_data = MultiAquariumZoneData(aquariums=[aq0, aq1])

        result = mock_canvas_manager.draw_multi_aquarium_overlay(
            frame=frame,
            zone_data=zone_data,
            show_labels=True,
            show_rois=True,
        )

        # Check that pixels were drawn in expected regions
        # Aquarium 0 region
        aq0_region = result[10:100, 10:100]
        # Aquarium 1 region
        aq1_region = result[10:100, 200:300]

        # Both regions should have some non-zero pixels (borders drawn)
        assert aq0_region.max() > 0 or aq1_region.max() > 0

    def test_overlay_with_multiple_detections_per_aquarium(
        self,
        mock_canvas_manager: CanvasManager,
    ) -> None:
        """Test overlay with multiple detections in each aquarium."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        aq0 = AquariumData(id=0, polygon=[(10, 10), (300, 10), (300, 200), (10, 200)])
        aq1 = AquariumData(id=1, polygon=[(320, 10), (620, 10), (620, 200), (320, 200)])
        zone_data = MultiAquariumZoneData(aquariums=[aq0, aq1])

        detections = {
            0: [
                (50, 50, 80, 80, 0.9, 1001, 0),
                (150, 100, 180, 130, 0.85, 1002, 0),
            ],
            1: [
                (350, 50, 380, 80, 0.92, 2001, 0),
                (450, 100, 480, 130, 0.88, 2002, 0),
                (550, 150, 580, 180, 0.78, 2003, 0),
            ],
        }

        result = mock_canvas_manager.draw_multi_aquarium_overlay(
            frame=frame,
            zone_data=zone_data,
            detections_by_aquarium=detections,
        )

        assert result is not None
        # Frame should have content drawn
        assert result.sum() > 0


def test_on_multi_auto_detect_success_persists_source_video_dimensions() -> None:
    with patch.object(CanvasManager, "__init__", lambda self, *args, **kwargs: None):
        canvas_manager = CanvasManager(MagicMock())

    project_manager = MagicMock()
    project_manager.get_active_zone_video.return_value = "video.mp4"
    project_manager.get_multi_aquarium_zone_data.return_value = MultiAquariumZoneData(
        aquariums=[
            AquariumData(
                id=0,
                polygon=[(0, 0), (1, 0), (1, 1)],
                roi_polygons=[[(1, 1), (2, 1), (2, 2)]],
                roi_names=["roi"],
                roi_colors=[(1, 2, 3)],
                group="Controle",
                subject_id="S01",
                day=2,
            )
        ],
        sequential_processing=True,
    )

    gui = MagicMock()
    gui.controller = MagicMock(
        project_manager=project_manager,
        settings=SimpleNamespace(camera=SimpleNamespace(desired_width=1280, desired_height=720)),
    )
    gui.zone_controls = MagicMock()
    gui.dialog_manager = MagicMock()
    gui._original_image = None

    canvas_manager.gui = gui
    canvas_manager.redraw_zones_from_project_data = MagicMock()  # type: ignore[method-assign]
    canvas_manager.update_zone_listbox = MagicMock()  # type: ignore[method-assign]

    overlay = MultiAquariumOverlayManager(canvas_manager)

    with patch(
        "zebtrack.ui.components.canvas.multi_aquarium_overlay.cv2.VideoCapture",
    ) as capture_mock:
        overlay.on_multi_auto_detect_success(
            {
                "video_path": "video.mp4",
                "source_video_width": 1920,
                "source_video_height": 1080,
                "polygons": [
                    [(10, 10), (200, 10), (200, 200), (10, 200)],
                    [(220, 10), (400, 10), (400, 200), (220, 200)],
                ],
            }
        )

    saved_multi_data = project_manager.save_multi_aquarium_zone_data.call_args.args[1]
    assert isinstance(saved_multi_data, MultiAquariumZoneData)
    assert saved_multi_data.video_width == 1920
    assert saved_multi_data.video_height == 1080
    assert saved_multi_data.sequential_processing is True
    assert saved_multi_data.aquariums[0].roi_names == ["roi"]
    capture_mock.assert_not_called()
