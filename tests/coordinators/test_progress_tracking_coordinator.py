"""Tests for ProgressTrackingCoordinator - batch context, lifecycle, and cancellation."""

from __future__ import annotations

import time
from threading import Event
from unittest.mock import MagicMock, Mock

import pytest

from zebtrack.coordinators.progress_tracking_coordinator import ProgressTrackingCoordinator


@pytest.fixture
def coordinator():
    state_manager = MagicMock()
    settings = MagicMock()
    ui_coordinator = MagicMock()
    cancel_event = Event()
    event_bus = MagicMock()
    root = MagicMock()
    view = MagicMock()

    coord = ProgressTrackingCoordinator(
        state_manager=state_manager,
        settings_obj=settings,
        ui_coordinator=ui_coordinator,
        cancel_event=cancel_event,
        event_bus=event_bus,
        view=view,
        root=root,
    )
    return coord


@pytest.fixture
def headless_coordinator():
    """Coordinator without view/root for pure-logic tests."""
    state_manager = MagicMock()
    settings = MagicMock()
    ui_coordinator = MagicMock()
    cancel_event = Event()
    event_bus = MagicMock()

    coord = ProgressTrackingCoordinator(
        state_manager=state_manager,
        settings_obj=settings,
        ui_coordinator=ui_coordinator,
        cancel_event=cancel_event,
        event_bus=event_bus,
        view=None,
        root=None,
    )
    return coord


# =====================================================================
# Batch Context Management
# =====================================================================


class TestBatchContext:
    def test_is_batch_processing_initially_false(self, coordinator):
        assert coordinator._is_batch_processing() is False

    def test_init_batch_context(self, coordinator):
        coordinator._init_batch_context(5)
        assert coordinator._is_batch_processing() is True
        assert coordinator._batch_context["total"] == 5
        assert coordinator._batch_context["completed"] == 0
        assert coordinator._batch_context["failed"] == 0
        assert coordinator._batch_context["skipped"] == 0

    def test_update_batch_context_completed(self, coordinator):
        coordinator._init_batch_context(3)
        coordinator._update_batch_context(completed=True)
        assert coordinator._batch_context["completed"] == 1

    def test_update_batch_context_failed(self, coordinator):
        coordinator._init_batch_context(3)
        coordinator._update_batch_context(failed=True, error_msg="test error")
        assert coordinator._batch_context["failed"] == 1
        assert "test error" in coordinator._batch_context["errors"]

    def test_update_batch_context_skipped(self, coordinator):
        coordinator._init_batch_context(3)
        coordinator._update_batch_context(skipped=True)
        assert coordinator._batch_context["skipped"] == 1

    def test_update_batch_context_no_context(self, coordinator):
        """Updating when there is no context should be a no-op."""
        coordinator._update_batch_context(completed=True)
        # No error raised

    def test_finalize_batch_context(self, coordinator):
        coordinator._init_batch_context(3)
        coordinator._update_batch_context(completed=True)
        coordinator._update_batch_context(completed=True)
        coordinator._update_batch_context(failed=True, error_msg="oops")
        ctx = coordinator._finalize_batch_context()
        assert ctx is not None
        assert ctx["completed"] == 2
        assert ctx["failed"] == 1
        assert "elapsed" in ctx
        assert coordinator._is_batch_processing() is False

    def test_finalize_batch_context_when_none(self, coordinator):
        ctx = coordinator._finalize_batch_context()
        assert ctx is None

    def test_set_dialog_suppression_enable(self, coordinator):
        coordinator._set_dialog_suppression(True)
        assert coordinator._is_batch_processing() is True

    def test_set_dialog_suppression_disable(self, coordinator):
        coordinator._init_batch_context(2)
        coordinator._set_dialog_suppression(False)
        assert coordinator._is_batch_processing() is False


# =====================================================================
# Active Processing Count
# =====================================================================


class TestActiveProcessingCount:
    def test_aquarium_count_for_task_none(self):
        assert ProgressTrackingCoordinator._aquarium_count_for_task(None) == 1

    def test_aquarium_count_for_task_non_multi(self):
        task = {"is_multi_aquarium": False}
        assert ProgressTrackingCoordinator._aquarium_count_for_task(task) == 1

    def test_aquarium_count_for_task_multi_with_aquariums(self):
        task = {
            "is_multi_aquarium": True,
            "zone_data": {"aquariums": [1, 2, 3]},
        }
        assert ProgressTrackingCoordinator._aquarium_count_for_task(task) == 3

    def test_aquarium_count_for_task_multi_empty_aquariums(self):
        task = {"is_multi_aquarium": True, "zone_data": {"aquariums": []}}
        assert ProgressTrackingCoordinator._aquarium_count_for_task(task) == 1

    def test_current_task_empty_batch(self, coordinator):
        assert coordinator._current_task() is None

    def test_current_task_with_videos(self, coordinator):
        coordinator._batch_videos = [{"path": "a.mp4"}, {"path": "b.mp4"}]
        coordinator._current_video_idx = 1
        assert coordinator._current_task() == {"path": "b.mp4"}

    def test_emit_processing_count_event(self, coordinator):
        coordinator._emit_processing_count_event(5)
        coordinator.event_bus.publish.assert_called_once()

    def test_publish_active_processing_count(self, coordinator):
        coordinator._publish_active_processing_count(3)
        coordinator.state_manager.update_processing_state.assert_called_once()
        coordinator.event_bus.publish.assert_called_once()

    def test_refresh_active_processing_count(self, coordinator):
        coordinator._batch_videos = [
            {"is_multi_aquarium": True, "zone_data": {"aquariums": [1, 2]}}
        ]
        coordinator._current_video_idx = 0
        coordinator._refresh_active_processing_count()
        coordinator.state_manager.update_processing_state.assert_called_once()


# =====================================================================
# Processing Lifecycle
# =====================================================================


class TestProcessingLifecycle:
    def test_on_processing_started(self, coordinator):
        coordinator._on_processing_started("/path/to/video.mp4")
        coordinator.state_manager.update_processing_state.assert_called_once()
        coordinator.root.after.assert_called_once()

    def test_on_processing_started_headless(self, headless_coordinator):
        headless_coordinator._on_processing_started("/path/to/video.mp4")
        headless_coordinator.state_manager.update_processing_state.assert_called_once()

    def test_on_processing_error_batch(self, coordinator):
        coordinator._init_batch_context(3)
        coordinator._on_processing_error({"error": "some error", "video_path": "v.mp4"})
        assert coordinator._batch_context["failed"] == 1
        assert "some error" in coordinator._batch_context["errors"]

    def test_on_processing_error_single(self, coordinator):
        coordinator._on_processing_error({"error": "some error", "video_path": "v.mp4"})
        coordinator.event_bus.publish.assert_called_once()

    def test_on_processing_error_no_video(self, coordinator):
        coordinator._on_processing_error({"error": "err"})
        coordinator.event_bus.publish.assert_called()

    def test_on_processing_fatal_error(self, coordinator):
        coordinator._on_processing_fatal_error({"error": "fatal!", "video_path": "v.mp4"})
        coordinator.state_manager.update_processing_state.assert_called()
        coordinator.root.after.assert_called()
        coordinator.event_bus.publish.assert_called()

    def test_on_processing_progress_updates_state(self, coordinator):
        coordinator._on_processing_progress(
            {
                "total_frames": 100,
                "processed_frames": 50,
                "detected_frames": 10,
            }
        )
        coordinator.state_manager.update_processing_state.assert_called()

    def test_on_processing_progress_video_switch(self, coordinator):
        coordinator._batch_videos = [{"path": "a.mp4"}, {"path": "b.mp4"}]
        coordinator._current_video_idx = 0
        coordinator._on_processing_progress(
            {
                "total_frames": 100,
                "processed_frames": 50,
                "idx": 1,
            }
        )
        assert coordinator._current_video_idx == 1

    def test_on_processing_progress_zero_total(self, coordinator):
        """Zero total frames should not trigger UI update."""
        coordinator._on_processing_progress(
            {
                "total_frames": 0,
                "processed_frames": 0,
            }
        )
        # state is still updated
        coordinator.state_manager.update_processing_state.assert_called()

    def test_on_frame_processed_no_view(self, headless_coordinator):
        """No view = no-op."""
        headless_coordinator._on_frame_processed({"frame": "data", "detections": []})
        # No error raised

    def test_on_frame_processed_no_frame(self, coordinator):
        """frame=None should not schedule update."""
        coordinator._on_frame_processed({"frame": None, "detections": []})
        coordinator.root.after.assert_not_called()

    def test_on_frame_processed_with_frame(self, coordinator):
        coordinator._on_frame_processed(
            {
                "frame": MagicMock(),
                "detections": [{"class": 0}],
                "frame_number": 42,
            }
        )
        coordinator.root.after.assert_called_once()

    def test_update_frame_display_no_view(self, headless_coordinator):
        headless_coordinator._update_frame_display(None, [], 0)

    def test_update_frame_display_with_canvas(self, coordinator):
        coordinator._update_frame_display(MagicMock(), [{"class": 0}], 42)
        coordinator.view.canvas_manager.update_video_frame.assert_called_once()


# =====================================================================
# Processing Completion
# =====================================================================


class TestProcessingComplete:
    def test_single_video_success(self, coordinator):
        coordinator._on_processing_complete(
            {
                "videos_to_process": [{"path": "v.mp4"}],
                "success": True,
                "output_dir": "/out",
            }
        )
        coordinator.state_manager.update_processing_state.assert_called()
        # Should publish info + refresh
        assert coordinator.event_bus.publish.call_count >= 2

    def test_single_video_failure(self, coordinator):
        coordinator._on_processing_complete(
            {
                "videos_to_process": [{"path": "v.mp4"}],
                "success": False,
                "output_dir": "/out",
            }
        )
        coordinator.state_manager.update_processing_state.assert_called()

    def test_batch_completion_triggers_summary(self, coordinator):
        coordinator._init_batch_context(1)
        coordinator._on_processing_complete(
            {
                "videos_to_process": [{"path": "v.mp4"}],
                "success": True,
            }
        )
        # Batch context finalized
        assert coordinator._batch_context is None

    def test_on_completed_callback(self, coordinator):
        cb = Mock()
        coordinator._on_processing_complete(
            {
                "success": True,
                "on_completed_callback": cb,
            }
        )
        cb.assert_called_once()

    def test_on_completed_callback_error(self, coordinator):
        cb = Mock(side_effect=RuntimeError("oops"))
        coordinator._on_processing_complete(
            {
                "success": True,
                "on_completed_callback": cb,
            }
        )
        # Should not raise, just log

    def test_finalize_progress_and_stop(self, coordinator):
        coordinator._finalize_progress_and_stop()
        coordinator.ui_coordinator.update_progress.assert_called_once()
        coordinator.root.after.assert_called_once()

    def test_update_ui_for_processing_stop(self, coordinator):
        coordinator._update_ui_for_processing_stop()
        coordinator.ui_coordinator.hide_progress_bar.assert_called_once()

    def test_update_ui_for_processing_stop_no_view(self, headless_coordinator):
        headless_coordinator._update_ui_for_processing_stop()
        # No error


# =====================================================================
# Batch Summary
# =====================================================================


class TestBatchSummary:
    def test_show_batch_summary_none(self, coordinator):
        coordinator._show_batch_summary(None)
        coordinator.event_bus.publish.assert_not_called()

    def test_show_batch_summary_success_only(self, coordinator):
        ctx = {
            "completed": 3,
            "failed": 0,
            "skipped": 0,
            "elapsed": 10.5,
            "errors": [],
        }
        coordinator._show_batch_summary(ctx)
        coordinator.event_bus.publish.assert_called_once()

    def test_show_batch_summary_with_failures(self, coordinator):
        ctx = {
            "completed": 2,
            "failed": 1,
            "skipped": 1,
            "elapsed": 20.0,
            "errors": ["error 1", "error 2"],
        }
        coordinator._show_batch_summary(ctx)
        coordinator.event_bus.publish.assert_called_once()

    def test_show_batch_summary_many_errors(self, coordinator):
        ctx = {
            "completed": 0,
            "failed": 10,
            "skipped": 0,
            "elapsed": 60.0,
            "errors": [f"error {i}" for i in range(10)],
        }
        coordinator._show_batch_summary(ctx)
        coordinator.event_bus.publish.assert_called_once()


# =====================================================================
# Cancellation
# =====================================================================


class TestCancellation:
    def test_cancel_processing(self, coordinator):
        coordinator.cancel_processing()
        assert coordinator.cancel_event.is_set()
        coordinator.state_manager.update_processing_state.assert_called()

    def test_cancel_processing_with_worker(self, coordinator):
        """The worker must be cancelled through the API it actually has.

        ``spec=ProcessingWorker`` is the whole point: this used to assert
        ``worker.stop()``, which a bare MagicMock happily accepts because it
        auto-creates every attribute. Production ``ProcessingWorker`` has no
        ``stop`` — only ``cancel`` — so the ``hasattr(worker, "stop")`` guard in
        ``cancel_processing`` skipped the call on every real run while the test
        stayed green. A spec'd double raises AttributeError instead.
        """
        from zebtrack.core.video.processing_worker import ProcessingWorker

        vpc = MagicMock()
        vpc.processing_worker = MagicMock(spec=ProcessingWorker)
        coordinator._video_processing_coordinator = vpc

        coordinator.cancel_processing()

        vpc.processing_worker.cancel.assert_called_once()
        _args, kwargs = vpc.processing_worker.cancel.call_args
        assert kwargs.get("timeout") == coordinator.WORKER_CANCEL_TIMEOUT_S, (
            "cancel must be bounded — it runs on the Tk main thread"
        )

    def test_cancel_processing_survives_worker_without_cancel(self, coordinator):
        """A worker double lacking the API must degrade, not raise."""
        vpc = MagicMock()
        vpc.processing_worker = object()
        coordinator._video_processing_coordinator = vpc

        coordinator.cancel_processing()

        assert coordinator.cancel_event.is_set()

    def test_update_ui_for_cancel(self, coordinator):
        coordinator._update_ui_for_cancel()
        coordinator.ui_coordinator.set_status.assert_called_once()

    def test_update_ui_for_cancel_no_view(self, headless_coordinator):
        headless_coordinator._update_ui_for_cancel()
        # No error


# =====================================================================
# Progress Callback Factory
# =====================================================================


class TestMakeProgressCallback:
    def test_make_progress_callback_returns_callable(self, coordinator):
        cb = coordinator.make_progress_callback(100, video_name="test.mp4")
        assert callable(cb)

    def test_progress_callback_zero_total(self, coordinator):
        cb = coordinator.make_progress_callback(0, video_name="test.mp4")
        cb(0, 0)  # Should return early without error

    def test_progress_callback_updates(self, coordinator):
        cb = coordinator.make_progress_callback(
            100, video_name="test.mp4", start_time=time.time() - 10
        )
        cb(50, 10)
        coordinator.state_manager.update_processing_state.assert_called()


# =====================================================================
# UI Update Methods
# =====================================================================


class TestUIUpdates:
    def test_update_ui_progress(self, coordinator):
        coordinator._update_ui_progress(0.5, 50, 100, 10)
        coordinator.ui_coordinator.update_progress.assert_called_once()
        coordinator.ui_coordinator.set_status.assert_called_once()

    def test_update_ui_progress_no_view(self, headless_coordinator):
        headless_coordinator._update_ui_progress(0.5, 50, 100, 10)
        # No error

    def test_update_ui_for_processing_start(self, coordinator):
        coordinator._update_ui_for_processing_start("video.mp4")
        coordinator.ui_coordinator.set_status.assert_called()

    def test_update_ui_for_processing_start_already_active(self, coordinator):
        coordinator.view.analysis_active = True
        coordinator._update_ui_for_processing_start("video.mp4", "/path/video.mp4")
        coordinator.ui_coordinator.set_status.assert_called()

    def test_update_ui_for_processing_start_no_view(self, headless_coordinator):
        headless_coordinator._update_ui_for_processing_start("video.mp4")
        # No error


# =====================================================================
# Metadata Publishing
# =====================================================================


class TestPublishAnalysisMetadata:
    def test_no_video_path(self, coordinator):
        coordinator._publish_analysis_metadata_for_video(None)
        # Early return, no publish

    def test_no_project_manager(self, coordinator):
        coordinator._video_processing_coordinator = None
        coordinator._publish_analysis_metadata_for_video("/path/video.mp4")
        # Early return

    def test_with_entry_metadata(self, coordinator):
        vpc = MagicMock()
        vpc.project_manager.find_video_entry.return_value = {
            "metadata": {"group": "A", "day": "1"},
        }
        vpc.project_manager.project_data = {}
        coordinator._video_processing_coordinator = vpc
        coordinator._publish_analysis_metadata_for_video("/path/video.mp4")
        coordinator.event_bus.publish.assert_called()

    def test_fallback_to_project_data(self, coordinator):
        vpc = MagicMock()
        vpc.project_manager.find_video_entry.return_value = {"metadata": {}}
        vpc.project_manager.project_data = {
            "last_selected_group": "GroupB",
            "last_selected_day": "3",
            "subjects_per_group": "5",
        }
        coordinator._video_processing_coordinator = vpc
        coordinator._publish_analysis_metadata_for_video("/path/video.mp4")
        coordinator.event_bus.publish.assert_called()

    def test_fallback_to_groups_list(self, coordinator):
        vpc = MagicMock()
        vpc.project_manager.find_video_entry.return_value = {"metadata": {}}
        vpc.project_manager.project_data = {
            "groups": ["Control", "Treatment"],
        }
        coordinator._video_processing_coordinator = vpc
        coordinator._publish_analysis_metadata_for_video("/path/video.mp4")
        coordinator.event_bus.publish.assert_called()

    def test_no_metadata_at_all(self, coordinator):
        vpc = MagicMock()
        vpc.project_manager.find_video_entry.return_value = None
        vpc.project_manager.project_data = {}
        coordinator._video_processing_coordinator = vpc
        coordinator._publish_analysis_metadata_for_video("/path/video.mp4")
        # No publish since combined is empty

    def test_entry_top_level_keys(self, coordinator):
        vpc = MagicMock()
        vpc.project_manager.find_video_entry.return_value = {
            "metadata": {},
            "group": "TopGroup",
            "day": "2",
            "subject": "1",
        }
        vpc.project_manager.project_data = {}
        coordinator._video_processing_coordinator = vpc
        coordinator._publish_analysis_metadata_for_video("/path/video.mp4")
        coordinator.event_bus.publish.assert_called()
