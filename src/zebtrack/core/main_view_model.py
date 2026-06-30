"""Main application view model orchestrating the ZebTrack-AI application.

Coordinates all core services, manages application state, handles user interactions,
and orchestrates video processing workflows with dependency injection.
"""

from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.core.application_bootstrapper import BootstrapResult
from zebtrack.core.dependency_container import MainViewModelDependencies
from zebtrack.core.detection import Detector
from zebtrack.core.recording.recording_service import RecordingService
from zebtrack.core.state_manager import StateCategory
from zebtrack.core.video.processing_mode import ProcessingMode
from zebtrack.core.viewmodels.analysis_control_view_model import AnalysisControlViewModel
from zebtrack.core.viewmodels.hardware_status_view_model import HardwareStatusViewModel
from zebtrack.core.viewmodels.main_view_model_runtime import MainViewModelRuntime
from zebtrack.core.viewmodels.project_view_model import ProjectViewModel

if TYPE_CHECKING:
    pass

log = structlog.get_logger()


class MainViewModel:
    """
    Main View Model for ZebTrack-AI application.

    Refactored to follow Single Responsibility Principle by delegating initialization
    to ApplicationBootstrapper and functionality to specialized ViewModels:
    - ProjectViewModel: Project management
    - AnalysisControlViewModel: Analysis control
    - HardwareStatusViewModel: Hardware/Model status
    view: Any
    """

    def __init__(
        self,
        dependencies: MainViewModelDependencies,
        bootstrap_result: BootstrapResult,
    ) -> None:
        """Initialize MainViewModel with pre-bootstrapped components.

        Args:
            dependencies: Injected dependencies container
            bootstrap_result: Result of ApplicationBootstrapper initialization
        """
        # 1. Extract core dependencies (kept for facade/legacy access if needed)
        self._extract_dependencies(dependencies)

        # 2. Assign bootstrap result components
        self._assign_bootstrap_result(bootstrap_result)

        # Event bus flag
        self.ui_event_bus = self.event_dispatcher.event_bus
        self._use_event_bus = bool(self.ui_event_bus)

        # Debug: Log event bus ID for comparison with GUI
        log.info(
            "main_view_model.init.event_bus_setup",
            ui_event_bus_id=id(self.ui_event_bus) if self.ui_event_bus else None,
            deps_event_bus_id=id(dependencies.event_bus) if dependencies.event_bus else None,
            same_bus=self.ui_event_bus is dependencies.event_bus if self.ui_event_bus else "N/A",
        )

        # 3. Initialize Sub-ViewModels
        self.project_vm = ProjectViewModel(dependencies, bootstrap_result, self.ui_event_bus)
        self.analysis_vm = AnalysisControlViewModel(
            dependencies, bootstrap_result, self.ui_event_bus
        )
        self.hardware_vm = HardwareStatusViewModel(
            dependencies, bootstrap_result, self.ui_event_bus
        )

        self._runtime_handlers = MainViewModelRuntime(self)

        # Phase 6: self.view is now set inside _assign_bootstrap_result() from
        # BootstrapResult.view — no longer needs a None default here.

        # 4. Subscribe to state changes
        self._subscribe_to_state()

        log.info("main_view_model.initialized", source="init")

    def _extract_dependencies(self, dependencies: MainViewModelDependencies) -> None:
        """Extract and assign injected dependencies."""
        self.root = dependencies.root
        self.settings = dependencies.settings_obj
        self._test_sync_event = dependencies.test_sync_event

        self.state_manager = dependencies.state_manager
        self.project_manager = dependencies.project_manager
        self.weight_manager = dependencies.weight_manager
        self.model_service = dependencies.model_service
        self.detector_service = dependencies.detector_service
        self.video_processing_service = dependencies.video_processing_service
        self.project_workflow_service = dependencies.project_workflow_service
        self.ui_coordinator = dependencies.ui_coordinator

        # Super coordinators
        self.project_lifecycle_coordinator = dependencies.project_lifecycle_coordinator
        # Phase 4.9: HardwareCoordinator decomposed into 2 sub-coordinators
        self.detector_setup_coordinator = dependencies.detector_setup_coordinator
        self.model_diagnostics_coordinator = dependencies.model_diagnostics_coordinator
        self.processing_coordinator = dependencies.processing_coordinator
        # Phase 4.7: SessionCoordinator decomposed into 3 sub-coordinators
        self.recording_session_coordinator = dependencies.recording_session_coordinator
        self.live_camera_session_coordinator = dependencies.live_camera_session_coordinator
        self.live_calibration_coordinator = dependencies.live_calibration_coordinator
        self.live_batch_coordinator = dependencies.live_batch_coordinator  # v2.3.0

        # Legacy dependencies
        self._live_camera_service_param = dependencies.live_camera_service

        if self._test_sync_event is not None:
            self.state_manager.subscribe_all(self._on_state_change_for_test)

    def _assign_bootstrap_result(self, result: BootstrapResult) -> None:
        """Assign components created by ApplicationBootstrapper."""
        # Services
        self.project_service = result.project_service
        self.analysis_service = result.analysis_service
        self.video_classification_service = result.video_classification_service
        self.video_selection_service = result.video_selection_service
        self.video_validation_service = result.video_validation_service
        self.batch_configuration_service = result.batch_configuration_service
        self.dialog_coordinator = result.dialog_coordinator
        self.event_dispatcher = result.event_dispatcher

        # Phase 6: View is now assigned from BootstrapResult instead of external patching
        # (previously set by bootstrapper via controller_proxy.view = self.view)
        self.view = result.view

        # Hardware & Runtime
        # Note: active_weight_name and use_openvino are now properties that delegate to hardware_vm
        # (initialized in hardware_vm from bootstrap_result values)
        self._hardware_summary = result.hardware.hardware_summary
        self._recommended_backend = result.hardware.recommended_backend
        self.recorder = result.hardware.recorder
        self.arduino_manager = result.hardware.arduino_manager

        # Queues & Events
        self.frame_queue = result.runtime.frame_queue
        self.video_queue = result.runtime.video_queue
        self.program_exit_event = result.runtime.program_exit_event
        self.cancel_event = result.runtime.cancel_event

        # Legacy Orchestrators
        # Phase 0.3: VideoProcessingOrchestrator removed (migrated to ProcessingCoordinator)
        self.ui_state_controller = result.ui_state_controller
        # Phase 3A/B/C/D: Removed superseded orchestrators (see BootstrapResult)

        # Legacy Coordinators
        # Phase 4.9: detector_coordinator replaced by detector_setup_coordinator
        self.detector_setup_coordinator = result.legacy_coordinators.get("detector_coordinator")
        # Phase 3.5/3.6: Removed video_orchestrator and analysis_coordinator (dead code)
        # Phase 4.7: Removed recording_coordinator and live_camera_coordinator (dead code)

        # Adapter
        self.project_workflow_adapter = result.project_workflow_adapter

        # Runtime flags
        self._active_processing_mode = ProcessingMode.MULTI_TRACK
        self._cancel_feedback_displayed = False
        self.active_frame_source = None
        self.arduino = None  # Will be set when manager is initialized
        self.report_results_paths: dict[str, str] = {}
        self.timed_recording_job = None
        self._pending_external_trigger = None
        self._using_project_overrides = False  # Model override flag (managed by orchestrators)

        # Set legacy services if needed (for properties)
        self._recording_service: RecordingService | None = None

    def _subscribe_to_state(self) -> None:
        """Subscribe to state manager updates."""
        self.state_manager.subscribe(
            StateCategory.PROJECT, self._runtime_handlers.on_project_state_changed
        )
        self.state_manager.subscribe(
            StateCategory.DETECTOR, self._runtime_handlers.on_detector_state_changed
        )
        self.state_manager.subscribe(
            StateCategory.PROCESSING, self._runtime_handlers.on_processing_state_changed
        )

    def setup_detector_zones(self) -> None:
        """Setup detector zones from project data via ProjectLifecycleCoordinator."""

        def _callback(_: Any = None) -> None:
            # Get active video and zone data
            active_video = self.project_manager.get_active_zone_video()
            zone_data = self.project_manager.get_zone_data(video_path=active_video)

            # Configure detector
            self.detector_service.configure_zones(zones_data=zone_data)

        if self.project_lifecycle_coordinator:
            self.project_lifecycle_coordinator._setup_zones_from_project(
                setup_detector_zones_callback=_callback
            )

    # =========================================================================
    # Application Lifecycle
    # =========================================================================

    def run(self) -> None:
        """Start the Tkinter main event loop."""
        self.root.mainloop()

    def bind_events(self) -> None:
        """Binds all UI events."""
        if self._use_event_bus:
            self._runtime_handlers.register_event_handlers()
            # Phase 0.3: VideoProcessingOrchestrator.register_event_handlers was no-op, removed
            if self.processing_coordinator:
                self.processing_coordinator.register_event_handlers()

    # ==================== Properties ====================

    @property
    def recording_service(self) -> RecordingService | None:
        if hasattr(self, "hardware_vm"):
            return self.hardware_vm.recording_service
        return getattr(self, "_recording_service", None)

    @recording_service.setter
    def recording_service(self, value: RecordingService | None) -> None:
        if hasattr(self, "hardware_vm"):
            self.hardware_vm.recording_service = value
        else:
            self._recording_service = value

    @property
    def processing_thread(self) -> threading.Thread | None:
        state = self.state_manager.get_processing_state()
        return getattr(state, "processing_thread", None)

    @processing_thread.setter
    def processing_thread(self, value: threading.Thread | None) -> None:
        self.state_manager.update_processing_state(
            source="main_view_model.processing_thread",
            processing_thread=value,
        )

    @property
    def pending_single_video_analysis(self) -> Any | None:
        state = self.state_manager.get_processing_state()
        return getattr(state, "pending_single_video_analysis", None)

    @pending_single_video_analysis.setter
    def pending_single_video_analysis(self, value: Any | None) -> None:
        self.state_manager.update_processing_state(
            source="main_view_model.pending_single_video_analysis",
            pending_single_video_analysis=value,
        )

    @property
    def is_capturing_for_video(self) -> bool:
        state = self.state_manager.get_recording_state()
        return bool(getattr(state, "is_capturing_for_video", False))

    @is_capturing_for_video.setter
    def is_capturing_for_video(self, value: bool) -> None:
        self.state_manager.update_recording_state(
            source="main_view_model.is_capturing_for_video",
            is_capturing_for_video=value,
        )

    @property
    def detector(self) -> Detector | None:
        if hasattr(self, "hardware_vm"):
            return self.hardware_vm.detector
        return getattr(self, "_detector", None)

    @detector.setter
    def detector(self, value: Detector | None) -> None:
        if hasattr(self, "hardware_vm"):
            self.hardware_vm.detector = value
        else:
            self._detector = value

    @detector.deleter
    def detector(self) -> None:
        if hasattr(self, "hardware_vm"):
            self.hardware_vm.detector = None
        else:
            self._detector = None

    @property
    def detector_initialized(self) -> bool:
        if hasattr(self, "hardware_vm"):
            return self.hardware_vm.detector_initialized
        return getattr(self, "_detector", None) is not None

    @property
    def active_weight_name(self) -> str | None:
        if hasattr(self, "hardware_vm"):
            return self.hardware_vm.active_weight_name
        return getattr(self, "_active_weight_name", None)

    @active_weight_name.setter
    def active_weight_name(self, value: str | None) -> None:
        if hasattr(self, "hardware_vm"):
            self.hardware_vm.active_weight_name = value
        else:
            self._active_weight_name = value

    @property
    def use_openvino(self) -> bool:
        if hasattr(self, "hardware_vm"):
            return self.hardware_vm.use_openvino
        return getattr(self, "_use_openvino", False)

    @use_openvino.setter
    def use_openvino(self, value: bool) -> None:
        if hasattr(self, "hardware_vm"):
            self.hardware_vm.use_openvino = value
        else:
            self._use_openvino = value

    @property
    def settings_obj(self) -> Any:
        return self.settings

    def get_openvino_status(self) -> str:
        if hasattr(self, "hardware_vm"):
            return self.hardware_vm.get_openvino_status()
        return "Desconhecido"

    def get_all_weight_names(self) -> list[str]:
        if hasattr(self, "hardware_vm"):
            return self.hardware_vm.get_all_weight_names()
        return []

    @property
    def is_processing(self) -> bool:
        return self.analysis_vm.is_processing

    def _on_state_change_for_test(
        self, category: StateCategory, key: str, old: Any, new: Any
    ) -> None:
        if self._test_sync_event is not None:
            self._test_sync_event.set()

    @contextmanager
    def global_calibration_session(self) -> Generator[None, None, None]:
        """Context manager for global calibration mode. Delegates to ProjectLifecycleCoordinator."""
        if self.project_lifecycle_coordinator:
            with self.project_lifecycle_coordinator.global_calibration_session(
                get_active_weight_name=lambda: self.hardware_vm.active_weight_name,
                get_use_openvino=lambda: self.hardware_vm.use_openvino,
            ):
                yield
        else:
            log.warning("main_view_model.global_calibration.coordinator_missing")
            yield

    @contextmanager
    def project_calibration_session(self) -> Generator[None, None, None]:
        """Context manager for project calibration mode.

        Phase 3C: Delegates to ProjectLifecycleCoordinator (supersedes ProjectOrchestrator).
        """
        if self.project_lifecycle_coordinator:
            with self.project_lifecycle_coordinator.project_calibration_session():
                yield
        else:
            yield

    def on_close(self) -> None:
        if self.dialog_coordinator.confirm_exit():
            self.join_threads()
            self.root.destroy()

    def join_threads(self) -> None:
        self._runtime_handlers.join_threads()

    def log_arduino_event(self, message: str) -> None:
        self.hardware_vm.log_arduino_event(message)

    def on_arduino_status_change(self, connected: bool, port: str | None) -> None:
        self.hardware_vm.on_arduino_status_change(connected, port)

    def on_arduino_command_sent(self, command: int, success: bool, source: str) -> None:
        self.hardware_vm.on_arduino_command_sent(command, success, source)

    def on_arduino_event(self, event_code: int) -> None:
        """Route an inbound Arduino serial event to the recording coordinator.

        The ``ArduinoManager`` reader thread calls this on the controller when a
        numeric line arrives from the device (external-trigger flow). Delegates
        to ``RecordingSessionCoordinator.on_arduino_event`` when wired.
        """
        coordinator = getattr(self.hardware_vm, "recording_session_coordinator", None)
        if coordinator is not None and hasattr(coordinator, "on_arduino_event"):
            coordinator.on_arduino_event(event_code)
