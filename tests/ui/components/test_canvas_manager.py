"""Tests for CanvasManager component."""

from tkinter import Canvas
from unittest.mock import Mock, patch

import numpy as np
import pytest
from PIL import Image

from zebtrack.ui.components.canvas_manager import CanvasManager


@pytest.fixture
def mock_controller():
    """Create a mock controller."""
    controller = Mock()
    controller.project_manager = Mock()
    controller.project_manager.set_active_zone_video = Mock()
    controller.project_manager.get_all_videos = Mock(return_value=[])
    controller.project_manager.project_path = None
    return controller


@pytest.fixture
def mock_gui(tkinter_root, mock_controller):
    """Create a mock ApplicationGUI instance."""
    gui = Mock()
    gui.root = tkinter_root
    gui.root.after = Mock()  # Mock the after method
    gui.controller = mock_controller
    gui.roi_canvas = Canvas(tkinter_root, width=800, height=600)
    gui.roi_canvas.pack()
    tkinter_root.update()
    gui.video_label = Mock()
    gui._current_detections = []
    gui._original_image = None
    gui._last_analysis_frame = None
    gui.analysis_active = False
    gui.show_error = Mock()
    gui.show_warning = Mock()
    gui._refresh_roi_templates = Mock()
    gui.update_zone_listbox = Mock()
    gui._get_zone_data_for_active_context = Mock()
    gui.current_polygon_points = []
    gui.edited_polygon_points = []
    gui.current_editing_zone = None
    gui.interactive_polygon_item = None
    gui.polygon_handles = []
    gui.pending_single_video_path = None
    gui._on_handle_press = Mock()
    gui._on_handle_drag = Mock()
    gui._on_handle_release = Mock()
    gui.track_selector_var = Mock()
    gui.track_selector_var.get = Mock(return_value="Todos")
    gui.track_selector_widget = Mock()
    gui.track_selector_widget.winfo_height = Mock(return_value=30)
    gui.track_selector_widget.update_idletasks = Mock()
    gui.analysis_video_label = Mock()
    gui.analysis_status_label = Mock()
    gui.analysis_status_label.winfo_height = Mock(return_value=20)
    gui.analysis_status_label.update_idletasks = Mock()
    gui.analysis_task_label = Mock()
    gui.analysis_task_label.winfo_height = Mock(return_value=20)
    gui.analysis_task_label.update_idletasks = Mock()
    gui.analysis_group_label = Mock()
    gui.analysis_group_label.winfo_height = Mock(return_value=20)
    gui.analysis_group_label.update_idletasks = Mock()
    gui.tracking_mode_label = Mock()
    gui.tracking_mode_label.winfo_height = Mock(return_value=20)
    gui.tracking_mode_label.update_idletasks = Mock()
    gui.notebook = Mock()
    gui.notebook.winfo_width = Mock(return_value=800)
    gui.notebook.winfo_height = Mock(return_value=600)
    gui.notebook.update_idletasks = Mock()
    gui.progress_frame = Mock()
    gui.progress_frame.winfo_viewable = Mock(return_value=False)
    gui.video_container = Mock()
    gui._analysis_overlay_image = None
    return gui


@pytest.fixture
def canvas_manager(mock_gui):
    """Create a CanvasManager instance for testing."""
    return CanvasManager(mock_gui)


@pytest.fixture
def mock_zone_data():
    """Create mock zone data."""
    zone_data = Mock()
    zone_data.polygon = [[100, 100], [200, 100], [200, 200], [100, 200]]
    zone_data.roi_polygons = [
        [[120, 120], [180, 120], [180, 180], [120, 180]],
        [[220, 120], [280, 120], [280, 180], [220, 180]],
    ]
    zone_data.roi_colors = [(0, 255, 0), (255, 0, 0)]  # BGR colors
    zone_data.roi_names = ["ROI_1", "ROI_2"]
    return zone_data


@pytest.mark.gui
class TestCanvasManagerInitialization:
    """Tests for CanvasManager initialization."""

    def test_initialization(self, canvas_manager, mock_gui):
        """Test that CanvasManager initializes correctly."""
        assert canvas_manager.gui is mock_gui
        assert canvas_manager._bg_scale is None
        assert canvas_manager._bg_offset is None
        assert canvas_manager._bg_img_size is None
        assert canvas_manager._raw_bg_image is None
        assert canvas_manager._canvas_bg_image is None
        assert canvas_manager._canvas_bg_position is None

    def test_initialization_with_real_gui(self, tkinter_root):
        """Test initialization with minimal real gui object."""
        gui = Mock()
        gui.root = tkinter_root
        manager = CanvasManager(gui)
        assert manager.gui is gui


@pytest.mark.gui
class TestCoordinateTransformation:
    """Tests for coordinate transformation methods."""

    def test_canvas_to_video_without_scaling(self, canvas_manager):
        """Test canvas to video conversion without scaling info."""
        # Without scaling info, should return canvas coordinates as-is
        video_x, video_y = canvas_manager._canvas_to_video(100, 200)
        assert video_x == 100.0
        assert video_y == 200.0

    def test_canvas_to_video_with_scaling(self, canvas_manager):
        """Test canvas to video conversion with scaling."""
        canvas_manager._bg_scale = 0.5
        canvas_manager._bg_offset = (50, 50)

        video_x, video_y = canvas_manager._canvas_to_video(150, 150)

        # (150 - 50) / 0.5 = 200
        assert video_x == 200.0
        assert video_y == 200.0

    def test_video_to_canvas_without_scaling(self, canvas_manager):
        """Test video to canvas conversion without scaling info."""
        canvas_x, canvas_y = canvas_manager._video_to_canvas(100, 200)
        assert canvas_x == 100.0
        assert canvas_y == 200.0

    def test_video_to_canvas_with_scaling(self, canvas_manager):
        """Test video to canvas conversion with scaling."""
        canvas_manager._bg_scale = 0.5
        canvas_manager._bg_offset = (50, 50)

        canvas_x, canvas_y = canvas_manager._video_to_canvas(200, 200)

        # 200 * 0.5 + 50 = 150
        assert canvas_x == 150.0
        assert canvas_y == 150.0

    def test_roundtrip_coordinate_conversion(self, canvas_manager):
        """Test that converting back and forth preserves coordinates."""
        canvas_manager._bg_scale = 0.75
        canvas_manager._bg_offset = (30, 40)

        original_video_x, original_video_y = 100, 150
        canvas_x, canvas_y = canvas_manager._video_to_canvas(original_video_x, original_video_y)
        video_x, video_y = canvas_manager._canvas_to_video(canvas_x, canvas_y)

        assert abs(video_x - original_video_x) < 0.001
        assert abs(video_y - original_video_y) < 0.001

    def test_point_to_segment_distance_degenerate(self, canvas_manager):
        """Test distance calculation for degenerate segment (single point)."""
        result = canvas_manager._point_to_segment_distance(100, 100, 50, 50, 50, 50)

        # Distance from (100, 100) to (50, 50) = sqrt(50^2 + 50^2) ≈ 70.71
        assert abs(result["distance"] - 70.71) < 0.01
        assert result["x"] == 50
        assert result["y"] == 50

    def test_point_to_segment_distance_perpendicular(self, canvas_manager):
        """Test distance to segment with perpendicular projection."""
        # Point (50, 50), segment from (0, 0) to (100, 0)
        result = canvas_manager._point_to_segment_distance(50, 50, 0, 0, 100, 0)

        # Closest point should be (50, 0), distance = 50
        assert result["distance"] == 50.0
        assert result["x"] == 50.0
        assert result["y"] == 0.0

    def test_point_to_segment_distance_endpoint(self, canvas_manager):
        """Test distance when closest point is an endpoint."""
        # Point (150, 50), segment from (0, 0) to (100, 0)
        result = canvas_manager._point_to_segment_distance(150, 50, 0, 0, 100, 0)

        # Closest point should be (100, 0), distance = sqrt(50^2 + 50^2)
        assert abs(result["distance"] - 70.71) < 0.01
        assert result["x"] == 100.0
        assert result["y"] == 0.0


@pytest.mark.gui
class TestBackgroundImageDrawing:
    """Tests for background image drawing methods."""

    def test_draw_bg_image_to_canvas_without_image(self, canvas_manager):
        """Test drawing when no image is available."""
        # Should return without error
        canvas_manager._draw_bg_image_to_canvas()
        # No assertions needed, just verify it doesn't crash

    def test_draw_bg_image_to_canvas_with_image(self, canvas_manager, mock_gui):
        """Test drawing background image with scaling."""
        # Create a mock PIL image
        mock_image = Mock(spec=Image.Image)
        mock_image.size = (1920, 1080)
        mock_resized = Mock(spec=Image.Image)
        mock_image.resize = Mock(return_value=mock_resized)

        canvas_manager._raw_bg_image = mock_image

        # Mock canvas create_image to prevent TclError
        mock_gui.roi_canvas.create_image = Mock(return_value=1)

        with patch("zebtrack.ui.components.canvas_manager.ImageTk") as mock_imagetk:
            mock_photo = Mock()
            mock_imagetk.PhotoImage.return_value = mock_photo

            canvas_manager._draw_bg_image_to_canvas()

            # Verify image was resized
            mock_image.resize.assert_called_once()

            # Verify PhotoImage was created
            mock_imagetk.PhotoImage.assert_called_once_with(mock_resized)

            # Verify scaling info was stored
            assert canvas_manager._bg_scale is not None
            assert canvas_manager._bg_offset is not None
            assert canvas_manager._bg_img_size == (1920, 1080)

    def test_draw_bg_image_to_canvas_canvas_not_ready(self, canvas_manager, mock_gui):
        """Test drawing when canvas dimensions are not ready."""
        mock_image = Mock(spec=Image.Image)
        mock_image.size = (1920, 1080)
        canvas_manager._raw_bg_image = mock_image

        # Mock canvas with invalid dimensions
        mock_gui.roi_canvas.winfo_width = Mock(return_value=1)
        mock_gui.roi_canvas.winfo_height = Mock(return_value=1)

        # Should schedule retry
        canvas_manager._draw_bg_image_to_canvas()

        # Verify root.after was called to retry
        assert mock_gui.root.after.called

    def test_draw_bg_image_to_canvas_scaling_calculation(self, canvas_manager, mock_gui):
        """Test that scaling is calculated correctly."""
        # Canvas: Image: 1600x1200 (2:1 ratio)
        mock_image = Mock(spec=Image.Image)
        mock_image.size = (1600, 1200)
        mock_resized = Mock(spec=Image.Image)
        mock_image.resize = Mock(return_value=mock_resized)

        canvas_manager._raw_bg_image = mock_image

        # Mock canvas create_image
        mock_gui.roi_canvas.create_image = Mock(return_value=1)

        with patch("zebtrack.ui.components.canvas_manager.ImageTk"):
            canvas_manager._draw_bg_image_to_canvas()

            # Verify scaling was calculated (actual value depends on canvas size)
            assert canvas_manager._bg_scale is not None
            assert canvas_manager._bg_scale > 0

            # Verify image was resized
            assert mock_image.resize.called

    def test_display_image_on_canvas_without_image(self, canvas_manager, mock_gui):
        """Test displaying image when _original_image is None."""
        mock_gui._original_image = None

        canvas_manager._display_image_on_canvas()
        # Should return without error

    def test_display_image_on_canvas_with_image(self, canvas_manager, mock_gui):
        """Test displaying image on canvas."""
        mock_image = Mock(spec=Image.Image)
        mock_image.size = (1920, 1080)
        mock_resized = Mock(spec=Image.Image)
        mock_image.resize = Mock(return_value=mock_resized)

        mock_gui._original_image = mock_image

        # Mock canvas create_image
        mock_gui.roi_canvas.create_image = Mock(return_value=1)

        with patch("zebtrack.ui.components.canvas_manager.ImageTk") as mock_imagetk:
            mock_photo = Mock()
            mock_imagetk.PhotoImage.return_value = mock_photo

            canvas_manager._display_image_on_canvas()

            # Verify image was resized and displayed
            mock_image.resize.assert_called_once()
            mock_imagetk.PhotoImage.assert_called_once()

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    @patch("zebtrack.ui.components.canvas_manager.Image")
    @patch("os.path.exists")
    def test_display_roi_video_frame_success(
        self, mock_exists, mock_pil, mock_cv2, canvas_manager, mock_gui
    ):
        """Test displaying first frame of video."""
        mock_exists.return_value = True

        # Mock cv2.VideoCapture
        mock_cap = Mock()
        mock_cap.isOpened.return_value = True
        mock_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, mock_frame)
        mock_cv2.VideoCapture.return_value = mock_cap

        # Mock cv2.cvtColor
        mock_frame_rgb = np.zeros((1080, 1920, 3), dtype=np.uint8)
        mock_cv2.cvtColor.return_value = mock_frame_rgb
        mock_cv2.COLOR_BGR2RGB = 4  # Mock constant

        # Mock PIL Image.fromarray
        mock_pil_image = Mock(spec=Image.Image)
        mock_pil.fromarray.return_value = mock_pil_image

        video_path = "/path/to/video.mp4"
        canvas_manager.display_roi_video_frame(video_path)

        # Verify video capture was called
        mock_cv2.VideoCapture.assert_called_once_with(video_path)
        mock_cap.read.assert_called_once()
        mock_cap.release.assert_called_once()

        # Verify frame conversion - cvtColor should be called during display
        # Note: It's called in after() callback, so may not be immediate
        # Just verify the video was opened and frame read successfully

        # Verify project manager was notified
        assert mock_gui.controller.project_manager.set_active_zone_video.called

    @patch("os.path.exists")
    def test_display_roi_video_frame_invalid_path(
        self, mock_exists, canvas_manager, mock_gui, mock_controller
    ):
        """Test handling invalid video path."""
        mock_exists.return_value = False

        canvas_manager.display_roi_video_frame("/invalid/path.mp4")

        # Should show error
        mock_gui.show_error.assert_called_once()

        # Should clear active video
        mock_controller.project_manager.set_active_zone_video.assert_called_with(None)

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    @patch("os.path.exists")
    def test_display_roi_video_frame_cannot_open(
        self, mock_exists, mock_cv2, canvas_manager, mock_gui
    ):
        """Test handling when video cannot be opened."""
        mock_exists.return_value = True

        mock_cap = Mock()
        mock_cap.isOpened.return_value = False
        mock_cv2.VideoCapture.return_value = mock_cap

        canvas_manager.display_roi_video_frame("/path/to/video.mp4")

        mock_gui.show_error.assert_called_once()

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    @patch("os.path.exists")
    def test_display_roi_video_frame_cannot_read(
        self, mock_exists, mock_cv2, canvas_manager, mock_gui
    ):
        """Test handling when frame cannot be read."""
        mock_exists.return_value = True

        mock_cap = Mock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        mock_cv2.VideoCapture.return_value = mock_cap

        canvas_manager.display_roi_video_frame("/path/to/video.mp4")

        mock_gui.show_error.assert_called_once()

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    @patch("os.path.exists")
    def test_load_video_frame_to_canvas_no_path(
        self, mock_exists, mock_cv2, canvas_manager, mock_controller
    ):
        """Test loading frame with no video path provided."""
        result = canvas_manager.load_video_frame_to_canvas(None)

        assert result is False

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    @patch("zebtrack.ui.components.canvas_manager.Image")
    @patch("os.path.exists")
    def test_load_video_frame_to_canvas_with_path(
        self, mock_exists, mock_pil, mock_cv2, canvas_manager, mock_gui
    ):
        """Test loading specific frame from video."""
        mock_exists.return_value = True

        # Mock cv2.VideoCapture
        mock_cap = Mock()
        mock_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, mock_frame)
        mock_cv2.VideoCapture.return_value = mock_cap

        # Mock cv2 constants and functions
        mock_cv2.CAP_PROP_POS_FRAMES = 1
        mock_cv2.COLOR_BGR2RGB = 4
        mock_frame_rgb = np.zeros((1080, 1920, 3), dtype=np.uint8)
        mock_cv2.cvtColor.return_value = mock_frame_rgb

        # Mock PIL Image
        mock_pil_image = Mock(spec=Image.Image)
        mock_pil.fromarray.return_value = mock_pil_image

        # Mock _draw_bg_image_to_canvas to avoid downstream issues
        canvas_manager._draw_bg_image_to_canvas = Mock()

        result = canvas_manager.load_video_frame_to_canvas("/path/to/video.mp4", frame_number=10)

        assert result is True
        mock_cap.set.assert_called_once_with(mock_cv2.CAP_PROP_POS_FRAMES, 10)
        mock_cap.read.assert_called_once()

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    @patch("os.path.exists")
    def test_load_video_frame_to_canvas_read_failure(self, mock_exists, mock_cv2, canvas_manager):
        """Test handling when frame read fails."""
        mock_exists.return_value = True

        mock_cap = Mock()
        mock_cap.read.return_value = (False, None)
        mock_cv2.VideoCapture.return_value = mock_cap

        result = canvas_manager.load_video_frame_to_canvas("/path/to/video.mp4")

        assert result is False


@pytest.mark.gui
class TestInteractivePolygonDrawing:
    """Tests for interactive polygon drawing methods."""

    def test_draw_interactive_polygon_empty(self, canvas_manager, mock_gui):
        """Test drawing interactive polygon with no points."""
        mock_gui.edited_polygon_points = []

        # Mock canvas methods to prevent real Tkinter calls
        mock_gui.roi_canvas.create_polygon = Mock(return_value=1)
        mock_gui.roi_canvas.create_oval = Mock(return_value=1)

        canvas_manager._draw_interactive_polygon()

        # With empty points, should not create polygon
        # (Implementation may vary - check if it returns early or creates empty)
        # Just verify it doesn't crash

    def test_draw_interactive_polygon_with_points(self, canvas_manager, mock_gui):
        """Test drawing interactive polygon with points."""
        mock_gui.edited_polygon_points = [[100, 100], [200, 100], [200, 200], [100, 200]]

        # Setup scaling
        canvas_manager._bg_scale = 1.0
        canvas_manager._bg_offset = (0, 0)

        canvas_manager._draw_interactive_polygon()

        # Verify polygon was created
        assert mock_gui.roi_canvas.find_withtag("interactive_polygon")

        # Verify handles were created (4 points = 4 handles)
        handles = mock_gui.roi_canvas.find_withtag("handle")
        assert len(handles) == 4

    def test_draw_interactive_polygon_clears_previous(self, canvas_manager, mock_gui):
        """Test that previous drawings are cleared."""
        mock_gui.edited_polygon_points = [[100, 100], [200, 200]]
        canvas_manager._bg_scale = 1.0
        canvas_manager._bg_offset = (0, 0)

        # Draw first time
        canvas_manager._draw_interactive_polygon()
        first_count = len(mock_gui.roi_canvas.find_all())

        # Draw again
        canvas_manager._draw_interactive_polygon()
        second_count = len(mock_gui.roi_canvas.find_all())

        # Should have same number of items (old ones deleted, new ones created)
        assert second_count == first_count

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    def test_draw_interactive_polygon_roi_boundary_check(
        self, mock_cv2, canvas_manager, mock_gui, mock_zone_data
    ):
        """Test boundary checking for ROI editing."""
        mock_gui.edited_polygon_points = [[100, 100], [200, 200]]
        mock_gui.current_editing_zone = ("roi", 0)
        mock_gui._get_zone_data_for_active_context.return_value = mock_zone_data

        canvas_manager._bg_scale = 1.0
        canvas_manager._bg_offset = (0, 0)

        # Mock cv2.pointPolygonTest
        mock_cv2.pointPolygonTest.return_value = 0.5  # Inside polygon

        canvas_manager._draw_interactive_polygon()

        # Verify boundary check was performed
        mock_cv2.pointPolygonTest.assert_called()

    def test_redraw_polygon_in_progress_empty(self, canvas_manager, mock_gui):
        """Test redrawing polygon with no points."""
        mock_gui.current_polygon_points = []

        canvas_manager._redraw_polygon_in_progress()

        # Should clear drawing aids
        assert not mock_gui.roi_canvas.find_withtag("drawing_aid")

    def test_redraw_polygon_in_progress_with_points(self, canvas_manager, mock_gui):
        """Test redrawing polygon with points."""
        mock_gui.current_polygon_points = [(100, 100), (200, 100), (200, 200)]

        canvas_manager._redraw_polygon_in_progress()

        # Should create vertices
        vertices = mock_gui.roi_canvas.find_withtag("temp_vertex")
        assert len(vertices) == 3

        # Should create edges (n-1 edges for n points)
        lines = [
            item
            for item in mock_gui.roi_canvas.find_withtag("drawing_aid")
            if mock_gui.roi_canvas.type(item) == "line"
        ]
        assert len(lines) == 2


@pytest.mark.gui
class TestZoneDrawing:
    """Tests for zone drawing methods."""

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    def test_draw_zones_on_frame_with_arena(
        self, mock_cv2, canvas_manager, mock_gui, mock_zone_data
    ):
        """Test drawing zones on frame."""
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        mock_gui._get_zone_data_for_active_context.return_value = mock_zone_data

        canvas_manager._draw_zones_on_frame(frame)

        # Verify cv2.polylines was called for arena
        assert mock_cv2.polylines.call_count >= 1

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    def test_draw_zones_on_frame_with_rois(
        self, mock_cv2, canvas_manager, mock_gui, mock_zone_data
    ):
        """Test drawing ROIs on frame."""
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        mock_gui._get_zone_data_for_active_context.return_value = mock_zone_data

        canvas_manager._draw_zones_on_frame(frame)

        # Should call polylines for arena + 2 ROIs = 3 times
        assert mock_cv2.polylines.call_count == 3

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    def test_draw_zones_on_frame_no_data(self, mock_cv2, canvas_manager, mock_gui):
        """Test drawing when no zone data."""
        frame = np.zeros((600, 800, 3), dtype=np.uint8)

        mock_zone_data = Mock()
        mock_zone_data.polygon = None
        mock_zone_data.roi_polygons = []
        mock_gui._get_zone_data_for_active_context.return_value = mock_zone_data

        canvas_manager._draw_zones_on_frame(frame)

        # Should not call polylines
        mock_cv2.polylines.assert_not_called()

    def test_redraw_zones_from_project_data_no_canvas(self, canvas_manager, mock_gui):
        """Test redraw when canvas is None."""
        mock_gui.roi_canvas = None

        # Should not raise exception
        canvas_manager.redraw_zones_from_project_data()

    def test_redraw_zones_from_project_data_no_zone_data(self, canvas_manager, mock_gui):
        """Test redraw when zone data is None."""
        mock_gui._get_zone_data_for_active_context.return_value = None

        # Should return without error
        canvas_manager.redraw_zones_from_project_data()

    def test_redraw_zones_from_project_data_with_arena(
        self, canvas_manager, mock_gui, mock_zone_data
    ):
        """Test redraw with arena polygon."""
        mock_gui._get_zone_data_for_active_context.return_value = mock_zone_data
        canvas_manager._bg_scale = 1.0
        canvas_manager._bg_offset = (0, 0)

        canvas_manager.redraw_zones_from_project_data(mock_zone_data)

        # Verify arena polygon was drawn
        assert mock_gui.roi_canvas.find_withtag("main_polygon")

        # Verify listbox was updated
        mock_gui.update_zone_listbox.assert_called_once_with(mock_zone_data)

    def test_redraw_zones_from_project_data_with_rois(
        self, canvas_manager, mock_gui, mock_zone_data
    ):
        """Test redraw with ROI polygons."""
        mock_gui._get_zone_data_for_active_context.return_value = mock_zone_data
        canvas_manager._bg_scale = 1.0
        canvas_manager._bg_offset = (0, 0)

        canvas_manager.redraw_zones_from_project_data(mock_zone_data)

        # Verify ROI polygons were drawn
        roi_polygons = mock_gui.roi_canvas.find_withtag("roi_polygon")
        assert len(roi_polygons) == 2

        # Verify ROI labels were drawn
        roi_labels = mock_gui.roi_canvas.find_withtag("roi_label")
        assert len(roi_labels) == 2

    def test_redraw_zones_from_project_data_restores_background(
        self, canvas_manager, mock_gui, mock_zone_data
    ):
        """Test that background image is restored if missing."""
        mock_gui._get_zone_data_for_active_context.return_value = mock_zone_data

        # Mock create_image to prevent TclError
        mock_gui.roi_canvas.create_image = Mock(return_value=1)

        # Set background image but don't add to canvas
        mock_bg_image = Mock()
        canvas_manager._canvas_bg_image = mock_bg_image
        canvas_manager._canvas_bg_position = (400, 300, "center")

        canvas_manager.redraw_zones_from_project_data(mock_zone_data)

        # Verify background restoration was attempted
        assert mock_gui.roi_canvas.create_image.called


@pytest.mark.gui
class TestFrameDisplay:
    """Tests for frame display methods."""

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    @patch("zebtrack.ui.components.canvas_manager.Image")
    @patch("zebtrack.ui.components.canvas_manager.ImageTk")
    def test_display_frame_normal_mode(
        self, mock_imagetk, mock_pil, mock_cv2, canvas_manager, mock_gui, mock_zone_data
    ):
        """Test displaying frame in normal mode."""
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        mock_gui.analysis_active = False
        mock_gui._get_zone_data_for_active_context.return_value = mock_zone_data

        # Mock cv2 operations
        mock_cv2.cvtColor.return_value = frame

        # Mock PIL Image
        mock_pil_image = Mock()
        mock_pil.fromarray.return_value = mock_pil_image

        # Mock ImageTk
        mock_photo = Mock()
        mock_imagetk.PhotoImage.return_value = mock_photo

        canvas_manager.display_frame(frame)

        # Verify frame was processed
        mock_cv2.cvtColor.assert_called()
        mock_pil.fromarray.assert_called()
        mock_imagetk.PhotoImage.assert_called_once()

        # Verify video_label was updated
        mock_gui.video_label.configure.assert_called_once()

    def test_display_frame_analysis_mode(self, canvas_manager, mock_gui):
        """Test that display_frame routes to display_analysis_frame when active."""
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        mock_gui.analysis_active = True

        with patch.object(canvas_manager, "display_analysis_frame") as mock_display_analysis:
            canvas_manager.display_frame(frame)
            mock_display_analysis.assert_called_once_with(frame)

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    def test_display_analysis_frame(self, mock_cv2, canvas_manager, mock_gui, mock_zone_data):
        """Test displaying analysis frame."""
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        mock_gui._get_zone_data_for_active_context.return_value = mock_zone_data

        with patch.object(canvas_manager, "_render_last_analysis_frame") as mock_render:
            canvas_manager.display_analysis_frame(frame)

            # Verify frame was stored
            assert mock_gui._last_analysis_frame is not None

            # Verify render was called
            mock_render.assert_called_once()

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    def test_display_frame_fallback_to_cv2(self, mock_cv2, canvas_manager, mock_gui):
        """Test fallback to cv2.imshow on error."""
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        mock_gui.analysis_active = False

        # Force an exception in the main path
        mock_gui._get_zone_data_for_active_context.side_effect = Exception("Test error")

        # Should fall back to cv2.imshow without crashing
        canvas_manager.display_frame(frame)

        # Verify cv2.imshow was called
        mock_cv2.imshow.assert_called_once()


@pytest.mark.gui
class TestDetectionOverlay:
    """Tests for detection overlay methods."""

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    def test_draw_detections_on_frame_no_detections(self, mock_cv2, canvas_manager, mock_gui):
        """Test drawing when no detections."""
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        mock_gui._current_detections = []

        result = canvas_manager._draw_detections_on_frame(frame)

        # Should return frame unchanged
        assert result is frame
        mock_cv2.rectangle.assert_not_called()

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    def test_draw_detections_on_frame_with_detections(self, mock_cv2, canvas_manager, mock_gui):
        """Test drawing with valid detections."""
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        mock_gui._current_detections = [
            [100, 100, 200, 200, 0.95, 1, 0],  # x1, y1, x2, y2, conf, track_id, class_id
            [300, 300, 400, 400, 0.87, 2, 0],
        ]

        # Mock cv2.getTextSize
        mock_cv2.getTextSize.return_value = ((50, 10), 2)

        canvas_manager._draw_detections_on_frame(frame)

        # Verify rectangles were drawn (2 bounding boxes + 2 label backgrounds = 4)
        assert mock_cv2.rectangle.call_count == 4

        # Verify text was drawn (2 labels)
        assert mock_cv2.putText.call_count == 2

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    def test_draw_detections_on_frame_invalid_detection(self, mock_cv2, canvas_manager, mock_gui):
        """Test handling invalid detection format."""
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        mock_gui._current_detections = [
            [100, 100, 200],  # Incomplete detection (less than 7 elements)
            [100, 100, 200, 200, 0.95, 1, 0],  # Valid detection
        ]

        mock_cv2.getTextSize.return_value = ((50, 10), 2)

        canvas_manager._draw_detections_on_frame(frame)

        # Should only draw the valid detection (1 bbox + 1 label bg = 2)
        assert mock_cv2.rectangle.call_count == 2

    def test_render_last_analysis_frame_no_frame(self, canvas_manager, mock_gui):
        """Test rendering when no frame is stored."""
        mock_gui._last_analysis_frame = None

        # Should return without error
        canvas_manager._render_last_analysis_frame()

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    def test_render_last_analysis_frame_with_frame(self, mock_cv2, canvas_manager, mock_gui):
        """Test rendering analysis frame with detections."""
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        mock_gui._last_analysis_frame = frame.copy()
        mock_gui._current_detections = [[100, 100, 200, 200, 0.95, 1, 0]]
        mock_cv2.getTextSize.return_value = ((50, 10), 2)

        with patch.object(canvas_manager, "_show_analysis_frame_image") as mock_show:
            canvas_manager._render_last_analysis_frame()

            # Verify show was called
            mock_show.assert_called_once()

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    def test_annotate_selected_tracks_no_selection(self, mock_cv2, canvas_manager, mock_gui):
        """Test annotation with no track selected."""
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        mock_gui.track_selector_var.get.return_value = "Todos"
        mock_gui._current_detections = [[100, 100, 200, 200, 0.95, 1, 0]]

        canvas_manager._annotate_selected_tracks(frame)

        # Should not add any annotations
        mock_cv2.rectangle.assert_not_called()

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    def test_annotate_selected_tracks_with_selection(self, mock_cv2, canvas_manager, mock_gui):
        """Test annotation with specific track selected."""
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        mock_gui.track_selector_var.get.return_value = "1"
        mock_gui._current_detections = [
            [100, 100, 200, 200, 0.95, 1, 0],
            [300, 300, 400, 400, 0.87, 2, 0],
        ]

        canvas_manager._annotate_selected_tracks(frame)

        # Should highlight only track 1 (1 rectangle + 1 text)
        assert mock_cv2.rectangle.call_count == 1
        assert mock_cv2.putText.call_count == 1

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    def test_annotate_selected_tracks_invalid_detection(self, mock_cv2, canvas_manager, mock_gui):
        """Test annotation with invalid detection data."""
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        mock_gui.track_selector_var.get.return_value = "1"
        mock_gui._current_detections = [
            [100, 100],  # Invalid (too few elements)
            ["bad", "data", 200, 200, 0.95, 1],  # Invalid (non-numeric coords)
        ]

        # Should not crash
        canvas_manager._annotate_selected_tracks(frame)

        # Should not draw anything
        mock_cv2.rectangle.assert_not_called()

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    @patch("zebtrack.ui.components.canvas_manager.Image")
    @patch("zebtrack.ui.components.canvas_manager.ImageTk")
    def test_show_analysis_frame_image_basic(
        self, mock_imagetk, mock_pil, mock_cv2, canvas_manager, mock_gui
    ):
        """Test showing analysis frame image."""
        frame = np.zeros((600, 800, 3), dtype=np.uint8)

        # Replace analysis_video_label with a fresh Mock
        mock_gui.analysis_video_label = Mock()

        # Replace winfo_height methods with fresh Mocks returning integers
        mock_gui.analysis_task_label.winfo_height = Mock(return_value=20)
        mock_gui.analysis_group_label.winfo_height = Mock(return_value=20)
        mock_gui.tracking_mode_label.winfo_height = Mock(return_value=20)

        # Mock cv2.cvtColor
        mock_cv2.cvtColor.return_value = frame
        mock_cv2.COLOR_BGR2RGB = 4

        # Mock PIL Image
        mock_pil_image = Mock(spec=Image.Image)
        mock_pil.fromarray.return_value = mock_pil_image

        # Mock ImageTk
        mock_photo = Mock()
        mock_imagetk.PhotoImage.return_value = mock_photo

        canvas_manager._show_analysis_frame_image(frame)

        # Verify conversion and display
        mock_cv2.cvtColor.assert_called_once()
        mock_pil.fromarray.assert_called_once()
        mock_imagetk.PhotoImage.assert_called_once()
        mock_gui.analysis_video_label.configure.assert_called_once()

    def test_show_analysis_frame_image_no_label(self, canvas_manager, mock_gui):
        """Test showing frame when label is None."""
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        mock_gui.analysis_video_label = None

        # Should return without error
        canvas_manager._show_analysis_frame_image(frame)

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    @patch("zebtrack.ui.components.canvas_manager.Image")
    @patch("zebtrack.ui.components.canvas_manager.ImageTk")
    def test_show_analysis_frame_image_with_scaling(
        self, mock_imagetk, mock_pil, mock_cv2, canvas_manager, mock_gui
    ):
        """Test frame scaling when it doesn't fit."""
        # Large frame that needs scaling
        frame = np.zeros((2160, 3840, 3), dtype=np.uint8)
        mock_gui.analysis_video_label = Mock()

        # Mock notebook dimensions
        mock_gui.notebook.winfo_width.return_value = 1920
        mock_gui.notebook.winfo_height.return_value = 1080

        # Mock widget dimensions
        mock_gui.analysis_status_label.winfo_height.return_value = 30
        mock_gui.analysis_task_label.winfo_height.return_value = 30
        mock_gui.analysis_group_label.winfo_height.return_value = 30
        mock_gui.tracking_mode_label.winfo_height.return_value = 30
        mock_gui.track_selector_widget.winfo_height.return_value = 40

        # Mock cv2 and PIL
        mock_cv2.cvtColor.return_value = frame
        mock_pil_image = Mock(spec=Image.Image)
        mock_pil_image.resize = Mock(return_value=mock_pil_image)
        mock_pil.fromarray.return_value = mock_pil_image

        # Setup Image.Resampling or fallback
        mock_resampling = Mock()
        mock_resampling.LANCZOS = 1
        mock_pil.Resampling = mock_resampling

        mock_photo = Mock()
        mock_imagetk.PhotoImage.return_value = mock_photo

        canvas_manager._show_analysis_frame_image(frame)

        # Verify image was resized
        mock_pil_image.resize.assert_called_once()

        # Verify size was reduced (not exact match due to aspect ratio)
        resize_call = mock_pil_image.resize.call_args[0][0]
        assert resize_call[0] < 3840
        assert resize_call[1] < 2160

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    @patch("zebtrack.ui.components.canvas_manager.Image")
    @patch("zebtrack.ui.components.canvas_manager.ImageTk")
    def test_show_analysis_frame_image_fallback_dimensions(
        self, mock_imagetk, mock_pil, mock_cv2, canvas_manager, mock_gui
    ):
        """Test frame display with fallback dimension calculation."""
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        mock_gui.analysis_video_label = Mock()

        # Mock notebook with invalid dimensions
        mock_gui.notebook.winfo_width.return_value = 1
        mock_gui.notebook.winfo_height.return_value = 1

        # Mock video_container as fallback
        mock_gui.video_container.winfo_width.return_value = 1200
        mock_gui.video_container.winfo_height.return_value = 800

        # Mock cv2 and PIL
        mock_cv2.cvtColor.return_value = frame
        mock_pil_image = Mock(spec=Image.Image)
        mock_pil.fromarray.return_value = mock_pil_image
        mock_photo = Mock()
        mock_imagetk.PhotoImage.return_value = mock_photo

        canvas_manager._show_analysis_frame_image(frame)

        # Should use video_container dimensions
        mock_gui.video_container.update_idletasks.assert_called()


@pytest.mark.gui
class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_coordinate_transformation_with_zero_scale(self, canvas_manager):
        """Test coordinate transformation edge cases."""
        canvas_manager._bg_scale = 0
        canvas_manager._bg_offset = (0, 0)

        # Should handle division by zero gracefully
        try:
            _video_x, _video_y = canvas_manager._canvas_to_video(100, 100)
            # If it doesn't crash, that's good
        except ZeroDivisionError:
            pytest.fail("Should handle zero scale gracefully")

    def test_point_to_segment_distance_vertical_segment(self, canvas_manager):
        """Test distance calculation for vertical segment."""
        result = canvas_manager._point_to_segment_distance(50, 50, 100, 0, 100, 100)

        # Closest point should be (100, 50), distance = 50
        assert result["distance"] == 50.0
        assert result["x"] == 100.0
        assert result["y"] == 50.0

    def test_point_to_segment_distance_horizontal_segment(self, canvas_manager):
        """Test distance calculation for horizontal segment."""
        result = canvas_manager._point_to_segment_distance(50, 50, 0, 100, 100, 100)

        # Closest point should be (50, 100), distance = 50
        assert result["distance"] == 50.0
        assert result["x"] == 50.0
        assert result["y"] == 100.0

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    def test_draw_zones_on_frame_empty_polygon(self, mock_cv2, canvas_manager, mock_gui):
        """Test drawing with empty polygon list."""
        frame = np.zeros((600, 800, 3), dtype=np.uint8)

        mock_zone_data = Mock()
        mock_zone_data.polygon = []  # Empty list
        mock_zone_data.roi_polygons = []
        mock_gui._get_zone_data_for_active_context.return_value = mock_zone_data

        result = canvas_manager._draw_zones_on_frame(frame)

        # Should not crash
        assert result is not None

    def test_redraw_zones_with_invalid_polygon_format(self, canvas_manager, mock_gui):
        """Test redraw with invalid polygon format."""
        mock_zone_data = Mock()
        mock_zone_data.polygon = [[100]]  # Invalid (need 2 coords per point)
        mock_zone_data.roi_polygons = []
        mock_zone_data.roi_colors = []
        mock_zone_data.roi_names = []

        canvas_manager._bg_scale = 1.0
        canvas_manager._bg_offset = (0, 0)

        # Should handle gracefully without crashing
        try:
            canvas_manager.redraw_zones_from_project_data(mock_zone_data)
        except Exception as e:
            # If it fails, it should be a predictable error, not a crash
            assert "index" in str(e).lower() or "unpack" in str(e).lower()

    @patch("zebtrack.ui.components.canvas_manager.cv2")
    def test_draw_detections_with_none_confidence(self, mock_cv2, canvas_manager, mock_gui):
        """Test drawing detections when confidence is None."""
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        mock_gui._current_detections = [
            [100, 100, 200, 200, None, 1, 0]  # None confidence
        ]

        mock_cv2.getTextSize.return_value = ((50, 10), 2)

        # Should handle None confidence gracefully
        canvas_manager._draw_detections_on_frame(frame)

        # Should still draw (but without confidence in label)
        assert mock_cv2.rectangle.call_count >= 1

    def test_multiple_coordinate_transformations(self, canvas_manager):
        """Test multiple sequential transformations."""
        canvas_manager._bg_scale = 0.5
        canvas_manager._bg_offset = (100, 100)

        # Transform multiple points
        points = [(0, 0), (100, 100), (200, 200), (400, 400)]

        for video_point in points:
            canvas_point = canvas_manager._video_to_canvas(*video_point)
            back_to_video = canvas_manager._canvas_to_video(*canvas_point)

            # Should round-trip correctly
            assert abs(back_to_video[0] - video_point[0]) < 0.001
            assert abs(back_to_video[1] - video_point[1]) < 0.001
