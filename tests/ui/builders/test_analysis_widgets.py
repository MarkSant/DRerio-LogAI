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
