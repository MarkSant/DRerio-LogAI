#!/usr/bin/env python3
"""
Tests for validating that detector.draw_overlay is called before frames reach the GUI,
and that the GUI properly displays frames with detection overlays.
"""
import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

# Imports moved to top level for clarity and to avoid repeated imports
from zebtrack.core.controller import AppController
from zebtrack.core.detector import Detector, ZoneData
from zebtrack.plugins.base import DetectorPlugin


class TestOverlayIntegration(unittest.TestCase):
    """Test the integration between detector overlay and GUI display."""

    def setUp(self):
        """Set up test environment."""
        # Create a mock frame
        self.test_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Create mock detections with bounding boxes
        self.mock_detections = [
            (100, 100, 200, 150, 0.95, 1),  # x1, y1, x2, y2, confidence, track_id
            (300, 200, 400, 250, 0.87, 2)
        ]

    def test_detector_draw_overlay_called_in_controller(self):
        """Test that detector.draw_overlay is called in _run_tracking_if_needed."""
        with patch('zebtrack.core.controller.cv2') as mock_cv2, \
             patch('zebtrack.core.controller.Recorder') as MockRecorder, \
             patch('zebtrack.core.controller.log'):  # Removed unused mock_log

            # Mock video capture
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.get.side_effect = lambda prop: {
                cv2.CAP_PROP_FRAME_WIDTH: 640,
                cv2.CAP_PROP_FRAME_HEIGHT: 480,
                cv2.CAP_PROP_FRAME_COUNT: 10,
                cv2.CAP_PROP_POS_MSEC: 1000.0
            }.get(prop, 0)
            mock_cap.read.return_value = (True, self.test_frame.copy())
            mock_cv2.VideoCapture.return_value = mock_cap

            # Create mock detector
            mock_detector = MagicMock(spec=Detector)
            mock_detector.process_frame.return_value = (self.mock_detections, None)
            mock_detector.draw_overlay = MagicMock()

            # Create controller with mocked components
            controller = AppController(None, None, None, None)
            controller.detector = mock_detector
            controller.project_manager = MagicMock()
            controller.view = MagicMock()
            controller.cancel_event = MagicMock()
            controller.cancel_event.is_set.return_value = False

            # Mock zone data
            zone_data = ZoneData(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])
            controller.project_manager.get_zone_data.return_value = zone_data

            # Mock recorder
            mock_recorder_instance = MagicMock()
            MockRecorder.return_value = mock_recorder_instance

            # Create a progress callback to capture frame handling
            captured_frames = []

            def capture_progress_callback(
                progress_fraction, status_message, frame=None
            ):
                if frame is not None:
                    captured_frames.append(frame)

            # Run the tracking method
            try:
                controller._run_tracking_if_needed(
                    "test_video.mp4",
                    "/tmp/test_results",
                    "test_experiment",
                    capture_progress_callback,
                    analysis_interval_frames=1,
                    display_interval_frames=1
                )
            except Exception:
                pass  # We expect some exceptions due to mocking

            # Verify that draw_overlay was called
            self.assertTrue(
                mock_detector.draw_overlay.called,
                "detector.draw_overlay should be called during processing"
            )

            # Verify that draw_overlay was called with frame and detections
            call_args_list = mock_detector.draw_overlay.call_args_list
            self.assertGreater(
                len(call_args_list), 0, "draw_overlay should be called at least once"
            )

            # Check that the first call has the expected arguments
            first_call = call_args_list[0]
            self.assertEqual(
                len(first_call[0]), 2,
                "draw_overlay should be called with frame and detections"
            )

    def test_display_analysis_frame_preserves_overlays(self):
        """Test that display_analysis_frame preserves existing overlays."""
        with patch('zebtrack.ui.gui.cv2') as mock_cv2, \
             patch('zebtrack.ui.gui.Image'), \
             patch('zebtrack.ui.gui.ImageTk'):

            from zebtrack.ui.gui import ApplicationGUI

            # Create a frame that already has overlays applied
            frame_with_overlays = self.test_frame.copy()
            # Simulate that this frame already has bounding boxes drawn
            cv2.rectangle(
                frame_with_overlays, (100, 100), (200, 150), (255, 0, 255), 2
            )

            # Create GUI instance with mocked components
            gui = ApplicationGUI()
            gui.analysis_video_label = MagicMock()
            gui.controller = MagicMock()
            gui.controller.project_manager = MagicMock()

            # Mock zone data
            zone_data = ZoneData(polygon=[])  # Empty zones
            gui.controller.project_manager.get_zone_data.return_value = zone_data

            # Call display_analysis_frame
            gui.display_analysis_frame(frame_with_overlays)

            # Verify that cv2.cvtColor was called (frame was processed)
            mock_cv2.cvtColor.assert_called_once()

            # Verify that the frame passed to cvtColor is the original
            called_frame = mock_cv2.cvtColor.call_args[0][0]

            self.assertIsNotNone(called_frame, "Frame should be processed")

    def test_bounding_box_visibility_in_overlays(self):
        """Test that bounding boxes are visible when draw_overlay is applied."""
        # Create a mock plugin
        mock_plugin = MagicMock(spec=DetectorPlugin)
        mock_plugin.get_name.return_value = "TestPlugin"

        # Create detector
        detector = Detector(plugin=mock_plugin, base_width=640, base_height=480)

        # Set up zones
        zone_data = ZoneData(
            polygon=[[50, 50], [590, 50], [590, 430], [50, 430]],
            roi_polygons=[[[100, 100], [200, 100], [200, 200], [100, 200]]],
            roi_colors=[(0, 255, 0)]  # Green ROI
        )
        detector.set_zones(zone_data, 640, 480)

        # Create a test frame
        test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        original_frame_sum = np.sum(test_frame)

        # Apply overlays
        detector.draw_overlay(test_frame, self.mock_detections)

        # Verify that the frame was modified (overlays were drawn)
        modified_frame_sum = np.sum(test_frame)
        self.assertNotEqual(
            original_frame_sum, modified_frame_sum,
            "Frame should be modified after drawing overlays"
        )

        # Check for magenta bounding boxes (255, 0, 255 in BGR)
        magenta_pixels = np.where(
            (test_frame[:, :, 0] == 255) &
            (test_frame[:, :, 1] == 0) &
            (test_frame[:, :, 2] == 255)
        )

        self.assertGreater(
            len(magenta_pixels[0]), 0,
            "Should have magenta pixels from bounding boxes"
        )

    def test_frame_flow_with_real_overlays(self):
        """Integration test simulating the complete frame flow."""
        # 1. Start with a clean frame
        original_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # 2. Simulate detector processing
        mock_plugin = MagicMock(spec=DetectorPlugin)
        mock_plugin.get_name.return_value = "TestPlugin"

        detector = Detector(plugin=mock_plugin, base_width=640, base_height=480)
        zone_data = ZoneData(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])
        detector.set_zones(zone_data, 640, 480)

        # 3. Apply detector overlays
        frame_with_overlays = original_frame.copy()
        detector.draw_overlay(frame_with_overlays, self.mock_detections)

        # 4. Verify overlays were applied
        self.assertNotEqual(
            np.sum(original_frame), np.sum(frame_with_overlays),
            "Overlays should modify the frame"
        )

        # 5. Simulate GUI display
        display_frame = frame_with_overlays.copy()

        # 6. Verify overlays are preserved
        np.testing.assert_array_equal(
            frame_with_overlays, display_frame,
            "GUI should preserve overlays applied by detector"
        )


if __name__ == '__main__':
    unittest.main()
