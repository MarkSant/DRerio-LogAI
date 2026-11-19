"""Tests for the Analysis-tab event handlers in ``ui/builders/analysis_widgets.py``.

The cancel handler is shared by the pre-recorded and the live flows, but its
consequences are not: in a live session it DELETES the recording. These tests
pin that asymmetry.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.ui.builders.analysis_widgets import AnalysisWidgetsBuilder
from zebtrack.ui.event_bus_v2 import UIEvents


@pytest.fixture
def gui() -> MagicMock:
    gui = MagicMock()
    gui.dialog_manager.ask_yes_no.return_value = True
    return gui


@pytest.fixture
def builder(gui: MagicMock) -> AnalysisWidgetsBuilder:
    return AnalysisWidgetsBuilder(gui, MagicMock(), settings_obj=None)


def _set_live(gui: MagicMock, active: bool) -> None:
    gui.analysis_view_controller._is_live_session_active.return_value = active


class TestCancelRequested:
    def test_prerecorded_cancel_asks_nothing(self, builder, gui):
        """Nada a perder no pré-gravado — um diálogo extra seria só atrito."""
        _set_live(gui, False)

        builder.handle_cancel_requested(None)

        gui.dialog_manager.ask_yes_no.assert_not_called()
        gui.event_dispatcher.publish_event.assert_called_once()
        assert gui.event_dispatcher.publish_event.call_args[0][0] == (
            UIEvents.VIDEO_CANCEL_ANALYSIS
        )

    def test_live_cancel_requires_confirmation(self, builder, gui):
        _set_live(gui, True)

        builder.handle_cancel_requested(None)

        gui.dialog_manager.ask_yes_no.assert_called_once()
        gui.event_dispatcher.publish_event.assert_called_once()

    def test_live_cancel_declined_does_not_discard(self, builder, gui):
        """Responder "não" precisa deixar a gravação correndo, intacta."""
        _set_live(gui, True)
        gui.dialog_manager.ask_yes_no.return_value = False

        assert builder.handle_cancel_requested(None) is None

        gui.event_dispatcher.publish_event.assert_not_called()

    def test_confirmation_mentions_the_save_alternative(self, builder, gui):
        """A confirmação tem de apontar a saída não destrutiva."""
        _set_live(gui, True)

        builder.handle_cancel_requested(None)

        message = gui.dialog_manager.ask_yes_no.call_args[0][1]
        assert "Finish and Save" in message
        assert "deleted" in message

    def test_unreadable_live_state_fails_open_and_asks(self, builder, gui):
        """Na dúvida, perguntar: descartar em silêncio é o erro irreversível."""
        gui.analysis_view_controller._is_live_session_active.side_effect = RuntimeError("boom")

        builder.handle_cancel_requested(None)

        gui.dialog_manager.ask_yes_no.assert_called_once()

    def test_missing_controller_is_treated_as_not_live(self, builder, gui):
        gui.analysis_view_controller = None

        builder.handle_cancel_requested(None)

        gui.dialog_manager.ask_yes_no.assert_not_called()
        gui.event_dispatcher.publish_event.assert_called_once()


class TestLiveFinishRequested:
    def test_finish_keeps_the_data(self, builder, gui):
        coordinator = gui.controller.live_camera_session_coordinator

        builder.handle_live_finish_requested(None)

        coordinator.stop_live_session.assert_called_once_with(discard=False)

    def test_finish_never_publishes_the_cancel_event(self, builder, gui):
        builder.handle_live_finish_requested(None)

        gui.event_dispatcher.publish_event.assert_not_called()

    def test_without_coordinator_is_a_noop(self, builder, gui):
        gui.controller.live_camera_session_coordinator = None

        assert builder.handle_live_finish_requested(None) is None


class TestSpeedCeilingInTheAdvancedTab:
    """#695: the project's speed ceiling is edited in the Advanced Settings tab.

    The project value lives in ``behavioral_config["max_plausible_speed_cm_s"]``;
    without one the form shows ``settings.behavioral_analysis``. Saving into a
    project never writes the project's ceiling into the SHARED ``Settings``,
    which every other run (single video, live ad hoc) falls back to.
    """

    @staticmethod
    def _settings(speed: float = 50.0):
        from zebtrack.settings import load_settings

        settings = load_settings()
        settings.behavioral_analysis.max_plausible_speed_cm_s = speed
        return settings

    @staticmethod
    def _project_gui(behavioral_config: dict | None) -> MagicMock:
        gui = MagicMock()
        gui._extract_setting.side_effect = lambda _obj, _path, default: default
        project_manager = gui.controller.project_manager
        project_manager.project_path = "C:/proj"
        project_manager.project_data = (
            {} if behavioral_config is None else {"behavioral_config": behavioral_config}
        )
        return gui

    @staticmethod
    def _form_behavioural(gui: MagicMock) -> dict:
        values = gui.config_editor_widget.set_values.call_args.args[0]
        return values["behavioral_analysis"]

    def test_the_form_shows_the_project_ceiling(self):
        gui = self._project_gui({"max_plausible_speed_cm_s": 120.0})
        builder = AnalysisWidgetsBuilder(gui, MagicMock(), settings_obj=self._settings(50.0))

        builder.reload_config_editor_values_widget()

        assert self._form_behavioural(gui)["max_plausible_speed_cm_s"] == 120.0

    def test_without_a_project_ceiling_the_form_shows_the_settings_one(self):
        gui = self._project_gui({"thigmotaxis_distance_cm": 3.0})
        builder = AnalysisWidgetsBuilder(gui, MagicMock(), settings_obj=self._settings(70.0))

        builder.reload_config_editor_values_widget()

        assert self._form_behavioural(gui)["max_plausible_speed_cm_s"] == 70.0

    def _save(self, behavioral_config: dict, form_speed: float, shared_speed: float = 50.0):
        shared = self._settings(shared_speed)
        gui = self._project_gui(behavioral_config)
        builder = AnalysisWidgetsBuilder(gui, MagicMock(), settings_obj=shared)
        validated = shared.model_copy(deep=True)
        validated.behavioral_analysis.max_plausible_speed_cm_s = form_speed
        validated.behavioral_analysis.default_thigmotaxis_distance_cm = 15.0

        builder._update_current_project_settings(validated)

        return shared, gui.controller.project_manager

    def test_saving_writes_the_ceiling_into_the_project(self):
        _shared, project_manager = self._save({}, form_speed=110.0)

        behavioural = project_manager.project_data["behavioral_config"]
        assert behavioural["max_plausible_speed_cm_s"] == 110.0
        project_manager.save_project.assert_called_once()

    def test_saving_never_writes_the_project_ceiling_into_shared_settings(self):
        shared, _pm = self._save({}, form_speed=110.0, shared_speed=50.0)

        assert shared.behavioral_analysis.max_plausible_speed_cm_s == 50.0

    def test_project_keys_use_the_project_names(self):
        """``behavioral_config`` is read by ``thigmotaxis_distance_cm``, not the settings name."""
        _shared, project_manager = self._save({}, form_speed=110.0)

        behavioural = project_manager.project_data["behavioral_config"]
        assert behavioural["thigmotaxis_distance_cm"] == 15.0
        assert "default_thigmotaxis_distance_cm" not in behavioural

    def test_keys_the_form_does_not_edit_are_kept(self):
        _shared, project_manager = self._save(
            {"geotaxis_enabled": True, "aquarium_perspective": "lateral"}, form_speed=60.0
        )

        assert project_manager.project_data["behavioral_config"]["geotaxis_enabled"] is True


class TestSavingRefreshesTheZoneTabRule:
    """A2-13: the Zones tab panel kept showing the old ROI rule after a save.

    It is seeded only when the tab is built, and nothing called its
    ``set_roi_rule_config``. After "Save Settings" it now shows the rule the
    resolver reads (project > settings > default), for both save paths.
    """

    @staticmethod
    def _builder(project_path: str | None):
        from zebtrack.settings import load_settings

        settings = load_settings()
        gui = MagicMock()
        gui._extract_setting.side_effect = lambda _obj, _path, default: default
        project_manager = gui.controller.project_manager
        project_manager.project_path = project_path
        project_manager.project_data = {}
        builder = AnalysisWidgetsBuilder(gui, MagicMock(), settings_obj=settings)
        return builder, gui, settings

    def test_a_project_save_shows_the_saved_rule(self, monkeypatch):
        builder, gui, settings = self._builder("C:/proj")
        # Only the form-shape check is skipped; the merge, the Settings
        # validation, the project write and the resolver are real.
        monkeypatch.setattr(builder, "_validate_config_values", lambda values: None)
        assert settings.roi_inclusion_rule != "centroid_in"

        builder.on_save_global_config_from_widget({"roi_inclusion_rule": "centroid_in"})

        shown = gui.zone_controls.set_roi_rule_config.call_args.args[0]
        assert shown.rule == "centroid_in"
        assert (
            gui.controller.project_manager.project_data["roi_settings"]["roi_inclusion_rule"]
            == "centroid_in"
        )
