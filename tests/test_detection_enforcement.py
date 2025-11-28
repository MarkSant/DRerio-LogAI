"""
Tests for dual-weight detection mode enforcement logic.
"""

import tempfile
from unittest.mock import MagicMock, patch

from tests.helpers import create_mock_settings, create_test_controller


def test_detection_mode_with_multiple_animals_blocked():
    """Test that detection mode with multiple animals is blocked with clear error."""
    with tempfile.TemporaryDirectory():
        # Create mock settings with detection mode
        mock_settings = create_mock_settings()
        mock_settings.model_selection.animal_method = "det"

        # Configure project manager mock BEFORE creating controller
        mock_pm = MagicMock()
        mock_pm.create_new_project.return_value = True

        # Create mock root
        mock_root = MagicMock()

        # Mock the event bus
        mock_event_bus = MagicMock()

        # Create controller using factory with project_manager and event_bus override
        controller = create_test_controller(
            root=mock_root,
            settings_obj=mock_settings,
            project_manager=mock_pm,
            event_bus=mock_event_bus,
            use_real_project_orchestrator=True,
        )

        # Try to create project with multiple animals per aquarium
        project_kwargs = {
            "project_path": "/tmp/test_project",
            "project_type": "pre-recorded",
            "animals_per_aquarium": 3,  # Multiple animals - should be blocked
            "num_aquariums": 1,
            "aquarium_width_cm": 10.0,
            "aquarium_height_cm": 10.0,
            "video_files": ["/tmp/test.mp4"],
        }

        # This should show an error and return early without creating project
        controller.create_project_workflow(**project_kwargs)

        # Verify error was shown via the event bus
        error_calls = [
            call
            for call in mock_event_bus.publish_event.call_args_list
            if len(call[0]) > 0 and "error" in str(call[0][0]).lower()
        ]
        assert len(error_calls) >= 1
        # Find the specific error call about detection mode
        det_error_calls = [
            call
            for call in error_calls
            if len(call) > 0
            and len(call[0]) > 1
            and isinstance(call[0][1], dict)
            and "modo de detecção" in call[0][1].get("message", "")
        ]
        assert len(det_error_calls) == 1
        event_name, payload = det_error_calls[0][0]
        assert "Configuração Inválida" in payload["title"]
        assert "modo de detecção (det)" in payload["message"]
        assert "3 animais por aquário" in payload["message"]

        # Project manager should not have been called
        mock_pm.create_new_project.assert_not_called()


def test_detection_mode_with_single_animal_allowed():
    """Test that detection mode with single animal is allowed."""
    with tempfile.TemporaryDirectory():
        # Create mock settings with detection mode
        mock_settings = create_mock_settings()
        mock_settings.model_selection.animal_method = "det"

        # Configure project manager mock BEFORE creating controller
        mock_pm = MagicMock()
        mock_pm.create_new_project.return_value = True

        # Create mock root
        mock_root = MagicMock()

        # Create controller using factory with project_manager override
        controller = create_test_controller(
            root=mock_root,
            settings_obj=mock_settings,
            project_manager=mock_pm,
            use_real_project_orchestrator=True,
        )

        # Mock setup_detector to succeed
        with patch.object(controller, "setup_detector", return_value=True):
            # Try to create project with single animal per aquarium
            project_kwargs = {
                "project_path": "/tmp/test_project",
                "project_type": "pre-recorded",
                "animals_per_aquarium": 1,  # Single animal - should be allowed
                "num_aquariums": 1,
                "aquarium_width_cm": 10.0,
                "aquarium_height_cm": 10.0,
                "video_files": ["/tmp/test.mp4"],
            }

            # This should succeed without error
            controller.create_project_workflow(**project_kwargs)

            # Verify no ui:show_error was published
            # (controller.view is a mock, can't check .show_error directly)

            # Project manager should have been called
            mock_pm.create_new_project.assert_called_once()


def test_segmentation_mode_with_multiple_animals_allowed():
    """Test that segmentation mode with multiple animals is allowed."""
    with tempfile.TemporaryDirectory():
        # Create mock settings with segmentation mode (default)
        mock_settings = create_mock_settings()
        mock_settings.model_selection.animal_method = "seg"

        # Configure project manager mock BEFORE creating controller
        mock_pm = MagicMock()
        mock_pm.create_new_project.return_value = True

        # Create mock root
        mock_root = MagicMock()

        # Create controller using factory with project_manager override
        controller = create_test_controller(
            root=mock_root,
            settings_obj=mock_settings,
            project_manager=mock_pm,
            use_real_project_orchestrator=True,
        )

        # Mock setup_detector to succeed
        with patch.object(controller, "setup_detector", return_value=True):
            # Try to create project with multiple animals per aquarium
            project_kwargs = {
                "project_path": "/tmp/test_project",
                "project_type": "pre-recorded",
                # Multiple animals - should be allowed in seg mode
                "animals_per_aquarium": 3,
                "num_aquariums": 1,
                "aquarium_width_cm": 10.0,
                "aquarium_height_cm": 10.0,
                "video_files": ["/tmp/test.mp4"],
            }

            # This should succeed without error
            controller.create_project_workflow(**project_kwargs)

            # Verify no ui:show_error was published
            # (controller.view is a mock, can't check .show_error directly)

            # Project manager should have been called
            mock_pm.create_new_project.assert_called_once()


def test_single_video_detection_mode_enforcement():
    """Test enforcement in single video workflow."""
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
        controller.start_single_video_workflow("/tmp/test.mp4", config)

        # Verify error was shown
        mock_event_bus.publish_event.assert_called_once()
        event_name, payload = mock_event_bus.publish_event.call_args[0]
        assert event_name == "ui:show_error"
        assert "Configuração Inválida" in payload["title"]
        assert "modo de detecção (det)" in payload["message"]

        # Zone setup should not have been called (view is mocked)
        # controller.view.setup_zone_definition_for_single_video would be a MagicMock method
