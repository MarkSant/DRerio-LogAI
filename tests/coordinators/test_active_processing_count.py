"""Card "Processando" AO VIVO — contador de aquários sob análise agora.

Cobre ProgressTrackingCoordinator: a contagem por tarefa (paralelo = N,
sequencial/single = 1) e a emissão de ``UI_UPDATE_PROCESSING_COUNT`` no
início, na troca de tarefa e ao concluir (zera).
"""

from __future__ import annotations

from threading import Event
from unittest.mock import MagicMock

import pytest

from zebtrack.coordinators.progress_tracking_coordinator import ProgressTrackingCoordinator
from zebtrack.ui.event_bus_v2 import UIEvents


@pytest.fixture
def ptc():
    return ProgressTrackingCoordinator(
        state_manager=MagicMock(),
        settings_obj=MagicMock(),
        ui_coordinator=MagicMock(),
        cancel_event=Event(),
        event_bus=MagicMock(),
        view=None,
        root=None,
    )


def _processing_counts(event_bus: MagicMock) -> list[int]:
    """Counts emitidos via UI_UPDATE_PROCESSING_COUNT, em ordem."""
    counts: list[int] = []
    for call in event_bus.publish.call_args_list:
        event = call.args[0]
        if event.type is UIEvents.UI_UPDATE_PROCESSING_COUNT:
            counts.append(event.data.count)
    return counts


# ---------------------------------------------------------------------------
# _aquarium_count_for_task
# ---------------------------------------------------------------------------


def test_parallel_multi_aquarium_counts_all_aquariums():
    task = {
        "is_multi_aquarium": True,
        "zone_data": {"aquariums": [{"id": 0}, {"id": 1}]},
    }
    assert ProgressTrackingCoordinator._aquarium_count_for_task(task) == 2


def test_single_video_counts_one():
    assert ProgressTrackingCoordinator._aquarium_count_for_task({"path": "v.mp4"}) == 1


def test_sequential_exploded_task_counts_one():
    # Tarefas sequenciais chegam explodidas em 1-aquário (is_multi_aquarium=False).
    task = {"is_multi_aquarium": False, "zone_data": {"aquariums": [{"id": 0}]}}
    assert ProgressTrackingCoordinator._aquarium_count_for_task(task) == 1


def test_none_task_counts_one():
    assert ProgressTrackingCoordinator._aquarium_count_for_task(None) == 1


def test_multi_aquarium_flag_without_zone_data_counts_one():
    assert ProgressTrackingCoordinator._aquarium_count_for_task({"is_multi_aquarium": True}) == 1


# ---------------------------------------------------------------------------
# Lifecycle: start → troca de tarefa → conclusão
# ---------------------------------------------------------------------------


def test_started_publishes_count_for_first_task(ptc):
    ptc._batch_videos = [{"is_multi_aquarium": True, "zone_data": {"aquariums": [{}, {}]}}]
    ptc._current_video_idx = -1

    ptc._on_processing_started("v.mp4")

    assert _processing_counts(ptc.event_bus) == [2]
    # A contagem é incluída no MESMO update_processing_state do start (snapshot
    # coerente para observers), e o evento de UI é emitido em seguida.
    ptc.state_manager.update_processing_state.assert_any_call(
        source="processing_coordinator._on_processing_started",
        is_processing=True,
        current_video="v.mp4",
        active_processing_count=2,
    )


def test_task_switch_republishes_count(ptc):
    # Lote sequencial de 2 vídeos single-aquário: cada um conta 1.
    ptc._batch_videos = [{"path": "a.mp4"}, {"path": "b.mp4"}]
    ptc._current_video_idx = 0

    ptc._on_processing_progress({"idx": 1, "total_frames": 0})

    assert ptc._current_video_idx == 1
    assert _processing_counts(ptc.event_bus) == [1]


def test_complete_resets_count_to_zero(ptc):
    ptc._batch_videos = [{"path": "a.mp4"}]
    ptc._on_processing_complete({"videos_to_process": [{"path": "a.mp4"}], "success": True})

    assert _processing_counts(ptc.event_bus)[-1] == 0
    # Reset coerente: count=0 no MESMO update que desliga is_processing.
    ptc.state_manager.update_processing_state.assert_any_call(
        source="processing_coordinator._on_processing_complete",
        is_processing=False,
        current_video=None,
        active_processing_count=0,
    )


def test_fatal_error_resets_count_to_zero(ptc):
    ptc._on_processing_fatal_error({"error": "boom", "message": "falhou"})

    assert _processing_counts(ptc.event_bus)[-1] == 0
    ptc.state_manager.update_processing_state.assert_any_call(
        source="processing_coordinator._on_processing_fatal_error",
        is_processing=False,
        current_video=None,
        active_processing_count=0,
    )
