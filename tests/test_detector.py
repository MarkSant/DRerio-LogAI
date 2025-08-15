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

if __name__ == "__main__":
    unittest.main()
