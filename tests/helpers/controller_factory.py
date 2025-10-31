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
        parts = key.split(".")
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
    from zebtrack.core.project_workflow_service import ProjectWorkflowService

    # Check for overrides first
    settings_obj = overrides.get("settings_obj", create_mock_settings())
    state_manager = overrides.get("state_manager", StateManager())
    project_manager = overrides.get("project_manager", MagicMock())
    model_service = overrides.get("model_service", MagicMock())
    ui_coordinator = overrides.get("ui_coordinator", MagicMock())

    # Create REAL ProjectWorkflowService (not a mock) so it works correctly
    # Use the potentially-overridden settings_obj and other services
    project_workflow_service = overrides.get("project_workflow_service") or ProjectWorkflowService(
        project_manager=project_manager,
        model_service=model_service,
        state_manager=state_manager,
        ui_coordinator=ui_coordinator,
        settings_obj=settings_obj,
    )

    # Default mocks for all dependencies (using potentially-overridden values)
    defaults = {
        "event_bus": overrides.get("event_bus", MagicMock()),
        "state_manager": state_manager,
        "ui_coordinator": ui_coordinator,
        "settings_obj": settings_obj,
        "project_manager": project_manager,
        "project_workflow_service": project_workflow_service,
        "weight_manager": overrides.get("weight_manager", MagicMock()),
        "model_service": model_service,
        "detector_service": overrides.get("detector_service", MagicMock()),
        "video_processing_service": overrides.get("video_processing_service", MagicMock()),
    }

    # Configure common mock behaviors
    if "weight_manager" not in overrides:
        defaults["weight_manager"].get_default_weight.return_value = ("best_seg.pt", "/fake/path")
        defaults["weight_manager"].get_all_weights.return_value = ["best_seg.pt"]

    if "model_service" not in overrides:
        defaults["model_service"].get_default_weight.return_value = ("best_seg.pt", "/fake/path")
        defaults["model_service"].get_all_weights.return_value = ["best_seg.pt"]

    if "detector_service" not in overrides:
        defaults["detector_service"].initialize_detector.return_value = (True, None)
        defaults["detector_service"].set_zones.return_value = None

    if "project_manager" not in overrides:
        defaults["project_manager"].project_path = None
        defaults["project_manager"].project_data = {}
        defaults["project_manager"].create_new_project.return_value = True
        defaults["project_manager"].create_project.return_value = {
            "project_type": "pre-recorded",
            "animals_per_aquarium": 1,
            "num_aquariums": 1,
            "aquarium_width_cm": 10.0,
            "aquarium_height_cm": 10.0,
        }

    # Mock ApplicationGUI to avoid Tkinter initialization issues in tests
    with patch("zebtrack.core.main_view_model.ApplicationGUI") as MockGUI:
        mock_view = MockGUI.return_value

        # Support test_sync_event if provided (for integration tests)
        test_sync_event = overrides.get("test_sync_event", None)
        if test_sync_event is not None:
            controller = MainViewModel(root, test_sync_event=test_sync_event, **defaults)
        else:
            controller = MainViewModel(root, **defaults)

        controller.view = mock_view  # Ensure view is the mock
        return controller
