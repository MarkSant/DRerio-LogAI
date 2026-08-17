"""Extended unit tests for coordinators/sequential_processing_coordinator.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.coordinators.sequential_processing_coordinator import (
    SequentialProcessingCoordinator,
)


class TestSequentialProcessingCoordinatorExtended:
    """Test SequentialProcessingCoordinator context management and lifecycle."""

    def test_initialization_and_context_property(self):
        state_mgr = MagicMock()
        project_mgr = MagicMock()
        detector_srv = MagicMock()
        settings = MagicMock()
        ui_coord = MagicMock()
        cancel_event = MagicMock()

        coordinator = SequentialProcessingCoordinator(
            state_manager=state_mgr,
            project_manager=project_mgr,
            detector_service=detector_srv,
            settings_obj=settings,
            ui_coordinator=ui_coord,
            cancel_event=cancel_event,
        )

        assert coordinator.sequential_context is None

        ctx = {"total_aquariums": 2, "current_index": 0}
        coordinator.sequential_context = ctx
        assert coordinator.sequential_context == ctx

    def test_process_next_aquarium_no_context(self):
        coordinator = SequentialProcessingCoordinator(
            state_manager=MagicMock(),
            project_manager=MagicMock(),
            detector_service=MagicMock(),
            settings_obj=MagicMock(),
            ui_coordinator=MagicMock(),
            cancel_event=MagicMock(),
        )
        coordinator._sequential_context = None
        # Should safely log and return without raising
        coordinator._process_next_aquarium_in_sequence()

    def test_process_next_aquarium_finalize_when_index_exceeds_total(self):
        coordinator = SequentialProcessingCoordinator(
            state_manager=MagicMock(),
            project_manager=MagicMock(),
            detector_service=MagicMock(),
            settings_obj=MagicMock(),
            ui_coordinator=MagicMock(),
            cancel_event=MagicMock(),
        )
        coordinator._sequential_context = {
            "current_index": 2,
            "total": 2,
            "completed": ["aq0", "aq1"],
        }
        coordinator._finalize_sequential_processing = MagicMock()  # type: ignore[assignment]
        coordinator._process_next_aquarium_in_sequence()
        coordinator._finalize_sequential_processing.assert_called_once()

    def test_finalize_sequential_processing_no_context(self):
        mock_state_mgr = MagicMock()
        coordinator = SequentialProcessingCoordinator(
            state_manager=mock_state_mgr,
            project_manager=MagicMock(),
            detector_service=MagicMock(),
            settings_obj=MagicMock(),
            ui_coordinator=MagicMock(),
            cancel_event=MagicMock(),
        )
        coordinator._sequential_context = None
        # Should return without raising or touching state_manager
        coordinator._finalize_sequential_processing()
        mock_state_mgr.update_processing_state.assert_not_called()

    def test_finalize_sequential_processing_with_completed_aquariums(self):
        mock_state_mgr = MagicMock()
        coordinator = SequentialProcessingCoordinator(
            state_manager=mock_state_mgr,
            project_manager=MagicMock(),
            detector_service=MagicMock(),
            settings_obj=MagicMock(),
            ui_coordinator=MagicMock(),
            cancel_event=MagicMock(),
        )
        coordinator._sequential_context = {
            "video_path": "/path/video.mp4",
            "completed": ["aq0", "aq1"],
            "failed": [],
        }
        coordinator._report_coordinator = None
        coordinator._finalize_sequential_processing()

        mock_state_mgr.update_processing_state.assert_called_once_with(
            source="processing_coordinator.sequential.finalized",
            is_processing=False,
            current_video=None,
        )
        assert coordinator._sequential_context is None
