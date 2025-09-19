"""
Tests for dual-weight detection mode enforcement logic.
"""

import tempfile
from unittest.mock import patch, MagicMock

import pytest


def test_detection_mode_with_multiple_animals_blocked():
    """Test that detection mode with multiple animals is blocked with clear error."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Mock settings to use detection mode for animals
        with patch('zebtrack.settings.settings') as mock_settings:
            mock_settings.model_selection.animal_method = "det"
            mock_settings.camera.desired_width = 640  
            mock_settings.camera.desired_height = 480
            
            # Also patch settings import in the controller module
            with patch('zebtrack.core.controller.settings', mock_settings):
                from zebtrack.core.controller import AppController
                
                # Create controller with mocked view and components
                mock_view = MagicMock()
                controller = AppController(mock_view)
                
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
                    "video_files": ["/tmp/test.mp4"]
                }
                
                # This should show an error and return early without creating project
                controller.create_project_workflow(**project_kwargs)
                
                # Verify error was shown and project creation was not called
                mock_view.show_error.assert_called_once()
                error_title, error_msg = mock_view.show_error.call_args[0]
                assert "Configuração Inválida" in error_title
                assert "modo de detecção (det)" in error_msg
                assert "1 animal por aquário" in error_msg
                assert "3 animais por aquário" in error_msg
                
                # Project manager should not have been called
                controller.project_manager.create_new_project.assert_not_called()


def test_detection_mode_with_single_animal_allowed():
    """Test that detection mode with single animal is allowed."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Mock settings to use detection mode for animals
        with patch('zebtrack.settings.settings') as mock_settings:
            mock_settings.model_selection.animal_method = "det"
            mock_settings.camera.desired_width = 640  
            mock_settings.camera.desired_height = 480
            
            # Also patch settings import in the controller module
            with patch('zebtrack.core.controller.settings', mock_settings):
                from zebtrack.core.controller import AppController
                
                # Create controller with mocked view and components
                mock_view = MagicMock()
                controller = AppController(mock_view)
                
                # Mock the project manager and weight manager
                controller.project_manager = MagicMock()
                controller.project_manager.create_new_project.return_value = True
                controller.weight_manager = MagicMock()
                controller.active_weight_name = "test_weight"
                
                # Mock setup_detector to succeed
                with patch.object(controller, 'setup_detector', return_value=True):
                    # Try to create project with single animal per aquarium
                    project_kwargs = {
                        "project_path": "/tmp/test_project",
                        "project_type": "pre-recorded", 
                        "animals_per_aquarium": 1,  # Single animal - should be allowed
                        "num_aquariums": 1,
                        "aquarium_width_cm": 10.0,
                        "aquarium_height_cm": 10.0,
                        "video_files": ["/tmp/test.mp4"]
                    }
                    
                    # This should succeed without error
                    controller.create_project_workflow(**project_kwargs)
                    
                    # Verify no error was shown
                    mock_view.show_error.assert_not_called()
                    
                    # Project manager should have been called
                    controller.project_manager.create_new_project.assert_called_once()


def test_segmentation_mode_with_multiple_animals_allowed():
    """Test that segmentation mode with multiple animals is allowed."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Mock settings to use segmentation mode for animals
        with patch('zebtrack.settings.settings') as mock_settings:
            mock_settings.model_selection.animal_method = "seg"
            mock_settings.camera.desired_width = 640  
            mock_settings.camera.desired_height = 480
            
            # Also patch settings import in the controller module
            with patch('zebtrack.core.controller.settings', mock_settings):
                from zebtrack.core.controller import AppController
                
                # Create controller with mocked view and components
                mock_view = MagicMock()
                controller = AppController(mock_view)
                
                # Mock the project manager and weight manager
                controller.project_manager = MagicMock()
                controller.project_manager.create_new_project.return_value = True
                controller.weight_manager = MagicMock()
                controller.active_weight_name = "test_weight"
                
                # Mock setup_detector to succeed
                with patch.object(controller, 'setup_detector', return_value=True):
                    # Try to create project with multiple animals per aquarium  
                    project_kwargs = {
                        "project_path": "/tmp/test_project",
                        "project_type": "pre-recorded",
                        "animals_per_aquarium": 3,  # Multiple animals - should be allowed in seg mode
                        "num_aquariums": 1,
                        "aquarium_width_cm": 10.0,
                        "aquarium_height_cm": 10.0,
                        "video_files": ["/tmp/test.mp4"]
                    }
                    
                    # This should succeed without error
                    controller.create_project_workflow(**project_kwargs)
                    
                    # Verify no error was shown
                    mock_view.show_error.assert_not_called()
                    
                    # Project manager should have been called
                    controller.project_manager.create_new_project.assert_called_once()


def test_single_video_detection_mode_enforcement():
    """Test enforcement in single video workflow."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Mock settings to use detection mode for animals
        with patch('zebtrack.settings.settings') as mock_settings:
            mock_settings.model_selection.animal_method = "det"
            mock_settings.camera.desired_width = 640  
            mock_settings.camera.desired_height = 480
            
            # Also patch settings import in the controller module
            with patch('zebtrack.core.controller.settings', mock_settings):
                from zebtrack.core.controller import AppController
                
                # Create controller with mocked view and components
                mock_view = MagicMock()
                controller = AppController(mock_view)
                
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
                mock_view.show_error.assert_called_once()
                error_title, error_msg = mock_view.show_error.call_args[0]
                assert "Configuração Inválida" in error_title
                assert "modo de detecção (det)" in error_msg
                
                # Zone setup should not have been called
                mock_view.setup_zone_definition_for_single_video.assert_not_called()