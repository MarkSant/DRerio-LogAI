import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from zebtrack.core.detector import Detector
from zebtrack.settings import settings


class TestDetector(unittest.TestCase):
    def setUp(self):
        """Set up a detector instance for tests."""
        self.yolo_patcher = patch("zebtrack.core.detector.YOLO")
        self.openvino_patcher = patch("zebtrack.core.detector.ov")
        self.glob_patcher = patch("zebtrack.core.detector.glob")

        self.mock_yolo = self.yolo_patcher.start()
        self.mock_openvino = self.openvino_patcher.start()
        self.mock_glob = self.glob_patcher.start()

        # Configure a default mock project manager to prevent OpenVINO loading
        self.mock_project_manager = MagicMock()
        self.mock_project_manager.project_data = {"use_openvino": False, "openvino_model_path": ""}

        self.detector = Detector(project_manager=self.mock_project_manager)

    def tearDown(self):
        """Stop the patchers."""
        self.yolo_patcher.stop()
        self.openvino_patcher.stop()
        self.glob_patcher.stop()

    def test_initialization_default_yolo(self):
        """Test that the detector initializes with YOLO by default."""
        # The setUp method already configures this scenario
        self.assertIsNotNone(self.detector.model)
        self.assertFalse(self.detector.is_openvino)
        self.mock_yolo.assert_called_with(settings.yolo_model.path)

    def test_initialization_openvino(self):
        """Test that the detector initializes with OpenVINO when configured."""
        self.mock_project_manager.project_data = {
            "use_openvino": True,
            "openvino_model_path": "/fake/path/model.xml",
        }
        # Mock glob to find a fake model file
        self.mock_glob.glob.return_value = ["/fake/path/model.xml"]

        detector = Detector(project_manager=self.mock_project_manager)

        self.assertTrue(detector.is_openvino)
        self.assertIsNotNone(detector.compiled_model)
        self.mock_openvino.Core.assert_called()

    def test_update_scaling(self):
        """Test the logic for scaling detection zones."""
        base_width = settings.camera.desired_width
        base_height = settings.camera.desired_height

        test_width = 640
        test_height = 360

        self.detector.update_scaling(test_width, test_height)

        scale_x = test_width / base_width
        scale_y = test_height / base_height

        original_point = self.detector.base_polygon[0]
        scaled_point = self.detector.scaled_polygon[0]

        expected_x = int(original_point[0] * scale_x)
        expected_y = int(original_point[1] * scale_y)

        self.assertEqual(scaled_point[0], expected_x)
        self.assertEqual(scaled_point[1], expected_y)

    def test_process_frame_yolo_path(self):
        """Test the frame processing logic using the YOLO path."""
        mock_results = MagicMock()
        fake_detection = np.array([[10, 10, 50, 50, 0.9, 0]])
        mock_results[0].boxes.data.cpu.return_value.numpy.return_value = fake_detection
        self.detector.model.return_value = mock_results

        dummy_frame = np.zeros((settings.camera.desired_height, settings.camera.desired_width, 3), dtype=np.uint8)

        with patch.object(self.detector, '_is_inside_polygon', return_value=True):
            detections, command = self.detector.process_frame(dummy_frame, "live")

            self.assertEqual(len(detections), 1)
            self.assertEqual(detections[0], (10, 10, 50, 50, 0.9))
            self.assertIsNone(command)

    def test_initialization_with_model_path_override(self):
        """Test that model_path argument overrides the settings."""
        override_path = "some/other/model.pt"
        detector = Detector(project_manager=self.mock_project_manager, model_path=override_path)
        self.mock_yolo.assert_called_with(override_path)

    def test_initialization_yolo_load_fails(self):
        """Test graceful failure when YOLO model loading raises an exception."""
        self.mock_yolo.side_effect = Exception("Model file is corrupted")
        # The __init__ should catch the exception and not crash
        detector = Detector(project_manager=self.mock_project_manager)
        self.assertIsNone(detector.model)

    def test_is_inside_square(self):
        """Test the _is_inside_square helper method."""
        square = ((100, 100), (200, 200))
        # Bbox completely inside
        self.assertTrue(self.detector._is_inside_square(110, 110, 190, 190, square))
        # Bbox overlapping
        self.assertTrue(self.detector._is_inside_square(150, 150, 250, 250, square))
        # Bbox outside
        self.assertFalse(self.detector._is_inside_square(300, 300, 400, 400, square))
        # Bbox touching edge
        self.assertTrue(self.detector._is_inside_square(90, 90, 100, 100, square))

    def test_is_inside_polygon(self):
        """Test the _is_inside_polygon helper method."""
        # A simple square polygon for testing
        polygon = np.array([[100, 100], [200, 100], [200, 200], [100, 200]], dtype=np.int32)
        # Point inside
        self.assertTrue(self.detector._is_inside_polygon(150, 150, 160, 160, polygon))
        # Point outside
        self.assertFalse(self.detector._is_inside_polygon(300, 300, 310, 310, polygon))
        # Point on edge
        self.assertTrue(self.detector._is_inside_polygon(100, 100, 110, 110, polygon))

    def test_state_machine_logic(self):
        """Test the command generation logic based on state."""
        # Setup: A detection inside the first configured square
        square = settings.detection_zones.squares[0]  # e.g., ((150, 490), (360, 660))
        x_c = (square[0][0] + square[1][0]) // 2
        y_c = (square[0][1] + square[1][1]) // 2

        mock_results = MagicMock()
        # A detection right in the middle of the first square
        fake_detection = np.array([[x_c - 5, y_c - 5, x_c + 5, y_c + 5, 0.9, 0]])
        mock_results[0].boxes.data.cpu.return_value.numpy.return_value = fake_detection
        self.detector.model.return_value = mock_results

        dummy_frame = np.zeros((settings.camera.desired_height, settings.camera.desired_width, 3), dtype=np.uint8)

        # --- Step 1: Object enters a square, should generate ENTER command ---
        # Ensure polygon check passes for this test
        with patch.object(self.detector, '_is_inside_polygon', return_value=True):
            detections, command = self.detector.process_frame(dummy_frame, "live")

        self.assertEqual(self.detector.flag, 1, "Flag should be 1 (waiting for exit)")
        self.assertEqual(self.detector.current_square, 1, "Should register entering square 1")
        self.assertEqual(command, settings.detection_zones.enter_commands[0])

        # --- Step 2: Object is still inside a square, should generate NO command ---
        with patch.object(self.detector, '_is_inside_polygon', return_value=True):
            detections, command = self.detector.process_frame(dummy_frame, "live")

        self.assertIsNone(command, "No command should be sent if object is still inside")

        # --- Step 3: Object moves outside all squares, should generate EXIT command ---
        # New detection is outside all squares
        mock_results[0].boxes.data.cpu.return_value.numpy.return_value = np.array([[10, 10, 20, 20, 0.9, 0]])

        with patch.object(self.detector, '_is_inside_polygon', return_value=True):
            detections, command = self.detector.process_frame(dummy_frame, "live")

        self.assertEqual(self.detector.flag, 0, "Flag should reset to 0 (waiting for entry)")
        self.assertEqual(self.detector.current_square, 0, "Current square should be reset")
        self.assertEqual(command, settings.detection_zones.exit_commands[0])

if __name__ == "__main__":
    unittest.main()
