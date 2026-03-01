"""
Unit tests for MainViewModel - Commands and Project Management.

Phase: Sprint 1.2 - Test coverage for critical MainViewModel commands
Tests project lifecycle (create, open, close), workflow orchestration,
and state synchronization.

Phase 3: Updated fixtures to use MainViewModelDependencies.
"""

from unittest.mock import Mock

import pytest

from zebtrack.core.application_bootstrapper import BootstrapResult
from zebtrack.core.dependency_container import MainViewModelDependencies
from zebtrack.core.main_view_model import MainViewModel


@pytest.fixture
def mock_root():
    """Create mock Tkinter root."""
    root = Mock()
    root.after = Mock()
    root.quit = Mock()
    return root


@pytest.fixture
def mock_dependencies(mock_root):
    """Create all mocked dependencies for MainViewModel (Phase 3)."""
    # Create properly structured settings mock
    settings = Mock()
    settings.recorder = Mock()
    settings.recorder.flush_interval_seconds = 30.0
    settings.recorder.buffer_size_frames = 300
    settings.recorder.flush_row_threshold = 500
    settings.video_processing = Mock()
    settings.video_processing.fps = 30.0
    settings.performance = Mock()
    settings.performance.parquet_compression = "snappy"
    settings.ui_features = Mock()
    settings.ui_features.enable_event_queue = False

    # Create weight manager with proper model_cache_dir attribute
    weight_mgr = Mock()
    weight_mgr.model_cache_dir = "openvino_model_cache"
    weight_mgr.get_all_weight_names = Mock(return_value=["yolo11n.pt", "yolo11m.pt"])
    weight_mgr.get_default_weight = Mock(return_value=("yolo11n.pt", None))
    weight_mgr._classify_weight_type = Mock(return_value="yolo")
    weight_mgr.delete_weight = Mock()
    # Mock get_weight_details to return None for openvino_path to skip conversion check
    weight_mgr.get_weight_details = Mock(return_value={"openvino_path": None})

    # Create model_service with proper delegation methods
    model_svc = Mock()
    model_svc.get_all_weight_names = Mock(return_value=["yolo11n.pt", "yolo11m.pt"])

    # Create project_workflow_service with proper return values
    project_workflow = Mock()
    project_workflow.open_project = Mock(
        return_value={
            "success": True,
            "error_message": None,
            "project_info": {
                "name": "Test Project",
                "videos_count": 0,
                "zone_status": "No zones defined",
                "roi_count": 0,
                "has_arena": False,
                "active_weight": "yolo11n.pt",
                "use_openvino": False,
            },
            "zone_data": None,
            "resolved_weight": "yolo11n.pt",
            "resolved_openvino": False,
        }
    )

    # Create detector_service with proper return value for initialize_detector
    detector_svc = Mock()
    detector_svc.initialize_detector = Mock(return_value=(True, None))

    # Phase 3: Create super coordinator mocks
    project_lifecycle_coord = Mock()

    hardware_coord = Mock()
    hardware_coord.set_recording_callbacks = Mock()
    hardware_coord.arduino = None
    hardware_coord.arduino_manager = Mock()

    processing_coord = Mock()

    session_coord = Mock()
    session_coord.trigger_recording = Mock()
    session_coord.stop_recording = Mock(return_value=True)

    # Phase 3: Return MainViewModelDependencies object instead of dict
    return MainViewModelDependencies(
        root=mock_root,
        event_bus=Mock(),
        state_manager=Mock(),
        ui_coordinator=Mock(),
        settings_obj=settings,
        project_manager=Mock(),
        project_workflow_service=project_workflow,
        weight_manager=weight_mgr,
        model_service=model_svc,
        detector_service=detector_svc,
        video_processing_service=Mock(),
        analysis_service=Mock(),
        recording_service=None,
        live_camera_service=None,
        # Phase 3: Super coordinators (properly mocked)
        project_lifecycle_coordinator=project_lifecycle_coord,
        detector_setup_coordinator=hardware_coord,
        model_diagnostics_coordinator=Mock(),
        processing_coordinator=processing_coord,
        # Phase 4.7: Replaced session_coordinator with 3 focused coordinators
        recording_session_coordinator=Mock(),
        live_camera_session_coordinator=Mock(),
        live_calibration_coordinator=Mock(),
    )


@pytest.fixture
def mock_bootstrap_result():
    """Create a mock BootstrapResult."""
    result = Mock(spec=BootstrapResult)

    # Mocks for legacy coordinators
    result.legacy_coordinators = {
        "detector_coordinator": Mock(),
        # Phase 4.7: Removed recording_coordinator and live_camera_coordinator (dead code)
    }

    # Mocks for orchestrators (Phase 3A/3B/3C/3D: Removed superseded orchestrators)
    # Phase 0.3: video_processing_orchestrator removed (migrated to ProcessingCoordinator)
    result.ui_state_controller = Mock()

    # Mocks for services
    result.project_service = Mock()
    result.analysis_service = Mock()
    result.video_classification_service = Mock()
    result.video_selection_service = Mock()
    result.video_validation_service = Mock()
    result.batch_configuration_service = Mock()
    result.thread_coordinator = Mock()
    result.dialog_coordinator = Mock()
    result.event_dispatcher = Mock()

    # Mocks for hardware/runtime
    result.active_weight_name = "yolo11n.pt"
    result.use_openvino = False
    result.hardware_summary = "CPU"
    result.recommended_backend = "pytorch"
    result.recorder = Mock()
    result.arduino_manager = Mock()

    # Mocks for queues/events
    result.frame_queue = Mock()
    result.video_queue = Mock()
    result.program_exit_event = Mock()
    result.cancel_event = Mock()

    result.orchestrators = {}
    result.project_workflow_adapter = Mock()

    # Phase 6: view is now assigned from BootstrapResult inside _assign_bootstrap_result
    result.view = Mock()

    return result


@pytest.fixture
def main_view_model(mock_dependencies, mock_bootstrap_result):
    """Create MainViewModel with mocked dependencies (Phase 3)."""
    controller = MainViewModel(
        dependencies=mock_dependencies, bootstrap_result=mock_bootstrap_result
    )
    # Mock the view to avoid UI dependencies (although view is decoupled, tests might access it)
    controller.view = Mock()
    # We also need to set controller.ui_state_controller.view if tests use it
    controller.ui_state_controller.view = controller.view

    return controller


class TestMainViewModelInitialization:
    """Test suite for MainViewModel initialization (Phase 3)."""

    def test_init_stores_all_dependencies(self, mock_dependencies, mock_bootstrap_result):
        """Test initialization stores all injected dependencies (Phase 3)."""
        controller = MainViewModel(
            dependencies=mock_dependencies, bootstrap_result=mock_bootstrap_result
        )

        assert controller.root == mock_dependencies.root
        assert controller.ui_event_bus == mock_bootstrap_result.event_dispatcher.event_bus
        assert controller.state_manager == mock_dependencies.state_manager
        assert controller.project_manager == mock_dependencies.project_manager
        assert controller.settings == mock_dependencies.settings_obj

    def test_detector_initialized_property_false_initially(self, main_view_model):
        """Test detector_initialized returns False when detector is None."""
        detector_state = Mock()
        detector_state.detector_initialized = False
        main_view_model.state_manager.get_detector_state.return_value = detector_state
        assert main_view_model.detector_initialized is False

    def test_detector_initialized_property_true_when_set(self, main_view_model):
        """Test detector_initialized returns True when detector exists."""
        detector_state = Mock()
        detector_state.detector_initialized = True
        main_view_model.state_manager.get_detector_state.return_value = detector_state
        assert main_view_model.detector_initialized is True


class TestCreateProjectWorkflow:
    """Test suite for create_project_workflow command."""

    def test_create_project_calls_workflow_service(self, main_view_model):
        """Test create_project_workflow delegates to ProjectViewModel (Phase 3)."""
        wizard_data = {
            "project_name": "Test Project",
            "project_path": "/fake/path",
            "project_type": "live",
        }

        # Mock project_vm create method (MainViewModel.create_project_workflow
        # delegates to project_vm)
        main_view_model.project_vm.create_project_workflow = Mock(
            return_value={"success": True, "animal_method": "det", "wizard_metadata": {}}
        )

        main_view_model.create_project_workflow(**wizard_data)

        # Should call workflow service through project_vm
        main_view_model.project_vm.create_project_workflow.assert_called_once_with(**wizard_data)
