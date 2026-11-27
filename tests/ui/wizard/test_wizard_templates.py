import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from zebtrack.core.conditions.presets import barnes_maze_preset, external_trigger_preset
from zebtrack.core.services.experiment_profile import (
    AnimalModel,
    ProtocolId,
    resolve_experiment_profile,
)
from zebtrack.ui.wizard import templates
from zebtrack.ui.wizard.templates import (
    NOTE_ANALYSIS_WINDOW_DROPPED,
    NOTE_CLASS_ROLES_DROPPED,
    NOTE_EXPERIMENT_PROFILE_NORMALISED,
    NOTE_EXTERNAL_TRIGGER_CONVERTED,
    TEMPLATE_SCHEMA_VERSION,
    TemplateManager,
    builtin_templates_dir,
    format_template_banner,
    migrate_template,
    protocol_window_spec,
    template_migration_note_text,
)


def _need(value):
    """A widget the test just built must exist; narrows ``X | None`` for mypy."""
    assert value is not None
    return value


_TRIGGER_WINDOW = external_trigger_preset().model_dump(mode="json", by_alias=True)


class TestTemplateManager:
    @pytest.fixture(autouse=True)
    def setup(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.templates_dir = Path(self._tmpdir.name)
        self.manager = TemplateManager(templates_dir=self.templates_dir)
        yield
        self._tmpdir.cleanup()

    def test_save_template_to_custom_path(self):
        destination = self.templates_dir / "custom" / "meu_template.json"

        payload = {
            "project_type": "experimental",
            "num_aquariums": 2,
        }

        saved = self.manager.save_template(
            "Template Manual",
            payload,
            destination_path=destination,
        )

        assert saved
        assert destination.exists()

        with open(destination, encoding="utf-8") as handle:
            data = json.load(handle)

        assert data["name"] == "Template Manual"
        assert data["project_type"] == "experimental"

    def test_load_template_from_path(self):
        """The raw loader returns the file verbatim -- including legacy values.

        ``"exploratory"`` is a project type this wizard no longer offers, but
        the loader must not silently rewrite a user's file. Normalization to a
        selectable type happens later, in ``DiscoveryStep`` (see
        ``ProjectType.normalize``).
        """
        template_path = self.templates_dir / "externo.json"
        template_path.write_text(
            json.dumps({"name": "Externo", "project_type": "exploratory"}),
            encoding="utf-8",
        )

        loaded = self.manager.load_template_from_path(template_path)
        assert loaded is not None
        assert loaded["name"] == "Externo"
        assert loaded["project_type"] == "exploratory"

    def test_save_template_includes_live_capture_and_behavioral(self):
        """Schema v3: LiveConfig (incl. camera) + behavioral_analysis are persisted.

        The camera is safe to store because LiveConfigStep reconciles it against
        the host hardware on load (graceful fallback when absent).
        """
        payload = {
            "project_type": "live",
            # Live capture block (Step 3), camera included.
            "camera_index": 2,
            "camera_friendly_name": "Cam Y",
            "use_arduino": True,
            "arduino_port": "COM7",
            "external_trigger_mode": True,
            "use_timed_recording": True,
            "recording_duration_s": 600.0,
            "use_countdown": True,
            "countdown_duration_s": 15,
            "preserve_real_aquarium_shape": True,
            "selected_live_mode": "MULTI",
            # Behavioral analysis (Step 4).
            "behavioral_analysis": {"freezing": True},
            # Experimental design (Step 2).
            "experiment_days": 5,
            "num_groups": 3,
            "subjects_per_group": 6,
            "group_names": ["g1", "g2", "g3"],
        }

        assert self.manager.save_template("Live T", payload)

        with open(self.templates_dir / "live_t.json", encoding="utf-8") as handle:
            data = json.load(handle)

        assert data["schema_version"] == 5
        for key, expected in payload.items():
            assert data[key] == expected, f"{key!r} not persisted correctly"


@pytest.mark.gui
class TestApplyTemplateData:
    """DiscoveryStep._apply_template_data must seed wizard_data with every
    step's keys so steps 2-4 repopulate from a loaded template."""

    @pytest.fixture(autouse=True)
    def setup(self, wizard_dependencies):
        self.root = wizard_dependencies["root"]

    def test_apply_template_populates_design_live_and_behavioral_keys(self):
        from zebtrack.ui.wizard.discovery_step import DiscoveryStep

        wizard_data: dict = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        template = {
            "name": "T",
            "project_type": "live",
            "experiment_days": 3,
            "num_groups": 2,
            "subjects_per_group": 4,
            "group_names": ["A", "B"],
            "camera_index": 1,
            "camera_friendly_name": "Cam X",
            "use_arduino": True,
            "arduino_port": "COM5",
            "external_trigger_mode": True,
            "use_timed_recording": False,
            "recording_duration_s": 120.0,
            "use_countdown": False,
            "countdown_duration_s": 5,
            "preserve_real_aquarium_shape": True,
            "selected_live_mode": "SINGLE",
            "behavioral_analysis": {"enabled": True},
            # v4: the legacy trigger flag is taken verbatim (no conversion).
            "schema_version": 4,
        }

        step._apply_template_data(template, "T.json")

        expected_keys = [
            "experiment_days",
            "num_groups",
            "subjects_per_group",
            "group_names",
            "camera_index",
            "camera_friendly_name",
            "use_arduino",
            "arduino_port",
            "external_trigger_mode",
            "use_timed_recording",
            "recording_duration_s",
            "use_countdown",
            "countdown_duration_s",
            "preserve_real_aquarium_shape",
            "selected_live_mode",
            "behavioral_analysis",
        ]
        for key in expected_keys:
            assert wizard_data[key] == template[key], f"{key!r} not applied to wizard_data"

    def test_builtin_rodent_template_prefills_the_behavioural_widget(self):
        """#695: loading the shipped template fills the calibration step's widget."""
        from zebtrack.ui.components.behavioral_config_widget import BehavioralConfigWidget
        from zebtrack.ui.wizard.discovery_step import DiscoveryStep
        from zebtrack.ui.wizard.templates import RODENT_TOP_DOWN_TEMPLATE, builtin_templates_dir

        path = builtin_templates_dir() / RODENT_TOP_DOWN_TEMPLATE
        wizard_data: dict = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()
        step._apply_template_data(json.loads(path.read_text(encoding="utf-8")), path)

        widget = BehavioralConfigWidget(self.root)
        widget.set_values(wizard_data["behavioral_analysis"])
        values = widget.get_values()

        assert values["aquarium_perspective"] == "top_down"
        assert values["geotaxis_enabled"] is False
        assert values["thigmotaxis_distance_cm"] == 15.0
        assert values["max_plausible_speed_cm_s"] == 100.0
        assert widget.validate() == (True, [])

    def test_v3_trigger_template_arrives_as_an_analysis_window(self):
        from zebtrack.ui.wizard.discovery_step import DiscoveryStep

        wizard_data: dict = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        step._apply_template_data(
            {
                "name": "Old",
                "schema_version": 3,
                "use_arduino": True,
                "external_trigger_mode": True,
            },
            "Old.json",
        )

        assert wizard_data["external_trigger_mode"] is False
        assert wizard_data["analysis_window"] == _TRIGGER_WINDOW
        assert wizard_data["template_metadata"]["migration_notes"] == [
            NOTE_EXTERNAL_TRIGGER_CONVERTED
        ]
        assert wizard_data["template_metadata"]["schema_version"] == 3

    def test_loading_a_template_without_window_clears_the_previous_one(self):
        from zebtrack.ui.wizard.discovery_step import DiscoveryStep

        wizard_data: dict = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()
        step._apply_template_data(
            {"schema_version": 3, "use_arduino": True, "external_trigger_mode": True}, "a.json"
        )

        step._apply_template_data({"schema_version": 4, "analysis_window": None}, "b.json")

        assert wizard_data["analysis_window"] is None
        assert "migration_notes" not in wizard_data["template_metadata"]

    def test_v5_class_roles_reach_wizard_data(self):
        from zebtrack.ui.wizard.discovery_step import DiscoveryStep

        wizard_data: dict = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        step._apply_template_data(
            {"schema_version": 5, "model_overrides": {"class_roles": {"Rat": "subject"}}},
            "rat.json",
        )

        assert wizard_data["template_class_roles"] == {
            "class_roles": {"rat": "subject"},
            "class_roles_weight_sha256": None,
        }

    def test_v4_template_clears_the_previous_class_roles(self):
        from zebtrack.ui.wizard.discovery_step import DiscoveryStep

        wizard_data: dict = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()
        step._apply_template_data(
            {"schema_version": 5, "model_overrides": {"class_roles": {"rat": "subject"}}},
            "a.json",
        )

        step._apply_template_data({"schema_version": 4, "name": "Old"}, "old.json")

        assert wizard_data["template_class_roles"] is None
        assert wizard_data["template_metadata"]["schema_version"] == 4


class TestFormatTemplateBanner:
    def test_banner_with_name_and_path(self):
        banner = format_template_banner(
            {
                "name": "Template Banner",
                "path": "C:/tmp/template_banner.json",
            }
        )

        assert "Template Banner" in banner
        assert "template_banner.json" in banner

    def test_banner_without_metadata(self):
        assert format_template_banner(None) == ""
        assert format_template_banner({}) == ""


class TestSaveTemplateAnalysisWindow:
    def test_window_is_saved_with_the_template(self, tmp_path: Path):
        manager = TemplateManager(templates_dir=tmp_path)
        window = barnes_maze_preset().model_dump(mode="json", by_alias=True)

        assert manager.save_template("Barnes", {"analysis_window": window})

        data = json.loads((tmp_path / "barnes.json").read_text(encoding="utf-8"))
        assert data["schema_version"] == TEMPLATE_SCHEMA_VERSION == 5
        assert data["analysis_window"] == window

    def test_saved_template_loads_back_unchanged(self, tmp_path: Path):
        manager = TemplateManager(templates_dir=tmp_path)
        window = barnes_maze_preset().model_dump(mode="json", by_alias=True)
        manager.save_template("Barnes", {"analysis_window": window})

        migrated, notes = migrate_template(manager.load_template("Barnes") or {})

        assert migrated["analysis_window"] == window
        assert notes == ()


class TestMigrateTemplate:
    """Pure v3 -> v4 migration (no Tk)."""

    def test_v3_external_trigger_becomes_an_arduino_window(self):
        template: dict[str, Any] = {
            "schema_version": 3,
            "use_arduino": True,
            "external_trigger_mode": True,
        }

        migrated, notes = migrate_template(template)

        assert migrated["analysis_window"] == _TRIGGER_WINDOW
        assert migrated["analysis_window"]["start"] == {
            "kind": "external",
            "source": "arduino",
            "code": 1,
        }
        assert migrated["analysis_window"]["stop"]["code"] == 0
        assert migrated["external_trigger_mode"] is False
        assert notes == (NOTE_EXTERNAL_TRIGGER_CONVERTED,)

    def test_input_is_not_modified(self):
        template: dict[str, Any] = {"schema_version": 3, "external_trigger_mode": True}

        migrate_template(template)

        assert template == {"schema_version": 3, "external_trigger_mode": True}

    def test_schema_version_is_kept_as_found(self):
        migrated, _notes = migrate_template({"schema_version": 3, "external_trigger_mode": True})

        assert migrated["schema_version"] == 3

    def test_v3_without_trigger_has_no_window(self):
        migrated, notes = migrate_template(
            {"schema_version": 3, "external_trigger_mode": False, "use_arduino": True}
        )

        assert migrated["analysis_window"] is None
        assert migrated["external_trigger_mode"] is False
        assert notes == ()

    def test_v3_stray_window_is_replaced(self):
        """v3 had no window; a key there is not trusted."""
        migrated, _notes = migrate_template(
            {"schema_version": 3, "analysis_window": {"version": 1}}
        )

        assert migrated["analysis_window"] is None

    @pytest.mark.parametrize("version", [None, "x", True, 1, 2])
    def test_unversioned_or_older_templates_are_legacy(self, version: Any):
        template: dict[str, Any] = {"external_trigger_mode": True}
        if version is not None:
            template["schema_version"] = version

        migrated, notes = migrate_template(template)

        assert migrated["analysis_window"] == _TRIGGER_WINDOW
        assert notes == (NOTE_EXTERNAL_TRIGGER_CONVERTED,)

    def test_v4_window_is_kept(self):
        window = barnes_maze_preset().model_dump(mode="json", by_alias=True)

        migrated, notes = migrate_template({"schema_version": 4, "analysis_window": window})

        assert migrated["analysis_window"] == window
        assert notes == ()

    def test_v4_trigger_flag_is_not_converted(self):
        """A v4 file wrote its flag knowing windows exist; it is left alone."""
        migrated, notes = migrate_template(
            {"schema_version": 4, "external_trigger_mode": True, "analysis_window": None}
        )

        assert migrated["external_trigger_mode"] is True
        assert migrated["analysis_window"] is None
        assert notes == ()

    def test_v4_without_window_key(self):
        migrated, notes = migrate_template({"schema_version": 4})

        assert migrated["analysis_window"] is None
        assert notes == ()

    def test_v4_unreadable_window_is_dropped_with_a_note(self):
        migrated, notes = migrate_template(
            {"schema_version": 4, "analysis_window": {"version": 1, "start": {"kind": "?"}}}
        )

        assert migrated["analysis_window"] is None
        assert notes == (NOTE_ANALYSIS_WINDOW_DROPPED,)

    def test_v4_window_is_normalized(self):
        """A hand-written window gains its defaults: the project stores one canonical form."""
        migrated, _notes = migrate_template(
            {
                "schema_version": 4,
                "analysis_window": {"start": {"kind": "external", "source": "manual"}},
            }
        )

        assert migrated["analysis_window"] == {
            "version": 1,
            "start": {"kind": "external", "source": "manual", "code": None},
            "stop": None,
            "on_start_not_met": "whole_recording",
            "on_stop": "mark",
        }

    def test_note_texts(self):
        converted = template_migration_note_text(NOTE_EXTERNAL_TRIGGER_CONVERTED)
        assert converted.startswith("This template used 'External Trigger Mode'.")
        assert "code 1 starts it, code 0 stops it" in converted
        assert template_migration_note_text(NOTE_ANALYSIS_WINDOW_DROPPED).startswith(
            "The template's analysis window could not be read"
        )
        assert template_migration_note_text("unknown_note") == "unknown_note"


_BARNES_ROLES = {
    "arena": "arena",
    "experimenter": "context",
    "rat": "subject",
    "start_box": "context",
}
_SHA = "ab" * 32


class TestTemplateClassRoles:
    """#646: v5 templates keep the class roles BY NAME, with the weight's sha."""

    def _saved(self, tmp_path: Path, wizard_data: dict[str, Any]) -> dict[str, Any]:
        manager = TemplateManager(templates_dir=tmp_path)
        assert manager.save_template("Roles", wizard_data)
        return json.loads((tmp_path / "roles.json").read_text(encoding="utf-8"))

    def test_edited_roles_are_saved_by_normalised_name_with_the_sha(self, tmp_path: Path):
        data = self._saved(
            tmp_path,
            {
                "class_roles": {" Rat ": "subject", "ARENA": "arena"},
                "class_roles_weight_sha256": _SHA,
            },
        )

        assert data["model_overrides"] == {
            "class_roles": {"rat": "subject", "arena": "arena"},
            "class_roles_weight_sha256": _SHA,
        }

    def test_loaded_template_roles_are_carried_forward(self, tmp_path: Path):
        block = {"class_roles": _BARNES_ROLES, "class_roles_weight_sha256": None}
        data = self._saved(tmp_path, {"class_roles": None, "template_class_roles": block})

        assert data["model_overrides"] == block

    def test_edited_roles_win_over_the_loaded_template(self, tmp_path: Path):
        data = self._saved(
            tmp_path,
            {
                "class_roles": {"mouse": "subject"},
                "class_roles_weight_sha256": _SHA.upper(),
                "template_class_roles": {"class_roles": _BARNES_ROLES},
            },
        )

        assert data["model_overrides"] == {
            "class_roles": {"mouse": "subject"},
            "class_roles_weight_sha256": _SHA,
        }

    def test_unreadable_edited_roles_fall_back_to_the_template(self, tmp_path: Path):
        data = self._saved(
            tmp_path,
            {
                "class_roles": {"rat": "boss"},
                "template_class_roles": {"class_roles": {"rat": "subject"}},
            },
        )

        assert data["model_overrides"]["class_roles"] == {"rat": "subject"}

    def test_no_roles_save_none(self, tmp_path: Path):
        assert self._saved(tmp_path, {"project_type": "live"})["model_overrides"] is None

    def test_saved_roles_load_back_unchanged(self, tmp_path: Path):
        manager = TemplateManager(templates_dir=tmp_path)
        manager.save_template(
            "Barnes", {"class_roles": _BARNES_ROLES, "class_roles_weight_sha256": _SHA}
        )

        migrated, notes = migrate_template(manager.load_template("Barnes") or {})

        assert migrated["model_overrides"] == {
            "class_roles": _BARNES_ROLES,
            "class_roles_weight_sha256": _SHA,
        }
        assert notes == ()

    def test_old_v4_template_still_loads(self, tmp_path: Path):
        """A v4 file on disk loads through the same path, with no class roles."""
        window = barnes_maze_preset().model_dump(mode="json", by_alias=True)
        path = tmp_path / "old_v4.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 4,
                    "name": "Old v4",
                    "project_type": "experimental",
                    "num_aquariums": 2,
                    "analysis_window": window,
                }
            ),
            encoding="utf-8",
        )

        loaded = TemplateManager(templates_dir=tmp_path).load_template_from_path(path)
        assert loaded is not None
        migrated, notes = migrate_template(loaded)

        assert migrated["model_overrides"] is None
        assert migrated["analysis_window"] == window
        assert migrated["num_aquariums"] == 2
        assert migrated["schema_version"] == 4
        assert notes == ()

    def test_v4_stray_roles_are_not_trusted(self):
        migrated, notes = migrate_template(
            {"schema_version": 4, "model_overrides": {"class_roles": {"rat": "subject"}}}
        )

        assert migrated["model_overrides"] is None
        assert notes == ()

    def test_v5_roles_are_normalised(self):
        migrated, notes = migrate_template(
            {
                "schema_version": 5,
                "model_overrides": {
                    "class_roles": {"Start Box": "context", "RAT": "subject"},
                    "class_roles_weight_sha256": " " + _SHA.upper() + " ",
                },
            }
        )

        assert migrated["model_overrides"] == {
            "class_roles": {"start_box": "context", "rat": "subject"},
            "class_roles_weight_sha256": _SHA,
        }
        assert notes == ()

    @pytest.mark.parametrize("sha", ["abc", 42, None, "z" * 64, "a" * 63])
    def test_v5_invalid_sha_is_dropped_not_the_roles(self, sha: Any):
        migrated, notes = migrate_template(
            {
                "schema_version": 5,
                "model_overrides": {
                    "class_roles": {"rat": "subject"},
                    "class_roles_weight_sha256": sha,
                },
            }
        )

        assert migrated["model_overrides"] == {
            "class_roles": {"rat": "subject"},
            "class_roles_weight_sha256": None,
        }
        assert notes == ()

    @pytest.mark.parametrize(
        "block",
        [
            {"class_roles": {"rat": "boss"}},
            {"class_roles": {}},
            {"class_roles": ["rat"]},
            "rat",
        ],
    )
    def test_v5_unreadable_roles_are_dropped_with_a_note(self, block: Any):
        migrated, notes = migrate_template({"schema_version": 5, "model_overrides": block})

        assert migrated["model_overrides"] is None
        assert notes == (NOTE_CLASS_ROLES_DROPPED,)

    @pytest.mark.parametrize("block", [None, {}, {"class_roles": None}])
    def test_v5_without_roles(self, block: Any):
        template: dict[str, Any] = {"schema_version": 5}
        if block is not None:
            template["model_overrides"] = block

        migrated, notes = migrate_template(template)

        assert migrated["model_overrides"] is None
        assert notes == ()

    def test_window_and_roles_notes_are_both_kept(self):
        migrated, notes = migrate_template(
            {
                "schema_version": 5,
                "analysis_window": {"version": 1, "start": {"kind": "?"}},
                "model_overrides": {"class_roles": {"rat": "boss"}},
            }
        )

        assert notes == (NOTE_ANALYSIS_WINDOW_DROPPED, NOTE_CLASS_ROLES_DROPPED)
        assert migrated["analysis_window"] is None

    def test_roles_note_text(self):
        assert template_migration_note_text(NOTE_CLASS_ROLES_DROPPED).startswith(
            "The template's class roles could not be read"
        )


class TestBuiltinRodentTemplate:
    """#695: a shipped "rodent, top view" template carries the three rodent defaults."""

    @staticmethod
    def _rodent() -> dict[str, Any]:
        from zebtrack.ui.wizard.templates import RODENT_TOP_DOWN_TEMPLATE, builtin_templates_dir

        path = builtin_templates_dir() / RODENT_TOP_DOWN_TEMPLATE
        return json.loads(path.read_text(encoding="utf-8"))

    def test_it_lives_in_the_curated_resources_folder(self):
        from zebtrack.paths import repo_root
        from zebtrack.ui.wizard.templates import builtin_templates_dir

        assert builtin_templates_dir() == repo_root() / "resources" / "wizard_templates"

    def test_behavioural_block_is_the_rodent_one(self):
        migrated, notes = migrate_template(self._rodent())
        behavioural = migrated["behavioral_analysis"]

        assert notes == ()
        assert behavioural["aquarium_perspective"] == "top_down"
        assert behavioural["geotaxis_enabled"] is False
        assert 10.0 <= behavioural["thigmotaxis_distance_cm"] <= 20.0
        # A rat sprints well past the 50 cm/s zebrafish ceiling.
        assert behavioural["max_plausible_speed_cm_s"] > 50.0

    def test_behavioural_block_passes_the_wizard_model(self):
        from zebtrack.ui.wizard.models import BehavioralAnalysisData

        data = BehavioralAnalysisData.model_validate(self._rodent()["behavioral_analysis"])

        assert (
            data.max_plausible_speed_cm_s
            == self._rodent()["behavioral_analysis"]["max_plausible_speed_cm_s"]
        )

    def test_no_class_roles_are_invented_without_a_shipped_rodent_weight(self):
        migrated, _notes = migrate_template(self._rodent())

        assert migrated["schema_version"] == TEMPLATE_SCHEMA_VERSION
        assert migrated["model_overrides"] is None


class TestBuiltinTemplateInstall:
    """Curated templates reach the folder the wizard's Load dialog opens."""

    @staticmethod
    def _builtin(tmp_path: Path) -> Path:
        source = tmp_path / "builtin"
        source.mkdir()
        (source / "rodent.json").write_text(
            json.dumps({"name": "Rodent", "builtin_id": "rodent", "schema_version": 5}),
            encoding="utf-8",
        )
        (source / "legacy.json").write_text(json.dumps({"name": "Legacy"}), encoding="utf-8")
        return source

    def test_flagged_templates_are_installed_into_an_empty_folder(self, tmp_path):
        user_dir = tmp_path / "user"
        TemplateManager(templates_dir=user_dir, builtin_templates_dir=self._builtin(tmp_path))

        assert (user_dir / "rodent.json").exists()
        # Only templates that declare a builtin_id are shipped to users.
        assert not (user_dir / "legacy.json").exists()

    def test_an_existing_user_file_is_never_overwritten(self, tmp_path):
        user_dir = tmp_path / "user"
        user_dir.mkdir()
        (user_dir / "rodent.json").write_text('{"name": "Mine"}', encoding="utf-8")

        TemplateManager(templates_dir=user_dir, builtin_templates_dir=self._builtin(tmp_path))

        assert json.loads((user_dir / "rodent.json").read_text(encoding="utf-8")) == {
            "name": "Mine"
        }

    def test_a_deleted_builtin_stays_deleted(self, tmp_path):
        user_dir = tmp_path / "user"
        source = self._builtin(tmp_path)
        TemplateManager(templates_dir=user_dir, builtin_templates_dir=source)
        (user_dir / "rodent.json").unlink()

        TemplateManager(templates_dir=user_dir, builtin_templates_dir=source)

        assert not (user_dir / "rodent.json").exists()

    def test_an_explicit_folder_without_a_source_installs_nothing(self, tmp_path):
        TemplateManager(templates_dir=tmp_path)

        assert list(tmp_path.glob("*.json")) == []

    def test_a_missing_source_folder_is_not_an_error(self, tmp_path):
        user_dir = tmp_path / "user"

        manager = TemplateManager(templates_dir=user_dir, builtin_templates_dir=tmp_path / "nope")

        assert manager.list_templates() == []

    def test_the_shipped_rodent_template_is_flagged_for_install(self, tmp_path):
        from zebtrack.ui.wizard.templates import RODENT_TOP_DOWN_TEMPLATE, builtin_templates_dir

        user_dir = tmp_path / "user"
        TemplateManager(templates_dir=user_dir, builtin_templates_dir=builtin_templates_dir())

        assert (user_dir / RODENT_TOP_DOWN_TEMPLATE).exists()


class TestExperimentProfileInTemplates:
    """ADR-014: the profile rides in ``behavioral_analysis``; no schema bump."""

    def test_a_template_saved_before_the_profile_is_untouched(self):
        template: dict[str, Any] = {
            "schema_version": 5,
            "behavioral_analysis": {"aquarium_perspective": "lateral", "geotaxis_enabled": True},
            "analysis_interval_frames": 7,
        }

        migrated, notes = migrate_template(template)

        assert migrated["behavioral_analysis"] == template["behavioral_analysis"]
        assert migrated["analysis_interval_frames"] == 7
        assert notes == ()

    def test_a_template_without_a_behavioural_block_is_untouched(self):
        migrated, notes = migrate_template({"schema_version": 5})

        assert "behavioral_analysis" not in migrated
        assert notes == ()

    def test_a_valid_profile_round_trips_without_a_note(self):
        block = {
            "animal_model": "rodent",
            "protocol": "generic",
            "aquarium_perspective": "top_down",
        }

        migrated, notes = migrate_template({"schema_version": 5, "behavioral_analysis": block})

        assert migrated["behavioral_analysis"]["animal_model"] == "rodent"
        assert migrated["behavioral_analysis"]["protocol"] == "generic"
        assert notes == ()

    def test_unknown_tokens_are_replaced_and_noted(self):
        block = {"animal_model": "dragon", "protocol": "stroop"}

        migrated, notes = migrate_template({"schema_version": 5, "behavioral_analysis": block})

        assert migrated["behavioral_analysis"]["animal_model"] == "other"
        assert migrated["behavioral_analysis"]["protocol"] == "generic"
        assert notes == (NOTE_EXPERIMENT_PROFILE_NORMALISED,)

    def test_barnes_carries_what_the_protocol_forces(self):
        block = {
            "animal_model": "rodent",
            "protocol": "barnes",
            "aquarium_perspective": "lateral",
            "geotaxis_enabled": True,
            "protocol_params": {"barnes": {"table_diameter_cm": 150.0}},
        }

        migrated, notes = migrate_template(
            {"schema_version": 5, "analysis_interval_frames": 10, "behavioral_analysis": block}
        )

        assert migrated["analysis_interval_frames"] == 1
        migrated_block = migrated["behavioral_analysis"]
        assert migrated_block["aquarium_perspective"] == "top_down"
        assert migrated_block["geotaxis_enabled"] is False
        assert migrated_block["protocol_params"] == {"barnes": {"table_diameter_cm": 150.0}}
        assert notes == ()

    def test_barnes_with_another_animal_is_corrected_and_noted(self):
        block = {"animal_model": "zebrafish", "protocol": "barnes"}

        migrated, notes = migrate_template({"schema_version": 5, "behavioral_analysis": block})

        assert migrated["behavioral_analysis"]["animal_model"] == "rodent"
        assert notes == (NOTE_EXPERIMENT_PROFILE_NORMALISED,)

    def test_malformed_parameters_are_dropped(self):
        block = {"protocol": "barnes", "protocol_params": "oops"}

        migrated, _notes = migrate_template({"schema_version": 5, "behavioral_analysis": block})

        assert "protocol_params" not in migrated["behavioral_analysis"]

    def test_the_input_is_not_modified(self):
        template = {
            "schema_version": 5,
            "behavioral_analysis": {"protocol": "barnes", "aquarium_perspective": "lateral"},
        }

        migrate_template(template)

        assert template["behavioral_analysis"] == {
            "protocol": "barnes",
            "aquarium_perspective": "lateral",
        }

    def test_the_note_has_user_facing_text(self):
        assert "experiment profile" in template_migration_note_text(
            NOTE_EXPERIMENT_PROFILE_NORMALISED
        )

    def test_a_saved_profile_loads_back_unchanged(self, tmp_path: Path):
        manager = TemplateManager(
            templates_dir=tmp_path / "user", builtin_templates_dir=tmp_path / "none"
        )
        block = {
            "animal_model": "rodent",
            "protocol": "barnes",
            "protocol_params": {"barnes": {"table_diameter_cm": 150.0}},
            "aquarium_perspective": "top_down",
        }
        path = tmp_path / "t.json"
        assert manager.save_template("t", {"behavioral_analysis": block}, destination_path=path)

        loaded = manager.load_template_from_path(path)

        assert loaded is not None
        migrated, notes = migrate_template(loaded)
        assert migrated["behavioral_analysis"]["protocol"] == "barnes"
        assert migrated["behavioral_analysis"]["protocol_params"] == block["protocol_params"]
        assert notes == ()


class TestProtocolWindowSpec:
    def test_generic_proposes_no_window(self):
        profile = resolve_experiment_profile(behavioral_config={"protocol": "generic"})

        assert protocol_window_spec(profile) is None

    def test_a_protocol_without_a_spec_proposes_no_window(self, monkeypatch):
        monkeypatch.setattr(templates, "get_protocol", lambda protocol: None)
        profile = resolve_experiment_profile(behavioral_config={"protocol": "barnes"})

        assert protocol_window_spec(profile) is None

    def test_a_spec_without_a_preset_proposes_no_window(self, monkeypatch):
        monkeypatch.setattr(
            templates, "get_protocol", lambda protocol: SimpleNamespace(window_preset=None)
        )
        profile = resolve_experiment_profile(behavioral_config={"protocol": "barnes"})

        assert protocol_window_spec(profile) is None

    def test_the_preset_is_called_with_the_protocol_params_and_stored_as_json(self, monkeypatch):
        seen: list = []

        def preset(params):
            seen.append(dict(params))
            return barnes_maze_preset()

        monkeypatch.setattr(
            templates, "get_protocol", lambda protocol: SimpleNamespace(window_preset=preset)
        )
        profile = resolve_experiment_profile(
            behavioral_config={
                "protocol": "barnes",
                "protocol_params": {"barnes": {"max_trial_s": 120}},
            }
        )

        window = protocol_window_spec(profile)

        assert window == barnes_maze_preset().model_dump(mode="json", by_alias=True)
        assert seen == [{"max_trial_s": 120}]

    def test_the_registered_barnes_spec_proposes_preset_v2(self):
        """The real registry, no patch: a new Barnes project gets preset v2 (#633)."""
        import json

        from zebtrack.core.conditions.presets import barnes_maze_preset_v2

        profile = resolve_experiment_profile(
            behavioral_config={
                "protocol": "barnes",
                "protocol_params": {"barnes": {"max_trial_s": 180.0, "entry_hold_s": 1.0}},
            }
        )

        window = protocol_window_spec(profile)

        assert window == barnes_maze_preset_v2(max_s=180.0, entry_hold_s=1.0).model_dump(
            mode="json", by_alias=True
        )
        assert "burrow_entry" in json.dumps(window)


class TestBuiltinBarnesTemplate:
    def _template(self) -> dict[str, Any]:
        path = builtin_templates_dir() / "barnes_maze.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_it_declares_the_barnes_profile_and_the_lab_table(self):
        template = self._template()
        profile = resolve_experiment_profile(behavioral_config=template["behavioral_analysis"])

        assert template["builtin_id"] == "barnes_maze"
        assert profile.protocol is ProtocolId.BARNES
        assert profile.animal_model is AnimalModel.RODENT
        assert profile.warnings == ()
        assert profile.protocol_params["table_diameter_cm"] == 184.0
        assert template["aquarium_width_cm"] == template["aquarium_height_cm"] == 184.0

    def test_it_loads_without_migration_notes_and_with_what_barnes_forces(self):
        migrated, notes = migrate_template(self._template())

        assert notes == ()
        assert migrated["analysis_interval_frames"] == 1
        assert migrated["behavioral_analysis"]["aquarium_perspective"] == "top_down"
        assert migrated["behavioral_analysis"]["geotaxis_enabled"] is False

    def test_it_is_a_valid_current_schema_template(self):
        assert self._template()["schema_version"] == TEMPLATE_SCHEMA_VERSION

    def test_it_is_installed_for_a_new_user(self, tmp_path: Path):
        manager = TemplateManager(
            templates_dir=tmp_path / "user", builtin_templates_dir=builtin_templates_dir()
        )

        assert (tmp_path / "user" / "barnes_maze.json").exists()
        assert "Barnes maze (rat)" in [entry["name"] for entry in manager.list_templates()]


@pytest.mark.gui
class TestDiscoveryAppliesAProfileTemplate:
    @pytest.fixture(autouse=True)
    def setup(self, wizard_dependencies):
        self.root = wizard_dependencies["root"]

    def test_loading_the_barnes_template_shows_and_locks_the_profile(self):
        from zebtrack.ui.wizard.discovery_step import DiscoveryStep

        wizard_data: dict = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        step._apply_template_data(
            json.loads((builtin_templates_dir() / "barnes_maze.json").read_text(encoding="utf-8")),
            "barnes_maze.json",
        )

        assert _need(step.protocol_combo).get() == "Barnes maze (rodents)"
        assert _need(step.animal_model_combo).get() == "Rodent (rat or mouse)"
        assert str(_need(step.animal_model_combo).cget("state")) == "disabled"
        assert wizard_data["behavioral_analysis"]["protocol"] == "barnes"
        assert wizard_data["analysis_interval_frames"] == 1
