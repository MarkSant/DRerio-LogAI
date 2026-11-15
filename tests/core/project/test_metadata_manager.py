"""Testes unitários para ``MetadataManager`` (métodos estáticos, sem estado).

Cobre carregamento de metadata.csv, busca de metadados por experimento (ordem
de prioridade CSV > project_data > regex), persistência de estado do detector,
normalização de thresholds e varredura de sessões concluídas.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from zebtrack.core.project.metadata_manager import MetadataManager


@pytest.mark.unit
class TestLoadMetadata:
    """Carregamento do metadata.csv."""

    def test_none_path_returns_none(self):
        assert MetadataManager.load_metadata(None) is None

    def test_nonexistent_path_returns_none(self, tmp_path):
        assert MetadataManager.load_metadata(tmp_path / "inexistente") is None

    def test_valid_csv_returns_dataframe(self, tmp_path):
        csv = tmp_path / "metadata.csv"
        csv.write_text("experiment_id,group\nexp1,G1\nexp2,G2\n", encoding="utf-8")

        df = MetadataManager.load_metadata(tmp_path)

        assert df is not None
        assert list(df["experiment_id"]) == ["exp1", "exp2"]

    def test_malformed_csv_returns_none(self, tmp_path):
        """CSV malformado (linhas com nº de campos inconsistente) -> None."""
        csv = tmp_path / "metadata.csv"
        # Cabeçalho com 2 colunas, mas uma linha com 4 campos -> ParserError.
        csv.write_text('a,b\n1,2\n3,4,5,6\n"unterminated', encoding="utf-8")

        assert MetadataManager.load_metadata(tmp_path) is None


@pytest.mark.unit
class TestGetMetadataForExperiment:
    """Busca de metadados por experimento."""

    def test_empty_experiment_id_returns_empty(self):
        result = MetadataManager.get_metadata_for_experiment(
            "",
            metadata_df=None,
            project_data={},
            find_video_entry_fn=lambda **kw: None,
        )
        assert result == {}

    def test_none_experiment_id_returns_empty(self):
        result = MetadataManager.get_metadata_for_experiment(
            None,
            metadata_df=None,
            project_data={},
            find_video_entry_fn=lambda **kw: None,
        )
        assert result == {}

    def test_csv_match_takes_priority(self):
        df = pd.DataFrame({"experiment_id": ["exp1"], "group_id": ["G1"], "subject": [7]})
        result = MetadataManager.get_metadata_for_experiment(
            "exp1",
            metadata_df=df,
            project_data={},
            find_video_entry_fn=lambda **kw: None,
        )
        assert result["group_id"] == "G1"
        assert result["subject"] == 7

    def test_project_data_fallback_when_no_csv(self):
        """Sem CSV, usa a hierarquia de project_data via find_video_entry_fn."""
        video_info = {"metadata": {"group_id": "GP", "subject_id": "S3"}}
        result = MetadataManager.get_metadata_for_experiment(
            "exp_x",
            metadata_df=None,
            project_data={"videos": {}},
            find_video_entry_fn=lambda **kw: video_info,
        )
        assert result["group_id"] == "GP"
        assert result["subject_id"] == "S3"

    def test_regex_fallback_parses_experiment_id(self):
        """Sem CSV nem project_data, extrai day/group/subject do padrão D#_G#_S#."""
        result = MetadataManager.get_metadata_for_experiment(
            "D5_GControl_S12",
            metadata_df=None,
            project_data={},
            find_video_entry_fn=lambda **kw: None,
        )
        assert result["day"] == 5
        assert result["group"] == "Control"
        assert result["subject"] == 12

    def test_unmatched_id_returns_empty_dict(self):
        """ID que não casa com nada retorna dict vazio sem erro."""
        result = MetadataManager.get_metadata_for_experiment(
            "qualquer_coisa_sem_padrao",
            metadata_df=None,
            project_data={},
            find_video_entry_fn=lambda **kw: None,
        )
        assert result == {}


@pytest.mark.unit
class TestDetectorState:
    """Persistência e leitura do estado do detector."""

    def test_save_without_project_data_returns_false(self):
        called = []
        ok = MetadataManager.save_detector_state(
            {"plugin_name": "yolo"},
            project_data={},
            project_path=None,
            save_project_fn=lambda: called.append(True),
        )
        assert ok is False
        assert called == []

    def test_save_in_memory_without_path(self):
        """Com project_data mas sem path -> salva em memória, não chama save_fn."""
        called = []
        project_data: dict = {"existing": 1}
        ok = MetadataManager.save_detector_state(
            {"plugin_name": "yolo", "conf_threshold": 0.4},
            project_data=project_data,
            project_path=None,
            save_project_fn=lambda: called.append(True),
        )
        assert ok is True
        assert called == []  # sem path, não persiste em disco
        assert project_data["detector_config"]["plugin_name"] == "yolo"

    def test_save_with_path_calls_save_fn(self, tmp_path):
        called = []
        project_data: dict = {"name": "proj"}
        ok = MetadataManager.save_detector_state(
            {"plugin_name": "openvino"},
            project_data=project_data,
            project_path=tmp_path,
            save_project_fn=lambda: called.append(True),
        )
        assert ok is True
        assert called == [True]
        assert "last_updated" in project_data["detector_config"]

    def test_get_detector_state_roundtrip(self):
        project_data = {"detector_config": {"plugin_name": "yolo"}}
        assert MetadataManager.get_detector_state(project_data) == {"plugin_name": "yolo"}

    def test_get_detector_state_empty_when_absent(self):
        assert MetadataManager.get_detector_state({}) == {}

    def test_normalize_thresholds_maps_and_casts(self):
        out = MetadataManager._normalize_detector_thresholds(
            {"conf_threshold": "0.5", "nms_threshold": 0.7, "irrelevant": "x"}
        )
        assert out["confidence_threshold"] == 0.5
        assert out["nms_threshold"] == 0.7
        assert "irrelevant" not in out

    def test_normalize_thresholds_empty_input(self):
        assert MetadataManager._normalize_detector_thresholds({}) == {}
        assert MetadataManager._normalize_detector_thresholds(None) == {}

    def test_normalize_thresholds_skips_non_numeric(self):
        out = MetadataManager._normalize_detector_thresholds({"conf_threshold": "nao_numerico"})
        assert out == {}


@pytest.mark.unit
class TestGetCompletedSessions:
    """Varredura de pastas de sessões concluídas."""

    def test_none_path_returns_empty_set(self):
        assert MetadataManager.get_completed_sessions(None) == set()

    def test_new_format_with_timestamp(self, tmp_path):
        (tmp_path / "day3_Control_7_20260101_120000").mkdir()
        result = MetadataManager.get_completed_sessions(tmp_path)
        assert (3, "Control", "7") in result

    def test_new_format_without_timestamp(self, tmp_path):
        (tmp_path / "day2_Treated_5").mkdir()
        result = MetadataManager.get_completed_sessions(tmp_path)
        assert (2, "Treated", "5") in result

    def test_legacy_format(self, tmp_path):
        # O padrão legado D(\d+)_G(.+)_S(\d+) captura o grupo sem o prefixo "G".
        (tmp_path / "D4_GSham_S9").mkdir()
        result = MetadataManager.get_completed_sessions(tmp_path)
        assert (4, "Sham", "9") in result

    def test_non_session_folders_ignored(self, tmp_path):
        (tmp_path / "random_folder").mkdir()
        (tmp_path / "openvino_model_cache").mkdir()
        result = MetadataManager.get_completed_sessions(tmp_path)
        assert result == set()

    def test_cancelled_legacy_live_session_is_ignored(self, tmp_path):
        session_dir = tmp_path / "live_analysis_sessions" / "day3_Control_7_20260101_120000"
        session_dir.mkdir(parents=True)
        (session_dir / ".cancelled").touch()

        result = MetadataManager.get_completed_sessions(tmp_path)

        assert (3, "Control", "7") not in result

    def test_hierarchical_session_with_only_arena_parquet_is_not_completed(self, tmp_path):
        """An aborted recording that only wrote the arena parquet (Recorder
        writes it as soon as the session folder opens, before any frame is
        captured) must NOT count as a completed session — otherwise the
        Progresso grid shows a video that was never actually recorded."""
        session_dir = tmp_path / "Grupo_Controle" / "Dia_1" / "Sujeito_1" / "live_20260101_120000"
        session_dir.mkdir(parents=True)
        (session_dir / "1_ProcessingArea_exp.parquet").touch()

        result = MetadataManager.get_completed_sessions(tmp_path)

        assert (1, "Controle", "1") not in result

    def test_hierarchical_session_with_trajectory_parquet_is_completed(self, tmp_path):
        """A session with a real trajectory parquet counts as completed."""
        session_dir = tmp_path / "Grupo_Controle" / "Dia_1" / "Sujeito_1" / "live_20260101_120000"
        session_dir.mkdir(parents=True)
        (session_dir / "1_ProcessingArea_exp.parquet").touch()
        (session_dir / "3_CoordMovimento_exp.parquet").touch()

        result = MetadataManager.get_completed_sessions(tmp_path)

        assert (1, "Controle", "1") in result

    def test_hierarchical_session_cancelled_with_trajectory_is_ignored(self, tmp_path):
        """A cancelled session is ignored even if it has a trajectory parquet."""
        session_dir = tmp_path / "Grupo_Controle" / "Dia_1" / "Sujeito_1" / "live_20260101_120000"
        session_dir.mkdir(parents=True)
        (session_dir / "3_CoordMovimento_exp.parquet").touch()
        (session_dir / ".cancelled").touch()

        result = MetadataManager.get_completed_sessions(tmp_path)

        assert (1, "Controle", "1") not in result


class TestMetadataManagerExtended:
    """Test MetadataManager static methods."""

    def test_load_metadata_none_path_returns_none(self):
        result = MetadataManager.load_metadata(None)
        assert result is None

    def test_load_metadata_nonexistent_path_returns_none(self, tmp_path: Path):
        result = MetadataManager.load_metadata(tmp_path / "no_such_project")
        assert result is None

    def test_load_metadata_valid_csv(self, tmp_path: Path):
        csv_path = tmp_path / "metadata.csv"
        csv_path.write_text("experiment_id,group\nD1_G1_S1,Control\n")
        result = MetadataManager.load_metadata(tmp_path)
        assert result is not None
        assert "experiment_id" in result.columns
        assert result.iloc[0]["group"] == "Control"

    def test_get_metadata_empty_experiment_id_returns_empty(self):
        result = MetadataManager.get_metadata_for_experiment(
            None,
            metadata_df=None,
            project_data={},
            find_video_entry_fn=MagicMock(return_value=None),
        )
        assert result == {}

    def test_get_metadata_regex_fallback_parses_id(self):
        result = MetadataManager.get_metadata_for_experiment(
            "D3_G2_S5",
            metadata_df=None,
            project_data={},
            find_video_entry_fn=MagicMock(return_value=None),
        )
        assert result["day"] == 3
        assert result["group"] == "2"
        assert result["subject"] == 5

    def test_get_metadata_no_match_returns_empty(self):
        result = MetadataManager.get_metadata_for_experiment(
            "random_filename",
            metadata_df=None,
            project_data={},
            find_video_entry_fn=MagicMock(return_value=None),
        )
        assert result == {}

    def test_get_metadata_from_project_data(self):
        video_entry = {"metadata": {"group": "CBD", "group_id": "g1", "day": 2, "subject": 1}}
        result = MetadataManager.get_metadata_for_experiment(
            "exp1",
            metadata_df=None,
            project_data={"videos": [video_entry]},
            find_video_entry_fn=MagicMock(return_value=video_entry),
        )
        assert result["group"] == "CBD"

    def test_save_detector_state_updates_and_saves(self):
        project_data: dict = {"project_name": "TestProj"}  # Must be non-empty
        save_fn = MagicMock()
        ok = MetadataManager.save_detector_state(
            {"animal_method": "seg", "conf": 0.5},
            project_data=project_data,
            project_path=Path("/tmp/proj"),
            save_project_fn=save_fn,
        )
        assert ok is True
        assert project_data.get("detector_config") is not None
        save_fn.assert_called_once()


# ---------------------------------------------------------------------------
# TASK-087: metadata.csv failures, session folders on disk, group listing.
# ---------------------------------------------------------------------------


class TestLoadMetadataFailures:
    def test_unreadable_metadata_csv_returns_none(self, tmp_path):
        (tmp_path / "metadata.csv").mkdir()

        assert MetadataManager.load_metadata(tmp_path) is None

    def test_undecodable_metadata_csv_returns_none(self, tmp_path):
        (tmp_path / "metadata.csv").write_bytes(b"experiment_id,group\n\xff\xfe\xfa,\xc3\x28\n")

        assert MetadataManager.load_metadata(str(tmp_path)) is None

    def test_unexpected_reader_failure_returns_none(self, tmp_path, monkeypatch):
        (tmp_path / "metadata.csv").write_text("experiment_id\nE1\n", encoding="utf-8")

        def explode(path):
            raise RuntimeError("reader crashed")

        monkeypatch.setattr(pd, "read_csv", explode)

        assert MetadataManager.load_metadata(tmp_path) is None


class TestMetadataPriority:
    def test_csv_row_without_group_is_completed_from_the_project_entry(self):
        csv = pd.DataFrame({"experiment_id": ["E1"], "day": [4]})
        lookups: list[dict] = []

        def find(**kwargs):
            lookups.append(kwargs)
            return {"metadata": {"group": "Ctrl", "day": 9}, "subject_id": "S3"}

        meta = MetadataManager.get_metadata_for_experiment(
            "E1", "C:/v/E1.mp4", metadata_df=csv, project_data={"x": 1}, find_video_entry_fn=find
        )

        assert meta == {"experiment_id": "E1", "day": 4, "group": "Ctrl", "subject_id": "S3"}
        assert lookups == [{"path": "C:/v/E1.mp4", "experiment_id": "E1"}]

    def test_regex_fills_only_what_is_missing(self):
        meta = MetadataManager.get_metadata_for_experiment(
            "D2_GTreated_S5",
            metadata_df=pd.DataFrame({"other": [1]}),
            project_data={"x": 1},
            find_video_entry_fn=lambda **kwargs: {"day": 7},
        )

        assert meta == {"day": 7, "group": "Treated", "subject": 5}


class TestDetectorStateClearing:
    def test_thresholds_are_merged_into_existing_overrides(self):
        project = {"model_overrides": {"detector_parameters": {"nms_threshold": 0.4}}}

        MetadataManager.save_detector_state(
            {"conf_threshold": 0.3, "last_updated": "t"},
            project_data=project,
            project_path=None,
            save_project_fn=lambda: pytest.fail("no path, no save"),
        )

        assert project["model_overrides"]["detector_parameters"] == {
            "nms_threshold": 0.4,
            "confidence_threshold": 0.3,
        }
        assert project["detector_config"]["last_updated"] == "t"

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "F2-P-002: save_detector_state({}) stamps last_updated into the dict before "
            "testing it, so the 'empty config clears detector_parameters' branch "
            "(metadata_manager.py:224) can never run and stale thresholds survive."
        ),
    )
    def test_saving_an_empty_detector_config_clears_the_threshold_overrides(self):
        project = {"model_overrides": {"detector_parameters": {"nms_threshold": 0.4}}}

        MetadataManager.save_detector_state(
            {}, project_data=project, project_path=None, save_project_fn=lambda: None
        )

        assert "detector_parameters" not in project["model_overrides"]


class TestCompletedSessionsOnDisk:
    @staticmethod
    def _session(root: Path, *parts: str, trajectory: bool = True, cancelled: bool = False):
        folder = root.joinpath(*parts)
        folder.mkdir(parents=True)
        if trajectory:
            (folder / "3_CoordMovimento_x.parquet").write_bytes(b"t")
        else:
            (folder / "1_ProcessingArea_x.parquet").write_bytes(b"a")
        if cancelled:
            (folder / ".cancelled").write_text("")
        return folder

    def test_every_layout_is_recognised_and_noise_is_ignored(self, tmp_path):
        root = tmp_path / "proj"
        root.mkdir()
        (root / "day1_Ctrl_2_20260101_101010").mkdir()
        (root / "D3_GTreated_S4").mkdir()
        cancelled_root = root / "day9_Ctrl_9"
        cancelled_root.mkdir()
        (cancelled_root / ".cancelled").write_text("")
        live = root / "live_analysis_sessions"
        (live / "day2_Ctrl_7").mkdir(parents=True)
        (live / "day5_Ctrl_8").mkdir()
        (live / "day5_Ctrl_8" / ".cancelled").write_text("")
        (live / "stray.txt").write_text("")
        self._session(root, "Grupo_Ctrl", "Dia_03", "Sujeito_05", "live_1")
        self._session(root, "Grupo_Ctrl", "Dia_04", "Sujeito_06", "live_1", trajectory=False)
        self._session(root, "Grupo_Ctrl", "Dia_04", "Sujeito_07", "live_1", cancelled=True)
        (root / "Grupo_Ctrl" / "Dia_03" / "Sujeito_05" / "notes.txt").write_text("")
        (root / "Grupo_Ctrl" / "Dia_03" / "Sujeito_X").mkdir()
        (root / "Grupo_Ctrl" / "Dia_03" / "readme.txt").write_text("")
        (root / "Grupo_Ctrl" / "Semana_1").mkdir()
        (root / "Grupo_Ctrl" / "file.txt").write_text("")
        (root / "Grupo_.txt").write_text("")
        (root / "other_folder").mkdir()

        assert MetadataManager.get_completed_sessions(root) == {
            (1, "Ctrl", "2"),
            (3, "Treated", "4"),
            (2, "Ctrl", "7"),
            (3, "Ctrl", "5"),
        }

    def test_without_a_project_there_are_no_sessions(self):
        assert MetadataManager.get_completed_sessions(None) == set()


class TestSessionDetailsAndGroups:
    def test_last_session_needs_a_project_path(self):
        project: dict = {}

        MetadataManager.save_last_session_details(
            2, "A", project_data=project, project_path=None, save_project_fn=pytest.fail
        )

        assert project == {}
        assert MetadataManager.get_last_session_details({}) == (None, None)
        assert MetadataManager.get_last_session_details({"last_selected_day": 3}) == (3, None)

    def test_groups_come_from_project_videos_aquariums_and_csv(self):
        videos = [
            {"metadata": {"group": "Video"}},
            {
                "metadata": {},
                "multi_aquarium_outputs": {"0": {"group": "Tank"}, "1": {"group": ""}},
            },
        ]
        csv = pd.DataFrame({"group": ["Csv", None, "Video"]})

        groups = MetadataManager.get_available_groups(
            {"groups": ["Wizard", "", None]}, csv, lambda: videos
        )

        assert groups == ["Csv", "Tank", "Video", "Wizard"]
        assert MetadataManager.get_available_groups({}, None, lambda: None) == []
