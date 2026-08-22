"""Tests for VideoManager helpers without filesystem scanning."""

from __future__ import annotations

from pathlib import Path

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
