"""Helper tests for VideoProcessingService small utilities."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from zebtrack.core.video.video_processing_service import VideoContext, VideoProcessingService
from zebtrack.ui.event_bus_v2 import Event, UIEvents
from zebtrack.ui.payloads import AnalysisMetadataPayload, AnalysisTaskStatusPayload


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
    # schedule_after defers the publish to the main thread; simulate immediate
    # execution so the test can assert on the final publish call.
    service.ui_coordinator.schedule_after.side_effect = lambda _delay, fn, *a, **kw: fn(*a, **kw)

    metadata = {"group": "G1"}
    service._schedule_analysis_metadata_update(metadata)

    expected = AnalysisMetadataPayload(metadata=metadata)
    service.ui_event_bus.publish.assert_called_once_with(
        Event(type=UIEvents.UI_UPDATE_ANALYSIS_METADATA, data=expected)
    )


def test_notify_task_status_start_publishes():
    service = _make_service()

    service._notify_task_status_start(index=1, total=5, experiment_id="exp1")

    service.ui_event_bus.publish.assert_called_once_with(
        Event(
            type=UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS,
            data=AnalysisTaskStatusPayload(index=1, total=5, experiment_id="exp1"),
        )
    )


def test_make_progress_callback_publishes_status():
    service = _make_service()

    callback = service._make_progress_callback(index=0, total_videos=2, experiment_id="exp1")
    callback(0.5, "Processing", None, None, None)

    service.ui_event_bus.publish.assert_called_once_with(
        Event(
            type=UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS,
            data=AnalysisTaskStatusPayload(
                index=0,
                total=2,
                experiment_id="exp1",
                step="Processing",
            ),
        )
    )


def _published(service, event_type):
    return [
        call.args[0].data
        for call in service.ui_event_bus.publish.call_args_list
        if call.args[0].type == event_type
    ]


def test_progress_callbacks_publish_the_detectors_roles():
    """#645: both callback variants forward the role map with the detections."""
    for factory in ("_make_progress_callback", "create_progress_callback"):
        service = _make_service()
        callback = getattr(service, factory)(index=0, total_videos=1, experiment_id="exp1")
        callback(0.5, "Processing", "frame", None, [(0, 0, 1, 1)], class_roles={2: "subject"})

        overlay = _published(service, UIEvents.UI_UPDATE_DETECTION_OVERLAY)
        frames = _published(service, UIEvents.UI_DISPLAY_FRAME)
        assert [p.class_roles for p in overlay] == [{2: "subject"}], factory
        assert [p.class_roles for p in frames] == [{2: "subject"}], factory


def test_progress_callbacks_without_roles_publish_none():
    for factory in ("_make_progress_callback", "create_progress_callback"):
        service = _make_service()
        callback = getattr(service, factory)(index=0, total_videos=1, experiment_id="exp1")
        callback(0.5, "Processing", "frame", None, [])

        overlay = _published(service, UIEvents.UI_UPDATE_DETECTION_OVERLAY)
        frames = _published(service, UIEvents.UI_DISPLAY_FRAME)
        assert [p.class_roles for p in overlay] == [None], factory
        assert [p.class_roles for p in frames] == [None], factory


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

    with patch("zebtrack.core.video.video_context_factory.datetime") as dt_mock:
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


# ---------------------------------------------------------------------------
# ProgressNotifierMixin: what each callback and message carries (TASK-087)
# ---------------------------------------------------------------------------


class _RecordingBus:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)

    def of(self, event_type):
        return [e.data for e in self.events if e.type == event_type]


def _notifier(*, bus=True, scheduler=None, entry=None):
    import threading
    from types import SimpleNamespace

    project = SimpleNamespace(
        find_video_entry=lambda **kw: entry,
        derive_processing_metadata=lambda *a: {},
    )
    service = _make_service()
    service.ui_event_bus = _RecordingBus() if bus else None
    service.ui_coordinator = scheduler
    service.cancel_event = threading.Event()
    service.project_manager = project
    return service


class TestMakeProgressCallback:
    def _callback(self, service, report=None):
        return service._make_progress_callback(
            index=2, total_videos=5, experiment_id="CECT_4", processing_report_callback=report
        )

    def test_a_cancelled_run_publishes_nothing(self):
        service = _notifier()
        service.cancel_event.set()

        self._callback(service)(0.5, "step", "frame", {"fps": 1}, [(1, 2, 3, 4, 0.9, 1)])

        assert service.ui_event_bus.events == []

    def test_the_status_event_names_the_video_and_the_step(self):
        service = _notifier()

        self._callback(service)(0.5, "Detecting")

        (status,) = service.ui_event_bus.of(UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS)
        assert (status.index, status.total, status.experiment_id, status.step) == (
            2,
            5,
            "CECT_4",
            "Detecting",
        )
        # Nothing else without stats, detections or a frame.
        assert len(service.ui_event_bus.events) == 1

    def test_stats_are_published_only_when_there_are_some(self):
        service = _notifier()
        callback = self._callback(service)

        callback(0.1, "a", stats={})
        callback(0.2, "b", stats={"fps": 12.5})

        stats = service.ui_event_bus.of(UIEvents.UI_UPDATE_PROCESSING_STATS)
        assert [s.stats for s in stats] == [{"fps": 12.5}]

    def test_detections_carry_the_report_and_the_roles(self):
        service = _notifier()
        detections = [(1, 2, 3, 4, 0.9, 7)]

        self._callback(service, report=lambda: {"frames": 9})(
            0.3, "x", detections=detections, class_roles={1: "subject"}
        )

        (overlay,) = service.ui_event_bus.of(UIEvents.UI_UPDATE_DETECTION_OVERLAY)
        assert overlay.detections == detections
        assert overlay.report == {"frames": 9}
        assert overlay.class_roles == {1: "subject"}

    def test_a_report_callback_that_raises_does_not_lose_the_overlay(self):
        service = _notifier()

        def broken():
            raise RuntimeError("report not ready")

        self._callback(service, report=broken)(0.3, "x", detections=[])

        (overlay,) = service.ui_event_bus.of(UIEvents.UI_UPDATE_DETECTION_OVERLAY)
        assert overlay.detections == []
        assert overlay.report is None

    def test_a_frame_is_displayed_with_its_detections_or_an_empty_list(self):
        service = _notifier()
        callback = self._callback(service)
        frame = object()

        callback(0.1, "a", frame=frame, detections=[(1, 2, 3, 4, 0.9, 7)])
        callback(0.2, "b", frame=frame)
        callback(0.3, "c", frame=None)

        shown = service.ui_event_bus.of(UIEvents.UI_DISPLAY_FRAME)
        assert [s.detections for s in shown] == [[(1, 2, 3, 4, 0.9, 7)], []]
        assert all(s.frame is frame for s in shown)


class TestNotifierHelpers:
    def test_the_analysis_metadata_goes_through_the_scheduler_at_delay_zero(self):
        class Scheduler:
            def __init__(self):
                self.delays = []
                self.pending = []

            def schedule_after(self, delay, fn):
                self.delays.append(delay)
                self.pending.append(fn)

        scheduler = Scheduler()
        service = _notifier(scheduler=scheduler)

        service._schedule_analysis_metadata_update({"group": "G"})

        # Deferred: nothing is published until the main thread runs it.
        assert service.ui_event_bus.events == []
        assert scheduler.delays == [0]
        scheduler.pending[0]()
        (payload,) = service.ui_event_bus.of(UIEvents.UI_UPDATE_ANALYSIS_METADATA)
        assert payload.metadata == {"group": "G"}

    def test_without_a_scheduler_the_metadata_is_published_directly(self):
        service = _notifier(scheduler=None)
        service._schedule_analysis_metadata_update({"group": "G"})
        assert len(service.ui_event_bus.of(UIEvents.UI_UPDATE_ANALYSIS_METADATA)) == 1

    def test_without_a_bus_metadata_and_task_status_are_dropped(self):
        service = _notifier(bus=False)
        service._schedule_analysis_metadata_update({"group": "G"})
        service._notify_task_status_start(index=0, total=1, experiment_id="E")


class TestComposeAnalysisViewMetadata:
    def _compose(self, service, **kw):
        defaults = {
            "experiment_id": "E1",
            "video_path": "/v.mp4",
            "metadata_context": None,
            "single_video_config": None,
            "analysis_profile": None,
        }
        defaults.update(kw)
        return service._compose_analysis_view_metadata(**defaults)

    def test_without_any_source_only_the_experiment_id_is_known(self):
        assert self._compose(_notifier()) == {"experiment_id": "E1"}

    def test_the_entry_metadata_wins_over_its_top_level_keys(self):
        entry = {
            "metadata": {"group": "FromMeta", "extra": 1},
            "group": "TopLevel",
            "group_display_name": "Display",
            "day": "",
            "subject": None,
        }
        combined = self._compose(_notifier(entry=entry))
        assert combined == {
            "group": "FromMeta",
            "extra": 1,
            "group_display_name": "Display",
            "experiment_id": "E1",
        }

    def test_the_context_overrides_but_skips_empty_values(self):
        entry = {"metadata": {"group": "A", "day": 1}}
        combined = self._compose(
            _notifier(entry=entry),
            metadata_context={"group": "B", "day": "", "subject": None, "age": 3},
        )
        assert combined == {"group": "B", "day": 1, "age": 3, "experiment_id": "E1"}

    def test_a_single_video_config_only_fills_the_gaps(self):
        combined = self._compose(
            _notifier(entry={"metadata": {"group": "Kept"}}),
            single_video_config={
                "group_id": "Ignored",
                "group_label": "Label",
                "day_id": 4,
                "animal": "A7",
                "subject": "",
            },
        )
        assert combined["group"] == "Kept"
        assert combined["group_display_name"] == "Label"
        assert combined["day"] == 4
        assert combined["subject"] == "A7"

    def test_the_experiment_id_never_overrides_one_already_known(self):
        combined = self._compose(_notifier(), metadata_context={"experiment_id": "Given"})
        assert combined["experiment_id"] == "Given"

    def test_the_analysis_profile_adds_its_name_and_tracks(self):
        combined = self._compose(
            _notifier(), analysis_profile={"name": "Focal", "track_ids": (1, 2)}
        )
        assert combined["analysis_profile"] == "Focal"
        assert combined["analysis_profile_tracks"] == [1, 2]

    def test_an_empty_or_malformed_profile_adds_nothing(self):
        service = _notifier()
        assert self._compose(service, analysis_profile={"name": "", "track_ids": []}) == {
            "experiment_id": "E1"
        }
        assert self._compose(service, analysis_profile=["not", "a", "dict"]) == {
            "experiment_id": "E1"
        }
