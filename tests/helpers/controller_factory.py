"""
Test helper factory for creating MainViewModel instances with mocked dependencies.

This factory simplifies test setup by providing pre-configured mocks for all
MainViewModel dependencies required by the DI pattern.
"""

import threading
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

    # ByteTrack settings (real values, not MagicMock)
    mock_settings.bytetrack.track_threshold = 0.25
    mock_settings.bytetrack.match_threshold = 0.80
    mock_settings.bytetrack.track_buffer = 30
    mock_settings.bytetrack.max_center_distance = 100
    mock_settings.bytetrack.iou_threshold = 0.3

    # Tracking settings
    mock_settings.tracking.use_bytetrack = True
    mock_settings.tracking.use_single_subject_tracker = False

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
    from unittest.mock import MagicMock

    from zebtrack.core.application_bootstrapper import BootstrapResult
    from zebtrack.core.dependency_container import MainViewModelDependencies
    from zebtrack.core.main_view_model import MainViewModel
    from zebtrack.core.project.project_workflow_service import ProjectWorkflowService

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
        "root": root,
        "test_sync_event": overrides.get("test_sync_event", None),
        # Add other dependencies required by MainViewModelDependencies
        "project_lifecycle_coordinator": overrides.get(
            "project_lifecycle_coordinator", MagicMock()
        ),
        "detector_setup_coordinator": overrides.get("detector_setup_coordinator", MagicMock()),
        "model_diagnostics_coordinator": overrides.get(
            "model_diagnostics_coordinator", MagicMock()
        ),
        "processing_coordinator": overrides.get("processing_coordinator", MagicMock()),
        # Phase 4.7: Replaced session_coordinator with 3 focused coordinators
        "recording_session_coordinator": overrides.get(
            "recording_session_coordinator", MagicMock()
        ),
        "live_camera_session_coordinator": overrides.get(
            "live_camera_session_coordinator", MagicMock()
        ),
        "live_calibration_coordinator": overrides.get("live_calibration_coordinator", MagicMock()),
        # Phase 4.7: Removed recording_coordinator (dead legacy code)
        "live_camera_service": overrides.get("live_camera_service", MagicMock()),
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

    # Create Dependencies Container
    dependencies = MainViewModelDependencies(**defaults)

    # Phase 3E: ProjectOrchestrator was removed - logic now in ProjectLifecycleCoordinator
    # Support use_real_project_lifecycle_coordinator for tests that need real workflow logic
    use_real_project_lifecycle = overrides.get(
        "use_real_project_orchestrator", False
    ) or overrides.get("use_real_project_lifecycle_coordinator", False)

    if use_real_project_lifecycle:
        # Create real ProjectWorkflowAdapter and ProjectLifecycleCoordinator
        from zebtrack.coordinators.project_lifecycle_coordinator import ProjectLifecycleCoordinator
        from zebtrack.ui.project_workflow_adapter import ProjectWorkflowAdapter

        project_workflow_adapter = ProjectWorkflowAdapter(
            project_workflow_service=project_workflow_service,
            project_manager=project_manager,
            detector_service=defaults["detector_service"],
            state_manager=state_manager,
            ui_event_bus=defaults["event_bus"],
        )

        project_lifecycle_coordinator = ProjectLifecycleCoordinator(
            state_manager=state_manager,
            project_manager=project_manager,
            project_workflow_service=project_workflow_service,
            project_workflow_adapter=project_workflow_adapter,
            settings_obj=settings_obj,
            event_bus=defaults["event_bus"],
            detector_service=defaults["detector_service"],  # Phase 3E: For default callbacks
        )

        # Update dependencies with real coordinator
        defaults["project_lifecycle_coordinator"] = project_lifecycle_coordinator
        dependencies = MainViewModelDependencies(**defaults)
    else:
        project_workflow_adapter = overrides.get("project_workflow_adapter", MagicMock())

    # Configure event dispatcher with event bus
    event_bus = overrides.get("event_bus", MagicMock())
    event_dispatcher = overrides.get("event_dispatcher", MagicMock())
    event_dispatcher.event_bus = event_bus

    # Ensure we always use a real cancel_event unless explicitly overridden
    cancel_event = overrides.get("cancel_event") or threading.Event()

    # Create BootstrapResult Mock
    bootstrap_result = BootstrapResult(
        project_service=overrides.get("project_service", MagicMock()),
        analysis_service=overrides.get("analysis_service", MagicMock()),
        video_classification_service=overrides.get("video_classification_service", MagicMock()),
        video_selection_service=overrides.get("video_selection_service", MagicMock()),
        video_validation_service=overrides.get("video_validation_service", MagicMock()),
        batch_configuration_service=overrides.get("batch_configuration_service", MagicMock()),
        dialog_coordinator=overrides.get("dialog_coordinator", MagicMock()),
        event_dispatcher=event_dispatcher,
        active_weight_name="best_seg.pt",
        use_openvino=False,
        hardware_summary={},
        recommended_backend="CPU",
        recorder=overrides.get("recorder", MagicMock()),
        arduino_manager=overrides.get("arduino_manager", MagicMock()),
        frame_queue=overrides.get("frame_queue", MagicMock()),
        video_queue=overrides.get("video_queue", MagicMock()),
        program_exit_event=overrides.get("program_exit_event", MagicMock()),
        # Use a real threading.Event so thread lifecycle tests behave correctly
        cancel_event=cancel_event,
        view=MagicMock(),  # Added missing view argument
        ui_state_controller=overrides.get("ui_state_controller", MagicMock()),
        # Phase 3A/3B/3C/3D/3E: Removed unused orchestrators (superseded by Super Coordinators)
        legacy_coordinators={
            "detector_coordinator": overrides.get(
                "detector_setup_coordinator",
                overrides.get("detector_coordinator", MagicMock()),
            ),
            # Phase 4.7: Removed recording_coordinator and live_camera_coordinator (dead code)
        },
        project_workflow_adapter=project_workflow_adapter,
    )

    controller = MainViewModel(dependencies, bootstrap_result)
    controller.view = MagicMock()  # Manually assign mock view as it's no longer in init

    return controller
