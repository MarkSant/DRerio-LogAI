"""
Extended unit tests for MetadataManager.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from zebtrack.core.project.metadata_manager import MetadataManager


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
