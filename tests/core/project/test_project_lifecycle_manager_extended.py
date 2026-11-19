"""
Extended unit tests for ProjectLifecycleManager in core/project/project_lifecycle_manager.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import structlog

from zebtrack.core.exceptions import ProjectInvalidError
from zebtrack.core.project.project_lifecycle_manager import ProjectLifecycleManager


class TestProjectLifecycleManagerExtended:
    """Test ProjectLifecycleManager validation, load, and save operations."""

    def test_validate_project_parameters_valid(self):
        # Should not raise
        ProjectLifecycleManager.validate_project_parameters(
            num_aquariums=2,
            animals_per_aquarium=1,
            aquarium_width_cm=30.0,
            aquarium_height_cm=20.0,
            analysis_interval_frames=2,
            display_interval_frames=5,
            camera_index=0,
            project_type="Pre-recorded",
            video_files=["video.mp4"],
        )

    def test_validate_project_parameters_invalid_aquariums_raises(self):
        with pytest.raises(ValueError, match="num_aquariums must be >= 1"):
            ProjectLifecycleManager.validate_project_parameters(
                num_aquariums=0,
                animals_per_aquarium=1,
                aquarium_width_cm=30.0,
                aquarium_height_cm=20.0,
                analysis_interval_frames=1,
                display_interval_frames=1,
                camera_index=0,
                project_type="Live",
                video_files=None,
            )

        with pytest.raises(ValueError, match="num_aquariums must be <= 100"):
            ProjectLifecycleManager.validate_project_parameters(
                num_aquariums=101,
                animals_per_aquarium=1,
                aquarium_width_cm=30.0,
                aquarium_height_cm=20.0,
                analysis_interval_frames=1,
                display_interval_frames=1,
                camera_index=0,
                project_type="Live",
                video_files=None,
            )

    def test_validate_project_parameters_invalid_dimensions_raises(self):
        with pytest.raises(ValueError, match="aquarium_width_cm must be >= 0"):
            ProjectLifecycleManager.validate_project_parameters(
                num_aquariums=1,
                animals_per_aquarium=1,
                aquarium_width_cm=-5.0,
                aquarium_height_cm=20.0,
                analysis_interval_frames=1,
                display_interval_frames=1,
                camera_index=0,
                project_type="Live",
                video_files=None,
            )

        with pytest.raises(ValueError, match="aquarium_width_cm must be <= 500"):
            ProjectLifecycleManager.validate_project_parameters(
                num_aquariums=1,
                animals_per_aquarium=1,
                aquarium_width_cm=600.0,
                aquarium_height_cm=20.0,
                analysis_interval_frames=1,
                display_interval_frames=1,
                camera_index=0,
                project_type="Live",
                video_files=None,
            )

    def test_validate_project_parameters_invalid_intervals_and_types(self):
        with pytest.raises(ValueError, match="analysis_interval_frames must be >= 1"):
            ProjectLifecycleManager.validate_project_parameters(
                num_aquariums=1,
                animals_per_aquarium=1,
                aquarium_width_cm=30.0,
                aquarium_height_cm=20.0,
                analysis_interval_frames=0,
                display_interval_frames=1,
                camera_index=0,
                project_type="Live",
                video_files=None,
            )

        with pytest.raises(ValueError, match="project_type must be one of"):
            ProjectLifecycleManager.validate_project_parameters(
                num_aquariums=1,
                animals_per_aquarium=1,
                aquarium_width_cm=30.0,
                aquarium_height_cm=20.0,
                analysis_interval_frames=1,
                display_interval_frames=1,
                camera_index=0,
                project_type="CustomNonExistent",
                video_files=None,
            )

    def test_save_project_data_no_path_raises(self):
        with pytest.raises(ProjectInvalidError, match="the project path is not set"):
            ProjectLifecycleManager.save_project_data(
                project_path=None,
                project_data={},
                save_config_fn=MagicMock(),
            )

    def test_save_project_data_success(self, tmp_path: Path):
        mock_save = MagicMock()
        data = {"project_name": "TestProj"}
        ProjectLifecycleManager.save_project_data(
            project_path=tmp_path,
            project_data=data,
            save_config_fn=mock_save,
        )
        mock_save.assert_called_once_with(tmp_path, data)

    def test_load_project_data_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(ProjectInvalidError, match="not found in the selected directory"):
            ProjectLifecycleManager.load_project_data(
                project_path=tmp_path,
                load_config_fn=MagicMock(),
                apply_migrations_fn=MagicMock(),
            )

    def test_load_project_data_success(self, tmp_path: Path):
        # Create empty config file
        (tmp_path / "project_config.json").write_text("{}")

        mock_load = MagicMock(return_value={"version": "3.3", "project_name": "MyProj"})
        migrated_ret: tuple[dict[str, Any], bool, list[str]] = (
            {"version": "3.3", "project_name": "MyProj"},
            False,
            [],
        )
        mock_migrate = MagicMock(return_value=migrated_ret)

        data, migrated, fields = ProjectLifecycleManager.load_project_data(
            project_path=tmp_path,
            load_config_fn=mock_load,
            apply_migrations_fn=mock_migrate,
        )

        assert data["project_name"] == "MyProj"
        assert migrated is False
        assert fields == []


# ---------------------------------------------------------------------------
# v8 additive migrations (ADR-012)
# ---------------------------------------------------------------------------


def _migrate(data: dict[str, Any]) -> tuple[dict[str, Any], bool, list[str]]:
    return ProjectLifecycleManager.apply_project_migrations(data, MagicMock())


class TestV8Migrations:
    def test_model_selection_is_backfilled_from_the_wizard_metadata(self):
        data: dict[str, Any] = {
            "_wizard_metadata": {
                "model_selection": {
                    "aquarium_method": "seg",
                    "animal_method": "seg",
                    "use_openvino": True,
                }
            }
        }

        migrated, applied, fields = _migrate(data)

        assert migrated["model_selection"] == {"aquarium_method": "seg", "animal_method": "seg"}
        assert applied is True
        assert "model_selection" in fields

    def test_existing_model_selection_is_never_overwritten(self):
        data: dict[str, Any] = {
            "model_selection": {"aquarium_method": "det", "animal_method": "det"},
            "_wizard_metadata": {"model_selection": {"animal_method": "seg"}},
        }

        migrated, _applied, fields = _migrate(data)

        assert migrated["model_selection"] == {"aquarium_method": "det", "animal_method": "det"}
        assert "model_selection" not in fields

    @pytest.mark.parametrize(
        "wizard",
        [None, {}, {"model_selection": None}, {"model_selection": {"animal_method": "bogus"}}],
    )
    def test_nothing_usable_in_the_wizard_leaves_the_global_fallback(self, wizard):
        data: dict[str, Any] = {} if wizard is None else {"_wizard_metadata": wizard}

        migrated, _applied, _fields = _migrate(data)

        assert "model_selection" not in migrated

    def test_inert_defaults_for_window_and_class_roles(self):
        data: dict[str, Any] = {
            "external_trigger_mode": True,
            "model_overrides": {
                "active_weight": "w.pt",
                "use_openvino": None,
                "device": "AUTO",
                "slot_weights": {"det:zebrafish": "w.pt"},
            },
        }

        migrated, _applied, fields = _migrate(data)

        assert migrated["analysis_window"] is None
        assert migrated["model_overrides"]["class_roles"] is None
        assert migrated["model_overrides"]["class_roles_weight_sha256"] is None
        assert migrated["model_overrides"]["slot_weights"] == {"det:zebrafish": "w.pt"}
        assert migrated["external_trigger_mode"] is True
        assert "analysis_window" in fields

    def test_existing_window_and_roles_are_kept(self):
        window = {"start": {"kind": "manual"}}
        data: dict[str, Any] = {
            "analysis_window": window,
            "model_overrides": {
                "class_roles": {"rat": "subject"},
                "class_roles_weight_sha256": "a" * 64,
                "slot_weights": {},
            },
        }

        migrated, _applied, _fields = _migrate(data)

        assert migrated["analysis_window"] == window
        assert migrated["model_overrides"]["class_roles"] == {"rat": "subject"}
        assert migrated["model_overrides"]["class_roles_weight_sha256"] == "a" * 64

    def test_new_projects_start_with_the_v8_keys(self, tmp_path: Path):
        data = ProjectLifecycleManager.create_new_project(
            tmp_path / "proj",
            "Pre-recorded",
            None,
            lambda: {"name": "default", "settings": {}},
            lambda *_a, **_k: None,
            lambda: None,
        )

        assert data["analysis_window"] is None
        assert data["model_overrides"]["class_roles"] is None
        assert data["model_overrides"]["class_roles_weight_sha256"] is None


# ---------------------------------------------------------------------------
# TASK-087: typed errors on real files, upper bounds, snapshot, legacy fixture.
# ---------------------------------------------------------------------------

BASE_PARAMS: dict[str, Any] = {
    "num_aquariums": 1,
    "animals_per_aquarium": 1,
    "aquarium_width_cm": 0.0,
    "aquarium_height_cm": 0.0,
    "analysis_interval_frames": 10,
    "display_interval_frames": 10,
    "camera_index": 0,
    "project_type": "live",
    "video_files": None,
}

LEGACY_7_2 = Path(__file__).resolve().parents[2] / "fixtures" / "legacy" / "project_7_2_0"


class TestTypedErrors:
    def test_corrupt_config_raises_project_invalid_with_the_cause(self, tmp_path):
        (tmp_path / "project_config.json").write_text("{broken", encoding="utf-8")

        def read(path):
            return json.loads((Path(path) / "project_config.json").read_text(encoding="utf-8"))

        with pytest.raises(ProjectInvalidError) as excinfo:
            ProjectLifecycleManager.load_project_data(tmp_path, read, lambda d, ctx: (d, False, []))

        assert isinstance(excinfo.value.__cause__, json.JSONDecodeError)

    @pytest.mark.parametrize(
        "error", [PermissionError("ro"), OSError("io"), TypeError("set"), RuntimeError("x")]
    )
    def test_every_save_failure_becomes_project_invalid(self, tmp_path, error):
        def write(path, data):
            raise error

        with pytest.raises(ProjectInvalidError) as excinfo:
            ProjectLifecycleManager.save_project_data(tmp_path, {}, write)

        assert excinfo.value.__cause__ is error

    def test_unserialisable_data_on_a_real_save(self, tmp_path):
        from zebtrack.core.project.project_service import ProjectService

        with pytest.raises(ProjectInvalidError):
            ProjectLifecycleManager.save_project_data(
                tmp_path, {"bad": {1, 2}}, ProjectService().save_project_config
            )

    def test_directory_that_cannot_be_created(self, tmp_path):
        blocker = tmp_path / "file"
        blocker.write_text("")

        with pytest.raises(ProjectInvalidError):
            ProjectLifecycleManager.create_new_project(
                blocker / "proj", "Live", None, dict, lambda *a, **k: None, lambda: None
            )


class TestUpperBounds:
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("num_aquariums", 101),
            ("animals_per_aquarium", 0),
            ("animals_per_aquarium", 101),
            ("aquarium_width_cm", 500.5),
            ("aquarium_height_cm", -0.1),
            ("aquarium_height_cm", 501.0),
            ("analysis_interval_frames", 31),
            ("display_interval_frames", 0),
            ("display_interval_frames", 31),
            ("camera_index", -1),
            ("camera_index", 11),
            ("project_type", "batch"),
        ],
    )
    def test_out_of_range_values_are_refused(self, field, value):
        with pytest.raises(ValueError):
            ProjectLifecycleManager.validate_project_parameters(**{**BASE_PARAMS, field: value})

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("num_aquariums", 100),
            ("animals_per_aquarium", 100),
            ("aquarium_width_cm", 500.0),
            ("aquarium_height_cm", 0.0),
            ("analysis_interval_frames", 30),
            ("display_interval_frames", 1),
            ("camera_index", 10),
            ("project_type", "PRE-RECORDED"),
        ],
    )
    def test_boundary_values_are_accepted(self, field, value):
        ProjectLifecycleManager.validate_project_parameters(**{**BASE_PARAMS, field: value})


class TestSettingsSnapshot:
    def test_real_settings_are_written_as_yaml(self, tmp_path):
        import yaml

        class _Settings:
            def model_dump_json(self):
                return json.dumps({"camera": {"index": 2}, "z": [1, 2]})

        assert ProjectLifecycleManager.save_settings_snapshot(tmp_path, _Settings()) is True

        written = yaml.safe_load((tmp_path / "config_snapshot.yaml").read_text(encoding="utf-8"))
        assert written == {"camera": {"index": 2}, "z": [1, 2]}

    def test_absent_or_fake_settings_are_skipped_without_a_file(self, tmp_path):
        class _NoDump:
            model_dump_json = None

        class _NotString:
            def model_dump_json(self):
                return 42

        assert ProjectLifecycleManager.save_settings_snapshot(None, object()) is False
        for settings in (None, _NoDump(), _NotString()):
            assert ProjectLifecycleManager.save_settings_snapshot(tmp_path, settings) is True
        assert not (tmp_path / "config_snapshot.yaml").exists()

    def test_unparsable_dump_reports_false(self, tmp_path):
        class _Broken:
            def model_dump_json(self):
                return "{not json"

        assert ProjectLifecycleManager.save_settings_snapshot(tmp_path, _Broken()) is False


class TestBatchesAndWizardRegex:
    def test_string_entries_and_empty_batches(self, tmp_path):
        project: dict = {}

        ProjectLifecycleManager.add_video_batch(project, [])
        assert project == {}

        ProjectLifecycleManager.add_video_batch(project, ["C:\\v\\a.mp4"])  # type: ignore[list-item]

        (entry,) = project["batches"][0]["videos"]
        assert entry["path"] == Path("C:\\v\\a.mp4").as_posix()
        assert (entry["status"], entry["has_complete_data"]) == ("pending", False)
        assert "metadata" not in entry

    def test_wizard_regex_is_stored_as_a_disabled_multi_aquarium_config(self, tmp_path):
        data = ProjectLifecycleManager.create_new_project(
            tmp_path / "p",
            "Pre-recorded",
            None,
            dict,
            lambda *a, **k: None,
            lambda: None,
            _wizard_metadata={
                "custom_regex_patterns": {
                    "group_pattern": "G(\\d+)",
                    "day_pattern": "D(\\d+)",
                    "subject_pattern": "S(\\d+)",
                }
            },
        )

        assert data["calibration"]["multi_aquarium"] == {
            "enabled": False,
            "regex_pattern": "G(?P<group>\\d+)_D(?P<day>\\d+)_S(?P<subject>\\d+)",
            "regex_group_field": "group",
            "regex_subject_field": "subject",
            "regex_day_field": "day",
            "aquarium_configs": [],
        }

    @pytest.mark.parametrize("patterns", [None, "text", {}, {"group_pattern": ""}])
    def test_wizard_without_usable_patterns_stores_nothing(self, tmp_path, patterns):
        data = ProjectLifecycleManager.create_new_project(
            tmp_path / "p",
            "Live",
            None,
            dict,
            lambda *a, **k: None,
            lambda: None,
            _wizard_metadata={"custom_regex_patterns": patterns, "x": 1},
        )

        assert "multi_aquarium" not in data["calibration"]
        assert data["_wizard_metadata"]["x"] == 1

    def test_tracker_flag_falls_back_to_the_settings_without_a_count(self):
        settings = type("S", (), {"tracking": type("T", (), {"use_single_subject_tracker": True})})

        data, applied, fields = ProjectLifecycleManager.apply_project_migrations(
            {"tracking": "corrupt"}, structlog.get_logger(), settings_obj=settings
        )

        assert applied is True
        assert data["tracking"] == {"use_single_subject_tracker": True}
        assert "tracking" in fields
        assert data["analysis_profiles"] == [
            {"name": "default", "description": "Default analysis profile", "settings": {}}
        ]


class TestLegacyFixture:
    def test_7_2_project_migrates_without_touching_the_fixture(self, tmp_path):
        import shutil

        copy = tmp_path / "legacy"
        shutil.copytree(LEGACY_7_2, copy)
        original = (LEGACY_7_2 / "project_config.json").read_bytes()
        from zebtrack.core.project.project_manager import ProjectManager

        pm = ProjectManager(settings_obj=None)
        pm.load_project(copy)

        assert (LEGACY_7_2 / "project_config.json").read_bytes() == original
        reloaded = json.loads((copy / "project_config.json").read_text(encoding="utf-8"))
        for key in ("analysis_window", "file_hash", "session_duration_overrides"):
            assert key in reloaded
        assert reloaded["model_overrides"]["class_roles"] is None
        assert pm.project_data["analysis_window"] is None
