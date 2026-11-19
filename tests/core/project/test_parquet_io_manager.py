"""Unit tests for ``zebtrack.core.project.ParquetIOManager``.

The manager is stateless: project state and lookups are injected as callables,
which makes it straightforward to test with ``tmp_path`` and small lambdas.

Focus is the zone-parquet **schema** (column names/order) and the canonical
filenames — both are part of the project's persisted data contract, so they are
pinned explicitly here.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.core.exceptions import ProjectInvalidError
from zebtrack.core.project.parquet_io_manager import ParquetIOManager
from zebtrack.core.project.zone_manager import ZoneManager


@pytest.fixture
def manager():
    return ParquetIOManager()


@pytest.fixture
def zone_data():
    return ZoneData(
        polygon=[[0, 0], [100, 0], [100, 80], [0, 80]],
        roi_polygons=[[[10, 10], [20, 10], [20, 20], [10, 20]]],
        roi_names=["Center"],
    )


class TestZoneParquetFilenames:
    def test_golden_filenames(self):
        names = ParquetIOManager._zone_parquet_filenames("myvideo")
        assert names == {
            "arena": "1_ProcessingArea_myvideo.parquet",
            "rois": "2_AreasOfInterest_myvideo.parquet",
        }


class TestExportZonesToParquet:
    def test_no_project_path_returns_empty(self, manager, zone_data):
        result = manager.export_zones_to_parquet(
            "video.mp4",
            zone_data,
            project_path=None,
            find_video_entry_fn=lambda path: None,
            resolve_results_directory_fn=lambda stem, **kw: None,
        )
        assert result == {}

    def test_exports_arena_and_rois_with_expected_schema(self, manager, zone_data, tmp_path):
        result = manager.export_zones_to_parquet(
            "session/myvideo.mp4",
            zone_data,
            project_path=tmp_path,
            find_video_entry_fn=lambda path: None,
            resolve_results_directory_fn=lambda stem, **kw: tmp_path,
        )
        assert set(result) == {"arena", "rois"}

        arena = pd.read_parquet(result["arena"])
        assert list(arena.columns) == ["x", "y"]
        assert arena.shape == (4, 2)
        assert [list(row) for row in arena.to_numpy()] == zone_data.polygon

        rois = pd.read_parquet(result["rois"])
        assert list(rois.columns) == ["roi_name", "point_index", "x", "y"]
        assert (rois["roi_name"] == "Center").all()
        assert list(rois["point_index"]) == [0, 1, 2, 3]

    def test_filenames_follow_canonical_pattern(self, manager, zone_data, tmp_path):
        result = manager.export_zones_to_parquet(
            "myvideo.mp4",
            zone_data,
            project_path=tmp_path,
            find_video_entry_fn=lambda path: None,
            resolve_results_directory_fn=lambda stem, **kw: tmp_path,
        )
        assert result["arena"].endswith("1_ProcessingArea_myvideo.parquet")
        assert result["rois"].endswith("2_AreasOfInterest_myvideo.parquet")

    def test_polygon_only_exports_arena_only(self, manager, tmp_path):
        zone = ZoneData(polygon=[[0, 0], [10, 0], [10, 10]])
        result = manager.export_zones_to_parquet(
            "v.mp4",
            zone,
            project_path=tmp_path,
            find_video_entry_fn=lambda path: None,
            resolve_results_directory_fn=lambda stem, **kw: tmp_path,
        )
        assert set(result) == {"arena"}

    def test_empty_zone_exports_nothing(self, manager, tmp_path):
        result = manager.export_zones_to_parquet(
            "v.mp4",
            ZoneData(),
            project_path=tmp_path,
            find_video_entry_fn=lambda path: None,
            resolve_results_directory_fn=lambda stem, **kw: tmp_path,
        )
        assert result == {}

    def test_video_entry_metadata_is_passed_to_resolver(self, manager, zone_data, tmp_path):
        captured = {}

        def resolver(stem, *, video_path, metadata):
            captured["metadata"] = metadata
            return tmp_path

        manager.export_zones_to_parquet(
            "v.mp4",
            zone_data,
            project_path=tmp_path,
            find_video_entry_fn=lambda path: {"metadata": {"group": "control"}},
            resolve_results_directory_fn=resolver,
        )
        assert captured["metadata"] == {"group": "control"}


class TestResolveSourceZoneParquets:
    def test_finds_files_in_source_directory(self, manager, tmp_path):
        # Lay down an arena parquet next to the source video.
        (tmp_path / "1_ProcessingArea_clip.parquet").write_bytes(b"x")
        found = ParquetIOManager._resolve_source_zone_parquets(
            source_video_path=tmp_path / "clip.mp4",
            source_entry=None,
            resolve_results_directory_fn=lambda stem, **kw: tmp_path,
            project_path=None,
        )
        assert "arena" in found
        assert found["arena"].endswith("1_ProcessingArea_clip.parquet")

    def test_returns_empty_when_nothing_on_disk(self, manager, tmp_path):
        found = ParquetIOManager._resolve_source_zone_parquets(
            source_video_path=tmp_path / "clip.mp4",
            source_entry=None,
            resolve_results_directory_fn=lambda stem, **kw: tmp_path,
            project_path=None,
        )
        assert found == {}


class TestParquetIOManagerExtended:
    """Test ParquetIOManager export and zone parquet importing."""

    @pytest.fixture
    def manager(self) -> ParquetIOManager:
        return ParquetIOManager()

    def test_import_zone_data_from_video_parquets_no_candidates(
        self, manager: ParquetIOManager, tmp_path: Path
    ):
        imported = manager.import_zone_data_from_video_parquets(
            video_path=tmp_path / "vid.mp4",
            project_path=tmp_path,
            find_video_entry_fn=lambda path: None,
            resolve_results_directory_fn=lambda stem, **kw: tmp_path,
            get_zone_data_fn=lambda **kw: ZoneData(),
            save_zone_data_fn=lambda *args, **kw: None,
        )
        assert imported is False

    def test_import_zone_data_from_video_parquets_success(
        self, manager: ParquetIOManager, tmp_path: Path
    ):
        video_stem = "sample_video"
        video_path = tmp_path / f"{video_stem}.mp4"

        # Create valid arena parquet
        arena_df = pd.DataFrame({"x": [10, 50, 50, 10], "y": [10, 10, 50, 50]})
        arena_file = tmp_path / f"1_ProcessingArea_{video_stem}.parquet"
        arena_df.to_parquet(arena_file)

        # Create valid ROIs parquet
        rois_df = pd.DataFrame(
            {
                "roi_name": ["Center", "Center", "Center", "Center"],
                "point_index": [0, 1, 2, 3],
                "x": [20, 30, 30, 20],
                "y": [20, 20, 30, 30],
            }
        )
        rois_file = tmp_path / f"2_AreasOfInterest_{video_stem}.parquet"
        rois_df.to_parquet(rois_file)

        target_zone_data = ZoneData()
        mock_save = MagicMock()

        imported = manager.import_zone_data_from_video_parquets(
            video_path=video_path,
            project_path=tmp_path,
            find_video_entry_fn=lambda path: {
                "parquet_files": {
                    "arena": str(arena_file),
                    "rois": str(rois_file),
                }
            },
            resolve_results_directory_fn=lambda stem, **kw: tmp_path,
            get_zone_data_fn=lambda **kw: target_zone_data,
            save_zone_data_fn=mock_save,
        )

        assert imported is True
        mock_save.assert_called_once_with(target_zone_data, str(video_path), persist=False)
        assert len(target_zone_data.polygon) == 4
        assert target_zone_data.roi_names == ["Center"]
        assert len(target_zone_data.roi_polygons) == 1

    def test_export_zones_to_parquet_with_multiple_rois(
        self, manager: ParquetIOManager, tmp_path: Path
    ):
        zone_data = ZoneData(
            polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            roi_polygons=[
                [[10, 10], [40, 10], [40, 40], [10, 40]],
                [[60, 60], [90, 60], [90, 90], [60, 90]],
            ],
            roi_names=["ZoneA", "ZoneB"],
        )

        exported = manager.export_zones_to_parquet(
            video_path="session/video123.mp4",
            zone_data=zone_data,
            project_path=tmp_path,
            find_video_entry_fn=lambda path: None,
            resolve_results_directory_fn=lambda stem, **kw: tmp_path,
        )

        assert "arena" in exported
        assert "rois" in exported

        df_arena = pd.read_parquet(exported["arena"])
        assert df_arena.shape == (4, 2)

        df_rois = pd.read_parquet(exported["rois"])
        assert df_rois.shape == (8, 4)
        assert set(df_rois["roi_name"].unique()) == {"ZoneA", "ZoneB"}


# ---------------------------------------------------------------------------
# TASK-087: the wizard import and the zone copy, on real parquet files and a
# real ZoneManager registry.
# ---------------------------------------------------------------------------


PALETTE = [(0, 128, 0), (255, 0, 0), (0, 0, 255), (0, 204, 204), (255, 0, 255), (0, 204, 204)]


def _arena_file(path: Path, points) -> str:
    pd.DataFrame(points, columns=["x", "y"]).to_parquet(path)
    return str(path)


def _rois_file(path: Path, rois: dict[str, list]) -> str:
    rows = [
        {"roi_name": name, "point_index": idx, "x": x, "y": y}
        for name, points in rois.items()
        for idx, (x, y) in reversed(list(enumerate(points)))
    ]
    pd.DataFrame(rows).to_parquet(path)
    return str(path)


class _Registry:
    """project_data + ZoneManager, exposing the callbacks the manager expects."""

    def __init__(self, tmp_path: Path):
        self.project_data: dict = {"project_type": "pre-recorded"}
        self.zones = ZoneManager()
        self.saved: list[int] = []
        self.root = tmp_path / "proj"

    def get_zone_data(self, video_path=None, *, fallback_to_global=True):
        return self.zones.get_zone_data(
            self.project_data, video_path, fallback_to_global=fallback_to_global
        )

    def save_zone_data(self, zone_data, video_path=None, *, persist=True):
        self.zones.save_zone_data(self.project_data, zone_data, video_path)

    def results_dir(self, stem, *, video_path=None, metadata=None):
        return self.root / "Grupo_A" / "Dia_01" / f"Sujeito_{stem}"

    def save_project(self):
        self.saved.append(1)

    def run(self, config, strategy="replace", scanned=None, **overrides):
        kwargs = dict(
            project_data=self.project_data,
            project_path=self.root,
            get_zone_data_fn=self.get_zone_data,
            save_zone_data_fn=self.save_zone_data,
            resolve_results_directory_fn=self.results_dir,
            save_project_fn=self.save_project,
        )
        kwargs.update(overrides)
        return ParquetIOManager().import_parquets_from_wizard(config, strategy, scanned, **kwargs)  # type: ignore[arg-type]


class TestWizardImport:
    def test_replace_imports_arena_and_rois_in_point_order(self, tmp_path):
        video = str(tmp_path / "v.mp4")
        arena = _arena_file(tmp_path / "1.parquet", [[1, 2], [3, 4], [5, 6]])
        rois = _rois_file(
            tmp_path / "2.parquet", {f"r{i}": [[i, 0], [i, 1], [i, 2]] for i in range(7)}
        )
        registry = _Registry(tmp_path)
        scanned = [{"path": video, "parquet_files": {"arena": arena, "rois": rois}}]

        ok = registry.run(
            [{"video": video, "import_arena": True, "import_rois": True}], scanned=scanned
        )

        assert ok is True
        zone = registry.get_zone_data(video, fallback_to_global=False)
        assert zone.polygon == [[1, 2], [3, 4], [5, 6]]
        assert zone.roi_names == [f"r{i}" for i in range(7)]
        assert zone.roi_polygons[4] == [[4, 0], [4, 1], [4, 2]]
        assert zone.roi_colors == [PALETTE[i % 6] for i in range(7)]
        assert registry.saved == [1]

    def test_merge_renames_colliding_rois_without_reusing_a_name(self, tmp_path):
        video = str(tmp_path / "v.mp4")
        rois = _rois_file(tmp_path / "2.parquet", {"toca": [[0, 0]], "novo": [[9, 9]]})
        registry = _Registry(tmp_path)
        registry.save_zone_data(
            ZoneData(roi_polygons=[[[1, 1]], [[2, 2]]], roi_names=["toca", "toca_imported1"]),
            video,
        )

        registry.run(
            [{"video": video, "import_rois": True}],
            "merge",
            [{"path": video, "parquet_files": {"rois": rois}}],
        )

        zone = registry.get_zone_data(video, fallback_to_global=False)
        assert zone.roi_names == ["toca", "toca_imported1", "toca_imported2", "novo"]
        assert zone.roi_polygons == [[[1, 1]], [[2, 2]], [[0, 0]], [[9, 9]]]
        assert zone.roi_colors == PALETTE[:4]

    def test_manual_strategy_falls_back_to_replace(self, tmp_path):
        video = str(tmp_path / "v.mp4")
        rois = _rois_file(tmp_path / "2.parquet", {"novo": [[9, 9]]})
        registry = _Registry(tmp_path)
        registry.save_zone_data(ZoneData(roi_polygons=[[[1, 1]]], roi_names=["old"]), video)

        registry.run(
            [{"video": video, "import_rois": True}],
            "manual",
            [{"path": video, "parquet_files": {"rois": rois}}],
        )

        assert registry.get_zone_data(video, fallback_to_global=False).roi_names == ["novo"]

    def test_trajectory_is_copied_under_the_canonical_name(self, tmp_path):
        video = str(tmp_path / "S1.mp4")
        source = tmp_path / "elsewhere.parquet"
        pd.DataFrame({"frame": [0, 1]}).to_parquet(source)
        registry = _Registry(tmp_path)

        assert registry.run(
            [{"video": video, "import_trajectory": True}],
            scanned=[{"path": video, "parquet_files": {"trajectory": str(source)}}],
        )

        copied = registry.results_dir("S1") / "3_CoordMovimento_S1.parquet"
        assert pd.read_parquet(copied)["frame"].tolist() == [0, 1]

    def test_trajectory_without_project_path_is_not_copied(self, tmp_path):
        video = str(tmp_path / "S1.mp4")
        source = tmp_path / "t.parquet"
        source.write_bytes(b"x")
        registry = _Registry(tmp_path)

        assert registry.run(
            [{"video": video, "import_trajectory": True}],
            scanned=[{"path": video, "parquet_files": {"trajectory": str(source)}}],
            project_path=None,
        )

        assert not registry.root.exists()

    def test_configs_that_import_nothing(self, tmp_path):
        video = str(tmp_path / "v.mp4")
        registry = _Registry(tmp_path)

        ok = registry.run(
            [
                {"import_arena": True},
                {"video": video},
                {"video": video, "import_arena": True},
                {"video": video, "import_arena": True, "import_rois": True},
            ],
            scanned=[{"path": str(tmp_path / "other.mp4"), "parquet_files": {}}],
        )

        assert ok is True
        assert registry.project_data.get("zones_by_video", {}) == {}
        assert registry.saved == [1]

    def test_empty_or_wrong_files_leave_the_zone_empty(self, tmp_path):
        video = str(tmp_path / "v.mp4")
        empty_arena = tmp_path / "1.parquet"
        pd.DataFrame({"x": [], "y": []}).to_parquet(empty_arena)
        bad_rois = tmp_path / "2.parquet"
        pd.DataFrame({"name": ["r"]}).to_parquet(bad_rois)
        registry = _Registry(tmp_path)

        registry.run(
            [{"video": video, "import_arena": True, "import_rois": True}],
            scanned=[
                {"path": video, "parquet_files": {"arena": str(empty_arena), "rois": str(bad_rois)}}
            ],
        )

        zone = registry.get_zone_data(video, fallback_to_global=False)
        assert (zone.polygon, zone.roi_names) == ([], [])

    def test_guard_clauses(self, tmp_path):
        registry = _Registry(tmp_path)

        assert registry.run([{"video": "v"}], project_data={}) is False
        assert registry.run([]) is True
        assert registry.saved == []

    @pytest.mark.parametrize(
        "error", [ProjectInvalidError(message="x"), OSError("disk"), RuntimeError("boom")]
    )
    def test_any_failure_is_reported_as_false(self, tmp_path, error):
        registry = _Registry(tmp_path)

        def failing_save():
            raise error

        assert registry.run([{"video": "v.mp4"}], save_project_fn=failing_save) is False


class TestOwnParquetImportEdges:
    def test_unusable_candidates_import_nothing(self, tmp_path):
        empty_arena = tmp_path / "1.parquet"
        pd.DataFrame({"x": [], "y": []}).to_parquet(empty_arena)
        bad_rois = tmp_path / "2.parquet"
        pd.DataFrame({"roi_name": ["r"]}).to_parquet(bad_rois)
        registry = _Registry(tmp_path)

        imported = ParquetIOManager().import_zone_data_from_video_parquets(
            tmp_path / "v.mp4",
            project_path=None,
            find_video_entry_fn=lambda path: None,
            resolve_results_directory_fn=registry.results_dir,
            get_zone_data_fn=registry.get_zone_data,
            save_zone_data_fn=registry.save_zone_data,
            candidates={"arena": str(empty_arena), "rois": str(bad_rois)},
        )

        assert imported is False
        assert registry.project_data["zones_by_video"] == {}

    def test_rois_only_import_marks_the_registered_entry(self, tmp_path):
        rois = _rois_file(tmp_path / "2.parquet", {"a": [[1, 1]], "b": [[2, 2]]})
        entry: dict = {"path": str(tmp_path / "v.mp4")}
        registry = _Registry(tmp_path)

        imported = ParquetIOManager().import_zone_data_from_video_parquets(
            tmp_path / "v.mp4",
            project_path=None,
            find_video_entry_fn=lambda path: entry,
            resolve_results_directory_fn=registry.results_dir,
            get_zone_data_fn=registry.get_zone_data,
            save_zone_data_fn=registry.save_zone_data,
            candidates={"rois": rois},
        )

        assert imported is True
        assert entry == {"path": entry["path"], "parquet_files": {"rois": rois}, "has_rois": True}
        zone = registry.get_zone_data(tmp_path / "v.mp4", fallback_to_global=False)
        assert (zone.roi_names, zone.roi_colors) == (["a", "b"], PALETTE[:2])


class TestCopyZoneParquets:
    @staticmethod
    def _copy(tmp_path, source, target, *, entries, scan=(), persist=True, saved=None):
        activated: list = []
        return ParquetIOManager().copy_zone_parquet_files(
            source,
            target,
            project_data={},
            project_path=tmp_path / "proj",
            set_active_zone_video_fn=activated.append,
            scan_input_paths_fn=lambda paths: list(scan),
            find_video_entry_fn=lambda path: entries.get(Path(path).name),
            resolve_results_directory_fn=lambda stem, video_path=None, metadata=None: (
                tmp_path / "proj" / f"Grupo_{(metadata or {}).get('group', 'Sem_Grupo')}" / stem
            ),
            save_project_fn=(lambda: saved.append(1)) if saved is not None else (lambda: None),
            persist=persist,
        )

    def test_registered_source_files_are_copied_next_to_the_target_and_into_its_folder(
        self, tmp_path
    ):
        src_dir = tmp_path / "src_results"
        src_dir.mkdir()
        arena = _arena_file(src_dir / "anything.parquet", [[0, 0], [1, 0], [1, 1]])
        source = tmp_path / "src" / "a.mp4"
        target = tmp_path / "dst" / "b.mp4"
        target_entry: dict = {"path": str(target), "group": "G", "metadata": {}}
        entries = {
            "a.mp4": {"parquet_files": {"arena": arena, "rois": None}},
            "b.mp4": target_entry,
        }
        saves: list = []

        copied = self._copy(tmp_path, source, target, entries=entries, saved=saves)

        hierarchical = tmp_path / "proj" / "Grupo_G" / "b" / "1_ProcessingArea_b.parquet"
        assert copied == {"arena": str(hierarchical)}
        assert (tmp_path / "dst" / "1_ProcessingArea_b.parquet").is_file()
        assert hierarchical.is_file()
        assert target_entry["has_arena"] is True and target_entry["zones_finalized"] is False
        assert target_entry["parquet_files"] == {"arena": str(hierarchical)}
        assert saves == [1]

    def test_target_without_group_is_not_copied_into_a_phantom_hierarchy(self, tmp_path):
        arena = _arena_file(tmp_path / "x.parquet", [[0, 0], [1, 0], [1, 1]])
        source, target = tmp_path / "a.mp4", tmp_path / "dst" / "b.mp4"
        scan = [{"parquet_files": {"arena": arena, "rois": None}}]

        copied = self._copy(tmp_path, source, target, entries={}, scan=scan, persist=False)

        assert copied == {"arena": str(tmp_path / "dst" / "1_ProcessingArea_b.parquet")}
        assert not (tmp_path / "proj" / "Grupo_Sem_Grupo").exists()

    def test_missing_source_files_copy_nothing(self, tmp_path):
        source, target = tmp_path / "a.mp4", tmp_path / "b.mp4"
        scan = [{"parquet_files": {"arena": str(tmp_path / "gone.parquet")}}]
        saves: list = []

        assert self._copy(tmp_path, source, target, entries={}, scan=scan, saved=saves) == {}
        assert self._copy(tmp_path, source, target, entries={}, saved=saves) == {}
        assert saves == []

    def test_failed_destination_does_not_stop_the_other_copy(self, tmp_path, monkeypatch):
        """F2: a locked hierarchical folder must not lose the copy next to the video."""
        import zebtrack.core.project.parquet_io_manager as module

        src_dir = tmp_path / "src_results"
        src_dir.mkdir()
        arena = _arena_file(src_dir / "anything.parquet", [[0, 0], [1, 0], [1, 1]])
        source = tmp_path / "src" / "a.mp4"
        target = tmp_path / "dst" / "b.mp4"
        target_entry: dict = {"path": str(target), "group": "G", "metadata": {}}
        entries = {
            "a.mp4": {"parquet_files": {"arena": arena, "rois": None}},
            "b.mp4": target_entry,
        }
        real_copy2 = module.shutil.copy2
        locked = tmp_path / "proj" / "Grupo_G" / "b"

        def copy2(src, dst):
            if Path(dst).parent == locked:
                raise PermissionError("folder locked by OneDrive")
            return real_copy2(src, dst)

        monkeypatch.setattr(module.shutil, "copy2", copy2)

        copied = self._copy(tmp_path, source, target, entries=entries, saved=[])

        sibling = tmp_path / "dst" / "1_ProcessingArea_b.parquet"
        assert copied == {"arena": str(sibling)}
        assert sibling.is_file()
        assert not (locked / "1_ProcessingArea_b.parquet").exists()
        assert target_entry["parquet_files"] == {"arena": str(sibling)}
