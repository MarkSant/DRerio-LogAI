"""Tests for UICoordinator helper behaviors."""

from collections.abc import Callable
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import UIEvents
from zebtrack.ui.ui_coordinator import (
    AQUARIUM_DETECTION_DEFAULT_FRAMES,
    AQUARIUM_DETECTION_STALE_MS,
    UICoordinator,
)


def test_safe_ui_call_uses_root_after():
    event_bus = MagicMock()
    root = MagicMock()
    func = MagicMock()

    coordinator = UICoordinator(event_bus=event_bus, root=root)

    coordinator._safe_ui_call(func)

    root.after.assert_called_once_with(0, func)
    func.assert_not_called()


def test_safe_ui_call_without_root_calls_directly():
    event_bus = MagicMock()
    func = MagicMock()

    coordinator = UICoordinator(event_bus=event_bus, root=None)

    coordinator._safe_ui_call(func)

    func.assert_called_once()


def test_get_statistics_returns_counts():
    event_bus = MagicMock()
    coordinator = UICoordinator(event_bus=event_bus)

    coordinator._events_handled = 5
    coordinator._errors_count = 2

    assert coordinator.get_statistics() == {"events_handled": 5, "errors_count": 2}


def test_setup_subscriptions_registers_key_events():
    event_bus = MagicMock()

    UICoordinator(event_bus=event_bus)

    subscribed_events = [call.args[0] for call in event_bus.subscribe.call_args_list]
    assert UIEvents.ZONES_UPDATED in subscribed_events
    assert UIEvents.VIDEO_TREE_REFRESH_REQUESTED in subscribed_events
    assert UIEvents.ANALYSIS_TASK_STATUS_UPDATED in subscribed_events
    assert UIEvents.ZONE_DISPLAY_CLEARED in subscribed_events


def test_on_video_tree_refresh_requests_population():
    event_bus = MagicMock()
    project_view_manager = MagicMock()

    coordinator = UICoordinator(event_bus=event_bus, project_view_manager=project_view_manager)

    coordinator._on_video_tree_refresh_requested({"filter_text": "fish"})

    project_view_manager._populate_video_selector_tree.assert_called_once_with("fish")


def test_on_readiness_snapshot_updated_applies_snapshot():
    event_bus = MagicMock()
    project_view_manager = MagicMock()
    coordinator = UICoordinator(event_bus=event_bus, project_view_manager=project_view_manager)

    payload = {
        "ready_with_trajectory": [{"path": "a"}],
        "ready_with_zones": [{"path": "b"}],
        "arena_only": [{"path": "c"}],
        "without_arena": [{"path": "d"}],
    }

    coordinator._on_readiness_snapshot_updated(payload)

    project_view_manager.apply_pending_readiness_snapshot.assert_called_once_with(**payload)


def test_on_project_views_refresh_requested_delegates():
    event_bus = MagicMock()
    project_view_manager = MagicMock()
    coordinator = UICoordinator(event_bus=event_bus, project_view_manager=project_view_manager)

    coordinator._on_project_views_refresh_requested(
        {"reason": "zones", "append_summary": True, "immediate": True}
    )

    project_view_manager.refresh_project_views.assert_called_once_with(
        reason="zones", append_summary=True, immediate=True
    )


def test_on_processing_stats_updated_delegates():
    event_bus = MagicMock()
    state_synchronizer = MagicMock()
    coordinator = UICoordinator(event_bus=event_bus, state_synchronizer=state_synchronizer)

    coordinator._on_processing_stats_updated({"fps": 30})

    state_synchronizer.update_processing_stats.assert_called_once_with(fps=30)


def test_on_external_trigger_notice_calls_dialog():
    event_bus = MagicMock()
    dialog_manager = MagicMock()
    coordinator = UICoordinator(event_bus=event_bus, dialog_manager=dialog_manager)

    coordinator._on_external_trigger_notice({"session_label": "S1", "source": "io"})

    dialog_manager.show_external_trigger_notice.assert_called_once_with(
        "S1", session_label="S1", source="io"
    )


def test_on_external_trigger_notice_cleared_calls_dialog():
    event_bus = MagicMock()
    dialog_manager = MagicMock()
    coordinator = UICoordinator(event_bus=event_bus, dialog_manager=dialog_manager)

    coordinator._on_external_trigger_notice_cleared({})

    dialog_manager.clear_external_trigger_notice.assert_called_once()


# --- F2-UI-007: the camera-disconnect dialog must go away when the camera is back -------------

RECOVERY_DIALOG = (
    "zebtrack.ui.dialogs.camera_disconnect_recovery_dialog.CameraDisconnectRecoveryDialog"
)


def _immediate_root() -> MagicMock:
    """A Tk root whose ``after(0, f)`` runs ``f`` at once (the main loop, collapsed)."""
    root = MagicMock()
    root.after.side_effect = lambda _delay, func, *args: func(*args)
    return root


def _disconnect(experiment_id: str = "E1") -> dict:
    return {"gap_duration_s": 4.0, "experiment_id": experiment_id}


def test_reconnect_closes_the_dialog_the_disconnect_opened():
    coordinator = UICoordinator(event_bus=MagicMock(), root=_immediate_root())

    with patch(RECOVERY_DIALOG) as dialog_cls:
        coordinator._on_camera_disconnect(_disconnect())
        dialog_cls.return_value.close_dialog.assert_not_called()

        coordinator._on_camera_reconnected({"gap_duration_s": 6.5, "total_gaps": 1})

    dialog_cls.assert_called_once()
    dialog_cls.return_value.close_dialog.assert_called_once_with()


def test_a_second_reconnect_has_no_dialog_left_to_close():
    coordinator = UICoordinator(event_bus=MagicMock(), root=_immediate_root())

    with patch(RECOVERY_DIALOG) as dialog_cls:
        coordinator._on_camera_disconnect(_disconnect())
        coordinator._on_camera_reconnected({"gap_duration_s": 6.5, "total_gaps": 1})
        coordinator._on_camera_reconnected({"gap_duration_s": 0.0, "total_gaps": 1})

    dialog_cls.return_value.close_dialog.assert_called_once_with()


def test_reconnect_without_any_dialog_is_harmless():
    coordinator = UICoordinator(event_bus=MagicMock(), root=_immediate_root())

    coordinator._on_camera_reconnected({"gap_duration_s": 1.0, "total_gaps": 1})

    assert coordinator.get_statistics() == {"events_handled": 1, "errors_count": 0}


def test_a_new_disconnect_closes_the_previous_dialog_before_opening_its_own():
    coordinator = UICoordinator(event_bus=MagicMock(), root=_immediate_root())
    first, second = MagicMock(name="first"), MagicMock(name="second")

    with patch(RECOVERY_DIALOG, side_effect=[first, second]):
        coordinator._on_camera_disconnect(_disconnect("E1"))
        first.close_dialog.assert_not_called()
        coordinator._on_camera_disconnect(_disconnect("E2"))
        first.close_dialog.assert_called_once_with()
        second.close_dialog.assert_not_called()
        coordinator._on_camera_reconnected({"gap_duration_s": 1.0, "total_gaps": 2})

    second.close_dialog.assert_called_once_with()


def test_the_dialog_is_closed_on_the_tk_thread_not_the_event_bus_thread():
    root = MagicMock()
    coordinator = UICoordinator(event_bus=MagicMock(), root=root)
    dialog = MagicMock()
    coordinator._camera_disconnect_dialog = dialog

    coordinator._on_camera_reconnected({"gap_duration_s": 1.0, "total_gaps": 1})

    dialog.close_dialog.assert_not_called()  # only scheduled, as a worker thread would
    scheduled = [call.args[1] for call in root.after.call_args_list if call.args[0] == 0]
    for func in scheduled:
        func()
    dialog.close_dialog.assert_called_once_with()


@pytest.mark.gui
def test_the_real_dialog_the_user_told_to_wait_is_gone_after_the_reconnect(tkinter_root):
    event_bus = MagicMock()
    coordinator = UICoordinator(event_bus=event_bus, root=tkinter_root)

    coordinator._on_camera_disconnect(_disconnect())
    tkinter_root.update()
    dialog = coordinator._camera_disconnect_dialog
    assert dialog is not None
    assert dialog.winfo_exists()

    dialog._on_wait()  # the user chose "wait": the dialog now ignores every further action
    dialog._on_stop()
    assert dialog.winfo_exists()

    coordinator._on_camera_reconnected({"gap_duration_s": 6.5, "total_gaps": 1})
    tkinter_root.update()

    assert not dialog.winfo_exists()
    assert coordinator._camera_disconnect_dialog is None


# --- F2-UI-008: the aquarium-detection dialog must close when detection ends ----------------

DETECTION_DIALOG = (
    "zebtrack.ui.dialogs.aquarium_detection_progress_dialog.AquariumDetectionProgressDialog"
)


class _FakeTkRoot:
    """``after(0, f)`` queues ``f`` for ``run_queued``; timed ``after`` calls wait in ``timers``."""

    def __init__(self) -> None:
        self.queued: list = []
        self.timers: dict[str, tuple[int, Callable[[], None]]] = {}
        self._next = 0

    def after(self, delay, func, *args):
        if delay == 0:
            self.queued.append(lambda: func(*args))
            return "immediate"
        self._next += 1
        timer_id = f"timer{self._next}"
        self.timers[timer_id] = (delay, func)
        return timer_id

    def after_cancel(self, timer_id) -> None:
        self.timers.pop(timer_id, None)

    def run_queued(self) -> None:
        while self.queued:
            self.queued.pop(0)()

    def fire_timers(self) -> None:
        pending, self.timers = list(self.timers.values()), {}
        for _delay, func in pending:
            func()


def _progress(frame_number: int, max_frames: int | None = 10, **extra) -> payloads.EventPayload:
    return payloads.AquariumDetectionProgressPayload(
        frame_number=frame_number,
        max_frames=max_frames,
        experiment_id="E1",
        detected_bbox=(1, 2, 30, 40),
        is_valid=True,
        valid_count=1,
        **extra,
    )


def _publish(coordinator: UICoordinator, root: _FakeTkRoot, *events) -> None:
    for event in events:
        coordinator._on_aquarium_detection_progress(event)
    root.run_queued()


def test_detection_dialog_opens_on_the_first_event_even_when_it_is_frame_zero():
    root = _FakeTkRoot()
    coordinator = UICoordinator(event_bus=MagicMock(), root=root)

    with patch(DETECTION_DIALOG) as dialog_cls:
        _publish(coordinator, root, _progress(0, max_frames=10))

    dialog_cls.assert_called_once_with(parent=root, experiment_id="E1", max_frames=10)
    dialog_cls.return_value.update_progress.assert_called_once_with(
        frame_number=0, frame_image=None, detected_bbox=(1, 2, 30, 40), is_valid=True
    )


def test_detection_dialog_is_sized_by_the_payload_not_by_a_constant():
    root = _FakeTkRoot()
    coordinator = UICoordinator(event_bus=MagicMock(), root=root)

    with patch(DETECTION_DIALOG) as dialog_cls:
        _publish(coordinator, root, _progress(3, max_frames=300))

    assert dialog_cls.call_args.kwargs["max_frames"] == 300


@pytest.mark.parametrize("missing", [None, 0, -4, True])
def test_a_payload_without_a_usable_max_falls_back_to_the_default_length(missing):
    root = _FakeTkRoot()
    coordinator = UICoordinator(event_bus=MagicMock(), root=root)

    with patch(DETECTION_DIALOG) as dialog_cls:
        _publish(coordinator, root, _progress(3, max_frames=missing))

    assert dialog_cls.call_args.kwargs["max_frames"] == AQUARIUM_DETECTION_DEFAULT_FRAMES == 100


def test_detection_dialog_closes_on_the_last_frame_of_the_phase_the_payload_declares():
    root = _FakeTkRoot()
    coordinator = UICoordinator(event_bus=MagicMock(), root=root)

    with patch(DETECTION_DIALOG) as dialog_cls:
        _publish(coordinator, root, _progress(0), _progress(8))
        dialog_cls.return_value.close_dialog.assert_not_called()

        _publish(coordinator, root, _progress(9))  # 10 frames: 0..9

    dialog_cls.return_value.close_dialog.assert_called_once_with()
    assert coordinator._aquarium_detection_dialog is None
    assert root.timers == {}  # nothing left to close a dialog that is gone


def test_a_frame_past_the_old_hard_coded_hundred_does_not_close_a_longer_phase():
    root = _FakeTkRoot()
    coordinator = UICoordinator(event_bus=MagicMock(), root=root)

    with patch(DETECTION_DIALOG) as dialog_cls:
        _publish(coordinator, root, _progress(0, 300), _progress(100, 300), _progress(250, 300))

    dialog_cls.return_value.close_dialog.assert_not_called()
    assert coordinator._aquarium_detection_dialog is dialog_cls.return_value


def test_a_second_event_for_the_final_frame_does_not_reopen_the_dialog():
    root = _FakeTkRoot()
    coordinator = UICoordinator(event_bus=MagicMock(), root=root)

    with patch(DETECTION_DIALOG) as dialog_cls:
        # A frame with two detections publishes twice with the same counter.
        _publish(coordinator, root, _progress(0), _progress(9), _progress(9))

    dialog_cls.assert_called_once()
    assert coordinator._aquarium_detection_dialog is None


def test_two_events_racing_the_main_loop_open_one_dialog():
    root = _FakeTkRoot()
    coordinator = UICoordinator(event_bus=MagicMock(), root=root)

    with patch(DETECTION_DIALOG) as dialog_cls:
        # Both arrive before the Tk thread ran the first creation.
        _publish(coordinator, root, _progress(0), _progress(0))

    dialog_cls.assert_called_once()


def test_the_next_phase_gets_a_fresh_dialog():
    root = _FakeTkRoot()
    coordinator = UICoordinator(event_bus=MagicMock(), root=root)
    first, second = MagicMock(name="first"), MagicMock(name="second")

    with patch(DETECTION_DIALOG, side_effect=[first, second]) as dialog_cls:
        _publish(coordinator, root, _progress(0), _progress(9))
        _publish(coordinator, root, _progress(0))

    assert dialog_cls.call_count == 2
    first.close_dialog.assert_called_once_with()
    second.close_dialog.assert_not_called()
    assert coordinator._aquarium_detection_dialog is second


def test_when_progress_goes_quiet_the_watchdog_closes_the_dialog():
    root = _FakeTkRoot()
    coordinator = UICoordinator(event_bus=MagicMock(), root=root)

    with patch(DETECTION_DIALOG) as dialog_cls:
        _publish(coordinator, root, _progress(0, 300))

        # One countdown, of the documented length, armed by that event.
        assert [delay for delay, _func in root.timers.values()] == [AQUARIUM_DETECTION_STALE_MS]
        assert AQUARIUM_DETECTION_STALE_MS == 5000
        dialog_cls.return_value.close_dialog.assert_not_called()

        root.fire_timers()

    dialog_cls.return_value.close_dialog.assert_called_once_with()
    assert coordinator._aquarium_detection_dialog is None


def test_every_progress_event_restarts_the_watchdog():
    root = _FakeTkRoot()
    coordinator = UICoordinator(event_bus=MagicMock(), root=root)

    with patch(DETECTION_DIALOG):
        _publish(coordinator, root, _progress(0, 300))
        (first_id,) = root.timers
        _publish(coordinator, root, _progress(1, 300))

    assert len(root.timers) == 1  # the earlier countdown was cancelled, not stacked
    assert first_id not in root.timers


def test_the_status_bar_counts_against_the_payload_length():
    root = _FakeTkRoot()
    synchronizer = MagicMock()
    coordinator = UICoordinator(event_bus=MagicMock(), root=root, state_synchronizer=synchronizer)

    with patch(DETECTION_DIALOG):
        _publish(coordinator, root, _progress(0, max_frames=10))

    synchronizer.update_status.assert_called_once_with("Detecting aquarium: frame 0/10")


def test_a_payload_without_a_frame_number_does_not_raise():
    root = _FakeTkRoot()
    coordinator = UICoordinator(event_bus=MagicMock(), root=root)

    with patch(DETECTION_DIALOG):
        _publish(coordinator, root, payloads.AquariumDetectionProgressPayload(max_frames=10))

    assert coordinator.get_statistics() == {"events_handled": 1, "errors_count": 0}


@pytest.mark.gui
def test_the_real_detection_dialog_is_gone_after_the_last_frame(tkinter_root):
    coordinator = UICoordinator(event_bus=MagicMock(), root=tkinter_root)

    coordinator._on_aquarium_detection_progress(_progress(0, max_frames=10))
    tkinter_root.update()
    dialog = coordinator._aquarium_detection_dialog
    assert dialog is not None
    assert dialog.winfo_exists()

    for frame_number in range(1, 10):
        coordinator._on_aquarium_detection_progress(_progress(frame_number, max_frames=10))
    tkinter_root.update()

    assert not dialog.winfo_exists()
    assert coordinator._aquarium_detection_dialog is None
