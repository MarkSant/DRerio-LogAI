"""
Extended unit tests for OutputRegistrationManager in project/output_registration_manager.py.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.core.project.output_registration_manager import (
    LEGACY_NO_DAY_DIRNAME,
    LEGACY_NO_GROUP_DIRNAME,
    LEGACY_NO_SUBJECT_DIRNAME,
    LIVE_REFERENCE_FRAME_STEM,
    REFERENCE_ZONES_DIRNAME,
    OutputRegistrationManager,
)


class TestOutputRegistrationManagerExtended:
    """Test OutputRegistrationManager resolution and registration."""

    @pytest.fixture
    def manager(self) -> OutputRegistrationManager:
        return OutputRegistrationManager()

    def test_sanitize_path_component(self, manager: OutputRegistrationManager):
        res = manager._sanitize_path_component("Grupo 1 / Ação", fallback="indefinido")
        assert res == "Grupo_1_Acao"
        assert manager._sanitize_path_component("", fallback="indefinido") == "indefinido"
        assert manager._sanitize_path_component(None, fallback="default") == "default"

    def test_format_group_component(self, manager: OutputRegistrationManager):
        assert manager._format_group_component({"group": "Controle"}) == "Grupo_Controle"
        res = manager._format_group_component({"group_display_name": "Controle"})
        assert res == "Grupo_Controle"
        assert manager._format_group_component(None) == LEGACY_NO_GROUP_DIRNAME
        assert manager._format_group_component({}) == LEGACY_NO_GROUP_DIRNAME

    def test_format_day_component(self, manager: OutputRegistrationManager):
        assert manager._format_day_component({"day": 1}) == "Dia_01"
        assert manager._format_day_component({"day": "2"}) == "Dia_02"
        assert manager._format_day_component({"day": "Dia_03"}) == "Dia_03"
        assert manager._format_day_component(None) == LEGACY_NO_DAY_DIRNAME
        assert manager._format_day_component({}) == LEGACY_NO_DAY_DIRNAME

    def test_format_subject_component(self, manager: OutputRegistrationManager):
        assert manager._format_subject_component({"subject": 5}) == "Sujeito_05"
        assert manager._format_subject_component({"subject_id": "12"}) == "Sujeito_12"
        assert manager._format_subject_component({"animal": "3"}) == "Sujeito_03"
        assert manager._format_subject_component(None) == LEGACY_NO_SUBJECT_DIRNAME
        assert manager._format_subject_component({}) == LEGACY_NO_SUBJECT_DIRNAME

    def test_resolve_results_directory_live_reference_frame(
        self, manager: OutputRegistrationManager, tmp_path: Path
    ):
        res = manager.resolve_results_directory(
            LIVE_REFERENCE_FRAME_STEM,
            project_path=tmp_path,
        )
        assert res == tmp_path / REFERENCE_ZONES_DIRNAME

    def test_resolve_results_directory_with_metadata(
        self, manager: OutputRegistrationManager, tmp_path: Path
    ):
        meta = {"group": "CBD", "day": 1, "subject": 3}
        res = manager.resolve_results_directory(
            "exp1",
            project_path=tmp_path,
            metadata=meta,
        )
        expected = tmp_path / "Grupo_CBD" / "Dia_01" / "Sujeito_03"
        assert res == expected

    def test_resolve_results_directory_forwards_video_path_to_metadata_lookup(
        self, manager: OutputRegistrationManager, tmp_path: Path
    ):
        """The lookup must receive video_path, not just the (ambiguous) stem.

        The stem repeats across days in a longitudinal project, so a lookup by id
        alone resolves to whichever day comes first — and this directory is where
        the summary parquet is written, so day 2 would overwrite day 1.
        """
        by_path = {
            "/vids/Dia_1/CECT_4/CECT_4.mp4": {"group": "CEC", "day": 1, "subject": 4},
            "/vids/Dia_2/CECT_4/CECT_4.mp4": {"group": "CEC", "day": 2, "subject": 4},
        }

        def lookup(experiment_id, video_path=None):
            return by_path.get(str(video_path), by_path["/vids/Dia_1/CECT_4/CECT_4.mp4"])

        res = manager.resolve_results_directory(
            "CECT_4",
            project_path=tmp_path,
            video_path="/vids/Dia_2/CECT_4/CECT_4.mp4",
            get_metadata_for_experiment_fn=lookup,
        )

        assert res == tmp_path / "Grupo_CEC" / "Dia_02" / "Sujeito_04"

    def test_resolve_results_directory_explicit_metadata_skips_lookup(
        self, manager: OutputRegistrationManager, tmp_path: Path
    ):
        """Live sessions pass metadata explicitly; the lookup must not run."""
        lookup = MagicMock()

        res = manager.resolve_results_directory(
            "exp1",
            project_path=tmp_path,
            metadata={"group": "CBD", "day": 3, "subject": 7},
            get_metadata_for_experiment_fn=lookup,
        )

        lookup.assert_not_called()
        assert res == tmp_path / "Grupo_CBD" / "Dia_03" / "Sujeito_07"

    def test_resolve_results_directory_no_project_path(
        self, manager: OutputRegistrationManager, tmp_path: Path
    ):
        video = tmp_path / "video.mp4"
        res = manager.resolve_results_directory(
            "video",
            project_path=None,
            video_path=str(video),
        )
        assert res == tmp_path / "video_results"

    def test_register_batch_outputs_and_get(self, manager: OutputRegistrationManager):
        project_data: dict = {"project_name": "TestProj"}
        save_fn = MagicMock()

        manager.register_batch_outputs(
            batch_id="batch_01",
            unified_excel="/reports/summary.xlsx",
            session_count=5,
            project_data=project_data,
            project_path="/proj",
            save_project_fn=save_fn,
            group="Control",
        )

        reports = manager.get_batch_reports(project_data)
        assert "batch_01" in reports
        assert reports["batch_01"]["session_count"] == 5
        assert reports["batch_01"]["group"] == "Control"
        save_fn.assert_called_once()


# ---------------------------------------------------------------------------
# TASK-087: the Grupo_X/Dia_Y/Sujeito_Z contract and output registration.
# ---------------------------------------------------------------------------

REGEX_PATTERNS = {
    "group_pattern": "G(\\d+)",
    "day_pattern": "D(\\d+)",
    "subject_pattern": "S(\\d+)",
}


class TestFolderComponents:
    @pytest.mark.parametrize(
        ("metadata", "expected"),
        [
            ({"day": "Dia 3"}, "Dia_03"),
            ({"dia": "day12"}, "Dia_12"),
            ({"day_id": "Dia final"}, "Dia_Dia_final"),
            ({"day": 2.0}, "Dia_02"),
            ({"day": 2.5}, "Dia_2.5"),
            ({"day": "semana"}, "Dia_semana"),
            ({"day": ""}, "Dia_Indefinido"),
            (None, "Dia_Indefinido"),
        ],
    )
    def test_day_component(self, metadata, expected):
        assert OutputRegistrationManager()._format_day_component(metadata) == expected

    @pytest.mark.parametrize(
        ("metadata", "expected"),
        [
            ({"subject": 7}, "Sujeito_07"),
            ({"subject_id": "3.0"}, "Sujeito_03"),
            ({"animal": 1.5}, "Sujeito_1.5"),
            ({"sujeito": "Rato A"}, "Sujeito_Rato_A"),
            ({}, "Sujeito_Indefinido"),
        ],
    )
    def test_subject_component(self, metadata, expected):
        assert OutputRegistrationManager()._format_subject_component(metadata) == expected

    def test_group_display_name_wins_over_the_group_id(self):
        manager = OutputRegistrationManager()

        assert manager._format_group_component({"group": "G1", "group_display_name": "Ação 1"}) == (
            "Grupo_Acao_1"
        )
        assert manager._format_group_component({"group_label": "", "group": "B"}) == "Grupo_B"

    def test_homonymous_videos_resolve_to_their_own_day_folder(self, tmp_path):
        entries = {
            "Dia_1/CECT_4/CECT_4.mp4": {"day": 1, "group": "Ctrl", "subject": 4},
            "Dia_2/CECT_4/CECT_4.mp4": {"day": 2, "group": "Ctrl", "subject": 4},
        }

        def lookup(experiment_id, video_path):
            return entries[video_path]

        manager = OutputRegistrationManager()
        folders = [
            manager.resolve_results_directory(
                "CECT_4",
                project_path=tmp_path,
                video_path=path,
                get_metadata_for_experiment_fn=lookup,
            )
            for path in entries
        ]

        assert folders == [
            tmp_path / "Grupo_Ctrl" / "Dia_01" / "Sujeito_04",
            tmp_path / "Grupo_Ctrl" / "Dia_02" / "Sujeito_04",
        ]

    def test_derived_metadata_is_used_when_the_lookup_finds_nothing(self, tmp_path):
        manager = OutputRegistrationManager()

        folder = manager.resolve_results_directory(
            "v",
            project_path=tmp_path,
            video_path="C:/x/v.mp4",
            get_metadata_for_experiment_fn=lambda *a: {},
            derive_processing_metadata_fn=lambda exp, path: {"group": "G", "day": 1},
        )

        assert folder == tmp_path / "Grupo_G" / "Dia_01" / "Sujeito_Indefinido"

    def test_without_project_and_without_video(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        manager = OutputRegistrationManager()

        assert manager.resolve_results_directory("", project_path=None) == (
            tmp_path / "experimento_results"
        )
        assert manager.resolve_results_directory(
            "", project_path=None, metadata={"experiment_id": "E9"}
        ) == (tmp_path / "E9_results")
        assert manager.resolve_results_directory(
            "v_aq2", project_path=None, video_path=str(tmp_path / "v.mp4")
        ) == (tmp_path / "v_aq2_results")


class TestDeriveProcessingMetadata:
    def test_entry_values_fill_the_metadata_without_a_regex(self):
        meta = OutputRegistrationManager().derive_processing_metadata(
            "E1",
            None,
            project_data={},
            find_video_entry_fn=lambda **kw: {"metadata": {"group": "A"}, "day": 0, "group": "B"},
            get_available_groups_fn=list,
        )

        assert meta == {
            "group": "A",
            "day": 0,
            "experiment_id": "E1",
            "video_name": "E1",
            "group_id": "A",
        }

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "F2-P-003: the wizard-regex fallback builds MultiAquariumData(enabled=True, "
            "aquarium_configs=[]), which the model rejects ('requires exactly 2 aquarium "
            "configurations'); the ValidationError is swallowed as ValueError, so the "
            "regex never fills group/day/subject (output_registration_manager.py:292)."
        ),
    )
    def test_entry_values_and_the_wizard_regex_fill_the_gaps(self):
        project = {"_wizard_metadata": {"custom_regex_patterns": REGEX_PATTERNS}}

        meta = OutputRegistrationManager().derive_processing_metadata(
            "G2_D3_S4",
            "C:/v/G2_D3_S4.mp4",
            project_data=project,
            find_video_entry_fn=lambda **kw: {"metadata": {"note": "x"}, "day": 0, "subject": ""},
            get_available_groups_fn=lambda: ["G01", "G02"],
        )

        assert meta == {
            "note": "x",
            "day": "3",
            "group": "G02",
            "subject": "4",
            "experiment_id": "G2_D3_S4",
            "video_name": "G2_D3_S4",
            "group_id": "G02",
        }

    def test_display_name_becomes_the_label_and_bad_regex_is_ignored(self):
        project = {"_wizard_metadata": {"custom_regex_patterns": {"group_pattern": "("}}}

        meta = OutputRegistrationManager().derive_processing_metadata(
            "E1",
            "C:/v/E1.mp4",
            project_data=project,
            find_video_entry_fn=lambda **kw: {"group_display_name": "Nice"},
            get_available_groups_fn=list,
        )

        assert meta == {
            "group_display_name": "Nice",
            "group_label": "Nice",
            "experiment_id": "E1",
            "video_name": "E1",
        }

    @pytest.mark.parametrize(
        ("raw", "groups", "expected"),
        [
            ("", ["G01"], "Sem_Grupo"),
            ("3", [], "3"),
            ("G02", ["G02"], "G02"),
            ("2", ["Ctrl", "G2"], "G2"),
            ("x", ["G1"], "x"),
            ("9", ["G1"], "9"),
        ],
    )
    def test_resolve_group_name(self, raw, groups, expected):
        assert OutputRegistrationManager.resolve_group_name(raw, groups) == expected


class TestRegisterProcessingOutputs:
    def _register(self, tmp_path, entry, **kwargs):
        batches: list = []
        saves: list[int] = []

        def find(path=None, experiment_id=None):
            return entry if entry is not None and (entry.get("path") == path or batches) else None

        def add(videos, save_project=True):
            batches.append(videos)
            if entry is not None:
                entry.update(videos[0])

        ok = OutputRegistrationManager().register_processing_outputs(
            tmp_path / "v.mp4",
            project_path=tmp_path,
            find_video_entry_fn=find,
            add_video_batch_fn=add,
            get_zone_data_fn=lambda path, fallback_to_global: ZoneData(),
            save_project_fn=lambda: saves.append(1),
            **kwargs,
        )
        return ok, batches, saves

    def test_unknown_video_is_added_with_its_metadata(self, tmp_path):
        entry: dict = {"path": "never-matches"}

        ok, batches, saves = self._register(
            tmp_path,
            entry,
            group="Ctrl",
            day="2",
            subject_id="5",
            trajectory_path=str(tmp_path / "3.parquet"),
            polygon_source="auto",
        )

        assert ok is True
        assert batches == [
            [
                {
                    "path": (tmp_path / "v.mp4").as_posix(),
                    "status": "processing",
                    "group": "Ctrl",
                    "day": "2",
                    "subject": "5",
                }
            ]
        ]
        assert entry["metadata"] == {
            "group": "Ctrl",
            "day": "2",
            "subject": "5",
            "polygon_source": "auto",
        }
        assert entry["status"] == "processed"
        assert saves == [1]

    def test_video_that_cannot_be_added_is_not_registered(self, tmp_path):
        ok, batches, saves = self._register(tmp_path, None)

        assert ok is False
        assert batches == [[{"path": (tmp_path / "v.mp4").as_posix(), "status": "processing"}]]
        assert saves == []

    def test_zone_files_on_disk_set_the_flags_of_a_live_recording(self, tmp_path):
        results = tmp_path / "live_analysis_sessions" / "s1"
        results.mkdir(parents=True)
        (results / "1_ProcessingArea_s1.parquet").write_bytes(b"a")
        (results / "2_AreasOfInterest_s1.parquet").write_bytes(b"r")
        entry = {"path": (tmp_path / "v.mp4").as_posix(), "metadata": {"group": "Keep"}}

        ok, _batches, saves = self._register(
            tmp_path,
            entry,
            results_dir=str(results),
            group="Ignored",
            summary_excel=str(results / "s.xlsx"),
            report_path=str(results / "r.docx"),
        )

        assert ok is True
        assert entry["metadata"] == {"group": "Keep"}
        assert entry["results_dir"] == results.as_posix()
        assert entry["parquet_files"] == {
            "arena": (results / "1_ProcessingArea_s1.parquet").as_posix(),
            "rois": (results / "2_AreasOfInterest_s1.parquet").as_posix(),
            "summary_excel": (results / "s.xlsx").as_posix(),
            "report_docx": (results / "r.docx").as_posix(),
        }
        assert (entry["has_arena"], entry["has_rois"], entry["has_summary"]) == (True, True, True)
        assert "status" not in entry and saves == [1]

    def test_registering_the_same_outputs_twice_does_not_save_again(self, tmp_path):
        entry = {"path": (tmp_path / "v.mp4").as_posix()}
        traj = str(tmp_path / "3.parquet")
        self._register(tmp_path, entry, trajectory_path=traj, summary_parquet=traj)

        ok, _batches, saves = self._register(
            tmp_path, entry, trajectory_path=traj, summary_parquet=traj
        )

        assert ok is True and saves == []

    def test_missing_results_dir_is_skipped(self, tmp_path):
        entry = {"path": (tmp_path / "v.mp4").as_posix()}

        self._register(tmp_path, entry, results_dir=str(tmp_path / "nowhere"))

        assert "has_arena" not in entry


class TestMultiAquariumRegistration:
    def test_directories_are_created_only_for_aquariums_with_a_group(self, tmp_path):
        dirs = OutputRegistrationManager().resolve_multi_aquarium_results_directories(
            "v",
            [{"aquarium_id": 0, "group": "A", "subject_id": "1", "day": 2}, {"aquarium_id": 1}],
            project_path=tmp_path,
        )

        assert dirs == {
            0: tmp_path / "Grupo_A" / "Dia_02" / "Sujeito_01",
            1: tmp_path / "Grupo_Sem_Grupo" / "Dia_01" / "Sujeito_Indefinido",
        }
        assert dirs[0].is_dir() and not dirs[1].exists()
        assert (
            OutputRegistrationManager().resolve_multi_aquarium_results_directories(
                "v", [{}], project_path=None
            )
            == {}
        )

    def test_outputs_complete_only_when_every_aquarium_has_a_trajectory(self, tmp_path):
        entry: dict = {"num_aquariums": 2}
        saves: list[int] = []
        manager = OutputRegistrationManager()

        def register(outputs):
            return manager.register_multi_aquarium_outputs(
                "C:/v.mp4",
                outputs,
                project_path=tmp_path,
                find_video_entry_fn=lambda path: entry,
                save_project_fn=lambda: saves.append(1),
            )

        register(
            {0: {"results_dir": "C:\\r0", "parquet_files": {"trajectory": "C:\\t0", "x": None}}}
        )
        assert "status" not in entry and "has_summary" not in entry
        register({1: {"parquet_files": {"trajectory": "t1", "summary_excel": "s1"}, "group": "B"}})

        assert entry["status"] == "processed" and entry["has_trajectory"] is True
        assert entry["has_summary"] is True
        assert entry["multi_aquarium_outputs"]["0"] == {
            "results_dir": "C:/r0",
            "parquet_files": {"trajectory": "C:/t0", "x": None},
            "group": "",
            "subject_id": "",
            "day": 1,
            "frame_crop_box": None,
        }
        assert (
            manager.get_multi_aquarium_outputs("C:/v.mp4", find_video_entry_fn=lambda path: entry)
            == entry["multi_aquarium_outputs"]
        )
        assert saves == [1, 1]

    def test_unknown_video_and_single_mode(self):
        manager = OutputRegistrationManager()

        assert (
            manager.register_multi_aquarium_outputs(
                "x.mp4",
                {},
                project_path=None,
                find_video_entry_fn=lambda path: None,
                save_project_fn=pytest.fail,
            )
            is False
        )
        assert (
            manager.get_multi_aquarium_outputs("x", find_video_entry_fn=lambda path: None) is None
        )
        assert manager.get_multi_aquarium_outputs("x", find_video_entry_fn=lambda path: {}) is None

    def test_batch_reports_need_a_project(self):
        manager = OutputRegistrationManager()

        assert (
            manager.register_batch_outputs(
                "b", "x.xlsx", 1, project_data={}, project_path=None, save_project_fn=pytest.fail
            )
            is False
        )
        assert OutputRegistrationManager.get_batch_reports({}) == {}
