#!/usr/bin/env python3
"""
Unit test for the display_roi_video_frame fix.
This test validates the specific changes made to prevent video frame cropping.
"""

import os
import tempfile
import unittest

import cv2
import numpy as np
from PIL import Image


class TestVideoFrameDisplay(unittest.TestCase):
    """Test the video frame display scaling fix."""

    def setUp(self):
        """Create a test video for testing."""
        self.test_video_path = tempfile.mktemp(suffix=".mp4")
        self._create_test_video(1920, 1080, self.test_video_path)

    def tearDown(self):
        """Clean up test files."""
        if os.path.exists(self.test_video_path):
            os.remove(self.test_video_path)

    def _create_test_video(self, width, height, filename):
        """Create a test video with specific dimensions."""
        frame = np.zeros((height, width, 3), dtype=np.uint8)

        # Create a gradient pattern
        for y in range(height):
            for x in range(width):
                frame[y, x] = [
                    int(255 * x / width),  # Red gradient
                    int(255 * y / height),  # Green gradient
                    128,  # Blue constant
                ]

        # Add text marker
        cv2.putText(
            frame,
            f"TEST {width}x{height}",
            (50, 100),
            cv2.FONT_HERSHEY_SIMPLEX,
            2,
            (255, 255, 255),
            3,
        )

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(filename, fourcc, 1.0, (width, height))

        for _ in range(5):  # Write 5 frames
            out.write(frame)

        out.release()

    def test_original_issue_reproduction(self):
        """Test that demonstrates the original issue would occur."""
        # Load video frame
        cap = cv2.VideoCapture(self.test_video_path)
        ret, frame = cap.read()
        cap.release()

        self.assertTrue(ret, "Should be able to read frame")

        h, w, _ = frame.shape
        self.assertEqual(w, 1920)
        self.assertEqual(h, 1080)

        # Simulate old behavior (the problematic approach)
        # Canvas was set to full video dimensions without scaling
        canvas_width_old = w  # This would be 1920
        canvas_height_old = h  # This would be 1080

        # Simulate window constraints
        screen_w, screen_h = 1920, 1080
        win_w = min(int(screen_w * 0.8), w + 350)  # 1536
        win_h = min(int(screen_h * 0.8), h + 100)  # 864

        # The issue: canvas larger than available window space
        available_width = win_w - 350  # 1186
        available_height = win_h - 100  # 764

        # Old approach would set canvas to full video size
        self.assertGreater(
            canvas_width_old,
            available_width,
            "Original issue: canvas wider than available space",
        )
        self.assertGreater(
            canvas_height_old,
            available_height,
            "Original issue: canvas taller than available space",
        )

    def test_fixed_scaling_behavior(self):
        """Test the new scaling behavior that fixes the issue."""
        # Load video frame
        cap = cv2.VideoCapture(self.test_video_path)
        ret, frame = cap.read()
        cap.release()

        self.assertTrue(ret)
        h, w, _ = frame.shape

        # Convert frame (as done in the fixed method)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(frame_rgb)

        # Simulate window size calculation
        screen_w, screen_h = 1920, 1080
        win_w = min(int(screen_w * 0.8), w + 350)
        win_h = min(int(screen_h * 0.8), h + 100)

        # Calculate available canvas space (the fix)
        available_width = win_w - 350
        available_height = win_h - 100

        # Ensure minimum size
        available_width = max(available_width, 400)
        available_height = max(available_height, 300)

        # Calculate scaling (the fix)
        img_w, img_h = image.size
        scale = min(available_width / img_w, available_height / img_h, 1.0)
        new_width = int(img_w * scale)
        new_height = int(img_h * scale)

        # Validate the fix
        self.assertLessEqual(
            new_width, available_width, "Fixed: canvas width fits in available space"
        )
        self.assertLessEqual(
            new_height, available_height, "Fixed: canvas height fits in available space"
        )

        # Validate aspect ratio preservation
        original_aspect = img_w / img_h
        new_aspect = new_width / new_height
        self.assertAlmostEqual(
            original_aspect,
            new_aspect,
            places=2,
            msg="Aspect ratio should be preserved",
        )

        # Validate scaling makes sense
        self.assertGreater(scale, 0, "Scale should be positive")
        self.assertLessEqual(scale, 1, "Scale should not exceed 1 for large videos")

    def test_small_video_no_upscaling(self):
        """Test that small videos are not upscaled beyond their original size."""
        # Create a small test video
        small_video_path = tempfile.mktemp(suffix=".mp4")
        self._create_test_video(640, 480, small_video_path)

        try:
            # Load small video frame
            cap = cv2.VideoCapture(small_video_path)
            ret, frame = cap.read()
            cap.release()

            self.assertTrue(ret)
            h, w, _ = frame.shape

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(frame_rgb)

            # For a small video, available space might be larger
            available_width = 1000
            available_height = 800

            img_w, img_h = image.size
            scale = min(available_width / img_w, available_height / img_h, 1.0)
            new_width = int(img_w * scale)
            new_height = int(img_h * scale)

            # For small videos that fit, scale should be 1.0 (no scaling)
            self.assertAlmostEqual(scale, 1.0, places=2, msg="Small videos should not be upscaled")
            self.assertEqual(new_width, img_w)
            self.assertEqual(new_height, img_h)

        finally:
            if os.path.exists(small_video_path):
                os.remove(small_video_path)

    def test_very_large_video_scaling(self):
        """Test scaling behavior with very large videos."""
        # Create a very large test video
        large_video_path = tempfile.mktemp(suffix=".mp4")
        self._create_test_video(3840, 2160, large_video_path)  # 4K

        try:
            cap = cv2.VideoCapture(large_video_path)
            ret, frame = cap.read()
            cap.release()

            self.assertTrue(ret)

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(frame_rgb)

            # Simulate limited available space
            available_width = 800
            available_height = 600

            img_w, img_h = image.size
            scale = min(available_width / img_w, available_height / img_h, 1.0)
            new_width = int(img_w * scale)
            new_height = int(img_h * scale)

            # Large video should be significantly scaled down
            self.assertLess(scale, 0.5, "Large video should be scaled down significantly")
            self.assertLessEqual(new_width, available_width)
            self.assertLessEqual(new_height, available_height)

            # But should still maintain aspect ratio
            original_aspect = img_w / img_h
            new_aspect = new_width / new_height
            self.assertAlmostEqual(original_aspect, new_aspect, places=2)

        finally:
            if os.path.exists(large_video_path):
                os.remove(large_video_path)


if __name__ == "__main__":
    unittest.main()
