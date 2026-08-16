"""
Extended unit tests for ZoneOrchestrationManager in project/zone_orchestration_manager.py.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from zebtrack.core.detection import AquariumData, MultiAquariumZoneData, ZoneData
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
