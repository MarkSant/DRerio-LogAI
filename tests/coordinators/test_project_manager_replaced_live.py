"""The live/recording coordinators must adopt a replaced ProjectManager.

``close_project`` does not mutate the existing manager: it builds a brand new
empty one and announces it via ``PROJECT_MANAGER_REPLACED``. Three coordinators
stored their manager at construction time and were never told, so after a close
they still saw the CLOSED project as open.

The user-visible symptom was a single-video LIVE camera analysis (started from
the main window, with no project at all) being asked "reuse existing zones?" and
being shown an unrelated closed project's arena -- because
``ensure_zones_before_recording`` reads ``project_path`` and ``get_zone_data()``
off that stale manager. The same staleness also lands the session's output
inside the closed project's directory.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from zebtrack.coordinators.live_calibration_coordinator import LiveCalibrationCoordinator
from zebtrack.core.viewmodels.main_view_model_runtime import MainViewModelRuntime


def _calibration_coordinator() -> LiveCalibrationCoordinator:
    return LiveCalibrationCoordinator(
        state_manager=MagicMock(),
        project_manager=MagicMock(),
        detector_service=MagicMock(),
        weight_manager=MagicMock(),
        settings_obj=MagicMock(),
        event_bus=MagicMock(),
        root=None,
        view=None,
    )


class TestLiveCalibrationCoordinator:
    def test_adopts_the_new_manager(self):
        coord = _calibration_coordinator()
        old = coord.project_manager
        new = MagicMock()

        coord._on_project_manager_replaced({"new_manager": new})

        assert coord.project_manager is new
        assert coord.project_manager is not old

    def test_clears_project_scoped_session_state(self):
        """A handshake tied to a closed project must not survive into the next session."""
        coord = _calibration_coordinator()
        coord._pending_zone_confirmation = True
        coord._session_count = 4
        coord._last_calibration_cancelled = True
        coord._calibration_detector = MagicMock()
        coord._calibration_preserve_real_shape = True
        coord._last_polygon_source = "auto"
        coord._adhoc_zone_dir = "C:/tmp/zebtrack_live_adhoc_old"

        coord._on_project_manager_replaced({"new_manager": MagicMock()})

        assert coord._pending_zone_confirmation is False
        assert coord._session_count == 0
        assert coord._last_calibration_cancelled is False
        assert coord._calibration_detector is None
        assert coord._calibration_preserve_real_shape is False
        assert coord._last_polygon_source is None
        assert coord._adhoc_zone_dir is None

    def test_ignores_a_payload_without_a_manager(self):
        """Never drop the working manager because an event arrived malformed."""
        coord = _calibration_coordinator()
        original = coord.project_manager

        coord._on_project_manager_replaced({"new_manager": None})

        assert coord.project_manager is original

    def test_accepts_a_dataclass_style_payload(self):
        coord = _calibration_coordinator()
        new = MagicMock()

        coord._on_project_manager_replaced(SimpleNamespace(new_manager=new))

        assert coord.project_manager is new


class TestRuntimeBroadcast:
    """The runtime must actually REACH the three live/recording coordinators."""

    @pytest.mark.parametrize(
        "attr",
        [
            "live_calibration_coordinator",
            "live_camera_session_coordinator",
            "recording_session_coordinator",
        ],
    )
    def test_coordinator_receives_the_replacement(self, attr):
        new_manager = MagicMock()
        target = MagicMock()
        # Force the duck-typed protocol branch off so the runtime falls back to
        # direct attribute assignment, which is what a plain coordinator needs.
        del target._on_project_manager_replaced

        vm = MagicMock()
        setattr(vm, attr, target)
        runtime = MainViewModelRuntime(vm)

        runtime.handle_project_manager_replaced({"new_manager": new_manager})

        assert target.project_manager is new_manager

    def test_protocol_hook_is_preferred_when_present(self):
        new_manager = MagicMock()
        target = MagicMock()

        vm = MagicMock()
        vm.live_calibration_coordinator = target
        runtime = MainViewModelRuntime(vm)

        runtime.handle_project_manager_replaced({"new_manager": new_manager})

        target._on_project_manager_replaced.assert_called_once()
