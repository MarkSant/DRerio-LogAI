import pytest
from unittest.mock import MagicMock, Mock, patch
import sys

# Mock tkinter to avoid GUI requirement
sys.modules['tkinter'] = MagicMock()
sys.modules['tkinter.ttk'] = MagicMock()
sys.modules['tkinter.messagebox'] = MagicMock()
sys.modules['tkinter.scrolledtext'] = MagicMock()
sys.modules['tkinter.font'] = MagicMock()
sys.modules['tkinter.simpledialog'] = MagicMock()
sys.modules['tkinter.filedialog'] = MagicMock()
sys.modules['ttkbootstrap'] = MagicMock()
sys.modules['cv2'] = MagicMock()

from zebtrack.core.application_bootstrapper import ApplicationBootstrapper
from zebtrack.core.dependency_container import MainViewModelDependencies

class TestApplicationBootstrapper:
    
    @pytest.fixture
    def dependencies(self):
        deps = MagicMock(spec=MainViewModelDependencies)
        deps.root = MagicMock()
        deps.settings_obj = MagicMock()
        deps.event_bus = MagicMock()
        deps.state_manager = MagicMock()
        deps.project_manager = MagicMock()
        deps.weight_manager = MagicMock()
        deps.model_service = MagicMock()
        deps.detector_service = MagicMock()
        deps.video_processing_service = MagicMock()
        deps.analysis_service = MagicMock()
        deps.project_workflow_service = MagicMock()
        deps.ui_coordinator = MagicMock()
        
        # Coordinators
        deps.processing_coordinator = MagicMock()
        deps.hardware_coordinator = MagicMock()
        deps.session_coordinator = MagicMock()
        deps.project_lifecycle_coordinator = MagicMock()
        
        return deps

    def test_init(self, dependencies):
        bootstrapper = ApplicationBootstrapper(dependencies)
        assert bootstrapper.deps == dependencies

    @patch('zebtrack.core.application_bootstrapper.ApplicationGUI')
    @patch('zebtrack.core.application_bootstrapper.Recorder')
    @patch('zebtrack.core.application_bootstrapper.get_hardware_summary')
    @patch('zebtrack.core.application_bootstrapper.recommend_backend')
    def test_initialize_structure(self, mock_backend, mock_hw, mock_recorder, mock_gui, dependencies):
        # Setup mocks
        mock_hw.return_value = {"cuda_available": False, "openvino_available": False, "has_intel_gpu": False}
        mock_backend.return_value = "pytorch"
        
        # Mock weight manager response
        dependencies.weight_manager.get_default_weight.return_value = ("yolov8n.pt", {})
        
        bootstrapper = ApplicationBootstrapper(dependencies)
        
        # Mock controller proxy
        controller_proxy = MagicMock()
        
        # Run initialize
        result = bootstrapper.initialize(controller_proxy)
        
        # Verify result
        assert result is not None
        assert result.view is not None
        assert result.recorder is not None
        assert result.event_dispatcher is not None
        
        # Verify proxy was populated
        assert controller_proxy.state_manager == dependencies.state_manager
        assert controller_proxy.ui_coordinator == dependencies.ui_coordinator
        assert controller_proxy.root == dependencies.root
