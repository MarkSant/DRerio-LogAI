#!/usr/bin/env python3
"""
Tests for validating that detector.draw_overlay integration is correctly implemented.
These tests verify the code structure rather than mocking complex Tkinter interactions.
"""

import os
import unittest


class TestOverlayIntegration(unittest.TestCase):
    """
    Test the integration between detector overlay and GUI display via code
    verification.
    """

    def test_detector_draw_overlay_called_in_controller(self):
        """Test that detector.draw_overlay is called in run_tracking_if_needed.
        
        Phase 3: Updated to check VideoProcessingService after refactoring.
        The implementation was moved from MainViewModel to VideoProcessingService.
        """
        # Check VideoProcessingService where the implementation now lives
        service_file = os.path.join(
            os.path.dirname(__file__), "..", "src", "zebtrack", "core", "video_processing_service.py"
        )

        with open(service_file, encoding="utf-8") as f:
            content = f.read()

        # Verify that draw_overlay is called in the tracking method
        assert "self.detector.draw_overlay(frame, detections)" in content, (
            "detector.draw_overlay should be called with frame and detections"
        )

        # Verify it's called within the run_tracking_if_needed method
        if "def run_tracking_if_needed(" in content:
            tracking_section = content.split("def run_tracking_if_needed(")[1]
            if "\n    def " in tracking_section:
                tracking_section = tracking_section.split("\n    def ")[0]
            assert "draw_overlay" in tracking_section, (
                "draw_overlay should be called in run_tracking_if_needed method"
            )
        
        # Also verify that MainViewModel delegates to the service
        controller_file = os.path.join(
            os.path.dirname(__file__), "..", "src", "zebtrack", "core", "main_view_model.py"
        )
        
        with open(controller_file, encoding="utf-8") as f:
            controller_content = f.read()
        
        assert "self.video_processing_service.run_tracking_if_needed" in controller_content, (
            "MainViewModel should delegate to video_processing_service.run_tracking_if_needed"
        )

    def test_display_analysis_frame_preserves_overlays(self):
        """Test that display_analysis_frame doesn't redraw overlays."""
        gui_file = os.path.join(os.path.dirname(__file__), "..", "src", "zebtrack", "ui", "gui.py")

        with open(gui_file, encoding="utf-8") as f:
            content = f.read()

        # Find the display_analysis_frame method
        if "def display_analysis_frame(" in content:
            display_section = content.split("def display_analysis_frame(")[1]
            if "\n    def " in display_section:
                display_section = display_section.split("\n    def ")[0]

            # Remove comments to check only actual code
            lines = [
                line for line in display_section.split("\n") if not line.strip().startswith("#")
            ]
            code_only = "\n".join(lines)

            # Verify it doesn't call detector.draw_overlay as a function call
            # (overlays should already be drawn by controller)
            assert ".draw_overlay(" not in code_only, (
                "display_analysis_frame should not call draw_overlay (overlays already on frame)"
            )

    def test_bounding_box_visibility_in_overlays(self):
        """Test that bounding boxes are drawn in detector overlay method."""
        detector_file = os.path.join(
            os.path.dirname(__file__), "..", "src", "zebtrack", "core", "detector.py"
        )

        with open(detector_file, encoding="utf-8") as f:
            content = f.read()

        # Verify draw_overlay method exists
        assert "def draw_overlay(self" in content, "Detector should have draw_overlay method"

        # Verify it draws rectangles (bounding boxes)
        overlay_section = content.split("def draw_overlay(self")[1].split("def ")[0]
        assert "cv2.rectangle" in overlay_section, (
            "draw_overlay should draw rectangles for bounding boxes"
        )

    def test_frame_flow_with_real_overlays(self):
        """Test that frame processing flow is correct in VideoProcessingService.
        
        Phase 3: Updated to check VideoProcessingService after refactoring.
        The implementation was moved from MainViewModel to VideoProcessingService.
        """
        # Check VideoProcessingService where the implementation now lives
        service_file = os.path.join(
            os.path.dirname(__file__), "..", "src", "zebtrack", "core", "video_processing_service.py"
        )

        with open(service_file, encoding="utf-8") as f:
            content = f.read()

        if "def run_tracking_if_needed(" in content:
            tracking_section = content.split("def run_tracking_if_needed(")[1]
            if "\n    def " in tracking_section:
                tracking_section = tracking_section.split("\n    def ")[0]

            # Verify processing order:
            # 1. detect frames -> 2. draw overlay -> 3. send to callback
            assert "self.detector.detect" in tracking_section, (
                "Should call detect to detect objects"
            )
            assert "draw_overlay" in tracking_section, "Should call draw_overlay after detection"
            assert "progress_callback" in tracking_section, (
                "Should call progress_callback to send frame to GUI"
            )

            # Verify draw_overlay comes before progress_callback in the flow
            detect_pos = tracking_section.find("self.detector.detect")
            overlay_pos = tracking_section.find("draw_overlay")
            callback_pos = tracking_section.find("progress_callback(")

            assert detect_pos < overlay_pos < callback_pos, (
                "Frame processing order should be: detect -> overlay -> callback"
            )


if __name__ == "__main__":
    unittest.main()
