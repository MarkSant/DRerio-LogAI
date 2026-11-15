"""
Extended unit tests for ZoneOrchestrationManager in project/zone_orchestration_manager.py.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from zebtrack.core.detection import AquariumData, MultiAquariumZoneData, ZoneData
from zebtrack.core.project.zone_manager import ZoneManager
from zebtrack.core.project.zone_orchestration_manager import ZoneOrchestrationManager


class TestZoneOrchestrationManagerExtended:
    """Test ZoneOrchestrationManager synchronization and persistence workflows."""

    def test_sync_active_zone_video_no_parquets(self, tmp_path: Path):
        save_zone_fn = MagicMock()
        ZoneOrchestrationManager.sync_active_zone_video(
            str(tmp_path / "video.mp4"),
            find_video_entry_fn=MagicMock(return_value=None),
            resolve_results_directory_fn=MagicMock(return_value=tmp_path / "res"),
            load_zones_from_parquet_fn=MagicMock(),
            get_zone_data_fn=MagicMock(return_value=ZoneData()),
            save_zone_data_fn=save_zone_fn,
        )
        save_zone_fn.assert_not_called()

    def test_sync_active_zone_video_with_parquets_syncs_memory(self, tmp_path: Path):
        res_dir = tmp_path / "res"
        res_dir.mkdir()
        (res_dir / "1_ProcessingArea_video.parquet").write_bytes(b"")

        video_path_str = str(tmp_path / "video.mp4")
        video_entry: dict = {"path": video_path_str}
        loaded_zd = ZoneData(polygon=[[0, 0], [10, 0], [10, 10]])
        save_zone_fn = MagicMock()

        ZoneOrchestrationManager.sync_active_zone_video(
            video_path_str,
            find_video_entry_fn=MagicMock(return_value=video_entry),
            resolve_results_directory_fn=MagicMock(return_value=res_dir),
            load_zones_from_parquet_fn=MagicMock(return_value=loaded_zd),
            get_zone_data_fn=MagicMock(return_value=ZoneData()),  # in-memory is empty
            save_zone_data_fn=save_zone_fn,
        )

        save_zone_fn.assert_called_once_with(
            loaded_zd,
            video_path=video_path_str,
            persist=False,
        )
        assert video_entry["has_arena"] is True

    def test_persist_zone_data_with_project_path(self, tmp_path: Path):
        update_flags_fn = MagicMock()
        export_parquet_fn = MagicMock(return_value={"arena": "/path/arena.parquet"})
        video_entry: dict = {"path": "video.mp4"}
        save_proj_fn = MagicMock()

        zd = ZoneData(polygon=[[0, 0], [10, 0], [10, 10]])
        ZoneOrchestrationManager.persist_zone_data(
            zd,
            target_video="video.mp4",
            project_path=tmp_path,
            update_video_zone_flags_fn=update_flags_fn,
            export_zones_to_parquet_fn=export_parquet_fn,
            find_video_entry_fn=MagicMock(return_value=video_entry),
            save_project_fn=save_proj_fn,
        )

        update_flags_fn.assert_called_once_with("video.mp4", zd)
        export_parquet_fn.assert_called_once_with("video.mp4", zd)
        assert video_entry["has_arena"] is True
        save_proj_fn.assert_called_once()

    def test_persist_multi_aquarium_zone_data_empty_aquariums(self, tmp_path: Path):
        save_proj_fn = MagicMock()
        multi_data = MultiAquariumZoneData(aquariums=[])

        ZoneOrchestrationManager.persist_multi_aquarium_zone_data(
            "video.mp4",
            multi_data,
            project_path=tmp_path,
            export_zones_to_parquet_fn=MagicMock(),
            find_video_entry_fn=MagicMock(),
            add_video_batch_fn=MagicMock(),
            save_project_fn=save_proj_fn,
            persist=True,
        )
        save_proj_fn.assert_called_once()

    def test_persist_multi_aquarium_zone_data_with_aquariums(self, tmp_path: Path):
        export_parquet_fn = MagicMock(return_value={"arena": "/path/aq0_arena.parquet"})
        save_proj_fn = MagicMock()
        add_batch_fn = MagicMock()
        video_entry: dict = {"path": "video.mp4"}

        aq0 = AquariumData(id=0, polygon=[[0, 0], [10, 0], [10, 10]])
        multi_data = MultiAquariumZoneData(aquariums=[aq0])

        ZoneOrchestrationManager.persist_multi_aquarium_zone_data(
            "video.mp4",
            multi_data,
            project_path=tmp_path,
            export_zones_to_parquet_fn=export_parquet_fn,
            find_video_entry_fn=MagicMock(return_value=video_entry),
            add_video_batch_fn=add_batch_fn,
            save_project_fn=save_proj_fn,
            persist=True,
        )

        export_parquet_fn.assert_called_once()
        assert video_entry["has_arena"] is True
        save_proj_fn.assert_called_once()


# ---------------------------------------------------------------------------
# TASK-087: the real ZoneManager behind the callbacks, real parquets on disk.
# ---------------------------------------------------------------------------


SQ = [[0, 0], [10, 0], [10, 10], [0, 10]]


class _Zones:
    def __init__(self, project_type="pre-recorded"):
        self.project_data: dict = {"project_type": project_type}
        self.manager = ZoneManager()
        self.saved: list[tuple] = []

    def get(self, video, fallback_to_global=True):
        return self.manager.get_zone_data(
            self.project_data, video, fallback_to_global=fallback_to_global
        )

    def save(self, zone, video_path=None, persist=True):
        self.saved.append((video_path, persist))
        self.manager.save_zone_data(self.project_data, zone, video_path)


def _sync(tmp_path, zones: _Zones, entry, *, loader=ZoneManager.load_zones_from_parquet):
    ZoneOrchestrationManager.sync_active_zone_video(
        str(tmp_path / "v.mp4"),
        find_video_entry_fn=lambda path: entry,
        resolve_results_directory_fn=lambda stem, video_path, metadata: tmp_path / "res",
        load_zones_from_parquet_fn=loader,
        get_zone_data_fn=zones.get,
        save_zone_data_fn=zones.save,
    )


class TestSyncFromDisk:
    @staticmethod
    def _write_rois(tmp_path):
        res = tmp_path / "res"
        res.mkdir()
        pd.DataFrame(
            {"roi_name": ["r", "r", "r"], "point_index": [0, 1, 2], "x": [1, 2, 3], "y": [4, 5, 6]}
        ).to_parquet(res / "2_AreasOfInterest_v.parquet")
        return res

    def test_rois_on_disk_fill_an_empty_memory_and_mark_the_entry(self, tmp_path):
        res = self._write_rois(tmp_path)
        zones = _Zones()
        entry: dict = {"path": str(tmp_path / "v.mp4")}

        _sync(tmp_path, zones, entry)

        assert zones.saved == [(str(tmp_path / "v.mp4"), False)]
        loaded = zones.get(tmp_path / "v.mp4", fallback_to_global=False)
        assert loaded.roi_polygons == [[[1, 4], [2, 5], [3, 6]]]
        assert entry["has_rois"] is True and "has_arena" not in entry
        assert entry["parquet_files"] == {"rois": str(res / "2_AreasOfInterest_v.parquet")}

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "F2-P-004: sync_active_zone_video saves the disk zones over the memory ones "
            "instead of merging them, so an in-memory arena is lost when only the ROI "
            "parquet is on disk (zone_orchestration_manager.py:103)."
        ),
    )
    def test_rois_on_disk_keep_the_arena_already_in_memory(self, tmp_path):
        self._write_rois(tmp_path)
        zones = _Zones()
        zones.save(ZoneData(polygon=SQ), str(tmp_path / "v.mp4"))

        _sync(tmp_path, zones, None)

        loaded = zones.get(tmp_path / "v.mp4", fallback_to_global=False)
        assert (loaded.polygon, len(loaded.roi_polygons)) == (SQ, 1)

    def test_complete_memory_is_not_overwritten_by_disk(self, tmp_path):
        self._write_rois(tmp_path)
        zones = _Zones()
        zones.save(
            ZoneData(polygon=SQ, roi_polygons=[SQ], roi_names=["m"]), str(tmp_path / "v.mp4")
        )

        _sync(tmp_path, zones, None)

        assert len(zones.saved) == 1
        assert zones.get(tmp_path / "v.mp4").roi_names == ["m"]

    def test_unloadable_or_failing_disk_zones_change_nothing(self, tmp_path):
        self._write_rois(tmp_path)
        zones = _Zones()

        _sync(tmp_path, zones, None, loader=lambda info: None)

        def boom(info):
            raise RuntimeError("bad parquet")

        _sync(tmp_path, zones, None, loader=boom)
        assert zones.saved == []


class TestPersistence:
    def test_export_failure_still_saves_the_project(self, tmp_path):
        flags: list = []
        saves: list[int] = []

        def failing_export(video, zone):
            raise OSError("disk full")

        ZoneOrchestrationManager.persist_zone_data(
            ZoneData(polygon=SQ),
            "v.mp4",
            tmp_path,
            update_video_zone_flags_fn=lambda video, zone: flags.append(video),
            export_zones_to_parquet_fn=failing_export,
            find_video_entry_fn=lambda path: pytest.fail("not reached"),
            save_project_fn=lambda: saves.append(1),
        )

        assert flags == ["v.mp4"] and saves == [1]

    def test_export_marks_the_entry_and_in_memory_saves_skip_disk(self, tmp_path):
        entry: dict = {"path": "v.mp4"}
        saves: list[int] = []
        common = dict(
            update_video_zone_flags_fn=lambda video, zone: None,
            export_zones_to_parquet_fn=lambda video, zone: {"rois": "r.parquet"},
            find_video_entry_fn=lambda path: entry,
            save_project_fn=lambda: saves.append(1),
        )

        ZoneOrchestrationManager.persist_zone_data(ZoneData(), "v.mp4", tmp_path, **common)  # type: ignore[arg-type]
        ZoneOrchestrationManager.persist_zone_data(ZoneData(), None, None, **common)  # type: ignore[arg-type]
        ZoneOrchestrationManager.persist_zone_data(ZoneData(), None, tmp_path, **common)  # type: ignore[arg-type]

        assert entry == {
            "path": "v.mp4",
            "parquet_files": {"rois": "r.parquet"},
            "has_rois": True,
        }
        assert saves == [1, 1]

    def test_unregistered_multi_aquarium_video_is_added_then_marked(self, tmp_path):
        added: list = []
        registered: dict = {}
        saves: list[int] = []
        data = MultiAquariumZoneData(
            aquariums=[AquariumData(id=0, polygon=SQ), AquariumData(id=1, roi_polygons=[SQ])]
        )

        def add(videos, save_project):
            added.append((videos, save_project))
            registered["entry"] = dict(videos[0])

        ZoneOrchestrationManager.persist_multi_aquarium_zone_data(
            str(tmp_path / "v.mp4"),
            data,
            tmp_path,
            export_zones_to_parquet_fn=lambda video, zone: {},
            find_video_entry_fn=lambda path: registered.get("entry"),
            add_video_batch_fn=add,
            save_project_fn=lambda: saves.append(1),
            persist=False,
        )

        assert added == [
            (
                [
                    {
                        "path": (tmp_path / "v.mp4").as_posix(),
                        "status": "pending",
                        "has_arena": True,
                        "has_rois": True,
                        "is_multi_aquarium": True,
                        "num_aquariums": 2,
                    }
                ],
                False,
            )
        ]
        assert registered["entry"]["zones_finalized"] is False
        assert "parquet_files" not in registered["entry"]
        assert saves == []

    def test_multi_aquarium_export_failure_still_persists(self, tmp_path):
        saves: list[int] = []

        def failing_export(video, zone):
            raise ValueError("bad")

        ZoneOrchestrationManager.persist_multi_aquarium_zone_data(
            "v.mp4",
            MultiAquariumZoneData(aquariums=[AquariumData(id=0, polygon=SQ)]),
            tmp_path,
            export_zones_to_parquet_fn=failing_export,
            find_video_entry_fn=lambda path: None,
            add_video_batch_fn=lambda videos, save_project: None,
            save_project_fn=lambda: saves.append(1),
        )

        assert saves == [1]


class TestFlagSyncAndClear:
    def test_flags_follow_the_multi_aquarium_registry(self):
        entries = [
            {"path": "a.mp4"},
            {"path": "b.mp4", "has_arena": True, "has_rois": True},
            {"path": "c.mp4"},
            {"path": ""},
        ]
        registry = {
            "a.mp4": MultiAquariumZoneData(
                aquariums=[AquariumData(id=0, polygon=[[0, 0], [1, 1]], roi_polygons=[SQ])]
            ),
            "b.mp4": MultiAquariumZoneData(aquariums=[AquariumData(id=0, polygon=SQ)]),
            "c.mp4": MultiAquariumZoneData(aquariums=[AquariumData(id=0, polygon=SQ)]),
        }

        ZoneOrchestrationManager.sync_multi_aquarium_flags(
            {},
            iter_project_videos_fn=lambda: [({}, e) for e in entries],
            get_multi_aquarium_zone_data_fn=registry.get,
        )

        assert entries[0] == {"path": "a.mp4", "has_rois": True}
        assert entries[1] == {"path": "b.mp4", "has_arena": True, "has_rois": True}
        assert entries[2] == {"path": "c.mp4", "has_arena": True}

    def test_clearing_the_active_video_empties_the_global(self, tmp_path):
        zones = _Zones(project_type="live")
        video = str(tmp_path / "v.mp4")
        zones.save(ZoneData(polygon=SQ), video)
        saves: list[int] = []

        ZoneOrchestrationManager.clear_zone_data_for_video(
            video,
            zones.project_data,
            get_active_zone_video_fn=lambda: ZoneManager.normalize_video_path(video),
            save_project_fn=lambda: saves.append(1),
        )

        assert zones.project_data["zones_by_video"] == {}
        assert zones.project_data["detection_zones"] == ZoneManager.zone_data_to_dict(None)
        assert zones.project_data["has_arena"] is False
        assert saves == [1]
