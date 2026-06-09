"""Tests for the live-analysis dispatch of RecordingSessionCoordinator.

Regressão (4º call site do fix de91d9d6): ``_schedule_recording`` com
``is_live_analysis=True`` despacha para ``LiveCameraService.start_session``
com preview integrado (``use_external_preview=False``), mas não executava a
preparação da aba "Análise" feita pelos 3 entrypoints do
``LiveCameraSessionCoordinator`` — então a 2ª gravação temporizada de projeto
live (retomada via confirmação de zonas) ficava com o preview congelado.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.coordinators import live_session_ui_prep
from zebtrack.coordinators.recording_session_coordinator import RecordingSessionCoordinator


def _make_coordinator(**overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "state_manager": MagicMock(),
        "recording_service": MagicMock(),
        "live_camera_service": MagicMock(),
        "project_manager": MagicMock(),
        "settings_obj": MagicMock(),
        "live_calibration_coordinator": MagicMock(),
        "event_bus": None,
        "arduino_manager": None,
        "root": None,
        "view": None,
    }
    kwargs.update(overrides)
    return cast(Any, RecordingSessionCoordinator(**kwargs))


def test_schedule_recording_live_dispatch_prepares_analysis_tab():
    """O despacho live deve preparar a aba Análise ANTES de start_session."""
    coord = _make_coordinator()
    coord.live_camera_service.start_session.return_value = True

    call_order: list[str] = []

    def _fake_start_session(**kwargs: Any) -> bool:
        call_order.append("start_session")
        return True

    coord.live_camera_service.start_session.side_effect = _fake_start_session

    context = {
        "is_live_analysis": True,
        "output_folder": "/tmp/out",
        "day": 1,
        "group": "Controle",
        "cobaia": "1",
        "camera_index": 0,
    }
    with patch.object(
        live_session_ui_prep,
        "prepare_analysis_tab_for_live_session",
        side_effect=lambda view, root: call_order.append("prepare"),
    ) as mock_prepare:
        coord._schedule_recording(context, {"recording_duration_s": 30}, trigger_source="manual")

    mock_prepare.assert_called_once_with(None, None)
    coord.live_camera_service.start_session.assert_called_once()
    assert call_order == ["prepare", "start_session"]
    # Sanidade: continua usando o canvas integrado da aba Análise.
    assert coord.live_camera_service.start_session.call_args.kwargs["use_external_preview"] is False


def test_schedule_recording_dumb_recording_does_not_prepare_analysis_tab():
    """Sem is_live_analysis (gravação "burra"), a preparação não roda."""
    coord = _make_coordinator()

    context = {"output_folder": "/tmp/out", "folder_name": "D1_GC_S1"}
    with patch.object(
        live_session_ui_prep, "prepare_analysis_tab_for_live_session"
    ) as mock_prepare:
        coord._schedule_recording(context, {}, trigger_source="manual")

    mock_prepare.assert_not_called()
    coord.recording_service.schedule_recording.assert_called_once()
    coord.live_camera_service.start_session.assert_not_called()


def test_prepare_analysis_tab_helper_resets_resubscribes_and_activates():
    """A função compartilhada executa as 3 preparações no view fornecido."""
    view = MagicMock()
    view.analysis_active = False

    live_session_ui_prep.prepare_analysis_tab_for_live_session(view, None)

    view.analysis_display_widget.reset_progress_stats.assert_called_once()
    view.canvas_manager.subscribe_to_live_frames.assert_called_once()
    assert view.analysis_active is True
    view.analysis_view_controller.switch_to_analysis_view.assert_called_once()


def test_prepare_analysis_tab_helper_tolerates_headless_view():
    """view=None (headless/testes) não pode levantar exceção."""
    live_session_ui_prep.prepare_analysis_tab_for_live_session(None, None)


def test_prepare_analysis_tab_helper_uses_root_after_when_root_present():
    """Com root presente, updates de UI são agendados via root.after(0, ...)."""
    view = MagicMock()
    root = MagicMock()

    live_session_ui_prep.prepare_analysis_tab_for_live_session(view, root)

    # reset dos contadores e ativação da view vão para a thread do Tk.
    assert root.after.call_count == 2
    for call in root.after.call_args_list:
        assert call.args[0] == 0
    view.analysis_display_widget.reset_progress_stats.assert_not_called()


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
