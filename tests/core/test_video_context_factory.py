"""Unit tests for ``zebtrack.core.video.video_context_factory.VideoContextFactoryMixin``.

The mixin bundles small, well-isolated helpers for frame seeking, arena-polygon
fallback, results-directory bookkeeping and trajectory loading. Most are pure
logic or filesystem operations, so they are tested directly on a bare mixin
instance with attributes injected as needed (``ui_event_bus``, ``project_manager``).

``cv2.VideoCapture`` is stood in with ``Mock``; the filesystem helpers use
``tmp_path``.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pandas as pd
import pytest

from zebtrack.core.video.video_context_factory import VideoContextFactoryMixin
from zebtrack.ui.event_bus_v2 import UIEvents


@pytest.fixture
def factory():
    obj = VideoContextFactoryMixin()
    obj.ui_event_bus = None  # type: ignore[assignment]  # error-publish helpers short-circuit on None
    obj.project_manager = Mock(project_path=None)
    return obj


class TestSeekToFrame:
    def test_backward_seek_uses_set(self, factory):
        cap = Mock()
        assert factory._seek_to_frame(cap, target_frame=5, current_frame=10) is True
        cap.set.assert_called_once()
        cap.grab.assert_not_called()

    def test_small_gap_uses_grab(self, factory):
        cap = Mock()
        cap.grab.return_value = True
        assert (
            factory._seek_to_frame(cap, target_frame=10, current_frame=5, skip_threshold=60) is True
        )
        assert cap.grab.call_count == 5
        cap.set.assert_not_called()

    def test_grab_failure_returns_false(self, factory):
        cap = Mock()
        cap.grab.return_value = False
        assert (
            factory._seek_to_frame(cap, target_frame=10, current_frame=5, skip_threshold=60)
            is False
        )

    def test_large_gap_uses_set(self, factory):
        cap = Mock()
        assert (
            factory._seek_to_frame(cap, target_frame=200, current_frame=0, skip_threshold=60)
            is True
        )
        cap.set.assert_called_once()
        cap.grab.assert_not_called()


class TestEnsureArenaPolygon:
    def test_existing_polygon_passthrough(self, factory):
        poly = [[0, 0], [10, 0], [10, 10]]
        assert factory.ensure_arena_polygon(poly) is poly

    def test_fallback_from_video_context(self, factory):
        ctx = SimpleNamespace(width=640, height=480)
        result = factory.ensure_arena_polygon(None, video_context=ctx)
        assert result == [[0, 0], [640, 0], [640, 480], [0, 480]]

    def test_all_none_returns_none(self, factory):
        assert factory.ensure_arena_polygon(None) is None


class TestResultsDirectoryHelpers:
    def test_snapshot_empty_for_missing_dir(self, factory, tmp_path):
        assert factory._snapshot_results_dir(tmp_path / "nope") == set()

    def test_snapshot_lists_names(self, factory, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.txt").write_text("y")
        assert factory._snapshot_results_dir(tmp_path) == {"a.txt", "b.txt"}

    def test_cleanup_removes_non_baseline_items(self, factory, tmp_path):
        keep = tmp_path / "keep.txt"
        keep.write_text("k")
        new = tmp_path / "new.txt"
        new.write_text("n")
        factory._cleanup_cancelled_results(tmp_path, baseline_items={"keep.txt"})
        assert keep.exists()
        assert not new.exists()

    def test_prepare_archives_previous_run(self, factory, tmp_path):
        results = tmp_path / "results"
        results.mkdir()
        (results / "old.parquet").write_text("data")
        factory._prepare_results_directory(results)
        # Previous artifact is moved under history/<timestamp>/, root no longer holds it.
        assert not (results / "old.parquet").exists()
        assert (results / "history").exists()
        archived = list((results / "history").rglob("old.parquet"))
        assert len(archived) == 1

    def test_prepare_noop_on_empty_dir(self, factory, tmp_path):
        results = tmp_path / "empty"
        factory._prepare_results_directory(results)
        assert results.exists()
        assert not (results / "history").exists()


class TestResolveResultsPath:
    def test_uses_output_base_dir_without_project(self, factory, tmp_path):
        out = tmp_path / "out"
        path, existed_before = factory.resolve_results_path(
            experiment_id="exp1",
            video_path="v.mp4",
            metadata_context=None,
            single_video_config=None,
            output_base_dir=str(out),
        )
        assert path == out
        assert existed_before is False
        assert out.exists()  # created by the call

    def test_reports_pre_existing_directory(self, factory, tmp_path):
        out = tmp_path / "existing"
        out.mkdir()
        _, existed_before = factory.resolve_results_path(
            experiment_id="exp1",
            video_path="v.mp4",
            metadata_context=None,
            single_video_config=None,
            output_base_dir=str(out),
        )
        assert existed_before is True


class TestLoadTrajectoryDataframe:
    def test_missing_file_returns_none(self, factory, tmp_path):
        assert factory.load_trajectory_dataframe(tmp_path / "missing.parquet", "exp1") is None

    def test_valid_parquet_loads(self, factory, tmp_path):
        df = pd.DataFrame({"frame": [0, 1, 2], "x": [1.0, 2.0, 3.0]})
        path = tmp_path / "traj.parquet"
        df.to_parquet(path)
        loaded = factory.load_trajectory_dataframe(path, "exp1")
        assert loaded is not None
        pd.testing.assert_frame_equal(loaded, df)


# ---------------------------------------------------------------------------
# Video context, first frame, arena fallback, cleanup (TASK-087)
# ---------------------------------------------------------------------------


class _Cap:
    """Scripted ``cv2.VideoCapture``; the frame at position ``i`` holds ``i + 1``."""

    def __init__(self, frames=3, *, width=64, height=48, fps=25.0, opened=True):
        self.n_frames = frames
        self.opened = opened
        self.pos = 0
        self.released = False
        self.props = {
            cv2.CAP_PROP_FRAME_WIDTH: width,
            cv2.CAP_PROP_FRAME_HEIGHT: height,
            cv2.CAP_PROP_FPS: fps,
        }
        self.sets: list[tuple[int, float]] = []
        self.last_frame = None

    def isOpened(self):
        return self.opened

    def get(self, prop):
        return self.props.get(prop, 0.0)

    def set(self, prop, value):
        self.sets.append((prop, value))
        if prop == cv2.CAP_PROP_POS_FRAMES:
            self.pos = int(value)
        return True

    def read(self):
        if self.pos >= self.n_frames:
            return False, None
        shape = (self.props[cv2.CAP_PROP_FRAME_HEIGHT], self.props[cv2.CAP_PROP_FRAME_WIDTH], 3)
        frame = np.full(shape, self.pos + 1, dtype=np.uint8)
        self.pos += 1
        self.last_frame = frame
        return True, frame

    def release(self):
        self.released = True


def _use_capture(monkeypatch, cap):
    opened: list[str] = []

    def factory(path):
        opened.append(path)
        return cap

    monkeypatch.setattr(cv2, "VideoCapture", factory)
    return opened


def _clock(monkeypatch, *ticks):
    from zebtrack.core.video import video_context_factory as module

    values = iter(ticks)
    monkeypatch.setattr(module, "time", SimpleNamespace(perf_counter=lambda: next(values)))


class TestCreateVideoContext:
    @pytest.fixture
    def service(self, factory):
        factory.settings = SimpleNamespace(video_processing=SimpleNamespace(fps=12.0))
        return factory

    @pytest.mark.parametrize(
        ("seek_s", "threshold"),
        [(0.0, 120), (0.0099, 120), (0.01, 80), (0.0499, 80), (0.05, 60), (0.2, 60)],
    )
    def test_the_skip_threshold_follows_the_measured_seek_time(
        self, service, monkeypatch, seek_s, threshold
    ):
        _use_capture(monkeypatch, _Cap())
        _clock(monkeypatch, 0.0, seek_s)

        context = service._create_video_context("clip.mp4")

        assert context.skip_threshold == threshold

    def test_the_context_carries_the_geometry_and_a_copy_of_the_first_frame(
        self, service, monkeypatch
    ):
        cap = _Cap(width=64, height=48, fps=25.0)
        opened = _use_capture(monkeypatch, cap)
        _clock(monkeypatch, 0.0, 0.0)

        context = service._create_video_context(Path("v") / "clip.mp4")

        assert opened == [str(Path("v") / "clip.mp4")]
        assert (context.width, context.height, context.fps) == (64, 48, 25.0)
        assert context.path == str(Path("v") / "clip.mp4")
        assert context.cap is cap
        assert context.first_frame is not None
        assert context.first_frame.shape == (48, 64, 3)
        assert int(context.first_frame[0, 0, 0]) == 1  # frame 0 of the video
        assert context.first_frame is not cap.last_frame  # a copy, not the live buffer
        assert cap.sets[-1] == (cv2.CAP_PROP_POS_FRAMES, 0)  # rewound for the worker

    def test_a_zero_fps_header_falls_back_to_the_settings_fps(self, service, monkeypatch):
        _use_capture(monkeypatch, _Cap(fps=0.0))
        _clock(monkeypatch, 0.0, 0.0)
        assert service._create_video_context("clip.mp4").fps == 12.0

    def test_a_video_whose_first_frame_cannot_be_read_still_gets_a_context(
        self, service, monkeypatch
    ):
        _use_capture(monkeypatch, _Cap(frames=0))
        _clock(monkeypatch, 0.0, 0.0)

        context = service._create_video_context("clip.mp4")

        assert context is not None
        assert context.first_frame is None

    def test_an_unopenable_video_yields_no_context(self, service, monkeypatch):
        _use_capture(monkeypatch, _Cap(opened=False))
        assert service._create_video_context("clip.mp4") is None


class TestDisplayInitialFrame:
    def _frames(self, factory):
        factory.ui_event_bus = Mock()
        return factory.ui_event_bus

    def test_a_preloaded_frame_is_shown_without_opening_the_video(self, factory, monkeypatch):
        bus = self._frames(factory)

        def forbidden(_path):
            raise AssertionError("the video must not be opened")

        monkeypatch.setattr(cv2, "VideoCapture", forbidden)
        frame = np.zeros((2, 2, 3), dtype=np.uint8)

        factory.display_initial_frame("clip.mp4", frame=frame)

        (event,) = [c.args[0] for c in bus.publish.call_args_list]
        assert event.type == UIEvents.UI_DISPLAY_FRAME
        assert event.data.frame is frame

    def test_without_a_frame_the_first_one_is_read_and_the_capture_released(
        self, factory, monkeypatch
    ):
        bus = self._frames(factory)
        cap = _Cap()
        opened = _use_capture(monkeypatch, cap)

        factory.display_initial_frame(Path("v") / "clip.mp4")

        assert opened == [str(Path("v") / "clip.mp4")]
        (event,) = [c.args[0] for c in bus.publish.call_args_list]
        assert int(event.data.frame[0, 0, 0]) == 1
        assert cap.released is True

    def test_an_unreadable_video_shows_nothing_but_is_still_released(self, factory, monkeypatch):
        bus = self._frames(factory)
        cap = _Cap(frames=0)
        _use_capture(monkeypatch, cap)

        factory.display_initial_frame("clip.mp4")

        bus.publish.assert_not_called()
        assert cap.released is True

    def test_a_capture_that_raises_is_swallowed(self, factory, monkeypatch):
        bus = self._frames(factory)

        def boom(_path):
            raise RuntimeError("codec")

        monkeypatch.setattr(cv2, "VideoCapture", boom)

        factory.display_initial_frame("clip.mp4")

        bus.publish.assert_not_called()


class TestEnsureArenaPolygonFallback:
    def test_an_existing_polygon_is_returned_untouched(self, factory):
        polygon = [[1, 1], [5, 1], [5, 5]]
        assert factory.ensure_arena_polygon(polygon, None) is polygon

    def test_a_cached_context_gives_the_full_frame_rectangle(self, factory):
        context = SimpleNamespace(width=640, height=480)
        assert factory.ensure_arena_polygon(None, "x.mp4", video_context=context) == [
            [0, 0],
            [640, 0],
            [640, 480],
            [0, 480],
        ]

    def test_nothing_to_measure_gives_none(self, factory):
        assert factory.ensure_arena_polygon(None, None) is None

    def test_the_video_is_probed_when_there_is_no_context(self, factory, monkeypatch):
        cap = _Cap(width=320, height=200)
        _use_capture(monkeypatch, cap)

        polygon = factory.ensure_arena_polygon([], "x.mp4")

        assert polygon == [[0, 0], [320, 0], [320, 200], [0, 200]]
        assert cap.released is True

    def test_an_unopenable_video_gives_none(self, factory, monkeypatch):
        _use_capture(monkeypatch, _Cap(opened=False))
        assert factory.ensure_arena_polygon(None, "x.mp4") is None


class TestResultsDirCleanup:
    def test_a_missing_directory_snapshots_empty_and_cleans_nothing(self, factory, tmp_path):
        missing = tmp_path / "nope"
        assert factory._snapshot_results_dir(missing) == set()
        factory._cleanup_cancelled_results(missing, set())
        assert not missing.exists()

    def test_only_new_items_are_removed_and_a_stubborn_one_does_not_stop_the_rest(
        self, factory, tmp_path, monkeypatch
    ):
        results = tmp_path / "results"
        results.mkdir()
        (results / "old.txt").write_text("keep")
        baseline = factory._snapshot_results_dir(results)
        (results / "locked.txt").write_text("x")
        (results / "new.txt").write_text("x")
        (results / "new_dir").mkdir()
        (results / "new_dir" / "inner.txt").write_text("x")
        original_unlink = Path.unlink

        def unlink(self, missing_ok=False):
            if self.name == "locked.txt":
                raise PermissionError("in use")
            return original_unlink(self, missing_ok=missing_ok)

        monkeypatch.setattr(Path, "unlink", unlink)

        factory._cleanup_cancelled_results(results, baseline)

        assert sorted(p.name for p in results.iterdir()) == ["locked.txt", "old.txt"]

    def test_a_directory_that_ends_up_empty_is_removed_when_nothing_pre_existed(
        self, factory, tmp_path
    ):
        results = tmp_path / "results"
        results.mkdir()
        (results / "new.txt").write_text("x")

        factory._cleanup_cancelled_results(results, set())

        assert not results.exists()


class TestResultsDirectoryThatIsAFile:
    """F2 pragma review: a results path taken by a FILE must not break the run."""

    def test_snapshot_of_a_file_is_empty(self, factory, tmp_path):
        clash = tmp_path / "results"
        clash.write_text("not a folder")

        assert factory._snapshot_results_dir(clash) == set()

    def test_cleanup_of_a_file_leaves_it_alone(self, factory, tmp_path):
        clash = tmp_path / "results"
        clash.write_text("not a folder")

        factory._cleanup_cancelled_results(clash, baseline_items=set())

        assert clash.read_text() == "not a folder"
