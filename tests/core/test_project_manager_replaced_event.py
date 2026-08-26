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

    def test_lifecycle_and_processing_coordinators_are_reached(self):
        """The two forwarding hops that own the rest of the graph.

        ``CalibrationCoordinator`` sits behind ``ProjectLifecycleCoordinator``
        and answers ``project_loaded = bool(pm.project_path)`` for the AI Model
        Config tab; the four processing sub-coordinators sit behind
        ``VideoProcessingCoordinator``. Neither was in ``services_to_update``,
        so both kept serving the CLOSED project after a close/reopen.
        """
        with patch.object(MainViewModel, "__init__", return_value=None):
            controller = MainViewModel(None, None)  # type: ignore

            new_manager = Mock()

            lifecycle = Mock(spec=["project_manager", "_on_project_manager_replaced"])
            processing = Mock(spec=["project_manager", "_on_project_manager_replaced"])
            batch = Mock(spec=["project_manager"])
            batch.project_manager = Mock()
            dialogs = Mock(spec=["project_manager"])
            dialogs.project_manager = Mock()

            controller.project_lifecycle_coordinator = lifecycle  # type: ignore
            controller.processing_coordinator = processing  # type: ignore
            controller.live_batch_coordinator = batch  # type: ignore
            controller.dialog_coordinator = dialogs  # type: ignore
            controller.project_workflow_service = None  # type: ignore
            controller.detector_service = None  # type: ignore
            controller.video_processing_service = None  # type: ignore
            controller.recording_service = None  # type: ignore

            runtime = MainViewModelRuntime(controller)
            payload = {"new_manager": new_manager}
            runtime.handle_project_manager_replaced(payload)

            # Owners get the hook (so they can forward); leaves get the attribute.
            lifecycle._on_project_manager_replaced.assert_called_once_with(payload)
            processing._on_project_manager_replaced.assert_called_once_with(payload)
            assert batch.project_manager is new_manager
            assert dialogs.project_manager is new_manager


class TestForwardingHops(unittest.TestCase):
    """Each owner must actually re-point the components it constructed."""

    def test_lifecycle_coordinator_forwards_to_calibration_and_overrides(self):
        from zebtrack.coordinators.project_lifecycle_coordinator import (
            ProjectLifecycleCoordinator,
        )

        coord = object.__new__(ProjectLifecycleCoordinator)
        coord.logger = Mock()
        coord.project_manager = Mock()
        coord._calibration_coordinator = Mock(spec=["project_manager"])
        coord._calibration_coordinator.project_manager = Mock()
        coord._model_override_service = Mock(spec=["project_manager"])
        coord._model_override_service.project_manager = Mock()

        new_manager = Mock()
        coord._on_project_manager_replaced({"new_manager": new_manager})

        assert coord.project_manager is new_manager
        assert coord._calibration_coordinator.project_manager is new_manager
        assert coord._model_override_service.project_manager is new_manager

    def test_lifecycle_coordinator_ignores_an_empty_payload(self):
        from zebtrack.coordinators.project_lifecycle_coordinator import (
            ProjectLifecycleCoordinator,
        )

        coord = object.__new__(ProjectLifecycleCoordinator)
        coord.logger = Mock()
        original = Mock()
        coord.project_manager = original
        coord._calibration_coordinator = None
        coord._model_override_service = None

        coord._on_project_manager_replaced({"new_manager": None})

        assert coord.project_manager is original

    def test_processing_coordinator_forwards_to_its_sub_coordinators(self):
        from zebtrack.coordinators.video_processing_coordinator import (
            VideoProcessingCoordinator,
        )

        coord = object.__new__(VideoProcessingCoordinator)
        coord.project_manager = Mock()
        subs = {}
        for attr in (
            "_multi_aquarium_coordinator",
            "_sequential_coordinator",
            "_report_coordinator",
            "_progress_coordinator",
            "ui_coordinator",
            "dialog_coordinator",
        ):
            sub = Mock(spec=["project_manager"])
            sub.project_manager = Mock()
            subs[attr] = sub
            setattr(coord, attr, sub)

        new_manager = Mock()
        coord._on_project_manager_replaced({"new_manager": new_manager})

        assert coord.project_manager is new_manager
        for attr, sub in subs.items():
            assert sub.project_manager is new_manager, attr


if __name__ == "__main__":
    unittest.main()
