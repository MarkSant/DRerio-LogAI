from unittest.mock import MagicMock, Mock

import pytest

from zebtrack.coordinators.hardware_coordinator import HardwareCoordinator
from zebtrack.coordinators.processing_coordinator import ProcessingCoordinator
from zebtrack.coordinators.project_lifecycle_coordinator import ProjectLifecycleCoordinator
from zebtrack.coordinators.session_coordinator import SessionCoordinator
from zebtrack.core.main_view_model import MainViewModel, MainViewModelDependencies


@pytest.fixture
def mock_dependencies():
    deps = Mock(spec=MainViewModelDependencies)

    # Mock core dependencies
    deps.root = MagicMock()
    deps.settings_obj = MagicMock()
    deps.test_sync_event = None

    # Mock services
    deps.state_manager = MagicMock()
    deps.project_manager = MagicMock()
    deps.weight_manager = MagicMock()
    deps.weight_manager.get_default_weight.return_value = ("mock_weight.pt", {})
    deps.weight_manager.get_weight_details.return_value = {"path": "models/mock_weight.pt", "openvino_path": "models/mock_weight_openvino"}
    deps.model_service = MagicMock()
    deps.detector_service = MagicMock()
    deps.video_processing_service = MagicMock()
    deps.project_workflow_service = MagicMock()
    deps.ui_coordinator = MagicMock()
    deps.recording_service = MagicMock()
    deps.analysis_service = MagicMock()
    deps.live_camera_service = MagicMock()
    deps.event_bus = MagicMock()

    # Mock Super Coordinators
    deps.project_lifecycle_coordinator = MagicMock(spec=ProjectLifecycleCoordinator)
    deps.hardware_coordinator = MagicMock(spec=HardwareCoordinator)
    deps.processing_coordinator = MagicMock(spec=ProcessingCoordinator)
    deps.session_coordinator = MagicMock(spec=SessionCoordinator)

    return deps

def test_main_view_model_initialization_with_super_coordinators(mock_dependencies):
    """Test that MainViewModel initializes correctly with injected Super Coordinators."""
    mock_view = MagicMock()
    vm = MainViewModel(mock_dependencies, view=mock_view)

    # Verify that Super Coordinators are assigned
    assert vm.project_lifecycle_coordinator == mock_dependencies.project_lifecycle_coordinator
    assert vm.hardware_coordinator == mock_dependencies.hardware_coordinator
    assert vm.processing_coordinator == mock_dependencies.processing_coordinator
    assert vm.session_coordinator == mock_dependencies.session_coordinator

    # Verify that legacy orchestrators are NOT created (or mapped to Super Coordinators)
    # In our refactor, we mapped them in orchestrators registry, but attributes might not exist directly
    # or might be the new coordinators

    # Verify orchestrators registry mapping
    assert vm.orchestrators.project == mock_dependencies.project_lifecycle_coordinator
    assert vm.orchestrators.video_processing == mock_dependencies.processing_coordinator
    assert vm.orchestrators.recording == mock_dependencies.session_coordinator
    assert vm.orchestrators.model_diagnostics == mock_dependencies.hardware_coordinator

def test_main_view_model_delegation_to_project_lifecycle(mock_dependencies):
    """Test that MainViewModel delegates project lifecycle methods to ProjectLifecycleCoordinator."""
    mock_view = MagicMock()
    vm = MainViewModel(mock_dependencies, view=mock_view)

    # Test close_project delegation
    vm.close_project()
    mock_dependencies.project_lifecycle_coordinator.close_project.assert_called_once()

    # Test create_project_workflow delegation
    vm.create_project_workflow(name="test")
    mock_dependencies.project_lifecycle_coordinator.create_project.assert_called_once()

    # Test open_project_workflow delegation
    vm.open_project_workflow("path/to/project")
    mock_dependencies.project_lifecycle_coordinator.open_project.assert_called_once()

def test_main_view_model_delegation_to_hardware_coordinator(mock_dependencies):
    """Test that MainViewModel delegates hardware methods to HardwareCoordinator."""
    mock_view = MagicMock()
    vm = MainViewModel(mock_dependencies, view=mock_view)

    # Setup mock return value for setup_detector to return (success, error)
    mock_dependencies.hardware_coordinator.setup_detector.return_value = (True, None)

    # Setup mock attributes for arduino sync
    mock_dependencies.hardware_coordinator.arduino = MagicMock()
    mock_dependencies.hardware_coordinator.arduino_manager = MagicMock()

    # Test setup_detector delegation
    vm.setup_detector(temp_animal_method="det")
    mock_dependencies.hardware_coordinator.setup_detector.assert_called_once()

    # Test setup_arduino delegation
    vm.setup_arduino()
    mock_dependencies.hardware_coordinator.setup_arduino.assert_called_once()

    # Test get_current_detector_parameters delegation
    vm.get_current_detector_parameters()
    mock_dependencies.hardware_coordinator.get_detector_parameters.assert_called_once()

def test_main_view_model_delegation_to_session_coordinator(mock_dependencies):
    """Test that MainViewModel delegates session methods to SessionCoordinator."""
    mock_view = MagicMock()
    vm = MainViewModel(mock_dependencies, view=mock_view)

    # Test start_live_camera_analysis delegation
    with vm.start_live_camera_analysis(camera_index=0):
        pass
    mock_dependencies.session_coordinator.start_live_camera_analysis.assert_called_once_with(camera_index=0)

from unittest.mock import patch


def test_main_view_model_delegation_to_processing_coordinator(mock_dependencies):
    """Test that MainViewModel delegates processing methods to ProcessingCoordinator."""
    mock_view = MagicMock()
    vm = MainViewModel(mock_dependencies, view=mock_view)

    # Test generate_parquet_summaries delegation
    video_paths = ["path/to/video1", "path/to/video2"]
    vm.generate_parquet_summaries(video_paths)

    # Check if generate_parquet_summaries was called on processing_coordinator
    # Note: The method converts list[str] to list[dict] internally
    mock_dependencies.processing_coordinator.generate_parquet_summaries.assert_called_once()

    # Test generate_report delegation (delegates to AnalysisService)
    # In Phase 4, MainViewModel uses self.dialog_coordinator.ask_save_filename
    # We need to mock that method on the vm instance or its dependency
    with patch.object(vm.dialog_coordinator, 'ask_save_filename', return_value="report.docx") as mock_ask_save:
        vm.generate_report([{"path": "video1"}], "unified")

        # MainViewModel calls dialog_coordinator.ask_save_filename
        mock_ask_save.assert_called_once()

    # MainViewModel calls analysis_service.generate_report with output path
    mock_dependencies.analysis_service.generate_report.assert_called_once()
    # Check args
    args, kwargs = mock_dependencies.analysis_service.generate_report.call_args
    assert args[0] == [{"path": "video1"}]
    assert args[1] == "unified"
    assert args[2] == "report.docx"
