"""
Tests for dual-weight detection mode enforcement logic.
"""

import tempfile
from unittest.mock import MagicMock, patch


def test_detection_mode_with_multiple_animals_blocked():
    """Test that detection mode with multiple animals is blocked with clear error."""
    with tempfile.TemporaryDirectory():
        # Mock settings to use detection mode for animals
        with patch("zebtrack.settings.settings") as mock_settings:
            mock_settings.model_selection.animal_method = "det"
            mock_settings.camera.desired_width = 640
            mock_settings.camera.desired_height = 480

            # Also patch settings import in the controller module
            with patch("zebtrack.core.main_view_model.settings", mock_settings):
                with patch("zebtrack.core.main_view_model.ApplicationGUI"):
                    from zebtrack.core.main_view_model import AppController

                    # Create controller with mocked view and components
                    mock_root = MagicMock()
                    controller = AppController(mock_root)

                    # Mock the project manager and weight manager
                controller.project_manager = MagicMock()
                controller.weight_manager = MagicMock()
                controller.active_weight_name = "test_weight"

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
                with patch.object(controller, "ui_event_bus", MagicMock()) as mock_event_bus:
                    controller.create_project_workflow(**project_kwargs)

                    # Verify error was shown and project creation was not called
                    mock_event_bus.publish_event.assert_called_once()
                    event_name, payload = mock_event_bus.publish_event.call_args[0]
                    assert event_name == "ui:show_error"
                    assert "Configuração Inválida" in payload["title"]
                    assert "modo de detecção (det)" in payload["message"]
                    assert "3 animais por aquário" in payload["message"]

                # Project manager should not have been called
                controller.project_manager.create_new_project.assert_not_called()


def test_detection_mode_with_single_animal_allowed():
    """Test that detection mode with single animal is allowed."""
    with tempfile.TemporaryDirectory():
        # Mock settings to use detection mode for animals
        with patch("zebtrack.settings.settings") as mock_settings:
            mock_settings.model_selection.animal_method = "det"
            mock_settings.camera.desired_width = 640
            mock_settings.camera.desired_height = 480

            # Also patch settings import in the controller module
            with patch("zebtrack.core.main_view_model.settings", mock_settings):
                with patch("zebtrack.core.main_view_model.ApplicationGUI") as MockApplicationGUI:
                    from zebtrack.core.main_view_model import AppController

                    # Create controller with mocked view and components
                    mock_root = MagicMock()
                    controller = AppController(mock_root)
                    mock_view = MockApplicationGUI.return_value
                    # Mock the project manager and weight manager
                controller.project_manager = MagicMock()
                controller.project_manager.create_new_project.return_value = True
                # Also update the service's reference to project_manager
                controller.project_workflow_service.project_manager = controller.project_manager
                controller.weight_manager = MagicMock()
                controller.active_weight_name = "test_weight"

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

                    # Verify no error was shown
                    mock_view.show_error.assert_not_called()

                    # Project manager should have been called
                    controller.project_manager.create_new_project.assert_called_once()


def test_segmentation_mode_with_multiple_animals_allowed():
    """Test that segmentation mode with multiple animals is allowed."""
    with tempfile.TemporaryDirectory():
        # Mock settings to use segmentation mode for animals
        with patch("zebtrack.settings.settings") as mock_settings:
            mock_settings.model_selection.animal_method = "seg"
            mock_settings.camera.desired_width = 640
            mock_settings.camera.desired_height = 480

            # Also patch settings import in the controller module
            with patch("zebtrack.core.main_view_model.settings", mock_settings):
                with patch("zebtrack.core.main_view_model.ApplicationGUI") as MockApplicationGUI:
                    from zebtrack.core.main_view_model import AppController

                    # Create controller with mocked view and components
                    mock_root = MagicMock()
                    controller = AppController(mock_root)
                    mock_view = MockApplicationGUI.return_value

                    # Mock the project manager and weight manager
                controller.project_manager = MagicMock()
                controller.project_manager.create_new_project.return_value = True
                # Also update the service's reference to project_manager
                controller.project_workflow_service.project_manager = controller.project_manager
                controller.weight_manager = MagicMock()
                controller.active_weight_name = "test_weight"

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

                    # Verify no error was shown
                    mock_view.show_error.assert_not_called()

                    # Project manager should have been called
                    controller.project_manager.create_new_project.assert_called_once()


def test_single_video_detection_mode_enforcement():
    """Test enforcement in single video workflow."""
    with tempfile.TemporaryDirectory():
        # Mock settings to use detection mode for animals
        with patch("zebtrack.settings.settings") as mock_settings:
            mock_settings.model_selection.animal_method = "det"
            mock_settings.camera.desired_width = 640
            mock_settings.camera.desired_height = 480

            # Also patch settings import in the controller module
            with patch("zebtrack.core.main_view_model.settings", mock_settings):
                with patch("zebtrack.core.main_view_model.ApplicationGUI") as MockApplicationGUI:
                    from zebtrack.core.main_view_model import AppController

                    # Create controller with mocked view and components
                    mock_root = MagicMock()
                    controller = AppController(mock_root)
                    mock_view = MockApplicationGUI.return_value
                    # Mock detector
                controller.detector = MagicMock()

                # Config with multiple animals - should be blocked
                config = {
                    "animals_per_aquarium": 2,
                    "num_aquariums": 1,
                }

                # This should show an error and return early
                with patch.object(controller, "ui_event_bus", MagicMock()) as mock_event_bus:
                    controller.start_single_video_workflow("/tmp/test.mp4", config)

                    # Verify error was shown
                    mock_event_bus.publish_event.assert_called_once()
                    event_name, payload = mock_event_bus.publish_event.call_args[0]
                    assert event_name == "ui:show_error"
                    assert "Configuração Inválida" in payload["title"]
                    assert "modo de detecção (det)" in payload["message"]

                # Zone setup should not have been called
                mock_view.setup_zone_definition_for_single_video.assert_not_called()
