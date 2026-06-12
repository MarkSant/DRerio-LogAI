"""Testes unitários para ``MetadataManager`` (métodos estáticos, sem estado).

Cobre carregamento de metadata.csv, busca de metadados por experimento (ordem
de prioridade CSV > project_data > regex), persistência de estado do detector,
normalização de thresholds e varredura de sessões concluídas.
"""

from __future__ import annotations

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
