"""
Test helper factory for creating MainViewModel instances with mocked dependencies.

This factory simplifies test setup by providing pre-configured mocks for all
MainViewModel dependencies required by the DI pattern.
"""

from unittest.mock import MagicMock

from zebtrack.core.state_manager import StateManager


def create_mock_settings(**overrides):
    """Create a mock settings object with common defaults."""
    mock_settings = MagicMock()
    
    # Camera settings
    mock_settings.camera.index = 0
    mock_settings.camera.desired_width = 1280
    mock_settings.camera.desired_height = 720
    mock_settings.camera.max_reconnect_attempts = 3
    mock_settings.camera.reconnect_timeout_seconds = 5.0
    mock_settings.camera.max_frame_lag_ms = 100.0
    
    # Video processing settings
    mock_settings.video_processing.fps = 30
    mock_settings.video_processing.processing_interval = 10
    mock_settings.video_processing.processing_offset = 0
    
    # Model selection settings
    mock_settings.model_selection.animal_method = "seg"
    
    # UI features
    mock_settings.ui_features.enable_event_queue = False
    
    # Apply any overrides
    for key, value in overrides.items():
        parts = key.split('.')
        obj = mock_settings
        for part in parts[:-1]:
            obj = getattr(obj, part)
        setattr(obj, parts[-1], value)
    
    return mock_settings


def create_test_controller(root, **overrides):
    """
    Create MainViewModel with all mocks for testing.
    
    Args:
        root: Mock Tkinter root
        **overrides: Override specific dependencies (e.g., settings_obj=custom_mock)
    
    Returns:
        MainViewModel instance with mocked dependencies
    """
    from unittest.mock import patch
    
    from zebtrack.core.main_view_model import MainViewModel
    
    # Default mocks for all dependencies
    defaults = {
        'event_bus': MagicMock(),
        'state_manager': StateManager(),
        'ui_coordinator': MagicMock(),
        'settings_obj': create_mock_settings(),
        'project_manager': MagicMock(),
        'project_workflow_service': MagicMock(),
        'weight_manager': MagicMock(),
        'model_service': MagicMock(),
        'detector_service': MagicMock(),
        'video_processing_service': MagicMock(),
    }
    
    # Apply overrides
    defaults.update(overrides)
    
    # Configure common mock behaviors
    if 'weight_manager' not in overrides:
        defaults['weight_manager'].get_default_weight.return_value = ("best_seg.pt", "/fake/path")
        defaults['weight_manager'].get_all_weights.return_value = ["best_seg.pt"]
    
    if 'project_manager' not in overrides:
        defaults['project_manager'].project_path = None
        defaults['project_manager'].project_data = {}
        defaults['project_manager'].create_new_project.return_value = True
    
    # Mock ApplicationGUI to avoid Tkinter initialization issues in tests
    with patch("zebtrack.core.main_view_model.ApplicationGUI") as MockGUI:
        mock_view = MockGUI.return_value
        controller = MainViewModel(root, **defaults)
        controller.view = mock_view  # Ensure view is the mock
        return controller
