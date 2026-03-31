"""
Tests for dual-weight detection mode enforcement logic.

Phase 3E: Refactored to test ProjectWorkflowService directly
instead of going through the full MainViewModel stack.
"""

import tempfile
from unittest.mock import MagicMock

from zebtrack.core.project.project_workflow_service import ProjectWorkflowService
from zebtrack.ui.event_bus_v2 import UIEvents


def test_detection_mode_with_multiple_animals_blocked():
    """Test that detection mode with multiple animals is blocked with clear error."""
    # Create minimal mocks for ProjectWorkflowService
    mock_pm = MagicMock()
    mock_model_service = MagicMock()
    mock_state_manager = MagicMock()
    mock_ui_coordinator = MagicMock()
    mock_settings = MagicMock()
    mock_settings.model_selection.animal_method = "det"

    service = ProjectWorkflowService(
        project_manager=mock_pm,
        model_service=mock_model_service,
        state_manager=mock_state_manager,
        ui_coordinator=mock_ui_coordinator,
        settings_obj=mock_settings,
    )

    # Validate with det method + multiple animals - should fail
    is_valid, error_msg = service.validate_project_parameters(
        animal_method="det",
        animals_per_aquarium=3,
    )

    assert not is_valid
    assert error_msg is not None
    assert "modo de detecção (det)" in error_msg
    assert "1 animal por aquário" in error_msg


def test_detection_mode_with_single_animal_allowed():
    """Test that detection mode with single animal is allowed."""
    mock_pm = MagicMock()
    mock_model_service = MagicMock()
    mock_state_manager = MagicMock()
    mock_ui_coordinator = MagicMock()
    mock_settings = MagicMock()
    mock_settings.model_selection.animal_method = "det"

    service = ProjectWorkflowService(
        project_manager=mock_pm,
        model_service=mock_model_service,
        state_manager=mock_state_manager,
        ui_coordinator=mock_ui_coordinator,
        settings_obj=mock_settings,
    )

    # Validate with det method + single animal - should pass
    is_valid, error_msg = service.validate_project_parameters(
        animal_method="det",
        animals_per_aquarium=1,
    )

    assert is_valid
    assert error_msg is None


def test_segmentation_mode_with_multiple_animals_allowed():
    """Test that segmentation mode with multiple animals is allowed."""
    mock_pm = MagicMock()
    mock_model_service = MagicMock()
    mock_state_manager = MagicMock()
    mock_ui_coordinator = MagicMock()
    mock_settings = MagicMock()
    mock_settings.model_selection.animal_method = "seg"

    service = ProjectWorkflowService(
        project_manager=mock_pm,
        model_service=mock_model_service,
        state_manager=mock_state_manager,
        ui_coordinator=mock_ui_coordinator,
        settings_obj=mock_settings,
    )

    # Validate with seg method + multiple animals - should pass
    is_valid, error_msg = service.validate_project_parameters(
        animal_method="seg",
        animals_per_aquarium=3,
    )

    assert is_valid
    assert error_msg is None


def test_single_video_detection_mode_enforcement():
    """Test enforcement in single video workflow via AnalysisControlViewModel."""
    from tests.helpers import create_mock_settings, create_test_controller

    with tempfile.TemporaryDirectory():
        # Create mock settings with detection mode
        mock_settings = create_mock_settings()
        mock_settings.model_selection.animal_method = "det"

        # Create mock root
        mock_root = MagicMock()

        # Mock event bus
        mock_event_bus = MagicMock()

        # Create controller using factory
        controller = create_test_controller(
            root=mock_root, settings_obj=mock_settings, event_bus=mock_event_bus
        )

        # Mock detector
        controller.detector = MagicMock()

        # Config with multiple animals - should be blocked
        config = {
            "animals_per_aquarium": 2,
            "num_aquariums": 1,
        }

        # This should show an error and return early
        controller.analysis_vm.start_single_video_workflow(
            "/tmp/test.mp4",
            config,
            detector_vm=controller.hardware_vm,
        )

        # Verify error was shown via v2 publish(Event(...))
        mock_event_bus.publish.assert_called_once()
        call_ev = mock_event_bus.publish.call_args[0][0]
        assert call_ev.type == UIEvents.SHOW_ERROR
        assert "Configuração Inválida" in call_ev.data.title
        assert "modo de detecção (det)" in call_ev.data.message
