"""
Tests for PROJECT_MANAGER_REPLACED event.

Validates that services are properly notified when ProjectManager is replaced
during project close operations.
"""

import unittest
from unittest.mock import Mock, patch

from zebtrack.core.main_view_model import MainViewModel
from zebtrack.core.viewmodels.main_view_model_runtime import MainViewModelRuntime


class TestProjectManagerReplacedEvent(unittest.TestCase):
    """Test PROJECT_MANAGER_REPLACED event handling."""

    def test_handler_updates_services_with_project_manager_attribute(self):
        """Test that _handle_project_manager_replaced updates services."""
        # Create minimal controller with mocked __init__
        with patch.object(MainViewModel, "__init__", return_value=None):
            controller = MainViewModel(None, None)  # type: ignore

            # Create new project manager
            new_manager = Mock()

            # Create mock services that have project_manager attribute
            # (no _on_project_manager_replaced)
            mock_service1 = Mock(spec=["project_manager"])  # Only project_manager
            mock_service1.project_manager = Mock()
            mock_service2 = Mock(spec=["project_manager"])  # Only project_manager
            mock_service2.project_manager = Mock()

            # Set all attributes that the handler accesses
            controller.project_workflow_service = mock_service1  # type: ignore
            controller.detector_service = mock_service2  # type: ignore
            controller.video_processing_service = None  # type: ignore
            controller.detector_setup_coordinator = None  # type: ignore
            controller.processing_coordinator = None  # type: ignore
            controller.analysis_orchestrator = None  # type: ignore
            controller.calibration_orchestrator = None  # type: ignore
            controller.processing_config_orchestrator = None  # type: ignore
            # Create mock coordinators to avoid property setter issues
            controller.recording_session_coordinator = Mock()  # type: ignore
            controller.live_camera_session_coordinator = Mock()  # type: ignore
            controller.recording_service = None  # type: ignore

            runtime = MainViewModelRuntime(controller)
            runtime.handle_project_manager_replaced({"new_manager": new_manager})

            # Verify services were updated
            assert mock_service1.project_manager == new_manager
            assert mock_service2.project_manager == new_manager

    def test_handler_skips_services_without_project_manager(self):
        """Test that services without project_manager are skipped gracefully."""
        with patch.object(MainViewModel, "__init__", return_value=None):
            controller = MainViewModel(None, None)  # type: ignore

            new_manager = Mock()

            # Create service without project_manager attribute
            mock_service = Mock(spec=[])  # Empty spec - no attributes
            controller.project_workflow_service = mock_service  # type: ignore
            controller.detector_service = None  # type: ignore
            controller.video_processing_service = None  # type: ignore
            controller.detector_setup_coordinator = None  # type: ignore
            controller.processing_coordinator = None  # type: ignore
            controller.analysis_orchestrator = None  # type: ignore
            controller.calibration_orchestrator = None  # type: ignore
            controller.processing_config_orchestrator = None  # type: ignore
            controller.recording_session_coordinator = Mock()  # type: ignore
            controller.live_camera_session_coordinator = Mock()  # type: ignore
            controller.recording_service = None  # type: ignore

            runtime = MainViewModelRuntime(controller)
            runtime.handle_project_manager_replaced({"new_manager": new_manager})

    def test_handler_handles_none_new_manager(self):
        """Test that handler returns early if new_manager is None."""
        with patch.object(MainViewModel, "__init__", return_value=None):
            controller = MainViewModel(None, None)  # type: ignore

            mock_service = Mock()
            mock_service.project_manager = Mock()
            controller.project_workflow_service = mock_service  # type: ignore
            controller.detector_service = None  # type: ignore
            controller.video_processing_service = None  # type: ignore
            controller.detector_setup_coordinator = None  # type: ignore
            controller.processing_coordinator = None  # type: ignore
            controller.analysis_orchestrator = None  # type: ignore
            controller.calibration_orchestrator = None  # type: ignore
            controller.processing_config_orchestrator = None  # type: ignore
            controller.recording_session_coordinator = Mock()  # type: ignore
            controller.live_camera_session_coordinator = Mock()  # type: ignore
            controller.recording_service = None  # type: ignore

            old_manager = mock_service.project_manager

            runtime = MainViewModelRuntime(controller)
            runtime.handle_project_manager_replaced({"new_manager": None})

            # Service should not be updated
            assert mock_service.project_manager == old_manager

    def test_handler_handles_empty_data(self):
        """Test that handler handles empty event data gracefully."""
        with patch.object(MainViewModel, "__init__", return_value=None):
            controller = MainViewModel(None, None)  # type: ignore

            mock_service = Mock()
            mock_service.project_manager = Mock()
            controller.project_workflow_service = mock_service  # type: ignore
            controller.detector_service = None  # type: ignore
            controller.video_processing_service = None  # type: ignore
            controller.detector_setup_coordinator = None  # type: ignore
            controller.processing_coordinator = None  # type: ignore
            controller.analysis_orchestrator = None  # type: ignore
            controller.calibration_orchestrator = None  # type: ignore
            controller.processing_config_orchestrator = None  # type: ignore
            controller.recording_session_coordinator = Mock()  # type: ignore
            controller.live_camera_session_coordinator = Mock()  # type: ignore
            controller.recording_service = None  # type: ignore

            old_manager = mock_service.project_manager

            runtime = MainViewModelRuntime(controller)
            runtime.handle_project_manager_replaced({})

            # Service should not be updated
            assert mock_service.project_manager == old_manager

    def test_handler_updates_main_view_model_project_manager(self):
        """Regression (2026-06-11): ``controller.project_manager`` must be
        updated when the manager is replaced. Antes o atributo do proprio
        MainViewModel ficava apontando para a instancia inicial e
        ``load_project_view`` lia ``pm.get_project_name()`` no manager
        antigo — a barra de titulo mantinha o nome do projeto anterior
        apos um close/reopen.
        """
        with patch.object(MainViewModel, "__init__", return_value=None):
            controller = MainViewModel(None, None)  # type: ignore

            old_manager = Mock()
            old_manager.get_project_name = Mock(return_value="Live_T4")
            new_manager = Mock()
            new_manager.get_project_name = Mock(return_value="Live_T9")

            controller.project_manager = old_manager  # type: ignore
            controller.project_workflow_service = None  # type: ignore
            controller.detector_service = None  # type: ignore
            controller.video_processing_service = None  # type: ignore
            controller.recording_service = None  # type: ignore
            controller.processing_coordinator = None  # type: ignore

            runtime = MainViewModelRuntime(controller)
            runtime.handle_project_manager_replaced({"new_manager": new_manager})

            assert controller.project_manager is new_manager
            assert controller.project_manager.get_project_name() == "Live_T9"

    def test_handler_updates_sub_view_models_project_manager(self):
        """Sub-view-models (``project_vm`` / ``analysis_vm``) also hold
        ``self.project_manager`` from their constructor — without updating
        here they keep using the stale manager after close/reopen.
        """
        with patch.object(MainViewModel, "__init__", return_value=None):
            controller = MainViewModel(None, None)  # type: ignore

            new_manager = Mock()

            project_vm = Mock()
            project_vm.project_manager = Mock()
            analysis_vm = Mock()
            analysis_vm.project_manager = Mock()

            controller.project_vm = project_vm  # type: ignore
            controller.analysis_vm = analysis_vm  # type: ignore
            controller.project_workflow_service = None  # type: ignore
            controller.detector_service = None  # type: ignore
            controller.video_processing_service = None  # type: ignore
            controller.recording_service = None  # type: ignore
            controller.processing_coordinator = None  # type: ignore

            runtime = MainViewModelRuntime(controller)
            runtime.handle_project_manager_replaced({"new_manager": new_manager})

            assert project_vm.project_manager is new_manager
            assert analysis_vm.project_manager is new_manager


if __name__ == "__main__":
    unittest.main()
