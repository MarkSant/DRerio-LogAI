import unittest

import numpy as np

from src.zebtrack.core.calibration import Calibration


class TestCalibration(unittest.TestCase):
    def setUp(self):
        """Set up a sample polygon and dimensions for testing."""
        # A simple, slightly distorted rectangle as a sample polygon
        self.polygon = np.array(
            [[105, 105], [495, 100], [505, 395], [100, 405]], dtype=np.int32
        )
        self.real_width_cm = 20.0
        self.real_height_cm = 15.0

    def test_calibration_initialization_and_processing(self):
        """
        Test if the Calibration class initializes correctly and calculates
        the homography matrix and pixel ratio.
        """
        calibration = Calibration(self.polygon, self.real_width_cm, self.real_height_cm)

        # 1. Test if homography matrix is calculated and has the correct shape
        self.assertIsNotNone(calibration.homography_matrix)
        self.assertEqual(calibration.homography_matrix.shape, (3, 3))

        # 2. Test if the pixel-to-cm ratio is calculated correctly
        # Based on the hardcoded target width of 600px in Calibration class
        target_width_px = 600
        aspect_ratio = self.real_height_cm / self.real_width_cm
        target_height_px = int(target_width_px * aspect_ratio)

        expected_ratio_x = target_width_px / self.real_width_cm
        expected_ratio_y = target_height_px / self.real_height_cm

        self.assertAlmostEqual(calibration.pixel_per_cm_ratio[0], expected_ratio_x)
        self.assertAlmostEqual(calibration.pixel_per_cm_ratio[1], expected_ratio_y)
        self.assertEqual(
            calibration.target_dims_px, (target_width_px, target_height_px)
        )

    def test_warp_frame(self):
        """
        Test if the warp_frame method returns a frame with the correct dimensions.
        """
        calibration = Calibration(self.polygon, self.real_width_cm, self.real_height_cm)

        # Create a dummy frame
        original_frame = np.zeros((600, 800, 3), dtype=np.uint8)

        warped_frame = calibration.warp_frame(original_frame)

        # The warped frame should have the target dimensions calculated during calibration
        expected_height, expected_width = (
            calibration.target_dims_px[1],
            calibration.target_dims_px[0],
        )

        self.assertEqual(warped_frame.shape[0], expected_height)
        self.assertEqual(warped_frame.shape[1], expected_width)

    def test_order_points(self):
        """
        Test the _order_points static method to ensure it sorts corners correctly.
        """
        pts = np.array(
            [
                (0, 100),  # bottom-left
                (100, 0),  # top-right
                (100, 100),  # bottom-right
                (0, 0),  # top-left
            ],
            dtype="float32",
        )

        ordered = Calibration._order_points(pts)

        # Expected order: top-left, top-right, bottom-right, bottom-left
        expected = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype="float32")

        np.testing.assert_array_equal(ordered, expected)


if __name__ == "__main__":
    unittest.main()
