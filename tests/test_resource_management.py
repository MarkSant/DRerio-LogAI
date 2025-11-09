"""Test resource management and context managers."""

from unittest.mock import Mock, patch

import numpy as np
import pytest

from zebtrack.core.detector import ZoneData
from zebtrack.core.live_camera_service import LiveCameraService
from zebtrack.io.camera import Camera
from zebtrack.io.recorder import Recorder


class TestCameraContextManager:
    """Test Camera context manager."""

    @pytest.mark.unit
    def test_context_manager_releases_camera(self, settings_obj):
        """Context manager automatically releases camera."""
        with patch('cv2.VideoCapture') as mock_capture_class:
            # Setup mock
            mock_cap = Mock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
            mock_cap.get.side_effect = lambda prop: {
                3: 640,  # CAP_PROP_FRAME_WIDTH
                4: 480,  # CAP_PROP_FRAME_HEIGHT
                5: 30.0,  # CAP_PROP_FPS
            }.get(prop, 0)
            mock_capture_class.return_value = mock_cap

            # Use context manager
            with Camera(settings_obj=settings_obj) as camera:
                assert camera is not None
                assert camera.cap is not None

            # After exit, camera should be released
            mock_cap.release.assert_called()

    @pytest.mark.unit
    def test_context_manager_releases_on_exception(self, settings_obj):
        """Context manager releases camera even if exception raised."""
        with patch('cv2.VideoCapture') as mock_capture_class:
            # Setup mock
            mock_cap = Mock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
            mock_cap.get.side_effect = lambda prop: {
                3: 640,  # CAP_PROP_FRAME_WIDTH
                4: 480,  # CAP_PROP_FRAME_HEIGHT
                5: 30.0,  # CAP_PROP_FPS
            }.get(prop, 0)
            mock_capture_class.return_value = mock_cap

            # Exception should be raised, but camera still cleaned up
            with pytest.raises(RuntimeError):
                with Camera(settings_obj=settings_obj):
                    raise RuntimeError("Test error")
            # Still cleaned up
            mock_cap.release.assert_called()

    @pytest.mark.unit
    def test_context_manager_handles_cleanup_failure(self, settings_obj):
        """Context manager handles cleanup failures gracefully."""
        with patch('cv2.VideoCapture') as mock_capture_class:
            # Setup mock that fails on release
            mock_cap = Mock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
            mock_cap.get.side_effect = lambda prop: {
                3: 640,  # CAP_PROP_FRAME_WIDTH
                4: 480,  # CAP_PROP_FRAME_HEIGHT
                5: 30.0,  # CAP_PROP_FPS
            }.get(prop, 0)
            mock_cap.release.side_effect = Exception("Release failed")
            mock_capture_class.return_value = mock_cap

            # Should not raise exception even if cleanup fails
            with Camera(settings_obj=settings_obj):
                pass

            # Cleanup was attempted
            mock_cap.release.assert_called()


class TestRecorderContextManager:
    """Test Recorder context manager."""

    @pytest.mark.unit
    def test_context_manager_stops_recording(self, tmp_path, settings_obj):
        """Context manager automatically stops recording."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        recorder = Recorder(settings_obj=settings_obj)

        # Mock the video writer to avoid actual file creation issues
        with patch('cv2.VideoWriter') as mock_writer_class:
            mock_writer = Mock()
            mock_writer.isOpened.return_value = True
            mock_writer_class.return_value = mock_writer

            with recorder:
                # Start recording
                zones = ZoneData()
                zones.polygon = [(0, 0), (100, 0), (100, 100), (0, 100)]
                recorder.start_recording(
                    output_folder=str(output_dir),
                    frame_width=640,
                    frame_height=480,
                    zones=zones,
                    is_video_file=False,
                )
                assert recorder.is_recording

            # After exit, recording should be stopped
            assert not recorder.is_recording
            mock_writer.release.assert_called()

    @pytest.mark.unit
    def test_context_manager_force_stop_on_exception(self, tmp_path, settings_obj):
        """Context manager force stops on exception."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        recorder = Recorder(settings_obj=settings_obj)

        # Mock the video writer
        with patch('cv2.VideoWriter') as mock_writer_class:
            mock_writer = Mock()
            mock_writer.isOpened.return_value = True
            mock_writer_class.return_value = mock_writer

            with pytest.raises(RuntimeError):
                with recorder:
                    zones = ZoneData()
                    zones.polygon = [(0, 0), (100, 0), (100, 100), (0, 100)]
                    recorder.start_recording(
                        output_folder=str(output_dir),
                        frame_width=640,
                        frame_height=480,
                        zones=zones,
                        is_video_file=False,
                    )
                    raise RuntimeError("Test error")
            # Recording should be stopped (force stop)
            assert not recorder.is_recording
            mock_writer.release.assert_called()

    @pytest.mark.unit
    def test_context_manager_no_recording_started(self, settings_obj):
        """Context manager handles case where no recording was started."""
        recorder = Recorder(settings_obj=settings_obj)

        # Should not raise exception even if no recording started
        with recorder:
            pass

        assert not recorder.is_recording


class TestLiveCameraServiceContextManager:
    """Test LiveCameraService context manager."""

    @pytest.mark.unit
    def test_context_manager_stops_session(self):
        """Context manager automatically stops session."""
        # Create mocks for dependencies
        mock_controller = Mock()
        mock_state_manager = Mock()
        mock_project_manager = Mock()
        mock_recording_service = Mock()
        mock_detector_service = Mock()
        mock_root = Mock()

        service = LiveCameraService(
            controller=mock_controller,
            state_manager=mock_state_manager,
            project_manager=mock_project_manager,
            recording_service=mock_recording_service,
            detector_service=mock_detector_service,
            root=mock_root,
        )

        # Mock stop_session to avoid actual cleanup
        with patch.object(service, 'stop_session') as mock_stop:
            with service:
                pass

            # stop_session should be called on exit
            mock_stop.assert_called_once()

    @pytest.mark.unit
    def test_context_manager_stops_on_exception(self):
        """Context manager stops session even on exception."""
        # Create mocks for dependencies
        mock_controller = Mock()
        mock_state_manager = Mock()
        mock_project_manager = Mock()
        mock_recording_service = Mock()
        mock_detector_service = Mock()
        mock_root = Mock()

        service = LiveCameraService(
            controller=mock_controller,
            state_manager=mock_state_manager,
            project_manager=mock_project_manager,
            recording_service=mock_recording_service,
            detector_service=mock_detector_service,
            root=mock_root,
        )

        # Mock stop_session
        with patch.object(service, 'stop_session') as mock_stop:
            with pytest.raises(RuntimeError):
                with service:
                    raise RuntimeError("Test error")
            # stop_session should still be called
            mock_stop.assert_called_once()

    @pytest.mark.unit
    def test_context_manager_handles_stop_failure(self):
        """Context manager handles stop_session failures gracefully."""
        # Create mocks for dependencies
        mock_controller = Mock()
        mock_state_manager = Mock()
        mock_project_manager = Mock()
        mock_recording_service = Mock()
        mock_detector_service = Mock()
        mock_root = Mock()

        service = LiveCameraService(
            controller=mock_controller,
            state_manager=mock_state_manager,
            project_manager=mock_project_manager,
            recording_service=mock_recording_service,
            detector_service=mock_detector_service,
            root=mock_root,
        )

        # Mock stop_session to raise exception
        with patch.object(service, 'stop_session', side_effect=Exception("Stop failed")):
            # Should not raise exception even if stop fails
            with service:
                pass

            # Exception was caught and logged


class TestResourceCleanupIntegration:
    """Integration tests for resource cleanup."""

    @pytest.mark.integration
    def test_nested_context_managers(self, tmp_path, settings_obj):
        """Test nested context managers clean up properly."""
        with patch('cv2.VideoCapture') as mock_capture_class, \
             patch('cv2.VideoWriter') as mock_writer_class:
            # Setup camera mock
            mock_cap = Mock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
            mock_cap.get.side_effect = lambda prop: {
                3: 640,  # CAP_PROP_FRAME_WIDTH
                4: 480,  # CAP_PROP_FRAME_HEIGHT
                5: 30.0,  # CAP_PROP_FPS
            }.get(prop, 0)
            mock_capture_class.return_value = mock_cap

            # Setup recorder mock
            mock_writer = Mock()
            mock_writer.isOpened.return_value = True
            mock_writer_class.return_value = mock_writer

            # Use nested context managers
            with Camera(settings_obj=settings_obj) as camera:
                with Recorder(settings_obj=settings_obj) as recorder:
                    # Both resources acquired
                    assert camera is not None
                    assert recorder is not None

            # Both resources cleaned up
            mock_cap.release.assert_called()

    @pytest.mark.integration
    def test_exception_in_nested_contexts(self, tmp_path, settings_obj):
        """Test exception handling in nested context managers."""
        with patch('cv2.VideoCapture') as mock_capture_class, \
             patch('cv2.VideoWriter') as mock_writer_class:
            # Setup camera mock
            mock_cap = Mock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
            mock_cap.get.side_effect = lambda prop: {
                3: 640,  # CAP_PROP_FRAME_WIDTH
                4: 480,  # CAP_PROP_FRAME_HEIGHT
                5: 30.0,  # CAP_PROP_FPS
            }.get(prop, 0)
            mock_capture_class.return_value = mock_cap

            # Setup recorder mock
            mock_writer = Mock()
            mock_writer.isOpened.return_value = True
            mock_writer_class.return_value = mock_writer

            # Exception in nested context
            with pytest.raises(RuntimeError):
                with Camera(settings_obj=settings_obj):
                    with Recorder(settings_obj=settings_obj):
                        raise RuntimeError("Test error")
            # Both resources still cleaned up
            mock_cap.release.assert_called()
