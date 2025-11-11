"""
Testes de Thread Safety para LiveCameraService.

Testa cenários de concorrência, race conditions, e thread lifecycle
para garantir operação segura em ambientes multi-threaded.

IMPORTANTE: Estes testes causam travamento do sistema em Windows.
Marcados como 'slow' para execução controlada.
"""

from __future__ import annotations

import queue
import threading
import time
from unittest.mock import Mock, patch

import numpy as np
import pytest

from zebtrack.core.live_camera_service import LiveCameraService

pytestmark = pytest.mark.slow  # Marca TODOS os testes deste arquivo como slow


@pytest.fixture
def mock_controller():
    """Create a mock MainViewModel controller."""
    controller = Mock()
    controller.settings.video_processing.fps = 30.0
    controller.settings.camera.index = 0
    # Mock recorder with stop_recording method
    controller.recorder = Mock()
    controller.recorder.stop_recording = Mock()
    controller.ui_event_bus = None
    controller.setup_detector.return_value = True
    return controller


@pytest.fixture
def mock_state_manager():
    """Create a mock StateManager."""
    state_manager = Mock()
    return state_manager


@pytest.fixture
def mock_project_manager():
    """Create a mock ProjectManager."""
    project_manager = Mock()
    project_manager.project_data = {}
    project_manager.get_zone_data.return_value = None
    return project_manager


@pytest.fixture
def mock_recording_service():
    """Create a mock RecordingService."""
    recording_service = Mock()
    recording_service.start_session.return_value = True
    recording_service.stop_session.return_value = None
    recording_service._ui_callbacks = {}

    def set_ui_callbacks(callbacks):
        recording_service._ui_callbacks = callbacks.copy()

    recording_service.set_ui_callbacks.side_effect = set_ui_callbacks
    return recording_service


@pytest.fixture
def mock_detector_service():
    """Create a mock DetectorService."""
    detector_service = Mock()
    detector = Mock()
    detector.detect.return_value = ([], None)
    detector.draw_overlay.return_value = None
    detector_service.detector = detector
    detector_service.configure_zones.return_value = None
    return detector_service


@pytest.fixture
def mock_root():
    """Create a mock Tkinter root."""
    root = Mock()
    root.after = Mock(side_effect=lambda delay, func, *args: func(*args))
    # Add Tkinter-specific attributes to avoid errors in LivePreviewWindow
    root._last_child_ids = {}
    root._w = "."
    root.children = {}
    root.tk = Mock()
    root.tk.call = Mock(return_value="")
    return root


@pytest.fixture
def live_camera_service(
    mock_controller,
    mock_state_manager,
    mock_project_manager,
    mock_recording_service,
    mock_detector_service,
    mock_root,
):
    """Create a LiveCameraService instance with mocked dependencies."""
    service = LiveCameraService(
        controller=mock_controller,
        state_manager=mock_state_manager,
        project_manager=mock_project_manager,
        recording_service=mock_recording_service,
        detector_service=mock_detector_service,
        root=mock_root,
    )
    return service


@pytest.fixture
def mock_camera():
    """Create a mock Camera."""
    camera = Mock()
    camera.is_opened.return_value = True
    camera.actual_width = 640
    camera.actual_height = 480
    camera.get_frame.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
    camera.release.return_value = None
    return camera


class TestLiveCameraServiceThreadLifecycle:
    """Test thread lifecycle management."""

    def test_thread_start_stop_lifecycle(self, live_camera_service, mock_camera):
        """Test basic thread start and stop lifecycle."""
        with patch("zebtrack.io.camera.Camera", return_value=mock_camera):
            # Manually setup camera and threads
            live_camera_service.camera = mock_camera
            live_camera_service.exit_event.clear()

            # Start threads
            assert live_camera_service._start_threads() is True
            assert live_camera_service.capture_thread is not None
            assert live_camera_service.processing_thread is not None
            assert live_camera_service.capture_thread.is_alive()
            assert live_camera_service.processing_thread.is_alive()

            # Give threads time to run
            time.sleep(0.2)

            # Stop threads
            live_camera_service.exit_event.set()
            live_camera_service.capture_thread.join(timeout=2.0)
            live_camera_service.processing_thread.join(timeout=2.0)

            # Verify threads stopped
            assert not live_camera_service.capture_thread.is_alive()
            assert not live_camera_service.processing_thread.is_alive()

    def test_rapid_start_stop_cycles(self, live_camera_service, mock_camera):
        """Test rapid start/stop cycles to detect race conditions."""
        with patch("zebtrack.io.camera.Camera", return_value=mock_camera):
            live_camera_service.camera = mock_camera

            for i in range(3):
                # Start threads
                live_camera_service.exit_event.clear()
                assert live_camera_service._start_threads() is True

                # Brief run
                time.sleep(0.1)

                # Stop threads
                live_camera_service.exit_event.set()
                if live_camera_service.capture_thread:
                    live_camera_service.capture_thread.join(timeout=2.0)
                if live_camera_service.processing_thread:
                    live_camera_service.processing_thread.join(timeout=2.0)

            # All threads should be stopped
            assert not live_camera_service.capture_thread.is_alive()
            assert not live_camera_service.processing_thread.is_alive()

    def test_thread_join_timeout_handling(self, live_camera_service, mock_camera):
        """Test that join timeout is handled correctly."""
        with patch("zebtrack.io.camera.Camera", return_value=mock_camera):
            live_camera_service.camera = mock_camera
            live_camera_service.exit_event.clear()

            # Start threads
            live_camera_service._start_threads()

            # Don't set exit event - simulate stuck threads
            # Verify join timeout doesn't hang
            start_time = time.time()
            if live_camera_service.capture_thread:
                live_camera_service.capture_thread.join(timeout=0.5)
            elapsed = time.time() - start_time

            # Should timeout in ~0.5s, not hang forever
            assert elapsed < 1.0, "Join timeout took too long"

            # Cleanup
            live_camera_service.exit_event.set()
            if live_camera_service.capture_thread:
                live_camera_service.capture_thread.join(timeout=2.0)
            if live_camera_service.processing_thread:
                live_camera_service.processing_thread.join(timeout=2.0)

    def test_graceful_shutdown_with_queue_full(self, live_camera_service, mock_camera):
        """Test graceful shutdown when queue is full."""
        with patch("zebtrack.io.camera.Camera", return_value=mock_camera):
            live_camera_service.camera = mock_camera
            live_camera_service.exit_event.clear()

            # Fill the frame queue
            for i in range(30):
                live_camera_service.frame_queue.put((i, np.zeros((480, 640, 3))))

            # Start threads
            live_camera_service._start_threads()
            time.sleep(0.2)

            # Stop session (should clear queues)
            live_camera_service.stop_session()

            # Verify queues cleared
            assert live_camera_service.frame_queue.empty()
            assert live_camera_service.video_queue.empty()


class TestLiveCameraServiceQueueOperations:
    """Test queue operations and edge cases."""

    def test_frame_queue_overflow_handling(self, live_camera_service, mock_camera):
        """Test that frame queue overflow is handled without blocking."""
        with patch("zebtrack.io.camera.Camera", return_value=mock_camera):
            live_camera_service.camera = mock_camera
            live_camera_service.exit_event.clear()

            # Fill the queue to capacity
            for i in range(30):
                live_camera_service.frame_queue.put((i, np.zeros((480, 640, 3))))

            assert live_camera_service.frame_queue.full()

            # Start capture thread
            live_camera_service.capture_thread = threading.Thread(
                target=live_camera_service._capture_loop,
                daemon=False,
            )
            live_camera_service.capture_thread.start()

            # Let it try to add frames (should not block due to queue.full() check)
            time.sleep(0.3)

            # Stop
            live_camera_service.exit_event.set()
            live_camera_service.capture_thread.join(timeout=2.0)

            # Thread should have finished without hanging
            assert not live_camera_service.capture_thread.is_alive()

    def test_frame_queue_empty_handling(self, live_camera_service):
        """Test that empty queue is handled with timeout."""
        live_camera_service.exit_event.clear()

        # Start processing thread with empty queue
        live_camera_service.processing_thread = threading.Thread(
            target=live_camera_service._processing_loop,
            daemon=False,
        )
        live_camera_service.processing_thread.start()

        # Let it run for a bit
        time.sleep(0.3)

        # Stop
        live_camera_service.exit_event.set()
        live_camera_service.processing_thread.join(timeout=2.0)

        # Should exit gracefully without hanging
        assert not live_camera_service.processing_thread.is_alive()

    def test_multiple_producers_consumers(self, live_camera_service, mock_camera):
        """Test queue with multiple concurrent producers and consumers."""
        with patch("zebtrack.io.camera.Camera", return_value=mock_camera):
            live_camera_service.camera = mock_camera
            live_camera_service.exit_event.clear()

            processed_frames = []

            def consumer():
                """Consumer that processes frames."""
                while not live_camera_service.exit_event.is_set():
                    try:
                        frame_num, _frame = live_camera_service.frame_queue.get(timeout=0.5)
                        processed_frames.append(frame_num)
                    except queue.Empty:
                        continue

            # Start producer (capture thread)
            live_camera_service.capture_thread = threading.Thread(
                target=live_camera_service._capture_loop,
                daemon=False,
            )
            live_camera_service.capture_thread.start()

            # Start multiple consumers
            consumers = []
            for i in range(2):
                consumer_thread = threading.Thread(target=consumer, daemon=False)
                consumer_thread.start()
                consumers.append(consumer_thread)

            # Run for a bit
            time.sleep(0.5)

            # Stop all
            live_camera_service.exit_event.set()
            live_camera_service.capture_thread.join(timeout=2.0)
            for consumer_thread in consumers:
                consumer_thread.join(timeout=2.0)

            # Verify some frames were processed
            assert len(processed_frames) > 0

    def test_queue_cleanup_on_stop(self, live_camera_service, mock_camera):
        """Test that queues are properly cleaned up on stop."""
        with patch("zebtrack.io.camera.Camera", return_value=mock_camera):
            # Add items to queues
            for i in range(10):
                live_camera_service.frame_queue.put((i, np.zeros((480, 640, 3))))
                live_camera_service.video_queue.put(np.zeros((480, 640, 3)))

            assert not live_camera_service.frame_queue.empty()
            assert not live_camera_service.video_queue.empty()

            # Clear queues
            live_camera_service._clear_queues()

            # Verify empty
            assert live_camera_service.frame_queue.empty()
            assert live_camera_service.video_queue.empty()


class TestLiveCameraServiceRaceConditions:
    """Test race conditions in concurrent access."""

    def test_concurrent_start_stop_calls(self, live_camera_service, mock_camera):
        """Test concurrent start_session and stop_session calls."""
        with (
            patch("zebtrack.io.camera.Camera", return_value=mock_camera),
            patch("zebtrack.ui.dialogs.LivePreviewWindow"),
        ):
            live_camera_service.camera = mock_camera

            def start_worker():
                live_camera_service.exit_event.clear()
                live_camera_service._start_threads()
                time.sleep(0.1)

            def stop_worker():
                time.sleep(0.05)
                live_camera_service.stop_session()

            # Run start and stop concurrently
            start_thread = threading.Thread(target=start_worker)
            stop_thread = threading.Thread(target=stop_worker)

            start_thread.start()
            stop_thread.start()

            start_thread.join(timeout=3.0)
            stop_thread.join(timeout=3.0)

            # Should complete without deadlock
            assert not start_thread.is_alive()
            assert not stop_thread.is_alive()

    def test_detector_access_during_processing(self, live_camera_service, mock_camera):
        """Test detector access during concurrent processing."""
        with patch("zebtrack.io.camera.Camera", return_value=mock_camera):
            live_camera_service.camera = mock_camera
            live_camera_service.exit_event.clear()

            # Add frames to queue
            for i in range(5):
                live_camera_service.frame_queue.put((i, np.zeros((480, 640, 3))))

            # Start processing thread
            live_camera_service.processing_thread = threading.Thread(
                target=live_camera_service._processing_loop,
                daemon=False,
            )
            live_camera_service.processing_thread.start()

            # Concurrently access detector
            for i in range(3):
                detector = live_camera_service.detector_service.detector
                if detector:
                    detector.detect(np.zeros((480, 640, 3)), "test")
                time.sleep(0.1)

            # Stop
            live_camera_service.exit_event.set()
            live_camera_service.processing_thread.join(timeout=2.0)

            # Should complete without error
            assert not live_camera_service.processing_thread.is_alive()

    def test_preview_update_during_session_stop(self, live_camera_service, mock_camera):
        """Test preview window update during session stop."""
        with patch("zebtrack.io.camera.Camera", return_value=mock_camera):
            live_camera_service.camera = mock_camera
            live_camera_service.preview_window = Mock()
            live_camera_service.exit_event.clear()

            # Add frames to queue
            for i in range(5):
                live_camera_service.frame_queue.put((i, np.zeros((480, 640, 3))))

            # Start processing
            live_camera_service.processing_thread = threading.Thread(
                target=live_camera_service._processing_loop,
                daemon=False,
            )
            live_camera_service.processing_thread.start()

            # Let processing start
            time.sleep(0.1)

            # Stop session (which destroys preview window)
            live_camera_service.stop_session()

            # Should complete without error
            assert not live_camera_service.processing_thread.is_alive()

    def test_state_manager_concurrent_updates(self, live_camera_service, mock_camera):
        """Test concurrent state manager updates."""
        with patch("zebtrack.io.camera.Camera", return_value=mock_camera):
            live_camera_service.camera = mock_camera

            def update_worker():
                for i in range(5):
                    live_camera_service.state_manager.update_processing_state(
                        source=f"worker_{threading.current_thread().name}",
                        is_processing=(i % 2 == 0),
                    )
                    time.sleep(0.01)

            # Start multiple workers
            workers = []
            for i in range(3):
                worker = threading.Thread(target=update_worker)
                worker.start()
                workers.append(worker)

            # Wait for completion
            for worker in workers:
                worker.join(timeout=2.0)

            # All workers should complete
            for worker in workers:
                assert not worker.is_alive()


class TestLiveCameraServiceErrorHandling:
    """Test error handling in threaded operations."""

    def test_camera_disconnect_during_capture(self, live_camera_service, mock_camera):
        """Test camera disconnect during capture loop."""
        with patch("zebtrack.io.camera.Camera", return_value=mock_camera):
            live_camera_service.camera = mock_camera
            live_camera_service.exit_event.clear()

            # Simulate camera disconnect after a few frames
            call_count = [0]

            def failing_get_frame():
                call_count[0] += 1
                if call_count[0] > 3:
                    return (False, None)
                return (True, np.zeros((480, 640, 3), dtype=np.uint8))

            mock_camera.get_frame = failing_get_frame

            # Start capture thread
            live_camera_service.capture_thread = threading.Thread(
                target=live_camera_service._capture_loop,
                daemon=False,
            )
            live_camera_service.capture_thread.start()

            # Let it run and handle failures
            time.sleep(0.5)

            # Stop
            live_camera_service.exit_event.set()
            live_camera_service.capture_thread.join(timeout=2.0)

            # Should exit gracefully despite failures
            assert not live_camera_service.capture_thread.is_alive()

    def test_detection_failure_during_processing(self, live_camera_service):
        """Test detection failure during processing loop."""
        live_camera_service.exit_event.clear()

        # Setup detector to fail
        live_camera_service.detector_service.detector.detect.side_effect = Exception(
            "Detection failed"
        )

        # Add frames to queue
        for i in range(3):
            live_camera_service.frame_queue.put((i, np.zeros((480, 640, 3))))

        # Start processing thread
        live_camera_service.processing_thread = threading.Thread(
            target=live_camera_service._processing_loop,
            daemon=False,
        )
        live_camera_service.processing_thread.start()

        # Let it process
        time.sleep(0.3)

        # Stop
        live_camera_service.exit_event.set()
        live_camera_service.processing_thread.join(timeout=2.0)

        # Should handle exception and exit gracefully
        assert not live_camera_service.processing_thread.is_alive()

    def test_preview_update_exception_handling(self, live_camera_service):
        """Test preview window update exception handling."""
        live_camera_service.exit_event.clear()
        live_camera_service.preview_window = Mock()
        live_camera_service.preview_window.update_frame.side_effect = Exception("Update failed")

        # Add frames to queue
        for i in range(3):
            live_camera_service.frame_queue.put((i, np.zeros((480, 640, 3))))

        # Start processing thread
        live_camera_service.processing_thread = threading.Thread(
            target=live_camera_service._processing_loop,
            daemon=False,
        )
        live_camera_service.processing_thread.start()

        # Let it process
        time.sleep(0.3)

        # Stop
        live_camera_service.exit_event.set()
        live_camera_service.processing_thread.join(timeout=2.0)

        # Should handle exception and continue
        assert not live_camera_service.processing_thread.is_alive()

    def test_thread_crash_recovery(self, live_camera_service, mock_camera):
        """Test system state after thread crash."""
        with patch("zebtrack.io.camera.Camera", return_value=mock_camera):
            live_camera_service.camera = mock_camera
            live_camera_service.exit_event.clear()

            # Start threads
            live_camera_service._start_threads()

            # Simulate crash by forcing exit event
            live_camera_service.exit_event.set()

            # Wait for threads to finish
            if live_camera_service.capture_thread:
                live_camera_service.capture_thread.join(timeout=2.0)
            if live_camera_service.processing_thread:
                live_camera_service.processing_thread.join(timeout=2.0)

            # Should be able to restart after crash
            live_camera_service.exit_event.clear()
            assert live_camera_service._start_threads() is True

            # Cleanup
            live_camera_service.exit_event.set()
            if live_camera_service.capture_thread:
                live_camera_service.capture_thread.join(timeout=2.0)
            if live_camera_service.processing_thread:
                live_camera_service.processing_thread.join(timeout=2.0)


class TestLiveCameraServiceMemoryPressure:
    """Test memory pressure scenarios."""

    def test_frame_queue_limit_enforcement(self, live_camera_service, mock_camera):
        """Test that frame queue limit is enforced."""
        with patch("zebtrack.io.camera.Camera", return_value=mock_camera):
            live_camera_service.camera = mock_camera
            live_camera_service.exit_event.clear()

            # Start capture thread
            live_camera_service.capture_thread = threading.Thread(
                target=live_camera_service._capture_loop,
                daemon=False,
            )
            live_camera_service.capture_thread.start()

            # Let it run and fill queue
            time.sleep(0.3)

            # Stop
            live_camera_service.exit_event.set()
            live_camera_service.capture_thread.join(timeout=2.0)

            # Queue should not exceed maxsize
            assert live_camera_service.frame_queue.qsize() <= 30

    def test_frame_drop_scenarios(self, live_camera_service, mock_camera):
        """Test frame drop when queue is full."""
        with patch("zebtrack.io.camera.Camera", return_value=mock_camera):
            live_camera_service.camera = mock_camera
            live_camera_service.exit_event.clear()

            # Fill the queue
            for i in range(30):
                live_camera_service.frame_queue.put((i, np.zeros((480, 640, 3))))

            # Start capture (should drop frames since queue is full)
            live_camera_service.capture_thread = threading.Thread(
                target=live_camera_service._capture_loop,
                daemon=False,
            )
            live_camera_service.capture_thread.start()

            # Let it attempt to add more frames
            time.sleep(0.2)

            # Stop
            live_camera_service.exit_event.set()
            live_camera_service.capture_thread.join(timeout=2.0)

            # Queue should remain at capacity (frames were dropped)
            assert live_camera_service.frame_queue.qsize() <= 30

    def test_memory_leak_detection_repeated_sessions(self, live_camera_service, mock_camera):
        """Test for memory leaks in repeated sessions."""
        with patch("zebtrack.io.camera.Camera", return_value=mock_camera):
            initial_queue_size = live_camera_service.frame_queue.qsize()

            for i in range(3):
                # Setup
                live_camera_service.camera = mock_camera
                live_camera_service.exit_event.clear()

                # Add some frames
                for j in range(5):
                    live_camera_service.frame_queue.put((j, np.zeros((480, 640, 3))))

                # Cleanup
                live_camera_service._clear_queues()

            # Queue should be empty after cleanup
            assert live_camera_service.frame_queue.qsize() == initial_queue_size


class TestLiveCameraServiceRecordingIntegration:
    """Test integration with RecordingService."""

    def test_timed_session_expiration(self, live_camera_service, mock_camera):
        """Test timed session expiration handling."""
        with (
            patch("zebtrack.io.camera.Camera", return_value=mock_camera),
            patch("zebtrack.ui.dialogs.LivePreviewWindow"),
            patch("zebtrack.core.live_camera_service.Path.mkdir"),
        ):
            # Mock completion callback
            completion_called = [False]

            def on_complete_callback():
                completion_called[0] = True

            # Simulate recording service calling completion
            def mock_start_session(*args, **kwargs):
                # Immediately call completion to simulate timer expiration
                if hasattr(live_camera_service.recording_service, "_ui_callbacks"):
                    callbacks = live_camera_service.recording_service._ui_callbacks
                    if callbacks and "stop_recording_callback" in callbacks:
                        callbacks["stop_recording_callback"]()
                return True

            live_camera_service.recording_service.start_session = mock_start_session

            # Start session (should trigger completion immediately in this mock)
            live_camera_service.start_session(
                camera_index=0,
                duration_s=1.0,
                experiment_id="test_exp",
                record_video=True,
            )

            # Give time for callback
            time.sleep(0.2)

            # Cleanup
            if live_camera_service.capture_thread and live_camera_service.capture_thread.is_alive():
                live_camera_service.exit_event.set()
                live_camera_service.capture_thread.join(timeout=2.0)
            if (
                live_camera_service.processing_thread
                and live_camera_service.processing_thread.is_alive()
            ):
                live_camera_service.processing_thread.join(timeout=2.0)

    def test_manual_stop_during_recording(self, live_camera_service, mock_camera):
        """Test manual stop during active recording."""
        with (
            patch("zebtrack.io.camera.Camera", return_value=mock_camera),
            patch("zebtrack.ui.dialogs.LivePreviewWindow"),
        ):
            live_camera_service.camera = mock_camera

            # Start threads
            live_camera_service._start_threads()

            # Let run briefly
            time.sleep(0.1)

            # Manual stop
            live_camera_service.stop_session()

            # Verify recorder was stopped (not recording_service)
            live_camera_service.controller.recorder.stop_recording.assert_called()

    def test_callback_registration_and_execution(self, live_camera_service, mock_camera):
        """Test that live camera service starts and manages recorder directly."""
        with (
            patch("zebtrack.io.camera.Camera", return_value=mock_camera),
            patch("zebtrack.ui.dialogs.LivePreviewWindow"),
            patch("zebtrack.core.live_camera_service.Path.mkdir"),
        ):
            # Start session
            live_camera_service.start_session(
                camera_index=0,
                duration_s=1.0,
                experiment_id="test_exp",
                record_video=True,
            )

            # Verify recorder was used (called start_recording)
            assert live_camera_service.controller.recorder.start_recording.called

            # Cleanup
            live_camera_service.stop_session()

    def test_output_directory_creation(self, live_camera_service, mock_camera):
        """Test that output directory is created correctly."""
        with (
            patch("zebtrack.io.camera.Camera", return_value=mock_camera),
            patch("zebtrack.ui.dialogs.LivePreviewWindow"),
        ):
            mock_mkdir = Mock()

            with patch("zebtrack.core.live_camera_service.Path.mkdir", mock_mkdir):
                # Start session
                live_camera_service.start_session(
                    camera_index=0,
                    duration_s=1.0,
                    experiment_id="test_exp",
                    record_video=True,
                )

                # Verify directories were created
                assert mock_mkdir.call_count >= 2  # Base dir + session dir

                # Cleanup
                live_camera_service.stop_session()
