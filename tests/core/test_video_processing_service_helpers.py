"""Helper tests for VideoProcessingService small utilities."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from zebtrack.core.video.video_processing_service import VideoContext, VideoProcessingService
from zebtrack.ui.event_bus_v2 import Event, UIEvents


def _make_service():
    project_manager = MagicMock()
    state_manager = MagicMock()
    ui_coordinator = MagicMock()
    ui_event_bus = MagicMock()
    cancel_event = MagicMock()
    cancel_event.is_set.return_value = False
    settings_obj = MagicMock()
    settings_obj.video_processing = MagicMock(fps=30.0)
    return VideoProcessingService(
        project_manager=project_manager,
        state_manager=state_manager,
        ui_coordinator=ui_coordinator,
        ui_event_bus=ui_event_bus,
        cancel_event=cancel_event,
        settings_obj=settings_obj,
    )


def test_video_context_reset_and_release():
    cap = MagicMock()
    cap.isOpened.return_value = True

    context = VideoContext(path="video.mp4", cap=cap, width=1, height=1, fps=30.0)
    context.reset()
    cap.set.assert_called_once()

    context.release()
    cap.release.assert_called_once()
    assert context.cap is None


def test_seek_to_frame_backward():
    service = _make_service()
    cap = MagicMock()

    assert service._seek_to_frame(cap, target_frame=0, current_frame=10, skip_threshold=5) is True
    cap.set.assert_called_once()


def test_seek_to_frame_small_gap():
    service = _make_service()
    cap = MagicMock()
    cap.grab.side_effect = [True, True, True]

    assert service._seek_to_frame(cap, target_frame=5, current_frame=2, skip_threshold=10) is True
    assert cap.grab.call_count == 3


def test_seek_to_frame_small_gap_failure():
    service = _make_service()
    cap = MagicMock()
    cap.grab.side_effect = [True, False]

    assert service._seek_to_frame(cap, target_frame=4, current_frame=2, skip_threshold=10) is False


def test_seek_to_frame_large_gap():
    service = _make_service()
    cap = MagicMock()

    assert service._seek_to_frame(cap, target_frame=100, current_frame=0, skip_threshold=10) is True
    cap.set.assert_called_once()


def test_resolve_results_path_project(tmp_path):
    service = _make_service()
    service.project_manager.project_path = tmp_path
    service.project_manager.resolve_results_directory.return_value = tmp_path / "results"

    path, existed = service.resolve_results_path(
        experiment_id="exp1",
        video_path="video.mp4",
        metadata_context=None,
        single_video_config=None,
        output_base_dir=str(tmp_path / "fallback"),
    )

    assert path.name == "results"
    assert existed is False
    assert path.exists() is True


def test_resolve_results_path_single_video(tmp_path):
    service = _make_service()
    service.project_manager.project_path = tmp_path

    path, _ = service.resolve_results_path(
        experiment_id="exp1",
        video_path="video.mp4",
        metadata_context=None,
        single_video_config={"mode": "single"},
        output_base_dir=str(tmp_path / "fallback"),
    )

    assert path == tmp_path / "fallback"


def test_resolve_results_path_existing(tmp_path):
    service = _make_service()
    existing = tmp_path / "results"
    existing.mkdir()

    service.project_manager.project_path = tmp_path
    service.project_manager.resolve_results_directory.return_value = existing

    path, existed = service.resolve_results_path(
        experiment_id="exp1",
        video_path="video.mp4",
        metadata_context=None,
        single_video_config=None,
        output_base_dir=str(tmp_path / "fallback"),
    )

    assert path == existing
    assert existed is True


def test_ensure_arena_polygon_from_context():
    service = _make_service()
    context = VideoContext(path="v", cap=None, width=100, height=50, fps=30.0)

    polygon = service.ensure_arena_polygon(None, video_context=context)

    assert polygon == [[0, 0], [100, 0], [100, 50], [0, 50]]


def test_ensure_arena_polygon_from_video_path(monkeypatch):
    service = _make_service()
    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.get.side_effect = [640, 480]

    monkeypatch.setattr(
        "zebtrack.core.video.video_processing_service.cv2.VideoCapture",
        lambda _: cap,
    )

    polygon = service.ensure_arena_polygon(None, video_path="video.mp4")

    assert polygon == [[0, 0], [640, 0], [640, 480], [0, 480]]
    cap.release.assert_called_once()


def test_load_trajectory_dataframe_missing_file(tmp_path):
    service = _make_service()
    missing = tmp_path / "missing.parquet"

    result = service.load_trajectory_dataframe(missing, experiment_id="exp1")

    assert result is None
    if service.ui_event_bus.publish.called:
        service.ui_event_bus.publish.assert_called_once()
        event = service.ui_event_bus.publish.call_args[0][0]
        assert event.type == UIEvents.SHOW_ERROR
    else:
        service.ui_event_bus.publish_event.assert_called_once()
        assert service.ui_event_bus.publish_event.call_args[0][0] == UIEvents.SHOW_ERROR


def test_build_metadata_context_skips_single_video_config():
    service = _make_service()

    result = service._build_metadata_context(
        video_info={"metadata": {"group": "G1"}},
        single_video_config={"mode": "single"},
        experiment_id="exp1",
        video_path="/video.mp4",
    )

    assert result is None


def test_build_metadata_context_merges_derived():
    service = _make_service()
    service.project_manager.derive_processing_metadata.return_value = {"group": "G2"}

    result = service._build_metadata_context(
        video_info={"metadata": {"subject": 1}},
        single_video_config=None,
        experiment_id="exp1",
        video_path="/video.mp4",
    )

    assert result == {"subject": 1, "group": "G2"}


def test_build_metadata_context_handles_errors():
    service = _make_service()
    service.project_manager.derive_processing_metadata.side_effect = Exception("boom")

    result = service._build_metadata_context(
        video_info={"metadata": {"subject": 1}},
        single_video_config=None,
        experiment_id="exp1",
        video_path="/video.mp4",
    )

    assert result == {"subject": 1}


def test_schedule_analysis_metadata_update_publishes():
    service = _make_service()

    service._schedule_analysis_metadata_update({"group": "G1"})

    service.ui_event_bus.publish.assert_called_once_with(
        Event(type=UIEvents.UI_UPDATE_ANALYSIS_METADATA, data={"metadata": {"group": "G1"}})
    )


def test_notify_task_status_start_publishes():
    service = _make_service()

    service._notify_task_status_start(index=1, total=5, experiment_id="exp1")

    service.ui_event_bus.publish.assert_called_once_with(
        Event(
            type=UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS,
            data={"payload": {"index": 1, "total": 5, "experiment_id": "exp1"}},
        )
    )


def test_make_progress_callback_publishes_status():
    service = _make_service()

    callback = service._make_progress_callback(index=0, total_videos=2, experiment_id="exp1")
    callback(0.5, "Processing", None, None, None)

    service.ui_event_bus.publish.assert_called_once_with(
        Event(
            type=UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS,
            data={
                "payload": {
                    "index": 0,
                    "total": 2,
                    "experiment_id": "exp1",
                    "step": "Processing",
                }
            },
        )
    )


def test_snapshot_results_dir_missing_returns_empty(tmp_path):
    service = _make_service()
    missing = tmp_path / "missing"

    assert service._snapshot_results_dir(missing) == set()


def test_snapshot_results_dir(tmp_path):
    service = _make_service()
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "a.txt").write_text("a")
    (results_dir / "b.txt").write_text("b")

    snapshot = service._snapshot_results_dir(results_dir)

    assert snapshot == {"a.txt", "b.txt"}


def test_cleanup_cancelled_results_removes_new_items(tmp_path):
    service = _make_service()
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "keep.txt").write_text("keep")
    (results_dir / "remove.txt").write_text("remove")
    (results_dir / "subdir").mkdir()

    service._cleanup_cancelled_results(str(results_dir), {"keep.txt"})

    assert (results_dir / "keep.txt").exists()
    assert not (results_dir / "remove.txt").exists()
    assert not (results_dir / "subdir").exists()


def test_cleanup_cancelled_results_removes_empty_dir(tmp_path):
    service = _make_service()
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "remove.txt").write_text("remove")

    service._cleanup_cancelled_results(str(results_dir), set())

    assert not results_dir.exists()


def test_prepare_results_directory_archives_existing(tmp_path):
    service = _make_service()
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "old.txt").write_text("old")

    with patch("zebtrack.core.video.video_processing_service.datetime") as dt_mock:
        dt_mock.now.return_value.strftime.return_value = "20240101-120000"
        service._prepare_results_directory(str(results_dir))

    archived = results_dir / "history" / "20240101-120000" / "old.txt"
    assert archived.exists()


def test_compose_analysis_view_metadata_merges_sources():
    service = _make_service()
    service.project_manager.find_video_entry.return_value = {
        "metadata": {},
        "group": "G1",
        "day": 1,
        "subject": 2,
    }

    result = service._compose_analysis_view_metadata(
        experiment_id="exp1",
        video_path="/video.mp4",
        metadata_context={"subject": 3},
        single_video_config={"group_label": "Custom", "animal": 4},
        analysis_profile={"name": "Profile", "track_ids": [1, 2]},
    )

    assert result["experiment_id"] == "exp1"
    assert result["group"] == "G1"
    assert result["subject"] == 3
    assert result["group_display_name"] == "Custom"
    assert result["analysis_profile"] == "Profile"
    assert result["analysis_profile_tracks"] == [1, 2]
