import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from zebtrack.core.conditions.presets import barnes_maze_preset, external_trigger_preset
from zebtrack.ui.wizard.templates import (
    NOTE_ANALYSIS_WINDOW_DROPPED,
    NOTE_CLASS_ROLES_DROPPED,
    NOTE_EXTERNAL_TRIGGER_CONVERTED,
    TEMPLATE_SCHEMA_VERSION,
    TemplateManager,
    format_template_banner,
    migrate_template,
    template_migration_note_text,
)

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
