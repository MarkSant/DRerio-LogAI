"""Tests for VideoManager helpers without filesystem scanning."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from zebtrack.core.project.video_manager import VideoManager


def test_normalize_path_handles_none():
    assert VideoManager.normalize_path(None) is None


def test_normalize_path_lowercase_and_slashes(tmp_path):
    path = tmp_path / "Some" / "Video.MP4"
    normalized = VideoManager.normalize_path(path)

    assert normalized is not None
    assert normalized.endswith("/some/video.mp4")


def test_refresh_complete_flag():
    entry = {"has_arena": True, "has_rois": True, "has_trajectory": False}
    VideoManager.refresh_complete_flag(entry)
    assert entry["has_complete_data"] is False

    entry["has_trajectory"] = True
    VideoManager.refresh_complete_flag(entry)
    assert entry["has_complete_data"] is True


def test_find_video_entry_by_path():
    project_data = {"batches": [{"videos": [{"path": "/data/A.MP4"}, {"path": "/data/B.MP4"}]}]}

    entry = VideoManager.find_video_entry(project_data, path="/data/a.mp4")
    assert entry is not None
    assert entry["path"] == "/data/A.MP4"


def test_find_video_entry_by_experiment_id():
    project_data = {"batches": [{"videos": [{"path": "/data/exp1.mp4"}]}]}

    entry = VideoManager.find_video_entry(project_data, experiment_id="exp1")
    assert entry is not None
    assert entry["path"] == "/data/exp1.mp4"


def _longitudinal_project():
    """Same subject filmed on two days — one basename, two entries."""
    return {
        "batches": [
            {
                "videos": [
                    {
                        "path": "/vids/Dia_1/CECT_4/CECT_4.mp4",
                        "metadata": {"group": "CEC", "day": "Day01", "subject": "S04"},
                    },
                    {
                        "path": "/vids/Dia_2/CECT_4/CECT_4.mp4",
                        "metadata": {"group": "CEC", "day": "Day02", "subject": "S04"},
                    },
                ]
            }
        ]
    }


def test_find_video_entry_path_wins_over_repeated_experiment_id():
    """A matching path must beat the stem fallback, even for a later batch entry.

    Longitudinal projects reuse the video basename across days, so the stem is
    ambiguous. Resolving day 2 to day 1's entry is what sent day 2's summary into
    day 1's results folder and overwrote it.
    """
    entry = VideoManager.find_video_entry(
        _longitudinal_project(),
        path="/vids/Dia_2/CECT_4/CECT_4.mp4",
        experiment_id="CECT_4",
    )

    assert entry is not None
    assert entry["metadata"]["day"] == "Day02"


def test_find_video_entry_first_day_still_resolves_with_experiment_id():
    entry = VideoManager.find_video_entry(
        _longitudinal_project(),
        path="/vids/Dia_1/CECT_4/CECT_4.mp4",
        experiment_id="CECT_4",
    )

    assert entry is not None
    assert entry["metadata"]["day"] == "Day01"


def test_find_video_entry_falls_back_to_stem_when_path_unknown():
    """Unregistered paths (single-video and live flows) still use the stem."""
    entry = VideoManager.find_video_entry(
        _longitudinal_project(),
        path="/somewhere/else/CECT_4.mp4",
        experiment_id="CECT_4",
    )

    assert entry is not None
    assert entry["metadata"]["day"] == "Day01"


def test_find_video_entry_returns_none_when_nothing_matches():
    entry = VideoManager.find_video_entry(
        _longitudinal_project(),
        path="/somewhere/else/OTHER.mp4",
        experiment_id="OTHER",
    )

    assert entry is None


def test_get_next_video():
    project_data = {
        "batches": [
            {
                "videos": [
                    {"path": "one.mp4", "status": "processed"},
                    {"path": "two.mp4", "status": "pending"},
                ]
            }
        ]
    }

    assert VideoManager.get_next_video(project_data) == "two.mp4"


def test_get_all_videos_excludes_cancelled_live_session(tmp_path):
    session_dir = tmp_path / "live_20260723_100000"
    session_dir.mkdir()
    cancelled_video = session_dir / "live_recording.mp4"
    cancelled_video.touch()
    (session_dir / ".cancelled").touch()
    valid_video = tmp_path / "recorded.mp4"
    valid_video.touch()
    project_data = {
        "batches": [{"videos": [{"path": str(cancelled_video)}, {"path": str(valid_video)}]}]
    }

    videos = VideoManager.get_all_videos(project_data)

    assert videos == [{"path": str(valid_video)}]


def test_remove_video_entry(tmp_path):
    target = str(tmp_path / "video.mp4")
    project_data = {
        "batches": [
            {"videos": [{"path": target}, {"path": "other.mp4"}]},
            {"videos": [{"path": target}]},
        ]
    }

    cleared = []

    def _clear(path: str) -> None:
        cleared.append(path)

    changed = VideoManager.remove_video_entry(
        project_data,
        video_path=Path(target),
        video_entry={"path": target},
        clear_zones_callback=_clear,
    )

    assert changed is True
    assert cleared == [target]
    assert all(target != v.get("path") for b in project_data["batches"] for v in b["videos"])


def test_scan_input_paths_detects_parquet(tmp_path):
    video = tmp_path / "sample.mp4"
    video.write_bytes(b"x")

    arena = tmp_path / "1_ProcessingArea_sample.parquet"
    rois = tmp_path / "2_AreasOfInterest_sample.parquet"
    trajectory = tmp_path / "3_CoordMovimento_sample.parquet"
    arena.write_text("arena")
    rois.write_text("rois")
    trajectory.write_text("traj")

    results = VideoManager.scan_input_paths([str(tmp_path)])

    assert len(results) == 1
    info = results[0]
    assert info["has_arena"] is True
    assert info["has_rois"] is True
    assert info["has_trajectory"] is True
    assert info["has_complete_data"] is True
    assert info["has_data"] is True


def test_scan_input_paths_missing_path(tmp_path):
    missing = tmp_path / "does_not_exist"
    results = VideoManager.scan_input_paths([str(missing)])
    assert results == []


class TestVideoManagerScanInputPaths:
    """Test VideoManager.scan_input_paths for various inputs."""

    def test_scan_empty_list(self):
        result = VideoManager.scan_input_paths([])
        assert result == []

    def test_scan_nonexistent_path_ignored(self, tmp_path: Path):
        result = VideoManager.scan_input_paths([str(tmp_path / "nope.mp4")])
        assert result == []

    def test_scan_non_video_file_ignored(self, tmp_path: Path):
        txt = tmp_path / "doc.txt"
        txt.write_text("data")
        result = VideoManager.scan_input_paths([str(txt)])
        assert result == []

    def test_scan_mp4_file(self, tmp_path: Path):
        video = tmp_path / "sample.mp4"
        video.write_bytes(b"\x00" * 100)
        result = VideoManager.scan_input_paths([str(video)])
        assert len(result) == 1
        assert result[0]["path"].endswith("sample.mp4")
        assert result[0]["has_arena"] is False
        assert result[0]["has_rois"] is False
        assert result[0]["has_trajectory"] is False
        assert result[0]["has_complete_data"] is False
        assert result[0]["has_data"] is False

    def test_scan_mp4_with_parquet_files(self, tmp_path: Path):
        video = tmp_path / "my_video.mp4"
        video.write_bytes(b"\x00" * 100)
        (tmp_path / "1_ProcessingArea_my_video.parquet").write_bytes(b"")
        (tmp_path / "2_AreasOfInterest_my_video.parquet").write_bytes(b"")
        (tmp_path / "3_CoordMovimento_my_video.parquet").write_bytes(b"")
        result = VideoManager.scan_input_paths([str(video)])
        assert result[0]["has_arena"] is True
        assert result[0]["has_rois"] is True
        assert result[0]["has_trajectory"] is True
        assert result[0]["has_complete_data"] is True
        assert result[0]["has_data"] is True

    def test_scan_directory_finds_videos(self, tmp_path: Path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "clip1.mp4").write_bytes(b"\x00")
        (sub / "clip2.avi").write_bytes(b"\x00")
        result = VideoManager.scan_input_paths([str(tmp_path)])
        assert len(result) == 2
        paths = {r["path"] for r in result}
        assert any("clip1.mp4" in p for p in paths)
        assert any("clip2.avi" in p for p in paths)

    def test_scan_with_recording_metadata_json(self, tmp_path: Path):
        import json

        video = tmp_path / "vid.mp4"
        video.write_bytes(b"\x00")
        meta_file = tmp_path / "_recording_metadata.json"
        meta_file.write_text(json.dumps({"session_id": "s1"}))
        result = VideoManager.scan_input_paths([str(video)])
        assert result[0].get("metadata") == {"session_id": "s1"}


class TestVideoManagerClearCache:
    """Test VideoManager cache management."""

    def test_clear_scan_cache_runs_without_error(self):
        VideoManager.clear_scan_cache()  # Should not raise


# ---------------------------------------------------------------------------
# TASK-087: scan cache, batches and statuses on real folders.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=False)
def fresh_cache():
    VideoManager.clear_scan_cache()
    yield
    VideoManager.clear_scan_cache()


class TestScanDetails:
    def test_zone_files_in_the_results_subfolder_and_a_corrupt_metadata_file(
        self, tmp_path, fresh_cache
    ):
        video = tmp_path / "S1.mp4"
        video.write_bytes(b"v")
        results = tmp_path / "S1_results"
        results.mkdir()
        (results / "2_AreasOfInterest_S1.parquet").write_bytes(b"r")
        (tmp_path / "1_ProcessingArea_S1.parquet").write_bytes(b"a")
        (tmp_path / "_recording_metadata.json").write_text("{not json", encoding="utf-8")

        (result,) = VideoManager.scan_input_paths([str(video)])

        assert result["parquet_files"] == {
            "arena": str(tmp_path / "1_ProcessingArea_S1.parquet"),
            "rois": str(results / "2_AreasOfInterest_S1.parquet"),
            "trajectory": None,
        }
        assert (result["has_complete_data"], result["has_data"]) == (False, False)
        assert "metadata" not in result

    def test_empty_metadata_file_adds_nothing(self, tmp_path, fresh_cache):
        video = tmp_path / "S1.MOV"
        video.write_bytes(b"v")
        (tmp_path / "_recording_metadata.json").write_text("{}", encoding="utf-8")

        (result,) = VideoManager.scan_input_paths([str(tmp_path)])

        assert result["path"] == video.as_posix()
        assert "metadata" not in result

    def test_directory_cache_is_invalidated_when_the_folder_changes(self, tmp_path, fresh_cache):
        (tmp_path / "a.mp4").write_bytes(b"a")
        first = VideoManager._scan_directory_for_videos(tmp_path, {".mp4"})
        cached = VideoManager._scan_directory_for_videos(str(tmp_path), {".mp4"})
        (tmp_path / "b.mp4").write_bytes(b"b")
        signature = VideoManager._compute_path_signature(tmp_path)
        key = str(tmp_path.resolve())
        VideoManager._scan_cache.set(key, (("stale", 0), [str(tmp_path / "a.mp4")]))

        refreshed = VideoManager._scan_directory_for_videos(tmp_path, {".mp4"})

        assert [p.name for p in first] == [p.name for p in cached] == ["a.mp4"]
        assert sorted(p.name for p in refreshed) == ["a.mp4", "b.mp4"]
        assert VideoManager._scan_cache.get(key)[0] == signature

    def test_file_entry_cache_and_non_video_files(self, tmp_path, fresh_cache):
        video = tmp_path / "a.avi"
        video.write_bytes(b"a")

        assert VideoManager._scan_file_entry(tmp_path / "notes.txt", {".avi"}) == []
        assert VideoManager._scan_file_entry(str(video), {".avi"}) == [video]
        VideoManager._scan_cache.set(str(video.resolve()), (("stale", 0), ["other.avi"]))
        assert VideoManager._scan_file_entry(video, {".avi"}) == [video]
        assert VideoManager._scan_file_entry(video, {".avi"}) == [video]

    def test_signature_of_a_missing_path_and_targeted_cache_clear(self, tmp_path, fresh_cache):
        assert VideoManager._compute_path_signature(tmp_path / "gone") == ("missing", 0)
        VideoManager._scan_directory_for_videos(tmp_path, {".mp4"})
        key = str(tmp_path.resolve())
        assert VideoManager._scan_cache.get(key) is not None

        VideoManager.clear_scan_cache(str(tmp_path))

        assert VideoManager._scan_cache.get(key) is None

    def test_unreadable_directory_degrades_to_an_empty_scan(
        self, tmp_path, fresh_cache, monkeypatch
    ):
        def denied(self, pattern):
            raise PermissionError("denied")

        monkeypatch.setattr(Path, "rglob", denied)

        assert VideoManager._scan_directory_for_videos(tmp_path, {".mp4"}) == []


class TestVideoBatches:
    def test_strings_and_dicts_become_entries_with_compact_metadata(self, tmp_path):
        video = tmp_path / "a.mp4"
        video.write_bytes(b"abc")
        project: dict = {}
        saves: list[int] = []

        added = VideoManager.add_video_batch(
            project,
            [
                str(tmp_path / "plain.mp4"),
                {
                    "path": video,
                    "has_complete_data": True,
                    "has_arena": 1,
                    "group": "A",
                    "day": 0,
                    "subject": "",
                    "is_multi_subject": False,
                    "metadata": {"note": "", "keep": "x", "none": None},
                },
            ],
            save_callback=lambda: saves.append(1),
        )

        assert added == 2
        plain, rich = project["batches"][0]["videos"]
        assert plain == {
            "path": str(tmp_path / "plain.mp4"),
            "sha256": "",
            "status": "pending",
            "has_arena": False,
            "has_rois": False,
            "has_trajectory": False,
            "has_complete_data": False,
            "zones_finalized": False,
        }
        assert rich["path"] == video.as_posix()
        assert rich["sha256"] == hashlib.sha256(b"abc").hexdigest()
        assert rich["status"] == "processed"
        assert rich["has_arena"] is True and rich["has_complete_data"] is True
        assert rich["metadata"] == {"keep": "x", "group": "A", "day": 0, "is_multi_subject": False}
        assert saves == [1]
        assert VideoManager.add_video_batch(project, []) == 0

    def test_status_updates_and_resets(self, tmp_path):
        project = {
            "batches": [
                {"videos": [{"path": "C:/v/a.mp4", "status": "pending"}]},
                {"videos": [{"path": "C:/v/b.mp4", "status": "processed"}]},
            ]
        }
        saves: list[int] = []

        assert VideoManager.update_video_status(
            project, "C:/v/b.mp4", "failed", save_callback=lambda: saves.append(1)
        )
        assert VideoManager.update_video_status(project, "C:/v/zz.mp4", "failed") is False
        assert VideoManager.reset_all_video_statuses(project, save_callback=lambda: saves.append(2))
        assert VideoManager.reset_all_video_statuses(project) is False

        assert [v["status"] for _b, v in VideoManager.iter_project_videos(project)] == [
            "pending",
            "pending",
        ]
        assert saves == [1, 2]

    def test_next_video_skips_processed_and_cancelled(self, tmp_path):
        session = tmp_path / "session"
        session.mkdir()
        (session / ".cancelled").write_text("")
        project = {
            "batches": [
                {
                    "videos": [
                        {"path": "a.mp4", "status": "processed"},
                        {"path": "b.mp4", "status": "pending", "cancelled": True},
                        {"path": str(session / "c.mp4"), "status": "pending"},
                        {"status": "processed", "path": ""},
                        {"path": "d.mp4", "status": "pending"},
                    ]
                }
            ]
        }

        assert VideoManager.get_next_video(project) == "d.mp4"
        assert VideoManager.get_next_video({"batches": []}) is None
        assert [v["path"] for v in VideoManager.get_all_videos(project)] == ["a.mp4", "", "d.mp4"]

    def test_lookup_without_project_or_with_pathless_entries(self):
        project = {"batches": [{"videos": [{"status": "pending"}, {"path": "C:/x/CECT_4.mp4"}]}]}

        assert VideoManager.find_video_entry({}, path="a.mp4") is None
        assert VideoManager.find_video_entry(
            project, path="C:/y/CECT_4.mp4", experiment_id="CECT_4"
        ) == {"path": "C:/x/CECT_4.mp4"}
