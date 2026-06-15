"""Unit tests for ``zebtrack.core.video.VideoContextFactoryMixin``.

The mixin bundles small, well-isolated helpers for frame seeking, arena-polygon
fallback, results-directory bookkeeping and trajectory loading. Most are pure
logic or filesystem operations, so they are tested directly on a bare mixin
instance with attributes injected as needed (``ui_event_bus``, ``project_manager``).

``cv2.VideoCapture`` is stood in with ``Mock``; the filesystem helpers use
``tmp_path``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from zebtrack.core.video.video_context_factory import VideoContextFactoryMixin


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
