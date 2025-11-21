"""Main application view model orchestrating the ZebTrack-AI application.

Coordinates all core services, manages application state, handles user interactions,
and orchestrates video processing workflows with dependency injection.
"""

from __future__ import annotations

import glob
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import structlog

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.analysis.reporter import Reporter
from zebtrack.analysis.roi import ROI
from zebtrack.coordinators.dialog_coordinator import DialogCoordinator
from zebtrack.coordinators.hardware_coordinator import HardwareCoordinator
from zebtrack.coordinators.processing_coordinator import ProcessingCoordinator

# Phase 3: Super Coordinator imports (REFACTOR-MASTER-PLAN-2025 Phase 3)
from zebtrack.coordinators.project_lifecycle_coordinator import ProjectLifecycleCoordinator
from zebtrack.coordinators.session_coordinator import SessionCoordinator

# Phase 1 Service imports (REFACTOR-VIEWMODEL-PHASE-1)
from zebtrack.core.batch_configuration_service import BatchConfigurationService
from zebtrack.core.calibration import Calibration
from zebtrack.core.dependency_container import MainViewModelDependencies
from zebtrack.core.detector import Detector, ZoneData

# Phase 2 imports (REFACTOR-VIEWMODEL-PHASE-2: Facade Removal)
from zebtrack.core.orchestrator_registry import OrchestratorRegistry
from zebtrack.core.processing_mode import ProcessingMode
from zebtrack.core.processing_worker import (
    ProcessingWorker,
)
from zebtrack.core.project_service import ProjectService
from zebtrack.core.recording_service import RecordingService
from zebtrack.core.state_manager import StateCategory
from zebtrack.core.thread_coordinator import ThreadCoordinator
from zebtrack.io.arduino import Arduino
from zebtrack.io.arduino_manager import ArduinoManager
from zebtrack.io.recorder import Recorder
from zebtrack.orchestrators.ui_state_controller import UIStateController
from zebtrack.ui.components.event_dispatcher import EventDispatcher
from zebtrack.ui.events import Events
from zebtrack.ui.project_workflow_adapter import ProjectWorkflowAdapter
from zebtrack.utils.hardware_detection import get_hardware_summary, recommend_backend

log = structlog.get_logger()

# Default thresholds (will be overridden by settings when injected)
DEFAULT_TRACK_THRESHOLD = 0.25
DEFAULT_MATCH_THRESHOLD = 0.15


def _is_valid_openvino_directory(path: str | None) -> bool:
    """
    Validate if an OpenVINO model directory exists and contains required .xml files.

    Args:
        path: Path to the OpenVINO model directory

    Returns:
        True if the directory exists and contains at least one .xml file, False otherwise
    """
    if not path or not os.path.exists(path):
        return False

    if not os.path.isdir(path):
        return False

    xml_files = glob.glob(os.path.join(path, "*.xml"))
    return len(xml_files) > 0


class DiagnosticAbortError(RuntimeError):
    """Signal used to stop diagnostic workflow without surfacing duplicate dialogs."""


class MainViewModel:
    """
    Main View Model for ZebTrack-AI application.

    Phase 1, Step 3: Refactored from AppController to follow
    Single Responsibility Principle.

    Phase 2, Step 4: Integrated with centralized StateManager
    for predictable state flow.

    Phase 3, Task 3.2: Constructor simplified to use MainViewModelDependencies
    config object pattern (reduces 26 parameters → 1).

    This class now focuses on:
    - UI-facing state management (via StateManager)
    - Command handling via event bus
    - Orchestrating services (ProjectService, AnalysisService)
    - Hardware setup (detector, Arduino)
    - Recording control

    Heavy file I/O moved to ProjectService.
    Analysis orchestration moved to AnalysisService.
    State mutations now tracked through StateManager.
    """

    def __init__(
        self,
        dependencies: MainViewModelDependencies,
        view=None,  # Phase 2: ApplicationGUI instance (optional - will be created if None)
    ):
        """Initialize MainViewModel with dependency injection.

        Task 3.2: Simplified constructor using config object pattern.
        Task 3.1: Ultra-lean __init__ delegates all setup to helper methods (34 lines).

        Args:
            dependencies: MainViewModelDependencies containing all required services
            view: ApplicationGUI instance (optional, will be created if None)
        """
        # Extract and assign all dependencies from config object
        self._extract_dependencies(dependencies)

        # Initialize all service layer components
        self._init_services(dependencies)

        # Initialize hardware and models
        self._init_hardware_and_models()

        # Initialize runtime state
        self._init_runtime_state(dependencies.event_bus)

        # Initialize view
        self._init_view(view)

        # Initialize orchestrators
        self._init_orchestrators(dependencies)

        # Subscribe to state changes
        self._subscribe_to_state()

        log.info("main_view_model.initialized", source="init")

    def _extract_dependencies(self, dependencies: MainViewModelDependencies):
        """Extract and assign all injected dependencies from config object.

        Task 3.1: Extracted from __init__ to reduce complexity (was 37 lines inline).
        Phase 3: Added extraction of 4 super coordinators.
        """
        # Core dependencies
        self.root = dependencies.root
        self.settings = dependencies.settings_obj
        self._test_sync_event = dependencies.test_sync_event

        # Service dependencies
        self.state_manager = dependencies.state_manager
        self.project_manager = dependencies.project_manager
        self.weight_manager = dependencies.weight_manager
        self.model_service = dependencies.model_service
        self.detector_service = dependencies.detector_service
        self.video_processing_service = dependencies.video_processing_service
        self.project_workflow_service = dependencies.project_workflow_service
        self.ui_coordinator = dependencies.ui_coordinator

        # Phase 3: Extract super coordinators (NEW)
        self._project_lifecycle_coordinator_param = dependencies.project_lifecycle_coordinator
        self._hardware_coordinator_param = dependencies.hardware_coordinator
        self._processing_coordinator_param = dependencies.processing_coordinator
        self._session_coordinator_param = dependencies.session_coordinator

        # Legacy coordinators (DEPRECATED - kept for backward compatibility during Phase 3)
        self.recording_coordinator = dependencies.recording_coordinator

        # Deferred initialization parameters
        self._live_camera_service_param = dependencies.live_camera_service

        # Register test observer if sync event provided
        if self._test_sync_event is not None:
            self.state_manager.subscribe_all(self._on_state_change_for_test)

    def _init_services(self, dependencies: MainViewModelDependencies):
        """Initialize all service layer components.

        Task 3.1: Extracted from __init__ to reduce complexity (was 24 lines inline).
        """
        # Core services
        self.project_service = ProjectService()
        self.analysis_service = (
            dependencies.analysis_service
            if dependencies.analysis_service is not None
            else AnalysisService(settings_obj=self.settings)
        )

        # Video processing helper services
        from zebtrack.core.video_classification_service import VideoClassificationService
        from zebtrack.core.video_selection_service import VideoSelectionService
        from zebtrack.core.video_validation_service import VideoValidationService

        self.video_classification_service = VideoClassificationService()
        self.video_selection_service = VideoSelectionService()
        self.video_validation_service = VideoValidationService()

        # Recording and live camera services (deferred initialization)
        self._recording_service = None
        self.recording_service = dependencies.recording_service
        self.recording_session_orchestrator = None  # Created in _init_orchestrators
        self.live_camera_service = None  # Initialized later

        # Phase 1 Services (REFACTOR-VIEWMODEL-PHASE-1)
        # Initialize services created during Phase 1 refactoring
        self.batch_configuration_service = BatchConfigurationService(
            project_manager=self.project_manager,
            settings_obj=self.settings,
        )
        self.thread_coordinator = ThreadCoordinator()
        self.dialog_coordinator = DialogCoordinator(
            ui_coordinator=self.ui_coordinator,
            event_bus=dependencies.event_bus,
            state_manager=self.state_manager,
        )
        self.event_dispatcher = EventDispatcher(event_bus=dependencies.event_bus)

    def _init_hardware_and_models(self):
        """Initialize hardware detection and model configuration."""
        # New state variables for model management (must exist before view)
        default_weight, _ = self._safe_get_default_weight()

        # ✅ Raise exception if no valid weight is available
        if not isinstance(default_weight, str) or not default_weight:
            raise RuntimeError(
                "No valid detector weight available. Cannot initialize application. "
                "Please ensure at least one .pt or .onnx file is in the 'models/' directory."
            )

        self.active_weight_name = default_weight

        # Hardware detection and auto-configuration (Phase 7)
        log.info("controller.init.hardware_detection_start")
        hardware_summary = get_hardware_summary()
        recommended_backend = recommend_backend()

        # Auto-configure use_openvino based on hardware detection
        if recommended_backend == "openvino":
            # Check if OpenVINO model is already converted
            default_weight_details = None
            if self.active_weight_name:
                default_weight_details = self.weight_manager.get_weight_details(
                    self.active_weight_name
                )

            openvino_converted = False
            if default_weight_details:
                ov_path = default_weight_details.get("openvino_path")
                openvino_converted = _is_valid_openvino_directory(ov_path)

            if openvino_converted:
                self.use_openvino = True
                log.info(
                    "controller.init.auto_selected_openvino",
                    reason="Hardware detection recommends OpenVINO and model is converted",
                    cuda_available=hardware_summary["cuda_available"],
                    openvino_available=hardware_summary["openvino_available"],
                    intel_gpu=hardware_summary["has_intel_gpu"],
                )
            else:
                # OpenVINO recommended but model not converted - fall back to PyTorch
                self.use_openvino = False
                log.warning(
                    "controller.init.openvino_recommended_but_not_converted",
                    reason=(
                        "OpenVINO recommended by hardware but model not yet "
                        "converted, using PyTorch"
                    ),
                    cuda_available=hardware_summary["cuda_available"],
                    openvino_available=hardware_summary["openvino_available"],
                    intel_gpu=hardware_summary["has_intel_gpu"],
                    active_weight=self.active_weight_name,
                )
        else:
            self.use_openvino = False
            log.info(
                "controller.init.auto_selected_pytorch",
                reason="Hardware detection recommends PyTorch",
                cuda_available=hardware_summary["cuda_available"],
            )

        # Phase 2.4: Removed _global_model_defaults dictionary
        # Now access via get_global_model_defaults() which uses StateManager
        self._using_project_overrides = False

        # Store for UI update later
        self._hardware_summary = hardware_summary
        self._recommended_backend = recommended_backend

    def _init_runtime_state(self, event_bus):
        """Initialize runtime attributes and threading primitives."""
        # Core runtime attributes
        # Note: detector is now managed by detector_service (Phase 6)
        # Access via self.detector property which delegates to service
        self.recorder = Recorder(settings_obj=self.settings)
        self.camera = None  # Camera instance (created on-demand for live analysis)
        self.live_preview_window = None  # Live preview window for camera analysis
        self.analysis_interval_frames = 1  # How often to run detection (default every frame)
        self.display_interval_frames = 1  # How often to display frames (default every frame)

        # Queues for live frame processing
        import queue

        self.frame_queue = queue.Queue(maxsize=30)  # Queue for frames to be processed
        self.video_queue = queue.Queue(maxsize=30)  # Queue for frames to be recorded
        self.is_capturing_for_video = False  # Flag for video recording
        self.active_frame_source = None  # Current source for live frames (Camera or other)

        self.arduino: Arduino | None = None
        self.arduino_manager: ArduinoManager | None = None
        self._arduino_manager_cls = ArduinoManager
        self.report_results_paths = {}
        # Note: is_recording now managed by StateManager via @property
        self.timed_recording_job = None
        self._pending_external_trigger: dict | None = None

        # Initialize recording state in StateManager
        self.state_manager.update_recording_state(
            source="controller.init",
            is_recording=False,
        )

        # Exit event for threads (deprecated - now managed by live_camera_service)
        import threading

        self.program_exit_event = threading.Event()

        # Event bus configuration
        self.ui_event_bus = event_bus
        if event_bus:
            self._use_event_bus = True
        else:
            ui_features = getattr(self.settings, "ui_features", None)
            self._use_event_bus = bool(
                ui_features and getattr(ui_features, "enable_event_queue", False)
            )

        if self._use_event_bus:
            log.info("controller.event_bus.enabled")
            # Event handlers are now registered via bind_events()
        else:
            log.warning(
                "controller.event_bus.disabled",
                message="EventBus is disabled. Using legacy direct callbacks. This is deprecated.",
            )

        # Set global model defaults on project workflow service
        self.project_workflow_service.set_global_model_defaults(
            active_weight=self.active_weight_name or None,
            use_openvino=self.use_openvino,
        )

        self._active_processing_mode = ProcessingMode.MULTI_TRACK

        # Initialize core threading primitives first
        self.processing_thread: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.pending_single_video_analysis = None
        self.processing_worker: ProcessingWorker | None = None
        self._cancel_feedback_displayed = False

    def _init_view(self, view):
        """Initialize the view integration.

        Phase 4: View is no longer stored in MainViewModel.
        It interacts solely through EventBus and Coordinators.
        """
        # Phase 4: View should be handled by UICoordinator or created in Composition Root
        # We no longer store self.view
        self._view_reference = view  # Temporary reference if absolutely needed for legacy bridging

        # Update GPU hardware display in UI via EventBus
        if self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_UPDATE_GPU_INFO, {"hardware_summary": self._hardware_summary}
            )

        # Update OpenVINO status via EventBus
        if self._recommended_backend == "openvino" and not self.use_openvino:
            status_msg = "Recomendado mas modelo não convertido. Use 'Diagnóstico' para converter."
            if self.ui_event_bus:
                self.ui_event_bus.publish_event(
                    Events.UI_UPDATE_OPENVINO_STATUS, {"status": status_msg}
                )

    def _init_orchestrators(self, dependencies: MainViewModelDependencies):
        """Initialize all orchestrators and coordinators."""
        # Initialize services (Phase 2.2 + Phase 3 + Phase 7.2)
        # Recording service initialization (setup callbacks if service was injected)
        # Note: recording_session_orchestrator functionality moved to session_coordinator
        # We rely on SessionCoordinator for recording logic now.

        # Task 2.2/2.3: Initialize or use injected coordinators (REFACTOR-VIEWMODEL-001)
        # Phase 3: Pass super coordinators
        self._init_coordinators(
            # Phase 3: Super Coordinators (NEW)
            project_lifecycle_coordinator=dependencies.project_lifecycle_coordinator,
            hardware_coordinator=dependencies.hardware_coordinator,
            processing_coordinator=dependencies.processing_coordinator,
            session_coordinator=dependencies.session_coordinator,
        )

        # Sprint 28: UI State Controller - Still needed for UI-specific logic
        # Phase 4: This will be refactored to UICoordinator in future
        self.ui_state_controller = UIStateController(self)

        # Phase 3: Setup coordinator callbacks AFTER all coordinators and orchestrators are initialized
        self._setup_coordinator_callbacks()

        # Phase 2: Create OrchestratorRegistry for direct access (REFACTOR-VIEWMODEL-PHASE-2)
        # This registry allows callers to access orchestrators directly without facade methods
        # Phase 3 Update: Registry now points to new Super Coordinators where applicable
        # Note: Some legacy keys are kept but point to new coordinators or None if deprecated
        self.orchestrators = OrchestratorRegistry(
            recording_session_orchestrator=self.session_coordinator, # Mapped to SessionCoordinator
            project_orchestrator=self.project_lifecycle_coordinator, # Mapped to ProjectLifecycleCoordinator
            ui_state_controller=self.ui_state_controller,
            video_processing_orchestrator=self.processing_coordinator, # Mapped to ProcessingCoordinator
            analysis_orchestrator=self.processing_coordinator, # Mapped to ProcessingCoordinator
            processing_config_orchestrator=self.processing_coordinator, # Mapped to ProcessingCoordinator
            model_diagnostics_orchestrator=self.hardware_coordinator, # Mapped to HardwareCoordinator
            zone_arena_orchestrator=self.processing_coordinator, # Mapped to ProcessingCoordinator
            calibration_orchestrator=self.project_lifecycle_coordinator, # Mapped to ProjectLifecycleCoordinator
            live_camera_coordinator=self.session_coordinator, # Mapped to SessionCoordinator
        )

    def _subscribe_to_state(self):
        """Subscribe to state manager updates."""
        # Phase 4: MVVM State Observer Callbacks
        self.state_manager.subscribe(StateCategory.PROJECT, self._on_project_state_changed)
        self.state_manager.subscribe(StateCategory.DETECTOR, self._on_detector_state_changed)
        # Phase 4 TODO: Implement _on_recording_state_changed or delegate to SessionCoordinator
        # self.state_manager.subscribe(StateCategory.RECORDING, self._on_recording_state_changed)
        self.state_manager.subscribe(StateCategory.PROCESSING, self._on_processing_state_changed)

        # NOTE: bind_events() foi movido para __main__.py na FASE 1
        # NÃO chamar self.bind_events() aqui para evitar dupla inscrição

    def _inject_or_create(self, attr_name: str, injected, factory_fn):
        """
        Helper to inject coordinator or create with factory.

        Sprint 16: Reduces boilerplate in _init_coordinators().
        """
        if injected is not None:
            setattr(self, attr_name, injected)
            log.info(f"main_view_model.{attr_name}.injected")
        else:
            setattr(self, attr_name, factory_fn())
            log.info(f"main_view_model.{attr_name}.created_internally")

    def _init_coordinators(
        self,
        # Phase 3: Super Coordinators (NEW)
        project_lifecycle_coordinator: ProjectLifecycleCoordinator | None = None,
        hardware_coordinator: HardwareCoordinator | None = None,
        processing_coordinator: ProcessingCoordinator | None = None,
        session_coordinator: SessionCoordinator | None = None,
        # Legacy coordinators (DEPRECATED - ignored)
        **kwargs
    ) -> None:
        """
        Initialize coordinators for hardware, video, analysis, recording, live camera,
        detector, and processing.

        Phase 3: Updated to accept and initialize 4 super coordinators.
        Legacy coordinators are deprecated and no longer initialized.

        Sprint 16: Simplified using _inject_or_create() helper.
        Task 2.2: Refactor ViewModel
        Task 2.3: Accept injected coordinators or create them for backward compatibility
        Sprint 4: Added recording_coordinator and live_camera_coordinator
        Sprint 5: Added detector_coordinator
        Sprint 6: Added processing_coordinator
        """
        # =========================================================================
        # Phase 3: SUPER COORDINATORS (NEW - replace legacy coordinators)
        # =========================================================================

        # 1. ProjectLifecycleCoordinator (consolidates ProjectOrchestrator + CalibrationOrchestrator)
        self._inject_or_create(
            "project_lifecycle_coordinator",
            project_lifecycle_coordinator,
            lambda: None,  # Must be injected from __main__.py
        )

        # 2. HardwareCoordinator (consolidates DetectorCoordinator + ModelDiagnosticsOrchestrator)
        # NOTE: This REPLACES the legacy hardware_coordinator (which was actually DetectorCoordinator)
        self._inject_or_create(
            "hardware_coordinator",
            hardware_coordinator,
            lambda: None,  # Must be injected from __main__.py
        )

        # 3. ProcessingCoordinator (consolidates 5 orchestrators)
        # NOTE: This REPLACES the legacy processing_coordinator
        self._inject_or_create(
            "processing_coordinator",
            processing_coordinator,
            lambda: None,  # Must be injected from __main__.py
        )

        # 4. SessionCoordinator (consolidates RecordingSessionOrchestrator + LiveCameraCoordinator + RecordingCoordinator)
        self._inject_or_create(
            "session_coordinator",
            session_coordinator,
            lambda: None,  # Must be injected from __main__.py
        )

        # Set View and Root for coordinators that still need UI access (Legacy bridge)
        # In Phase 4, we will move away from direct View access
        # Note: View is now typically passed via UICoordinator or handled internally
        if self.processing_coordinator:
            self.processing_coordinator.view = self._view_reference
            self.processing_coordinator.root = self.root
            self.processing_coordinator.detector = self.detector

        if self.session_coordinator:
            self.session_coordinator.view = self._view_reference
            self.session_coordinator.root = self.root

        if self.hardware_coordinator:
            self.hardware_coordinator.view = self._view_reference
            self.hardware_coordinator.root = self.root
            self.hardware_coordinator.set_convert_weight_callback(self._convert_weight_callback_bridge)

        log.info(
            "main_view_model.super_coordinators_initialized",
            project_lifecycle=self.project_lifecycle_coordinator is not None,
            hardware=self.hardware_coordinator is not None,
            processing=self.processing_coordinator is not None,
            session=self.session_coordinator is not None,
        )

        # Project workflow adapter (P2-T2: project create/open/close workflows)
        self.project_workflow_adapter = ProjectWorkflowAdapter(
            project_workflow_service=self.project_workflow_service,
            project_manager=self.project_manager,
            detector_service=self.detector_service,
            state_manager=self.state_manager,
            ui_event_bus=self.ui_event_bus,
        )

        log.info("main_view_model.coordinators_initialized")

    def _convert_weight_callback_bridge(self, weight_name: str):
        """Bridge method for weight conversion callback.
        Phase 4: Move logic to ModelService/HardwareCoordinator entirely.
        """
        # Logic was in MainViewModel, now should be handled by HardwareCoordinator
        # or ModelService. For now, this is a placeholder if needed.
        pass

    def _setup_coordinator_callbacks(self):
        """Setup callbacks between coordinators and orchestrators.

        Phase 3: This method is called AFTER all coordinators and orchestrators
        are initialized, to avoid circular dependencies during initialization.
        """
        # Phase 3: Recording callbacks now point to SessionCoordinator (super coordinator)
        if self.hardware_coordinator and self.session_coordinator:
            self.hardware_coordinator.set_recording_callbacks(
                self.session_coordinator.trigger_recording,
                self.session_coordinator.stop_recording,
            )

    # =========================================================================
    # Phase 3: Delegation Methods (TEMPORARY - for backward compatibility)
    # =========================================================================
    # These methods delegate to super coordinators/orchestrators.
    # Phase 4 TODO: Remove these and refactor callers to use coordinators directly.

    def set_active_weight(self, name: str | None, dialog=None):
        """Phase 3: Delegate to UIStateController."""
        return self.ui_state_controller.set_active_weight(name, dialog)

    def set_openvino_usage(self, use_openvino: bool, dialog=None):
        """Phase 3: Delegate to UIStateController."""
        return self.ui_state_controller.set_openvino_usage(use_openvino, dialog)

    def update_openvino_status(self, dialog=None):
        """Phase 3: Delegate to UIStateController."""
        return self.ui_state_controller.update_openvino_status(dialog)

    def close_project(self):
        """Phase 3: Delegate to ProjectLifecycleCoordinator."""
        return self.project_lifecycle_coordinator.close_project()

    def _setup_zones_from_project(self):
        """Phase 3: Delegate to ProjectLifecycleCoordinator."""
        # Assuming callback logic is handled within coordinator or adapter
        return self.project_lifecycle_coordinator._setup_zones_from_project(
            setup_detector_zones_callback=self.detector_service.configure_zones
        )

    def open_project_workflow(self, project_path):
        """Phase 3: Delegate to ProjectLifecycleCoordinator."""
        return self.project_lifecycle_coordinator.open_project(
            project_path,
            setup_detector_callback=self.setup_detector,
            set_active_weight_callback=self.set_active_weight,
            set_openvino_usage_callback=self.set_openvino_usage,
            update_openvino_status_callback=self.update_openvino_status,
            restore_detector_callback=lambda: None, # handled internally by coordinator if needed
            get_active_weight_name=lambda: self.active_weight_name,
            get_use_openvino=lambda: self.use_openvino
        )

    # =========================================================================
    # Application Lifecycle
    # =========================================================================

    def run(self):
        """Start the Tkinter main event loop.

        This is the main entry point for running the application GUI.
        """
        # The GUI is now responsible for populating its own widgets when created.
        self.root.mainloop()

    def bind_events(self):
        """
        Binds all UI events to their respective handlers in the ViewModel.

        This method should be called after the ViewModel and View are fully
        initialized to ensure that all dependencies are in place before
        event listeners are attached. Separating event binding from __init__
        is crucial for testability, as it allows mocks to be injected
        before the event bus starts routing events.
        """
        if self._use_event_bus:
            log.info("controller.bind_events.start")
            self._register_event_handlers()
            # Phase 2.3: Orchestrators register their own event handlers
            self.video_processing_orchestrator.register_event_handlers()
            log.info("controller.bind_events.complete")

    # ==================== Phase 2, Step 4: State Manager Properties ====================  # noqa: E501
    # Backward-compatible properties that delegate to StateManager

    @property
    def recording_service(self) -> RecordingService | None:
        return self._recording_service

    @recording_service.setter
    def recording_service(self, value: RecordingService | None) -> None:
        self._recording_service = value
        coordinator = getattr(self, "recording_coordinator", None)
        if coordinator is not None:
            coordinator.recording_service = value

    @property
    def _global_model_defaults(self) -> dict:
        """Phase 2.4: Backward-compatible proxy to StateManager.

        WARNING: This is a read-only property. Direct assignment like
        `_global_model_defaults["key"] = value` will NOT persist to StateManager.
        Use StateManager.update_detector_state() instead.

        Returns:
            Dictionary with active_weight and use_openvino from StateManager.
        """
        detector_state = self.state_manager.get_detector_state()
        return {
            "active_weight": detector_state.active_weight_name,
            "use_openvino": detector_state.use_openvino,
        }

    @property
    def detector(self) -> Detector | None:
        """
        Get detector instance from DetectorService.

        Phase 6: Detector is now managed by detector_service.
        This property provides backward compatibility.
        """
        return self.detector_service.detector

    @detector.setter
    def detector(self, value: Detector | None) -> None:
        """
        Set detector instance on DetectorService.

        Phase 6: Allows tests to inject mock detectors and provides backward compatibility.
        """
        self.detector_service.detector = value

    @detector.deleter
    def detector(self) -> None:
        """
        Delete detector instance from DetectorService.

        Phase 6: Allows proper cleanup in mocked tests.
        """
        self.detector_service.detector = None

    @property
    def detector_initialized(self) -> bool:
        """Get detector initialization status from StateManager."""
        return self.state_manager.get_detector_state().detector_initialized

    @property
    def is_processing(self) -> bool:
        """Get processing status from StateManager."""
        return self.state_manager.get_processing_state().is_processing

    def _on_state_change_for_test(
        self,
        category: StateCategory,
        key: str,
        old_value: Any,
        new_value: Any,
    ) -> None:
        """
        Observer callback for test synchronization.

        Phase 1.1: Signals test_sync_event after state changes are processed,
        eliminating race conditions in integration tests.

        Args:
            category: State category that changed
            key: State key that changed
            old_value: Previous value
            new_value: New value
        """
        if self._test_sync_event is not None:
            # Signal that state change has been processed
            self._test_sync_event.set()
            log.debug(
                "controller.test_sync.state_change_signaled",
                category=category.name,
                key=key,
            )

    # Phase 4: MVVM State Observer Callbacks
    def _on_project_state_changed(
        self, category: StateCategory, key: str, old_value: Any, new_value: Any
    ):
        """Publica eventos de UI em resposta a mudanças no estado do Projeto."""
        if not self.ui_event_bus:
            return
        if key == "active_zone_video" or key == "project_data":
            zone_data = self.project_manager.get_zone_data()
            self.ui_event_bus.publish_event(Events.UI_REDRAW_ZONES, {"zone_data": zone_data})
            self.ui_event_bus.publish_event(Events.UI_UPDATE_ZONE_LIST, {"zone_data": zone_data})

    def _on_detector_state_changed(
        self, category: StateCategory, key: str, old_value: Any, new_value: Any
    ):
        """Publica eventos de UI em resposta a mudanças no estado do Detector."""
        if not self.ui_event_bus:
            return
        if key == "active_weight_name":
            self.ui_event_bus.publish_event(Events.UI_SET_ACTIVE_WEIGHT, {"weight_name": new_value})
        elif key == "use_openvino":
            self.ui_event_bus.publish_event(
                Events.UI_UPDATE_OPENVINO_CHECKBOX, {"is_checked": new_value}
            )
            self.ui_state_controller.update_openvino_status()

    def _on_processing_state_changed(
        self, category: StateCategory, key: str, old_value: Any, new_value: Any
    ):
        """Publica eventos de UI em resposta a mudanças no estado de Processamento."""
        if key == "is_processing":
            # Phase 4: Use generic view update via UICoordinator (which holds view reference)
            if new_value:  # Processamento iniciou
                self.ui_coordinator.update_view(None, "start_analysis_view_mode")
            else:  # Processamento terminou
                self.ui_coordinator.update_view(None, "stop_analysis_view_mode")
        elif key == "cancel_requested" and new_value:
            self.ui_state_controller._show_cancel_feedback()  # Mostrar feedback de cancelamento imediatamente

    def get_openvino_status(self) -> str:
        """
        Get the current OpenVINO status text based on the model and self.settings.

        Delegates to ModelService for business logic (Phase 2.1).
        """
        return self.model_service.get_openvino_status(
            weight_name=self.active_weight_name, use_openvino=self.use_openvino
        )

    def on_close(self):
        """Handle application close event with user confirmation.

        Prompts user for confirmation, stops event bus polling, joins threads,
        and destroys the root window.
        """
        if self.dialog_coordinator.confirm_exit(None): # Phase 4: UICoordinator has view
            # Access view through UICoordinator if needed for stop_event_bus_polling
            view = self.ui_coordinator.view
            if view and hasattr(view, "stop_event_bus_polling"):
                try:
                    view.stop_event_bus_polling()
                except (RuntimeError, OSError) as e:
                    # Expected errors during cleanup (e.g., already stopped, thread issues)
                    log.warning("controller.event_bus.stop_failed", error=str(e), exc_info=True)
            self.join_threads()
            self.root.destroy()

    def join_threads(self):
        """Signals all threads to stop and waits for them to finish."""
        log.info("controller.shutdown.start")
        self.program_exit_event.set()

        # Join background threads (video processing threads)
        # Note: Live camera threads are managed by LiveCameraService
        if self.processing_thread is not None and self.processing_thread.is_alive():
            log.info("controller.shutdown.join_processing_thread")
            self.processing_thread.join()

        capture_thread = getattr(self, "capture_thread", None)
        if capture_thread is not None and capture_thread.is_alive():
            log.info("controller.shutdown.join_capture_thread")
            capture_thread.join()

        # Release camera resources
        if hasattr(self, "camera") and self.camera:
            log.info("controller.shutdown.release_camera")
            self.camera.release()

        self._shutdown_arduino_manager()

        log.info("controller.shutdown.complete")

    def _get_arduino_manager(self) -> ArduinoManager:
        if self.arduino_manager is None:
            self.arduino_manager = self._arduino_manager_cls(self)
        return self.arduino_manager

    def _shutdown_arduino_manager(self):
        if self.arduino_manager:
            try:
                self.arduino_manager.shutdown()
            except (OSError, RuntimeError) as e:
                # Expected errors: serial port issues, already closed
                log.warning("controller.arduino.shutdown_failed", error=str(e), exc_info=True)
            self.arduino_manager = None
        self.arduino = None

    def _create_event_dispatcher(self, event_name: str):
        """Create event-specific dispatcher closures.

        Phase 7.1: Generic dispatcher that replaces 32 individual _handle_* methods.

        Args:
            event_name: The event identifier (e.g., Events.RECORDING_START)

        Returns:
            Callable that extracts params from event data and calls controller method
        """
        method_name, param_names, mode = self._EVENT_METHOD_MAPPING[event_name]

        def dispatcher(data: dict) -> None:
            """Delegate event to controller method."""
            method = getattr(self, method_name)

            if mode == "no_params":
                method()
            elif mode == "kwargs_all":
                method(**data)
            elif mode == "kwargs_get":
                kwargs = {param: data.get(param) for param in param_names}
                method(**kwargs)
            elif mode == "positional":
                args = [data[param] for param in param_names]
                method(*args)
            elif mode == "positional_optional":
                # Positional args where later params are optional (use .get() for all)
                args = [data.get(param) for param in param_names]
                method(*args)
            else:
                log.error("controller.event_dispatcher.unknown_mode", event=event_name, mode=mode)

        return dispatcher

    def _register_event_handlers(self) -> None:
        """Subscribe to all UI->Controller events when event bus is enabled.

        Phase 7.1: Uses generic dispatcher to eliminate 32 individual handler methods.
        Each event is mapped to (method_name, params, mode) in _EVENT_METHOD_MAPPING.
        """
        if not self.ui_event_bus:
            return

        bus = self.ui_event_bus
        log.info("controller.register_event_handlers.start")

        # Subscribe all events to generic dispatcher
        for event_name in self._EVENT_METHOD_MAPPING.keys():
            dispatcher = self._create_event_dispatcher(event_name)
            bus.subscribe(event_name, dispatcher)

        # Also subscribe to the special single-video setup event
        bus.subscribe(
            "ui:setup_zone_definition_for_single_video",
            self._handle_setup_zone_definition_for_single_video,
        )

        # P0-ARCH001: Subscribe to PROJECT_MANAGER_REPLACED to update all cached references
        bus.subscribe(
            Events.PROJECT_MANAGER_REPLACED,
            self._handle_project_manager_replaced,
        )

        log.info(
            "controller.register_event_handlers.complete", count=len(self._EVENT_METHOD_MAPPING) + 2
        )


    def _handle_project_manager_replaced(self, data: dict):
        """Handle PROJECT_MANAGER_REPLACED event to update all cached references.

        P0-ARCH001 Fix: Ensures all services and orchestrators receive the new
        ProjectManager instance after close_project() to prevent state divergence.

        Args:
            data: Event payload containing old_manager and new_manager
        """
        new_manager = data.get("new_manager")
        if not new_manager:
            log.warning("main_view_model.project_manager_replaced.missing_new_manager")
            return

        # Update all services and orchestrators that cache ProjectManager
        services_to_update = [
            ("project_workflow_service", self.project_workflow_service),
            ("detector_service", self.detector_service),
            ("video_processing_service", self.video_processing_service),
            ("live_camera_service", self.live_camera_service),
            ("recording_service", self.recording_service),
            ("video_orchestrator", self.video_orchestrator),
            ("analysis_coordinator", self.analysis_coordinator),
            ("hardware_coordinator", self.hardware_coordinator),
            ("processing_coordinator", self.processing_coordinator),
            ("zone_management_facade", self.zone_management_facade),
        ]

        # Update orchestrators that cache ProjectManager
        orchestrators_to_update = [
            ("video_processing_orchestrator", self.video_processing_orchestrator),
            ("analysis_orchestrator", self.analysis_orchestrator),
            ("calibration_orchestrator", self.calibration_orchestrator),
            ("recording_session_orchestrator", self.recording_session_orchestrator),
            ("processing_config_orchestrator", self.processing_config_orchestrator),
        ]

        updated_count = 0

        # Call rebinding method on each service/orchestrator
        for name, service in services_to_update + orchestrators_to_update:
            if service and hasattr(service, "_on_project_manager_replaced"):
                try:
                    service._on_project_manager_replaced(data)
                    updated_count += 1
                except Exception as exc:
                    log.error(
                        "main_view_model.project_manager_replaced.service_update_failed",
                        service=name,
                        error=str(exc),
                        exc_info=True
                    )
            elif service and hasattr(service, "project_manager"):
                # Fallback: directly update if method doesn't exist
                try:
                    service.project_manager = new_manager
                    updated_count += 1
                    log.debug(
                        "main_view_model.project_manager_replaced.direct_update",
                        service=name
                    )
                except Exception as exc:
                    log.error(
                        "main_view_model.project_manager_replaced.direct_update_failed",
                        service=name,
                        error=str(exc)
                    )

        log.info(
            "main_view_model.project_manager_replaced.complete",
            services_updated=updated_count,
            total_services=len(services_to_update) + len(orchestrators_to_update)
        )

    def log_arduino_event(self, message: str):
        """Task 2.2: Delegates to HardwareCoordinator."""
        self.hardware_coordinator.log_arduino_event(message)

    def on_arduino_status_change(self, connected: bool, port: str | None):
        """Task 2.2: Delegates to HardwareCoordinator."""
        self.hardware_coordinator.on_arduino_status_change(connected, port)

    def on_arduino_command_sent(self, command: int, success: bool, source: str):
        """Task 2.2: Delegates to HardwareCoordinator."""
        self.hardware_coordinator.on_arduino_command_sent(command, success, source)

    def create_project_workflow(self, **wizard_data):
        """Create new project workflow with backward-compatible signature."""
        return self.project_lifecycle_coordinator.create_project(
            setup_detector_callback=self.setup_detector,
            set_active_weight_callback=self.set_active_weight,
            set_openvino_usage_callback=self.set_openvino_usage,
            update_openvino_status_callback=self.update_openvino_status,
            get_active_weight_name=lambda: self.active_weight_name,
            get_use_openvino=lambda: self.use_openvino,
            apply_wizard_overrides_callback=self._apply_wizard_detector_overrides,
            **wizard_data
        )

    def _apply_wizard_detector_overrides(self, wizard_metadata: dict) -> None:
        """Apply detector parameter overrides captured during the wizard flow."""
        if not wizard_metadata:
            return

        detector_params = wizard_metadata.get("detector_parameters")
        if not isinstance(detector_params, dict):
            log.debug(
                "controller.wizard.detector_params.skipped",
                reason="metadata_missing_or_invalid",
            )
            return

        normalized_params: dict[str, float] = {}
        for key in ("confidence_threshold", "nms_threshold", "track_threshold", "match_threshold"):
            raw_value = detector_params.get(key)
            if raw_value is None:
                continue
            try:
                normalized_params[key] = float(raw_value)
            except (TypeError, ValueError):
                log.warning(
                    "controller.wizard.detector_params.invalid_value",
                    key=key,
                    value=raw_value,
                )

        if not normalized_params:
            return

        try:
            success = self.ui_state_controller.update_detector_parameters(normalized_params, scope="project")
        except Exception as exc:  # pragma: no cover - defensive guard
            log.warning(
                "controller.wizard.detector_params.apply_failed",
                error=str(exc),
                params=normalized_params,
                exc_info=True,
            )
            return

        event_name = (
            "controller.wizard.detector_params.applied"
            if success
            else "controller.wizard.detector_params.no_change"
        )
        log.info(event_name, params=normalized_params)

    def _restore_detector_settings(self, saved_detector_config: dict) -> None:
        """
        Restore detector settings from saved configuration.

        Phase 3: Delegates to HardwareCoordinator.

        Args:
            saved_detector_config: Saved detector configuration from project
        """
        self.hardware_coordinator.restore_detector_settings(saved_detector_config)

    def setup_detector(self, temp_animal_method: str | None = None) -> bool:
        """
        Initialize the detector instance based on the animal method selection.

        Phase 3: Delegates to HardwareCoordinator.

        Args:
            temp_animal_method: Temporary override for animal detection method
                ('det' or 'seg'). If None, uses global self.settings.
        """
        success, _ = self.hardware_coordinator.setup_detector(
            animal_method=temp_animal_method,
            use_openvino=self.use_openvino,
            active_weight_name=self.active_weight_name,
        )
        return success

    def setup_arduino(self) -> bool:
        """Ensure the Arduino connection is ready when the project requests it.

        Task 2.2: Delegates to HardwareCoordinator.
        """
        success = self.hardware_coordinator.setup_arduino()
        # Sync arduino references
        self.arduino = self.hardware_coordinator.arduino
        self.arduino_manager = self.hardware_coordinator.arduino_manager
        return success

    def _safe_get_default_weight(self) -> tuple[str | None, dict | None]:
        manager = getattr(self, "weight_manager", None)
        if manager is None:
            return None, None
        try:
            result = manager.get_default_weight()
        except (FileNotFoundError, OSError, KeyError, ValueError) as e:
            # Expected errors: weight file not found, I/O issues, malformed config
            log.warning("controller.default_weight.safe_get_failed", error=str(e), exc_info=True)
            return None, None
        if isinstance(result, tuple):
            if not result:
                return None, None
            if len(result) == 1:
                return result[0], None
            return result[0], result[1]
        if result:
            return result, None
        return None, None

    def get_all_weight_names(self) -> list:
        """
        Get all available weight names.

        Phase 2.4: Delegates to ModelService for consistency.
        """
        return self.model_service.get_all_weight_names()

    def classify_weight_type(self, filename: str) -> str | None:
        """Classify weight type from filename - delegates to weight manager."""
        return self.weight_manager._classify_weight_type(filename)

    def are_project_overrides_active(self) -> bool:
        """Whether project overrides are currently active."""
        return self.project_lifecycle_coordinator.are_project_overrides_active()

    def get_global_model_defaults(self) -> dict:
        """Get global model default settings.

        Phase 2.4: Now reads from StateManager as single source of truth.

        Returns:
            Dictionary with 'active_weight' and 'use_openvino' keys.
        """
        detector_state = self.state_manager.get_detector_state()
        return {
            "active_weight": detector_state.active_weight_name or None,
            "use_openvino": detector_state.use_openvino,
        }

    def _get_project_data_dict(self) -> dict:
        project_data = getattr(self.project_manager, "project_data", None)
        if not isinstance(project_data, dict):
            project_data = {} if not project_data else dict(project_data)
            self.project_manager.project_data = project_data
        return project_data

    def get_current_detector_parameters(self) -> dict[str, float]:
        """
        Return detector thresholds, falling back to saved or default values.

        Phase 3: Delegates to HardwareCoordinator.

        Returns parameters with long-form names for backward compatibility.
        """
        params = self.hardware_coordinator.get_detector_parameters()
        # Normalize conf_threshold to confidence_threshold for backward compatibility
        if "conf_threshold" in params:
            params["confidence_threshold"] = params.pop("conf_threshold")
        return params

    def get_factory_detector_parameters(self) -> dict[str, float]:
        """
        Return detector thresholds defined in config.yaml without overrides.

        Phase 3: Delegates to HardwareCoordinator.

        Returns parameters with long-form names for backward compatibility.
        """
        params = self.hardware_coordinator.get_factory_detector_parameters()
        # Normalize conf_threshold to confidence_threshold for backward compatibility
        if "conf_threshold" in params:
            params["confidence_threshold"] = params.pop("conf_threshold")
        return params

    @contextmanager
    def start_live_camera_analysis(self, camera_index: int | None = None):
        """Start a live camera analysis session.

        Phase 3: Delegate to SessionCoordinator.

        Args:
            camera_index: Optional camera index. If provided, uses this camera directly
                         without showing the configuration dialog. If None, shows dialog.
        """
        self.session_coordinator.start_live_camera_analysis(camera_index=camera_index)
        yield

    def cancel_current_analysis(self) -> None:
        """Request cancellation for the currently running analysis workflow."""
        worker_running = bool(self.processing_worker and self.processing_worker.is_running)
        thread_running = bool(self.processing_thread and self.processing_thread.is_alive())

        if not worker_running and not thread_running:
            log.info("controller.analysis.cancel_ignored", reason="no_active_processing")
            return

        log.info("controller.analysis.cancel_requested")
        self.cancel_event.set()

        self.state_manager.update_processing_state(
            source="controller.cancel_current_analysis",
            cancel_requested=True,
        )

        # Provide immediate feedback to the user interface
        self.ui_coordinator.set_status(None, "Cancelando análise em andamento...") # Phase 4
        if self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_UPDATE_BUTTON_STATE,
                {"button_name": "cancel_processing", "state": "disabled"},
            )
        else:
            self.ui_coordinator.update_view(
                None, # Phase 4
                "update_button_state",
                "cancel_processing",
                "disabled",
            )

        self.ui_state_controller._show_cancel_feedback()

        def _await_shutdown() -> None:
            """Wait for the worker (or legacy thread) to acknowledge cancellation."""
            try:
                finished = True
                if self.processing_worker and self.processing_worker.is_running:
                    finished = self.processing_worker.cancel()
                elif self.processing_thread and self.processing_thread.is_alive():
                    self.processing_thread.join(timeout=5.0)
                    finished = not self.processing_thread.is_alive()

                if not finished:
                    log.warning("controller.analysis.cancel_wait_timeout")
            except RuntimeError as e:  # pragma: no cover - defensive
                # Expected error: thread already stopped or joined
                log.error("controller.analysis.cancel_failed", error=str(e), exc_info=True)
            finally:
                if self.processing_thread and not self.processing_thread.is_alive():
                    self.processing_thread = None

        threading.Thread(target=_await_shutdown, name="CancelAnalysisJoin", daemon=True).start()

    def start_single_video_workflow(self, video_path: Path | str, config: dict):
        """Prepare the UI for zone definition in the single video workflow."""
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        log.info("workflow.single_video.setup_start", video=str(video_path))

        self.project_manager.set_active_zone_video(str(video_path))

        # Use detection methods from config if provided, otherwise fall back to
        # global settings
        animal_method = config.get("animal_method", self.settings.model_selection.animal_method)
        animals_per_aquarium = config.get("animals_per_aquarium", 1)

        # Apply OpenVINO setting from config
        use_openvino = config.get("use_openvino", self.settings.model_selection.use_openvino)
        self.use_openvino = use_openvino
        log.info("controller.single_video.openvino_set", use_openvino=use_openvino)

        if animal_method == "det" and animals_per_aquarium != 1:
            if self.ui_event_bus:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Configuração Inválida",
                        "message": "O modo de detecção (det) para animais só é compatível com 1 "
                        f"animal por aquário.\n"
                        f"Configuração atual: {animals_per_aquarium} "
                        "animais por aquário.\n\n"
                        "Para usar múltiplos animais por aquário, altere o método de "
                        "detecção de animais para 'seg' (segmentação) nas configurações.",
                    },
                )
            return

        # Ensure the detector is set up before showing the UI that needs it.
        # This is crucial for the single video flow.
        if not self.detector:
            log.info("controller.single_video.setup_detector")
            # Pass the animal method from config to setup detector with temporary
            # override
            temp_animal_method = config.get("animal_method")
            if not self.setup_detector(temp_animal_method):
                # setup_detector shows its own error message
                return

        # The processing logic has been moved to a new method.
        # This function now only delegates to the UI to prepare the drawing screen.
        self.ui_event_bus.publish_event(
            "ui:setup_zone_definition_for_single_video",
            {"video_path": video_path, "config": config},
        )

    def _handle_mixed_data_scenario(self, scanned_videos: list[dict]) -> list[dict] | None:
        """
        Handle the scenario where some videos have data and some do not.

        Sprint 13: Extracted from start_project_processing_workflow().
        Handles user interaction for deciding which videos to process.

        Args:
            scanned_videos: List of scanned video info dictionaries

        Returns:
            list[dict] | None: Videos to process, or None if all should be skipped/added only
        """
        return self.dialog_coordinator.handle_mixed_data_scenario(
            scanned_videos, self.project_manager, view=None # Phase 4
        )

    def generate_parquet_summaries(self, video_paths: list[str]) -> None:
        """Regera arquivos de sumário em Parquet para os vídeos selecionados.

        Phase 3: Delegates to ProcessingCoordinator.
        """
        # Convert paths to dict objects required by generator
        target_videos = [{"path": p} for p in video_paths]
        self.processing_coordinator.generate_parquet_summaries(
            target_videos,
            settings_obj=self.settings,
            on_complete=lambda msg: self.ui_event_bus.publish_event(Events.UI_SET_STATUS, {"message": msg})
        )

    def _run_tracking_if_needed(
        self,
        video_path: Path | str,
        results_dir: str,
        experiment_id: str,
        progress_callback=None,
        calibration_data: dict | None = None,
        analysis_interval_frames: int = 10,
        display_interval_frames: int = 10,
    ) -> tuple[bool, list | None]:
        """Delegate to VideoProcessingService.run_tracking_if_needed.

        Phase 3: Refactored to delegate to service layer.
        Injects current detector state before delegating.
        """
        # Inject current detector state into service
        self.video_processing_service.detector = self.detector
        return self.video_processing_service.run_tracking_if_needed(
            video_path=video_path,
            results_dir=results_dir,
            experiment_id=experiment_id,
            progress_callback=progress_callback,
            calibration_data=calibration_data,
            analysis_interval_frames=analysis_interval_frames,
            display_interval_frames=display_interval_frames,
        )

    def _prepare_zone_data_for_tracking(
        self, frame_width: int, frame_height: int
    ) -> tuple[ZoneData, list[list[int]]]:
        """Ensure zone data is ready for tracking and inform plugins."""
        assert self.detector is not None

        zone_data = self.project_manager.get_zone_data()
        if not zone_data.polygon:
            log.warning("controller.tracking.no_arena_defined.using_default")
            zone_data.polygon = [
                [0, 0],
                [frame_width, 0],
                [frame_width, frame_height],
                [0, frame_height],
            ]

        arena_polygon = zone_data.polygon

        self.detector.set_zones(zone_data, frame_width, frame_height)

        if self.detector:
            has_aquarium = bool(zone_data and zone_data.polygon)
            self.detector.set_aquarium_region_defined(has_aquarium)
            log.info(
                "controller.tracking.aquarium_status",
                defined=has_aquarium,
                plugin=self.detector.plugin.get_name(),
            )

        return zone_data, arena_polygon

    def _tracking_cancelled(self, experiment_id: str, frame_num: int, log_key: str) -> bool:
        """Handle cancel-event checks during tracking loop."""
        if not self.cancel_event.is_set():
            return False

        log.info(log_key, frame=frame_num, video=experiment_id)
        return True

    @contextmanager
    def _build_metadata_context(
        self,
        *,
        video_info: dict,
        single_video_config: dict | None,
        experiment_id: str,
        video_path: str,
    ) -> dict | None:
        if single_video_config:
            return None

        metadata_context = dict(video_info.get("metadata") or {})
        try:
            derived_metadata = self.project_manager.derive_processing_metadata(
                experiment_id,
                video_path,
            )
            metadata_context.update(derived_metadata)
        # pragma: no cover - defensive fallback
        except (KeyError, ValueError, FileNotFoundError) as e:
            # Expected errors: malformed metadata, invalid values, missing project file
            log.debug(
                "controller.processing.metadata_derive_failed",
                experiment=experiment_id,
                video_path=video_path,
                error=str(e),
            )

        return metadata_context

    def _prepare_calibration_context(
        self,
        *,
        arena_polygon_px: list,
        width_cm: float | None,
        height_cm: float | None,
        zone_data: ZoneData,
    ) -> tuple[
        Calibration | None,
        list[tuple[float, float]] | None,
        list[ROI],
        dict[str, tuple[int, int, int]],
        float | None,
        float | None,
    ]:
        """Delegate to VideoProcessingService._prepare_analysis_calibration_context.

        Phase 3: Refactored to delegate to service layer.
        """
        return self.video_processing_service._prepare_analysis_calibration_context(
            arena_polygon_px=arena_polygon_px,
            width_cm=width_cm,
            height_cm=height_cm,
            zone_data=zone_data,
        )

    def _generate_reports_for_video(
        self,
        *,
        reporter: Reporter,
        experiment_id: str,
        results_dir: str,
        progress_callback,
        cancel_event: threading.Event | None = None,
    ) -> tuple[str, str, str] | None:
        """Delegate to VideoProcessingService._generate_reports_for_video.

        Phase 3: Refactored to delegate to service layer.
        """
        return self.video_processing_service._generate_reports_for_video(
            reporter=reporter,
            experiment_id=experiment_id,
            results_dir=results_dir,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

    def _run_analysis_pipeline(
        self,
        *,
        experiment_id: str,
        video_path: str,
        results_dir: str,
        arena_polygon_px: list | None,
        metadata_context: dict | None,
        single_video_config: dict | None,
        progress_callback,
        analysis_profile: dict | None,
    ) -> bool:
        """Delegate to VideoProcessingService._run_analysis_pipeline.

        Phase 3: Refactored to delegate to service layer.
        Injects current detector state before delegating.
        """
        # Inject current detector state into service
        self.video_processing_service.detector = self.detector

        success = self.video_processing_service._run_analysis_pipeline(
            experiment_id=experiment_id,
            video_path=video_path,
            results_dir=results_dir,
            arena_polygon_px=arena_polygon_px,
            metadata_context=metadata_context,
            single_video_config=single_video_config,
            progress_callback=progress_callback,
            analysis_profile=analysis_profile,
        )

        # After analysis, refresh project views which service can't do
        if success:
            self.refresh_project_views(
                reason="processing_progress",
                append_summary=True,
            )

        return success

    def _process_single_video(
        self,
        *,
        index: int,
        total_videos: int,
        video_info: dict,
        single_video_config: dict | None,
        analysis_interval_frames: int,
        display_interval_frames: int,
        output_base_dir: str,
        experiment_id: str,
        metadata_context: dict | None,
        analysis_profile: dict | None,
    ) -> tuple[bool, str | None]:
        """Delegate to VideoProcessingService.process_single_video.

        Phase 3: Refactored to delegate to service layer.
        Injects current detector/recorder state before delegating.
        """
        # Inject current state into service
        self.video_processing_service.detector = self.detector
        self.video_processing_service.recorder = self.recorder
        self.video_processing_service.cancel_event = self.cancel_event

        # Apply temporary single-animal mode if configured
        with self._temporary_single_animal_mode(single_video_config):
            success, results_dir = self.video_processing_service.process_single_video(
                index=index,
                total_videos=total_videos,
                video_info=video_info,
                single_video_config=single_video_config,
                analysis_interval_frames=analysis_interval_frames,
                display_interval_frames=display_interval_frames,
                output_base_dir=output_base_dir,
                experiment_id=experiment_id,
                metadata_context=metadata_context,
                analysis_profile=analysis_profile,
            )

            # After processing, call refresh_project_views which service can't do
            if success:
                self.refresh_project_views(
                    reason="processing_progress",
                    append_summary=True,
                )

            return success, results_dir

    def apply_project_settings_to_batch(self, videos: list):
        """Aplica configurações do projeto a novos vídeos."""
        if not self.project_manager.project_path:
            log.warning("controller.batch.no_project_path")
            return False

        # Obtém configurações do projeto
        project_data = self.project_manager.project_data
        zone_data = self.project_manager.get_zone_data()
        calibration = project_data.get("calibration", {})

        log.info(
            "controller.batch.apply_settings",
            videos_count=len(videos),
            has_zones=bool(zone_data and zone_data.polygon),
            has_calibration=bool(calibration),
            has_rois=len(zone_data.roi_polygons) if zone_data else 0,
        )

        # Para cada vídeo no lote
        settings_applied = 0
        for video_info in videos:
            video_path = video_info.get("path")
            if not video_path:
                continue

            experiment_id = os.path.splitext(os.path.basename(video_path))[0]
            results_path = self.project_manager.resolve_results_directory(
                experiment_id,
                video_path=video_path,
            )

            try:
                self._prepare_results_directory(str(results_path))

                # Salva configurações completas do projeto
                settings_file = results_path / "project_settings.json"
                settings_data = {
                    "project_name": self.project_manager.get_project_name(),
                    "active_weight": project_data.get("active_weight"),
                    "use_openvino": project_data.get("use_openvino", False),
                    "calibration": calibration,
                    "video_settings": video_info,
                    "timestamp": self.project_manager.project_data.get("timestamp"),
                    "analysis_interval_frames": project_data.get("analysis_interval_frames", 10),
                    "display_interval_frames": project_data.get("display_interval_frames", 10),
                    "detector_config": self.project_manager.get_detector_state(),
                }

                import json

                with open(settings_file, "w") as f:
                    json.dump(settings_data, f, indent=2)

                # Salva zonas no diretório de resultados
                if zone_data and (zone_data.polygon or zone_data.roi_polygons):
                    zones_file = results_path / "zones.json"

                    from dataclasses import asdict

                    with open(zones_file, "w") as f:
                        json.dump(asdict(zone_data), f, indent=2)

                    log.info(
                        "controller.batch.zones_saved",
                        video=experiment_id,
                        zones_file=str(zones_file),
                        settings_file=settings_file,
                    )

                settings_applied += 1

            except Exception as e:
                log.error(
                    "controller.batch.settings_save_error",
                    video=experiment_id,
                    error=str(e),
                )

        log.info(
            "controller.batch.settings_applied",
            total_videos=len(videos),
            successful=settings_applied,
        )

        return settings_applied == len(videos)

    def _prepare_results_directory(self, results_dir: str) -> None:
        """Delegate to VideoProcessingService._prepare_results_directory.

        Phase 3: Refactored to delegate to service layer.
        """
        self.video_processing_service._prepare_results_directory(results_dir)

    def _process_videos(
        self,
        videos_to_process: list[dict],
        output_base_dir: str,
        single_video_config: dict | None = None,
    ):
        """
        Private helper to process a list of videos and save results.

        This is designed to be run in a background thread.
        Phase 3: Delegates batch processing orchestration to AnalysisService.
        """
        log.info("controller.processing.start_delegating", count=len(videos_to_process))

        # Delegate to AnalysisService for batch processing orchestration
        with self._temporary_single_animal_mode(single_video_config) as _:
            self.analysis_service.process_videos_batch(
                videos_to_process=videos_to_process,
                output_base_dir=output_base_dir,
                single_video_config=single_video_config,
                controller=self,
                cancel_event=self.cancel_event,
                project_manager=self.project_manager,
                root_tk=self.root,
            )

    def generate_report(self, videos: list[dict], report_type: str = "unified"):
        """Generate a report from a list of processed videos.

        Phase 3: Delegates to AnalysisService, handling UI interaction for path.
        Phase 4: Use DialogCoordinator for file dialog.
        """
        # Ask for save path via DialogCoordinator (Phase 4)
        output_path = self.dialog_coordinator.ask_save_filename(
            title="Salvar Relatório",
            defaultextension=".docx",
            initialfile="project_report.docx",
            filetypes=[("Word Documents", "*.docx")]
        )

        if not output_path:
            return

        # Delegate generation to service
        success = self.analysis_service.generate_report(
            videos,
            report_type,
            output_path,
            project_manager=self.project_manager
        )

        if success:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {"title": "Sucesso", "message": f"Relatório salvo em:\n{output_path}"}
            )
        else:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro", "message": "Falha ao gerar relatório. Verifique os logs."}
            )


# -----------------------------------------------------------------------------
# Backward Compatibility Alias (Phase 1, Step 3)
# -----------------------------------------------------------------------------
# Maintain backward compatibility during migration.
# All existing code can continue importing AppController.
# New code should prefer MainViewModel for clarity.

AppController = MainViewModel
