from unittest.mock import MagicMock, patch

import pytest

from zebtrack.core.application_bootstrapper import ApplicationBootstrapper
from zebtrack.core.dependency_container import LazyRef, MainViewModelDependencies


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
        deps.detector_setup_coordinator = MagicMock()
        deps.model_diagnostics_coordinator = MagicMock()
        # Phase 4.7: Replaced session_coordinator with 3 focused coordinators
        deps.recording_session_coordinator = MagicMock()
        deps.live_camera_session_coordinator = MagicMock()
        deps.live_calibration_coordinator = MagicMock()
        deps.project_lifecycle_coordinator = MagicMock()

        return deps

    def test_init(self, dependencies):
        bootstrapper = ApplicationBootstrapper(dependencies)
        assert bootstrapper.deps == dependencies

    @patch("zebtrack.core.application_bootstrapper.ApplicationGUI")
    @patch("zebtrack.core.application_bootstrapper.Recorder")
    @patch("zebtrack.core.application_bootstrapper.get_hardware_summary")
    @patch("zebtrack.core.application_bootstrapper.recommend_backend")
    def test_initialize_structure(
        self, mock_backend, mock_hw, mock_recorder, mock_gui, dependencies
    ):
        # Setup mocks
        mock_hw.return_value = {
            "cuda_available": False,
            "openvino_available": False,
            "has_intel_gpu": False,
        }
        mock_backend.return_value = "pytorch"

        # Mock weight manager response
        dependencies.weight_manager.get_default_weight.return_value = ("yolov8n.pt", {})

        bootstrapper = ApplicationBootstrapper(dependencies)

        # Phase 6: Use LazyRef instead of bare MagicMock for controller
        controller_ref: LazyRef[MagicMock] = LazyRef("MainViewModel")

        # Run initialize
        result = bootstrapper.initialize(controller_ref)

        # Verify result
        assert result is not None
        assert result.view is not None
        assert result.recorder is not None
        assert result.event_dispatcher is not None

        # Phase 6: Proxy is NOT populated with attributes anymore — MainViewModel.__init__
        # handles all attribute assignment via _extract_dependencies + _assign_bootstrap_result.
        # Verify LazyRef is still unresolved (set() called only from __main__.py after init)
        assert controller_ref.is_resolved is False
