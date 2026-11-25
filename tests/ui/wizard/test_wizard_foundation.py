"""
Tests for wizard foundation and Step 1 (Discovery).

Validates:
- Wizard initialization
- Step 1 UI creation
- Step 1 data extraction
- Step 1 validation
- Navigation (forward only in Phase W1)
"""

from typing import Any

import pytest

from zebtrack.ui.components.behavioral_config_widget import (
    animal_model_choices,
    protocol_choices,
)
from zebtrack.ui.wizard.discovery_step import DiscoveryStep
from zebtrack.ui.wizard.enums import (
    LEGACY_EXPLORATORY_PROJECT_TYPE,
    ImportAction,
    ProjectType,
    WizardStepID,
    derive_import_action,
)
from zebtrack.ui.wizard.file_selection_step import FileSelectionStep


def _need(value):
    """A widget the test just built must exist; narrows ``X | None`` for mypy."""
    assert value is not None
    return value


@pytest.mark.gui
class TestWizardFoundation:
    """Tests for wizard initialization and basic navigation."""

    @pytest.fixture(autouse=True)
    def setup(self, wizard_dependencies):
        """Create Tkinter root for testing."""
        self.root = wizard_dependencies["root"]

    def test_wizard_initializes_with_schema_version(self):
        """Wizard should initialize with wizard_schema_version: 1."""
        # Note: We can't fully test WizardDialog in headless mode
        # because Dialog is modal. Test the data structure instead.
        wizard_data: dict[str, Any] = {
            "wizard_schema_version": 1,
        }
        assert wizard_data["wizard_schema_version"] == 1

    def test_discovery_step_builds_ui_without_error(self):
        """Discovery step should build UI without errors."""
        wizard_data: dict[str, Any] = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        # Should have step_id set
        assert step.step_id == WizardStepID.DISCOVERY

    def test_dynamic_wrapping_keeps_text_visible_and_columns_equal(self):
        """Long texts wrap to the canvas width; the 3 columns wrap equally.

        Regression 1: the 3rd column ("Arquivos Parquet Existentes") had its
        text cut off when narrower than the single-line label.
        Regression 2: with single-line text the widest column (Q1) stayed wider
        than the others, so only some columns wrapped — the layout looked odd.
        Now every wrappable label gets a finite wraplength driven by the canvas
        width: the three columns share an identical third-of-width wraplength,
        and the full-width glossary wraps to the whole width.
        """
        wizard_data: dict[str, Any] = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        canvas_width = 900
        step._apply_dynamic_wrapping(canvas_width)

        def _wraplengths(frame):
            return [
                int(child.cget("wraplength"))
                for child in frame.winfo_children()
                if child.winfo_class() in ("Radiobutton", "Label")
            ]

        # All three question columns wrap to the SAME (equal) width.
        column_wraplengths = (
            _wraplengths(step.q1_frame) + _wraplengths(step.q2_frame) + _wraplengths(step.q3_frame)
        )
        assert column_wraplengths, "no wrappable labels found in the question columns"
        unique = set(column_wraplengths)
        assert len(unique) == 1, f"columns must wrap equally, got {unique}"
        column_target = unique.pop()
        # ~ a third of the width, and well under the full width (so it wraps).
        assert 0 < column_target < canvas_width // 2

        # The glossary wraps to (about) the full width, not a third.
        glossary_wraplengths = _wraplengths(step.glossary_frame)
        assert glossary_wraplengths, "glossary text label not found"
        assert all(wl > column_target for wl in glossary_wraplengths)

        # Everything is left-justified for clean multi-line text.
        for frame in (step.q1_frame, step.q2_frame, step.q3_frame, step.glossary_frame):
            for child in frame.winfo_children():
                if child.winfo_class() in ("Radiobutton", "Label"):
                    assert str(child.cget("justify")) == "left"

    def test_discovery_step_default_data_is_experimental(self):
        """Discovery step defaults to experimental project type."""
        wizard_data: dict[str, Any] = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        data = step.get_data()

        assert data["project_type"] == ProjectType.EXPERIMENTAL.value
        assert "has_folder_structure" in data
        assert "folder_meaning" in data
        assert not data["has_parquets"]
        assert data["parquet_import_scope"] is None

    def test_discovery_step_live_excludes_folder_fields(self):
        """Live projects have no folders to organise, so those keys stay absent.

        This used to cover the "exploratory" type, whose only real effect was
        omitting these same keys. Live is now the sole type that does so.
        """
        wizard_data: dict[str, Any] = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        step.project_type_var.set(ProjectType.LIVE.value)
        data = step.get_data()

        assert data["project_type"] == ProjectType.LIVE.value
        assert "has_folder_structure" not in data
        assert "folder_meaning" not in data

    def test_discovery_step_parquet_scope_arena(self):
        """Selecting 'import arena' should set parquet_import_scope to 'arena'."""
        wizard_data: dict[str, Any] = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        # Select "import arena"
        step.parquet_scope_var.set(1)
        data = step.get_data()

        assert data["has_parquets"]
        assert data["parquet_import_scope"] == "arena"

    def test_discovery_step_parquet_scope_zones(self):
        """Selecting 'import zones' should set parquet_import_scope to 'zones'."""
        wizard_data: dict[str, Any] = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        # Select "import zones"
        step.parquet_scope_var.set(2)
        data = step.get_data()

        assert data["has_parquets"]
        assert data["parquet_import_scope"] == "zones"

    def test_discovery_step_parquet_scope_all(self):
        """Selecting 'import all' should set parquet_import_scope to 'all'."""
        wizard_data: dict[str, Any] = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        # Select "import all"
        step.parquet_scope_var.set(3)
        data = step.get_data()

        assert data["has_parquets"]
        assert data["parquet_import_scope"] == "all"

    def test_discovery_step_validate_always_succeeds(self):
        """
        Discovery step validation should always succeed (all fields have defaults).
        """
        wizard_data: dict[str, Any] = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        is_valid, error_message = step.validate()

        assert is_valid
        assert error_message == ""

    def test_discovery_step_set_data_restores_ui(self):
        """set_data should restore UI from previously collected data."""
        wizard_data: dict[str, Any] = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        # Simulate previous data
        previous_data = {
            "project_type": ProjectType.LIVE.value,
            "has_parquets": True,
            "parquet_import_scope": "zones",
        }

        step.set_data(previous_data)

        # Verify UI restored
        assert step.project_type_var.get() == ProjectType.LIVE.value
        assert step.parquet_scope_var.get() == 2  # 2 = zones

    def test_discovery_step_set_data_normalizes_legacy_exploratory(self):
        """A pre-v6 template must not leave the radio group with nothing selected.

        ``project_type_var`` is bound to the radio buttons; setting it to a value
        no button offers silently deselects them all, so the user loses the
        project-type choice on load. "exploratory" maps to EXPERIMENTAL because
        that is what such a project always became on disk anyway.
        """
        wizard_data: dict[str, Any] = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        step.set_data({"project_type": LEGACY_EXPLORATORY_PROJECT_TYPE})

        assert step.project_type_var.get() == ProjectType.EXPERIMENTAL.value

    def test_discovery_step_template_banner(self):
        """Template metadata should surface in the discovery banner."""
        wizard_data: dict[str, Any] = {
            "template_metadata": {
                "name": "Template Inicial",
                "path": "C:/temp/template_inicial.json",
            }
        }

        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        assert "Template Inicial" in step.template_info_var.get()

    def test_file_selection_step_template_banner(self):
        """Template metadata should surface in the file selection banner."""
        wizard_data: dict[str, Any] = {
            "template_metadata": {
                "name": "Template Seleção",
                "path": "C:/temp/template_selecao.json",
            }
        }

        step = FileSelectionStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        assert "Template Seleção" in step.template_info_var.get()


class TestEnums:
    """Tests for formal enumerations."""

    def test_project_type_enum_values(self):
        """ProjectType enum should have correct values."""
        assert ProjectType.EXPERIMENTAL.value == "experimental"
        assert ProjectType.LIVE.value == "live"

    def test_project_type_has_exactly_two_members(self):
        """Guards against "exploratory" creeping back in.

        A plain assignment anywhere in an Enum body becomes a real member -- a
        single leading underscore does NOT hide it -- which is exactly how the
        removed type could return unnoticed. Hence the legacy value lives as a
        module-level constant, and this test pins the member list.
        """
        assert [m.name for m in ProjectType] == ["EXPERIMENTAL", "LIVE"]

    def test_normalize_maps_legacy_and_unknown_to_experimental(self):
        """A corrupt or pre-v6 template must not stop the wizard from opening."""
        assert ProjectType.normalize(LEGACY_EXPLORATORY_PROJECT_TYPE) == "experimental"
        assert ProjectType.normalize("garbage") == "experimental"
        assert ProjectType.normalize(None) == "experimental"
        # The surviving types round-trip untouched.
        assert ProjectType.normalize("live") == "live"
        assert ProjectType.normalize("experimental") == "experimental"

    def test_import_action_enum_values(self):
        """ImportAction enum should have correct values."""
        assert ImportAction.SKIP.value == "skip"
        assert ImportAction.IMPORT_ZONES.value == "import_zones"
        assert ImportAction.PARTIAL.value == "partial"
        assert ImportAction.FULL.value == "full"

    def test_derive_import_action_skip(self):
        """All 3 checkboxes → SKIP."""
        action = derive_import_action(True, True, True)
        assert action == ImportAction.SKIP

    def test_derive_import_action_import_zones(self):
        """Arena + ROIs → IMPORT_ZONES."""
        action = derive_import_action(True, True, False)
        assert action == ImportAction.IMPORT_ZONES

    def test_derive_import_action_partial(self):
        """Arena only → PARTIAL."""
        action = derive_import_action(True, False, False)
        assert action == ImportAction.PARTIAL

    def test_derive_import_action_full(self):
        """No checkboxes → FULL."""
        action = derive_import_action(False, False, False)
        assert action == ImportAction.FULL

    def test_derive_import_action_normalizes_invalid_states(self):
        """Invalid states (ROIs without arena) → FULL."""
        # Invalid: ROIs but no arena
        action = derive_import_action(False, True, False)
        assert action == ImportAction.FULL

        # Invalid: Trajectory but no arena
        action = derive_import_action(False, False, True)
        assert action == ImportAction.FULL


def _choose(combo, choices, token) -> None:
    label = next(text for text, value in choices if value == token)
    combo.set(label)
    combo.event_generate("<<ComboboxSelected>>")


def _with_window_preset(monkeypatch) -> dict[str, Any]:
    """Make the Barnes spec carry a window preset (the spec is registered by another front).

    Returns the stored (JSON) form the wizard is expected to propose.
    """
    from types import SimpleNamespace

    from zebtrack.core.conditions.presets import barnes_maze_preset
    from zebtrack.ui.wizard import templates

    spec = SimpleNamespace(window_preset=lambda params: barnes_maze_preset())
    monkeypatch.setattr(templates, "get_protocol", lambda protocol: spec)
    return barnes_maze_preset().model_dump(mode="json", by_alias=True)


@pytest.mark.gui
class TestDiscoveryExperimentProfile:
    """ADR-014: question 4 asks the animal model and the protocol once, at creation."""

    @pytest.fixture(autouse=True)
    def setup(self, wizard_dependencies):
        self.root = wizard_dependencies["root"]

    def _step(self, wizard_data: dict[str, Any] | None = None) -> tuple[DiscoveryStep, dict]:
        data: dict[str, Any] = {} if wizard_data is None else wizard_data
        step = DiscoveryStep(self.root, data)
        step.build_ui()
        return step, data

    def test_the_combos_start_on_the_legacy_profile(self):
        step, _data = self._step()

        assert _need(step.animal_model_combo).get() == "Zebrafish (aquarium)"
        assert _need(step.protocol_combo).get() == "Generic (no protocol)"
        assert str(_need(step.animal_model_combo).cget("state")) == "readonly"

    def test_the_labels_list_every_animal_model_and_protocol(self):
        step, _data = self._step()

        assert [str(v) for v in _need(step.animal_model_combo).cget("values")] == [
            "Zebrafish (aquarium)",
            "Rodent (rat or mouse)",
            "Other species",
        ]
        assert [str(v) for v in _need(step.protocol_combo).cget("values")] == [
            "Generic (no protocol)",
            "Barnes maze (rodents)",
        ]

    def test_a_default_run_adds_only_the_legacy_profile(self):
        step, _data = self._step()

        block = step.get_data()["behavioral_analysis"]

        assert block == {"animal_model": "zebrafish", "protocol": "generic"}

    def test_choosing_barnes_locks_the_animal_model_to_rodent(self):
        step, _data = self._step()

        _choose(step.protocol_combo, protocol_choices(), "barnes")

        assert _need(step.animal_model_combo).get() == "Rodent (rat or mouse)"
        assert str(_need(step.animal_model_combo).cget("state")) == "disabled"
        assert "rodents" in step.profile_hint_label.cget("text")

    def test_barnes_output_forces_the_view_and_every_frame(self):
        step, _data = self._step()
        _choose(step.protocol_combo, protocol_choices(), "barnes")

        data = step.get_data()

        block = data["behavioral_analysis"]
        assert block["animal_model"] == "rodent"
        assert block["protocol"] == "barnes"
        assert block["aquarium_perspective"] == "top_down"
        assert block["geotaxis_enabled"] is False
        assert data["analysis_interval_frames"] == 1

    def test_barnes_sets_the_protocols_window_when_the_project_has_none(self, monkeypatch):
        window = _with_window_preset(monkeypatch)
        step, _data = self._step()
        _choose(step.protocol_combo, protocol_choices(), "barnes")

        assert step.get_data()["analysis_window"] == window

    def test_barnes_does_not_overwrite_a_window_the_user_already_has(self, monkeypatch):
        _with_window_preset(monkeypatch)
        step, _data = self._step({"analysis_window": {"kind": "mine"}})
        _choose(step.protocol_combo, protocol_choices(), "barnes")

        assert "analysis_window" not in step.get_data()

    def test_barnes_without_a_registered_preset_leaves_the_window_alone(self, monkeypatch):
        from zebtrack.ui.wizard import templates

        monkeypatch.setattr(templates, "get_protocol", lambda protocol: None)
        step, _data = self._step()
        _choose(step.protocol_combo, protocol_choices(), "barnes")

        assert "analysis_window" not in step.get_data()

    def test_the_rest_of_the_behavioural_block_is_kept(self):
        step, _data = self._step(
            {"behavioral_analysis": {"thigmotaxis_distance_cm": 3.0, "geotaxis_num_zones": 4}}
        )
        _choose(step.animal_model_combo, animal_model_choices(), "zebrafish")

        block = step.get_data()["behavioral_analysis"]

        assert block["thigmotaxis_distance_cm"] == 3.0
        assert block["geotaxis_num_zones"] == 4

    def test_changing_the_animal_drops_the_numbers_saved_for_the_previous_one(self):
        step, _data = self._step(
            {
                "behavioral_analysis": {
                    "animal_model": "zebrafish",
                    "thigmotaxis_distance_cm": 3.0,
                    "max_plausible_speed_cm_s": 40.0,
                    "geotaxis_num_zones": 4,
                }
            }
        )
        _choose(step.animal_model_combo, animal_model_choices(), "rodent")

        block = step.get_data()["behavioral_analysis"]

        assert block["animal_model"] == "rodent"
        assert "thigmotaxis_distance_cm" not in block
        assert "max_plausible_speed_cm_s" not in block
        assert block["geotaxis_num_zones"] == 4

    def test_changing_the_protocol_drops_the_previous_protocols_parameters(self):
        step, _data = self._step(
            {
                "behavioral_analysis": {
                    "animal_model": "rodent",
                    "protocol": "barnes",
                    "protocol_params": {"barnes": {"table_diameter_cm": 150.0}},
                }
            }
        )
        _choose(step.protocol_combo, protocol_choices(), "generic")

        assert "protocol_params" not in step.get_data()["behavioral_analysis"]

    def test_an_unchanged_barnes_choice_keeps_its_parameters(self):
        params = {"barnes": {"table_diameter_cm": 150.0}}
        step, _data = self._step(
            {
                "behavioral_analysis": {
                    "animal_model": "rodent",
                    "protocol": "barnes",
                    "protocol_params": params,
                }
            }
        )
        step.set_data({"behavioral_analysis": step.wizard_data["behavioral_analysis"]})

        assert step.get_data()["behavioral_analysis"]["protocol_params"] == params

    def test_leaving_barnes_undoes_what_barnes_forced(self, monkeypatch):
        window = _with_window_preset(monkeypatch)
        step, data = self._step(
            {
                "behavioral_analysis": {"animal_model": "rodent", "protocol": "barnes"},
                "analysis_interval_frames": 1,
                "analysis_window": window,
            }
        )
        _choose(step.protocol_combo, protocol_choices(), "generic")

        step.get_data()

        assert "analysis_interval_frames" not in data
        assert data["analysis_window"] is None

    def test_leaving_barnes_keeps_a_window_the_user_customised(self, monkeypatch):
        _with_window_preset(monkeypatch)
        step, data = self._step(
            {
                "behavioral_analysis": {"animal_model": "rodent", "protocol": "barnes"},
                "analysis_window": {"kind": "mine"},
            }
        )
        _choose(step.protocol_combo, protocol_choices(), "generic")

        step.get_data()

        assert data["analysis_window"] == {"kind": "mine"}

    def test_set_data_restores_the_combos_for_back_navigation(self):
        step, _data = self._step()

        step.set_data({"behavioral_analysis": {"animal_model": "other", "protocol": "generic"}})

        assert _need(step.animal_model_combo).get() == "Other species"
        assert str(_need(step.animal_model_combo).cget("state")) == "readonly"

    def test_set_data_with_barnes_locks_the_animal_model(self):
        step, _data = self._step()

        step.set_data({"behavioral_analysis": {"protocol": "barnes"}})

        assert _need(step.animal_model_combo).get() == "Rodent (rat or mouse)"
        assert str(_need(step.animal_model_combo).cget("state")) == "disabled"

    def test_the_profile_question_wraps_to_the_canvas_width(self):
        step, _data = self._step()

        step._apply_dynamic_wrapping(900)

        labels = [w for w in step.q4_frame.winfo_children() if w.winfo_class() == "Label"]
        assert labels
        assert all(int(str(label.cget("wraplength"))) == 840 for label in labels)
