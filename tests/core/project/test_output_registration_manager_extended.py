"""
Extended unit tests for OutputRegistrationManager in project/output_registration_manager.py.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

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
