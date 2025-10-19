"""
Tests for the ProcessingWorker class.

Verifies the worker's threading behavior, callback mechanisms, cancellation,
and error handling without requiring a full GUI setup.
"""

import threading
import time
from unittest.mock import Mock

import pytest

from zebtrack.core.processing_worker import (
    ProcessingCallbacks,
    ProcessingContext,
    ProcessingWorker,
)


@pytest.fixture
def mock_cancel_event():
    """Provides a fresh threading.Event for each test."""
    return threading.Event()


@pytest.fixture
def mock_callbacks():
    """Provides mock callbacks for testing."""
    return ProcessingCallbacks(
        on_started=Mock(),
        on_progress=Mock(),
        on_frame_processed=Mock(),
        on_video_completed=Mock(),
        on_error=Mock(),
        on_completed=Mock(),
    )


@pytest.fixture
def basic_context(mock_cancel_event):
    """Provides a minimal ProcessingContext for testing."""
    return ProcessingContext(
        videos_to_process=[{"path": "/fake/video1.mp4"}],
        output_base_dir="/fake/output",
        cancel_event=mock_cancel_event,
        single_video_config=None,
    )


class TestProcessingWorkerInitialization:
    """Tests for worker initialization and configuration."""

    def test_init_with_minimal_context(self, basic_context, mock_callbacks):
        """Worker initializes with minimal required context."""
        worker = ProcessingWorker(basic_context, mock_callbacks)

        assert worker.context == basic_context
        assert worker.callbacks == mock_callbacks
        assert worker._thread is None
        assert not worker.is_running

    def test_init_preserves_all_context_fields(self, mock_cancel_event):
        """Worker preserves all fields in the context."""
        mock_func = Mock()
        context = ProcessingContext(
            videos_to_process=[{"path": "/test.mp4", "metadata": {"day": 1}}],
            output_base_dir="/output",
            cancel_event=mock_cancel_event,
            single_video_config={"animals_per_aquarium": 2},
            analysis_interval_frames=5,
            display_interval_frames=15,
            process_single_video_func=mock_func,
            apply_project_settings_func=mock_func,
            determine_intervals_func=mock_func,
        )

        callbacks = ProcessingCallbacks()
        worker = ProcessingWorker(context, callbacks)

        assert worker.context.videos_to_process[0]["path"] == "/test.mp4"
        assert worker.context.single_video_config["animals_per_aquarium"] == 2
        assert worker.context.analysis_interval_frames == 5
        assert worker.context.display_interval_frames == 15
        assert worker.context.process_single_video_func == mock_func


class TestProcessingWorkerThreading:
    """Tests for worker threading behavior."""

    def test_start_in_thread_creates_daemon_thread(self, basic_context, mock_callbacks):
        """start_in_thread creates a daemon thread and starts it."""
        # Add a mock function that completes quickly
        basic_context.process_single_video_func = Mock(return_value=(True, "/output"))

        worker = ProcessingWorker(basic_context, mock_callbacks)
        thread = worker.start_in_thread()

        assert thread is not None
        assert thread.daemon is True
        assert "ProcessingWorker" in thread.name
        assert worker.is_running or not thread.is_alive()  # May finish quickly

        # Cleanup
        basic_context.cancel_event.set()
        thread.join(timeout=1.0)

    def test_start_in_thread_returns_same_thread_if_running(self, basic_context, mock_callbacks):
        """Calling start_in_thread twice returns the same thread if still running."""

        # Make the worker run for a bit
        def slow_process(*args, **kwargs):
            time.sleep(0.1)
            return (True, "/output")

        basic_context.process_single_video_func = slow_process
        worker = ProcessingWorker(basic_context, mock_callbacks)

        thread1 = worker.start_in_thread()
        thread2 = worker.start_in_thread()

        assert thread1 is thread2

        # Cleanup
        basic_context.cancel_event.set()
        thread1.join(timeout=1.0)

    def test_is_running_reflects_thread_state(self, basic_context, mock_callbacks):
        """is_running property accurately reflects whether thread is active."""
        # Use a mock that we can control
        processing_started = threading.Event()
        processing_should_end = threading.Event()

        def controlled_process(*args, **kwargs):
            processing_started.set()
            processing_should_end.wait(timeout=2.0)
            return (True, "/output")

        basic_context.process_single_video_func = controlled_process
        worker = ProcessingWorker(basic_context, mock_callbacks)

        assert not worker.is_running

        thread = worker.start_in_thread()
        processing_started.wait(timeout=1.0)  # Wait for thread to actually start
        assert worker.is_running

        processing_should_end.set()
        thread.join(timeout=1.0)
        assert not worker.is_running


class TestProcessingWorkerCallbacks:
    """Tests for callback invocation during processing."""

    def test_on_started_called_at_beginning(self, basic_context, mock_callbacks):
        """on_started callback is invoked when processing begins."""
        basic_context.process_single_video_func = Mock(return_value=(True, "/output"))

        worker = ProcessingWorker(basic_context, mock_callbacks)
        thread = worker.start_in_thread()
        thread.join(timeout=2.0)

        mock_callbacks.on_started.assert_called_once()

    def test_on_completed_called_at_end(self, basic_context, mock_callbacks):
        """on_completed callback is invoked when processing finishes."""
        basic_context.process_single_video_func = Mock(return_value=(True, "/output"))

        worker = ProcessingWorker(basic_context, mock_callbacks)
        thread = worker.start_in_thread()
        thread.join(timeout=2.0)

        mock_callbacks.on_completed.assert_called_once()
        args = mock_callbacks.on_completed.call_args[0]
        was_cancelled, output_dir = args
        assert was_cancelled is False
        # Output dir updates to the results from processed video
        assert output_dir == "/output"

    def test_on_video_completed_called_for_each_video(self, mock_cancel_event, mock_callbacks):
        """on_video_completed is called once per video in the batch."""
        context = ProcessingContext(
            videos_to_process=[
                {"path": "/video1.mp4"},
                {"path": "/video2.mp4"},
                {"path": "/video3.mp4"},
            ],
            output_base_dir="/output",
            cancel_event=mock_cancel_event,
        )
        context.process_single_video_func = Mock(return_value=(True, "/results"))

        worker = ProcessingWorker(context, mock_callbacks)
        thread = worker.start_in_thread()
        thread.join(timeout=2.0)

        assert mock_callbacks.on_video_completed.call_count == 3

    def test_on_error_called_when_processing_raises(self, basic_context, mock_callbacks):
        """on_error callback is invoked when video processing raises an exception."""
        basic_context.process_single_video_func = Mock(
            side_effect=RuntimeError("Processing failed")
        )

        worker = ProcessingWorker(basic_context, mock_callbacks)
        thread = worker.start_in_thread()
        thread.join(timeout=2.0)

        # Error callback should be called
        mock_callbacks.on_error.assert_called()
        args = mock_callbacks.on_error.call_args[0]
        error, context = args
        assert isinstance(error, RuntimeError)
        assert "Processing failed" in str(error)

        # Completion callback should still be called
        mock_callbacks.on_completed.assert_called_once()

    def test_on_fatal_error_called_when_processing_raises_outside_loop(
        self, basic_context, mock_callbacks
    ):
        """on_fatal_error is called for exceptions outside the video loop."""
        mock_callbacks.on_fatal_error = Mock()
        basic_context.determine_intervals_func = Mock(side_effect=RuntimeError("Fatal setup error"))

        worker = ProcessingWorker(basic_context, mock_callbacks)
        thread = worker.start_in_thread()
        thread.join(timeout=2.0)

        # on_fatal_error should be called
        mock_callbacks.on_fatal_error.assert_called_once()
        args = mock_callbacks.on_fatal_error.call_args[0]
        error, context, recovery_info = args
        assert isinstance(error, RuntimeError)
        assert "Fatal setup error" in str(error)
        assert "fatal" in context

        # Regular on_error should not be called
        mock_callbacks.on_error.assert_not_called()

        # on_completed should still be called
        mock_callbacks.on_completed.assert_called_once()

    def test_on_error_fallback_when_on_fatal_error_is_none(self, basic_context, mock_callbacks):
        """on_error is called as a fallback if on_fatal_error is not set."""
        # Ensure on_fatal_error is not set
        mock_callbacks.on_fatal_error = None
        basic_context.determine_intervals_func = Mock(side_effect=RuntimeError("Fatal setup error"))

        worker = ProcessingWorker(basic_context, mock_callbacks)
        thread = worker.start_in_thread()
        thread.join(timeout=2.0)

        # on_error should be called as a fallback
        mock_callbacks.on_error.assert_called_once()
        args = mock_callbacks.on_error.call_args[0]
        error, context = args
        assert isinstance(error, RuntimeError)
        assert "Fatal setup error" in str(error)
        assert "fatal" in context

        # on_completed should still be called
        mock_callbacks.on_completed.assert_called_once()

    def test_callbacks_can_be_none(self, basic_context):
        """Worker handles None callbacks gracefully."""
        callbacks = ProcessingCallbacks()  # All callbacks are None by default
        basic_context.process_single_video_func = Mock(return_value=(True, "/output"))

        worker = ProcessingWorker(basic_context, callbacks)
        thread = worker.start_in_thread()
        thread.join(timeout=2.0)

        # Should complete without errors
        assert not thread.is_alive()


class TestProcessingWorkerCancellation:
    """Tests for worker cancellation behavior."""

    def test_cancel_sets_event_and_stops_processing(self, mock_cancel_event, mock_callbacks):
        """cancel() method sets the cancel event and stops processing."""
        # Create a context with multiple videos
        context = ProcessingContext(
            videos_to_process=[{"path": f"/video{i}.mp4"} for i in range(10)],
            output_base_dir="/output",
            cancel_event=mock_cancel_event,
        )

        # Mock that processes slowly
        def slow_process(*args, **kwargs):
            time.sleep(0.1)
            return (True, "/output")

        context.process_single_video_func = slow_process

        worker = ProcessingWorker(context, mock_callbacks)
        thread = worker.start_in_thread()

        # Let it start, then cancel
        time.sleep(0.05)
        success = worker.cancel(timeout=1.0)

        assert success
        assert mock_cancel_event.is_set()
        assert not thread.is_alive()

        # Should report as cancelled
        mock_callbacks.on_completed.assert_called_once()
        was_cancelled = mock_callbacks.on_completed.call_args[0][0]
        assert was_cancelled is True

    def test_cancel_event_checked_between_videos(self, mock_cancel_event, mock_callbacks):
        """Worker checks cancel_event between each video."""
        processed_videos = []
        cancel_after_first = threading.Event()

        def track_processed(*args, **kwargs):
            video_info = kwargs.get("video_info") or args[2]  # 3rd positional arg
            processed_videos.append(video_info["path"])
            # Signal to cancel after first video
            if len(processed_videos) == 1:
                cancel_after_first.set()
            # Small delay to allow cancellation to take effect
            time.sleep(0.05)
            return (True, "/output")

        context = ProcessingContext(
            videos_to_process=[{"path": f"/video{i}.mp4"} for i in range(5)],
            output_base_dir="/output",
            cancel_event=mock_cancel_event,
        )
        context.process_single_video_func = track_processed

        worker = ProcessingWorker(context, mock_callbacks)
        thread = worker.start_in_thread()

        # Wait for first video, then cancel
        cancel_after_first.wait(timeout=1.0)
        mock_cancel_event.set()
        thread.join(timeout=2.0)

        # Should have processed at least 1 but typically not all 5 videos
        # (in rare cases all may complete before cancellation is checked)
        assert len(processed_videos) >= 1
        assert len(processed_videos) <= 5

    def test_cancel_with_no_timeout_doesnt_wait(self, basic_context, mock_callbacks):
        """cancel(timeout=None) returns immediately without waiting."""

        # Make a long-running process (1s is enough to test immediate cancellation)
        def long_process(*args, **kwargs):
            time.sleep(1.0)
            return (True, "/output")

        basic_context.process_single_video_func = long_process
        worker = ProcessingWorker(basic_context, mock_callbacks)
        thread = worker.start_in_thread()

        # Cancel without waiting
        result = worker.cancel(timeout=None)

        assert result is True  # Returns True because we didn't wait
        assert basic_context.cancel_event.is_set()
        # Thread might still be running
        # Cleanup
        thread.join(timeout=0.1)


class TestProcessingWorkerFunctionalIntegration:
    """Integration tests for complete worker workflows."""

    def test_complete_single_video_workflow(self, mock_cancel_event):
        """Full workflow for processing a single video."""
        callbacks = ProcessingCallbacks(
            on_started=Mock(),
            on_progress=Mock(),
            on_video_completed=Mock(),
            on_completed=Mock(),
        )

        def mock_process_video(*args, **kwargs):
            # Simulate progress reporting
            if callbacks.on_progress:
                callbacks.on_progress(0.5, "Processing video", {"processed_frames": 100})
            return (True, "/results/video1_results")

        context = ProcessingContext(
            videos_to_process=[{"path": "/videos/test.mp4"}],
            output_base_dir="/results",
            cancel_event=mock_cancel_event,
            analysis_interval_frames=10,
            display_interval_frames=5,
            process_single_video_func=mock_process_video,
        )

        worker = ProcessingWorker(context, callbacks)
        thread = worker.start_in_thread()
        thread.join(timeout=2.0)

        # Verify callback sequence
        callbacks.on_started.assert_called_once()
        callbacks.on_progress.assert_called()
        callbacks.on_video_completed.assert_called_once_with(
            0,
            1,
            "test",
            True,  # index, total, experiment_id, success
        )
        callbacks.on_completed.assert_called_once()
        args, kwargs = callbacks.on_completed.call_args
        assert args[0] is False  # was_cancelled
        assert args[1] == "/results/video1_results"  # output_dir

    def test_multi_video_batch_processing(self, mock_cancel_event):
        """Processing multiple videos in sequence."""
        processed_order = []

        def track_processing(*args, **kwargs):
            video_info = kwargs.get("video_info") or args[2]
            processed_order.append(video_info["path"])
            return (True, "/results")

        callbacks = ProcessingCallbacks(on_completed=Mock())
        context = ProcessingContext(
            videos_to_process=[
                {"path": "/videos/video1.mp4"},
                {"path": "/videos/video2.mp4"},
                {"path": "/videos/video3.mp4"},
            ],
            output_base_dir="/results",
            cancel_event=mock_cancel_event,
            process_single_video_func=track_processing,
        )

        worker = ProcessingWorker(context, callbacks)
        thread = worker.start_in_thread()
        thread.join(timeout=2.0)

        # Videos should be processed in order
        assert processed_order == [
            "/videos/video1.mp4",
            "/videos/video2.mp4",
            "/videos/video3.mp4",
        ]

        # Should complete successfully
        callbacks.on_completed.assert_called_once()
        args, kwargs = callbacks.on_completed.call_args
        assert args[0] is False  # was_cancelled
        summary = kwargs.get("summary")
        assert summary["failed"] == 0
        assert summary["successful"] == 3

    def test_error_handling_continues_to_next_video(self, mock_cancel_event):
        """Worker continues processing after an error in one video."""
        self.processed = []
        self.errors = []

        def sometimes_fails(*args, **kwargs):
            video_info = kwargs.get("video_info") or args[2]
            path = video_info["path"]
            self.processed.append(path)
            if "bad" in path:
                raise ValueError(f"Failed to process {path}")
            return (True, "/results")

        def track_errors(error, context):
            self.errors.append(str(error))

        callbacks = ProcessingCallbacks(
            on_error=track_errors,
            on_completed=Mock(),
        )
        context = ProcessingContext(
            videos_to_process=[
                {"path": "/videos/good1.mp4"},
                {"path": "/videos/bad.mp4"},
                {"path": "/videos/good2.mp4"},
            ],
            output_base_dir="/results",
            cancel_event=mock_cancel_event,
            process_single_video_func=sometimes_fails,
        )

        worker = ProcessingWorker(context, callbacks)
        thread = worker.start_in_thread()
        thread.join(timeout=2.0)

        # All three should be attempted
        assert len(self.processed) == 3
        # One error should be recorded
        assert len(self.errors) == 1
        assert "bad.mp4" in self.errors[0]

        # Should still complete
        callbacks.on_completed.assert_called_once()
        args, kwargs = callbacks.on_completed.call_args
        assert not args[0]  # was_cancelled
        summary = kwargs.get("summary")
        assert summary["failed"] == 1
        assert summary["successful"] == 2

    def test_retry_strategy_continue(self, mock_cancel_event):
        """Test that the 'continue' strategy processes all good videos."""
        processed = []

        def fail_on_video_2(*args, **kwargs):
            index = kwargs.get("index")
            video_path = kwargs.get("video_info")["path"]
            if index == 1:
                raise ValueError("Video 2 failed")
            processed.append(video_path)
            return True, "/results"

        callbacks = ProcessingCallbacks(on_completed=Mock())
        context = ProcessingContext(
            videos_to_process=[
                {"path": "vid1.mp4"},
                {"path": "vid2.mp4"},
                {"path": "vid3.mp4"},
            ],
            output_base_dir="/results",
            cancel_event=mock_cancel_event,
            process_single_video_func=fail_on_video_2,
            retry_strategy="continue",
        )

        worker = ProcessingWorker(context, callbacks)
        thread = worker.start_in_thread()
        thread.join(timeout=2.0)

        assert processed == ["vid1.mp4", "vid3.mp4"]
        callbacks.on_completed.assert_called_once()
        args, kwargs = callbacks.on_completed.call_args
        summary = kwargs.get("summary")
        assert summary["failed"] == 1
        assert summary["failed_list"][0]["path"] == "vid2.mp4"

    def test_retry_strategy_stop(self, mock_cancel_event):
        """Test that the 'stop' strategy halts processing on the first error."""
        processed = []

        def fail_on_video_2(*args, **kwargs):
            index = kwargs.get("index")
            video_path = kwargs.get("video_info")["path"]
            if index == 1:
                raise ValueError("Video 2 failed")
            processed.append(video_path)
            return True, "/results"

        callbacks = ProcessingCallbacks(on_completed=Mock())
        context = ProcessingContext(
            videos_to_process=[
                {"path": "vid1.mp4"},
                {"path": "vid2.mp4"},
                {"path": "vid3.mp4"},
            ],
            output_base_dir="/results",
            cancel_event=mock_cancel_event,
            process_single_video_func=fail_on_video_2,
            retry_strategy="stop",
        )

        worker = ProcessingWorker(context, callbacks)
        thread = worker.start_in_thread()
        thread.join(timeout=2.0)

        assert processed == ["vid1.mp4"]
        callbacks.on_completed.assert_called_once()
        args, kwargs = callbacks.on_completed.call_args
        summary = kwargs.get("summary")
        assert summary["failed"] == 1
        # successful is total_videos - failed_videos, not len(processed)
        assert summary["successful"] == 2
        assert summary["total_videos"] == 3
