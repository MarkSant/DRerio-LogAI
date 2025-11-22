"""
Application Bootstrapper for ZebTrack-AI.

Responsibility:
- Initialize all internal services and orchestrators that are not injected via __main__.py
- Configure hardware and runtime state
- Create and wire the ApplicationGUI
- Prepare the BootstrapResult for the MainViewModel

This class removes initialization complexity from the MainViewModel, adhering to SRP.
"""

from __future__ import annotations

import glob
import os
import queue
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.analysis.analysis_service import AnalysisService

# Legacy Coordinators for backward compatibility
from zebtrack.coordinators.detector_coordinator import DetectorCoordinator
from zebtrack.coordinators.dialog_coordinator import DialogCoordinator
from zebtrack.coordinators.live_camera_coordinator import LiveCameraCoordinator
from zebtrack.coordinators.recording_coordinator import RecordingCoordinator
from zebtrack.core.analysis_coordinator import AnalysisCoordinator
from zebtrack.core.batch_configuration_service import BatchConfigurationService
from zebtrack.core.dependency_container import MainViewModelDependencies
from zebtrack.core.orchestrator_registry import OrchestratorRegistry
from zebtrack.core.project_service import ProjectService
from zebtrack.core.thread_coordinator import ThreadCoordinator
from zebtrack.core.video_classification_service import VideoClassificationService
from zebtrack.core.video_orchestrator import VideoOrchestrator
from zebtrack.core.video_selection_service import VideoSelectionService
from zebtrack.core.video_validation_service import VideoValidationService
from zebtrack.io.arduino_manager import ArduinoManager
from zebtrack.io.recorder import Recorder
from zebtrack.orchestrators.analysis_orchestrator import AnalysisOrchestrator
from zebtrack.orchestrators.calibration_orchestrator import CalibrationOrchestrator
from zebtrack.orchestrators.model_diagnostics_orchestrator import ModelDiagnosticsOrchestrator
from zebtrack.orchestrators.processing_config_orchestrator import ProcessingConfigOrchestrator
from zebtrack.orchestrators.project_orchestrator import ProjectOrchestrator

# Legacy Orchestrators (to be removed in future phases)
from zebtrack.orchestrators.recording_session_orchestrator import RecordingSessionOrchestrator
from zebtrack.orchestrators.ui_state_controller import UIStateController
from zebtrack.orchestrators.video_processing_orchestrator import VideoProcessingOrchestrator
from zebtrack.orchestrators.zone_arena_orchestrator import ZoneArenaOrchestrator
from zebtrack.ui.components.event_dispatcher import EventDispatcher
from zebtrack.ui.gui import ApplicationGUI
from zebtrack.ui.project_workflow_adapter import ProjectWorkflowAdapter
from zebtrack.utils.hardware_detection import get_hardware_summary, recommend_backend

if TYPE_CHECKING:
    pass

log = structlog.get_logger()


@dataclass
class BootstrapResult:
    """Result of the application bootstrap process."""

    # Internal Services
    project_service: ProjectService
    analysis_service: AnalysisService
    video_classification_service: VideoClassificationService
    video_selection_service: VideoSelectionService
    video_validation_service: VideoValidationService
    batch_configuration_service: BatchConfigurationService
    thread_coordinator: ThreadCoordinator
    dialog_coordinator: DialogCoordinator
    event_dispatcher: EventDispatcher

    # Hardware & Runtime State
    active_weight_name: str | None
    use_openvino: bool
    hardware_summary: dict
    recommended_backend: str
    recorder: Recorder
    arduino_manager: ArduinoManager | None

    # Threading & Queues
    frame_queue: queue.Queue
    video_queue: queue.Queue
    program_exit_event: threading.Event
    cancel_event: threading.Event

    # View
    view: ApplicationGUI

    # Legacy Orchestrators
    video_processing_orchestrator: VideoProcessingOrchestrator
    analysis_orchestrator: AnalysisOrchestrator
    recording_session_orchestrator: RecordingSessionOrchestrator
    project_orchestrator: ProjectOrchestrator
    ui_state_controller: UIStateController
    model_diagnostics_orchestrator: ModelDiagnosticsOrchestrator
    zone_arena_orchestrator: ZoneArenaOrchestrator
    processing_config_orchestrator: ProcessingConfigOrchestrator
    calibration_orchestrator: CalibrationOrchestrator

    # Registry & Adapter
    orchestrators: OrchestratorRegistry
    project_workflow_adapter: ProjectWorkflowAdapter

    # Legacy Coordinators (created internally if not injected)
    legacy_coordinators: dict[str, Any] = field(default_factory=dict)


class ApplicationBootstrapper:
    """
    Handles the initialization of application components that are not
    injected via the Composition Root (__main__.py).
    """

    def __init__(self, dependencies: MainViewModelDependencies, view: Any = None):
        self.deps = dependencies
        self.view = view
        self.state_manager = dependencies.state_manager
        self.settings = dependencies.settings_obj

        # Temporary storage for initialization results
        self._services: dict = {}
        self._hardware_state: dict = {}
        self._runtime_state: dict = {}
        self._orchestrators: dict = {}
        self._legacy_coordinators: dict = {}

    def initialize(self, controller_proxy: Any) -> BootstrapResult:
        """
        Execute the bootstrap process.
        
        Args:
            controller_proxy: A proxy or "self" reference from MainViewModel to pass
                            to legacy orchestrators that demand it in __init__.
        
        Returns:
            BootstrapResult containing all initialized components.
        """
        log.info("bootstrapper.initialize.start")

        # 1. Initialize internal services
        self._init_services()

        # 2. Initialize hardware and models
        self._init_hardware_and_models()

        # 3. Initialize runtime state
        self._init_runtime_state()

        # 4. Initialize view
        self._init_view(controller_proxy)

        # -----------------------------------------------------------------------
        # CRITICAL: Populate controller proxy with dependencies required by
        # legacy orchestrators' __init__ methods.
        # This allows us to break the circular dependency without rewriting
        # all legacy code immediately.
        # -----------------------------------------------------------------------

        # Core dependencies
        controller_proxy.state_manager = self.state_manager
        controller_proxy.project_manager = self.deps.project_manager
        controller_proxy.ui_coordinator = self.deps.ui_coordinator
        controller_proxy.root = self.deps.root
        controller_proxy.settings = self.settings
        controller_proxy.ui_event_bus = self.deps.event_bus

        # Services created in step 1
        controller_proxy.video_selection_service = self._services["video_selection_service"]
        controller_proxy.video_validation_service = self._services["video_validation_service"]
        controller_proxy.video_classification_service = self._services["video_classification_service"]

        # Hardware from step 2/deps
        controller_proxy.detector = self.deps.detector_service.detector

        # Runtime state from step 3
        controller_proxy.cancel_event = self._runtime_state["cancel_event"]

        # View from step 4
        controller_proxy.view = self.view

        # Coordinators from deps
        controller_proxy.processing_coordinator = self.deps.processing_coordinator
        controller_proxy.hardware_coordinator = self.deps.hardware_coordinator
        controller_proxy.session_coordinator = self.deps.session_coordinator
        controller_proxy.project_lifecycle_coordinator = self.deps.project_lifecycle_coordinator

        # -----------------------------------------------------------------------

        # 5. Initialize orchestrators (requires controller_proxy)
        self._init_orchestrators(controller_proxy)

        log.info("bootstrapper.initialize.complete")

        return BootstrapResult(
            project_service=self._services["project_service"],
            analysis_service=self._services["analysis_service"],
            video_classification_service=self._services["video_classification_service"],
            video_selection_service=self._services["video_selection_service"],
            video_validation_service=self._services["video_validation_service"],
            batch_configuration_service=self._services["batch_configuration_service"],
            thread_coordinator=self._services["thread_coordinator"],
            dialog_coordinator=self._services["dialog_coordinator"],
            event_dispatcher=self._services["event_dispatcher"],

            active_weight_name=self._hardware_state["active_weight_name"],
            use_openvino=self._hardware_state["use_openvino"],
            hardware_summary=self._hardware_state["hardware_summary"],
            recommended_backend=self._hardware_state["recommended_backend"],

            recorder=self._runtime_state["recorder"],
            arduino_manager=self._runtime_state["arduino_manager"],
            frame_queue=self._runtime_state["frame_queue"],
            video_queue=self._runtime_state["video_queue"],
            program_exit_event=self._runtime_state["program_exit_event"],
            cancel_event=self._runtime_state["cancel_event"],

            view=self.view,

            video_processing_orchestrator=self._orchestrators["video_processing_orchestrator"],
            analysis_orchestrator=self._orchestrators["analysis_orchestrator"],
            recording_session_orchestrator=self._orchestrators["recording_session_orchestrator"],
            project_orchestrator=self._orchestrators["project_orchestrator"],
            ui_state_controller=self._orchestrators["ui_state_controller"],
            model_diagnostics_orchestrator=self._orchestrators["model_diagnostics_orchestrator"],
            zone_arena_orchestrator=self._orchestrators["zone_arena_orchestrator"],
            processing_config_orchestrator=self._orchestrators["processing_config_orchestrator"],
            calibration_orchestrator=self._orchestrators["calibration_orchestrator"],

            orchestrators=self._orchestrators["registry"],
            project_workflow_adapter=self._orchestrators["project_workflow_adapter"],

            legacy_coordinators=self._legacy_coordinators
        )

    def _init_services(self):
        """Initialize all service layer components."""
        # Core services
        project_service = ProjectService()
        analysis_service = (
            self.deps.analysis_service
            if self.deps.analysis_service is not None
            else AnalysisService(settings_obj=self.settings)
        )

        # Video processing helper services
        video_classification_service = VideoClassificationService()
        video_selection_service = VideoSelectionService()
        video_validation_service = VideoValidationService()

        # Initialize services created during Phase 1 refactoring
        batch_configuration_service = BatchConfigurationService(
            project_manager=self.deps.project_manager,
            settings_obj=self.settings,
        )
        thread_coordinator = ThreadCoordinator()
        dialog_coordinator = DialogCoordinator(
            ui_coordinator=self.deps.ui_coordinator,
            event_bus=self.deps.event_bus,
            state_manager=self.state_manager,
            project_manager=self.deps.project_manager,
        )
        event_dispatcher = EventDispatcher(self.deps.event_bus)

        self._services = {
            "project_service": project_service,
            "analysis_service": analysis_service,
            "video_classification_service": video_classification_service,
            "video_selection_service": video_selection_service,
            "video_validation_service": video_validation_service,
            "batch_configuration_service": batch_configuration_service,
            "thread_coordinator": thread_coordinator,
            "dialog_coordinator": dialog_coordinator,
            "event_dispatcher": event_dispatcher,
        }

    def _init_hardware_and_models(self):
        """Initialize hardware detection and model configuration."""
        # New state variables for model management (must exist before view)
        default_weight, _ = self._safe_get_default_weight()

        # Raise exception if no valid weight is available
        if not isinstance(default_weight, str) or not default_weight:
            raise RuntimeError(
                "No valid detector weight available. Cannot initialize application. "
                "Please ensure at least one .pt or .onnx file is in the 'models/' directory."
            )

        active_weight_name = default_weight

        # Hardware detection and auto-configuration
        log.info("bootstrapper.hardware.detection_start")
        hardware_summary = get_hardware_summary()
        recommended_backend = recommend_backend()

        # Auto-configure use_openvino based on hardware detection
        use_openvino = False
        if recommended_backend == "openvino":
            # Check if OpenVINO model is already converted
            default_weight_details = None
            if active_weight_name:
                default_weight_details = self.deps.weight_manager.get_weight_details(
                    active_weight_name
                )

            openvino_converted = False
            if default_weight_details:
                ov_path = default_weight_details.get("openvino_path")
                openvino_converted = self._is_valid_openvino_directory(ov_path)

            if openvino_converted:
                use_openvino = True
                log.info(
                    "bootstrapper.hardware.auto_selected_openvino",
                    reason="Hardware detection recommends OpenVINO and model is converted",
                )
            else:
                # OpenVINO recommended but model not converted - fall back to PyTorch
                use_openvino = False
                log.warning(
                    "bootstrapper.hardware.openvino_recommended_but_not_converted",
                    reason="OpenVINO recommended but model not converted",
                )
        else:
            use_openvino = False
            log.info(
                "bootstrapper.hardware.auto_selected_pytorch",
                reason="Hardware detection recommends PyTorch",
            )

        self._hardware_state = {
            "active_weight_name": active_weight_name,
            "use_openvino": use_openvino,
            "hardware_summary": hardware_summary,
            "recommended_backend": recommended_backend
        }

    def _init_runtime_state(self):
        """Initialize runtime attributes and threading primitives."""
        # Core runtime attributes
        recorder = Recorder(settings_obj=self.settings)

        # Initialize recording state in StateManager
        self.state_manager.update_recording_state(
            source="bootstrapper.init",
            is_recording=False,
        )

        # Queues for live frame processing
        frame_queue = queue.Queue(maxsize=30)  # Queue for frames to be processed
        video_queue = queue.Queue(maxsize=30)  # Queue for frames to be recorded

        # Exit event for threads
        program_exit_event = threading.Event()
        cancel_event = threading.Event()

        self._runtime_state = {
            "recorder": recorder,
            "arduino_manager": None, # Will be initialized on demand
            "frame_queue": frame_queue,
            "video_queue": video_queue,
            "program_exit_event": program_exit_event,
            "cancel_event": cancel_event
        }

        # Configure global model defaults
        self.deps.project_workflow_service.set_global_model_defaults(
            active_weight=self._hardware_state["active_weight_name"] or None,
            use_openvino=self._hardware_state["use_openvino"],
        )

    def _init_view(self, controller_proxy):
        """Initialize the view and update it with initial state."""
        # Phase 2: Inversion of Control - view can be injected or created
        if self.view is None:
            # Create view after core state is ready so it can reflect it (legacy pattern)
            # Use event bus from dependencies
            ui_features = getattr(self.settings, "ui_features", None)
            use_event_bus = bool(
                self.deps.event_bus or
                (ui_features and getattr(ui_features, "enable_event_queue", False))
            )

            self.view = ApplicationGUI(
                self.deps.root,
                controller_proxy, # Must pass controller for legacy callbacks
                event_bus=self.deps.event_bus if use_event_bus else None,
                settings_obj=self.settings,
            )

        # Update GPU hardware display in UI
        if hasattr(self.view, "update_gpu_hardware_display"):
            self.view.update_gpu_hardware_display(self._hardware_state["hardware_summary"])

        # Update OpenVINO status
        if (self._hardware_state["recommended_backend"] == "openvino"
            and not self._hardware_state["use_openvino"]):
            if hasattr(self.view, "update_openvino_status_display"):
                self.view.update_openvino_status_display(
                    "Recomendado mas modelo não convertido. Use 'Diagnóstico' para converter."
                )

    def _init_orchestrators(self, controller_proxy):
        """Initialize all orchestrators and coordinators."""

        # Legacy Coordinators (DEPRECATED - created only if not injected)
        legacy_coords = {}

        # Detector Coordinator
        if self.deps.detector_coordinator:
            legacy_coords["detector_coordinator"] = self.deps.detector_coordinator
        else:
            legacy_coords["detector_coordinator"] = DetectorCoordinator(
                state_manager=self.state_manager,
                detector_service=self.deps.detector_service,
                model_service=self.deps.model_service,
                weight_manager=self.deps.weight_manager,
                event_bus=self.deps.event_bus,
            )

        # Video Orchestrator
        if self.deps.video_orchestrator:
            legacy_coords["video_orchestrator"] = self.deps.video_orchestrator
        else:
            video_orc = VideoOrchestrator(
                root=self.deps.root,
                state_manager=self.state_manager,
                ui_event_bus=self.deps.event_bus,
                ui_coordinator=self.deps.ui_coordinator,
                settings_obj=self.settings,
                project_manager=self.deps.project_manager,
                video_processing_service=self.deps.video_processing_service,
                analysis_service=self._services["analysis_service"],
                recorder=self._runtime_state["recorder"],
            )
            video_orc.set_view(self.view)
            legacy_coords["video_orchestrator"] = video_orc

        # Analysis Coordinator
        if self.deps.analysis_coordinator:
            legacy_coords["analysis_coordinator"] = self.deps.analysis_coordinator
        else:
            analysis_coord = AnalysisCoordinator(
                root=self.deps.root,
                ui_event_bus=self.deps.event_bus,
                ui_coordinator=self.deps.ui_coordinator,
                settings_obj=self.settings,
                project_manager=self.deps.project_manager,
                analysis_service=self._services["analysis_service"],
                video_processing_service=self.deps.video_processing_service,
            )
            analysis_coord.set_view(self.view)
            legacy_coords["analysis_coordinator"] = analysis_coord

        # Project Coordinator
        if self.deps.project_coordinator:
            legacy_coords["project_coordinator"] = self.deps.project_coordinator
        else:
            legacy_coords["project_coordinator"] = None

        # Recording Coordinator
        if self.deps.recording_coordinator:
            legacy_coords["recording_coordinator"] = self.deps.recording_coordinator
        else:
            legacy_coords["recording_coordinator"] = RecordingCoordinator(
                state_manager=self.state_manager,
                recording_service=self.deps.recording_service,
                arduino_manager=None, # Initialized lazily
                event_bus=self.deps.event_bus,
            )

        # Live Camera Coordinator
        if self.deps.live_camera_coordinator:
            legacy_coords["live_camera_coordinator"] = self.deps.live_camera_coordinator
        else:
            legacy_coords["live_camera_coordinator"] = LiveCameraCoordinator(
                state_manager=self.state_manager,
                live_camera_service=self.deps.live_camera_service,
                project_manager=self.deps.project_manager,
                settings=self.settings,
                camera=None,
                event_bus=self.deps.event_bus,
            )

        self._legacy_coordinators = legacy_coords

        # Initialize Orchestrators
        # NOTE: These legacy orchestrators require the controller (MainViewModel)
        # We pass the controller_proxy which should be the 'self' from MainViewModel.__init__

        recording_session_orchestrator = RecordingSessionOrchestrator(controller_proxy)
        # Manual setup for recording service callbacks since we're bypassing _init_orchestrators logic
        recording_session_orchestrator._setup_recording_service_callbacks()

        video_processing_orchestrator = VideoProcessingOrchestrator(controller_proxy)
        analysis_orchestrator = AnalysisOrchestrator(controller_proxy)
        project_orchestrator = ProjectOrchestrator(controller_proxy)
        ui_state_controller = UIStateController(controller_proxy)
        model_diagnostics_orchestrator = ModelDiagnosticsOrchestrator(controller_proxy)
        zone_arena_orchestrator = ZoneArenaOrchestrator(controller_proxy)
        processing_config_orchestrator = ProcessingConfigOrchestrator(controller_proxy)
        calibration_orchestrator = CalibrationOrchestrator(controller_proxy)

        self._orchestrators = {
            "recording_session_orchestrator": recording_session_orchestrator,
            "video_processing_orchestrator": video_processing_orchestrator,
            "analysis_orchestrator": analysis_orchestrator,
            "project_orchestrator": project_orchestrator,
            "ui_state_controller": ui_state_controller,
            "model_diagnostics_orchestrator": model_diagnostics_orchestrator,
            "zone_arena_orchestrator": zone_arena_orchestrator,
            "processing_config_orchestrator": processing_config_orchestrator,
            "calibration_orchestrator": calibration_orchestrator,
        }

        # Registry
        registry = OrchestratorRegistry(
            recording_session_orchestrator=recording_session_orchestrator,
            project_orchestrator=project_orchestrator,
            ui_state_controller=ui_state_controller,
            video_processing_orchestrator=video_processing_orchestrator,
            analysis_orchestrator=analysis_orchestrator,
            processing_config_orchestrator=processing_config_orchestrator,
            model_diagnostics_orchestrator=model_diagnostics_orchestrator,
            zone_arena_orchestrator=zone_arena_orchestrator,
            calibration_orchestrator=calibration_orchestrator,
            live_camera_coordinator=legacy_coords["live_camera_coordinator"],
        )
        self._orchestrators["registry"] = registry

        # Project Workflow Adapter
        project_workflow_adapter = ProjectWorkflowAdapter(
            project_workflow_service=self.deps.project_workflow_service,
            project_manager=self.deps.project_manager,
            detector_service=self.deps.detector_service,
            state_manager=self.state_manager,
            ui_event_bus=self.deps.event_bus,
        )
        self._orchestrators["project_workflow_adapter"] = project_workflow_adapter

        # Setup coordinator callbacks
        # This replicates _setup_coordinator_callbacks from MainViewModel
        if self.deps.hardware_coordinator and self.deps.session_coordinator:
            self.deps.hardware_coordinator.set_recording_callbacks(
                self.deps.session_coordinator.trigger_recording,
                self.deps.session_coordinator.stop_recording,
            )

    def _safe_get_default_weight(self) -> tuple[str | None, dict | None]:
        manager = self.deps.weight_manager
        if manager is None:
            return None, None
        try:
            result = manager.get_default_weight()
        except (FileNotFoundError, OSError, KeyError, ValueError) as e:
            log.warning("bootstrapper.default_weight.safe_get_failed", error=str(e))
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

    def _is_valid_openvino_directory(self, path: str | None) -> bool:
        if not path or not os.path.exists(path):
            return False
        if not os.path.isdir(path):
            return False
        xml_files = glob.glob(os.path.join(path, "*.xml"))
        return len(xml_files) > 0
