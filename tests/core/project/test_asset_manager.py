"""Basic tests for AssetManager utilities and asset removal logic."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.core.project.asset_manager import ZONE_PARQUET_PREFIXES, AssetManager
from zebtrack.core.project.zone_manager import ZoneManager


def test_slugify_normalizes_text():
    assert AssetManager._slugify("Meu Template Ç") == "meu-template-c"
    assert AssetManager._slugify("  ###  ") == "template"


def test_list_roi_templates_aggregates_and_sorts(monkeypatch):
    manager = AssetManager()
    manager.roi_template_manager = MagicMock()
    manager.roi_template_manager.list_global_templates.return_value = [
        {"name": "Global B"},
        {"name": "Global A"},
    ]

    project_data = {
        "roi_templates": [
            {"name": "Project Z", "location": "project"},
            {"name": "Project A"},
        ]
    }

    result = manager.list_roi_templates(project_data, include_global=True)

    assert [item["name"] for item in result][:2] == ["Project A", "Project Z"]
    assert any(item.get("location") == "global" for item in result)


def test_resolve_roi_template_entry():
    project_data = {"roi_templates": [{"name": "Template A"}, {"name": "Template B"}]}
    idx, entry = AssetManager._resolve_roi_template_entry(project_data, "Template B")
    assert idx == 1
    assert entry is not None
    assert entry["name"] == "Template B"

    idx, entry = AssetManager._resolve_roi_template_entry(project_data, "Missing")
    assert idx is None
    assert entry is None


def test_get_analysis_profiles_default():
    manager = AssetManager()
    project_data: dict[str, Any] = {}

    profiles = manager.get_analysis_profiles(project_data)

    assert profiles[0]["name"] == "default"
    assert project_data["analysis_profiles"] == profiles


def test_resolve_analysis_profile_matches_synonym():
    manager = AssetManager()
    project_data = {
        "analysis_profiles": [
            {"name": "fallback", "criteria": {}},
            {"name": "subject_profile", "criteria": {"subject": ["alpha"]}},
        ]
    }

    selected = manager.resolve_analysis_profile(project_data, {"animal": "Alpha"})
    assert selected["name"] == "subject_profile"


def test_profile_matches_with_list_metadata():
    manager = AssetManager()
    criteria = {"day": ["d1", "d2"]}
    metadata = {"day_label": ["D2", "D3"]}

    assert manager._profile_matches(criteria, metadata) is True


def test_video_has_asset():
    manager = AssetManager()
    video_entry = {
        "has_arena": True,
        "has_rois": False,
        "has_trajectory": False,
        "has_summary": False,
        "path": "video.mp4",
        "parquet_files": {"rois": "rois.parquet", "summary_excel": "sum.xlsx"},
    }

    assert manager.video_has_asset(video_entry, "arena") is True
    assert manager.video_has_asset(video_entry, "rois") is True
    assert manager.video_has_asset(video_entry, "trajectory") is False
    assert manager.video_has_asset(video_entry, "summary") is True
    assert manager.video_has_asset(video_entry, "video") is True

    with pytest.raises(ValueError, match="desconhecido"):
        manager.video_has_asset(video_entry, cast(Any, "unknown"))


def test_can_remove_asset_summary_dependency():
    manager = AssetManager()
    video_entry = {"has_summary": True, "parquet_files": {"summary": "sum.parquet"}}

    can_remove, message = manager.can_remove_asset(video_entry, "arena")
    assert can_remove is False
    assert "Remove the reports and summaries" in (message or "")


def test_remove_summary_asset(monkeypatch, tmp_path):
    manager = AssetManager()

    delete_calls = []

    def _delete(path: Path | str) -> bool:
        delete_calls.append(str(path))
        return True

    monkeypatch.setattr(manager, "delete_file_if_exists", _delete)

    video_entry = {
        "has_summary": True,
        "parquet_files": {
            "summary": str(tmp_path / "sum.parquet"),
            "summary_excel": str(tmp_path / "sum.xlsx"),
            "report_docx": str(tmp_path / "sum.docx"),
        },
    }

    changed = manager.remove_summary_asset(video_entry, delete_files=True)

    assert changed is True
    assert video_entry["has_summary"] is False
    assert video_entry["parquet_files"] == {}
    assert len(delete_calls) == 3


def test_remove_trajectory_asset(monkeypatch, tmp_path):
    manager = AssetManager()

    monkeypatch.setattr(manager, "delete_file_if_exists", lambda _: True)

    video_entry = {
        "has_arena": True,
        "has_rois": True,
        "has_trajectory": True,
        "has_complete_data": True,
        "parquet_files": {"trajectory": str(tmp_path / "traj.parquet")},
    }

    changed = manager.remove_trajectory_asset(video_entry, delete_files=True)

    assert changed is True
    assert video_entry["has_trajectory"] is False
    assert video_entry["has_complete_data"] is False
    parquet_files = cast(dict[str, str], video_entry["parquet_files"])
    assert "trajectory" not in parquet_files


def test_delete_file_if_exists(tmp_path):
    manager = AssetManager()
    target = tmp_path / "file.txt"
    target.write_text("data")

    assert manager.delete_file_if_exists(target) is True
    assert not target.exists()

    assert manager.delete_file_if_exists(target) is False


class TestAssetManagerExtended:
    def test_slugify(self):
        assert AssetManager._slugify("Standard 2x2 Arena") == "standard-2x2-arena"
        assert AssetManager._slugify("Área Central (10cm)") == "area-central-10cm"
        assert AssetManager._slugify("---Test---") == "test"
        assert AssetManager._slugify("") == "template"

    def test_resolve_roi_template_entry(self):
        project_data = {
            "roi_templates": [
                {"name": "TemplateA", "file": "tmpl_a.json"},
                {"name": "TemplateB", "file": "tmpl_b.json"},
                "corrupted_entry",
            ]
        }
        idx, entry = AssetManager._resolve_roi_template_entry(project_data, "TemplateB")
        assert idx == 1
        assert entry is not None
        assert entry["file"] == "tmpl_b.json"

        idx_none, entry_none = AssetManager._resolve_roi_template_entry(project_data, "NonExistent")
        assert idx_none is None
        assert entry_none is None

    def test_list_roi_templates(self):
        manager = AssetManager()
        manager.roi_template_manager = MagicMock()
        manager.roi_template_manager.list_global_templates.return_value = [
            {"name": "GlobalTemplate", "file": "global.json"}
        ]

        project_data = {"roi_templates": [{"name": "ProjectTemplate", "file": "proj.json"}]}

        templates = manager.list_roi_templates(project_data, include_global=True)
        assert len(templates) == 2
        assert templates[0]["name"] == "ProjectTemplate"
        assert templates[0]["location"] == "project"
        assert templates[1]["name"] == "GlobalTemplate"
        assert templates[1]["location"] == "global"

    def test_profile_synonyms_structure(self):
        synonyms = AssetManager._PROFILE_SYNONYMS
        assert "group" in synonyms
        assert "day" in synonyms
        assert "subject" in synonyms
        assert "experiment_id" in synonyms
        assert "cobaia" in synonyms["subject"]
        assert "video_name" in synonyms["experiment_id"]

    def test_save_roi_template_validations(self):
        manager = AssetManager()
        project_data: dict = {}

        # 1. Empty name
        with pytest.raises(ValueError, match="cannot be empty"):
            manager.save_roi_template(project_data, "/proj", "", MagicMock(), MagicMock())

        # 2. None zone_data
        with pytest.raises(ValueError, match="Invalid zone data"):
            manager.save_roi_template(
                project_data,
                "/proj",
                "Name",
                None,  # type: ignore[arg-type]
                MagicMock(),
            )

        # 3. Neither arena nor ROIs
        mock_zones = MagicMock()
        with pytest.raises(ValueError, match="Select at least"):
            manager.save_roi_template(
                project_data,
                "/proj",
                "Name",
                mock_zones,
                MagicMock(),
                save_arena=False,
                save_rois=False,
            )

        # 4. No project path when saving to project
        with pytest.raises(ValueError, match="no project loaded"):
            manager.save_roi_template(
                project_data, "", "Name", mock_zones, MagicMock(), save_location="project"
            )

    def test_import_roi_template_file_not_found(self, tmp_path: Path):
        manager = AssetManager()
        project_data: dict = {}
        missing_file = tmp_path / "nonexistent_tmpl.json"

        with pytest.raises(FileNotFoundError):
            manager.import_roi_template(
                project_data=project_data,
                project_path=tmp_path,
                file_path=missing_file,
                zone_data_from_dict_fn=MagicMock(),
                zone_data_to_dict_fn=MagicMock(),
            )

    def test_load_roi_template_missing_file_in_project(self, tmp_path: Path):
        manager = AssetManager()
        project_data = {
            "roi_templates": [{"name": "TemplateMissing", "file": "roi_templates/missing.json"}]
        }

        with pytest.raises(FileNotFoundError):
            manager.load_roi_template(
                project_data=project_data,
                project_path=tmp_path,
                name="TemplateMissing",
                zone_data_from_dict_fn=MagicMock(),
            )


class TestAssetManagerExtended2:
    def test_profile_synonyms(self):
        assert "group" in AssetManager._PROFILE_SYNONYMS
        assert "day" in AssetManager._PROFILE_SYNONYMS
        assert "subject" in AssetManager._PROFILE_SYNONYMS
        assert "experiment_id" in AssetManager._PROFILE_SYNONYMS

    def test_slugify(self):
        assert AssetManager._slugify("My Test Template!") == "my-test-template"
        assert AssetManager._slugify("Arena_1-TopDown") == "arena_1-topdown"
        assert AssetManager._slugify("   ") == "template"
        assert AssetManager._slugify("Água & Peixe") == "agua-peixe"

    def test_slugify_numbers_and_underscores(self):
        assert AssetManager._slugify("Batch_123_456") == "batch_123_456"
        assert AssetManager._slugify("---test---") == "test"


class TestAssetManagerExtended4:
    def test_slugify_string(self):
        assert AssetManager._slugify("Simple Name") == "simple-name"
        assert AssetManager._slugify("Ação & Reação 123") == "acao-reacao-123"
        assert AssetManager._slugify("---") == "template"
        assert AssetManager._slugify("") == "template"

    def test_list_roi_templates_project_and_global_sorting(self):
        manager = AssetManager()
        manager.roi_template_manager = MagicMock()
        manager.roi_template_manager.list_global_templates.return_value = [
            {"name": "GlobalTemplateZ"},
            {"name": "GlobalTemplateA"},
        ]

        project_data = {
            "roi_templates": [
                {"name": "ProjectTemplateB"},
                {"name": "ProjectTemplateA"},
            ]
        }

        templates = manager.list_roi_templates(project_data, include_global=True)
        # Project templates come first, sorted by name; then global templates
        assert len(templates) == 4
        assert templates[0]["name"] == "ProjectTemplateA"
        assert templates[0]["location"] == "project"
        assert templates[1]["name"] == "ProjectTemplateB"
        assert templates[1]["location"] == "project"
        assert templates[2]["name"] == "GlobalTemplateA"
        assert templates[2]["location"] == "global"
        assert templates[3]["name"] == "GlobalTemplateZ"
        assert templates[3]["location"] == "global"

    def test_resolve_roi_template_entry(self):
        project_data = {
            "roi_templates": [
                {"name": "First"},
                {"name": "TargetTemplate"},
            ]
        }

        idx, entry = AssetManager._resolve_roi_template_entry(project_data, "TargetTemplate")
        assert idx == 1
        assert entry is not None
        assert entry["name"] == "TargetTemplate"

        idx_miss, entry_miss = AssetManager._resolve_roi_template_entry(project_data, "NonExistent")
        assert idx_miss is None
        assert entry_miss is None


class TestAssetManagerExtended5:
    def test_save_roi_template_empty_name_raises(self):
        am = AssetManager()
        with pytest.raises(ValueError, match="cannot be empty"):
            am.save_roi_template({}, "/path", "", MagicMock(), MagicMock())

    def test_save_roi_template_none_zone_data_raises(self):
        am = AssetManager()
        with pytest.raises(ValueError, match="Invalid zone data"):
            am.save_roi_template({}, "/path", "MyTemplate", None, MagicMock())  # type: ignore[arg-type]

    def test_save_roi_template_neither_arena_nor_rois_raises(self):
        am = AssetManager()
        with pytest.raises(ValueError, match="at least the arena or the ROIs"):
            am.save_roi_template(
                {},
                "/path",
                "MyTemplate",
                MagicMock(),
                MagicMock(),
                save_arena=False,
                save_rois=False,
            )

    def test_save_roi_template_no_project_loaded_raises(self):
        am = AssetManager()
        with pytest.raises(ValueError, match="no project loaded"):
            am.save_roi_template(
                {}, "", "MyTemplate", MagicMock(), MagicMock(), save_location="project"
            )


class TestAssetManagerExtended6:
    def test_asset_manager_slugify(self):
        assert AssetManager._slugify("My Test Arena 01!") == "my-test-arena-01"
        assert AssetManager._slugify("Grupo_Controle #2") == "grupo_controle-2"
        assert AssetManager._slugify("  simple  ") == "simple"


class TestAssetManagerExtended7:
    def test_asset_manager_roi_template_manager_instantiated(self):
        am = AssetManager()
        assert am.roi_template_manager is not None

    def test_slugify_with_special_characters(self):
        assert AssetManager._slugify("Arena #1 @ Lab (Main)") == "arena-1-lab-main"
        assert AssetManager._slugify("---test---") == "test"

    def test_slugify_numbers_and_underscores(self):
        assert AssetManager._slugify("arena_123_test") == "arena_123_test"


# ---------------------------------------------------------------------------
# TASK-087: templates on real files, removal cascades on real folders.
# ---------------------------------------------------------------------------


TEMPLATE_ARENA = [[0, 0], [100, 0], [100, 80], [0, 80]]
TEMPLATE_ROI = [[10, 10], [30, 10], [30, 30]]


@pytest.fixture
def isolated_manager(tmp_path, monkeypatch) -> AssetManager:
    """AssetManager whose global template folder lives under tmp_path."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    manager = AssetManager()
    assert manager.roi_template_manager.global_templates_dir == home / ".zebtrack" / "roi_templates"
    return manager


def _template_zone() -> ZoneData:
    return ZoneData(
        polygon=[list(p) for p in TEMPLATE_ARENA],
        roi_polygons=[[list(p) for p in TEMPLATE_ROI]],
        roi_names=["toca"],
        roi_colors=[(1, 2, 3)],
    )


def _save(manager, project_data, project_path, name, **kwargs):
    return manager.save_roi_template(
        project_data, project_path, name, _template_zone(), ZoneManager.zone_data_to_dict, **kwargs
    )


class TestProjectTemplates:
    def test_colliding_slugs_get_numbered_and_files_are_relative(self, isolated_manager, tmp_path):
        project_data: dict = {"roi_templates": "corrupted"}
        calls: list[int] = []

        first = _save(
            isolated_manager,
            project_data,
            tmp_path,
            "A B",
            persist_callback=lambda: calls.append(1),
        )
        second = _save(isolated_manager, project_data, tmp_path, "A-B")
        third = _save(isolated_manager, project_data, tmp_path, "a.b")

        assert [first["slug"], second["slug"], third["slug"]] == ["a-b", "a-b-2", "a-b-3"]
        assert second["file"] == str(Path("roi_templates") / "a-b-2.json")
        assert (tmp_path / "roi_templates" / "a-b-3.json").is_file()
        assert [t["name"] for t in project_data["roi_templates"]] == ["A B", "A-B", "a.b"]
        assert first["roi_count"] == 1
        assert calls == [1]

    def test_overwrite_keeps_slug_position_and_creation_date(self, isolated_manager, tmp_path):
        project_data: dict = {}
        original = _save(isolated_manager, project_data, tmp_path, "Arena")
        project_data["roi_templates"][0]["created_at"] = "2020-01-01"

        updated = _save(isolated_manager, project_data, tmp_path, "Arena", save_rois=False)

        assert updated["slug"] == original["slug"]
        assert updated["created_at"] == "2020-01-01"
        assert updated["includes_rois"] is False
        assert len(project_data["roi_templates"]) == 1

    def test_refusing_to_overwrite_raises(self, isolated_manager, tmp_path):
        project_data: dict = {}
        _save(isolated_manager, project_data, tmp_path, "Arena")

        with pytest.raises(ValueError, match="already exists"):
            _save(isolated_manager, project_data, tmp_path, "Arena", overwrite=False)

    def test_global_and_custom_locations_do_not_touch_the_project(self, isolated_manager, tmp_path):
        project_data: dict = {}
        custom = tmp_path / "custom"
        custom.mkdir()

        global_meta = _save(isolated_manager, project_data, tmp_path, "G", save_location="global")
        custom_meta = _save(
            isolated_manager,
            project_data,
            tmp_path,
            "C",
            save_location="custom",
            custom_path=custom,
        )

        assert global_meta["location"] == "global"
        assert (
            Path(global_meta["file"]).parent
            == isolated_manager.roi_template_manager.global_templates_dir
        )
        assert custom_meta["location"] == "custom"
        assert Path(custom_meta["file"]) == custom / "c.json"
        assert project_data == {}

    def test_import_into_a_project_and_without_a_project(self, isolated_manager, tmp_path):
        source = tmp_path / "exported.json"
        source.write_text(
            json.dumps({"name": "Imported", "data": {"polygon": TEMPLATE_ARENA}}), encoding="utf-8"
        )
        project_data: dict = {}
        calls: list[int] = []

        in_project = isolated_manager.import_roi_template(
            project_data,
            tmp_path,
            source,
            ZoneManager.zone_data_from_dict,
            ZoneManager.zone_data_to_dict,
            persist_callback=lambda: calls.append(1),
        )
        orphan = isolated_manager.import_roi_template(
            {},
            None,
            str(source),
            ZoneManager.zone_data_from_dict,
            ZoneManager.zone_data_to_dict,
            name="Renamed",
            persist_callback=lambda: calls.append(2),
        )

        assert in_project["name"] == "Imported"
        assert (in_project["includes_arena"], in_project["includes_rois"]) == (True, False)
        assert orphan["location"] == "global"
        assert orphan["name"] == "Renamed"
        assert calls == [1]

    def test_import_without_data_block_raises(self, isolated_manager, tmp_path):
        source = tmp_path / "bad.json"
        source.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")

        with pytest.raises(ValueError, match="'data' block"):
            isolated_manager.import_roi_template(
                {}, tmp_path, source, ZoneManager.zone_data_from_dict, ZoneManager.zone_data_to_dict
            )


class TestLoadTemplates:
    def test_project_template_round_trip(self, isolated_manager, tmp_path):
        project_data: dict = {}
        _save(isolated_manager, project_data, tmp_path, "Arena")

        zone = isolated_manager.load_roi_template(
            project_data, tmp_path, "Arena", ZoneManager.zone_data_from_dict
        )

        assert zone.polygon == TEMPLATE_ARENA
        assert zone.roi_polygons == [TEMPLATE_ROI]
        assert zone.roi_colors == [(1, 2, 3)]

    def test_project_entry_without_file_and_with_invalid_content(self, isolated_manager, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"data": "nope"}), encoding="utf-8")
        project_data = {"roi_templates": [{"name": "nofile"}, {"name": "bad", "file": "bad.json"}]}

        with pytest.raises(ValueError, match="not registered"):
            isolated_manager.load_roi_template(project_data, tmp_path, "nofile", dict)
        with pytest.raises(ValueError, match="Invalid template content"):
            isolated_manager.load_roi_template(project_data, tmp_path, "bad", dict)

    def test_project_only_lookup_does_not_fall_back_to_global(self, isolated_manager, tmp_path):
        _save(isolated_manager, {}, tmp_path, "Shared", save_location="global")

        with pytest.raises(ValueError, match="not found in the project"):
            isolated_manager.load_roi_template({}, tmp_path, "Shared", dict, location="project")

        zone = isolated_manager.load_roi_template(
            {}, tmp_path, "Shared", ZoneManager.zone_data_from_dict
        )
        assert zone.polygon == TEMPLATE_ARENA

    def test_explicit_file_and_unknown_name(self, isolated_manager, tmp_path):
        custom = tmp_path / "x.json"
        custom.write_text(json.dumps({"data": {"roi_names": ["a"]}}), encoding="utf-8")
        broken = tmp_path / "y.json"
        broken.write_text(json.dumps({"data": 1}), encoding="utf-8")

        zone = isolated_manager.load_roi_template(
            {}, None, "x", ZoneManager.zone_data_from_dict, location="custom", file_path=custom
        )

        assert zone.roi_names == ["a"]
        with pytest.raises(FileNotFoundError):
            isolated_manager.load_roi_template(
                {}, None, "z", dict, location="custom", file_path=tmp_path / "missing.json"
            )
        with pytest.raises(ValueError, match="Invalid template content"):
            isolated_manager.load_roi_template({}, None, "y", dict, file_path=broken)
        with pytest.raises(ValueError, match="requested context"):
            isolated_manager.load_roi_template({}, None, "ghost", dict)

    def test_listing_skips_non_dict_entries(self, isolated_manager, tmp_path):
        _save(isolated_manager, {}, tmp_path, "Glob", save_location="global")
        project_data = {"roi_templates": ["junk", {"name": "Proj"}]}

        listed = isolated_manager.list_roi_templates(project_data)

        assert [(t["name"], t["location"]) for t in listed] == [
            ("Proj", "project"),
            ("Glob", "global"),
        ]
        assert (
            isolated_manager.list_roi_templates({"roi_templates": None}, include_global=False) == []
        )


class TestAnalysisProfiles:
    def test_criteria_less_profile_is_the_fallback_even_when_not_first(self):
        manager = AssetManager.__new__(AssetManager)
        project_data = {
            "analysis_profiles": [
                {"name": "treated", "criteria": {"group": ["Tratamento"]}},
                {"name": "catch-all", "criteria": {}},
                {"name": "day2", "criteria": {"day": 2, "subject": [""]}},
            ]
        }

        assert manager.resolve_analysis_profile(project_data, {"group_id": " tratamento "})[
            "name"
        ] == ("treated")
        assert manager.resolve_analysis_profile(project_data, {"day_label": "2"})["name"] == "day2"
        assert manager.resolve_analysis_profile(project_data, {"day": None, "group": ""})[
            "name"
        ] == ("catch-all")
        assert manager.resolve_analysis_profile(project_data, None)["name"] == "catch-all"

    def test_profiles_are_returned_as_copies(self):
        manager = AssetManager.__new__(AssetManager)
        project_data = {"analysis_profiles": [{"name": "p", "criteria": {}}]}

        manager.get_analysis_profiles(project_data)[0]["name"] = "changed"

        assert project_data["analysis_profiles"][0]["name"] == "p"


class TestAssetQueries:
    def test_aquarium_asset_lookup(self):
        entry = {
            "has_trajectory": True,
            "multi_aquarium_outputs": {
                "0": {"parquet_files": {"trajectory": "t0", "report_docx": "r0"}},
                1: {"parquet_files": None},
            },
        }

        assert AssetManager.video_has_asset_for_aquarium(None, 0, "trajectory") is False
        assert AssetManager.video_has_asset_for_aquarium(entry, 0, "trajectory") is True
        assert AssetManager.video_has_asset_for_aquarium(entry, 0, "summary") is True
        assert AssetManager.video_has_asset_for_aquarium(entry, 1, "trajectory") is False
        assert AssetManager.video_has_asset_for_aquarium(entry, 5, "summary") is False
        single = {"has_summary": True}
        assert AssetManager.video_has_asset_for_aquarium(single, 3, "summary") is True
        with pytest.raises(ValueError):
            AssetManager.video_has_asset_for_aquarium(entry, 0, "arena")  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            AssetManager.video_has_asset(entry, "masks")  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        ("entry", "asset", "expected"),
        [
            ({}, "arena", (False, "There is no arena recorded for this video.")),
            ({}, "rois", (False, "There are no ROIs recorded for this video.")),
            ({}, "trajectory", (False, "There is no trajectory recorded for this video.")),
            ({}, "summary", (False, "There are no reports or summaries to remove.")),
            ({"has_arena": True}, "arena", (True, None)),
            ({"path": "v.mp4"}, "video", (True, None)),
            (
                {"has_summary": True},
                "video",
                (False, "Remove the reports and summaries before deleting the video."),
            ),
            (
                {"has_rois": True},
                "video",
                (
                    False,
                    "Remove the arena, the ROIs and the trajectory before deleting "
                    "the video from the project.",
                ),
            ),
        ],
    )
    def test_can_remove_asset_messages(self, entry, asset, expected):
        manager = AssetManager.__new__(AssetManager)

        assert manager.can_remove_asset(entry, asset) == expected


class TestRemovalOnRealFiles:
    def test_remove_arena_drops_arena_and_rois_files(self, tmp_path):
        arena, rois = tmp_path / "1.parquet", tmp_path / "2.parquet"
        arena.write_bytes(b"a")
        rois.write_bytes(b"r")
        entry = {
            "has_arena": True,
            "has_rois": True,
            "has_trajectory": True,
            "has_complete_data": True,
            "parquet_files": {"arena": str(arena), "rois": str(rois), "trajectory": "t"},
        }
        cleared: list[str] = []

        changed = AssetManager.__new__(AssetManager).remove_arena_asset(
            tmp_path / "v.mp4", entry, True, clear_zone_data_fn=cleared.append
        )

        assert changed is True
        assert not arena.exists() and not rois.exists()
        assert entry["parquet_files"] == {"trajectory": "t"}
        assert (entry["has_arena"], entry["has_rois"], entry["has_complete_data"]) == (
            False,
            False,
            False,
        )
        assert cleared == [str(tmp_path / "v.mp4")]

    def test_remove_rois_clears_zone_rois_but_keeps_the_arena(self, tmp_path):
        rois = tmp_path / "2.parquet"
        rois.write_bytes(b"r")
        zone = ZoneData(polygon=TEMPLATE_ARENA, roi_polygons=[TEMPLATE_ROI], roi_names=["t"])
        saved: list[tuple] = []
        entry = {"has_rois": True, "has_arena": True, "parquet_files": {"rois": str(rois)}}

        changed = AssetManager.__new__(AssetManager).remove_rois_asset(
            "v.mp4",
            entry,
            False,
            get_zone_data_fn=lambda path, fallback_to_global: zone,
            save_zone_data_fn=lambda z, video_path, persist: saved.append((z, video_path, persist)),
        )

        assert changed is True
        assert rois.exists()
        assert saved == [(zone, "v.mp4", False)]
        assert (zone.polygon, zone.roi_polygons, zone.roi_names) == (TEMPLATE_ARENA, [], [])
        assert entry == {
            "has_rois": False,
            "has_arena": True,
            "has_complete_data": False,
            "parquet_files": {},
        }

    def test_remove_rois_with_nothing_to_remove_reports_no_change(self):
        entry: dict = {}

        changed = AssetManager.__new__(AssetManager).remove_rois_asset(
            "v.mp4",
            entry,
            True,
            get_zone_data_fn=lambda path, fallback_to_global: ZoneData(),
            save_zone_data_fn=lambda *a, **k: pytest.fail("nothing to save"),
        )

        assert changed is False

    def test_remove_video_entry_without_files_matches_the_path_case_insensitively(self, tmp_path):
        video = tmp_path / "Dia_1" / "S1.mp4"
        video.parent.mkdir()
        video.write_bytes(b"v")
        project_data = {
            "batches": [
                {"videos": [{"path": str(video).upper()}, {"path": str(tmp_path / "other.mp4")}]}
            ]
        }
        cleared: list[str] = []
        refreshed: list = []

        changed = AssetManager.__new__(AssetManager).remove_video_entry(
            str(video),
            {"path": str(video)},
            False,
            project_data=project_data,
            clear_zone_data_fn=cleared.append,
            refresh_last_zone_source_fn=lambda removed_path: refreshed.append(removed_path),
        )

        assert changed is True
        assert video.exists()
        assert project_data["batches"][0]["videos"] == [{"path": str(tmp_path / "other.mp4")}]
        assert cleared == [str(video)] and refreshed == [str(video)]

    def test_remove_unknown_video_entry_changes_nothing(self, tmp_path):
        project_data = {"batches": [{"videos": [{"path": "a.mp4"}]}]}

        changed = AssetManager.__new__(AssetManager).remove_video_entry(
            "b.mp4",
            {},
            False,
            project_data=project_data,
            clear_zone_data_fn=lambda p: None,
            refresh_last_zone_source_fn=lambda removed_path: pytest.fail("no change"),
        )

        assert changed is False

    def test_remove_video_entry_with_files_deletes_its_outputs(self, tmp_path):
        subject = tmp_path / "Grupo_A" / "Dia_01" / "Sujeito_01"
        subject.mkdir(parents=True)
        video = subject / "S1.mp4"
        video.write_bytes(b"v")
        results = tmp_path / "results"
        results.mkdir()
        (results / "x.txt").write_text("x")
        aq_dir = tmp_path / "aq"
        aq_dir.mkdir()
        aq_file = tmp_path / "aq_traj.parquet"
        aq_file.write_bytes(b"t")
        entry = {
            "path": str(video),
            "results_dir": str(results),
            "parquet_files": {"trajectory": str(subject / "3.parquet")},
            "multi_aquarium_outputs": {
                "0": {"results_dir": str(aq_dir), "parquet_files": {"trajectory": str(aq_file)}}
            },
        }
        project_data = {"batches": [{"videos": [entry]}]}

        changed = AssetManager.__new__(AssetManager).remove_video_entry(
            str(video),
            entry,
            True,
            project_data=project_data,
            clear_zone_data_fn=lambda p: None,
            refresh_last_zone_source_fn=lambda removed_path: None,
        )

        assert changed is True
        assert not video.exists() and not subject.exists()
        assert not results.exists() and not aq_dir.exists() and not aq_file.exists()
        assert project_data["batches"][0]["videos"] == []

    @staticmethod
    def _remove(video, project_data):
        return AssetManager.__new__(AssetManager).remove_video_entry(
            str(video),
            {"path": str(video)},
            True,
            project_data=project_data,
            clear_zone_data_fn=lambda p: None,
            refresh_last_zone_source_fn=lambda removed_path: None,
        )

    def test_removing_one_video_keeps_its_sibling_in_the_same_folder(self, tmp_path):
        # F2-P-001: the parent folder used to be rmtree()d, taking every sibling with it.
        folder = tmp_path / "videos"
        folder.mkdir()
        removed, sibling = folder / "a.mp4", folder / "b.mp4"
        removed.write_bytes(b"a")
        sibling.write_bytes(b"b")
        own_zones = [folder / f"{prefix}a.parquet" for prefix in ZONE_PARQUET_PREFIXES]
        sibling_zones = [folder / f"{prefix}b.parquet" for prefix in ZONE_PARQUET_PREFIXES]
        for zone_file in own_zones + sibling_zones:
            zone_file.write_bytes(b"z")
        project_data = {"batches": [{"videos": [{"path": str(removed)}, {"path": str(sibling)}]}]}

        changed = self._remove(removed, project_data)

        assert changed is True
        assert not removed.exists()
        assert [z.name for z in own_zones if z.exists()] == []
        assert sibling.exists()
        assert [z.name for z in sibling_zones if z.exists()] == [z.name for z in sibling_zones]
        assert project_data["batches"][0]["videos"] == [{"path": str(sibling)}]

    def test_a_folder_left_empty_by_the_removal_is_deleted(self, tmp_path):
        folder = tmp_path / "Sujeito_01"
        folder.mkdir()
        video = folder / "S1.mp4"
        video.write_bytes(b"v")
        (folder / "2_AreasOfInterest_S1.parquet").write_bytes(b"z")

        self._remove(video, {"batches": []})

        assert not folder.exists()
        assert tmp_path.exists()

    def test_a_video_in_the_project_root_never_takes_the_project_with_it(self, tmp_path):
        video = tmp_path / "S1.mp4"
        video.write_bytes(b"v")
        config = tmp_path / "project_config.json"
        config.write_text("{}")

        self._remove(video, {"batches": []})

        assert config.read_text() == "{}"


class TestAquariumScopedRemoval:
    @staticmethod
    def _entry(tmp_path):
        files = {}
        for aq in (0, 1):
            folder = tmp_path / f"aq{aq}"
            folder.mkdir()
            traj = tmp_path / f"traj{aq}.parquet"
            traj.write_bytes(b"t")
            summ = tmp_path / f"sum{aq}.parquet"
            summ.write_bytes(b"s")
            files[aq] = (folder, traj, summ)
        entry = {
            "multi_aquarium_mode": True,
            "has_arena": True,
            "has_rois": True,
            "multi_aquarium_outputs": {
                "0": {
                    "results_dir": str(files[0][0]),
                    "subject_id": "S1",
                    "parquet_files": {"trajectory": str(files[0][1]), "summary": str(files[0][2])},
                },
                1: {
                    "results_dir": str(files[1][0]),
                    "subject_id": "S2",
                    "parquet_files": {"trajectory": str(files[1][1])},
                },
            },
            "metadata": {
                "subject_entries": [
                    {"aquarium_id": 0, "subject": "S1"},
                    {"aquarium_id": None, "subject": "S9"},
                    "junk",
                    {"aquarium_id": "1", "subject": "S2"},
                ]
            },
        }
        return entry, files

    def test_removing_one_aquarium_refreshes_flags_from_the_other(self, tmp_path):
        entry, files = self._entry(tmp_path)
        manager = AssetManager.__new__(AssetManager)

        assert manager.remove_aquarium_subject_data(entry, 0, True) is True

        assert list(entry["multi_aquarium_outputs"]) == [1]
        assert not files[0][0].exists() and not files[0][1].exists()
        assert files[1][1].exists()
        assert (entry["has_trajectory"], entry["has_summary"], entry["has_complete_data"]) == (
            True,
            False,
            True,
        )

    def test_removing_the_last_aquarium_leaves_single_mode(self, tmp_path):
        entry, files = self._entry(tmp_path)
        manager = AssetManager.__new__(AssetManager)
        manager.remove_aquarium_subject_data(entry, 0, False)

        assert manager.remove_aquarium_subject_data(entry, 1, False) is True

        assert "multi_aquarium_outputs" not in entry and "multi_aquarium_mode" not in entry
        assert (entry["has_trajectory"], entry["has_summary"]) == (False, False)
        assert files[1][1].exists()

    def test_unknown_aquarium_or_single_video_is_not_removed(self, tmp_path):
        entry, _files = self._entry(tmp_path)
        manager = AssetManager.__new__(AssetManager)

        assert manager.remove_aquarium_subject_data(entry, 7, True) is False
        assert manager.remove_aquarium_subject_data({}, 0, True) is False

    def test_reset_one_aquarium_keeps_the_other_and_the_zones(self, tmp_path):
        entry, files = self._entry(tmp_path)
        manager = AssetManager.__new__(AssetManager)

        assert manager.reset_analysis_data(entry, delete_files=True, aquarium_id=1) is True

        assert entry["multi_aquarium_outputs"][1]["parquet_files"] == {}
        assert not files[1][1].exists()
        assert files[0][1].exists()
        assert (entry["has_arena"], entry["has_rois"], entry["has_trajectory"]) == (
            True,
            True,
            True,
        )
        assert manager.reset_analysis_data(entry, delete_files=True, aquarium_id=9) is False

    def test_reset_all_aquariums(self, tmp_path):
        entry, files = self._entry(tmp_path)
        manager = AssetManager.__new__(AssetManager)

        assert manager.reset_analysis_data(entry, delete_files=False) is True

        assert entry["has_trajectory"] is False
        assert files[0][1].exists()
        assert manager.reset_analysis_data(entry, delete_files=False) is False

    def test_reset_single_video_removes_trajectory_and_summary(self, tmp_path):
        traj = tmp_path / "3.parquet"
        traj.write_bytes(b"t")
        entry = {
            "has_trajectory": True,
            "has_summary": True,
            "parquet_files": {"trajectory": str(traj), "summary_excel": "s.xlsx"},
        }

        assert AssetManager.__new__(AssetManager).reset_analysis_data(entry, delete_files=True)

        assert not traj.exists()
        assert entry["parquet_files"] == {}
        assert (entry["has_trajectory"], entry["has_summary"]) == (False, False)

    def test_clear_subject_binding_keeps_geometry_and_other_subjects(self, tmp_path):
        entry, files = self._entry(tmp_path)
        manager = AssetManager.__new__(AssetManager)

        changed = manager.clear_aquarium_subject_binding(
            entry, 1, delete_analysis_data=False, delete_files=False
        )

        assert changed is True
        assert entry["multi_aquarium_outputs"][1]["subject_id"] == ""
        assert entry["multi_aquarium_outputs"]["0"]["subject_id"] == "S1"
        subjects = [
            e["subject"] for e in entry["metadata"]["subject_entries"] if isinstance(e, dict)
        ]
        assert subjects == ["S1", "S9", ""]
        assert files[1][1].exists()

    def test_clear_subject_binding_with_analysis_reset(self, tmp_path):
        entry, files = self._entry(tmp_path)
        manager = AssetManager.__new__(AssetManager)

        assert manager.clear_aquarium_subject_binding(
            entry, 0, delete_analysis_data=True, delete_files=True
        )

        assert not files[0][1].exists()
        assert (
            manager.clear_aquarium_subject_binding(
                entry, 4, delete_analysis_data=True, delete_files=True
            )
            is False
        )

    def test_rmtree_safe_gives_up_after_its_retries(self, tmp_path, monkeypatch):
        import shutil
        import time

        sleeps: list[float] = []
        real_rmtree = shutil.rmtree
        monkeypatch.setattr(time, "sleep", sleeps.append)

        def locked(path, onerror=None):
            raise PermissionError(path)

        monkeypatch.setattr(shutil, "rmtree", locked)
        assert AssetManager._rmtree_safe(tmp_path, retries=3) is False
        assert sleeps == [0.5, 0.5]
        monkeypatch.setattr(shutil, "rmtree", real_rmtree)
        folder = tmp_path / "gone"
        (folder / "sub").mkdir(parents=True)
        assert AssetManager._rmtree_safe(folder) is True
        assert not folder.exists()
