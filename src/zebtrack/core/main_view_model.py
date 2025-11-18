"""Main application view model orchestrating the ZebTrack-AI application.

Coordinates all core services, manages application state, handles user interactions,
and orchestrates video processing workflows with dependency injection.
"""

from __future__ import annotations

import glob
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from zebtrack.settings import Settings

import structlog

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.analysis.reporter import Reporter
from zebtrack.analysis.roi import ROI

# Task 2.2: Coordinator imports (REFACTOR-VIEWMODEL-001)
from zebtrack.core.analysis_coordinator import AnalysisCoordinator
from zebtrack.core.calibration import Calibration
from zebtrack.core.detector import Detector, ZoneData
from zebtrack.core.detector_service import DetectorService
from zebtrack.core.hardware_coordinator import HardwareCoordinator
from zebtrack.core.model_service import ModelService
from zebtrack.core.processing_mode import ProcessingMode, ProcessingReport
from zebtrack.core.processing_worker import (
    ProcessingCallbacks,
    ProcessingContext,
    ProcessingWorker,
)
from zebtrack.core.project_manager import AssetType, ProjectManager
from zebtrack.core.project_service import ProjectService
from zebtrack.core.project_workflow_service import ProjectWorkflowService
from zebtrack.core.recording_service import RecordingService
from zebtrack.core.state_manager import StateCategory, StateManager
from zebtrack.core.ui_coordinator import UICoordinator
from zebtrack.core.video_orchestrator import VideoOrchestrator
from zebtrack.core.video_processing_service import VideoProcessingService
from zebtrack.core.weight_manager import WeightManager
from zebtrack.io.arduino import Arduino
from zebtrack.io.arduino_manager import ArduinoManager
from zebtrack.io.recorder import Recorder
from zebtrack.orchestrators.analysis_orchestrator import AnalysisOrchestrator
from zebtrack.orchestrators.calibration_orchestrator import CalibrationOrchestrator
from zebtrack.orchestrators.model_diagnostics_orchestrator import ModelDiagnosticsOrchestrator
from zebtrack.orchestrators.processing_config_orchestrator import ProcessingConfigOrchestrator
from zebtrack.orchestrators.project_orchestrator import ProjectOrchestrator
from zebtrack.orchestrators.recording_session_orchestrator import RecordingSessionOrchestrator
from zebtrack.orchestrators.ui_state_controller import UIStateController
from zebtrack.orchestrators.video_processing_orchestrator import VideoProcessingOrchestrator
from zebtrack.orchestrators.zone_arena_orchestrator import ZoneArenaOrchestrator
from zebtrack.ui.event_bus import EventBus
from zebtrack.ui.events import Events
from zebtrack.ui.gui import ApplicationGUI
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
        root,
        event_bus: EventBus | None,
        state_manager: StateManager,
        ui_coordinator: UICoordinator,
        settings_obj: Settings,
        project_manager: ProjectManager,
        project_workflow_service: ProjectWorkflowService,
        weight_manager: WeightManager,
        model_service: ModelService,
        detector_service: DetectorService,
        video_processing_service: VideoProcessingService,
        analysis_service: AnalysisService | None = None,
        recording_service: RecordingService | None = None,
        live_camera_service=None,
        hardware_coordinator: HardwareCoordinator | None = None,
        analysis_coordinator: AnalysisCoordinator | None = None,
        video_orchestrator: VideoOrchestrator | None = None,
        project_coordinator=None,  # Sprint 3: Project lifecycle coordinator
        recording_coordinator=None,  # Sprint 4: Recording workflow coordinator
        live_camera_coordinator=None,  # Sprint 4: Live camera coordinator
        detector_coordinator=None,  # Sprint 5: Detector setup coordinator
        processing_coordinator=None,  # Sprint 6: Video processing coordinator
        view=None,  # Phase 2: ApplicationGUI instance (optional - will be created if None)
        test_sync_event: threading.Event | None = None,
    ):
        """Initialize MainViewModel with dependency injection.

        Args:
            root: Tkinter root window
            event_bus: Event bus for UI events
            state_manager: Centralized state manager
            ui_coordinator: UI coordinator for scheduling
            settings_obj: Settings instance (injected)
            project_manager: Project manager
            project_workflow_service: Project workflow service
            weight_manager: Weight manager
            model_service: Model service
            detector_service: Detector service
            video_processing_service: Video processing service
            analysis_service: Analysis service (optional, will be created if None)
            recording_service: Recording service (optional, will be created later)
            live_camera_service: Live camera service (optional)
            hardware_coordinator: Hardware coordinator (Phase 2, optional - created if None)
            analysis_coordinator: Analysis coordinator (Phase 2, optional - created if None)
            video_orchestrator: Video orchestrator (Phase 2, optional - created if None)
            project_coordinator: Project coordinator (Sprint 3, optional)
            recording_coordinator: Recording coordinator (Sprint 4, optional - created if None)
            live_camera_coordinator: Live camera coordinator (Sprint 4, optional - created if None)
            detector_coordinator: Detector coordinator (Sprint 5, optional - created if None)
            processing_coordinator: Processing coordinator (Sprint 6, optional - created if None)
            test_sync_event: Test synchronization event (for tests only)
        """
        self.root = root
        self.settings = settings_obj

        # Test synchronization support (Phase 1.1)
        self._test_sync_event = test_sync_event

        # Phase 2, Step 4: Injected dependencies
        self.state_manager = state_manager
        self.project_manager = project_manager
        self.weight_manager = weight_manager
        self.model_service = model_service
        self.detector_service = detector_service
        self.video_processing_service = video_processing_service
        self.project_workflow_service = project_workflow_service
        self.ui_coordinator = ui_coordinator
        # Ensure coordinator attributes exist before orchestrators access them
        self.recording_coordinator = recording_coordinator

        # Live camera service will be initialized after recording_service
        self._live_camera_service_param = live_camera_service

        # Register test observer if sync event provided
        if self._test_sync_event is not None:
            self.state_manager.subscribe_all(self._on_state_change_for_test)

        # Service layer dependencies (Phase 1, Step 3)
        self.project_service = ProjectService()
        self.analysis_service = (
            analysis_service
            if analysis_service is not None
            else AnalysisService(settings_obj=self.settings)
        )

        # Sprint 12: Helper services for processing workflows
        from zebtrack.core.video_classification_service import VideoClassificationService
        from zebtrack.core.video_selection_service import VideoSelectionService
        from zebtrack.core.video_validation_service import VideoValidationService

        self.video_classification_service = VideoClassificationService()
        self.video_selection_service = VideoSelectionService()
        self.video_validation_service = VideoValidationService()

        # New state variables for model management (must exist before view)
        default_weight, _ = self._safe_get_default_weight()
        if isinstance(default_weight, str):
            self.active_weight_name = default_weight
        elif default_weight is None:
            self.active_weight_name = ""
            log.warning("controller.init.no_default_weight")
        else:
            self.active_weight_name = ""
            log.warning(
                "controller.init.default_weight.invalid_type",
                received_type=type(default_weight).__name__,
            )

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

        # Recording service (Phase 2.2) - will be fully initialized after arduino_manager
        self._recording_service: RecordingService | None = None
        self.recording_service = recording_service
        self.recording_session_orchestrator: RecordingSessionOrchestrator | None = None

        # Live camera service - initialized later or from parameter
        self.live_camera_service = None

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

        # Phase 2: Inversion of Control - view can be injected or created
        if view is not None:
            # View was injected (testable pattern)
            self.view = view
        else:
            # Create view after core state is ready so it can reflect it (legacy pattern)
            self.view = ApplicationGUI(
                root,
                self,
                event_bus=self.ui_event_bus if self._use_event_bus else None,
                settings_obj=self.settings,
            )

        # Update GPU hardware display in UI (Phase 7)
        # Only call if view was created internally (has update method)
        if hasattr(self.view, "update_gpu_hardware_display"):
            self.view.update_gpu_hardware_display(hardware_summary)

        # Update OpenVINO status if it was recommended but not available due to missing conversion
        if recommended_backend == "openvino" and not self.use_openvino:
            if hasattr(self.view, "update_openvino_status_display"):
                self.view.update_openvino_status_display(
                    "Recomendado mas modelo não convertido. Use 'Diagnóstico' para converter."
                )

        # Initialize core threading primitives first
        self.program_exit_event = threading.Event()
        self.processing_thread: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.pending_single_video_analysis = None
        self.processing_worker: ProcessingWorker | None = None
        self._cancel_feedback_displayed = False

        # Orchestrators that must exist before service initialization
        if self.recording_session_orchestrator is None:
            self.recording_session_orchestrator = RecordingSessionOrchestrator(self)

        # Initialize services (Phase 2.2 + Phase 3 + Phase 7.2)
        # Recording service initialization (setup callbacks if service was injected)
        if self.recording_service is None:
            # Create recording service if not injected (for backward compatibility)
            self._init_recording_service()
        else:
            # Service was injected, just setup UI callbacks
            self._setup_recording_service_callbacks()

        # Phase 4: Subscribe to StateManager changes for MVVM flow
        self.state_manager.subscribe(StateCategory.PROJECT, self._on_project_state_changed)
        self.state_manager.subscribe(StateCategory.DETECTOR, self._on_detector_state_changed)
        self.state_manager.subscribe(StateCategory.RECORDING, self._on_recording_state_changed)
        self.state_manager.subscribe(StateCategory.PROCESSING, self._on_processing_state_changed)

        # NOTE: bind_events() foi movido para __main__.py na FASE 1
        # NÃO chamar self.bind_events() aqui para evitar dupla inscrição

        # Task 2.2/2.3: Initialize or use injected coordinators (REFACTOR-VIEWMODEL-001)
        self._init_coordinators(
            hardware_coordinator=hardware_coordinator,
            analysis_coordinator=analysis_coordinator,
            video_orchestrator=video_orchestrator,
            recording_coordinator=recording_coordinator,
            live_camera_coordinator=live_camera_coordinator,
            detector_coordinator=detector_coordinator,
            processing_coordinator=processing_coordinator,
            project_coordinator=project_coordinator,  # Sprint 11: Fix missing parameter
        )

        self._publish_processing_mode(source="init", force=True)

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
        hardware_coordinator: HardwareCoordinator | None,
        analysis_coordinator: AnalysisCoordinator | None,
        video_orchestrator: VideoOrchestrator | None,
        recording_coordinator=None,
        live_camera_coordinator=None,
        detector_coordinator=None,
        processing_coordinator=None,
        project_coordinator=None,  # Sprint 11: Added missing parameter
    ) -> None:
        """
        Initialize coordinators for hardware, video, analysis, recording, live camera,
        detector, and processing.

        Sprint 16: Simplified using _inject_or_create() helper.
        Task 2.2: REFACTOR-VIEWMODEL-001
        Task 2.3: Accept injected coordinators or create them for backward compatibility
        Sprint 4: Added recording_coordinator and live_camera_coordinator
        Sprint 5: Added detector_coordinator
        Sprint 6: Added processing_coordinator
        """
        # Hardware coordinator (detector, Arduino, zones)
        self._inject_or_create(
            "hardware_coordinator",
            hardware_coordinator,
            lambda: HardwareCoordinator(
                state_manager=self.state_manager,
                ui_event_bus=self.ui_event_bus,
                settings_obj=self.settings,
                project_manager=self.project_manager,
                detector_service=self.detector_service,
                arduino_manager_cls=self._arduino_manager_cls,
            ),
        )

        # Video orchestrator (batch processing, video workflows)
        self._inject_or_create(
            "video_orchestrator",
            video_orchestrator,
            lambda: VideoOrchestrator(
                root=self.root,
                state_manager=self.state_manager,
                ui_event_bus=self.ui_event_bus,
                ui_coordinator=self.ui_coordinator,
                settings_obj=self.settings,
                project_manager=self.project_manager,
                video_processing_service=self.video_processing_service,
                analysis_service=self.analysis_service,
                recorder=self.recorder,
            ),
        )
        self.video_orchestrator.set_view(self.view)

        # Analysis coordinator (reports, summaries, analysis pipeline)
        self._inject_or_create(
            "analysis_coordinator",
            analysis_coordinator,
            lambda: AnalysisCoordinator(
                root=self.root,
                ui_event_bus=self.ui_event_bus,
                ui_coordinator=self.ui_coordinator,
                settings_obj=self.settings,
                project_manager=self.project_manager,
                analysis_service=self.analysis_service,
                video_processing_service=self.video_processing_service,
            ),
        )
        self.analysis_coordinator.set_view(self.view)

        # Project coordinator (Sprint 3: project lifecycle workflows)
        if project_coordinator is not None:
            self.project_coordinator = project_coordinator
            log.info("main_view_model.project_coordinator.injected")
        else:
            # If not injected, create lazily when needed (backward compatibility)
            self.project_coordinator = None
            log.warning(
                "main_view_model.project_coordinator.not_injected",
                message="ProjectCoordinator not injected - will use legacy workflow",
            )

        # Recording coordinator (Sprint 4: recording workflow orchestration)
        from zebtrack.coordinators.recording_coordinator import RecordingCoordinator

        self._inject_or_create(
            "recording_coordinator",
            recording_coordinator,
            lambda: RecordingCoordinator(
                state_manager=self.state_manager,
                recording_service=self.recording_service,
                arduino_manager=self.arduino_manager,
                event_bus=self.ui_event_bus,
            ),
        )

        # Live camera coordinator (Sprint 4: live camera analysis orchestration)
        from zebtrack.coordinators.live_camera_coordinator import LiveCameraCoordinator

        self._inject_or_create(
            "live_camera_coordinator",
            live_camera_coordinator,
            lambda: LiveCameraCoordinator(
                state_manager=self.state_manager,
                live_camera_service=self.live_camera_service,
                project_manager=self.project_manager,
                settings=self.settings,
                camera=None,  # Camera initialized lazily when needed
                event_bus=self.ui_event_bus,
            ),
        )

        # Detector coordinator (Sprint 5: detector setup and configuration)
        from zebtrack.coordinators.detector_coordinator import DetectorCoordinator

        self._inject_or_create(
            "detector_coordinator",
            detector_coordinator,
            lambda: DetectorCoordinator(
                state_manager=self.state_manager,
                detector_service=self.detector_service,
                model_service=self.model_service,
                weight_manager=self.weight_manager,
                event_bus=self.ui_event_bus,
            ),
        )

        # Processing coordinator (Sprint 6: video processing orchestration)
        from zebtrack.coordinators.processing_coordinator import ProcessingCoordinator

        self._inject_or_create(
            "processing_coordinator",
            processing_coordinator,
            lambda: ProcessingCoordinator(
                state_manager=self.state_manager,
                video_orchestrator=self.video_orchestrator,
                video_processing_service=self.video_processing_service,
                analysis_service=self.analysis_service,
                project_manager=self.project_manager,
                recorder_factory=self.recorder,
                event_bus=self.ui_event_bus,
            ),
        )

        # Project workflow adapter (P2-T2: project create/open/close workflows)
        self.project_workflow_adapter = ProjectWorkflowAdapter(
            project_workflow_service=self.project_workflow_service,
            project_manager=self.project_manager,
            detector_service=self.detector_service,
            state_manager=self.state_manager,
            ui_event_bus=self.ui_event_bus,
        )

        # Set callbacks for coordinators that need to call back to MainViewModel
        self.hardware_coordinator.set_recording_callbacks(
            self.trigger_recording, self.stop_recording
        )
        self.video_orchestrator.set_arena_callback(self.set_main_arena_polygon)
        self.video_orchestrator.set_analysis_view_mode_callback(self._activate_analysis_view_mode)
        self.video_orchestrator.set_refresh_callback(self.refresh_project_views)
        self.video_orchestrator.set_publish_processing_mode_callback(self._publish_processing_mode)
        self.analysis_coordinator.set_refresh_callback(self.refresh_project_views)

        log.info("main_view_model.coordinators_initialized")

        # Sprint 24: Video Processing Orchestrator
        self.video_processing_orchestrator = VideoProcessingOrchestrator(self)

        # Sprint 25: Analysis Orchestrator
        self.analysis_orchestrator = AnalysisOrchestrator(self)

        # Sprint 26: Recording Session Orchestrator
        if self.recording_session_orchestrator is None:
            self.recording_session_orchestrator = RecordingSessionOrchestrator(self)

        # Sprint 27: Project Orchestrator
        self.project_orchestrator = ProjectOrchestrator(self)

        # Sprint 28: UI State Controller
        self.ui_state_controller = UIStateController(self)

        # Sprint 29: Model Diagnostics Orchestrator
        self.model_diagnostics_orchestrator = ModelDiagnosticsOrchestrator(self)

        # Sprint 30: Zone Arena Orchestrator
        self.zone_arena_orchestrator = ZoneArenaOrchestrator(self)

        # Sprint 31: Processing Config Orchestrator
        self.processing_config_orchestrator = ProcessingConfigOrchestrator(self)

        # Sprint 32: Calibration Orchestrator
        self.calibration_orchestrator = CalibrationOrchestrator(self)

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
    def is_recording(self) -> bool:
        """Check if currently recording.

        Facade - delegates to RecordingSessionOrchestrator (Sprint 26).
        """
        return self.recording_session_orchestrator.is_recording

    @is_recording.setter
    def is_recording(self, value: bool) -> None:
        """Set recording state.

        Facade - delegates to RecordingSessionOrchestrator (Sprint 26).
        """
        self.recording_session_orchestrator.is_recording = value

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
            self.update_openvino_status()

    def _on_recording_state_changed(
        self, category: StateCategory, key: str, old_value, new_value
    ) -> None:
        """Handle recording state changes.

        Facade - delegates to RecordingSessionOrchestrator (Sprint 26).
        """
        return self.recording_session_orchestrator._on_recording_state_changed(
            category=category, key=key, old_value=old_value, new_value=new_value
        )

    def _on_processing_state_changed(
        self, category: StateCategory, key: str, old_value: Any, new_value: Any
    ):
        """Publica eventos de UI em resposta a mudanças no estado de Processamento."""
        if key == "is_processing":
            if new_value:  # Processamento iniciou
                self.ui_coordinator.update_view(self.view, "start_analysis_view_mode")
            else:  # Processamento terminou
                self.ui_coordinator.update_view(self.view, "stop_analysis_view_mode")
        elif key == "cancel_requested" and new_value:
            self._show_cancel_feedback()  # Mostrar feedback de cancelamento imediatamente

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
        if self.view.ask_ok_cancel("Sair", "Deseja realmente sair?"):
            if hasattr(self.view, "stop_event_bus_polling"):
                try:
                    self.view.stop_event_bus_polling()
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

    def _schedule_on_ui(self, func, *args, **kwargs):
        """Schedule a function to run on the UI thread.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller._schedule_on_ui(func, *args, **kwargs)

    def _setup_recording_service_callbacks(self) -> None:
        """Setup callbacks for recording service.

        Facade - delegates to RecordingSessionOrchestrator (Sprint 26).
        """
        return self.recording_session_orchestrator._setup_recording_service_callbacks()

    def _init_recording_service(self) -> None:
        """Initialize recording service.

        Facade - delegates to RecordingSessionOrchestrator (Sprint 26).
        """
        return self.recording_session_orchestrator._init_recording_service()

    # Phase 7.1: Generic event dispatcher mapping (consolidates 32 handlers into declarative config)
    _EVENT_METHOD_MAPPING: ClassVar[dict] = {
        # Recording events
        Events.RECORDING_START: ("start_recording", ["day", "group", "cobaia"], "kwargs_get"),
        Events.RECORDING_STOP: ("stop_recording", [], "no_params"),
        Events.RECORDING_TRIGGER: ("trigger_recording", ["event_code"], "kwargs_get"),
        # Project events
        Events.PROJECT_CREATE: ("create_project_workflow", None, "kwargs_all"),
        Events.WIZARD_CREATE_PROJECT: ("create_project_workflow", None, "kwargs_all"),
        Events.PROJECT_OPEN: ("open_project_workflow", ["project_path"], "positional"),
        Events.PROJECT_CLOSE: ("close_project", [], "no_params"),
        # Events.PROJECT_PROCESS_VIDEOS - Phase 2.3: Moved to VideoProcessingOrchestrator
        Events.PROJECT_GENERATE_SUMMARIES: (
            "generate_parquet_summaries",
            ["video_paths"],
            "positional",
        ),
        Events.PROJECT_APPLY_SETTINGS: (
            "apply_project_settings_to_batch",
            ["videos"],
            "positional",
        ),
        Events.PROJECT_DELETE_ASSET: (
            "delete_project_asset",
            ["video_path", "asset"],
            "positional",
        ),
        # Video processing events - Phase 2.3: Moved to VideoProcessingOrchestrator
        # Events.VIDEO_ANALYZE_SINGLE, VIDEO_START_SINGLE_PROCESSING, VIDEO_CANCEL_ANALYSIS
        # Events.PROJECT_PROCESS_VIDEOS - now handled by VideoProcessingOrchestrator
        # Model & weight events
        Events.MODEL_SET_WEIGHT: ("set_active_weight", ["name", "dialog"], "kwargs_get"),
        Events.MODEL_SET_OPENVINO: (
            "set_openvino_usage",
            ["use_openvino", "dialog"],
            "positional_optional",
        ),
        Events.MODEL_CONVERT_OPENVINO: (
            "convert_active_weight_to_openvino",
            ["dialog"],
            "kwargs_get",
        ),
        Events.MODEL_UPDATE_OPENVINO_STATUS: ("update_openvino_status", ["dialog"], "kwargs_get"),
        Events.MODEL_ADD_WEIGHT: (
            "add_new_weight",
            ["path", "set_as_default", "weight_type"],
            "positional_optional",
        ),
        Events.MODEL_DELETE_WEIGHT: ("delete_weight", ["name"], "positional"),
        Events.MODEL_RUN_DIAGNOSTIC: ("run_model_diagnostic", ["config"], "positional"),
        Events.MODEL_LOAD_NEW_WEIGHT: ("load_new_weight", [], "no_params"),
        Events.MODEL_MANAGE_WEIGHTS: ("manage_weights", [], "no_params"),
        # Detector & zone events
        Events.DETECTOR_SETUP: ("setup_detector", ["temp_animal_method"], "kwargs_get"),
        Events.DETECTOR_SETUP_ZONES: ("setup_detector_zones", [], "no_params"),
        Events.DETECTOR_UPDATE_PARAMETERS: (
            "update_detector_parameters",
            ["conf_threshold", "nms_threshold", "track_threshold", "match_threshold"],
            "kwargs_get",
        ),
        Events.ZONE_SET_ARENA_POLYGON: ("set_main_arena_polygon", ["points"], "positional"),
        Events.ZONE_SAVE_MANUAL_ARENA: ("save_manual_arena", ["polygon_points"], "positional"),
        Events.ZONE_UPDATE_ARENA: ("update_main_arena", ["polygon_points"], "positional"),
        Events.ZONE_AUTO_DETECT: (
            "run_aquarium_detection",
            ["video_path", "stabilization_frames"],
            "kwargs_get",
        ),
        Events.ZONE_APPLY_ROI_TEMPLATE: ("apply_roi_template", ["template"], "kwargs_get"),
        # Calibration events
        Events.CALIBRATION_RUN_LIVE: (
            "run_live_calibration",
            ["temp_aquarium_method"],
            "kwargs_get",
        ),
        Events.CALIBRATION_COPY_TO_PROJECT: (
            "copy_global_model_settings_to_project",
            [],
            "no_params",
        ),
        Events.CALIBRATION_SAVE_TO_PROJECT: (
            "save_current_calibration_to_project",
            [],
            "no_params",
        ),
        # Arduino events
        Events.ARDUINO_SETUP: ("setup_arduino", [], "no_params"),
        Events.ARDUINO_LOG_EVENT: ("log_arduino_event", ["message"], "positional"),
        # Report events
        Events.REPORT_GENERATE: (
            "generate_report",
            ["videos", "report_type"],
            "positional_optional",
        ),
        # Application events
        Events.APP_CLOSE: ("on_close", [], "no_params"),
    }

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
        """Subscribe to all UI→Controller events when event bus is enabled.

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

        log.info(
            "controller.register_event_handlers.complete", count=len(self._EVENT_METHOD_MAPPING) + 1
        )

    def _handle_setup_zone_definition_for_single_video(self, data: dict):
        """Handle the special single video zone definition event."""
        video_path = data.get("video_path")
        config = data.get("config")
        if video_path and config:
            self.view.setup_zone_definition_for_single_video(video_path, config)

    def _determine_processing_mode(self) -> ProcessingMode:
        """Inspect current detector/settings state to infer active mode.

        Facade - delegates to ProcessingConfigOrchestrator (Sprint 31).
        """
        return self.processing_config_orchestrator._determine_processing_mode()

    def _publish_processing_mode(
        self,
        *,
        source: str,
        force: bool = False,
        mode_override: ProcessingMode | None = None,
    ) -> ProcessingReport:
        """Notify the GUI about the current processing mode when it changes.

        Facade - delegates to ProcessingConfigOrchestrator (Sprint 31).
        """
        return self.processing_config_orchestrator._publish_processing_mode(
            source=source, force=force, mode_override=mode_override
        )

    def refresh_project_views(
        self,
        reason: str | None = None,
        *,
        append_summary: bool = False,
        immediate: bool = False,
    ) -> None:
        """Request a refresh of project-related UI components on the main thread.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller.refresh_project_views(
            reason=reason,
            append_summary=append_summary,
            immediate=immediate,
        )

    def _clear_external_trigger_wait(self) -> None:
        """Clear external trigger wait state.

        Facade - delegates to RecordingSessionOrchestrator (Sprint 26).
        """
        return self.recording_session_orchestrator._clear_external_trigger_wait()

    def log_arduino_event(self, message: str):
        """Task 2.2: Delegates to HardwareCoordinator."""
        self.hardware_coordinator.log_arduino_event(message)

    def on_arduino_status_change(self, connected: bool, port: str | None):
        """Task 2.2: Delegates to HardwareCoordinator."""
        self.hardware_coordinator.on_arduino_status_change(connected, port)

    def on_arduino_command_sent(self, command: int, success: bool, source: str):
        """Task 2.2: Delegates to HardwareCoordinator."""
        self.hardware_coordinator.on_arduino_command_sent(command, success, source)

    def on_arduino_event(self, event_code: int) -> None:
        """Handle Arduino event.

        Facade - delegates to RecordingSessionOrchestrator (Sprint 26).
        """
        return self.recording_session_orchestrator.on_arduino_event(event_code=event_code)

    def trigger_recording(self, event_code: int | None = None):
        """Trigger recording via external event.

        Facade - delegates to RecordingSessionOrchestrator (Sprint 26).
        """
        return self.recording_session_orchestrator.trigger_recording(event_code=event_code)

    def _schedule_recording(
        self,
        context: dict,
        project_data: dict,
        *,
        trigger_source: str,
    ) -> None:
        """Schedule recording after delay.

        Facade - delegates to RecordingSessionOrchestrator (Sprint 26).
        """
        return self.recording_session_orchestrator._schedule_recording(
            context=context,
            project_data=project_data,
            trigger_source=trigger_source,
        )

    def close_project(self) -> None:
        """Close current project.

        Facade - delegates to ProjectOrchestrator (Sprint 27).
        """
        return self.project_orchestrator.close_project()

    def create_project_workflow(self, **wizard_data):
        """Create new project workflow with backward-compatible signature."""
        return self.project_orchestrator.create_project_workflow(**wizard_data)

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
            success = self.update_detector_parameters(normalized_params, scope="project")
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

    def _show_post_creation_guide(self, wizard_metadata: dict):
        """Display a contextual onboarding message after project creation.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller._show_post_creation_guide(wizard_metadata=wizard_metadata)

    def _restore_detector_settings(self, saved_detector_config: dict) -> None:
        """
        Restore detector settings from saved configuration.

        Sprint 7: Delegates to DetectorCoordinator.

        Args:
            saved_detector_config: Saved detector configuration from project
        """
        self.detector_coordinator.restore_detector_settings(saved_detector_config)

    def _setup_zones_from_project(self):
        """Setup zones from project.

        Facade - delegates to ProjectOrchestrator (Sprint 27).
        """
        return self.project_orchestrator._setup_zones_from_project()

    def open_project_workflow(self, project_path: str | None = None):
        """Open existing project workflow.

        Facade - delegates to ProjectOrchestrator (Sprint 27).
        """
        return self.project_orchestrator.open_project_workflow(project_path=project_path)

    def setup_detector(self, temp_animal_method: str | None = None) -> bool:
        """
        Initialize the detector instance based on the animal method selection.

        Sprint 7: Delegates to DetectorCoordinator.

        Args:
            temp_animal_method: Temporary override for animal detection method
                ('det' or 'seg'). If None, uses global self.settings.
        """
        success, _ = self.detector_coordinator.setup_detector(
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

    def setup_detector_zones(self):
        """Load zone data from project and sets it on the detector instance.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller.setup_detector_zones()

    # --- New Methods for Weight Management ---

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

    def add_new_weight(
        self, path: Path | str, set_as_default: bool, weight_type: str | None = None
    ):
        """Add a new weight with type classification.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller.add_new_weight(
            path=path, set_as_default=set_as_default, weight_type=weight_type
        )

    def delete_weight(self, name: str):
        """Delete a model weight from the catalog.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller.delete_weight(name=name)

    def set_active_weight(self, name: str | None, dialog=None):
        """Set the active model weight and update UI accordingly.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller.set_active_weight(name=name, dialog=dialog)

    def manage_weights(self):
        """Open the weight management dialog.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller.manage_weights()

    def load_new_weight(
        self,
        filepath: Path | str | None = None,
        weight_type: str | None = None,
        choice: str | None = None,
    ):
        """Handle the 'Load New Weight' button click.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller.load_new_weight(
            filepath=filepath, weight_type=weight_type, choice=choice
        )

    def set_openvino_usage(self, use_openvino: bool, dialog=None):
        """Enable or disable OpenVINO inference mode.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller.set_openvino_usage(use_openvino=use_openvino, dialog=dialog)

    def convert_active_weight_to_openvino(self, dialog):
        """Convert the active weight to OpenVINO format.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller.convert_active_weight_to_openvino(dialog=dialog)

    def update_openvino_status(self, dialog=None):
        """Update the status label in the GUI based on the current state.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller.update_openvino_status(dialog=dialog)

    @property
    def are_project_overrides_active(self) -> bool:
        """Whether project overrides are currently active."""
        return self.project_orchestrator.are_project_overrides_active()

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

    def _ensure_project_overrides_record(self) -> dict:
        """Ensure project overrides record exists.

        Facade - delegates to ProjectOrchestrator (Sprint 27).
        """
        return self.project_orchestrator._ensure_project_overrides_record()

    def has_project_override_settings(self) -> bool:
        """Check if project has override settings.

        Facade - delegates to ProjectOrchestrator (Sprint 27).
        """
        return self.project_orchestrator.has_project_override_settings()

    def get_calibration_scope_info(self) -> dict:
        """Get calibration scope information for UI display.

        Facade - delegates to CalibrationOrchestrator (Sprint 32).
        """
        return self.calibration_orchestrator.get_calibration_scope_info()

    def get_current_detector_parameters(self) -> dict[str, float]:
        """
        Return detector thresholds, falling back to saved or default values.

        Sprint 7: Delegates to DetectorCoordinator.

        Returns parameters with long-form names for backward compatibility.
        """
        params = self.detector_coordinator.get_detector_parameters()
        # Normalize conf_threshold to confidence_threshold for backward compatibility
        if "conf_threshold" in params:
            params["confidence_threshold"] = params.pop("conf_threshold")
        return params

    def get_factory_detector_parameters(self) -> dict[str, float]:
        """
        Return detector thresholds defined in config.yaml without overrides.

        Sprint 7: Delegates to DetectorCoordinator.

        Returns parameters with long-form names for backward compatibility.
        """
        params = self.detector_coordinator.get_factory_detector_parameters()
        # Normalize conf_threshold to confidence_threshold for backward compatibility
        if "conf_threshold" in params:
            params["confidence_threshold"] = params.pop("conf_threshold")
        return params

    def update_detector_parameters(
        self,
        params: dict[str, float],
        *,
        reset_overrides: bool = False,
        scope: str = "global",
    ) -> bool:
        """Apply detector threshold updates and persist them when possible.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller.update_detector_parameters(
            params=params, reset_overrides=reset_overrides, scope=scope
        )

    def _persist_project_model_settings(self, weight: str | None, use_openvino: bool) -> dict:
        """Persist model settings to project configuration.

        Facade - delegates to ProjectOrchestrator (Sprint 34).
        """
        return self.project_orchestrator._persist_project_model_settings(
            weight=weight, use_openvino=use_openvino
        )

    def copy_global_model_settings_to_project(self) -> None:
        """Copy global model settings to project.

        Facade - delegates to ProjectOrchestrator (Sprint 27).
        """
        return self.project_orchestrator.copy_global_model_settings_to_project()

    def save_current_calibration_to_project(self) -> None:
        """Save current calibration to project.

        Facade - delegates to ProjectOrchestrator (Sprint 27).
        """
        return self.project_orchestrator.save_current_calibration_to_project()

    def _apply_model_settings(
        self, weight_name: str | None, use_openvino: bool, dialog=None
    ) -> None:
        """Apply model settings (weight and OpenVINO) to the detector.

        Facade - delegates to ProjectOrchestrator (Sprint 34).
        """
        return self.project_orchestrator._apply_model_settings(
            weight_name=weight_name, use_openvino=use_openvino, dialog=dialog
        )

    def resolve_project_model_settings(
        self,
        model_type: str,
        model_key: str,
        field_name: str,
        default_value=None,
    ):
        """Resolve project model settings with fallback.

        Facade - delegates to ProjectOrchestrator (Sprint 27).
        """
        return self.project_orchestrator.resolve_project_model_settings(
            model_type=model_type,
            model_key=model_key,
            field_name=field_name,
            default_value=default_value,
        )

    def apply_project_model_overrides(
        self, overrides: dict | None = None
    ) -> tuple[str | None, bool]:
        """Apply project-specific model overrides to current settings.

        Facade - delegates to ProjectOrchestrator (Sprint 34).

        Args:
            overrides: Optional override dictionary to use instead of stored overrides.

        Returns:
            Tuple of (resolved_weight, resolved_openvino).
        """
        return self.project_orchestrator.apply_project_model_overrides(overrides=overrides)

    def save_project_model_overrides(
        self, active_weight_override: str | None, use_openvino_override: bool | None
    ) -> tuple[str | None, bool]:
        """Save model settings as project overrides and apply them.

        Facade - delegates to ProjectOrchestrator (Sprint 34).

        Args:
            active_weight_override: Weight name to save as override.
            use_openvino_override: OpenVINO preference to save as override.

        Returns:
            Tuple of (resolved_weight, resolved_openvino).
        """
        return self.project_orchestrator.save_project_model_overrides(
            active_weight_override=active_weight_override,
            use_openvino_override=use_openvino_override,
        )

    def _restore_global_model_defaults(self) -> None:
        """Restore global model defaults after closing a project.

        Facade - delegates to ProjectOrchestrator (Sprint 34).
        """
        return self.project_orchestrator._restore_global_model_defaults()

    @contextmanager
    def global_calibration_session(self):
        """Context manager for global calibration mode.

        Facade - delegates to CalibrationOrchestrator (Sprint 32).
        """
        with self.calibration_orchestrator.global_calibration_session():
            yield

    @contextmanager
    def project_calibration_session(self):
        """Project calibration context manager.

        Facade - delegates to ProjectOrchestrator (Sprint 27).
        """
        with self.project_orchestrator.project_calibration_session():
            yield

    def run_aquarium_detection(
        self,
        video_path: Path | str | None = None,
        stabilization_frames: int = 10,
        temp_aquarium_method: str | None = None,
    ):
        """Run the aquarium detection model on the specified or first project video.

        Facade - delegates to AnalysisOrchestrator (Sprint 25).

        Args:
            video_path: Path to video file, if None uses next project video
            stabilization_frames: Number of frames to analyze for stabilization
            temp_aquarium_method: Temporary override for aquarium detection method
                ('det' or 'seg'). If None, uses global self.settings.
        """
        return self.analysis_orchestrator.run_aquarium_detection(
            video_path=video_path,
            stabilization_frames=stabilization_frames,
            temp_aquarium_method=temp_aquarium_method,
        )

    def apply_roi_template(self, template: dict[str, Any]) -> None:
        """Aplica um template de ROI ao vídeo ativo.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller.apply_roi_template(template=template)

    def set_main_arena_polygon(self, points: list) -> bool:
        """Salva polígono com validações robustas.

        Facade - delegates to ZoneArenaOrchestrator (Sprint 30).
        """
        return self.zone_arena_orchestrator.set_main_arena_polygon(points=points)

    def save_manual_arena(self, polygon_points: list[list[int]]):
        """Save the manually adjusted arena and updates the detector.

        Facade - delegates to ZoneArenaOrchestrator (Sprint 30).
        """
        return self.zone_arena_orchestrator.save_manual_arena(polygon_points=polygon_points)

    def update_main_arena(self, polygon_points: list[list[int]]):
        """Update the main arena polygon in the project's zone data.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller.update_main_arena(polygon_points=polygon_points)

    def add_roi_polygon(self, roi_points: list[list[int]], name: str, color: tuple[int, int, int]):
        """Adiciona ROI com validação de sobreposição.

        Facade - delegates to ZoneArenaOrchestrator (Sprint 30).
        """
        return self.zone_arena_orchestrator.add_roi_polygon(
            roi_points=roi_points, name=name, color=color
        )

    def can_remove_project_asset(self, asset_type: AssetType, video_name: str) -> tuple[bool, str]:
        """Check if project asset can be removed.

        Facade - delegates to ProjectOrchestrator (Sprint 27).
        """
        return self.project_orchestrator.can_remove_project_asset(
            asset_type=asset_type, video_name=video_name
        )

    def delete_project_asset(self, asset_type: AssetType, video_name: str) -> bool:
        """Delete project asset.

        Facade - delegates to ProjectOrchestrator (Sprint 27).
        """
        return self.project_orchestrator.delete_project_asset(
            asset_type=asset_type, video_name=video_name
        )

    def run_live_calibration(self, temp_aquarium_method: str | None = None):
        """Record a short clip from the live camera and runs aquarium detection.

        Facade - delegates to RecordingSessionOrchestrator (Sprint 26).

        Args:
            temp_aquarium_method: Temporary override for aquarium detection method
                ('det' or 'seg'). If None, uses global self.settings.
        """
        return self.recording_session_orchestrator.run_live_calibration(
            temp_aquarium_method=temp_aquarium_method
        )

    def _handle_external_trigger(self, context: dict, arduino_enabled: bool) -> bool:
        """Handle external trigger setup for recording.

        Facade - delegates to RecordingSessionOrchestrator (Sprint 26).

        Args:
            context: Recording context with session details
            arduino_enabled: Whether Arduino is available

        Returns:
            bool: True if waiting for trigger (stop processing), False if proceed
        """
        return self.recording_session_orchestrator._handle_external_trigger(
            context=context, arduino_enabled=arduino_enabled
        )

    def start_recording(
        self,
        day: int | None = None,
        group: str | None = None,
        cobaia: str | None = None,
    ):
        """Start a recording session (live mode) with zone validation.

        Facade - delegates to RecordingSessionOrchestrator (Sprint 26).
        """
        return self.recording_session_orchestrator.start_recording(
            day=day, group=group, cobaia=cobaia
        )

    def start_live_camera_analysis(self, camera_index: int | None = None):
        """Start a live camera analysis session.

        Phase 2.3: Simplified to always delegate to RecordingSessionOrchestrator.
        Removed fallback since orchestrator is always initialized in __init__.

        Args:
            camera_index: Optional camera index. If provided, uses this camera directly
                         without showing the configuration dialog. If None, shows dialog.
        """
        return self.recording_session_orchestrator.start_live_camera_analysis(
            camera_index=camera_index
        )

    def start_live_camera_analysis_from_config(self, config: dict) -> bool:
        """Start live camera analysis with full configuration.

        Facade - delegates to LiveCameraCoordinator (Sprint 33).

        Args:
            config: Configuration dictionary from SingleVideoConfigDialog containing:
                - camera_index: int - Camera device index
                - analysis_interval_frames: int - Analyze every N frames
                - display_interval_frames: int - Display every N frames
                - (other dialog parameters)

        Returns:
            True if session started successfully, False otherwise
        """
        return self.live_camera_coordinator.start_session_from_config(config=config)

    def stop_recording(self):
        """Stop the current recording session.

        Facade - delegates to RecordingSessionOrchestrator (Sprint 26).
        """
        return self.recording_session_orchestrator.stop_recording()

    def start_live_project_session(
        self,
        day: int,
        group: str,
        subject: str,
        duration_s: float | None = None,
    ) -> bool:
        """Start a live recording session for a Live project.

        Facade - delegates to RecordingSessionOrchestrator (Sprint 26).

        Args:
            day: Day number (from project grid)
            group: Group identifier
            subject: Subject/animal identifier
            duration_s: Optional duration override (uses project default if None)

        Returns:
            True if session started successfully, False otherwise
        """
        return self.recording_session_orchestrator.start_live_project_session(
            day=day, group=group, subject=subject, duration_s=duration_s
        )

    def _ensure_zones_before_recording(self) -> bool:
        """Ensure project zones are defined before starting recording.

        Facade - delegates to RecordingSessionOrchestrator (Sprint 33).
        """
        return self.recording_session_orchestrator._ensure_zones_before_recording()

    # --- New Refactored Workflows ---

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
        self.ui_coordinator.set_status(self.view, "Cancelando análise em andamento...")
        if self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_UPDATE_BUTTON_STATE,
                {"button_name": "cancel_processing", "state": "disabled"},
            )
        else:
            self.ui_coordinator.update_view(
                self.view,
                "update_button_state",
                "cancel_processing",
                "disabled",
            )

        self._show_cancel_feedback()

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

    def _show_cancel_feedback(self) -> None:
        """Update UI immediately after a cancellation request.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller._show_cancel_feedback()

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
        Handle the scenario where some videos have data and some don't.

        Sprint 13: Extracted from start_project_processing_workflow().
        Handles user interaction for deciding which videos to process.

        Args:
            scanned_videos: List of scanned video info dictionaries

        Returns:
            list[dict] | None: Videos to process, or None if all should be skipped/added only
        """
        with_data = [v for v in scanned_videos if v["has_data"]]
        without_data = [v for v in scanned_videos if not v["has_data"]]

        if with_data and without_data:
            # Mixed case: some have data, some don't
            msg = (
                f"{len(with_data)} vídeo(s) já possuem dados de análise.\n"
                f"{len(without_data)} vídeo(s) precisam ser processados.\n\n"
                "Deseja reprocessar os vídeos que já possuem dados?"
            )
            if self.view.ask_ok_cancel("Dados Mistos Encontrados", msg):
                # User wants to re-process everything
                return scanned_videos
            else:
                # User wants to skip re-processing
                return without_data

        elif with_data and not without_data:
            # All selected videos have data
            if self.view.ask_ok_cancel(
                "Dados Encontrados",
                "Todos os vídeos selecionados já possuem dados de análise. "
                "Deseja reprocessá-los todos?",
            ):
                return with_data
            else:
                # User doesn't want to reprocess - add to project but don't process
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Processamento Ignorado",
                        "message": "Nenhum novo vídeo foi processado.",
                    },
                )
                # Still add them to the project for reporting purposes
                self.project_manager.add_video_batch(scanned_videos)
                return None  # Signal: don't process, already handled
        else:
            # No videos have data, process all of them
            return without_data

    def _validate_zones_with_ui(self) -> bool:
        """Validate that zones are defined, with UI dialogs for user interaction.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller._validate_zones_with_ui()

    def _handle_validation_error(self, validation_result) -> bool:
        """Handle validation errors by showing appropriate UI messages.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller._handle_validation_error(
            validation_result=validation_result
        )

    def start_single_video_processing(
        self, video_path: Path | str, config: dict, zone_data: ZoneData
    ):
        """
        Start the actual processing for a single video after zone setup.

        Facade - delegates to VideoProcessingOrchestrator (Sprint 24).
        """
        return self.video_processing_orchestrator.start_single_video_processing(
            video_path=video_path, config=config, zone_data=zone_data
        )

    def start_project_processing_workflow(self):
        """
        Adiciona vídeos com validação robusta de zonas.

        Facade - delegates to VideoProcessingOrchestrator (Sprint 24).
        """
        return self.video_processing_orchestrator.start_project_processing_workflow()

    def process_pending_project_videos(
        self,
        video_paths: list[str] | None = None,
    ) -> None:
        """
        Processa vídeos já adicionados ao projeto que possuem dados pendentes.

        Facade - delegates to VideoProcessingOrchestrator (Sprint 24).
        """
        return self.video_processing_orchestrator.process_pending_project_videos(
            video_paths=video_paths
        )

    def generate_parquet_summaries(self, video_paths: list[str]) -> None:
        """Regera arquivos de sumário em Parquet para os vídeos selecionados.

        Task 2.2: Delegates to AnalysisCoordinator.
        """
        self.analysis_coordinator.generate_parquet_summaries(
            video_paths, processing_thread_ref=self.processing_thread
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

    def _build_calibration_context(
        self,
        arena_polygon: list[list[int]] | list | None,
        calibration_data: dict | None,
    ) -> tuple[Calibration | None, tuple[float, float] | None]:
        """Calculate calibration and pixel/cm ratio for tracking outputs.

        Facade - delegates to CalibrationOrchestrator (Sprint 32).
        """
        return self.calibration_orchestrator._build_calibration_context(
            arena_polygon=arena_polygon, calibration_data=calibration_data
        )

    def _tracking_cancelled(self, experiment_id: str, frame_num: int, log_key: str) -> bool:
        """Handle cancel-event checks during tracking loop."""
        if not self.cancel_event.is_set():
            return False

        log.info(log_key, frame=frame_num, video=experiment_id)
        return True

    def _resolve_single_animal_mode(self, single_video_config: dict | None) -> bool | None:
        """Derive whether single-animal tracking mode should be active.

        Facade - delegates to ProcessingConfigOrchestrator (Sprint 31).
        """
        return self.processing_config_orchestrator._resolve_single_animal_mode(
            single_video_config=single_video_config
        )

    def _resolve_single_subject_tracker_preference(
        self, single_video_config: dict | None
    ) -> bool | None:
        """Resolve single-subject tracker preference from project or single video config.

        Facade - delegates to ProcessingConfigOrchestrator (Sprint 31).
        """
        return self.processing_config_orchestrator._resolve_single_subject_tracker_preference(
            single_video_config=single_video_config
        )

    def _configure_single_subject_tracker(self, enabled: bool) -> None:
        """Configure single-subject tracking mode.

        Facade - delegates to ProcessingConfigOrchestrator (Sprint 31).
        """
        self.processing_config_orchestrator._configure_single_subject_tracker(enabled=enabled)

    def _determine_processing_intervals(self, single_video_config: dict | None) -> tuple[int, int]:
        """Determine analysis and display intervals from config.

        Facade - delegates to ProcessingConfigOrchestrator (Sprint 31).
        """
        return self.processing_config_orchestrator._determine_processing_intervals(
            single_video_config=single_video_config
        )

    @contextmanager
    def _temporary_single_animal_mode(self, single_video_config: dict | None) -> Iterator[bool]:
        """Temporarily set single-animal/single-subject mode for processing scope.

        Facade - delegates to ProcessingConfigOrchestrator (Sprint 31).
        """
        with self.processing_config_orchestrator._temporary_single_animal_mode(
            single_video_config=single_video_config
        ) as result:
            yield result

    def _activate_analysis_view_mode(self) -> None:
        """Ensure the analysis tab is active so frames scale correctly.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller._activate_analysis_view_mode()

    def _prepare_processing_ui(self, total_videos: int) -> None:
        """Prepare processing UI.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller._prepare_processing_ui(total_videos=total_videos)

    def _finalize_processing(
        self,
        *,
        was_cancelled: bool,
        videos_to_process: list[dict],
        final_output_dir: str,
    ) -> None:
        """Finalize processing.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller._finalize_processing(
            was_cancelled=was_cancelled,
            videos_to_process=videos_to_process,
            final_output_dir=final_output_dir,
        )

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

    def _select_eligible_videos(
        self,
        skip_dialog: bool,
        ready_with_trajectory: list[dict],
        ready_with_zones: list[dict],
        arena_only: list[dict],
        without_arena: list[dict],
    ) -> list[dict] | None:
        """Select eligible videos for processing (either skip dialog or show it).

        Facade - delegates to VideoProcessingOrchestrator (Sprint 24).
        """
        return self.video_processing_orchestrator._select_eligible_videos(
            skip_dialog=skip_dialog,
            ready_with_trajectory=ready_with_trajectory,
            ready_with_zones=ready_with_zones,
            arena_only=arena_only,
            without_arena=without_arena,
        )

    def _generate_parquet_summaries_worker(self, target_videos: list[dict], settings_obj) -> None:
        """Worker method to generate parquet summaries for a list of videos.

        Facade - delegates to AnalysisOrchestrator (Sprint 25).
        """
        return self.analysis_orchestrator._generate_parquet_summaries_worker(
            target_videos=target_videos,
            settings_obj=settings_obj,
        )

    def _process_summary_video(
        self,
        video: dict,
        settings_obj,
    ) -> tuple[str, str | None, str | None, bool]:
        """Process a single video for summary generation.

        Facade - delegates to AnalysisOrchestrator (Sprint 25).
        """
        return self.analysis_orchestrator._process_summary_video(
            video=video,
            settings_obj=settings_obj,
        )

    def _make_progress_callback(
        self,
        *,
        index: int,
        total_videos: int,
        experiment_id: str,
    ):
        """Create a progress callback for video processing.

        Facade - delegates to VideoProcessingOrchestrator (Sprint 24).
        """
        return self.video_processing_orchestrator._make_progress_callback(
            index=index, total_videos=total_videos, experiment_id=experiment_id
        )

    # Phase 7.2b: Removed 4 auxiliary methods (75 lines) -
    # migrated to VideoProcessingService:
    # - _display_initial_frame
    # - _resolve_results_path
    # - _ensure_arena_polygon
    # - _load_trajectory_dataframe

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

    def _register_project_outputs(self, project_path: str, video_file: str) -> None:
        """Register project outputs.

        Facade - delegates to ProjectOrchestrator (Sprint 27).
        """
        return self.project_orchestrator._register_project_outputs(
            project_path=project_path, video_file=video_file
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

    def _create_processing_callbacks(self, videos_to_process: list[dict]) -> ProcessingCallbacks:
        """
        Create thread-safe callbacks for the processing worker.

        Facade - delegates to VideoProcessingOrchestrator (Sprint 24).
        """
        return self.video_processing_orchestrator._create_processing_callbacks(
            videos_to_process=videos_to_process
        )

    def _create_processing_context(
        self,
        videos_to_process: list[dict],
        output_base_dir: str,
        single_video_config: dict | None = None,
    ) -> ProcessingContext:
        """Create the processing context with all necessary configuration.

        Facade - delegates to VideoProcessingOrchestrator (Sprint 24).
        """
        return self.video_processing_orchestrator._create_processing_context(
            videos_to_process=videos_to_process,
            output_base_dir=output_base_dir,
            single_video_config=single_video_config,
        )

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

        Task 2.2: Delegates to AnalysisCoordinator.
        """
        self.analysis_coordinator.generate_report(videos, report_type)

    def run_model_diagnostic(self, config: dict):
        """
        Prepare for and launches the diagnostic test in a background thread.

        Now shows a progress dialog during execution.

        Facade - delegates to ModelDiagnosticsOrchestrator (Sprint 29).
        """
        return self.model_diagnostics_orchestrator.run_model_diagnostic(config=config)

    def _diagnostic_processing_thread(self, config: dict, weight_details: dict):
        """
        Run actual diagnostic processing logic in a background thread.

        Updates progress dialog during execution.

        Facade - delegates to ModelDiagnosticsOrchestrator (Sprint 29).
        """
        return self.model_diagnostics_orchestrator._diagnostic_processing_thread(
            config=config, weight_details=weight_details
        )

    def _update_diagnostic_progress(
        self,
        progress_dialog,
        message: str,
        current: int | None = None,
        total: int | None = None,
    ) -> None:
        """Thread-safe progress dialog update helper.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller._update_diagnostic_progress(
            progress_dialog=progress_dialog,
            message=message,
            current=current,
            total=total,
        )

    def _finish_progress_dialog(self, progress_dialog) -> None:
        """Safely close the diagnostic progress dialog.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller._finish_progress_dialog(progress_dialog=progress_dialog)

    def _initialize_diagnostic_yolo_model(
        self,
        model_to_test: str,
        weight_details: dict,
        results: dict[str, list],
        progress_dialog,
    ) -> Any | None:
        """Set up YOLO model for diagnostics.

        Facade - delegates to ModelDiagnosticsOrchestrator (Sprint 29).
        """
        return self.model_diagnostics_orchestrator._initialize_diagnostic_yolo_model(
            model_to_test=model_to_test,
            weight_details=weight_details,
            results=results,
            progress_dialog=progress_dialog,
        )

    def _initialize_diagnostic_openvino_model(
        self,
        model_to_test: str,
        weight_details: dict,
        results: dict[str, list],
        progress_dialog,
    ) -> Any | None:
        """Set up OpenVINO model for diagnostics.

        Facade - delegates to ModelDiagnosticsOrchestrator (Sprint 29).
        """
        return self.model_diagnostics_orchestrator._initialize_diagnostic_openvino_model(
            model_to_test=model_to_test,
            weight_details=weight_details,
            results=results,
            progress_dialog=progress_dialog,
        )

    def _run_diagnostic_frame_loop(
        self,
        video_path: str,
        frames_to_analyze: int,
        conf_threshold: float,
        yolo_model,
        openvino_model,
        results: dict[str, list],
        progress_dialog,
    ) -> None:
        """Process video frames for the diagnostic routine.

        Facade - delegates to ModelDiagnosticsOrchestrator (Sprint 29).
        """
        return self.model_diagnostics_orchestrator._run_diagnostic_frame_loop(
            video_path=video_path,
            frames_to_analyze=frames_to_analyze,
            conf_threshold=conf_threshold,
            yolo_model=yolo_model,
            openvino_model=openvino_model,
            results=results,
            progress_dialog=progress_dialog,
        )

    def _finish_diagnostic_and_save_report(self, config, results):
        """Format and saves the report. Runs on the main UI thread.

        Facade - delegates to ModelDiagnosticsOrchestrator (Sprint 29).
        """
        return self.model_diagnostics_orchestrator._finish_diagnostic_and_save_report(
            config=config, results=results
        )

    def _format_diagnostic_report(self, config, results) -> str:
        """Format the collected diagnostic data into a string.

        Facade - delegates to ModelDiagnosticsOrchestrator (Sprint 29).
        """
        return self.model_diagnostics_orchestrator._format_diagnostic_report(
            config=config, results=results
        )


# -----------------------------------------------------------------------------
# Backward Compatibility Alias (Phase 1, Step 3)
# -----------------------------------------------------------------------------
# Maintain backward compatibility during migration.
# All existing code can continue importing AppController.
# New code should prefer MainViewModel for clarity.

AppController = MainViewModel
