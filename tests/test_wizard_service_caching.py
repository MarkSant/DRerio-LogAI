"""
Tests for WizardService hardware detection caching (Phase 5.4).

Validates that hardware detection results are properly cached to improve
performance and reduce unnecessary hardware probing.
"""

import time
from unittest.mock import MagicMock, patch

import numpy as np

from zebtrack.core.services.wizard_service import WizardService


class TestWizardServiceCaching:
    """Test caching functionality in WizardService."""

    def setup_method(self):
        """Clear cache before each test."""
        WizardService.clear_hardware_cache()

    def teardown_method(self):
        """Clear cache after each test."""
        WizardService.clear_hardware_cache()

    @patch("cv2.VideoCapture")
    def test_camera_detection_caches_results(self, mock_video_capture):
        """Test that camera detection results are cached."""
        # Setup mock with real numpy frame to pass ghost detection
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = [640, 480, 30.0]  # width, height, fps
        # Create a valid frame (not black) to pass ghost camera detection
        valid_frame = np.ones((480, 640, 3), dtype=np.uint8) * 128
        mock_cap.read.return_value = (True, valid_frame)
        mock_video_capture.return_value = mock_cap

        # First call should hit the actual detection
        cameras1 = WizardService.detect_available_cameras()
        assert len(cameras1) > 0
        first_call_count = mock_video_capture.call_count

        # Second call should use cache (no new VideoCapture calls)
        cameras2 = WizardService.detect_available_cameras()
        assert cameras2 == cameras1
        assert mock_video_capture.call_count == first_call_count  # Same count = cache used

    @patch("cv2.VideoCapture")
    def test_camera_detection_force_refresh(self, mock_video_capture):
        """Test that use_cache=False forces fresh detection."""

        # Setup mock to return consistent values
        def create_mock_cap(*args, **kwargs):
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.get.side_effect = [640, 480, 30.0]
            return mock_cap

        mock_video_capture.side_effect = create_mock_cap

        # First call
        cameras1 = WizardService.detect_available_cameras()
        first_call_count = mock_video_capture.call_count

        # Second call with use_cache=False should re-detect
        cameras2 = WizardService.detect_available_cameras(use_cache=False)
        assert len(cameras2) == len(cameras1)  # Same number of cameras detected
        assert mock_video_capture.call_count > first_call_count  # More calls = fresh detection

    @patch("serial.tools.list_ports.comports")
    @patch("zebtrack.io.arduino.Arduino.scan_available_ports")
    def test_arduino_detection_caches_results(self, mock_scan, mock_comports):
        """Test that Arduino detection results are cached."""
        # Setup mocks
        mock_port = MagicMock()
        mock_port.device = "COM3"
        mock_port.description = "Arduino Uno"
        mock_scan.return_value = ([mock_port], [])
        mock_comports.return_value = []

        # First call should hit the actual detection
        ports1 = WizardService.detect_arduino_ports()
        assert len(ports1) > 0
        first_call_count = mock_scan.call_count

        # Second call should use cache
        ports2 = WizardService.detect_arduino_ports()
        assert ports2 == ports1
        assert mock_scan.call_count == first_call_count  # Same count = cache used

    @patch("serial.tools.list_ports.comports")
    @patch("zebtrack.io.arduino.Arduino.scan_available_ports")
    def test_arduino_detection_force_refresh(self, mock_scan, mock_comports):
        """Test that use_cache=False forces fresh Arduino detection."""
        # Setup mocks
        mock_port = MagicMock()
        mock_port.device = "COM3"
        mock_port.description = "Arduino Uno"
        mock_scan.return_value = ([mock_port], [])
        mock_comports.return_value = []

        # First call
        ports1 = WizardService.detect_arduino_ports()
        first_call_count = mock_scan.call_count

        # Second call with use_cache=False should re-detect
        ports2 = WizardService.detect_arduino_ports(use_cache=False)
        assert ports2 == ports1
        assert mock_scan.call_count > first_call_count  # More calls = fresh detection

    @patch("cv2.VideoCapture")
    def test_cache_expiration_after_ttl(self, mock_video_capture):
        """Test that cache expires after TTL."""

        # Setup mock to return consistent values
        def create_mock_cap(*args, **kwargs):
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.get.side_effect = [640, 480, 30.0]
            return mock_cap

        mock_video_capture.side_effect = create_mock_cap

        # Temporarily reduce TTL for testing
        original_ttl = WizardService._hw_cache.ttl_seconds
        WizardService._hw_cache.ttl_seconds = 0.1  # 100ms

        try:
            # First call
            cameras1 = WizardService.detect_available_cameras()
            first_call_count = mock_video_capture.call_count

            # Wait for cache to expire (intentional delay for TTL test)
            time.sleep(0.15)

            # Second call should re-detect because cache expired
            cameras2 = WizardService.detect_available_cameras()
            assert len(cameras2) == len(cameras1)  # Same number of cameras
            assert mock_video_capture.call_count > first_call_count  # Cache expired, re-detected

        finally:
            # Restore original TTL
            WizardService._hw_cache.ttl_seconds = original_ttl

    def test_clear_cache_method(self):
        """Test that clear_hardware_cache clears all caches."""
        # Manually set some cache values via TTLCache API
        WizardService._hw_cache.set("cameras", [{"index": 0}])
        WizardService._hw_cache.set("arduino", [{"device": "COM3"}])

        # Clear cache
        WizardService.clear_hardware_cache()

        # Verify all caches are cleared
        assert WizardService._hw_cache.get("cameras") is None
        assert WizardService._hw_cache.get("arduino") is None

    @patch("cv2.VideoCapture")
    def test_cache_reduces_detection_time(self, mock_video_capture):
        """Test that caching significantly reduces detection time."""
        # Setup mock with slight delay to simulate real detection
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = [640, 480, 30.0, 640, 480, 30.0]
        # Valid frame for ghost detection
        valid_frame = np.ones((480, 640, 3), dtype=np.uint8) * 128
        mock_cap.read.return_value = (True, valid_frame)

        def delayed_capture(*args, **kwargs):
            time.sleep(0.01)  # Intentional: simulate 10ms detection time
            return mock_cap

        mock_video_capture.side_effect = delayed_capture

        # First call (no cache)
        start1 = time.time()
        cameras1 = WizardService.detect_available_cameras()
        time1 = time.time() - start1

        # Second call (with cache)
        start2 = time.time()
        cameras2 = WizardService.detect_available_cameras()
        time2 = time.time() - start2

        # Cached call should be significantly faster (at least 5x faster)
        assert time2 < time1 / 5
        assert cameras2 == cameras1

    @patch("cv2.VideoCapture")
    @patch("serial.tools.list_ports.comports")
    @patch("zebtrack.io.arduino.Arduino.scan_available_ports")
    def test_independent_caches(self, mock_scan, mock_comports, mock_video_capture):
        """Test that camera and Arduino caches are independent."""
        # Setup mocks
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = [640, 480, 30.0, 640, 480, 30.0]
        # Valid frame for ghost detection
        valid_frame = np.ones((480, 640, 3), dtype=np.uint8) * 128
        mock_cap.read.return_value = (True, valid_frame)
        mock_video_capture.return_value = mock_cap

        mock_port = MagicMock()
        mock_port.device = "COM3"
        mock_port.description = "Arduino Uno"
        mock_scan.return_value = ([mock_port], [])
        mock_comports.return_value = []

        # Detect cameras (populates camera cache)
        WizardService.detect_available_cameras()
        camera_calls1 = mock_video_capture.call_count

        # Detect Arduino (populates Arduino cache)
        WizardService.detect_arduino_ports()
        arduino_calls1 = mock_scan.call_count

        # Detect cameras again (should use cache)
        WizardService.detect_available_cameras()
        assert mock_video_capture.call_count == camera_calls1  # Cache used

        # Detect Arduino again (should use cache)
        WizardService.detect_arduino_ports()
        assert mock_scan.call_count == arduino_calls1  # Cache used

        # Force refresh cameras only
        WizardService.detect_available_cameras(use_cache=False)
        assert mock_video_capture.call_count > camera_calls1  # Fresh detection

        # Arduino cache should still be valid
        WizardService.detect_arduino_ports()
        assert mock_scan.call_count == arduino_calls1  # Cache still used
