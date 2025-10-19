from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, cast

import cv2
import numpy as np
import pandas as pd
import structlog
from shapely.geometry import Polygon

try:
    from ultralytics import YOLO

    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.analysis.reporter import Reporter
from zebtrack.analysis.roi import ROI, ROIAnalyzer
from zebtrack.core.aquarium_detector import AquariumDetector
from zebtrack.core.calibration import Calibration
from zebtrack.core.detector import Detector, ZoneData
from zebtrack.core.detector_service import DetectorService
from zebtrack.core.processing_mode import ProcessingMode, ProcessingReport
from zebtrack.core.processing_worker import (
    ProcessingCallbacks,
    ProcessingContext,
    ProcessingWorker,
)
from zebtrack.core.project_manager import AssetType, ProjectManager
from zebtrack.core.project_service import ProjectService
from zebtrack.core.recording_service import RecordingService
from zebtrack.core.state_manager import StateCategory, StateManager
from zebtrack.core.ui_coordinator import UICoordinator
from zebtrack.core.video_processing_service import VideoProcessingService
from zebtrack.core.weight_manager import WeightManager
from zebtrack.io.arduino import Arduino
from zebtrack.io.arduino_manager import ArduinoManager
from zebtrack.io.recorder import Recorder
from zebtrack.plugins import DETECTOR_PLUGINS
from zebtrack.settings import settings
from zebtrack.ui.event_bus import EventBus
from zebtrack.ui.events import Events
from zebtrack.ui.gui import ApplicationGUI

log = structlog.get_logger()

try:
    DEFAULT_TRACK_THRESHOLD = float(settings.bytetrack.track_threshold)
    DEFAULT_MATCH_THRESHOLD = float(settings.bytetrack.match_threshold)
except AttributeError:  # pragma: no cover - legacy settings fallback
    DEFAULT_TRACK_THRESHOLD = 0.25
    DEFAULT_MATCH_THRESHOLD = 0.15


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

    def __init__(self, root, test_sync_event: threading.Event | None = None):
        self.root = root

        # Test synchronization support (Phase 1.1)
        self._test_sync_event = test_sync_event

        # Phase 2, Step 4: Centralized state management
        self.state_manager = StateManager(enable_history=True, max_history_size=100)

        # Register test observer if sync event provided
        if self._test_sync_event is not None:
            self.state_manager.subscribe_all(self._on_state_change_for_test)

        # Service layer dependencies (Phase 1, Step 3)
        self.project_service = ProjectService()
        self.analysis_service = AnalysisService()

        # State managers (pass StateManager reference to ProjectManager)
        self.project_manager = ProjectManager(state_manager=self.state_manager)
        self.weight_manager = WeightManager()

        # Model management service (Phase 2, Step 1)
        from zebtrack.core.model_service import ModelService

        self.model_service = ModelService(self.weight_manager)

        # Detector management service (Phase 6)
        self.detector_service = DetectorService(
            state_manager=self.state_manager,
            project_manager=self.project_manager,
            weight_manager=self.weight_manager,
            model_service=self.model_service,
        )

        # Project workflow service (Phase 5) - initialize after UICoordinator
        # Will be fully initialized after UICoordinator is created
        self.project_workflow_service = None

        # New state variables for model management (must exist before view)
        default_weight, _ = self._safe_get_default_weight()
        self.active_weight_name = default_weight if default_weight is not None else ""
        if self.active_weight_name is None:
            self.active_weight_name = ""
            log.warning("controller.init.no_default_weight")
        self.use_openvino = False  # Default to not using OpenVINO
        self._global_model_defaults = {
            "active_weight": self.active_weight_name or None,
            "use_openvino": self.use_openvino,
        }
        self._using_project_overrides = False

        # Core runtime attributes
        # Note: detector is now managed by detector_service (Phase 6)
        # Access via self.detector property which delegates to service
        self.recorder = Recorder()
        self.arduino: Arduino | None = None
        self.arduino_manager: ArduinoManager | None = None
        self._arduino_manager_cls = ArduinoManager
        self.report_results_paths = {}
        # Note: is_recording now managed by StateManager via @property
        self.timed_recording_job = None

        # Recording service (Phase 2.2) - will be fully initialized after arduino_manager
        self.recording_service: RecordingService | None = None

        # Initialize recording state in StateManager
        self.state_manager.update_recording_state(
            source="controller.init",
            is_recording=False,
        )

        ui_features = getattr(settings, "ui_features", None)
        self._use_event_bus = bool(
            ui_features and getattr(ui_features, "enable_event_queue", False)
        )
        self.ui_event_bus: EventBus | None = EventBus() if self._use_event_bus else None
        if self._use_event_bus:
            log.info("controller.event_bus.enabled")
            # Subscribe to all UI→Controller events
            self._register_event_handlers()

        # Phase 4: UI Coordinator for consolidated UI scheduling
        self.ui_coordinator = UICoordinator(
            root=self.root,
            event_bus=self.ui_event_bus,
        )

        # Phase 5: Project Workflow Service for project creation/opening orchestration
        from zebtrack.core.project_workflow_service import ProjectWorkflowService

        self.project_workflow_service = ProjectWorkflowService(
            project_manager=self.project_manager,
            model_service=self.model_service,
            state_manager=self.state_manager,
            ui_coordinator=self.ui_coordinator,
        )
        # Set global model defaults
        self.project_workflow_service.set_global_model_defaults(
            active_weight=self.active_weight_name or None,
            use_openvino=self.use_openvino,
        )

        self._active_processing_mode = ProcessingMode.MULTI_TRACK

        # Create view after core state is ready so it can reflect it
        self.view = ApplicationGUI(
            root,
            self,
            event_bus=self.ui_event_bus if self._use_event_bus else None,
        )
        self._publish_processing_mode(source="init", force=True)

        # Initialize core threading primitives first
        self.program_exit_event = threading.Event()
        self.processing_thread: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.pending_single_video_analysis = None
        self.processing_worker: ProcessingWorker | None = None
        self._pending_external_trigger: dict | None = None

        # Initialize services (Phase 2.2 + Phase 3 + Phase 7.2)
        # Note: video_processing_service needs cancel_event, so init it after threading setup
        self._init_recording_service()
        self._init_analysis_service()
        self._init_video_processing_service()

    def run(self):
        # The GUI is now responsible for populating its own widgets when created.
        self.root.mainloop()

    # ==================== Phase 2, Step 4: State Manager Properties ====================  # noqa: E501
    # Backward-compatible properties that delegate to StateManager

    @property
    def is_recording(self) -> bool:
        """Get recording status from StateManager."""
        return self.state_manager.get_recording_state().is_recording

    @is_recording.setter
    def is_recording(self, value: bool) -> None:
        """Update recording status in StateManager."""
        self.state_manager.update_recording_state(
            source="controller.is_recording_setter",
            is_recording=value,
        )

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

    def get_openvino_status(self) -> str:
        """
        Gets the current OpenVINO status text based on the model and settings.

        Delegates to ModelService for business logic (Phase 2.1).
        """
        return self.model_service.get_openvino_status(
            weight_name=self.active_weight_name, use_openvino=self.use_openvino
        )

    def on_close(self):
        if self.view.ask_ok_cancel("Sair", "Deseja realmente sair?"):
            if hasattr(self.view, "stop_event_bus_polling"):
                try:
                    self.view.stop_event_bus_polling()
                except Exception:
                    log.warning("controller.event_bus.stop_failed", exc_info=True)
            self.join_threads()
            self.root.destroy()

    def join_threads(self):
        """Signals all threads to stop and waits for them to finish."""
        log.info("controller.shutdown.start")
        self.program_exit_event.set()

        # Join background threads
        if hasattr(self, "capture_thread") and self.capture_thread.is_alive():
            log.info("controller.shutdown.join_capture_thread")
            self.capture_thread.join()

        if self.processing_thread is not None and self.processing_thread.is_alive():
            log.info("controller.shutdown.join_processing_thread")
            self.processing_thread.join()

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
            except Exception:
                log.warning("controller.arduino.shutdown_failed", exc_info=True)
            self.arduino_manager = None
        self.arduino = None

    def _schedule_on_ui(self, func, *args, **kwargs):
        """
        Schedule a function to run on the UI thread.

        Phase 4: Delegates to UICoordinator for centralized UI scheduling.
        Kept for backward compatibility with existing code.
        """
        self.ui_coordinator.schedule(func, *args, **kwargs)

    def _init_recording_service(self) -> None:
        """
        Initialize RecordingService with dependencies and UI callbacks.

        Phase 2.2: Extracts recording orchestration logic from MainViewModel.

        Note:
        - recorder, state_manager, project_manager are passed as references (will update)
        - arduino_manager is initially None and updated via _sync_recording_service_arduino()
          when setup_arduino() is called.
        """
        # Store controller reference so RecordingService can access current recorder/managers
        self.recording_service = RecordingService(
            controller=self,  # Pass self to access current recorder/arduino_manager
            state_manager=self.state_manager,
            project_manager=self.project_manager,
            root=self.root,
        )

        # Inject UI callbacks for view updates
        self.recording_service.set_ui_callbacks(
            {
                "show_error": lambda title, msg: self.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR, {"title": title, "message": msg}
                ),
                "update_button_state": lambda btn, state: self.ui_event_bus.publish_event(
                    Events.UI_UPDATE_BUTTON_STATE, {"button_name": btn, "state": state}
                ),
                "set_status": lambda msg: self.ui_event_bus.publish_event(
                    Events.UI_SET_STATUS, {"message": msg}
                ),
                "stop_recording_callback": self.stop_recording,
            }
        )

    def _init_analysis_service(self) -> None:
        """
        Initialize AnalysisService for processing orchestration.

        Phase 3: Extracts video processing orchestration logic from MainViewModel.
        AnalysisService now handles batch processing and coordinates with existing
        _process_single_video methods.
        """
        from zebtrack.analysis.analysis_service import AnalysisService

        self.analysis_service = AnalysisService()

        log.info(
            "controller.init_analysis_service.complete",
            service=type(self.analysis_service).__name__,
        )

    def _init_video_processing_service(self) -> None:
        """
        Initialize VideoProcessingService for video processing orchestration.

        Phase 7.2: Extracts video processing logic (tracking, single video workflow)
        from MainViewModel into dedicated service layer.
        """
        self.video_processing_service = VideoProcessingService(
            detector=self.detector,
            recorder=self.recorder,
            project_manager=self.project_manager,
            state_manager=self.state_manager,
            ui_coordinator=self.ui_coordinator,
            root=self.root,
            view=self.view,
            cancel_event=self.cancel_event,
        )

        log.info(
            "controller.init_video_processing_service.complete",
            service=type(self.video_processing_service).__name__,
        )

    # Phase 7.1: Generic event dispatcher mapping (consolidates 32 handlers into declarative config)
    _EVENT_METHOD_MAPPING: ClassVar[dict] = {
        # Recording events
        Events.RECORDING_START: ("start_recording", ["day", "group", "cobaia"], "kwargs_get"),
        Events.RECORDING_STOP: ("stop_recording", [], "no_params"),
        Events.RECORDING_TRIGGER: ("trigger_recording", ["event_code"], "kwargs_get"),
        # Project events
        Events.PROJECT_CREATE: ("create_project_workflow", None, "kwargs_all"),
        Events.PROJECT_OPEN: ("open_project_workflow", ["project_path"], "positional"),
        Events.PROJECT_CLOSE: ("close_project", [], "no_params"),
        Events.PROJECT_PROCESS_VIDEOS: (
            "process_pending_project_videos",
            ["video_paths"],
            "kwargs_get",
        ),
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
        # Video processing events
        Events.VIDEO_ANALYZE_SINGLE: (
            "start_single_video_workflow",
            ["video_path", "config"],
            "positional",
        ),
        Events.VIDEO_CANCEL_ANALYSIS: ("cancel_current_analysis", [], "no_params"),
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
        """Factory to create event-specific dispatcher closures.

        Phase 7.1: Generic dispatcher that replaces 32 individual _handle_* methods.

        Args:
            event_name: The event identifier (e.g., Events.RECORDING_START)

        Returns:
            Callable that extracts params from event data and calls controller method
        """
        method_name, param_names, mode = self._EVENT_METHOD_MAPPING[event_name]

        def dispatcher(data: dict) -> None:
            """Generic event handler that delegates to controller method."""
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
        """Handler for the special single video zone definition event."""
        video_path = data.get("video_path")
        config = data.get("config")
        if video_path and config:
            self.view.setup_zone_definition_for_single_video(video_path, config)

    def _determine_processing_mode(self) -> ProcessingMode:
        """Inspect current detector/settings state to infer active mode."""

        detector = getattr(self, "detector", None)
        if detector and hasattr(detector, "is_single_subject_mode"):
            try:
                if detector.is_single_subject_mode():
                    return ProcessingMode.SINGLE_SUBJECT
            except Exception:  # pragma: no cover - defensive telemetry
                log.warning(
                    "controller.processing_mode.detector_probe_failed",
                    exc_info=True,
                )

        try:
            if bool(settings.tracking.use_single_subject_tracker):
                return ProcessingMode.SINGLE_SUBJECT
        except AttributeError:  # pragma: no cover - optional settings
            pass

        return ProcessingMode.MULTI_TRACK

    def _publish_processing_mode(
        self,
        *,
        source: str,
        force: bool = False,
        mode_override: ProcessingMode | None = None,
    ) -> ProcessingReport:
        """Notify the GUI about the current processing mode when it changes."""

        mode = mode_override or self._determine_processing_mode()
        if not force and mode == getattr(self, "_active_processing_mode", None):
            return ProcessingReport(mode=mode, source=source)

        self._active_processing_mode = mode
        report = ProcessingReport(mode=mode, source=source)
        view = getattr(self, "view", None)
        if view and hasattr(view, "update_processing_mode"):
            self._schedule_on_ui(view.update_processing_mode, report)
        return report

    def refresh_project_views(
        self,
        reason: str | None = None,
        *,
        append_summary: bool = False,
        immediate: bool = False,
    ) -> None:
        """Request a refresh of project-related UI components on the main thread."""

        if not getattr(self, "view", None):
            return

        refresh_fn = getattr(self.view, "refresh_project_views", None)
        if not callable(refresh_fn):
            return

        self._schedule_on_ui(
            refresh_fn,
            reason,
            append_summary=append_summary,
            immediate=immediate,
        )

    def _clear_external_trigger_wait(self):
        if not self._pending_external_trigger:
            return

        self._pending_external_trigger = None
        self.ui_event_bus.publish_event(Events.UI_CLEAR_EXTERNAL_TRIGGER_NOTICE)
        self.ui_event_bus.publish_event(
            Events.UI_UPDATE_BUTTON_STATE, {"button_name": "start_rec", "state": "normal"}
        )
        self.ui_event_bus.publish_event(
            Events.UI_UPDATE_BUTTON_STATE, {"button_name": "stop_rec", "state": "disabled"}
        )
        self.ui_event_bus.publish_event(Events.UI_SET_STATUS, {"message": "Pronto."})

    def log_arduino_event(self, message: str):
        log.info("controller.arduino.log", message=message)
        self.ui_event_bus.publish_event(Events.UI_APPEND_ARDUINO_LOG, {"message": message})

    def on_arduino_status_change(self, connected: bool, port: str | None):
        log.info("controller.arduino.status", connected=connected, port=port)
        self.ui_event_bus.publish_event(
            Events.UI_UPDATE_ARDUINO_STATUS, {"connected": connected, "port": port}
        )

    def on_arduino_command_sent(self, command: int, success: bool, source: str):
        label_text = str(command) if success else f"{command} (falha)"
        self.ui_event_bus.publish_event(
            Events.UI_SET_STATUS, {"message": f"Comando Arduino: {label_text}"}
        )

    def on_arduino_event(self, event_code: int):
        log.info("controller.arduino.event_received", code=event_code)
        self.log_arduino_event(f"Evento {event_code} recebido do Arduino.")

        if event_code == 1:
            if self._pending_external_trigger:
                self.log_arduino_event("Sinal externo recebido. Iniciando gravação...")
                self.trigger_recording(event_code)
            else:
                log.warning("controller.arduino.event.unexpected_start")
        elif event_code == 0:
            if self.is_recording or self._pending_external_trigger:
                self.log_arduino_event("Sinal externo solicitando parada.")
                self.stop_recording()
        else:
            log.info("controller.arduino.event.ignored", code=event_code)

    def trigger_recording(self, event_code: int | None = None):
        if not self._pending_external_trigger:
            log.warning("controller.external_trigger.no_pending", code=event_code)
            return

        context = self._pending_external_trigger
        self._pending_external_trigger = None

        if self.ui_event_bus:
            self.ui_event_bus.publish_event(Events.UI_CLEAR_EXTERNAL_TRIGGER_NOTICE)
        project_data = self.project_manager.project_data or {}
        self._schedule_recording(context, project_data, trigger_source="external")

    def _schedule_recording(
        self,
        context: dict,
        project_data: dict,
        *,
        trigger_source: str,
    ) -> None:
        """Delegate to RecordingService (Phase 2.2)."""
        # Inject camera dimensions into context
        camera_width = getattr(self.view.camera, "actual_width", None)
        camera_height = getattr(self.view.camera, "actual_height", None)
        context["camera_width"] = camera_width
        context["camera_height"] = camera_height

        self.recording_service.schedule_recording(
            context, project_data, trigger_source=trigger_source
        )

    def close_project(self):
        # Restore global defaults before clearing project state
        self._restore_global_model_defaults()

        # Reset project manager (pass StateManager reference)
        self.project_manager = ProjectManager(state_manager=self.state_manager)

        # Update StateManager: project closed
        self.state_manager.update_project_state(
            source="controller.close_project",
            project_path=None,
            project_data={},
            active_zone_video=None,
        )

        # _create_welcome_frame handles all UI cleanup
        self.ui_event_bus.publish_event(Events.UI_NAVIGATE_TO_WELCOME)

    def create_project_workflow(self, **kwargs):
        """
        Create project workflow orchestration.

        Phase 5: Refactored to use ProjectWorkflowService for orchestration.
        Controller now focuses on UI updates and detector setup.
        """
        # Update global model defaults before creation
        self.project_workflow_service.set_global_model_defaults(
            active_weight=self.active_weight_name or None,
            use_openvino=self.use_openvino,
        )

        # Orchestrate project creation via service
        result = self.project_workflow_service.create_project(
            setup_detector_callback=self.setup_detector,
            active_weight_setter=self.set_active_weight,
            use_openvino_setter=self.set_openvino_usage,
            **kwargs,
        )

        # Handle failure
        if not result["success"]:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Configuração Inválida", "message": result["error_message"]},
            )
            return

        # Extract result data
        animal_method = result["animal_method"]
        wizard_metadata = result["wizard_metadata"]

        # Setup detector with the resolved animal method
        if self.setup_detector(temp_animal_method=animal_method):
            # Update UI
            self.ui_event_bus.publish_event(Events.UI_NAVIGATE_TO_PROJECT_VIEW, {})
            self.ui_event_bus.publish_event(
                Events.UI_UPDATE_OPENVINO_CHECKBOX, {"is_checked": self.use_openvino}
            )
            self.ui_event_bus.publish_event(
                Events.UI_SET_ACTIVE_WEIGHT, {"weight_name": self.active_weight_name}
            )
            self.update_openvino_status()

            # Show post-creation guide if wizard metadata provided
            if wizard_metadata:
                self._show_post_creation_guide(wizard_metadata)
        else:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro", "message": "Falha ao configurar o detector."},
            )

    def _show_post_creation_guide(self, wizard_metadata: dict):
        """
        Display a contextual onboarding message after project creation.

        Phase 5: Refactored to use ProjectWorkflowService for guide generation.
        """
        # Check view-level suppression flag
        if getattr(self.view, "suppress_post_creation_guide", False):
            log.info("controller.post_creation_guide.skipped", reason="view_flag")
            return

        # Generate guide content via service
        guide = self.project_workflow_service.generate_post_creation_guide(
            wizard_metadata=wizard_metadata,
            check_suppression=True,
        )

        # Display guide if generated
        if guide:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO, {"title": guide["title"], "message": guide["message"]}
            )

    def _restore_detector_settings(self, saved_detector_config: dict) -> None:
        """
        Restore detector settings from saved configuration.

        Phase 6: Delegates to DetectorService.

        Args:
            saved_detector_config: Saved detector configuration from project
        """
        self.detector_service.restore_detector_settings(saved_detector_config)

    def _setup_zones_from_project(self) -> None:
        """
        Setup zones from project data.

        Phase 5: Extracted from open_project_workflow for use as callback.
        """
        # Setup zones in detector
        self.setup_detector_zones()

        # Update zone visualization in GUI
        self.ui_event_bus.publish_event(Events.UI_REDRAW_ZONES)
        self.ui_event_bus.publish_event(Events.UI_UPDATE_ZONE_LIST)

    def open_project_workflow(self, project_path):
        """
        Load project and configure everything automatically.

        Phase 5: Refactored to use ProjectWorkflowService for orchestration.
        Controller now focuses on UI updates and detector/zone setup.
        """
        # Update global model defaults before opening
        self.project_workflow_service.set_global_model_defaults(
            active_weight=self.active_weight_name or None,
            use_openvino=self.use_openvino,
        )

        # Orchestrate project opening via service
        result = self.project_workflow_service.open_project(
            project_path=project_path,
            active_weight_setter=self.set_active_weight,
            use_openvino_setter=self.set_openvino_usage,
            restore_detector_callback=self._restore_detector_settings,
            setup_zones_callback=self._setup_zones_from_project,
        )

        # Handle failure
        if not result["success"]:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro", "message": result["error_message"]},
            )
            return False

        # Extract result data
        project_info = result["project_info"]

        # Update UI to reflect restored state
        self.ui_event_bus.publish_event(
            Events.UI_UPDATE_OPENVINO_CHECKBOX, {"is_checked": self.use_openvino}
        )
        self.ui_event_bus.publish_event(
            Events.UI_SET_ACTIVE_WEIGHT, {"weight_name": self.active_weight_name}
        )
        self.update_openvino_status()

        # Initialize detector
        if not self.setup_detector():
            log.warning("controller.load_project.detector_setup_failed")
        else:
            # Load project view
            self.ui_event_bus.publish_event(Events.UI_NAVIGATE_TO_PROJECT_VIEW, {})

        # Display success message
        self.ui_event_bus.publish_event(
            Events.UI_SHOW_INFO,
            {
                "title": "Projeto Carregado",
                "message": f"Projeto '{project_info['name']}' carregado com sucesso!\n\n"
                f"• Vídeos: {project_info['videos_count']}\n"
                f"• Arena Principal: {project_info['zone_status']}\n"
                f"• ROIs: {project_info['roi_count']}\n"
                f"• Peso: {project_info['active_weight']}\n"
                f"• OpenVINO: {'✓' if project_info['use_openvino'] else '✗'}",
            },
        )

        log.info(
            "controller.load_project.complete",
            project=project_info["name"],
            videos=project_info["videos_count"],
        )

        return True

    def setup_detector(self, temp_animal_method: str | None = None) -> bool:
        """
        Initializes the detector instance based on the animal method selection.

        Phase 6: Delegates to DetectorService.

        Args:
            temp_animal_method: Temporary override for animal detection method
                ('det' or 'seg'). If None, uses global settings.
        """
        success, error = self.detector_service.initialize_detector(
            animal_method=temp_animal_method,
            use_openvino=self.use_openvino,
            active_weight_name=self.active_weight_name,
        )

        if not success:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro de Detector",
                    "message": error or "Falha ao inicializar o detector",
                },
            )
            return False

        return True

    def _is_arduino_connected(self) -> bool:
        """Checks whether there is an active Arduino connection."""
        if not self.arduino_manager:
            return False
        return self.arduino_manager.is_connected()

    def setup_arduino(self) -> bool:
        """Ensures the Arduino connection is ready when the project requests it."""
        project_data = getattr(self.project_manager, "project_data", {}) or {}
        use_arduino = bool(project_data.get("use_arduino"))
        if not use_arduino:
            log.debug("controller.arduino.disabled")
            if self.arduino_manager:
                self.arduino_manager.disconnect()
                # Update StateManager: Arduino disconnected
                self.state_manager.update_recording_state(
                    source="controller.setup_arduino",
                    arduino_connected=False,
                    arduino_port=None,
                )
            return False

        port = (project_data.get("arduino_port") or "").strip()
        if not port:
            log.warning("controller.arduino.no_port_configured")
            return False

        manager = self._get_arduino_manager()
        if manager.is_connected() and manager.current_port() == port:
            log.debug("controller.arduino.already_connected", port=port)
            self.arduino = manager.arduino
            return True

        baud_rate = settings.arduino.baud_rate
        if manager.connect(port, baud_rate):
            self.arduino = manager.arduino
            # Update StateManager: Arduino connected
            self.state_manager.update_recording_state(
                source="controller.setup_arduino",
                arduino_connected=True,
                arduino_port=port,
            )
            return True

        # Update StateManager: Arduino connection failed
        self.state_manager.update_recording_state(
            source="controller.setup_arduino",
            arduino_connected=False,
            arduino_port=None,
        )
        return False

    def setup_detector_zones(self):
        """
        Loads zone data from project and sets it on the detector instance.

        Phase 6: Delegates zone configuration to DetectorService.
        """
        # Delegate zone configuration to service
        success = self.detector_service.configure_zones()

        if not success:
            log.warning("controller.setup_zones.failed")
            return

        # UI logic remains in controller
        zone_data = self.project_manager.get_zone_data()
        if not zone_data.polygon:
            if self.project_manager.get_project_type() == "pre-recorded":
                self.ui_event_bus.publish_event(Events.UI_SELECT_TAB, {"tab_name": "zone_tab"})
                first_video = self.project_manager.get_next_video()
                if first_video:
                    self.ui_event_bus.publish_event(
                        Events.UI_DISPLAY_VIDEO_FRAME, {"video_path": first_video}
                    )
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Configuração Necessária",
                        "message": "Erro: A área de processamento principal (aquário) não foi "
                        "definida. Por favor, defina-a na aba 'Configuração de Zonas' "
                        "antes de continuar.",
                    },
                )

    # --- New Methods for Weight Management ---

    def _safe_get_default_weight(self) -> tuple[str | None, dict | None]:
        manager = getattr(self, "weight_manager", None)
        if manager is None:
            return None, None
        try:
            result = manager.get_default_weight()
        except Exception:
            log.warning("controller.default_weight.safe_get_failed", exc_info=True)
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

    def add_new_weight(self, path: str, set_as_default: bool, weight_type: str | None = None):
        """Add a new weight with type classification."""
        self.weight_manager.add_weight(path, set_as_default, weight_type)
        new_name = os.path.basename(path)
        # Refresh UI
        self.ui_event_bus.publish_event(
            Events.UI_UPDATE_WEIGHTS_LIST, {"weights": self.get_all_weight_names()}
        )
        self.ui_event_bus.publish_event(Events.UI_SET_ACTIVE_WEIGHT, {"weight_name": new_name})
        self.set_active_weight(new_name)  # This will also trigger conversion check

    def delete_weight(self, name: str):
        self.weight_manager.delete_weight(name)
        # Refresh UI
        self.ui_event_bus.publish_event(
            Events.UI_UPDATE_WEIGHTS_LIST, {"weights": self.get_all_weight_names()}
        )
        name, _ = self._safe_get_default_weight()
        self.ui_event_bus.publish_event(Events.UI_SET_ACTIVE_WEIGHT, {"weight_name": name})
        self.set_active_weight(name, None)

    def set_active_weight(self, name: str | None, dialog=None):
        candidate = name or ""
        available = set(self.get_all_weight_names())

        if candidate and candidate in available:
            self.active_weight_name = candidate
            log.info("controller.active_weight.set", name=candidate)
            self.ui_event_bus.publish_event(Events.UI_SET_ACTIVE_WEIGHT, {"weight_name": candidate})
            self.update_openvino_status(dialog)
            if self.use_openvino:
                self.convert_active_weight_to_openvino(dialog)
        else:
            if candidate:
                log.warning("controller.active_weight.not_found", name=name)
            self.active_weight_name = ""
            self.ui_event_bus.publish_event(Events.UI_SET_ACTIVE_WEIGHT, {"weight_name": ""})
            self.update_openvino_status(dialog)

        if not self._using_project_overrides:
            self._global_model_defaults["active_weight"] = self.active_weight_name or None

    def set_openvino_usage(self, use_openvino: bool, dialog=None):
        self.use_openvino = bool(use_openvino)
        log.info("controller.openvino_usage.set", enabled=self.use_openvino)
        self.ui_event_bus.publish_event(
            Events.UI_UPDATE_OPENVINO_CHECKBOX, {"is_checked": self.use_openvino}
        )
        if self.use_openvino and self.active_weight_name:
            # Trigger conversion if switching to OpenVINO and model isn't converted
            self.convert_active_weight_to_openvino(dialog)
        self.update_openvino_status(dialog)

        if not self._using_project_overrides:
            self._global_model_defaults["use_openvino"] = self.use_openvino

    def convert_active_weight_to_openvino(self, dialog):
        """
        Convert the active weight to OpenVINO format.

        Delegates conversion logic to ModelService (Phase 2.1).
        MainViewModel only handles UI updates and status feedback.
        """
        if not self.active_weight_name:
            return

        if self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_SET_STATUS,
                {"message": f"Convertendo {self.active_weight_name} para OpenVINO..."},
            )

        # Delegate conversion to ModelService
        self.model_service.convert_to_openvino(self.active_weight_name)

        self.update_openvino_status(dialog)
        if self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_SET_STATUS,
                {"message": "Verificação de conversão concluída. Pronto."},
            )

    def update_openvino_status(self, dialog=None):
        """Updates the status label in the GUI based on the current state."""
        status = self.get_openvino_status()
        if dialog:
            dialog.update_openvino_status_label(status)
        self.ui_event_bus.publish_event(Events.UI_UPDATE_OPENVINO_STATUS, {"status": status})

    @property
    def are_project_overrides_active(self) -> bool:
        return bool(self._using_project_overrides)

    def get_global_model_defaults(self) -> dict:
        return {
            "active_weight": self._global_model_defaults.get("active_weight"),
            "use_openvino": self._global_model_defaults.get("use_openvino", False),
        }

    def _get_project_data_dict(self) -> dict:
        project_data = getattr(self.project_manager, "project_data", None)
        if not isinstance(project_data, dict):
            project_data = {} if not project_data else dict(project_data)
            self.project_manager.project_data = project_data
        return project_data

    def _ensure_project_overrides_record(self) -> dict:
        project_data = self._get_project_data_dict()
        overrides = project_data.get("model_overrides")
        if not isinstance(overrides, dict):
            overrides = {"active_weight": None, "use_openvino": None}
            project_data["model_overrides"] = overrides
        return overrides

    def has_project_override_settings(self) -> bool:
        if not getattr(self.project_manager, "project_path", None):
            return False
        overrides = self._ensure_project_overrides_record()
        return any(value not in (None, "", "inherit") for value in overrides.values())

    def get_calibration_scope_info(self) -> dict:
        project_path = getattr(self.project_manager, "project_path", None)
        project_loaded = bool(project_path)
        project_name = None
        if project_loaded and hasattr(self.project_manager, "get_project_name"):
            try:
                project_name = self.project_manager.get_project_name()
            except Exception:  # pragma: no cover - defensive
                project_name = None

        overrides_active = self.has_project_override_settings()
        inheriting_globals = project_loaded and not overrides_active
        scope = "project" if project_loaded and self._using_project_overrides else "global"

        if scope == "project":
            label = f"Escopo: Projeto ({project_name})" if project_name else "Escopo: Projeto"
            if overrides_active:
                detail = (
                    "Este projeto usa overrides salvos. Ajustes nesta janela são "
                    "persistidos apenas neste projeto."
                )
            else:
                detail = (
                    "Este projeto está herdando os padrões globais. Ao salvar "
                    "aqui, os valores se tornam overrides específicos."
                )
        else:
            label = "Escopo: Configuração Global"
            if project_loaded:
                detail = (
                    "Alterações atualizam o padrão global. Use a ação de cópia para "
                    "fixar estes valores no projeto atual."
                )
            else:
                detail = "Nenhum projeto carregado; ajustes atualizam os padrões globais."

        return {
            "scope": scope,
            "project_loaded": project_loaded,
            "project_name": project_name,
            "overrides_active": overrides_active,
            "inheriting_globals": inheriting_globals,
            "label": label,
            "detail": detail,
        }

    def get_current_detector_parameters(self) -> dict[str, float]:
        """
        Return detector thresholds, falling back to saved or default values.

        Phase 6: Delegates to DetectorService.

        Returns parameters with long-form names for backward compatibility.
        """
        params = self.detector_service.get_detector_parameters()
        # Normalize conf_threshold to confidence_threshold for backward compatibility
        if "conf_threshold" in params:
            params["confidence_threshold"] = params.pop("conf_threshold")
        return params

    def get_factory_detector_parameters(self) -> dict[str, float]:
        """
        Return detector thresholds defined in config.yaml without overrides.

        Phase 6: Delegates to DetectorService.

        Returns parameters with long-form names for backward compatibility.
        """
        params = self.detector_service.get_factory_detector_parameters()
        # Normalize conf_threshold to confidence_threshold for backward compatibility
        if "conf_threshold" in params:
            params["confidence_threshold"] = params.pop("conf_threshold")
        return params

    def update_detector_parameters(
        self,
        params: dict[str, float],
        *,
        reset_overrides: bool = False,
    ) -> bool:
        """
        Apply detector threshold updates and persist them when possible.

        Phase 6: Delegates to DetectorService.
        """
        try:
            success = self.detector_service.update_tracking_parameters(
                params=params, reset_overrides=reset_overrides
            )

            if success:
                self.ui_event_bus.publish_event(
                    Events.UI_SET_STATUS,
                    {"message": "Parâmetros do detector atualizados."},
                )

            return success
        except ValueError as e:
            log.error("controller.detector.update.validation_failed", error=str(e))
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro de Validação", "message": str(e)},
            )
            return False

    def _persist_project_model_settings(self, weight: str | None, use_openvino: bool) -> dict:
        """
        Persist model settings to project configuration.

        Phase 2.1: Uses ProjectService for data structure management,
        but delegates actual persistence to ProjectManager to maintain
        backward compatibility with existing test mocks.
        """
        project_data = self._get_project_data_dict()
        overrides = self._ensure_project_overrides_record()

        # Update overrides (business logic extracted to helper)
        overrides["active_weight"] = weight
        overrides["use_openvino"] = use_openvino
        project_data["active_weight"] = weight
        project_data["use_openvino"] = bool(use_openvino)

        # Update in-memory state
        self.project_manager.project_data = project_data

        # Delegate persistence to ProjectManager (maintains test compatibility)
        if getattr(self.project_manager, "project_path", None):
            self.project_manager.save_project()

        return overrides

    def copy_global_model_settings_to_project(self) -> tuple[str | None, bool] | None:
        if not getattr(self.project_manager, "project_path", None):
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Nenhum Projeto",
                    "message": "Abra um projeto antes de copiar configurações globais.",
                },
            )
            return None

        defaults = self.get_global_model_defaults()
        weight = defaults.get("active_weight") or (self.active_weight_name or None)
        use_openvino = bool(defaults.get("use_openvino", False))

        overrides = self._persist_project_model_settings(weight, use_openvino)

        message = "Configurações globais aplicadas ao projeto."
        self.ui_event_bus.publish_event(Events.UI_SET_STATUS, {"message": message})
        self.refresh_project_views(reason=message, append_summary=True)

        return overrides.get("active_weight"), bool(overrides.get("use_openvino"))

    def save_current_calibration_to_project(self) -> tuple[str | None, bool] | None:
        if not getattr(self.project_manager, "project_path", None):
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Nenhum Projeto",
                    "message": "Abra um projeto antes de salvar overrides de calibração.",
                },
            )
            return None

        overrides = self._persist_project_model_settings(
            self.active_weight_name or None,
            bool(self.use_openvino),
        )

        # Garantir que o estado em memória reflita os overrides recém-salvos
        self.apply_project_model_overrides(overrides)

        message = "Overrides do projeto atualizados a partir desta calibração."
        self.ui_event_bus.publish_event(Events.UI_SET_STATUS, {"message": message})
        self.refresh_project_views(reason=message, append_summary=True)

        return overrides.get("active_weight"), bool(overrides.get("use_openvino"))

    def _apply_model_settings(
        self, weight_name: str | None, use_openvino: bool, dialog=None
    ) -> None:
        if weight_name:
            self.set_active_weight(weight_name, dialog)
        else:
            self.set_active_weight("", dialog)
        self.set_openvino_usage(bool(use_openvino), dialog)

    def resolve_project_model_settings(
        self, overrides: dict | None = None
    ) -> tuple[str | None, bool]:
        project_data = getattr(self.project_manager, "project_data", {}) or {}
        base_overrides = project_data.get("model_overrides") or {}
        if overrides is not None:
            merged_overrides = base_overrides.copy()
            merged_overrides.update(overrides)
        else:
            merged_overrides = base_overrides

        weight_override = merged_overrides.get("active_weight")
        if isinstance(weight_override, str):
            weight_override = weight_override.strip() or None

        openvino_override = merged_overrides.get("use_openvino")
        if isinstance(openvino_override, str):
            lowered = openvino_override.strip().lower()
            if lowered in {"", "inherit", "auto"}:
                openvino_override = None
            else:
                openvino_override = lowered in {"true", "1", "yes", "on"}

        resolved_weight = weight_override
        if not resolved_weight:
            resolved_weight = project_data.get("active_weight") or None
        if not resolved_weight:
            resolved_weight = self._global_model_defaults.get("active_weight")
        if not resolved_weight:
            default_weight, _ = self._safe_get_default_weight()
            resolved_weight = default_weight

        available_weights = set(self.get_all_weight_names())
        if resolved_weight and resolved_weight not in available_weights:
            log.warning(
                "controller.project_overrides.weight_missing",
                weight=resolved_weight,
                available=list(available_weights),
            )
            fallback_weight = self._global_model_defaults.get("active_weight")
            if fallback_weight and fallback_weight in available_weights:
                resolved_weight = fallback_weight
            else:
                default_weight, _ = self._safe_get_default_weight()
                resolved_weight = default_weight if default_weight else None

        if openvino_override is None:
            if project_data.get("use_openvino") is not None:
                resolved_openvino = bool(project_data.get("use_openvino"))
            else:
                resolved_openvino = bool(self._global_model_defaults.get("use_openvino", False))
        else:
            resolved_openvino = bool(openvino_override)

        return resolved_weight, resolved_openvino

    def apply_project_model_overrides(
        self, overrides: dict | None = None
    ) -> tuple[str | None, bool]:
        if not getattr(self.project_manager, "project_data", None):
            return self.active_weight_name or None, bool(self.use_openvino)

        resolved_weight, resolved_openvino = self.resolve_project_model_settings(overrides)

        self._using_project_overrides = True
        self._apply_model_settings(resolved_weight, resolved_openvino)

        updated = False
        if self.project_manager.project_data.get("active_weight") != resolved_weight:
            self.project_manager.project_data["active_weight"] = resolved_weight
            updated = True
        if self.project_manager.project_data.get("use_openvino") != resolved_openvino:
            self.project_manager.project_data["use_openvino"] = resolved_openvino
            updated = True

        if updated and getattr(self.project_manager, "project_path", None):
            self.project_manager.save_project()

        return resolved_weight, resolved_openvino

    def save_project_model_overrides(
        self, active_weight_override: str | None, use_openvino_override: bool | None
    ) -> tuple[str | None, bool]:
        if not getattr(self.project_manager, "project_path", None):
            log.warning("controller.project_overrides.no_project_loaded")
            return self.active_weight_name or None, self.use_openvino

        overrides = self.project_manager.project_data.setdefault(
            "model_overrides",
            {"active_weight": None, "use_openvino": None},
        )
        overrides["active_weight"] = active_weight_override or None
        overrides["use_openvino"] = use_openvino_override

        resolved_weight, resolved_openvino = self.apply_project_model_overrides(overrides)

        self.project_manager.project_data["model_overrides"] = overrides
        self.project_manager.save_project()

        return resolved_weight, resolved_openvino

    def _restore_global_model_defaults(self) -> None:
        target_weight = self._global_model_defaults.get("active_weight")
        target_openvino = bool(self._global_model_defaults.get("use_openvino", False))
        self._using_project_overrides = False
        self._apply_model_settings(target_weight, target_openvino)

    @contextmanager
    def global_calibration_session(self):
        previous_flag = self._using_project_overrides
        self._using_project_overrides = False
        try:
            yield
        finally:
            self._global_model_defaults["active_weight"] = self.active_weight_name or None
            self._global_model_defaults["use_openvino"] = self.use_openvino
            self._using_project_overrides = previous_flag
            if previous_flag and getattr(self.project_manager, "project_path", None):
                self.apply_project_model_overrides()

    def run_aquarium_detection(
        self,
        video_path: str | None = None,
        stabilization_frames: int = 10,
        temp_aquarium_method: str | None = None,
    ):
        """Runs the aquarium detection model on the specified or first project video.

        Args:
            video_path: Path to video file, if None uses next project video
            stabilization_frames: Number of frames to analyze for stabilization
            temp_aquarium_method: Temporary override for aquarium detection method
                ('det' or 'seg'). If None, uses global settings.
        """
        log.info("controller.aquarium_detection.start")
        self.ui_event_bus.publish_event(
            Events.UI_SET_STATUS,
            {"message": "Detectando aquário, por favor aguarde..."},
        )
        self._publish_processing_mode(
            source="calibration.aquarium.start",
            force=True,
            mode_override=ProcessingMode.SINGLE_SUBJECT,
        )

        try:
            if video_path is None:
                video_path = self.project_manager.get_next_video()

            if not video_path:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Aviso",
                        "message": "Nenhum vídeo foi encontrado para a detecção.",
                    },
                )
                return

            self.project_manager.set_active_zone_video(video_path)

            # Display the first frame of the video as a preview background
            self.ui_event_bus.publish_event(
                Events.UI_DISPLAY_VIDEO_FRAME, {"video_path": video_path}
            )

            # Use selected aquarium method and get appropriate weight
            # Use temporary override if provided, otherwise use global settings
            aquarium_method = temp_aquarium_method or settings.model_selection.aquarium_method
            model_path = self.weight_manager.get_weight_path_by_method(aquarium_method, "aquarium")

            if not model_path:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro",
                        "message": f"Não foi possível encontrar um modelo {aquarium_method} para "
                        "detecção do aquário.",
                    },
                )
                return

            detector = AquariumDetector(model_path=model_path, mode=aquarium_method)
            polygons = detector.detect_aquariums(
                video_path, stabilization_frames=stabilization_frames
            )

            if not polygons:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Detecção Automática Falhou",
                        "message": "Não foi possível identificar uma área de aquário estável "
                        "no vídeo. Isso pode ocorrer devido a reflexos, pouca luz ou "
                        "movimento excessivo da câmera.\n\nPor favor, defina a área "
                        "do aquário manualmente utilizando a ferramenta 'Desenhar "
                        "Polígono Principal'.",
                    },
                )
                return

            main_polygon = polygons[0]
            log.info(
                "controller.aquarium_detection.success",
                polygon_points=len(main_polygon),
            )
            # The view will handle drawing this polygon interactively
            self.ui_event_bus.publish_event(
                Events.UI_SETUP_INTERACTIVE_POLYGON, {"polygon": main_polygon}
            )

        except Exception as e:
            log.error("controller.aquarium_detection.error", exc_info=True)
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro na Detecção",
                    "message": f"Ocorreu um erro ao detectar o aquário: {e}",
                },
            )
        finally:
            self._publish_processing_mode(
                source="calibration.aquarium.complete",
                force=True,
            )
            self.ui_event_bus.publish_event(Events.UI_SET_STATUS, {"message": "Pronto."})

    def set_main_arena_polygon(self, points: list) -> bool:
        """Salva polígono com validações robustas"""
        try:
            # Validação 1: Pontos válidos
            if not points or len(points) < 3:
                log.error(
                    "controller.polygon.invalid_points",
                    count=len(points) if points else 0,
                )
                return False

            # Validação 2: Projeto existe
            if not self.project_manager.project_path:
                log.error("controller.polygon.no_project")
                # Para single video workflow, cria projeto temporário
                if (
                    hasattr(self.view, "pending_single_video_path")
                    and self.view.pending_single_video_path
                ):
                    import tempfile

                    temp_dir = tempfile.mkdtemp(prefix="zebtrack_temp_")
                    self.project_manager.project_path = temp_dir
                    self.project_manager.project_data = {
                        "project_name": "Temporary Single Video Project",
                        "project_type": "single_video",
                        "detection_zones": {},
                    }
                    log.warning("controller.polygon.created_temp_project", path=temp_dir)
                else:
                    return False

            # Validação 3: Estrutura de dados
            if "detection_zones" not in self.project_manager.project_data:
                self.project_manager.save_zone_data(ZoneData(), persist=False)
                log.info("controller.polygon.initialized_detection_zones")

            # Salva
            self.project_manager.update_main_polygon(points)

            # Força atualização visual
            self.ui_event_bus.publish_event(Events.UI_REDRAW_ZONES, {})

            log.info("controller.polygon.saved", points=len(points))
            return True

        except Exception as e:
            log.error("controller.polygon.save_error", error=str(e))
            return False

    def save_manual_arena(self, polygon_points: list[list[int]]):
        """
        Saves the manually adjusted arena and updates the detector.

        Delegates to ProjectService for persistence (Phase 2.1).
        MainViewModel handles UI coordination and detector updates.
        """
        log.info("controller.arena.save_manual", points_count=len(polygon_points))
        self.update_main_arena(polygon_points)

    def update_main_arena(self, polygon_points: list[list[int]]):
        """
        Updates the main arena polygon in the project's zone data.

        Phase 2.1: Logic simplified but maintains compatibility with existing tests.
        ProjectService methods available for future direct usage.
        """
        log.info("controller.zone.update_arena", points=len(polygon_points))

        # Update in-memory zone data
        zone_data = self.project_manager.get_zone_data()
        zone_data.polygon = polygon_points
        self.project_manager.save_zone_data(zone_data)

        # After updating, we need to reload the zones in the detector
        self.setup_detector_zones()
        log.info("controller.zone.update_arena.success")

    def add_roi_polygon(self, roi_points: list[list[int]], name: str, color: tuple[int, int, int]):
        """Adiciona ROI com validação de sobreposição"""
        try:
            log.info("controller.zone.add_roi", name=name, points=len(roi_points))

            # Critical Fix #4: Add project validation before saving ROI
            if not self.project_manager.project_path:
                log.error("controller.zone.add_roi.no_project", name=name)
                return False

            zone_data = self.project_manager.get_zone_data()

            # Validação 1: Verifica se está dentro da arena principal
            if zone_data.polygon and len(zone_data.polygon) >= 3:
                import cv2
                import numpy as np

                arena_poly = np.array(zone_data.polygon, dtype=np.float32)

                # First pass: adjust points that are slightly outside (likely from
                # snapping)
                adjusted_points = []
                # Calculate arena centroid once (convert to native Python float)
                centroid_x = float(np.mean(arena_poly[:, 0]))
                centroid_y = float(np.mean(arena_poly[:, 1]))

                for point in roi_points:
                    px, py = float(point[0]), float(point[1])
                    # True returns signed distance
                    result = cv2.pointPolygonTest(arena_poly, (px, py), True)

                    # If point is slightly outside (within 3 pixels), nudge it inside
                    if -3.0 <= result < 0:
                        # Move point toward centroid by 3 pixels
                        dx = centroid_x - px
                        dy = centroid_y - py
                        length = float(np.sqrt(dx * dx + dy * dy))
                        if length > 0:
                            px += (dx / length) * 3.0
                            py += (dy / length) * 3.0

                    # Ensure values are native Python float, not numpy types
                    adjusted_points.append([float(px), float(py)])

                # Second pass: validate adjusted points
                points_outside = 0
                for point in adjusted_points:
                    result = cv2.pointPolygonTest(arena_poly, tuple(point), False)
                    if result < 0:  # Ponto está fora
                        points_outside += 1

                # If adjustment worked, use adjusted points
                if points_outside == 0:
                    roi_points = adjusted_points

                if points_outside > 0:
                    outside_percent = (points_outside / len(roi_points)) * 100
                    log.warning(
                        "controller.roi.outside_arena",
                        name=name,
                        points_outside=points_outside,
                        percent=outside_percent,
                    )

                    if not self.view.ask_ok_cancel(
                        "ROI Fora da Arena",
                        (
                            f"A ROI '{name}' tem {points_outside} pontos "
                            f"({outside_percent:.1f}%) "
                            "fora da arena principal.\n\nDeseja continuar mesmo assim?"
                        ),
                    ):
                        return False

            # Validação 2: Verifica sobreposição com outras ROIs
            for i, existing_roi in enumerate(zone_data.roi_polygons):
                if len(existing_roi) >= 3:
                    # Calcula sobreposição simples verificando pontos
                    overlapping_points = 0

                    existing_poly = np.array(existing_roi, dtype=np.int32)

                    for point in roi_points:
                        result = cv2.pointPolygonTest(existing_poly, tuple(point), False)
                        if result >= 0:  # Ponto está dentro ou na borda
                            overlapping_points += 1

                    if overlapping_points > 0:
                        overlap_percent = (overlapping_points / len(roi_points)) * 100

                        if overlap_percent > 20:  # Mais de 20% de sobreposição
                            existing_name = (
                                zone_data.roi_names[i]
                                if i < len(zone_data.roi_names)
                                else f"ROI_{i + 1}"
                            )
                            log.warning(
                                "controller.roi.overlap",
                                name=name,
                                existing=existing_name,
                                percent=overlap_percent,
                            )

                            if not self.view.ask_ok_cancel(
                                "ROIs Sobrepostas",
                                f"A nova ROI '{name}' tem {overlap_percent:.1f}% de "
                                f"sobreposição com '{existing_name}'.\n\n"
                                "Deseja continuar?",
                            ):
                                return False

            # Adiciona a ROI após validações
            zone_data.roi_polygons.append(roi_points)
            zone_data.roi_names.append(name)
            zone_data.roi_colors.append(color)

            # Save the project and reload the zones in the active detector
            self.project_manager.save_zone_data(zone_data)
            self.setup_detector_zones()
            log.info("controller.zone.add_roi.success", name=name)
            return True

        except Exception as e:
            log.error("controller.zone.add_roi.error", name=name, error=str(e))
            return False

    def can_remove_project_asset(self, video_path: str, asset: str) -> tuple[bool, str | None]:
        """Validate whether a project asset can be safely removed."""

        try:
            asset_type = cast(AssetType, asset)
            return self.project_manager.can_remove_asset(video_path, asset_type)
        except Exception as exc:  # pragma: no cover - defensive logging
            log.error(
                "controller.project_asset.can_remove_failed",
                asset=asset,
                video=video_path,
                error=str(exc),
            )
            return False, "Não foi possível validar a remoção solicitada."

    def delete_project_asset(
        self,
        video_path: str,
        asset: str,
        *,
        delete_source: bool = True,
    ) -> bool:
        """Remove a project asset (arena, ROIs, trajetória, sumário ou vídeo)."""

        try:
            asset_type = cast(AssetType, asset)
            removed = self.project_manager.remove_asset(
                video_path,
                asset_type,
                delete_files=delete_source,
            )
            log.info(
                "controller.project_asset.removal_result",
                asset=asset,
                video=video_path,
                removed=removed,
                delete_source=delete_source,
            )
            return removed
        except Exception as exc:  # pragma: no cover - defensive logging
            log.error(
                "controller.project_asset.remove_failed",
                asset=asset,
                video=video_path,
                error=str(exc),
                exc_info=True,
            )
            return False

    def run_live_calibration(self, temp_aquarium_method: str | None = None):
        """Records a short clip from the live camera and runs aquarium detection.

        Args:
            temp_aquarium_method: Temporary override for aquarium detection method
                ('det' or 'seg'). If None, uses global settings.
        """
        log.info("controller.live_calibration.start")
        if not self.view.camera or not self.view.camera.is_opened():
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro", "message": "A câmera não está disponível ou aberta."},
            )
            return

        temp_video_path = None
        self._publish_processing_mode(
            source="calibration.live.start",
            force=True,
            mode_override=ProcessingMode.SINGLE_SUBJECT,
        )
        try:
            # 1. Create a temporary file for the calibration video
            temp_video_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            temp_video_path = temp_video_file.name
            temp_video_file.close()

            # 2. Record a short clip
            w, h = self.view.camera.actual_width, self.view.camera.actual_height
            fps = settings.video_processing.fps
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(temp_video_path, fourcc, fps, (w, h))

            self.ui_event_bus.publish_event(
                Events.UI_SET_STATUS,
                {"message": "Calibrando... Gravando um pequeno clipe."},
            )

            start_time = time.time()
            while time.time() - start_time < 5:  # Record for 5 seconds
                ret, frame = self.view.camera.get_frame()
                if not ret:
                    break
                writer.write(frame)
            writer.release()
            self.ui_event_bus.publish_event(
                Events.UI_SET_STATUS,
                {"message": "Calibração: Analisando o clipe..."},
            )

            # 3. Run detection on the clip using selected aquarium method
            # Use temporary override if provided, otherwise use global settings
            aquarium_method = temp_aquarium_method or settings.model_selection.aquarium_method
            model_path = self.weight_manager.get_weight_path_by_method(aquarium_method, "aquarium")

            if not model_path:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro",
                        "message": f"Não foi possível encontrar um modelo {aquarium_method} para "
                        "detecção do aquário.",
                    },
                )
                return

            detector = AquariumDetector(model_path=model_path, mode=aquarium_method)
            polygons = detector.detect_aquariums(temp_video_path)

            if not polygons:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Detecção Falhou",
                        "message": "Nenhum aquário foi detectado. Por favor, desenhe a área manualmente.",  # noqa: E501
                    },
                )
                return

            main_polygon = polygons[0]
            self.ui_event_bus.publish_event(
                Events.UI_SETUP_INTERACTIVE_POLYGON, {"polygon": main_polygon}
            )

        except Exception as e:
            log.error("controller.live_calibration.error", exc_info=True)
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro na Calibração", "message": f"Ocorreu um erro: {e}"},
            )
        finally:
            # 4. Clean up the temporary file
            if temp_video_path and os.path.exists(temp_video_path):
                os.remove(temp_video_path)
            self._publish_processing_mode(
                source="calibration.live.complete",
                force=True,
            )
            self.ui_event_bus.publish_event(Events.UI_SET_STATUS, {"message": "Pronto."})

    def start_recording(
        self,
        day: int | None = None,
        group: str | None = None,
        cobaia: str | None = None,
    ):
        """Starts a recording session (live mode) with zone validation."""
        log.info("controller.recording.start")

        # Live recordings rely on project-wide zones, not per-video ones
        self.project_manager.set_active_zone_video(None)

        # Reset any previous waiting state before starting a new session
        self._clear_external_trigger_wait()

        # Enhanced zone validation for Live projects
        if not self._ensure_zones_before_recording():
            return

        # Ensure detector is set up before recording
        if not self.detector:
            if not self.setup_detector():
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {"title": "Erro", "message": "Falha ao configurar detector."},
                )
                return

        # Apply zones to detector
        self.setup_detector_zones()

        # 1. Get recording details
        if not all((day, group, cobaia)):
            # Details not provided, ask user with the new unified dialog
            details = self.view.ask_recording_details_unified()
            if not details:
                log.warning("controller.recording.cancelled_by_user")
                return
            day, group, cobaia = (
                details["day"],
                details["group"],
                details["cobaia"],
            )
        else:
            log.info(
                "controller.recording.details_from_grid",
                day=day,
                group=group,
                cobaia=cobaia,
            )

        # 2. Save the selected day and group for "Smart State Retention"
        self.project_manager.save_last_session_details(day, group)

        # 3. Create output folder with the new naming convention
        folder_name = f"D{day}_G{group}_S{cobaia}"
        output_folder = os.path.join(self.project_manager.project_path, folder_name)
        os.makedirs(output_folder, exist_ok=True)

        project_data = self.project_manager.project_data or {}

        arduino_enabled = False
        if project_data.get("use_arduino"):
            arduino_enabled = self.setup_arduino()
            if not arduino_enabled:
                log.warning(
                    "controller.recording.arduino_unavailable",
                    port=project_data.get("arduino_port"),
                )

        context = {
            "day": day,
            "group": group,
            "cobaia": cobaia,
            "folder_name": folder_name,
            "output_folder": output_folder,
            "arduino_enabled": arduino_enabled,
        }

        arduino_port = (project_data.get("arduino_port") or "").strip()
        if arduino_port:
            context["arduino_port"] = arduino_port

        external_trigger_requested = bool(project_data.get("external_trigger_mode"))
        if external_trigger_requested and not arduino_enabled:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Trigger Externo Indisponível",
                    "message": "O modo de trigger externo exige um Arduino configurado e "
                    "conectado. Verifique o hardware e tente novamente.",
                },
            )
            return

        external_trigger_active = external_trigger_requested and arduino_enabled

        if external_trigger_active:
            self._pending_external_trigger = context
            waiting_message = "Aguardando sinal externo do Arduino para iniciar..."
            if arduino_port:
                waiting_message = f"{waiting_message} (porta {arduino_port})"

            self.ui_event_bus.publish_event(
                Events.UI_SHOW_EXTERNAL_TRIGGER_NOTICE,
                {
                    "folder_name": folder_name,
                    "day": day,
                    "group": group,
                    "cobaia": cobaia,
                    "port": arduino_port,
                },
            )

            self.ui_event_bus.publish_event(
                Events.UI_UPDATE_BUTTON_STATE,
                {"button_name": "start_rec", "state": "disabled"},
            )
            self.ui_event_bus.publish_event(
                Events.UI_UPDATE_BUTTON_STATE,
                {"button_name": "stop_rec", "state": "disabled"},
            )
            self.ui_event_bus.publish_event(Events.UI_SET_STATUS, {"message": waiting_message})
            self.log_arduino_event("Modo trigger externo habilitado. Aguardando sinal do Arduino.")
            return

        self._pending_external_trigger = None
        self._schedule_recording(context, project_data, trigger_source="manual")

    def stop_recording(self):
        """Stops the current recording session (delegates to RecordingService - Phase 2.2)."""
        log.info("controller.recording.stop")

        if self._pending_external_trigger:
            self._clear_external_trigger_wait()

        # Delegate to RecordingService
        self.recording_service.stop_session()

        # Update UI on main thread
        self.ui_event_bus.publish_event(
            Events.UI_UPDATE_BUTTON_STATE, {"button_name": "start_rec", "state": "normal"}
        )
        self.ui_event_bus.publish_event(
            Events.UI_UPDATE_BUTTON_STATE, {"button_name": "stop_rec", "state": "disabled"}
        )

    def _ensure_zones_before_recording(self) -> bool:
        """Ensure project zones are defined (live or non-live) before starting recording.

        Returns True if recording can proceed, False if it should be cancelled.
        """
        # Enhanced zone validation for Live projects
        if self.project_manager.project_path:
            project_type = self.project_manager.get_project_type()
            zone_data = self.project_manager.get_zone_data()

            if project_type == "live" and (not zone_data or not zone_data.polygon):
                log.info("controller.recording.live_zone_validation.start")

                # For Live projects, prompt for automatic calibration
                response = self.view.ask_ok_cancel(
                    "Calibração Necessária",
                    "Deseja fazer calibração automática do aquário?\n"
                    "(Recomendado para projetos ao vivo)",
                )

                if response:
                    # Run auto-calibration
                    self.run_live_calibration()

                    # Check if calibration was successful
                    zone_data = self.project_manager.get_zone_data()
                    if not zone_data or not zone_data.polygon:
                        self.ui_event_bus.publish_event(
                            Events.UI_SHOW_ERROR,
                            {
                                "title": "Calibração Falhou",
                                "message": "Não foi possível detectar o aquário.\nPor favor, desenhe manualmente.",  # noqa: E501
                            },
                        )
                        # Switch to zones tab
                        self.ui_event_bus.publish_event(
                            Events.UI_SELECT_TAB, {"tab_name": "zone_tab"}
                        )
                        return False
                    else:
                        log.info("controller.recording.live_zone_validation.success")
                else:
                    # User declined calibration
                    self.ui_event_bus.publish_event(
                        Events.UI_SHOW_ERROR,
                        {
                            "title": "Zonas Obrigatórias",
                            "message": "Projetos ao vivo requerem definição de zonas.\n"
                            "Defina o polígono principal antes de gravar.",
                        },
                    )
                    return False

            elif not zone_data or not zone_data.polygon:
                # Generic validation for non-Live projects (preserve existing behavior)
                log.warning("controller.recording.no_main_arena")

                response = self.view.ask_ok_cancel(
                    "Arena Principal Não Definida",
                    "O polígono principal do aquário não foi definido.\n\n"
                    "É recomendado definir a arena antes de iniciar gravação.\n"
                    "Deseja definir agora?",
                )

                if response:
                    # Muda para aba de zonas e inicia câmera para calibração
                    self.ui_event_bus.publish_event(Events.UI_SELECT_TAB, {"tab_name": "zone_tab"})

                    self.ui_event_bus.publish_event(
                        Events.UI_SHOW_INFO,
                        {
                            "title": "Defina a Arena Principal",
                            "message": "Por favor:\n"
                            "1. Use a câmera ao vivo para calibrar\n"
                            "2. Use 'Detectar Aquário (Auto)' ou\n"
                            "3. Desenhe manualmente o polígono principal\n"
                            "4. Depois volte para iniciar a gravação",
                        },
                    )
                    return False
                else:
                    # Continua sem arena definida (usando padrão)
                    if not self.view.ask_ok_cancel(
                        "Continuar Sem Arena?",
                        "Deseja continuar a gravação sem arena definida?\n"
                        "(A arena padrão será o frame completo)",
                    ):
                        log.info("controller.recording.cancelled_no_arena")
                        return False

                    log.info("controller.recording.proceeding_without_arena")

        return True

    # --- New Refactored Workflows ---

    def cancel_current_analysis(self):
        """Sets the event to signal the running analysis thread to stop."""
        if self.processing_thread and self.processing_thread.is_alive():
            log.info("controller.analysis.cancel_requested")
            self.cancel_event.set()

    def start_single_video_workflow(self, video_path: str, config: dict):
        """Prepares the UI for zone definition in the single video workflow."""
        log.info("workflow.single_video.setup_start", video=video_path)

        self.project_manager.set_active_zone_video(video_path)

        # Use detection methods from config if provided, otherwise fall back to
        # global settings
        animal_method = config.get("animal_method", settings.model_selection.animal_method)
        animals_per_aquarium = config.get("animals_per_aquarium", 1)

        # Apply OpenVINO setting from config
        use_openvino = config.get("use_openvino", settings.model_selection.use_openvino)
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

    def start_single_video_processing(self, video_path: str, config: dict, zone_data: ZoneData):
        """Starts the actual processing for a single video after zone setup."""
        log.info("workflow.single_video.processing_start", video=video_path)

        self.project_manager.set_active_zone_video(video_path)

        # Register the single video in project_manager for display in UI
        # This allows the video to appear in Main Control and Reports tabs
        video_entry = self.project_manager.find_video_entry(path=video_path)
        if not video_entry:
            log.info("workflow.single_video.registering_video", video=video_path)
            video_name = os.path.splitext(os.path.basename(video_path))[0]

            # Prepare metadata for single video - use config if available
            metadata = {}
            if config:
                # Extract metadata from config if provided
                for key in ["group", "group_display_name", "day", "subject"]:
                    if key in config:
                        metadata[key] = config[key]

            # Set defaults for missing metadata to ensure proper tree display
            if "group" not in metadata:
                metadata["group"] = "single_video"
            if "group_display_name" not in metadata:
                metadata["group_display_name"] = "Vídeo Único"
            if "day" not in metadata:
                metadata["day"] = "1"
            if "subject" not in metadata:
                metadata["subject"] = "1"

            # Include zone information in the video entry
            video_data = {
                "path": video_path,
                "status": "processing",
                "has_arena": bool(zone_data and zone_data.polygon),
                "has_rois": bool(zone_data and zone_data.roi_polygons),
            }
            if metadata:
                video_data["metadata"] = metadata

            self.project_manager.add_video_batch(
                [video_data],
                save_project=False,  # Don't save to disk for single video workflow
            )

        # Save the zone data for this video so it can be retrieved later
        if zone_data and (zone_data.polygon or zone_data.roi_polygons):
            log.info(
                "workflow.single_video.saving_zones",
                video=video_path,
                has_arena=bool(zone_data.polygon),
                roi_count=len(zone_data.roi_polygons),
            )
            self.project_manager.save_zone_data(zone_data, video_path)

        # Refresh views so the video appears in Main Control and Reports tabs
        # Ensures the user sees the registered video before processing starts
        self.refresh_project_views(reason="Single video registered", immediate=True)

        # 1. Update the detector with the newly created zone data
        # We need to know the video dimensions to set up the zones correctly
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro", "message": f"Não foi possível abrir o vídeo: {video_path}"},
            )
            return
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        self.detector.set_zones(zone_data, width, height)
        log.info(
            "controller.single_video.zones_set",
            count=len(zone_data.roi_polygons) + (1 if zone_data.polygon else 0),
        )

        # Inform plugin that aquarium region is defined
        if self.detector and hasattr(self.detector.plugin, "set_aquarium_region_defined"):
            has_aquarium = bool(zone_data and zone_data.polygon)
            self.detector.plugin.set_aquarium_region_defined(has_aquarium)
            log.info(
                "controller.single_video.aquarium_status",
                defined=has_aquarium,
                plugin=self.detector.plugin.get_name(),
                context=getattr(self.detector.plugin, "_context", "unknown"),
            )

        # 2. Prepare the environment for _process_videos
        scanned_files = ProjectManager.scan_input_paths([video_path])
        if not scanned_files:
            self.view.show_error("Erro", "Não foi possível identificar um arquivo de vídeo válido.")
            return
        video_to_process = scanned_files[0]

        video_name = os.path.splitext(os.path.basename(video_path))[0]
        output_dir = os.path.join(os.path.dirname(video_path), f"{video_name}_results")
        self._prepare_results_directory(output_dir)

        # 3. Create and start the processing worker
        self.cancel_event.clear()

        callbacks = self._create_processing_callbacks([video_to_process])
        context = self._create_processing_context(
            [video_to_process], output_dir, single_video_config=config
        )

        self.processing_worker = ProcessingWorker(context, callbacks)
        self.processing_thread = self.processing_worker.start_in_thread()

        # Update processing state in StateManager
        self.state_manager.update_processing_state(
            source="controller.start_single_video_analysis",
            is_processing=True,
            current_video=os.path.basename(video_path),
            processing_start_time=datetime.now(),
        )

        # 4. Switch to analysis view mode immediately
        if self.ui_event_bus:
            self.ui_event_bus.publish_event(Events.UI_NAVIGATE_TO_ANALYSIS_VIEW)

        # Permanecer na tela principal para exibir a barra de progresso
        # self.view._create_welcome_frame()
        if self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Análise Iniciada",
                    "message": "A análise do vídeo foi iniciada em segundo plano.\n"
                    "Você será notificado quando terminar. Os resultados serão salvos em:\n"
                    f"{output_dir}",
                },
            )

    def start_project_processing_workflow(self):
        """Adiciona vídeos com validação robusta de zonas"""
        log.info("workflow.project_processing.start")

        if self.processing_thread and self.processing_thread.is_alive():
            self.ui_event_bus.publish(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Análise em Andamento",
                    "message": "Uma análise de vídeo já está em andamento. "
                    "Por favor, aguarde ou cancele a análise atual.",
                },
            )
            return

        # Validação 1: Projeto existe
        if not self.project_manager.project_path:
            if self.ui_event_bus:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR, {"title": "Erro", "message": "Nenhum projeto carregado"}
                )
            return

        # Validação 2: Zonas definidas
        zone_data = self.project_manager.get_zone_data()
        if not zone_data or not zone_data.polygon:
            log.warning("workflow.project_processing.no_main_arena")

            response = self.view.ask_ok_cancel(
                "Arena Principal Não Definida",
                "O polígono principal do aquário não foi definido.\n\n"
                "É necessário definir a arena principal para análise precisa.\n"
                "Deseja definir agora antes de processar?",
            )

            if response:
                # Muda para aba de zonas
                self.ui_event_bus.publish(Events.UI_SELECT_TAB, {"tab_name": "zone_tab"})

                # Carrega frame do primeiro vídeo se disponível
                first_video = self.project_manager.get_next_video()
                if first_video:
                    self.ui_event_bus.publish(
                        Events.UI_DISPLAY_VIDEO_FRAME, {"video_path": first_video}
                    )

                self.ui_event_bus.publish(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Defina a Arena Principal",
                        "message": "Por favor:\n"
                        "1. Use 'Detectar Aquário (Auto)' ou\n"
                        "2. Desenhe manualmente o polígono principal\n"
                        "3. Depois volte para adicionar vídeos",
                    },
                )
                return
            else:
                # Oferece arena padrão como fallback
                if not self.view.ask_ok_cancel(
                    "Usar Arena Padrão?",
                    "Deseja usar o frame completo como arena?\n"
                    "(Não recomendado para análise precisa)",
                ):
                    log.info("workflow.project_processing.cancelled_no_arena")
                    return

                # Cria arena padrão baseada no primeiro vídeo
                first_video = self.project_manager.get_next_video()
                if first_video:
                    import cv2

                    cap = cv2.VideoCapture(first_video)
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    cap.release()

                    default_arena = [[0, 0], [width, 0], [width, height], [0, height]]

                    success = self.set_main_arena_polygon(default_arena)
                    if success:
                        log.info(
                            "workflow.project_processing.default_arena_created",
                            size=f"{width}x{height}",
                        )
                        self.ui_event_bus.publish(
                            Events.UI_SHOW_INFO,
                            {
                                "title": "Arena Padrão Criada",
                                "message": f"Arena padrão criada ({width}x{height})\n"
                                "Recomenda-se ajustar manualmente depois.",
                            },
                        )
                    else:
                        self.ui_event_bus.publish(
                            Events.UI_SHOW_ERROR,
                            {"title": "Erro", "message": "Não foi possível criar arena padrão"},
                        )
                        return
                else:
                    self.ui_event_bus.publish(
                        Events.UI_SHOW_ERROR,
                        {"title": "Erro", "message": "Nenhum vídeo encontrado no projeto"},
                    )
                    return

        # Validação 3: Aviso sobre ROIs (opcional, mas informativo)
        if not zone_data.roi_polygons:
            if not self.view.ask_ok_cancel(
                "Nenhuma ROI Definida",
                "Nenhuma Área de Interesse (ROI) foi definida.\n\n"
                "A análise usará apenas a arena principal.\n"
                "Para análises detalhadas, considere definir ROIs.\n\n"
                "Deseja continuar?",
            ):
                log.info("workflow.project_processing.cancelled_by_user_no_roi")
                return

        log.info(
            "workflow.project_processing.zones_validated",
            has_main_arena=bool(zone_data.polygon),
            roi_count=len(zone_data.roi_polygons),
        )

        # 1. Ask user to select files or folders
        paths = self.view.ask_open_filenames(
            "Selecione Vídeos ou Pastas para Adicionar ao Projeto",
            [
                ("Todos os arquivos", "*.*"),
                ("Arquivos de vídeo", "*.mp4 *.avi *.mov"),
                ("Pastas", "*/"),
            ],
        )
        if not paths:
            return

        # 2. Scan the inputs
        scanned_videos = self.project_manager.scan_input_paths(paths)
        if not scanned_videos:
            self.ui_event_bus.publish(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Nenhum Vídeo Encontrado",
                    "message": "Nenhum novo arquivo de vídeo foi encontrado nos caminhos selecionados.",  # noqa: E501
                },
            )
            return

        # 3. Handle mixed data scenario
        videos_to_process = []
        with_data = [v for v in scanned_videos if v["has_data"]]
        without_data = [v for v in scanned_videos if not v["has_data"]]

        if with_data and without_data:
            # The complex case: some have data, some don't
            msg = (
                f"{len(with_data)} vídeo(s) já possuem dados de análise.\n"
                f"{len(without_data)} vídeo(s) precisam ser processados.\n\n"
                "Deseja reprocessar os vídeos que já possuem dados?"
            )
            if self.view.ask_ok_cancel("Dados Mistos Encontrados", msg):
                # User wants to re-process everything
                videos_to_process = scanned_videos
            else:
                # User wants to skip re-processing
                videos_to_process = without_data
        elif with_data and not without_data:
            # All selected videos have data
            if self.view.ask_ok_cancel(
                "Dados Encontrados",
                "Todos os vídeos selecionados já possuem dados de análise. "
                "Deseja reprocessá-los todos?",
            ):
                videos_to_process = with_data
            else:
                self.ui_event_bus.publish(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Processamento Ignorado",
                        "message": "Nenhum novo vídeo foi processado.",
                    },
                )
                # Still add them to the project for reporting purposes
                self.project_manager.add_video_batch(scanned_videos)
                return
        else:
            # No videos have data, process all of them
            videos_to_process = without_data

        if not videos_to_process:
            self.ui_event_bus.publish(
                Events.UI_SHOW_INFO,
                {
                    "title": "Processamento Concluído",
                    "message": "Nenhum novo vídeo para processar.",
                },
            )
            return

        # 4. Add the batch to the project
        self.project_manager.add_video_batch(scanned_videos)

        # 5. Process the videos that need it using worker
        self.cancel_event.clear()

        callbacks = self._create_processing_callbacks(videos_to_process)
        context = self._create_processing_context(
            videos_to_process, self.project_manager.project_path
        )

        self.processing_worker = ProcessingWorker(context, callbacks)
        self.processing_thread = self.processing_worker.start_in_thread()

        # 6. Update statuses in project file
        for video in videos_to_process:
            self.project_manager.update_video_status(video["path"], "complete")

        self.ui_event_bus.publish(
            Events.UI_SHOW_INFO,
            {
                "title": "Sucesso",
                "message": f"{len(videos_to_process)} vídeo(s) foram processados e adicionados ao projeto.",  # noqa: E501
            },
        )

    def process_pending_project_videos(  # noqa: C901
        self,
        video_paths: list[str] | None = None,
    ) -> None:
        """Processa vídeos já adicionados ao projeto que possuem dados pendentes."""
        log.info(
            "workflow.project_processing.resume_requested",
            targeted=len(video_paths or []),
        )

        if self.processing_thread and self.processing_thread.is_alive():
            self.ui_event_bus.publish(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Análise em Andamento",
                    "message": "Um processamento já está ativo. Aguarde a conclusão ou "
                    "cancele a análise atual antes de iniciar um novo lote.",
                },
            )
            return

        if not self.project_manager.project_path:
            self.ui_event_bus.publish(
                Events.UI_SHOW_ERROR, {"title": "Erro", "message": "Nenhum projeto carregado"}
            )
            return

        all_videos = self.project_manager.get_all_videos() or []
        if not all_videos:
            if self.ui_event_bus:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Processamento",
                        "message": "Nenhum vídeo cadastrado no projeto atualmente.",
                    },
                )
            return

        videos_by_norm: dict[str, dict] = {}
        for video in all_videos:
            path_value = video.get("path")
            if isinstance(path_value, str) and path_value:
                videos_by_norm[os.path.normpath(path_value)] = video
        skip_dialog = bool(video_paths)
        candidate_entries = self._gather_candidate_entries(video_paths, all_videos)
        if candidate_entries is None:
            return

        info_by_norm, missing_files, scanned_videos = self._scan_and_validate_candidate_paths(
            candidate_entries
        )
        if info_by_norm is None:
            return

        (
            ready_with_trajectory,
            ready_with_zones,
            arena_only,
            without_arena,
            data_changed,
        ) = self._classify_candidate_videos(candidate_entries, info_by_norm)

        if data_changed:
            self.project_manager.save_project()

        if not (ready_with_trajectory or ready_with_zones or arena_only):
            self.ui_event_bus.publish(
                Events.UI_SHOW_INFO,
                {
                    "title": "Processamento",
                    "message": "Nenhum vídeo elegível foi encontrado com dados suficientes para análise.",  # noqa: E501
                },
            )
            return

        eligible_videos = self._select_eligible_videos(
            skip_dialog, ready_with_trajectory, ready_with_zones, arena_only, without_arena
        )
        if eligible_videos is None:
            return

        zones_updated = False
        for video_info in eligible_videos:
            if video_info.get("has_arena") or video_info.get("has_rois"):
                try:
                    zone_data = ProjectManager.load_zones_from_parquet(video_info)
                except Exception as exc:  # pragma: no cover - defensive
                    log.warning(
                        "workflow.project_processing.zone_load_failed",
                        video=os.path.basename(video_info.get("path", "")),
                        error=str(exc),
                    )
                    zone_data = None
                if zone_data and (zone_data.polygon or zone_data.roi_polygons):
                    self.project_manager.save_zone_data(
                        zone_data, video_info["path"], persist=False
                    )
                    zones_updated = True

        if zones_updated:
            self.project_manager.save_project()

        self.cancel_event.clear()

        callbacks = self._create_processing_callbacks(eligible_videos)
        context = self._create_processing_context(
            eligible_videos, self.project_manager.project_path
        )

        self.processing_worker = ProcessingWorker(context, callbacks)
        self.processing_thread = self.processing_worker.start_in_thread()

        for video_info in eligible_videos:
            path_value = video_info.get("path")
            if path_value:
                self.project_manager.update_video_status(path_value, "complete")

        self.ui_event_bus.publish(
            Events.UI_SET_STATUS,
            {"message": f"Processando {len(eligible_videos)} vídeo(s) com dados existentes..."},
        )
        display_names = [
            os.path.basename(video_info.get("path", "")) or "(arquivo desconhecido)"
            for video_info in eligible_videos
        ]
        preview_lines = [f"• {name}" for name in display_names[:5]]
        if len(display_names) > 5:
            preview_lines.append(f"• ... (+{len(display_names) - 5} restante(s))")

        message = (
            f"O processamento de {len(eligible_videos)} vídeo(s) foi iniciado em segundo plano."
        )
        if preview_lines:
            message += "\n\nFila:\n" + "\n".join(preview_lines)

        self.ui_event_bus.publish(
            Events.UI_SHOW_INFO, {"title": "Processamento Iniciado", "message": message}
        )

        log.info(
            "workflow.project_processing.resume_started",
            total=len(eligible_videos),
            with_trajectory=len(ready_with_trajectory),
            with_zones=len(ready_with_zones),
            targeted=bool(video_paths),
        )

    def generate_parquet_summaries(self, video_paths: list[str]) -> None:
        """Regera arquivos de sumário em Parquet para os vídeos selecionados."""
        log.info(
            "workflow.summaries.generate_requested",
            requested=len(video_paths or []),
        )

        if self.processing_thread and self.processing_thread.is_alive():
            self.ui_event_bus.publish(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Processamento em andamento",
                    "message": "Aguarde a conclusão do processamento atual antes de gerar os sumários.",  # noqa: E501
                },
            )
            return

        if not video_paths:
            self.ui_event_bus.publish(
                Events.UI_SHOW_INFO,
                {
                    "title": "Sumários",
                    "message": "Nenhum vídeo selecionado para geração de sumários.",
                },
            )
            return

        if not self.project_manager.project_path:
            self.ui_event_bus.publish(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Projeto ausente",
                    "message": "Abra um projeto antes de gerar sumários parquet.",
                },
            )
            return

        all_videos = self.project_manager.get_all_videos() or []
        if not all_videos:
            self.ui_event_bus.publish(
                Events.UI_SHOW_INFO,
                {
                    "title": "Sumários",
                    "message": "Nenhum vídeo cadastrado no projeto atualmente.",
                },
            )
            return

        normalized_targets: set[str] = set()
        raw_lookup: dict[str, str] = {}
        for raw_path in video_paths:
            if not isinstance(raw_path, str) or not raw_path:
                continue
            norm_path = os.path.normpath(raw_path)
            normalized_targets.add(norm_path)
            raw_lookup.setdefault(norm_path, raw_path)

        if not normalized_targets:
            self.view.show_info(
                "Sumários",
                "Nenhum vídeo selecionado para geração de sumários.",
            )
            return

        videos_by_norm = {
            os.path.normpath(video.get("path") or ""): video
            for video in all_videos
            if isinstance(video.get("path"), str) and video.get("path")
        }

        selected_videos = [
            videos_by_norm[norm_path]
            for norm_path in normalized_targets
            if norm_path in videos_by_norm
        ]

        missing_targets = [
            norm_path for norm_path in normalized_targets if norm_path not in videos_by_norm
        ]
        if missing_targets:
            sample = [os.path.basename(raw_lookup[norm]) for norm in list(missing_targets)[:5]]
            if len(missing_targets) > 5:
                sample.append(f"... (+{len(missing_targets) - 5})")
            self.ui_event_bus.publish(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Vídeos fora do projeto",
                    "message": "Alguns itens selecionados não pertencem ao projeto atual:\n"
                    + "\n".join(sample),
                },
            )

        if not selected_videos:
            self.ui_event_bus.publish(
                Events.UI_SHOW_INFO,
                {
                    "title": "Sumários",
                    "message": "Nenhum dos vídeos selecionados pertence ao projeto ativo.",
                },
            )
            return

        eligible_videos = [video for video in selected_videos if video.get("has_trajectory")]
        if not eligible_videos:
            self.ui_event_bus.publish(
                Events.UI_SHOW_INFO,
                {
                    "title": "Sumários",
                    "message": "Nenhum dos vídeos selecionados possui trajetória gerada.",
                },
            )
            return

        settings_obj = settings
        # Offload the heavy per-video processing to a dedicated worker method.
        self.processing_thread = threading.Thread(
            target=self._generate_parquet_summaries_worker,
            args=(eligible_videos, settings_obj),
            daemon=True,
        )
        self.processing_thread.start()

    def _run_tracking_if_needed(
        self,
        video_path: str,
        results_dir: str,
        experiment_id: str,
        progress_callback=None,
        calibration_data: dict | None = None,
        analysis_interval_frames: int = 10,
        display_interval_frames: int = 10,
    ) -> tuple[bool, list | None]:
        """
        Checks if a trajectory file exists. If not, runs the tracking process
        to generate it. This is a blocking operation.
        Returns:
            A tuple containing:
            - bool: True if tracking was successful or already existed, False otherwise.
            - list | None: The arena polygon used for tracking, or None if tracking
              failed.
        """
        log.info("controller.tracking.check_or_run", video=experiment_id)
        trajectory_path = os.path.join(results_dir, f"3_CoordMovimento_{experiment_id}.parquet")
        arena_polygon = self.project_manager.get_zone_data().polygon
        if os.path.exists(trajectory_path):
            log.info("controller.tracking.exists", path=trajectory_path)
            return True, arena_polygon

        if self.detector is None:
            log.error("controller.tracking.no_detector")
            return False, None

        log.info("controller.tracking.generating", video=experiment_id)
        self.ui_event_bus.publish_event(
            Events.UI_SET_STATUS,
            {"message": f"Gerando trajetória para {experiment_id}..."},
        )

        recorder = Recorder()
        cap = cv2.VideoCapture(video_path)
        try:
            if not cap.isOpened():
                log.error("controller.tracking.video_open_failed", path=video_path)
                return False, None

            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            zone_data = self.project_manager.get_zone_data()
            if not zone_data.polygon:
                log.warning("controller.tracking.no_arena_defined.using_default")
                arena_polygon = [
                    [0, 0],
                    [frame_width, 0],
                    [frame_width, frame_height],
                    [0, frame_height],
                ]
                zone_data.polygon = arena_polygon
            else:
                arena_polygon = zone_data.polygon

            self.detector.set_zones(zone_data, frame_width, frame_height)

            # Inform plugin that aquarium region is defined
            if self.detector and hasattr(self.detector.plugin, "set_aquarium_region_defined"):
                has_aquarium = bool(zone_data and zone_data.polygon)
                self.detector.plugin.set_aquarium_region_defined(has_aquarium)
                log.info(
                    "controller.tracking.aquarium_status",
                    defined=has_aquarium,
                    plugin=self.detector.plugin.get_name(),
                    context=getattr(self.detector.plugin, "_context", "unknown"),
                )

            # --- New: Calculate pixel/cm ratio before recording ---
            pixel_per_cm_ratio = None
            cal = None
            calibration_source = calibration_data or (
                self.project_manager.project_data.get("calibration")
                if self.project_manager and self.project_manager.project_data
                else None
            )
            if calibration_source:
                width_cm = calibration_source.get("aquarium_width_cm")
                height_cm = calibration_source.get("aquarium_height_cm")
                if width_cm and height_cm and arena_polygon:
                    cal = Calibration(np.array(arena_polygon), width_cm, height_cm)
                    pixel_per_cm_ratio = cal.pixel_per_cm_ratio

            recorder.start_recording(
                output_folder=results_dir,
                frame_width=frame_width,
                frame_height=frame_height,
                zones=zone_data,
                is_video_file=True,
                base_name=experiment_id,
                pixel_per_cm_ratio=pixel_per_cm_ratio,
                calibration=cal,
            )

            if self.detector and hasattr(self.detector, "reset_tracking_state"):
                try:
                    self.detector.reset_tracking_state()
                except Exception:  # pragma: no cover - defensive
                    plugin_obj = getattr(self.detector, "plugin", None)
                    plugin_class = getattr(plugin_obj, "__class__", type(self.detector))
                    log.warning(
                        "controller.tracking.reset_tracker_failed",
                        plugin=plugin_class,
                        exc_info=True,
                    )

            frame_num = 0
            processed_frames_count = 0
            detected_frames_count = 0  # Frames that actually have detections
            import time

            start_time = time.time()  # Track processing start time
            log.info("controller.tracking.loop.start", video=experiment_id)
            while not self.cancel_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    log.info("controller.tracking.loop.end_of_video", frame=frame_num)
                    break

                # Check if we should process this frame (analysis interval)
                should_process = frame_num % analysis_interval_frames == 0
                detections = []

                if should_process:
                    detections, _ = self.detector.detect(frame, project_type="pre-recorded")

                    timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                    recorder.write_detection_data(timestamp, frame_num, detections)

                    processed_frames_count += 1

                    # Count frames that actually have detections
                    if detections:
                        detected_frames_count += 1

                # Update GUI display every processed frame for smoother visualization
                if progress_callback and should_process:
                    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    progress_fraction = (frame_num + 1) / total_frames if total_frames > 0 else 0

                    # Prepare statistics for GUI update
                    stats = {
                        "total_frames": total_frames,
                        "current_frame": frame_num + 1,  # For accurate ETA calculation
                        "processed_frames": processed_frames_count,
                        "detected_frames": detected_frames_count,
                        "start_time": start_time,
                    }

                    # Always draw overlay on processed frames
                    self.detector.draw_overlay(frame, detections)
                    progress_callback(
                        progress_fraction,
                        "Gerando trajetória...",
                        frame,
                        stats,
                        detections=detections,
                    )

                frame_num += 1

            recorder.stop_recording()  # This saves the parquet file
            log.info("controller.tracking.success", path=trajectory_path)
            self.ui_event_bus.publish_event(
                Events.UI_SET_STATUS,
                {"message": f"Trajetória para {experiment_id} gerada."},
            )
            return True, arena_polygon

        except Exception as e:
            log.error(
                "controller.tracking.error",
                video=experiment_id,
                error=str(e),
                exc_info=True,
            )
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro de Rastreamento",
                    "message": f"Ocorreu um erro inesperado ao gerar a trajetória para {experiment_id}:\n{e}",  # noqa: E501
                },
            )
            return False, None
        finally:
            if cap.isOpened():
                cap.release()

    def _resolve_single_animal_mode(self, single_video_config: dict | None) -> bool | None:
        """Derive whether single-animal tracking mode should be active."""

        def _coerce_to_int(value):
            if value is None:
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        if single_video_config:
            count = _coerce_to_int(single_video_config.get("animals_per_aquarium"))
            if count is not None:
                enabled = count == 1
                log.debug(
                    "controller.single_animal_mode.resolved_single_video",
                    animals_per_aquarium=count,
                    enabled=enabled,
                )
                return enabled

        project_data = getattr(self.project_manager, "project_data", {}) or {}
        calibration = project_data.get("calibration") or {}
        count = _coerce_to_int(calibration.get("animals_per_aquarium"))
        if count is not None:
            enabled = count == 1
            log.debug(
                "controller.single_animal_mode.resolved_project",
                animals_per_aquarium=count,
                enabled=enabled,
            )
            return enabled

        return None

    def _resolve_single_subject_tracker_preference(
        self, single_video_config: dict | None
    ) -> bool | None:
        """
        Resolve single-subject tracker preference from project or single video config.

        Args:
            single_video_config: Optional single video configuration dict

        Returns:
            bool | None: Tracker preference or None if not set
        """
        # Try to get project type from single video config or project manager
        project_type = None
        if single_video_config:
            project_type = single_video_config.get("project_type")

        if not project_type:
            project_data = getattr(self.project_manager, "project_data", {})
            if project_data:
                project_type = project_data.get("project_type")

        # Delegate to detector service
        return self.detector_service._resolve_single_subject_tracker_preference(project_type)

    def _configure_single_subject_tracker(self, enabled: bool) -> None:
        """
        Configure single-subject tracking mode.

        Phase 6: Delegates to DetectorService.
        """
        self.detector_service.set_single_subject_mode(bool(enabled))
        self._publish_processing_mode(
            source="tracker_configuration",
            force=True,
        )

    def _determine_processing_intervals(self, single_video_config: dict | None) -> tuple[int, int]:
        analysis_interval_frames = 10
        display_interval_frames = 10

        if single_video_config:
            analysis_interval_frames = single_video_config.get(
                "analysis_interval_frames", analysis_interval_frames
            )
            display_interval_frames = single_video_config.get(
                "display_interval_frames", display_interval_frames
            )
            log.info(
                "controller.processing.intervals_single_video",
                analysis_interval=analysis_interval_frames,
                display_interval=display_interval_frames,
                config_keys=list(single_video_config.keys()),
            )
        else:
            project_data = getattr(self.project_manager, "project_data", {}) or {}
            analysis_interval_frames = project_data.get(
                "analysis_interval_frames", analysis_interval_frames
            )
            display_interval_frames = project_data.get(
                "display_interval_frames", display_interval_frames
            )

        return int(analysis_interval_frames), int(display_interval_frames)

    @contextmanager
    def _temporary_single_animal_mode(self, single_video_config: dict | None) -> Iterator[bool]:
        previous_mode = settings.video_processing.single_animal_per_aquarium
        resolved_mode = self._resolve_single_animal_mode(single_video_config)

        previous_tracker_pref = settings.tracking.use_single_subject_tracker
        resolved_tracker_pref = self._resolve_single_subject_tracker_preference(single_video_config)
        if resolved_tracker_pref is None:
            resolved_tracker_pref = previous_tracker_pref

        if resolved_mode is not None and resolved_mode != previous_mode:
            settings.video_processing.single_animal_per_aquarium = resolved_mode
            log.info(
                "controller.processing.single_animal_mode",
                enabled=resolved_mode,
                previous=previous_mode,
                scope="single_video" if single_video_config else "project",
            )

        tracker_changed = resolved_tracker_pref != previous_tracker_pref
        if tracker_changed:
            settings.tracking.use_single_subject_tracker = resolved_tracker_pref
            log.info(
                "controller.processing.single_subject_tracker",
                enabled=resolved_tracker_pref,
                previous=previous_tracker_pref,
                scope="single_video" if single_video_config else "project",
            )

        self._configure_single_subject_tracker(settings.tracking.use_single_subject_tracker)
        self._publish_processing_mode(
            source="processing.temporary_mode.enter",
            force=True,
        )

        try:
            yield settings.video_processing.single_animal_per_aquarium
        finally:
            if settings.video_processing.single_animal_per_aquarium != previous_mode:
                settings.video_processing.single_animal_per_aquarium = previous_mode
                log.info(
                    "controller.processing.single_animal_mode_restored",
                    restored=previous_mode,
                )

            if tracker_changed:
                settings.tracking.use_single_subject_tracker = previous_tracker_pref
                log.info(
                    "controller.processing.single_subject_tracker_restored",
                    restored=previous_tracker_pref,
                )

            self._configure_single_subject_tracker(settings.tracking.use_single_subject_tracker)
            self._publish_processing_mode(
                source="processing.temporary_mode.exit",
                force=True,
            )

    def _prepare_processing_ui(self, total_videos: int) -> None:
        # Phase 4: Use UICoordinator for UI updates
        self.ui_coordinator.show_progress_bar(self.view)
        self.ui_coordinator.schedule_after(
            0,
            lambda: self.view.set_status(f"Iniciando processamento para {total_videos} vídeos..."),
        )
        self.project_manager.set_active_zone_video(None)

    def _finalize_processing(
        self,
        *,
        was_cancelled: bool,
        videos_to_process: list[dict],
        final_output_dir: str,
    ) -> None:
        # Phase 4: Use UICoordinator for UI updates
        self.project_manager.set_active_zone_video(None)
        self.ui_coordinator.update_view(self.view, "stop_analysis_view_mode")
        self.ui_coordinator.hide_progress_bar(self.view)

        if was_cancelled:
            self.ui_coordinator.show_info(
                self.view, "Cancelado", "A análise de vídeo foi cancelada."
            )
        elif videos_to_process:
            msg = f"Análise concluída. Resultados salvos em:\n{final_output_dir}"
            self.ui_coordinator.show_info(self.view, "Sucesso", msg)

        self.ui_coordinator.set_status(self.view, "Pronto.")
        self._publish_processing_mode(
            source="processing.finalize",
            force=True,
        )
        self.refresh_project_views()

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
        except Exception:  # pragma: no cover - defensive fallback
            log.debug(
                "controller.processing.metadata_derive_failed",
                experiment=experiment_id,
                video_path=video_path,
            )

        return metadata_context

    def _gather_candidate_entries(
        self,
        video_paths: list[str] | None,
        all_videos: list[dict],
    ) -> list[dict] | None:
        """Return a list of candidate video entries to process, or None if the
        calling function should abort (due to user cancel or invalid selection).
        """
        videos_by_norm: dict[str, dict] = {}
        for video in all_videos:
            path_value = video.get("path")
            if isinstance(path_value, str) and path_value:
                videos_by_norm[os.path.normpath(path_value)] = video

        if video_paths:
            normalized_targets: list[str] = []
            raw_lookup: dict[str, str] = {}
            for raw_path in video_paths:
                if not isinstance(raw_path, str) or not raw_path:
                    continue
                norm_path = os.path.normpath(raw_path)
                normalized_targets.append(norm_path)
                raw_lookup.setdefault(norm_path, raw_path)

            if not normalized_targets:
                self.ui_event_bus.publish(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Processamento",
                        "message": "Nenhum vídeo selecionado para processamento.",
                    },
                )
                return None

            candidate_entries = [
                videos_by_norm[norm_path]
                for norm_path in normalized_targets
                if norm_path in videos_by_norm
            ]

            missing_targets = [
                norm_path for norm_path in normalized_targets if norm_path not in videos_by_norm
            ]
            if missing_targets:
                sample = [os.path.basename(raw_lookup[norm]) for norm in missing_targets[:5]]
                if len(missing_targets) > 5:
                    sample.append(f"... (+{len(missing_targets) - 5})")
                self.ui_event_bus.publish(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Vídeos fora do projeto",
                        "message": "Alguns itens selecionados não pertencem ao projeto atual:\n"
                        + "\n".join(sample),
                    },
                )

            if not candidate_entries:
                self.ui_event_bus.publish(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Processamento",
                        "message": "Nenhum dos vídeos selecionados pertence ao projeto ativo.",
                    },
                )
                return None

            return candidate_entries
        else:
            candidate_entries = [
                video
                for video in all_videos
                if video.get("status") not in {"processed", "complete"}
            ]
            if not candidate_entries:
                self.ui_event_bus.publish(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Processamento",
                        "message": "Nenhum vídeo pendente para ser processado.",
                    },
                )
                return None
            return candidate_entries

    def _classify_candidate_videos(
        self, candidate_entries: list[dict], info_by_norm: dict
    ) -> tuple[list[dict], list[dict], list[dict], list[dict], bool]:
        """Given candidate entries and a lookup, classify them into buckets and
        return (ready_with_trajectory, ready_with_zones, arena_only, without_arena, data_changed).
        """
        ready_with_trajectory: list[dict] = []
        ready_with_zones: list[dict] = []
        arena_only: list[dict] = []
        without_arena: list[dict] = []

        data_changed = False

        for video in candidate_entries:
            path = video.get("path")
            if not isinstance(path, str) or not path:
                continue

            info = info_by_norm.get(os.path.normpath(path))
            if not info:
                continue

            for key in ("has_arena", "has_rois", "has_trajectory", "has_complete_data"):
                new_value = info.get(key, False)
                if video.get(key) != new_value:
                    video[key] = new_value
                    data_changed = True

            if info.get("has_arena"):
                if info.get("has_trajectory"):
                    ready_with_trajectory.append(info)
                elif info.get("has_rois"):
                    ready_with_zones.append(info)
                else:
                    arena_only.append(info)
            else:
                without_arena.append(info)

        return (
            ready_with_trajectory,
            ready_with_zones,
            arena_only,
            without_arena,
            data_changed,
        )

    def _select_eligible_videos(
        self,
        skip_dialog: bool,
        ready_with_trajectory: list[dict],
        ready_with_zones: list[dict],
        arena_only: list[dict],
        without_arena: list[dict],
    ) -> list[dict] | None:
        """Select eligible videos for processing (either skip dialog or show it).

        Returns list of eligible videos or None if user cancelled.
        """
        eligible_videos: list[dict] = []

        if skip_dialog:
            eligible_videos.extend(ready_with_trajectory)
            eligible_videos.extend(ready_with_zones)

            if arena_only:
                skipped_names = [
                    os.path.basename(info.get("path", "")) or "(desconhecido)"
                    for info in arena_only[:5]
                ]
                if len(arena_only) > 5:
                    skipped_names.append(f"... (+{len(arena_only) - 5})")
                self.ui_event_bus.publish(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Processamento",
                        "message": "Alguns vídeos selecionados foram ignorados porque não "
                        "possuem ROIs desenhadas:\n"
                        + "\n".join(f"• {name}" for name in skipped_names),
                    },
                )

            if not eligible_videos:
                if self.ui_event_bus:
                    self.ui_event_bus.publish_event(
                        Events.UI_SHOW_INFO,
                        {
                            "title": "Processamento",
                            "message": "Nenhum dos vídeos selecionados contém arena e ROIs "
                            "suficientes para gerar trajetórias.",
                        },
                    )
                return None
        else:
            dialog_result = self.view.show_pending_videos_dialog(
                ready_with_trajectory=ready_with_trajectory,
                ready_with_zones=ready_with_zones,
                arena_only=arena_only,
                without_arena=without_arena,
            )

            if not dialog_result or not dialog_result.get("confirmed"):
                log.info("workflow.project_processing.resume_cancelled_by_user")
                return None

            include_arena_only = bool(dialog_result.get("include_arena_only"))

            eligible_videos.extend(ready_with_trajectory)
            eligible_videos.extend(ready_with_zones)
            if include_arena_only:
                eligible_videos.extend(arena_only)
            elif arena_only:
                log.info(
                    "workflow.project_processing.skip_arena_only",
                    skipped=len(arena_only),
                )

            if not eligible_videos:
                self.ui_event_bus.publish(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Processamento",
                        "message": "Nenhum vídeo foi selecionado para processamento neste momento.",
                    },
                )
                return None

        return eligible_videos

    def _scan_and_validate_candidate_paths(self, candidate_entries: list[dict]):
        """Scan candidate paths and return (info_by_norm, missing_files, scanned_videos).

        Returns (None, None, None) if there are no valid candidate paths.
        """
        candidate_paths = [
            video.get("path")
            for video in candidate_entries
            if isinstance(video.get("path"), str) and video.get("path")
        ]
        if not candidate_paths:
            self.ui_event_bus.publish(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro",
                    "message": "Não foi possível localizar caminhos válidos para os vídeos selecionados.",  # noqa: E501
                },
            )
            return None, None, None

        scanned_videos = ProjectManager.scan_input_paths(candidate_paths)
        info_by_norm = {
            os.path.normpath(info["path"]): info
            for info in scanned_videos
            if isinstance(info.get("path"), str)
        }

        missing_files = [
            path for path in candidate_paths if os.path.normpath(path) not in info_by_norm
        ]
        if missing_files:
            sample_names = [os.path.basename(path) for path in missing_files[:5]]
            if len(missing_files) > 5:
                sample_names.append(f"... (+{len(missing_files) - 5})")
            self.ui_event_bus.publish(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Vídeos Não Encontrados",
                    "message": "Alguns vídeos foram ignorados porque não foram localizados:\n"
                    + "\n".join(sample_names),
                },
            )
            log.warning(
                "workflow.project_processing.missing_sources",
                missing=len(missing_files),
            )

        return info_by_norm, missing_files, scanned_videos

    def _generate_parquet_summaries_worker(self, target_videos: list[dict], settings_obj) -> None:
        """Worker method to generate parquet summaries for a list of videos.

        Separated to reduce complexity in the public API method.
        """
        completed: list[str] = []
        skipped: list[str] = []
        details: list[str] = []
        data_changed = False

        for video in target_videos:
            # Reuse the same logic previously extracted inlined; keep small and focused
            state = None
            try:
                # Simplified wrapper calling existing logic for each video. Defer to the
                # per-video helper implemented earlier.
                state, info_msg, _ppath, changed = self._process_summary_video(
                    video,
                    settings_obj,
                )
            except Exception as exc:  # pragma: no cover - defensive
                state, info_msg, _ppath, changed = "failed", str(exc), None, False

            if state == "completed":
                completed.append(info_msg or "(desconhecido)")
                data_changed = data_changed or bool(changed)
            else:
                skipped.append(info_msg.split(":")[0] if info_msg else "(desconhecido)")
                details.append(f"• {info_msg}")

        if data_changed:
            self.project_manager.save_project()

        def finalize() -> None:
            if completed:
                self.ui_event_bus.publish(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Sumários Gerados",
                        "message": "Sumários parquet atualizados para "
                        f"{len(completed)} vídeo(s).\n"
                        + "\n".join(f"• {item}" for item in completed),
                    },
                )
                status_msg = f"Σ Sumários atualizados: {len(completed)} vídeo(s)."
            else:
                status_msg = "Nenhum sumário foi atualizado."

            if details:
                self.ui_event_bus.publish(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Vídeos ignorados",
                        "message": "Alguns sumários não puderam ser gerados:\n"
                        + "\n".join(details),
                    },
                )

            self.ui_event_bus.publish(Events.UI_SET_STATUS, {"message": status_msg})
            self.refresh_project_views(reason=status_msg, append_summary=True)
            self.processing_thread = None

        self.root.after(0, finalize)

    def _process_summary_video(
        self,
        video: dict,
        settings_obj,
    ) -> tuple[str, str | None, str | None, bool]:
        """Process a single video for summary generation. Extracted from the main method."""
        path = video.get("path")
        if not isinstance(path, str) or not path:
            return "skipped", "Caminho do vídeo não definido.", None, False

        experiment_id = os.path.splitext(os.path.basename(path))[0]
        metadata_hint = dict(video.get("metadata") or {})
        results_path = self.project_manager.resolve_results_directory(
            experiment_id, video_path=path, metadata=metadata_hint
        )
        results_dir = str(results_path)

        parquet_info = video.get("parquet_files") or {}
        trajectory_path = parquet_info.get("trajectory")
        if trajectory_path and not os.path.exists(trajectory_path):
            trajectory_path = None

        if not trajectory_path:
            candidates = [
                os.path.join(results_dir, f"3_CoordMovimento_{experiment_id}.parquet"),
                os.path.join(os.path.dirname(path), f"3_CoordMovimento_{experiment_id}.parquet"),
            ]
            for candidate in candidates:
                if os.path.exists(candidate):
                    trajectory_path = candidate
                    break

        if not trajectory_path:
            return (
                "skipped",
                f"{experiment_id}: arquivo de trajetória ausente.",
                None,
                False,
            )

        try:
            trajectory_df = pd.read_parquet(trajectory_path)
        except Exception as exc:  # pragma: no cover - I/O defensive
            return (
                "skipped",
                f"{experiment_id}: falha ao ler trajetória ({exc}).",
                None,
                False,
            )

        if trajectory_df.empty:
            return (
                "skipped",
                f"{experiment_id}: trajetória vazia, sumário não gerado.",
                None,
                False,
            )

        self.project_manager.set_active_zone_video(path)
        try:
            zone_data = self.project_manager.get_zone_data(video_path=path)

            arena_polygon_px = list(zone_data.polygon or [])

            if not arena_polygon_px:
                cap = cv2.VideoCapture(path)
                if not cap.isOpened():
                    return (
                        "skipped",
                        f"{experiment_id}: não foi possível abrir o vídeo.",
                        None,
                        False,
                    )
                frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()
                arena_polygon_px = [
                    [0, 0],
                    [frame_width, 0],
                    [frame_width, frame_height],
                    [0, frame_height],
                ]

            calib_data = self.project_manager.project_data.get("calibration", {})
            width_cm = calib_data.get("aquarium_width_cm")
            height_cm = calib_data.get("aquarium_height_cm")
            if not width_cm or not height_cm:
                return "skipped", f"{experiment_id}: calibração incompleta (px/cm).", None, False

            cal = Calibration(np.array(arena_polygon_px), width_cm, height_cm)
            video_width_px, video_height_px = cal.target_dims_px
            pixelcm_x, pixelcm_y = cal.pixel_per_cm_ratio
            arena_polygon_warped = cal.transform_points(arena_polygon_px)

            roi_polygons = list(zone_data.roi_polygons or [])
            roi_names = list(zone_data.roi_names or [])
            roi_colors_list = list(zone_data.roi_colors or [])

            rois: list[ROI] = []
            for idx, roi_points in enumerate(roi_polygons):
                warped_points = cal.transform_points(roi_points)
                roi_polygon_px = [(float(x), float(y)) for x, y in warped_points]
                roi_name = roi_names[idx] if idx < len(roi_names) else f"ROI {idx + 1}"
                rois.append(
                    ROI(
                        name=roi_name,
                        geometry=Polygon(roi_polygon_px),
                        coordinate_space="px",
                    )
                )

            roi_colors = {
                (roi_names[i] if i < len(roi_names) else f"ROI {i + 1}"): roi_colors_list[i]
                for i in range(len(roi_colors_list))
            }

            metadata = self.project_manager.get_metadata_for_experiment(experiment_id) or {
                "experiment_id": experiment_id,
                "video_name": experiment_id,
            }

            reporter = Reporter(
                trajectory_df=trajectory_df,
                metadata=metadata,
                pixelcm_x=pixelcm_x,
                pixelcm_y=pixelcm_y,
                video_height_px=video_height_px,
                arena_polygon_px=arena_polygon_warped,
                rois=rois,
                fps=settings_obj.video_processing.fps,
                roi_colors=roi_colors,
                video_path=path,
                calibration=cal,
                sharp_turn_threshold=settings_obj.video_processing.sharp_turn_threshold_deg_s,
                freezing_threshold=settings_obj.video_processing.freezing_velocity_threshold,
                freezing_duration=settings_obj.video_processing.freezing_min_duration_s,
                smoothing_window_length=settings_obj.trajectory_smoothing.window_length,
                smoothing_polyorder=settings_obj.trajectory_smoothing.polyorder,
            )

            os.makedirs(results_dir, exist_ok=True)
            parquet_path = os.path.join(results_dir, f"{experiment_id}_summary.parquet")
            reporter.export_summary_data(parquet_path, format="parquet")

            video.setdefault("parquet_files", {})["summary"] = parquet_path
            video["has_complete_data"] = True
            return "completed", experiment_id, parquet_path, True
        except Exception as exc:  # pragma: no cover - defensive
            return "failed", f"{experiment_id}: erro inesperado ({exc}).", None, False
        finally:
            self.project_manager.set_active_zone_video(None)

    def _schedule_analysis_metadata_update(self, metadata: dict) -> None:
        if self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_UPDATE_ANALYSIS_METADATA, {"metadata": metadata}
            )

    def _notify_task_status_start(self, *, index: int, total: int, experiment_id: str) -> None:
        if self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_UPDATE_ANALYSIS_TASK_STATUS,
                {"payload": {"index": index, "total": total, "experiment_id": experiment_id}},
            )

    def _make_progress_callback(
        self,
        *,
        index: int,
        total_videos: int,
        experiment_id: str,
    ):
        def progress_callback(
            progress_fraction,
            status_message,
            frame=None,
            stats=None,
            detections=None,
        ):
            if self.cancel_event.is_set():
                return

            overall_progress = f"Processando {index + 1}/{total_videos}: {experiment_id}"
            step_status = f"Etapa: {status_message}"
            # Phase 4: Use UICoordinator for UI updates
            self.ui_coordinator.set_status(self.view, f"{overall_progress} - {step_status}")
            self.ui_coordinator.update_progress(self.view, progress_fraction)
            self.ui_coordinator.update_view(
                self.view, "update_analysis_progress", progress_fraction, step_status
            )
            self.ui_event_bus.publish(
                Events.UI_UPDATE_ANALYSIS_TASK_STATUS,
                {
                    "payload": {
                        "index": index,
                        "total": total_videos,
                        "experiment_id": experiment_id,
                        "step": status_message,
                    }
                },
            )

            if stats:
                if self.ui_event_bus:
                    self.ui_event_bus.publish_event(
                        Events.UI_UPDATE_PROCESSING_STATS, {"stats": stats}
                    )

            processing_report = self._publish_processing_mode(
                source="analysis_progress",
                force=False,
            )

            if detections is not None:
                if self.ui_event_bus:
                    self.ui_event_bus.publish_event(
                        Events.UI_UPDATE_DETECTION_OVERLAY,
                        {"detections": detections, "report": processing_report},
                    )

            if frame is not None:
                if self.ui_event_bus:
                    self.ui_event_bus.publish_event(Events.UI_DISPLAY_FRAME, {"frame": frame})

        return progress_callback

    # Phase 7.2b: Removed 4 auxiliary methods (75 lines) -
    # migrated to VideoProcessingService:
    # - _display_initial_frame
    # - _resolve_results_path
    # - _ensure_arena_polygon
    # - _load_trajectory_dataframe

    def _collect_params_from_single_video(self, config: dict, experiment_id: str):
        """Extract parameters from single video config (Phase 7.3)."""
        metadata = dict(config)
        metadata.setdefault("experiment_id", experiment_id)
        metadata.setdefault("video_name", experiment_id)
        if not metadata.get("group_id"):
            metadata["group_id"] = "single_video"

        return (
            metadata,
            config.get("aquarium_width_cm"),
            config.get("aquarium_height_cm"),
            config.get(
                "sharp_turn_threshold_deg_s", settings.video_processing.sharp_turn_threshold_deg_s
            ),
            config.get(
                "freezing_velocity_threshold", settings.video_processing.freezing_velocity_threshold
            ),
            config.get(
                "freezing_min_duration_s", settings.video_processing.freezing_min_duration_s
            ),
            config.get("smoothing_window_length", settings.trajectory_smoothing.window_length),
            config.get("smoothing_polyorder", settings.trajectory_smoothing.polyorder),
        )

    def _collect_params_from_project(
        self, metadata_context: dict | None, experiment_id: str, video_path: str
    ):
        """Extract parameters from project data (Phase 7.3)."""
        project_data = getattr(self.project_manager, "project_data", {}) or {}
        calibration = project_data.get("calibration", {})

        metadata = dict(metadata_context or {})
        csv_metadata = self.project_manager.get_metadata_for_experiment(experiment_id)
        if csv_metadata:
            metadata.update(csv_metadata)
        if not metadata:
            metadata = self.project_manager.derive_processing_metadata(experiment_id, video_path)
            log.info(
                "controller.processing.metadata_fallback",
                experiment_id=experiment_id,
                fields=list(metadata.keys()),
            )

        return (
            metadata,
            calibration.get("aquarium_width_cm"),
            calibration.get("aquarium_height_cm"),
            settings.video_processing.sharp_turn_threshold_deg_s,
            settings.video_processing.freezing_velocity_threshold,
            settings.video_processing.freezing_min_duration_s,
            settings.trajectory_smoothing.window_length,
            settings.trajectory_smoothing.polyorder,
        )

    def _collect_analysis_parameters(
        self,
        *,
        single_video_config: dict | None,
        metadata_context: dict | None,
        experiment_id: str,
        video_path: str,
    ) -> tuple[dict, float | None, float | None, float, float, float, int, int]:
        """Phase 7.3: Simplified via extraction of collection logic to submethods."""
        if single_video_config:
            return self._collect_params_from_single_video(single_video_config, experiment_id)
        else:
            return self._collect_params_from_project(metadata_context, experiment_id, video_path)

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
        if not all([width_cm, height_cm, arena_polygon_px]):
            return None, None, [], {}, None, None

        assert width_cm is not None
        assert height_cm is not None

        cal = Calibration(np.array(arena_polygon_px), width_cm, height_cm)
        video_width_px, video_height_px = cal.target_dims_px
        pixelcm_x, pixelcm_y = cal.pixel_per_cm_ratio

        warped_points = cal.transform_points(arena_polygon_px)
        arena_polygon_warped = [(float(point[0]), float(point[1])) for point in warped_points]
        rois: list[ROI] = []
        for i, polygon in enumerate(zone_data.roi_polygons):
            warped_points = cal.transform_points(polygon)
            roi_points_px = [(float(x), float(y)) for x, y in warped_points]
            roi_name = zone_data.roi_names[i] if i < len(zone_data.roi_names) else f"ROI {i + 1}"
            rois.append(
                ROI(
                    name=roi_name,
                    geometry=Polygon(roi_points_px),
                    coordinate_space="px",
                )
            )

        roi_colors = {
            (zone_data.roi_names[i] if i < len(zone_data.roi_names) else f"ROI {i + 1}"): color
            for i, color in enumerate(zone_data.roi_colors)
        }

        return cal, arena_polygon_warped, rois, roi_colors, pixelcm_x, pixelcm_y

    def _generate_reports_for_video(
        self,
        *,
        reporter: Reporter,
        experiment_id: str,
        results_dir: str,
        progress_callback,
    ) -> tuple[str, str, str]:
        summary_parquet_path = os.path.join(results_dir, f"{experiment_id}_summary.parquet")
        summary_excel_path = os.path.join(results_dir, f"{experiment_id}_summary.xlsx")
        report_docx_path = os.path.join(results_dir, f"{experiment_id}_report.docx")

        reporter.export_summary_data(summary_parquet_path, format="parquet")
        reporter.export_summary_data(summary_excel_path, format="excel")
        reporter.export_individual_report_step_by_step(report_docx_path, progress_callback)

        return summary_parquet_path, summary_excel_path, report_docx_path

    def _register_project_outputs(
        self,
        *,
        video_path: str,
        results_dir: str,
        trajectory_path: str,
        summary_parquet: str,
        summary_excel: str,
        report_path: str,
    ) -> None:
        self.project_manager.register_processing_outputs(
            video_path,
            results_dir=results_dir,
            trajectory_path=trajectory_path,
            summary_parquet=summary_parquet,
            summary_excel=summary_excel,
            report_path=report_path,
        )
        self.refresh_project_views(
            reason="processing_progress",
            append_summary=True,
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
        trajectory_path = os.path.join(results_dir, f"3_CoordMovimento_{experiment_id}.parquet")
        trajectory_df = self.video_processing_service.load_trajectory_dataframe(
            trajectory_path, experiment_id
        )
        if trajectory_df is None:
            return False

        profile_dict = analysis_profile if isinstance(analysis_profile, dict) else {}
        requested_track_ids_raw = profile_dict.get("track_ids", [])
        if isinstance(requested_track_ids_raw, (list, tuple, set)):
            requested_track_ids = list(requested_track_ids_raw)
        elif requested_track_ids_raw in (None, ""):
            requested_track_ids = []
        else:
            requested_track_ids = [requested_track_ids_raw]

        filtered_df = trajectory_df
        resolved_track_ids: list[str] = []

        if "track_id" in trajectory_df.columns:
            resolved_track_ids = sorted(
                {str(track) for track in trajectory_df["track_id"].dropna().unique().tolist()}
            )

            if requested_track_ids:
                requested_str = {
                    str(track).strip() for track in requested_track_ids if track not in (None, "")
                }

                mask = trajectory_df["track_id"].astype(str).isin(requested_str)
                narrowed = trajectory_df[mask]
                if narrowed.empty:
                    log.warning(
                        "controller.analysis.profile_track_miss",
                        video=experiment_id,
                        requested=list(requested_str),
                    )
                else:
                    filtered_df = narrowed
                    resolved_track_ids = sorted(requested_str)
        elif requested_track_ids:
            log.warning(
                "controller.analysis.profile_track_column_missing",
                video=experiment_id,
            )

        (
            metadata,
            width_cm,
            height_cm,
            sharp_turn_threshold,
            freezing_threshold,
            freezing_duration,
            smoothing_window,
            smoothing_polyorder,
        ) = self._collect_analysis_parameters(
            single_video_config=single_video_config,
            metadata_context=metadata_context,
            experiment_id=experiment_id,
            video_path=video_path,
        )

        if isinstance(profile_dict, dict):
            profile_name = profile_dict.get("name")
            if profile_name and isinstance(metadata, dict):
                metadata.setdefault("analysis_profile", profile_name)
            track_list = profile_dict.get("track_ids")
            if track_list and isinstance(metadata, dict):
                metadata.setdefault("analysis_profile_tracks", list(track_list))

        zone_data = self.project_manager.get_zone_data()
        arena_polygon_px = self.video_processing_service.ensure_arena_polygon(
            arena_polygon_px, video_path
        )
        if not all([width_cm, height_cm, arena_polygon_px]):
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro de Processamento",
                    "message": "Dados de calibração incompletos.",
                },
            )
            return False

        assert arena_polygon_px is not None

        (
            calibration,
            arena_polygon_warped,
            rois,
            roi_colors,
            pixelcm_x,
            pixelcm_y,
        ) = self._prepare_calibration_context(
            arena_polygon_px=arena_polygon_px,
            width_cm=width_cm,
            height_cm=height_cm,
            zone_data=zone_data,
        )

        if (
            not calibration
            or arena_polygon_warped is None
            or pixelcm_x is None
            or pixelcm_y is None
        ):
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro de Processamento",
                    "message": "Falha ao preparar dados de calibração.",
                },
            )
            return False

        reporter = Reporter(
            trajectory_df=filtered_df,
            metadata=metadata,
            pixelcm_x=pixelcm_x,
            pixelcm_y=pixelcm_y,
            video_height_px=calibration.target_dims_px[1],
            arena_polygon_px=arena_polygon_warped,
            rois=rois,
            fps=settings.video_processing.fps,
            roi_colors=roi_colors,
            video_path=video_path,
            calibration=calibration,
            sharp_turn_threshold=sharp_turn_threshold,
            freezing_threshold=freezing_threshold,
            freezing_duration=freezing_duration,
            smoothing_window_length=smoothing_window,
            smoothing_polyorder=smoothing_polyorder,
        )

        (
            summary_parquet_path,
            summary_excel_path,
            report_docx_path,
        ) = self._generate_reports_for_video(
            reporter=reporter,
            experiment_id=experiment_id,
            results_dir=results_dir,
            progress_callback=progress_callback,
        )

        social_summary: dict | None = None
        raw_social_config = profile_dict.get("social") if isinstance(profile_dict, dict) else {}
        social_config = raw_social_config if isinstance(raw_social_config, dict) else {}
        social_enabled = bool(social_config.get("enabled"))
        if (
            social_enabled
            and pixelcm_x is not None
            and pixelcm_y is not None
            and "track_id" in filtered_df.columns
        ):
            active_tracks = filtered_df["track_id"].dropna().unique().tolist()
            if len(active_tracks) > 1:
                try:
                    radius_cm = float(social_config.get("radius_cm", 5.0))
                except (TypeError, ValueError):
                    radius_cm = 5.0

                try:
                    social_summary = ROIAnalyzer.analyze_social_proximity(
                        filtered_df,
                        radius_cm,
                        pixelcm_x,
                        pixelcm_y,
                    )
                except Exception:  # pragma: no cover - defensive
                    log.warning(
                        "controller.analysis.social_failed",
                        video=experiment_id,
                        exc_info=True,
                    )

        profile_name = profile_dict.get("name", "default")
        self.ui_event_bus.publish_event(
            Events.UI_UPDATE_SOCIAL_SUMMARY,
            {"profile": profile_name, "stats": social_summary, "tracks": resolved_track_ids},
        )

        # Register outputs for both project and single video workflows
        # This ensures the video and reports appear in the UI tabs
        self._register_project_outputs(
            video_path=video_path,
            results_dir=results_dir,
            trajectory_path=trajectory_path,
            summary_parquet=summary_parquet_path,
            summary_excel=summary_excel_path,
            report_path=report_docx_path,
        )

        return True

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
        try:
            video_path = video_info.get("path")
            if not video_path:
                return False, None

            if metadata_context is None:
                metadata_context = self._build_metadata_context(
                    video_info=video_info,
                    single_video_config=single_video_config,
                    experiment_id=experiment_id,
                    video_path=video_path,
                )

            analysis_view_metadata = self._compose_analysis_view_metadata(
                experiment_id=experiment_id,
                video_path=video_path,
                metadata_context=metadata_context,
                single_video_config=single_video_config,
                analysis_profile=analysis_profile,
            )
            self._schedule_analysis_metadata_update(analysis_view_metadata)
            self._notify_task_status_start(
                index=index,
                total=total_videos,
                experiment_id=experiment_id,
            )

            self.project_manager.set_active_zone_video(video_path)
            progress_callback = self._make_progress_callback(
                index=index,
                total_videos=total_videos,
                experiment_id=experiment_id,
            )

            self.video_processing_service.display_initial_frame(video_path)

            results_path = self.video_processing_service.resolve_results_path(
                experiment_id=experiment_id,
                video_path=video_path,
                metadata_context=metadata_context,
                single_video_config=single_video_config,
                output_base_dir=output_base_dir,
            )
            results_dir = str(results_path)

            tracking_success, arena_polygon_px = self._run_tracking_if_needed(
                video_path,
                results_dir,
                experiment_id,
                progress_callback,
                calibration_data=single_video_config,
                analysis_interval_frames=analysis_interval_frames,
                display_interval_frames=display_interval_frames,
            )

            if self.cancel_event.is_set():
                return False, results_dir

            if not tracking_success:
                return False, results_dir

            analysis_success = self._run_analysis_pipeline(
                experiment_id=experiment_id,
                video_path=video_path,
                results_dir=results_dir,
                arena_polygon_px=arena_polygon_px,
                metadata_context=metadata_context,
                single_video_config=single_video_config,
                progress_callback=progress_callback,
                analysis_profile=analysis_profile,
            )

            return analysis_success, results_dir
        finally:
            # Release frame references
            if (
                hasattr(self, "detector")
                and self.detector
                and hasattr(self.detector, "clear_cache")
            ):
                self.detector.clear_cache()

    def apply_project_settings_to_batch(self, videos: list):
        """Aplica configurações do projeto a novos vídeos"""
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
        """Keep per-video results folders clean and archive older runs."""
        path = Path(results_dir)
        path.mkdir(parents=True, exist_ok=True)

        existing_items = [item for item in path.iterdir() if item.name != "history"]
        if not existing_items:
            return

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        history_root = path / "history"
        archive_dir = history_root / timestamp
        archive_dir.mkdir(parents=True, exist_ok=True)

        for item in existing_items:
            target = archive_dir / item.name
            shutil.move(str(item), str(target))

        log.info(
            "controller.results.archive_previous_run",
            results_dir=str(path),
            archive_dir=str(archive_dir),
            item_count=len(existing_items),
        )

    def _compose_analysis_view_metadata(
        self,
        *,
        experiment_id: str,
        video_path: str,
        metadata_context: dict | None,
        single_video_config: dict | None,
        analysis_profile: dict | None,
    ) -> dict:
        combined: dict = {}

        entry = self.project_manager.find_video_entry(
            path=video_path,
            experiment_id=experiment_id,
        )
        if entry:
            combined.update(dict(entry.get("metadata") or {}))
            for key in ("group", "group_display_name", "day", "subject"):
                value = entry.get(key)
                if value not in (None, "") and key not in combined:
                    combined[key] = value

        if metadata_context:
            for key, value in metadata_context.items():
                if value in (None, ""):
                    continue
                combined[key] = value

        if single_video_config:
            mapping = {
                "group_display_name": "group_display_name",
                "group_label": "group_display_name",
                "group_name": "group_display_name",
                "group_id": "group",
                "group": "group",
                "day": "day",
                "day_id": "day",
                "subject": "subject",
                "subject_id": "subject",
                "animal": "subject",
                "cobaia": "subject",
            }
            for source_key, target_key in mapping.items():
                value = single_video_config.get(source_key)
                if value in (None, ""):
                    continue
                combined.setdefault(target_key, value)

        combined.setdefault("experiment_id", experiment_id)

        if analysis_profile and isinstance(analysis_profile, dict):
            profile_name = analysis_profile.get("name")
            if profile_name:
                combined["analysis_profile"] = profile_name
            track_ids = analysis_profile.get("track_ids")
            if track_ids:
                combined["analysis_profile_tracks"] = list(track_ids)

        return combined

    def _create_processing_callbacks(self, videos_to_process: list[dict]) -> ProcessingCallbacks:
        """
        Creates thread-safe callbacks for the processing worker.
        All callbacks schedule UI updates via root.after() to ensure thread safety.
        """

        def on_started():
            """Called when processing starts."""
            # Phase 4: Use UICoordinator for UI updates
            self.ui_coordinator.show_progress_bar(self.view)
            self.ui_coordinator.set_status(
                self.view,
                f"Iniciando processamento para {len(videos_to_process)} vídeos...",
            )
            self.project_manager.set_active_zone_video(None)
            self._publish_processing_mode(source="worker.started", force=True)

        def on_progress(fraction: float, message: str, stats: dict | None):
            """Called with progress updates."""
            if self.cancel_event.is_set():
                return

            # Phase 4: Use UICoordinator for UI updates
            self.ui_coordinator.set_status(self.view, message)
            self.ui_coordinator.update_progress(self.view, fraction)
            self.ui_coordinator.update_view(
                self.view, "update_analysis_progress", fraction, message
            )

            if stats:
                # Update processing state in StateManager
                self.state_manager.update_processing_state(
                    source="controller.processing_progress",
                    current_frame=stats.get("current_frame", 0),
                    total_frames=stats.get("total_frames", 0),
                )

                self.ui_event_bus.publish(Events.UI_UPDATE_PROCESSING_STATS, {"stats": stats})

        def on_frame_processed(frame, detections, processing_info):
            """Called when a frame is ready for display."""
            if frame is not None:
                # Phase 4: Use UICoordinator for frame display
                self.ui_event_bus.publish(Events.UI_DISPLAY_FRAME, {"frame": frame})

            if detections is not None and processing_info:
                self.ui_event_bus.publish(
                    Events.UI_UPDATE_DETECTION_OVERLAY,
                    {"detections": detections, "report": processing_info},
                )

        def on_video_completed(index: int, total: int, experiment_id: str, success: bool):
            """Called when a single video completes."""
            log.info(
                "controller.video_completed",
                index=index,
                total=total,
                experiment_id=experiment_id,
                success=success,
            )

        def on_error(error: Exception, context: str):
            """Called when an error occurs."""
            log.error("controller.processing.worker_error", context=context, error=str(error))
            self.root.after(
                0,
                lambda: self.view.show_error("Erro na Análise", f"{context}: {error}"),
            )

        def _on_processing_fatal_error(exc, context, recovery_info):
            log.error(
                "controller.processing.fatal_error",
                context=context,
                error=str(exc),
                affected_videos=len(recovery_info["affected_videos"]),
            )
            self.ui_coordinator.schedule(
                lambda: self.view.show_error(
                    "Erro Crítico de Processamento",
                    f"{context}\n\nErro: {exc}\n\n"
                    f"Vídeos afetados: {len(recovery_info['affected_videos'])}\n"
                    f"Verifique os logs para detalhes.",
                )
            )
            self.state_manager.update_processing_state(
                source="worker.fatal_error", is_processing=False, error=str(exc)
            )
            self.ui_coordinator.set_status(self.view, "Processamento falhou")

        def on_completed(was_cancelled: bool, output_dir: str, summary: dict | None = None):
            """Called when all processing completes."""
            # Phase 4: Use UICoordinator for UI updates
            self.project_manager.set_active_zone_video(None)
            self.ui_coordinator.update_view(self.view, "stop_analysis_view_mode")
            self.ui_coordinator.hide_progress_bar(self.view)

            # Update processing state in StateManager
            self.state_manager.update_processing_state(
                source="controller.processing_completed",
                is_processing=False,
                cancel_requested=was_cancelled,
                current_video=None,
            )

            if was_cancelled:
                self.ui_coordinator.show_info(
                    self.view, "Cancelado", "A análise de vídeo foi cancelada."
                )
            elif videos_to_process:
                msg = f"Análise concluída. Resultados salvos em:\n{output_dir}"
                self.ui_coordinator.show_info(self.view, "Sucesso", msg)

            self.ui_coordinator.set_status(self.view, "Pronto.")
            self._publish_processing_mode(source="worker.completed", force=True)
            self.refresh_project_views()

        return ProcessingCallbacks(
            on_started=on_started,
            on_progress=on_progress,
            on_frame_processed=on_frame_processed,
            on_video_completed=on_video_completed,
            on_error=on_error,
            on_completed=on_completed,
            on_fatal_error=_on_processing_fatal_error,
        )

    def _create_processing_context(
        self,
        videos_to_process: list[dict],
        output_base_dir: str,
        single_video_config: dict | None = None,
    ) -> ProcessingContext:
        """
        Creates the processing context with all necessary configuration.
        """
        return ProcessingContext(
            videos_to_process=videos_to_process,
            output_base_dir=output_base_dir,
            cancel_event=self.cancel_event,
            single_video_config=single_video_config,
            analysis_interval_frames=10,  # Will be updated by worker
            display_interval_frames=10,  # Will be updated by worker
            process_single_video_func=self._process_single_video,
            apply_project_settings_func=self.apply_project_settings_to_batch,
            determine_intervals_func=self._determine_processing_intervals,
            retry_strategy=settings.video_processing.batch_retry_strategy,
        )

    def _process_videos(
        self,
        videos_to_process: list[dict],
        output_base_dir: str,
        single_video_config: dict | None = None,
    ):
        """
        Private helper to process a list of videos and save results. This is
        designed to be run in a background thread.

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
        """
        Generates a report from a list of processed videos.
        """
        log.info("reports.generate.start", count=len(videos), type=report_type)
        if not videos:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_WARNING,
                {"title": "Nenhum Vídeo", "message": "Nenhum vídeo selecionado para o relatório."},
            )
            return

        all_tidy_data = []

        for video_info in videos:
            video_path = video_info.get("path")
            if not isinstance(video_path, str) or not video_path:
                log.warning(
                    "reports.load.invalid_path",
                    video_info=video_info,
                )
                continue
            experiment_id = os.path.splitext(os.path.basename(video_path))[0]
            metadata_hint = dict(video_info.get("metadata") or {})
            results_path = self.project_manager.resolve_results_directory(
                experiment_id,
                video_path=video_path,
                metadata=metadata_hint,
            )
            summary_path = results_path / f"{experiment_id}_summary.parquet"

            if summary_path.exists():
                try:
                    df = pd.read_parquet(summary_path)
                    all_tidy_data.append(df)
                except Exception as e:
                    log.warning("reports.load.error", path=str(summary_path), error=e)
            else:
                log.warning("reports.load.not_found", path=str(summary_path))

        if not all_tidy_data:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro no Relatório",
                    "message": "Não foi possível encontrar dados de resumo para os vídeos selecionados.",  # noqa: E501
                },
            )
            return

        aggregated_df = pd.concat(all_tidy_data, ignore_index=True)
        save_path = self.view.ask_save_filename(
            title=f"Salvar Relatório {report_type.capitalize()}",
            defaultextension=".xlsx",
            initialfile=f"{report_type}_report.xlsx",
            filetypes=[
                ("Pasta de Trabalho do Excel", "*.xlsx"),
                ("Arquivo CSV", "*.csv"),
                ("Arquivo Parquet", "*.parquet"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if not save_path:
            return

        # Determine format from extension and export data
        file_extension = os.path.splitext(save_path)[1].lower()
        if file_extension == ".xlsx":
            aggregated_df.to_excel(save_path, index=False)
        elif file_extension == ".csv":
            aggregated_df.to_csv(save_path, index=False)
        elif file_extension == ".parquet":
            aggregated_df.to_parquet(save_path, index=False)
        else:
            # Default to Excel if extension is unknown or missing
            if not file_extension:
                save_path += ".xlsx"
            aggregated_df.to_excel(save_path, index=False)

        # Also generate the visual .docx report, except for parquet
        if file_extension != ".parquet":
            docx_path = os.path.splitext(save_path)[0] + "_report.docx"
            Reporter.export_project_report(aggregated_df, docx_path)

        if self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {"title": "Relatório Gerado", "message": f"Relatório salvo em:\n{save_path}"},
            )

    def run_model_diagnostic(self, config: dict):
        """
        Prepares for and launches the diagnostic test in a background thread.
        """
        log.info("controller.diagnostic.start", config=config)
        self.view.set_status("Iniciando diagnóstico do modelo...")
        self.view.update_idletasks()

        model_to_test = config["model_to_test"]
        active_weight_details = self.weight_manager.get_weight_details(self.active_weight_name)
        log.info(
            "controller.diagnostic.active_weight",
            active_weight_name=self.active_weight_name,
            pytorch_path=(active_weight_details.get("path") if active_weight_details else None),
            openvino_path=(
                active_weight_details.get("openvino_path") if active_weight_details else None
            ),
        )
        if not active_weight_details:
            self.ui_event_bus.publish(
                Events.UI_SHOW_ERROR,
                {"title": "Erro", "message": "Nenhum peso ativo selecionado."},
            )
            return

        # --- Pre-flight checks (OpenVINO conversion) ---
        if model_to_test in ["OpenVINO", "Ambos"]:
            ov_path = active_weight_details.get("openvino_path")
            if not ov_path or not os.path.exists(ov_path):
                if self.view.ask_ok_cancel(
                    "Converter Modelo?",
                    "O modelo OpenVINO não foi encontrado. Deseja convertê-lo agora?",
                ):
                    self.convert_active_weight_to_openvino(dialog=None)
                    # Refresh details after conversion
                    active_weight_details = self.weight_manager.get_weight_details(
                        self.active_weight_name
                    )
                    if not active_weight_details.get("openvino_path"):
                        self.ui_event_bus.publish(
                            Events.UI_SHOW_ERROR,
                            {"title": "Erro", "message": "A conversão para OpenVINO falhou."},
                        )
                        return
                else:
                    log.warning("diagnostic.openvino.conversion_skipped")
                    # If user skips conversion, modify config to only run YOLO if
                    # possible
                    if model_to_test == "Ambos":
                        config["model_to_test"] = "YOLO (PyTorch)"
                    else:  # model_to_test was 'OpenVINO'
                        self.ui_event_bus.publish(
                            Events.UI_SET_STATUS, {"message": "Diagnóstico cancelado."}
                        )
                        return

        # --- Launch background thread ---
        self.cancel_event.clear()
        self._publish_processing_mode(
            source="diagnostic.start",
            force=True,
            mode_override=ProcessingMode.SINGLE_SUBJECT,
        )
        thread = threading.Thread(
            target=self._diagnostic_processing_thread,
            args=(config, active_weight_details),
            daemon=True,
        )
        thread.start()

    def _diagnostic_processing_thread(self, config: dict, weight_details: dict):
        """
        The actual diagnostic processing logic that runs in a background thread.
        """
        video_path = config["video_path"]
        frames_to_analyze = config["frames_to_analyze"]
        conf_threshold = config["confidence_threshold"]
        model_to_test = config["model_to_test"]
        results = {}

        # --- Model Loading ---
        yolo_model = None
        openvino_model = None

        try:
            if model_to_test in ["YOLO (PyTorch)", "Ambos"]:
                if not ULTRALYTICS_AVAILABLE:
                    log.error("diagnostic.yolo.unavailable")
                    config["update_progress"](
                        "Erro: YOLO não está disponível (ultralytics não instalado)"
                    )
                    return

                yolo_model = YOLO(weight_details["path"])
                # Define contexto diagnóstico
                if hasattr(yolo_model, "set_context"):
                    yolo_model.set_context("diagnostic")
                    log.info("diagnostic.thread.yolo_context_set", context="diagnostic")
                results["YOLO (PyTorch)"] = []

            if model_to_test in ["OpenVINO", "Ambos"]:
                ov_path = weight_details.get("openvino_path")
                if ov_path and os.path.exists(ov_path):
                    plugin_class = DETECTOR_PLUGINS.get("OpenVINO")
                    if plugin_class:
                        openvino_model = plugin_class(ov_path)
                        # Verify the plugin has the required predict method
                        if not hasattr(openvino_model, "predict"):
                            log.error(
                                "diagnostic.thread.missing_predict_method",
                                plugin_class=str(plugin_class),
                            )
                            self.ui_event_bus.publish(
                                Events.UI_SHOW_ERROR,
                                {
                                    "title": "Erro de Plugin",
                                    "message": "O plugin OpenVINO não possui o método predict "
                                    "necessário para diagnóstico.",
                                },
                            )
                            return
                        # Set diagnostic context to allow all classes
                        if hasattr(openvino_model, "set_context"):
                            openvino_model.set_context("diagnostic")
                            log.info(
                                "diagnostic.thread.openvino_context_set",
                                context="diagnostic",
                            )
                        results["OpenVINO"] = []
                        log.info("diagnostic.thread.openvino_loaded", path=ov_path)

            # --- Video Processing ---
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                self.ui_event_bus.publish(
                    Events.UI_SHOW_ERROR,
                    {"title": "Erro", "message": f"Não foi possível abrir o vídeo: {video_path}"},
                )
                return

            for frame_count in range(frames_to_analyze):
                if self.cancel_event.is_set():
                    break
                ret, frame = cap.read()
                if not ret:
                    break

                status_msg = f"Analisando frame {frame_count + 1}/{frames_to_analyze}..."
                self.ui_event_bus.publish(Events.UI_SET_STATUS, {"message": status_msg})

                if yolo_model:
                    preds = yolo_model.predict(frame, conf=conf_threshold, verbose=False)
                    results.setdefault("YOLO (PyTorch)", []).append(preds[0])

                if openvino_model:
                    try:
                        log.debug(
                            "diagnostic.thread.openvino_predict_start",
                            frame=frame_count + 1,
                        )
                        preds = openvino_model.predict(frame, conf_threshold)
                        log.debug(
                            "diagnostic.thread.openvino_predict_success",
                            frame=frame_count + 1,
                            detections=len(preds),
                        )
                        results.setdefault("OpenVINO", []).append(preds)
                    except Exception as e:
                        log.error(
                            "diagnostic.thread.openvino_predict_error",
                            frame=frame_count + 1,
                            exc_info=True,
                        )
                        self.ui_event_bus.publish(
                            Events.UI_SHOW_ERROR,
                            {
                                "title": "Erro de Inferência OpenVINO",
                                "message": f"Falha na inferência do frame {frame_count + 1}: {e}",
                            },
                        )
                        return
            cap.release()

            # --- Schedule report generation on main thread ---
            self.root.after(0, self._finish_diagnostic_and_save_report, config, results)
        except Exception as e:
            log.error("diagnostic.thread.load_error", exc_info=True)
            self.ui_event_bus.publish(
                Events.UI_SHOW_ERROR,
                {"title": "Erro ao Carregar Modelo", "message": f"Falha: {e}"},
            )
        finally:
            self._publish_processing_mode(
                source="diagnostic.thread_exit",
                force=True,
            )

    def _finish_diagnostic_and_save_report(self, config, results):
        """Formats and saves the report. Runs on the main UI thread."""
        report_str = self._format_diagnostic_report(config, results)
        save_path = self.view.ask_save_filename(
            title="Salvar Relatório de Diagnóstico",
            defaultextension=".txt",
            initialfile="diagnostic_report.txt",
            filetypes=[("Arquivos de Texto", "*.txt")],
        )

        if save_path:
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(report_str)
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Sucesso",
                        "message": f"Relatório de diagnóstico salvo em:\n{save_path}",
                    },
                )
            except OSError as e:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro ao Salvar",
                        "message": f"Não foi possível salvar o arquivo: {e}",
                    },
                )

        self._publish_processing_mode(
            source="diagnostic.complete",
            force=True,
        )
        self.ui_event_bus.publish_event(
            Events.UI_SET_STATUS, {"message": "Diagnóstico concluído. Pronto."}
        )

    def _format_diagnostic_report(self, config, results) -> str:
        """Formats the collected diagnostic data into a string."""
        report_lines = [
            "Relatório de Diagnóstico do Modelo",
            "-----------------------------------",
            f"- Vídeo: {config['video_path']}",
            f"- Frames Analisados: {config['frames_to_analyze']}",
            f"- Limiar de Confiança: {config['confidence_threshold']}",
            "-----------------------------------",
            "",
        ]

        for model_name, preds_list in results.items():
            report_lines.append(f"--- [ RESULTADOS {model_name.upper()} ] ---")
            report_lines.append("")

            for i, preds in enumerate(preds_list):
                frame_num = i + 1
                report_lines.append(f"Frame {frame_num}:")

                detections = []
                mask_only_detections = []

                # Handle ultralytics results object
                if hasattr(preds, "boxes") or hasattr(preds, "masks"):
                    # Processa boxes com suas máscaras
                    if preds.boxes is not None:
                        for j, box in enumerate(preds.boxes):
                            class_id = int(box.cls)
                            class_name = preds.names.get(class_id, "desconhecido")
                            conf = float(box.conf)
                            bbox = [int(coord) for coord in box.xyxy[0]]

                            # Verifica se tem máscara
                            has_mask = (
                                preds.masks is not None
                                and preds.masks.xy is not None
                                and j < len(preds.masks.xy)
                            )
                            mask_info = (
                                f", Máscara: {len(preds.masks.xy[j])} pontos" if has_mask else ""
                            )

                            detections.append(
                                f"  - Classe {class_id} ('{class_name}'), "
                                f"Conf: {conf:.2f}, BBox: {bbox}{mask_info}"
                            )

                    # Processa máscaras sem boxes (órfãs)
                    if preds.masks is not None and preds.masks.xy is not None:
                        num_boxes = len(preds.boxes) if preds.boxes else 0
                        for j in range(num_boxes, len(preds.masks.xy)):
                            mask = preds.masks.xy[j]
                            x_min = int(mask[:, 0].min())
                            y_min = int(mask[:, 1].min())
                            x_max = int(mask[:, 0].max())
                            y_max = int(mask[:, 1].max())
                            area = (x_max - x_min) * (y_max - y_min)

                            mask_only_detections.append(
                                f"  - [MÁSCARA SEM BOX] Provável Aquário, "
                                f"BBox aprox: [{x_min}, {y_min}, {x_max}, {y_max}], "
                                f"Área: {area}, Pontos: {len(mask)}"
                            )

                # Handle OpenVINO plugin format
                elif isinstance(preds, list):
                    for det in preds:
                        class_id = det["class_id"]
                        class_name = det["class_name"]
                        conf = det["confidence"]
                        bbox = det["box"]
                        mask_info = (
                            f", Máscara: {det.get('mask_points', 0)} pontos"
                            if det.get("has_mask")
                            else ""
                        )

                        detections.append(
                            f"  - Classe {class_id} ('{class_name}'), "
                            f"Conf: {conf:.2f}, BBox: {bbox}{mask_info}"
                        )

                # Adiciona detecções ao relatório
                if detections:
                    report_lines.extend(detections)
                if mask_only_detections:
                    report_lines.append("  Máscaras sem bounding box (possíveis aquários):")
                    report_lines.extend(mask_only_detections)
                if not detections and not mask_only_detections:
                    report_lines.append("  - Nenhuma detecção encontrada.")

                report_lines.append("")

            report_lines.append("")  # Spacer between models

        return "\n".join(report_lines)


# -----------------------------------------------------------------------------
# Backward Compatibility Alias (Phase 1, Step 3)
# -----------------------------------------------------------------------------
# Maintain backward compatibility during migration.
# All existing code can continue importing AppController.
# New code should prefer MainViewModel for clarity.

AppController = MainViewModel
