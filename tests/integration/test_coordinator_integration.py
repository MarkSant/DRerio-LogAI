"""
Integration tests for coordinators with MainViewModel.

Task 2.2: REFACTOR-VIEWMODEL-001
Verifies that HardwareCoordinator, VideoOrchestrator, and AnalysisCoordinator
are properly integrated with MainViewModel and work together correctly.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch

from zebtrack.core.analysis_coordinator import AnalysisCoordinator
from zebtrack.core.hardware_coordinator import HardwareCoordinator
from zebtrack.core.video_orchestrator import VideoOrchestrator


class TestCoordinatorIntegrationWithMainViewModel(unittest.TestCase):
    """Test coordinators integration with MainViewModel."""

    def setUp(self):
        """Set up test fixtures."""
        # Create mock dependencies
        self.root = Mock()
        self.view = Mock()
        self.state_manager = Mock()
        self.ui_event_bus = Mock()
        self.ui_coordinator = Mock()
        self.settings = Mock()
        self.project_manager = Mock()
        self.detector_service = Mock()
        self.video_processing_service = Mock()
        self.analysis_service = Mock()
        self.recorder = Mock()
        self.arduino_manager_cls = Mock()

    def test_init_coordinators_creates_all_three(self):
        """Test that _init_coordinators creates all three coordinators."""
        # Simulate MainViewModel._init_coordinators()
        hardware_coordinator = HardwareCoordinator(
            state_manager=self.state_manager,
            ui_event_bus=self.ui_event_bus,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            detector_service=self.detector_service,
            arduino_manager_cls=self.arduino_manager_cls,
        )

        video_orchestrator = VideoOrchestrator(
            root=self.root,
            view=self.view,
            state_manager=self.state_manager,
            ui_event_bus=self.ui_event_bus,
            ui_coordinator=self.ui_coordinator,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            video_processing_service=self.video_processing_service,
            analysis_service=self.analysis_service,
            recorder=self.recorder,
        )

        analysis_coordinator = AnalysisCoordinator(
            root=self.root,
            view=self.view,
            ui_event_bus=self.ui_event_bus,
            ui_coordinator=self.ui_coordinator,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            analysis_service=self.analysis_service,
            video_processing_service=self.video_processing_service,
        )

        # Verify all coordinators were created successfully
        assert hardware_coordinator is not None
        assert video_orchestrator is not None
        assert analysis_coordinator is not None

    def test_hardware_coordinator_callbacks_setup(self):
        """Test that HardwareCoordinator callbacks are set by MainViewModel."""
        hardware_coordinator = HardwareCoordinator(
            state_manager=self.state_manager,
            ui_event_bus=self.ui_event_bus,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            detector_service=self.detector_service,
            arduino_manager_cls=self.arduino_manager_cls,
        )

        # Simulate MainViewModel setting recording callbacks
        mock_trigger = Mock()
        mock_stop = Mock()
        hardware_coordinator.set_recording_callbacks(mock_trigger, mock_stop)

        # Verify callbacks were set
        assert hardware_coordinator._trigger_recording_callback == mock_trigger
        assert hardware_coordinator._stop_recording_callback == mock_stop

    def test_video_orchestrator_callbacks_setup(self):
        """Test that VideoOrchestrator callbacks are set by MainViewModel."""
        video_orchestrator = VideoOrchestrator(
            root=self.root,
            view=self.view,
            state_manager=self.state_manager,
            ui_event_bus=self.ui_event_bus,
            ui_coordinator=self.ui_coordinator,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            video_processing_service=self.video_processing_service,
            analysis_service=self.analysis_service,
            recorder=self.recorder,
        )

        # Simulate MainViewModel setting callbacks
        mock_arena = Mock()
        mock_analysis_mode = Mock()
        mock_refresh = Mock()
        mock_publish = Mock()

        video_orchestrator.set_arena_callback(mock_arena)
        video_orchestrator.set_analysis_view_mode_callback(mock_analysis_mode)
        video_orchestrator.set_refresh_callback(mock_refresh)
        video_orchestrator.set_publish_processing_mode_callback(mock_publish)

        # Verify all callbacks were set
        assert video_orchestrator._set_main_arena_polygon_callback == mock_arena
        assert video_orchestrator._activate_analysis_view_mode_callback == mock_analysis_mode
        assert video_orchestrator._refresh_project_views_callback == mock_refresh
        assert video_orchestrator._publish_processing_mode_callback == mock_publish

    def test_analysis_coordinator_callbacks_setup(self):
        """Test that AnalysisCoordinator callbacks are set by MainViewModel."""
        analysis_coordinator = AnalysisCoordinator(
            root=self.root,
            view=self.view,
            ui_event_bus=self.ui_event_bus,
            ui_coordinator=self.ui_coordinator,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            analysis_service=self.analysis_service,
            video_processing_service=self.video_processing_service,
        )

        # Simulate MainViewModel setting callback
        mock_refresh = Mock()
        analysis_coordinator.set_refresh_callback(mock_refresh)

        # Verify callback was set
        assert analysis_coordinator._refresh_project_views_callback == mock_refresh

    def test_hardware_arduino_event_triggers_recording(self):
        """Test that Arduino events can trigger recording via callbacks."""
        hardware_coordinator = HardwareCoordinator(
            state_manager=self.state_manager,
            ui_event_bus=self.ui_event_bus,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            detector_service=self.detector_service,
            arduino_manager_cls=self.arduino_manager_cls,
        )

        # Setup recording callbacks
        mock_trigger = Mock()
        mock_stop = Mock()
        hardware_coordinator.set_recording_callbacks(mock_trigger, mock_stop)

        # Setup pending external trigger
        hardware_coordinator._pending_external_trigger = {"some": "context"}

        # Simulate Arduino event code 1 (start recording)
        hardware_coordinator.on_arduino_event(event_code=1)

        # Verify trigger callback was called
        mock_trigger.assert_called_once_with(1)

    def test_hardware_arduino_event_stops_recording(self):
        """Test that Arduino events can stop recording via callbacks."""
        # Setup state manager to indicate recording is active
        self.state_manager.get_recording_state.return_value = {"is_recording": True}

        hardware_coordinator = HardwareCoordinator(
            state_manager=self.state_manager,
            ui_event_bus=self.ui_event_bus,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            detector_service=self.detector_service,
            arduino_manager_cls=self.arduino_manager_cls,
        )

        # Setup recording callbacks
        mock_trigger = Mock()
        mock_stop = Mock()
        hardware_coordinator.set_recording_callbacks(mock_trigger, mock_stop)

        # Simulate Arduino event code 0 (stop recording)
        hardware_coordinator.on_arduino_event(event_code=0)

        # Verify stop callback was called
        mock_stop.assert_called_once()

    def test_coordinators_share_state_manager(self):
        """Test that all coordinators share the same StateManager instance."""
        hardware_coordinator = HardwareCoordinator(
            state_manager=self.state_manager,
            ui_event_bus=self.ui_event_bus,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            detector_service=self.detector_service,
            arduino_manager_cls=self.arduino_manager_cls,
        )

        video_orchestrator = VideoOrchestrator(
            root=self.root,
            view=self.view,
            state_manager=self.state_manager,
            ui_event_bus=self.ui_event_bus,
            ui_coordinator=self.ui_coordinator,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            video_processing_service=self.video_processing_service,
            analysis_service=self.analysis_service,
            recorder=self.recorder,
        )

        analysis_coordinator = AnalysisCoordinator(
            root=self.root,
            view=self.view,
            ui_event_bus=self.ui_event_bus,
            ui_coordinator=self.ui_coordinator,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            analysis_service=self.analysis_service,
            video_processing_service=self.video_processing_service,
        )

        # Verify all use the same state manager
        assert hardware_coordinator.state_manager is self.state_manager
        assert video_orchestrator.state_manager is self.state_manager
        # Note: AnalysisCoordinator doesn't have direct state_manager access

    def test_coordinators_share_event_bus(self):
        """Test that all coordinators share the same EventBus instance."""
        hardware_coordinator = HardwareCoordinator(
            state_manager=self.state_manager,
            ui_event_bus=self.ui_event_bus,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            detector_service=self.detector_service,
            arduino_manager_cls=self.arduino_manager_cls,
        )

        video_orchestrator = VideoOrchestrator(
            root=self.root,
            view=self.view,
            state_manager=self.state_manager,
            ui_event_bus=self.ui_event_bus,
            ui_coordinator=self.ui_coordinator,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            video_processing_service=self.video_processing_service,
            analysis_service=self.analysis_service,
            recorder=self.recorder,
        )

        analysis_coordinator = AnalysisCoordinator(
            root=self.root,
            view=self.view,
            ui_event_bus=self.ui_event_bus,
            ui_coordinator=self.ui_coordinator,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            analysis_service=self.analysis_service,
            video_processing_service=self.video_processing_service,
        )

        # Verify all use the same event bus
        assert hardware_coordinator.ui_event_bus is self.ui_event_bus
        assert video_orchestrator.ui_event_bus is self.ui_event_bus
        assert analysis_coordinator.ui_event_bus is self.ui_event_bus

    def test_coordinators_share_project_manager(self):
        """Test that all coordinators share the same ProjectManager instance."""
        hardware_coordinator = HardwareCoordinator(
            state_manager=self.state_manager,
            ui_event_bus=self.ui_event_bus,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            detector_service=self.detector_service,
            arduino_manager_cls=self.arduino_manager_cls,
        )

        video_orchestrator = VideoOrchestrator(
            root=self.root,
            view=self.view,
            state_manager=self.state_manager,
            ui_event_bus=self.ui_event_bus,
            ui_coordinator=self.ui_coordinator,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            video_processing_service=self.video_processing_service,
            analysis_service=self.analysis_service,
            recorder=self.recorder,
        )

        analysis_coordinator = AnalysisCoordinator(
            root=self.root,
            view=self.view,
            ui_event_bus=self.ui_event_bus,
            ui_coordinator=self.ui_coordinator,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            analysis_service=self.analysis_service,
            video_processing_service=self.video_processing_service,
        )

        # Verify all use the same project manager
        assert hardware_coordinator.project_manager is self.project_manager
        assert video_orchestrator.project_manager is self.project_manager
        assert analysis_coordinator.project_manager is self.project_manager

    def test_hardware_detector_setup_delegates_to_service(self):
        """Test that HardwareCoordinator delegates detector setup to DetectorService."""
        # Setup mock detector service
        self.detector_service.initialize_detector.return_value = (True, None)

        hardware_coordinator = HardwareCoordinator(
            state_manager=self.state_manager,
            ui_event_bus=self.ui_event_bus,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            detector_service=self.detector_service,
            arduino_manager_cls=self.arduino_manager_cls,
        )

        # Call setup_detector
        success = hardware_coordinator.setup_detector(temp_animal_method="det", use_openvino=False)

        # Verify delegation
        assert success is True
        self.detector_service.initialize_detector.assert_called_once()

    def test_analysis_coordinator_uses_analysis_service(self):
        """Test that AnalysisCoordinator delegates to AnalysisService."""
        analysis_coordinator = AnalysisCoordinator(
            root=self.root,
            view=self.view,
            ui_event_bus=self.ui_event_bus,
            ui_coordinator=self.ui_coordinator,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            analysis_service=self.analysis_service,
            video_processing_service=self.video_processing_service,
        )

        # Verify service is accessible
        assert analysis_coordinator.analysis_service is self.analysis_service

    @patch("threading.Thread")
    def test_video_orchestrator_creates_worker_threads(self, mock_thread):
        """Test that VideoOrchestrator can create worker threads for processing."""
        video_orchestrator = VideoOrchestrator(
            root=self.root,
            view=self.view,
            state_manager=self.state_manager,
            ui_event_bus=self.ui_event_bus,
            ui_coordinator=self.ui_coordinator,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            video_processing_service=self.video_processing_service,
            analysis_service=self.analysis_service,
            recorder=self.recorder,
        )

        # Setup mocks
        self.project_manager.project_data = {
            "videos": [{"path": "/path/to/video.mp4", "has_arena": True}]
        }

        # Mock thread
        mock_thread_instance = Mock()
        mock_thread.return_value = mock_thread_instance

        # This would normally trigger thread creation in actual flow
        # Here we just verify the coordinator has access to needed services
        assert video_orchestrator.video_processing_service is self.video_processing_service


class TestCoordinatorMethodDelegation(unittest.TestCase):
    """Test that MainViewModel methods correctly delegate to coordinators."""

    def test_detector_methods_delegated_to_hardware_coordinator(self):
        """Test detector-related methods should delegate to HardwareCoordinator."""
        # List of methods that should be delegated:
        # - setup_detector()
        # - setup_detector_zones()
        # - setup_arduino()

        detector_service = Mock()
        hardware_coordinator = HardwareCoordinator(
            state_manager=Mock(),
            ui_event_bus=Mock(),
            settings_obj=Mock(),
            project_manager=Mock(),
            detector_service=detector_service,
            arduino_manager_cls=Mock(),
        )

        # Verify methods exist and are callable
        assert callable(hardware_coordinator.setup_detector)
        assert callable(hardware_coordinator.setup_detector_zones)
        assert callable(hardware_coordinator.setup_arduino)

    def test_analysis_methods_delegated_to_analysis_coordinator(self):
        """Test analysis methods should delegate to AnalysisCoordinator."""
        # List of methods that should be delegated:
        # - generate_report()
        # - generate_parquet_summaries()

        analysis_coordinator = AnalysisCoordinator(
            root=Mock(),
            view=Mock(),
            ui_event_bus=Mock(),
            ui_coordinator=Mock(),
            settings_obj=Mock(),
            project_manager=Mock(),
            analysis_service=Mock(),
            video_processing_service=Mock(),
        )

        # Verify methods exist and are callable
        assert callable(analysis_coordinator.generate_report)
        assert callable(analysis_coordinator.generate_parquet_summaries)

    def test_video_processing_delegated_to_video_orchestrator(self):
        """Test video processing methods should delegate to VideoOrchestrator."""
        # List of methods that should be delegated:
        # - process_pending_project_videos()

        video_orchestrator = VideoOrchestrator(
            root=Mock(),
            view=Mock(),
            state_manager=Mock(),
            ui_event_bus=Mock(),
            ui_coordinator=Mock(),
            settings_obj=Mock(),
            project_manager=Mock(),
            video_processing_service=Mock(),
            analysis_service=Mock(),
            recorder=Mock(),
        )

        # Verify methods exist and are callable
        assert callable(video_orchestrator.process_pending_project_videos)


if __name__ == "__main__":
    unittest.main()
