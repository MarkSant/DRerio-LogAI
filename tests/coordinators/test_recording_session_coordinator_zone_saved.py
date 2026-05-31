"""Tests for RecordingSessionCoordinator._on_zone_saved ownership gating.

Regression: clicking "Salvar Edição" in the live auto-detect flow published a
zone-save event that RecordingSessionCoordinator consumed as a recording-resume
handshake — resetting the SHARED ``pending_zone_confirmation`` flag (owned by the
live flow) and re-triggering the recording path, which made the auto-detected
polygon reappear over the user's edit. The handshake must only act when THIS
coordinator owns a pending recording (``_pending_recording_context``).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from zebtrack.coordinators.recording_session_coordinator import RecordingSessionCoordinator


def _make_coordinator() -> RecordingSessionCoordinator:
    coord = RecordingSessionCoordinator(
        state_manager=MagicMock(),
        recording_service=MagicMock(),
        live_camera_service=MagicMock(),
        project_manager=MagicMock(),
        settings_obj=MagicMock(),
        live_calibration_coordinator=SimpleNamespace(pending_zone_confirmation=True),
        event_bus=MagicMock(),
        arduino_manager=None,
        root=None,
        view=None,
    )
    coord.start_recording = MagicMock()  # type: ignore[method-assign]
    return coord


def test_zone_saved_ignored_when_no_local_context_live_flow():
    """Live flow (no _pending_recording_context): must NOT reset the shared flag
    nor start a recording — otherwise "Salvar Edição" hijacks the live handshake."""
    coord = _make_coordinator()
    coord._pending_recording_context = None
    coord.live_calibration_coordinator.pending_zone_confirmation = True

    coord._on_zone_saved()

    # Flag compartilhada preservada (o fluxo live ainda precisa dela).
    assert coord.live_calibration_coordinator.pending_zone_confirmation is True
    coord.start_recording.assert_not_called()


def test_zone_saved_resumes_when_local_context_prerecorded_flow():
    """Pré-gravado (com _pending_recording_context): mantém o comportamento —
    reseta a flag e retoma a gravação."""
    coord = _make_coordinator()
    coord.project_manager.get_project_type.return_value = "live"
    coord._pending_recording_context = {"output_folder": "/tmp/out"}
    coord.live_calibration_coordinator.pending_zone_confirmation = True

    coord._on_zone_saved()

    assert coord.live_calibration_coordinator.pending_zone_confirmation is False
    coord.start_recording.assert_called_once()


def test_zone_saved_noop_when_not_pending():
    """Sem pending_zone_confirmation, é no-op (não reseta nada, não grava)."""
    coord = _make_coordinator()
    coord._pending_recording_context = {"output_folder": "/tmp/out"}
    coord.live_calibration_coordinator.pending_zone_confirmation = False

    coord._on_zone_saved()

    coord.start_recording.assert_not_called()


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
