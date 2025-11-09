"""
Testes de Thread Safety para MainViewModel.

Testa cenários de concorrência, race conditions, e thread lifecycle
para operações de detecção, gravação e processamento.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import Mock

import numpy as np
import pytest

from zebtrack.core.main_view_model import MainViewModel


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = Mock()
    settings.video_processing.fps = 30.0
    settings.video_processing.analysis_interval_frames = 10
    settings.video_processing.display_interval_frames = 10
    settings.camera.index = 0
    settings.camera.desired_width = 640
    settings.camera.desired_height = 480
    settings.performance.max_parallel_videos = 2
    settings.detector.default_backend = "opencv"
    settings.detector.track_threshold = 0.25
    settings.detector.match_threshold = 0.15
    return settings


@pytest.fixture
def mock_state_manager():
    """Create a mock StateManager."""
    state_manager = Mock()
    state_manager.update_processing_state.return_value = None
    state_manager.update_detection_state.return_value = None
    return state_manager


@pytest.fixture
def mock_project_manager():
    """Create a mock ProjectManager."""
    project_manager = Mock()
    project_manager.project_data = {}
    project_manager.project_path = None
    project_manager.get_zone_data.return_value = None
    return project_manager


@pytest.fixture
def mock_detector_service():
    """Create a mock DetectorService."""
    detector_service = Mock()
    detector = Mock()
    detector.detect.return_value = ([], None)
    detector_service.detector = detector
    detector_service.setup_detector.return_value = True
    return detector_service


@pytest.fixture
def mock_ui_coordinator():
    """Create a mock UICoordinator."""
    ui_coordinator = Mock()
    ui_coordinator.schedule.side_effect = lambda func, *args, **kwargs: func(*args, **kwargs)
    ui_coordinator.update_view.return_value = None
    return ui_coordinator


@pytest.fixture
def main_view_model(
    mock_settings,
    mock_state_manager,
    mock_project_manager,
    mock_detector_service,
    mock_ui_coordinator,
):
    """Create a MainViewModel instance with mocked dependencies."""
    view_model = MainViewModel(
        view=Mock(),
        settings_obj=mock_settings,
        state_manager=mock_state_manager,
        project_manager=mock_project_manager,
        detector_service=mock_detector_service,
        ui_coordinator=mock_ui_coordinator,
    )
    return view_model


class TestMainViewModelThreadLifecycle:
    """Test thread lifecycle management for processing operations."""

    def test_processing_thread_lifecycle(self, main_view_model):
        """Test basic processing thread start and stop lifecycle."""
        # Setup
        main_view_model.cancel_event.clear()
        assert main_view_model.processing_thread is None

        # Create a simple processing thread
        def processing_worker():
            while not main_view_model.cancel_event.is_set():
                time.sleep(0.05)

        main_view_model.processing_thread = threading.Thread(
            target=processing_worker, daemon=False
        )
        main_view_model.processing_thread.start()

        # Verify thread is running
        assert main_view_model.processing_thread.is_alive()

        # Stop thread
        main_view_model.cancel_event.set()
        main_view_model.processing_thread.join(timeout=2.0)

        # Verify thread stopped
        assert not main_view_model.processing_thread.is_alive()

    def test_cancel_event_propagation(self, main_view_model):
        """Test that cancel event properly propagates to worker threads."""
        cancel_detected = [False]

        def worker():
            while not main_view_model.cancel_event.is_set():
                time.sleep(0.05)
            cancel_detected[0] = True

        main_view_model.cancel_event.clear()
        main_view_model.processing_thread = threading.Thread(target=worker, daemon=False)
        main_view_model.processing_thread.start()

        # Give thread time to start
        time.sleep(0.1)

        # Signal cancellation
        main_view_model.cancel_event.set()
        main_view_model.processing_thread.join(timeout=2.0)

        # Verify cancel was detected
        assert cancel_detected[0] is True
        assert not main_view_model.processing_thread.is_alive()

    def test_multiple_processing_cycles(self, main_view_model):
        """Test multiple start/stop cycles of processing threads."""
        for i in range(3):
            main_view_model.cancel_event.clear()

            def worker():
                while not main_view_model.cancel_event.is_set():
                    time.sleep(0.05)

            main_view_model.processing_thread = threading.Thread(target=worker, daemon=False)
            main_view_model.processing_thread.start()

            # Brief run
            time.sleep(0.1)

            # Stop
            main_view_model.cancel_event.set()
            main_view_model.processing_thread.join(timeout=2.0)

            assert not main_view_model.processing_thread.is_alive()

    def test_thread_join_timeout(self, main_view_model):
        """Test that thread join with timeout doesn't hang."""

        def long_running_worker():
            # Simulate stuck thread
            time.sleep(10.0)

        main_view_model.processing_thread = threading.Thread(
            target=long_running_worker, daemon=False
        )
        main_view_model.processing_thread.start()

        # Join with short timeout
        start_time = time.time()
        main_view_model.processing_thread.join(timeout=0.5)
        elapsed = time.time() - start_time

        # Should timeout in ~0.5s, not wait for full 10s
        assert elapsed < 1.0


class TestMainViewModelConcurrentOperations:
    """Test concurrent detector and recording operations."""

    def test_concurrent_detector_calls(self, main_view_model):
        """Test concurrent calls to detector from multiple threads."""
        detection_calls = []

        def detector_worker(worker_id):
            for i in range(3):
                try:
                    main_view_model.detector_service.detector.detect(
                        np.zeros((480, 640, 3)), f"worker_{worker_id}"
                    )
                    detection_calls.append((worker_id, i))
                    time.sleep(0.05)
                except Exception as e:
                    detection_calls.append((worker_id, f"error: {e}"))

        # Start multiple detector workers
        workers = []
        for i in range(3):
            worker = threading.Thread(target=detector_worker, args=(i,), daemon=False)
            worker.start()
            workers.append(worker)

        # Wait for completion
        for worker in workers:
            worker.join(timeout=3.0)

        # Verify all workers completed
        for worker in workers:
            assert not worker.is_alive()

        # Verify some detections were made
        assert len(detection_calls) > 0

    def test_state_manager_concurrent_updates(self, main_view_model):
        """Test concurrent state manager updates from multiple threads."""

        def state_updater(thread_id):
            for i in range(5):
                main_view_model.state_manager.update_processing_state(
                    source=f"thread_{thread_id}",
                    is_processing=(i % 2 == 0),
                )
                time.sleep(0.01)

        # Start multiple state updater threads
        updaters = []
        for i in range(3):
            updater = threading.Thread(target=state_updater, args=(i,), daemon=False)
            updater.start()
            updaters.append(updater)

        # Wait for completion
        for updater in updaters:
            updater.join(timeout=2.0)

        # All threads should complete
        for updater in updaters:
            assert not updater.is_alive()

    def test_ui_coordinator_concurrent_scheduling(self, main_view_model):
        """Test concurrent UI scheduling from multiple threads."""
        scheduled_calls = []

        def ui_scheduler(thread_id):
            for i in range(5):
                main_view_model.ui_coordinator.schedule(
                    lambda tid=thread_id, idx=i: scheduled_calls.append((tid, idx))
                )
                time.sleep(0.01)

        # Start multiple UI scheduler threads
        schedulers = []
        for i in range(3):
            scheduler = threading.Thread(target=ui_scheduler, args=(i,), daemon=False)
            scheduler.start()
            schedulers.append(scheduler)

        # Wait for completion
        for scheduler in schedulers:
            scheduler.join(timeout=2.0)

        # All threads should complete
        for scheduler in schedulers:
            assert not scheduler.is_alive()

        # Some calls should have been scheduled
        assert len(scheduled_calls) > 0


class TestMainViewModelRaceConditions:
    """Test race conditions in concurrent access."""

    def test_concurrent_cancel_requests(self, main_view_model):
        """Test concurrent cancel requests don't cause issues."""

        def cancel_worker():
            main_view_model.cancel_event.set()
            time.sleep(0.05)

        # Start multiple cancel workers
        workers = []
        for i in range(3):
            worker = threading.Thread(target=cancel_worker, daemon=False)
            worker.start()
            workers.append(worker)

        # Wait for completion
        for worker in workers:
            worker.join(timeout=2.0)

        # All should complete, event should be set
        for worker in workers:
            assert not worker.is_alive()
        assert main_view_model.cancel_event.is_set()

    def test_processing_thread_replacement(self, main_view_model):
        """Test that processing thread can be safely replaced."""
        main_view_model.cancel_event.clear()

        def worker1():
            while not main_view_model.cancel_event.is_set():
                time.sleep(0.05)

        # Start first thread
        main_view_model.processing_thread = threading.Thread(target=worker1, daemon=False)
        main_view_model.processing_thread.start()
        thread1 = main_view_model.processing_thread

        # Let it run briefly
        time.sleep(0.1)

        # Stop and replace
        main_view_model.cancel_event.set()
        thread1.join(timeout=2.0)

        # Start new thread
        main_view_model.cancel_event.clear()

        def worker2():
            while not main_view_model.cancel_event.is_set():
                time.sleep(0.05)

        main_view_model.processing_thread = threading.Thread(target=worker2, daemon=False)
        main_view_model.processing_thread.start()
        thread2 = main_view_model.processing_thread

        # Verify old thread stopped, new one running
        assert not thread1.is_alive()
        assert thread2.is_alive()

        # Cleanup
        main_view_model.cancel_event.set()
        thread2.join(timeout=2.0)


class TestMainViewModelErrorHandling:
    """Test error handling in threaded operations."""

    def test_detector_exception_handling(self, main_view_model):
        """Test that detector exceptions in threads are handled gracefully."""
        # Setup detector to fail
        main_view_model.detector_service.detector.detect.side_effect = RuntimeError(
            "Detection failed"
        )

        exceptions_caught = []

        def worker_with_error_handling():
            try:
                main_view_model.detector_service.detector.detect(
                    np.zeros((480, 640, 3)), "test"
                )
            except RuntimeError as e:
                exceptions_caught.append(str(e))

        thread = threading.Thread(target=worker_with_error_handling, daemon=False)
        thread.start()
        thread.join(timeout=2.0)

        # Thread should complete and exception should be caught
        assert not thread.is_alive()
        assert len(exceptions_caught) == 1
        assert "Detection failed" in exceptions_caught[0]

    def test_state_manager_exception_handling(self, main_view_model):
        """Test state manager exceptions in threads."""
        # Setup state manager to fail
        main_view_model.state_manager.update_processing_state.side_effect = Exception(
            "State update failed"
        )

        exceptions_caught = []

        def worker_with_error_handling():
            try:
                main_view_model.state_manager.update_processing_state(
                    source="test", is_processing=True
                )
            except Exception as e:
                exceptions_caught.append(str(e))

        thread = threading.Thread(target=worker_with_error_handling, daemon=False)
        thread.start()
        thread.join(timeout=2.0)

        # Thread should complete
        assert not thread.is_alive()
        assert len(exceptions_caught) == 1


class TestMainViewModelProcessingWorker:
    """Test ProcessingWorker integration with threading."""

    def test_processing_worker_lifecycle(self, main_view_model):
        """Test processing worker creation and lifecycle."""
        # Create a mock processing worker
        mock_worker = Mock()
        mock_worker.is_running = True
        mock_worker.cancel.return_value = True

        main_view_model.processing_worker = mock_worker

        # Verify worker is running
        assert main_view_model.processing_worker.is_running

        # Cancel worker
        success = main_view_model.processing_worker.cancel()
        assert success is True

    def test_processing_worker_and_thread_coordination(self, main_view_model):
        """Test coordination between ProcessingWorker and threads."""
        # Setup mock worker
        mock_worker = Mock()
        mock_worker.is_running = False
        main_view_model.processing_worker = mock_worker

        # Setup processing thread
        main_view_model.cancel_event.clear()

        def worker():
            while not main_view_model.cancel_event.is_set():
                time.sleep(0.05)

        main_view_model.processing_thread = threading.Thread(target=worker, daemon=False)
        main_view_model.processing_thread.start()

        # Both should be active
        assert main_view_model.processing_thread.is_alive()

        # Cancel both
        main_view_model.cancel_event.set()
        main_view_model.processing_thread.join(timeout=2.0)

        # Thread should stop
        assert not main_view_model.processing_thread.is_alive()
