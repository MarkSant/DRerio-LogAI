"""
Testes de Thread Safety para MainViewModel.

Testa cenários de concorrência, race conditions, e thread lifecycle
para operações de detecção, gravação e processamento.
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from tests.helpers.controller_factory import create_test_controller
from tests.utils.wait_helpers import wait_for_thread_exit


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = SimpleNamespace()
    settings.video_processing = SimpleNamespace(
        fps=30.0,
        analysis_interval_frames=10,
        display_interval_frames=10,
    )
    settings.camera = SimpleNamespace(index=0, desired_width=640, desired_height=480)
    settings.performance = SimpleNamespace(max_parallel_videos=2, parquet_compression="snappy")
    settings.recorder = SimpleNamespace(flush_interval_seconds=5.0, flush_row_threshold=500)
    settings.detector = SimpleNamespace(
        default_backend="opencv",
        track_threshold=0.25,
        match_threshold=0.15,
    )
    settings.weights = SimpleNamespace(seg_filename=None, det_filename=None)
    settings.yolo_model = SimpleNamespace(path=None)
    settings.ui_features = SimpleNamespace(enable_event_queue=False)
    return settings


@pytest.fixture
def mock_state_manager():
    """Create a mock StateManager."""
    state_manager = Mock()
    processing_state = SimpleNamespace(
        is_processing=False,
        processing_thread=None,
        pending_single_video_analysis=None,
    )
    recording_state = SimpleNamespace(is_recording=False, is_capturing_for_video=False)
    detector_state = SimpleNamespace(detector_initialized=False)

    def _update_state(target_state, **kwargs):
        for key, value in kwargs.items():
            setattr(target_state, key, value)

    state_manager.update_processing_state.side_effect = lambda **kwargs: _update_state(
        processing_state, **kwargs
    )
    state_manager.update_detector_state.side_effect = lambda **kwargs: _update_state(
        detector_state, **kwargs
    )
    state_manager.update_recording_state.side_effect = lambda **kwargs: _update_state(
        recording_state, **kwargs
    )
    state_manager.subscribe.return_value = None
    state_manager.subscribe_all.return_value = None
    state_manager.get_recording_state.return_value = recording_state
    state_manager.get_detector_state.return_value = detector_state
    state_manager.get_processing_state.return_value = processing_state
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
    """Create a mock UIScheduler."""
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
    monkeypatch,
):
    """Create a MainViewModel instance with mocked dependencies."""

    class DummyGUI:
        def __init__(self, *args, **kwargs):
            pass

        def update_gpu_hardware_display(self, *_args, **_kwargs):
            pass

        def update_openvino_status_display(self, *_args, **_kwargs):
            pass

    class DummyDetectorSetupCoordinator:
        def __init__(self, *args, **kwargs):
            pass

        def setup_detector_zones(self, *_args, **_kwargs):
            pass

        def shutdown(self):
            pass

    class DummyVideoOrchestrator:
        def __init__(self, *args, **kwargs):
            pass

        def set_view(self, *_args, **_kwargs):
            pass

        def set_arena_callback(self, *_args, **_kwargs):
            pass

        def set_analysis_view_mode_callback(self, *_args, **_kwargs):
            pass

        def set_refresh_callback(self, *_args, **_kwargs):
            pass

        def set_publish_processing_mode_callback(self, *_args, **_kwargs):
            pass

        def shutdown(self):
            pass

    class DummyAnalysisCoordinator:
        def __init__(self, *args, **kwargs):
            pass

        def set_view(self, *_args, **_kwargs):
            pass

        def set_refresh_callback(self, *_args, **_kwargs):
            pass

        def shutdown(self):
            pass

    project_workflow_service = Mock()
    project_workflow_service.set_global_model_defaults.return_value = None

    weight_manager = Mock()
    weight_manager.get_default_weight.return_value = (None, None)
    weight_manager.get_weight_details.return_value = {}
    weight_manager._classify_weight_type.return_value = None

    model_service = Mock()
    model_service.get_all_weight_names.return_value = []

    video_processing_service = Mock()
    video_processing_service.cancel_event = threading.Event()

    analysis_service = Mock()
    recording_service = Mock()

    view_model = create_test_controller(
        root=Mock(),
        event_bus=None,
        state_manager=mock_state_manager,
        ui_coordinator=mock_ui_coordinator,
        settings_obj=mock_settings,
        project_manager=mock_project_manager,
        project_workflow_service=project_workflow_service,
        weight_manager=weight_manager,
        model_service=model_service,
        detector_service=mock_detector_service,
        video_processing_service=video_processing_service,
        analysis_service=analysis_service,
        recording_service=recording_service,
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
                time.sleep(0.05)  # intentional interleaving delay

        main_view_model.processing_thread = threading.Thread(target=processing_worker, daemon=False)
        main_view_model.processing_thread.start()

        # Verify thread is running
        assert main_view_model.processing_thread.is_alive()

        # Stop thread
        main_view_model.cancel_event.set()
        wait_for_thread_exit(main_view_model.processing_thread, timeout=5.0)

        # Verify thread stopped
        assert not main_view_model.processing_thread.is_alive()

    def test_cancel_event_propagation(self, main_view_model):
        """Test that cancel event properly propagates to worker threads."""
        cancel_detected = [False]

        def worker():
            while not main_view_model.cancel_event.is_set():
                time.sleep(0.05)  # intentional interleaving delay
            cancel_detected[0] = True

        main_view_model.cancel_event.clear()
        main_view_model.processing_thread = threading.Thread(target=worker, daemon=False)
        main_view_model.processing_thread.start()

        # Give thread time to start
        time.sleep(0.1)  # intentional interleaving delay

        # Signal cancellation
        main_view_model.cancel_event.set()
        wait_for_thread_exit(main_view_model.processing_thread, timeout=5.0)

        # Verify cancel was detected
        assert cancel_detected[0] is True
        assert not main_view_model.processing_thread.is_alive()

    def test_multiple_processing_cycles(self, main_view_model):
        """Test multiple start/stop cycles of processing threads."""
        for i in range(3):
            main_view_model.cancel_event.clear()

            def worker():
                while not main_view_model.cancel_event.is_set():
                    time.sleep(0.05)  # intentional interleaving delay

            main_view_model.processing_thread = threading.Thread(target=worker, daemon=False)
            main_view_model.processing_thread.start()

            # Brief run
            time.sleep(0.1)  # intentional interleaving delay

            # Stop
            main_view_model.cancel_event.set()
            wait_for_thread_exit(main_view_model.processing_thread, timeout=5.0)

            assert not main_view_model.processing_thread.is_alive()

    def test_thread_join_timeout(self, main_view_model):
        """Test that thread join with timeout doesn't hang."""

        def long_running_worker():
            # Simulate stuck thread
            time.sleep(10.0)  # intentional interleaving delay

        main_view_model.processing_thread = threading.Thread(
            target=long_running_worker, daemon=True
        )
        main_view_model.processing_thread.start()

        # Join with short timeout
        start_time = time.time()
        wait_for_thread_exit(main_view_model.processing_thread, timeout=0.5)
        elapsed = time.time() - start_time

        # Should timeout quickly and never wait for full 10s.
        # On busy Windows CI runners, scheduling jitter can exceed 1s.
        assert elapsed < 2.0


class TestMainViewModelConcurrentOperations:
    """Test concurrent detector and recording operations."""

    def test_concurrent_detector_calls(self, main_view_model):
        """Test concurrent calls to detector from multiple threads."""
        detection_calls: list[tuple[int, int | str]] = []

        def detector_worker(worker_id):
            for i in range(3):
                try:
                    main_view_model.detector_service.detector.detect(
                        np.zeros((480, 640, 3)), f"worker_{worker_id}"
                    )
                    detection_calls.append((worker_id, i))
                    time.sleep(0.05)  # intentional interleaving delay
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
            wait_for_thread_exit(worker, timeout=3.0)

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
                time.sleep(0.01)  # intentional interleaving delay

        # Start multiple state updater threads
        updaters = []
        for i in range(3):
            updater = threading.Thread(target=state_updater, args=(i,), daemon=False)
            updater.start()
            updaters.append(updater)

        # Wait for completion
        for updater in updaters:
            wait_for_thread_exit(updater, timeout=5.0)

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
                time.sleep(0.01)  # intentional interleaving delay

        # Start multiple UI scheduler threads
        schedulers = []
        for i in range(3):
            scheduler = threading.Thread(target=ui_scheduler, args=(i,), daemon=False)
            scheduler.start()
            schedulers.append(scheduler)

        # Wait for completion
        for scheduler in schedulers:
            wait_for_thread_exit(scheduler, timeout=5.0)

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
            time.sleep(0.05)  # intentional interleaving delay

        # Start multiple cancel workers
        workers = []
        for i in range(3):
            worker = threading.Thread(target=cancel_worker, daemon=False)
            worker.start()
            workers.append(worker)

        # Wait for completion
        for worker in workers:
            wait_for_thread_exit(worker, timeout=5.0)

        # All should complete, event should be set
        for worker in workers:
            assert not worker.is_alive()
        assert main_view_model.cancel_event.is_set()

    def test_processing_thread_replacement(self, main_view_model):
        """Test that processing thread can be safely replaced."""
        main_view_model.cancel_event.clear()

        def worker1():
            while not main_view_model.cancel_event.is_set():
                time.sleep(0.05)  # intentional interleaving delay

        # Start first thread
        main_view_model.processing_thread = threading.Thread(target=worker1, daemon=False)
        main_view_model.processing_thread.start()
        thread1 = main_view_model.processing_thread

        # Let it run briefly
        time.sleep(0.1)  # intentional interleaving delay

        # Stop and replace
        main_view_model.cancel_event.set()
        wait_for_thread_exit(thread1, timeout=5.0)

        # Start new thread
        main_view_model.cancel_event.clear()

        def worker2():
            while not main_view_model.cancel_event.is_set():
                time.sleep(0.05)  # intentional interleaving delay

        main_view_model.processing_thread = threading.Thread(target=worker2, daemon=False)
        main_view_model.processing_thread.start()
        thread2 = main_view_model.processing_thread

        # Verify old thread stopped, new one running
        assert not thread1.is_alive()
        assert thread2.is_alive()

        # Cleanup
        main_view_model.cancel_event.set()
        wait_for_thread_exit(thread2, timeout=5.0)


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
                main_view_model.detector_service.detector.detect(np.zeros((480, 640, 3)), "test")
            except RuntimeError as e:
                exceptions_caught.append(str(e))

        thread = threading.Thread(target=worker_with_error_handling, daemon=False)
        thread.start()
        wait_for_thread_exit(thread, timeout=5.0)

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
        wait_for_thread_exit(thread, timeout=5.0)

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
                time.sleep(0.05)  # intentional interleaving delay

        main_view_model.processing_thread = threading.Thread(target=worker, daemon=True)
        main_view_model.processing_thread.start()

        # Both should be active
        assert main_view_model.processing_thread.is_alive()

        # Cancel both
        main_view_model.cancel_event.set()
        wait_for_thread_exit(main_view_model.processing_thread, timeout=5.0)

        # Thread should stop
        assert not main_view_model.processing_thread.is_alive()
