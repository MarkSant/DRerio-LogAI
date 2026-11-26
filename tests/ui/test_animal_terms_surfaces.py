"""The migrated screens say "arena"/"animal" for a rodent project, "aquarium"/"fish" otherwise.

One test class per surface (Barnes v8.1, stage 3). Each proves both directions: a
rodent/Barnes project reads the neutral wording, and a zebrafish (or legacy, profile-less)
project reads exactly today's text -- including after switching back and forth.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

import pytest

from zebtrack.core.services.experiment_profile import AnimalModel
from zebtrack.ui.components.behavioral_config_widget import (
    BehavioralConfigWidget,
    animal_model_choices,
    protocol_choices,
)
from zebtrack.ui.components.zone_controls import ZoneControlsWidget
from zebtrack.ui.wizard.calibration_step import CalibrationStep


def _pick(combo: Any, choices: list[tuple[str, str]], token: str) -> None:
    label = next(text for text, value in choices if value == token)
    combo.set(label)
    combo.event_generate("<<ComboboxSelected>>")


def _text(widget: Any) -> str:
    return str(widget.cget("text"))


def _tip(help_label: Any) -> str:
    """The tooltip text of a label made by ``create_help_label``."""
    return str(help_label._help_tooltip.text)


@pytest.mark.gui
class TestWizardCalibration:
    @pytest.fixture
    def step(self, tkinter_root):
        built = CalibrationStep(tkinter_root, {})
        built.build_ui()
        tkinter_root.update_idletasks()
        return built

    def test_a_fresh_step_reads_the_legacy_text(self, step) -> None:
        assert _text(step._count_label) == "Number of aquariums (videos):"
        assert _text(step._animals_label) == "Animals per aquarium:"
        assert step._count_tip.text.startswith("🎬 Number of Aquariums (Videos)")
        assert step._animals_tip.text.startswith("🐾 Animals per Aquarium")

    def test_a_rodent_profile_rewords_labels_and_tooltips(self, step) -> None:
        step.set_data({"behavioral_analysis": {"animal_model": "rodent"}})

        assert _text(step._count_label) == "Number of arenas (videos):"
        assert _text(step._animals_label) == "Animals per arena:"
        assert step._count_tip.text.startswith("🎬 Number of Arenas (Videos)")
        assert "aquarium" not in step._count_tip.text.lower()
        assert step._animals_tip.text.startswith("🐾 Animals per Arena")
        assert "zebrafish" not in step._animals_tip.text

    def test_a_barnes_project_reads_the_neutral_wording_too(self, step) -> None:
        step.set_data({"behavioral_analysis": {"protocol": "barnes"}})

        assert _text(step._count_label) == "Number of arenas (videos):"

    def test_going_back_to_zebrafish_restores_the_legacy_text(self, step) -> None:
        step.set_data({"behavioral_analysis": {"animal_model": "rodent"}})
        step.set_data({"behavioral_analysis": {"animal_model": "zebrafish"}})

        assert _text(step._count_label) == "Number of aquariums (videos):"
        assert step._animals_tip.text.startswith("🐾 Animals per Aquarium")

    def test_the_persisted_keys_do_not_change(self, step) -> None:
        step.set_data({"behavioral_analysis": {"animal_model": "rodent"}})

        data = step.get_data()

        assert {"num_aquariums", "animals_per_aquarium", "aquarium_width_cm"} <= set(data)
        assert data["behavioral_analysis"]["animal_model"] == "rodent"
        assert "aquarium_perspective" in data["behavioral_analysis"]


@pytest.mark.gui
class TestBehavioralConfigWidget:
    @pytest.fixture
    def widget(self, tkinter_root):
        built = BehavioralConfigWidget(tkinter_root, show_profile=True)
        built.pack()
        tkinter_root.update_idletasks()
        return built

    def test_a_fresh_widget_reads_the_legacy_text(self, widget) -> None:
        assert _text(widget._perspective_frame) == "Aquarium Perspective *"
        assert _text(widget._perspective_help_label) == "Select how the camera sees the aquarium:"
        assert _text(widget._thigmotaxis_help_label) == (
            "Distance threshold for considering the fish close to the aquarium walls:"
        )
        assert _text(widget._zones_split_label) == "Split the aquarium into:"

    def test_choosing_a_rodent_rewords_the_labels(self, widget) -> None:
        _pick(widget.animal_model_combo, animal_model_choices(), "rodent")

        assert _text(widget._perspective_frame) == "Arena Perspective *"
        assert _text(widget._perspective_help_label) == "Select how the camera sees the arena:"
        assert _text(widget._thigmotaxis_help_label) == (
            "Distance threshold for considering the animal close to the arena walls:"
        )
        assert _text(widget._zones_split_label) == "Split the arena into:"

    def test_choosing_barnes_forces_the_rodent_wording(self, widget) -> None:
        _pick(widget.protocol_combo, protocol_choices(), "barnes")

        assert _text(widget._perspective_frame) == "Arena Perspective *"

    def test_switching_back_to_zebrafish_restores_every_label(self, widget) -> None:
        _pick(widget.animal_model_combo, animal_model_choices(), "rodent")
        _pick(widget.animal_model_combo, animal_model_choices(), "zebrafish")

        assert _text(widget._perspective_frame) == "Aquarium Perspective *"
        assert _text(widget._zones_split_label) == "Split the aquarium into:"

    def test_restoring_a_saved_rodent_profile_rewords_without_the_combos(
        self, tkinter_root
    ) -> None:
        built = BehavioralConfigWidget(tkinter_root)  # the wizard's Calibration step shape
        built.set_values({"animal_model": "rodent"})

        assert _text(built._perspective_frame) == "Arena Perspective *"

    def test_the_perspective_value_keeps_its_persisted_key(self, widget) -> None:
        _pick(widget.animal_model_combo, animal_model_choices(), "rodent")

        assert "aquarium_perspective" in widget.get_values()


@pytest.mark.gui
class TestZoneControls:
    @pytest.fixture
    def zone_widget(self, tkinter_root):
        bus = Mock()
        built = ZoneControlsWidget(tkinter_root, event_bus=bus)
        tkinter_root.update_idletasks()
        return built

    def test_a_fresh_zones_tab_reads_the_legacy_text(self, zone_widget) -> None:
        assert _text(zone_widget.auto_detect_button) == "Detect Aquarium (Auto)"
        assert _text(zone_widget.aquarium_selector_frame) == "🐟 Active Aquarium"
        assert _text(zone_widget.aquarium_radio_1) == "Aquarium 1 (Left)"
        assert _text(zone_widget.aquarium_radio_2) == "Aquarium 2 (Right)"
        assert _text(zone_widget.sequential_radio) == "Sequential (2 passes, 1 aquarium at a time)"
        assert _text(zone_widget.sequential_help_label) == (
            "Sequential: processes the whole video for each aquarium separately"
        )

    def test_a_rodent_project_rewords_every_arena_control(self, zone_widget) -> None:
        zone_widget.set_animal_model(AnimalModel.RODENT)

        assert _text(zone_widget.auto_detect_button) == "Detect Arena (Auto)"
        assert _text(zone_widget.aquarium_selector_frame) == "🐀 Active Arena"
        assert _text(zone_widget.aquarium_radio_1) == "Arena 1 (Left)"
        assert _text(zone_widget.aquarium_radio_2) == "Arena 2 (Right)"
        assert _text(zone_widget.sequential_radio) == "Sequential (2 passes, 1 arena at a time)"
        assert _text(zone_widget.sequential_help_label) == (
            "Sequential: processes the whole video for each arena separately"
        )

    def test_another_species_gets_its_own_emoji(self, zone_widget) -> None:
        zone_widget.set_animal_model(AnimalModel.OTHER)

        assert _text(zone_widget.aquarium_selector_frame) == "🐾 Active Arena"

    def test_it_is_idempotent_and_reversible(self, zone_widget) -> None:
        zone_widget.set_animal_model(AnimalModel.RODENT)
        zone_widget.set_animal_model(AnimalModel.RODENT)
        zone_widget.set_animal_model(AnimalModel.ZEBRAFISH)

        assert _text(zone_widget.auto_detect_button) == "Detect Aquarium (Auto)"
        assert _text(zone_widget.aquarium_selector_frame) == "🐟 Active Aquarium"

    def test_the_dispatcher_feeds_the_open_projects_animal_model(self, zone_widget) -> None:
        from zebtrack.ui.components.event_dispatcher import EventDispatcher

        manager = SimpleNamespace(project_data={"behavioral_config": {"animal_model": "rodent"}})
        gui = SimpleNamespace(
            zone_controls=zone_widget, controller=SimpleNamespace(project_manager=manager)
        )
        dispatcher = EventDispatcher.__new__(EventDispatcher)
        dispatcher.gui = gui  # type: ignore[assignment]

        dispatcher.refresh_animal_terminology()
        assert _text(zone_widget.auto_detect_button) == "Detect Arena (Auto)"

        manager.project_data = {}
        dispatcher.refresh_animal_terminology()
        assert _text(zone_widget.auto_detect_button) == "Detect Aquarium (Auto)"

    def test_the_barnes_button_refresh_also_rewords_the_zones_tab(self, zone_widget) -> None:
        # The refresh that runs on project open and on every zone-list update.
        from zebtrack.ui.components.event_dispatcher import EventDispatcher

        manager = SimpleNamespace(project_data={"behavioral_config": {"animal_model": "rodent"}})
        gui = SimpleNamespace(
            zone_controls=zone_widget, controller=SimpleNamespace(project_manager=manager)
        )
        dispatcher = EventDispatcher.__new__(EventDispatcher)
        dispatcher.gui = gui  # type: ignore[assignment]

        dispatcher.refresh_barnes_assistant_visibility()

        assert _text(zone_widget.auto_detect_button) == "Detect Arena (Auto)"

    def test_the_dispatcher_tolerates_no_project(self, zone_widget) -> None:
        from zebtrack.ui.components.event_dispatcher import EventDispatcher

        dispatcher = EventDispatcher.__new__(EventDispatcher)
        dispatcher.gui = SimpleNamespace(zone_controls=zone_widget, controller=None)  # type: ignore[assignment]

        dispatcher.refresh_animal_terminology()

        assert _text(zone_widget.auto_detect_button) == "Detect Aquarium (Auto)"


@pytest.mark.gui
class TestAdHocDialogs:
    @staticmethod
    def _labels(dialog: Any) -> tuple[str, str]:
        return _text(dialog._count_label), _text(dialog._animals_label)

    def test_single_video_dialog_follows_the_chosen_animal(self, tkinter_root, test_settings):
        from zebtrack.ui.dialogs.single_video_config_dialog import SingleVideoConfigDialog

        with patch.object(SingleVideoConfigDialog, "wait_window"):
            dialog: Any = SingleVideoConfigDialog(tkinter_root, settings_obj=test_settings)
            tkinter_root.update_idletasks()
        widget = dialog.behavioral_config_widget

        assert self._labels(dialog) == ("Number of Aquariums:", "Animals per Aquarium:")

        _pick(widget.animal_model_combo, animal_model_choices(), "rodent")
        assert self._labels(dialog) == ("Number of Arenas:", "Animals per Arena:")

        _pick(widget.animal_model_combo, animal_model_choices(), "zebrafish")
        assert self._labels(dialog) == ("Number of Aquariums:", "Animals per Aquarium:")

    def test_single_video_dialog_rewords_the_tooltips_too(self, tkinter_root, test_settings):
        from zebtrack.ui.dialogs.single_video_config_dialog import SingleVideoConfigDialog

        with patch.object(SingleVideoConfigDialog, "wait_window"):
            dialog: Any = SingleVideoConfigDialog(tkinter_root, settings_obj=test_settings)
        widget = dialog.behavioral_config_widget

        assert _tip(dialog._count_help).startswith("Number of Aquariums")
        _pick(widget.protocol_combo, protocol_choices(), "barnes")
        assert _tip(dialog._count_help).startswith("Number of Arenas")
        assert "tanks" not in _tip(dialog._count_help)

    def test_live_analysis_dialog_follows_the_chosen_animal(self, tkinter_root, test_settings):
        from zebtrack.ui.dialogs.live_analysis_dialog import LiveAnalysisDialog

        with (
            patch.object(LiveAnalysisDialog, "wait_window"),
            patch(
                "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras",
                return_value=[],
            ),
        ):
            dialog: Any = LiveAnalysisDialog(tkinter_root, settings_obj=test_settings)
            tkinter_root.update_idletasks()
        widget = dialog.behavioral_config_widget

        assert self._labels(dialog) == ("No. of aquariums:", "Animals/aquarium:")
        assert "ONE aquarium" in _text(dialog._one_arena_notice)

        _pick(widget.animal_model_combo, animal_model_choices(), "rodent")
        assert self._labels(dialog) == ("No. of arenas:", "Animals/arena:")
        assert "ONE arena" in _text(dialog._one_arena_notice)
        assert "arenas" in _tip(dialog._count_help)
        assert "aquarium" not in _tip(dialog._animals_help)

        _pick(widget.animal_model_combo, animal_model_choices(), "zebrafish")
        assert self._labels(dialog) == ("No. of aquariums:", "Animals/aquarium:")

    def test_live_dialog_count_error_names_the_arena_for_a_rodent(
        self, tkinter_root, test_settings
    ):
        from zebtrack.ui.dialogs.live_analysis_dialog import LiveAnalysisDialog

        with (
            patch.object(LiveAnalysisDialog, "wait_window"),
            patch(
                "zebtrack.core.services.wizard_service.WizardService.detect_available_cameras",
                return_value=[],
            ),
        ):
            dialog: Any = LiveAnalysisDialog(tkinter_root, settings_obj=test_settings)
        dialog.camera_selection_var.set("Cam 0")
        dialog.camera_index_map = {"Cam 0": 0}
        dialog.num_aquariums_var.set(0)

        def error_text() -> str:
            with patch("zebtrack.ui.dialogs.live_analysis_dialog.messagebox.showerror") as shown:
                assert dialog.validate() is False
            return str(shown.call_args.args[1])

        assert "number of aquariums and animals" in error_text()
        _pick(dialog.behavioral_config_widget.animal_model_combo, animal_model_choices(), "rodent")
        assert "number of arenas and animals" in error_text()

    def test_assignment_dialog_names_the_arena_for_a_rodent_project(self, tkinter_root):
        from zebtrack.ui.dialogs.aquarium_assignment_dialog import AquariumAssignmentDialog

        with patch("ttkbootstrap.Style"), patch.object(AquariumAssignmentDialog, "wait_window"):
            rodent = AquariumAssignmentDialog(
                parent=tkinter_root, available_groups=["G1"], animal_model="rodent"
            )
            legacy = AquariumAssignmentDialog(parent=tkinter_root, available_groups=["G1"])

        assert rodent.title() == "Arena Configuration"
        assert legacy.title() == "Aquarium Configuration"
        rodent._group_vars[0].set("")
        with pytest.raises(ValueError, match="group of Arena 1"):
            rodent.get_configs()
        rodent.destroy()
        legacy.destroy()


@pytest.mark.gui
class TestWizardSummariesAndGlossary:
    @staticmethod
    def _summary(tkinter_root: Any, animal: str | None) -> list[str]:
        from zebtrack.ui.wizard.confirmation_step import ConfirmationStep

        data: dict[str, Any] = {
            "num_aquariums": 2,
            "animals_per_aquarium": 3,
            "aquarium_width_cm": 40.0,
            "aquarium_height_cm": 30.0,
            "weight_assignments": {"aquarium": "arena.pt", "animal": "rat.pt"},
            "model_selection": {"aquarium_method": "seg", "animal_method": "det"},
        }
        if animal is not None:
            data["behavioral_analysis"] = {"animal_model": animal}
        step = ConfirmationStep(tkinter_root, data)
        lines: list[str] = []
        step._append_calibration(lines)
        step._append_detection_settings(lines)
        return lines

    def test_the_confirmation_summary_for_a_legacy_project(self, tkinter_root) -> None:
        lines = self._summary(tkinter_root, None)

        assert "  • Aquariums: 2" in lines
        assert "  • Animals per aquarium: 3" in lines
        assert "  • Aquarium weight: arena.pt" in lines
        assert any(line.startswith("  • Aquarium method:") for line in lines)

    def test_the_confirmation_summary_for_a_rodent_project(self, tkinter_root) -> None:
        lines = self._summary(tkinter_root, "rodent")

        assert "  • Arenas: 2" in lines
        assert "  • Animals per arena: 3" in lines
        assert "  • Arena weight: arena.pt" in lines
        assert any(line.startswith("  • Arena method:") for line in lines)
        assert not any("quarium" in line for line in lines)

    def test_the_discovery_glossary_follows_the_animal_model(self, tkinter_root) -> None:
        from zebtrack.ui.wizard.discovery_step import DiscoveryStep

        step = DiscoveryStep(tkinter_root, {})
        step.build_ui()
        tkinter_root.update_idletasks()
        assert "the area of the tank" in _text(step._glossary_text)

        _pick(step.animal_model_combo, animal_model_choices(), "rodent")
        assert "such as a table or a box" in _text(step._glossary_text)
        assert "tank" not in _text(step._glossary_text)

        _pick(step.animal_model_combo, animal_model_choices(), "zebrafish")
        assert "the area of the tank" in _text(step._glossary_text)


class TestSubjectLabelsInTheTrees:
    @staticmethod
    def _builder(project_data: dict) -> Any:
        from zebtrack.ui.components.project_views.report_tree_builder import ReportTreeBuilder

        manager = SimpleNamespace(project_data=project_data)
        validation: Any = SimpleNamespace(format_subject_label=lambda sid: f"S{sid}")
        return ReportTreeBuilder(project_manager_getter=manager, validation_manager=validation)

    @staticmethod
    def _inserted_text(builder: Any) -> str:
        tree = Mock()
        builder._insert_subject_node(tree, "day", 3, [{"x": 1}, {"x": 2}], "g", "d", {})
        return tree.insert.call_args.kwargs["text"]

    def test_zebrafish_and_legacy_projects_keep_the_fish(self) -> None:
        assert self._inserted_text(self._builder({})) == "🐟 Subject 03"
        zebra = {"behavioral_config": {"animal_model": "zebrafish"}}
        assert self._inserted_text(self._builder(zebra)) == "🐟 Subject 03"

    def test_rodent_and_other_projects_get_their_own_emoji(self) -> None:
        rodent = {"behavioral_config": {"animal_model": "rodent"}}
        other = {"behavioral_config": {"animal_model": "other"}}

        assert self._inserted_text(self._builder(rodent)) == "🐀 Subject 03"
        assert self._inserted_text(self._builder(other)) == "🐾 Subject 03"


@pytest.mark.gui
class TestHelpLabelTooltips:
    def test_set_help_text_rewords_the_tooltip(self, tkinter_root) -> None:
        from zebtrack.ui.wizard.tooltip import create_help_label, set_help_text

        label = create_help_label(tkinter_root, "before")
        set_help_text(label, "after")

        assert _tip(label) == "after"

    def test_a_label_not_made_by_create_help_label_is_left_alone(self, tkinter_root) -> None:
        from tkinter import Label

        from zebtrack.ui.wizard.tooltip import set_help_text

        plain = Label(tkinter_root, text="x")

        set_help_text(plain, "ignored")  # must not raise

        assert not hasattr(plain, "_help_tooltip")

    def test_destroying_a_help_label_frees_it_and_its_tooltip(self) -> None:
        # Hub review: a module-level registry whose values reference their keys kept
        # every dialog's labels alive for the whole session. Probed in a fresh
        # interpreter with a bare Tk root: the suite's shared root runs ttkbootstrap,
        # which keeps its own references to every Tk widget and would mask the result.
        import subprocess
        import sys

        probe = "; ".join(
            [
                "import gc, weakref, tkinter as tk",
                "from zebtrack.ui.wizard.tooltip import create_help_label, set_help_text",
                "root = tk.Tk()",
                "label = create_help_label(root, 'a')",
                "set_help_text(label, 'b')",
                "refs = (weakref.ref(label), weakref.ref(label._help_tooltip))",
                "label.destroy()",
                "del label",
                "gc.collect()",
                "print('FREED' if all(r() is None for r in refs) else 'LEAKED')",
                "root.destroy()",
            ]
        )
        done = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, timeout=60, check=False
        )

        assert done.stdout.strip().endswith("FREED"), done.stdout + done.stderr

    def test_no_module_level_registry_holds_the_tooltips(self) -> None:
        import zebtrack.ui.wizard.tooltip as tooltip_module

        assert not [name for name in vars(tooltip_module) if name.endswith("TOOLTIPS")]


class TestVideoNodeEmoji:
    """The tree's per-video row carries the animal's emoji, not always the fish."""

    @pytest.mark.parametrize(
        ("project_data", "emoji"),
        [
            ({}, "🐟"),
            ({"behavioral_config": {"animal_model": "zebrafish"}}, "🐟"),
            ({"behavioral_config": {"animal_model": "rodent"}}, "🐀"),
            ({"behavioral_config": {"animal_model": "other"}}, "🐾"),
        ],
    )
    def test_video_row_text(self, project_data, emoji) -> None:
        from zebtrack.ui.components.project_views.report_tree_builder import ReportTreeBuilder

        manager = Mock()
        manager.project_data = project_data
        manager.resolve_results_directory.return_value = None
        builder = ReportTreeBuilder(project_manager_getter=lambda: manager)
        tree = Mock()

        builder._insert_video_node(tree, "day", {"path": "/data/v.mp4", "subject": "3"}, {})

        assert tree.insert.call_args.kwargs["text"] == f"{emoji} Subject 3"


@pytest.mark.gui
class TestOverviewSubjectFallback:
    @staticmethod
    def _subject_text(overview: Any, animal: str | None) -> str:
        hierarchy: dict[str, Any] = {
            "groups": [
                {
                    "id": "g",
                    "display": "G",
                    "status_summary": "",
                    "data_summary": "",
                    "days": [
                        {
                            "id": "d",
                            "title": "D",
                            "status": "",
                            "data": "",
                            "subjects": [{"id": "s1", "videos": []}],  # no "label": the fallback
                        }
                    ],
                }
            ]
        }
        if animal is not None:
            hierarchy["terms_model"] = animal
        overview.populate_tree_with_hierarchy(hierarchy, {})
        tree = overview.project_overview_tree
        group = tree.get_children()[0]
        day = tree.get_children(group)[0]
        return str(tree.item(tree.get_children(day)[0], "text"))

    @pytest.fixture
    def overview(self, tkinter_root):
        from zebtrack.ui.components.project_overview import ProjectOverviewWidget
        from zebtrack.ui.event_bus_v2 import EventBusV2

        widget = ProjectOverviewWidget(tkinter_root, event_bus=EventBusV2())
        widget.pack()
        tkinter_root.update()
        return widget

    @pytest.mark.parametrize(
        ("animal", "emoji"), [(None, "🐟"), ("zebrafish", "🐟"), ("rodent", "🐀"), ("other", "🐾")]
    )
    def test_the_fallback_label_uses_the_animals_emoji(self, overview, animal, emoji) -> None:
        assert self._subject_text(overview, animal) == f"{emoji} Subject s1"

    def test_the_hierarchy_carries_the_open_projects_animal_model(self) -> None:
        from zebtrack.ui.components.validation_manager import ValidationManager

        manager = ValidationManager.__new__(ValidationManager)
        project_manager = Mock()
        project_manager.project_data = {"behavioral_config": {"animal_model": "rodent"}}
        project_manager.get_project_type.return_value = "pre-recorded"
        manager.gui = SimpleNamespace(  # type: ignore[assignment]
            controller=SimpleNamespace(project_manager=project_manager)
        )

        assert manager.prepare_overview_hierarchy_for_widget([])["terms_model"] == "rodent"
