import argparse
import logging
import logging.handlers
import sys
import threading
import time
import tkinter as tk
import warnings
from tkinter import messagebox

import structlog

# Suppress pkg_resources deprecation from docxcompose (setuptools pinned to <81)
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated",
    category=UserWarning,
    module="docxcompose.properties",
)


class CompactConsoleRenderer(structlog.dev.ConsoleRenderer):
    """Custom renderer with minimal spacing for compact output."""

    def __call__(self, logger, name, event_dict):
        """Render log with minimal spacing."""
        # Call parent renderer
        result = super().__call__(logger, name, event_dict)
        # Reduce excessive whitespace to single space
        import re

        # Replace multiple spaces with single space (but preserve single spaces)
        result = re.sub(r"  +", " ", result)
        return result


def configure_logging():
    """
    Configures logging for the application.

    This function sets up structlog to process logs with a consistent format
    for both application logs and standard library/third-party logs.
    Uses CompactConsoleRenderer for minimal spacing in output.
    """
    # Shared processors for both structlog and stdlib logging
    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Configure structlog with ConsoleRenderer for compact output
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Formatter for console output (human-readable, compact)
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processor=CompactConsoleRenderer(
            colors=True,
            pad_event=1,  # Minimal padding (1 space between event and fields)
        ),
    )

    # Formatter for file output (JSON for structured logs)
    file_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
    )

    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        "analysis.log", maxBytes=5 * 1024 * 1024, backupCount=5, mode="a"
    )
    file_handler.setFormatter(file_formatter)

    # Console handler for development
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)

    # Configure root logger to route ALL logs (including stdlib/libs) through structlog
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    root_logger.setLevel(logging.INFO)


def main():
    """
    Initializes and runs the application.
    """
    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(description="ZebTrack-AI: Multi-animal tracking.")
    parser.add_argument(
        "--log-level",
        action="append",
        help="Override log level: MODULE=LEVEL (e.g., zebtrack.core.detector=DEBUG)",
    )
    args = parser.parse_args()

    # --- Logging Configuration ---
    configure_logging()
    from zebtrack.logging_config import configure_logging_levels

    # Called twice by design:
    # 1. Here: Initial call with None (does nothing, but import must happen before settings load)
    # 2. After settings load: Applies logging levels from config.yaml
    configure_logging_levels()

    # Apply CLI overrides after initial configuration
    if args.log_level:
        for override in args.log_level:
            try:
                module, level = override.split("=", 1)
                level_upper = level.upper()
                # Basic validation, though setLevel handles unknown strings
                if level_upper not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
                    print(f"Warning: Invalid log level '{level}' in override. Ignoring.")
                    continue

                logging.getLogger(module).setLevel(level_upper)
                print(f"CLI override: Set log level for '{module}' to '{level_upper}'")
            except ValueError:
                print(f"Warning: Invalid --log-level format '{override}'. Use MODULE=LEVEL.")

    log = structlog.get_logger()

    # Configuration constants
    SPLASH_DISPLAY_DURATION_MS = 300  # Time to show "Pronto!" message before closing splash

    # ========================================================================
    # COMPOSITION ROOT: Dependency Injection Setup
    # ========================================================================
    # This is where all dependencies are created and wired together.
    # The application follows Inversion of Control (IoC) pattern.

    # Import zebtrack modules after logging is configured
    from zebtrack.settings import load_settings
    from zebtrack.ui.window_utils import maximize_window
    from zebtrack.utils import set_seed

    # Load settings (Composition Root responsibility)
    try:
        settings_obj = load_settings()
        log.info(
            "settings.loaded",
            camera_index=settings_obj.camera.index,
            yolo_path=settings_obj.yolo_model.path,
        )
        # Apply logging levels from loaded settings
        configure_logging_levels(settings_obj)
    except FileNotFoundError as e:
        log.critical("settings.load.file_not_found", error=str(e))
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Configuration File Not Found",
            f"Could not find configuration file: {e}\n\n"
            "The application requires 'config.yaml' to start.",
        )
        sys.exit(1)
    except ValueError as e:
        # ValueError is raised by load_settings() for YAML parse errors and validation errors
        log.critical("settings.load.validation_error", error=str(e))
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Configuration Validation Error",
            f"Configuration file contains invalid values:\n\n{e}\n\n"
            "Please check your config.yaml file.",
        )
        sys.exit(1)

    # Set seed for reproducibility
    if settings_obj.reproducibility and settings_obj.reproducibility.seed:
        set_seed(settings_obj.reproducibility.seed)
        log.info("reproducibility.seed.set", seed=settings_obj.reproducibility.seed)

    log.info("application.starting", component="main")

    try:
        # Create Tkinter root FIRST (required for Toplevel widgets)
        root = tk.Tk()
        root.withdraw()  # Hide main window while loading

        # Set application icon
        from zebtrack.ui.icon_utils import set_window_icon

        set_window_icon(root)

        # Create splash screen (lightweight, shows immediately)
        from zebtrack.ui.splash_screen import create_splash

        splash = create_splash(parent=root)
        splash.update_status("Carregando configurações...")

        # ===== DEPENDENCY INJECTION: Create all services =====

        # Core infrastructure
        from zebtrack.core.state_manager import StateManager
        from zebtrack.core.ui_coordinator import UICoordinator
        from zebtrack.ui.event_bus import EventBus

        event_bus = EventBus()
        state_manager = StateManager(enable_history=True, max_history_size=100)
        ui_coordinator = UICoordinator(root=root, event_bus=event_bus)

        splash.update_status("Carregando sistema de modelos...")

        # Model and weight management
        _t0 = time.perf_counter()
        from zebtrack.core.model_service import ModelService
        from zebtrack.core.weight_manager import WeightManager

        weight_manager = WeightManager(settings_obj=settings_obj)
        model_service = ModelService(weight_manager)
        log.info("timing.model_service", elapsed_ms=int((time.perf_counter() - _t0) * 1000))

        splash.update_status("Inicializando gerenciador de projetos...")

        # Project management
        _t0 = time.perf_counter()
        from zebtrack.core.project_manager import ProjectManager
        from zebtrack.core.project_workflow_service import ProjectWorkflowService

        log.info(
            "timing.import_project_manager", elapsed_ms=int((time.perf_counter() - _t0) * 1000)
        )

        _t0 = time.perf_counter()
        project_manager = ProjectManager(state_manager=state_manager, settings_obj=settings_obj)
        log.info("timing.project_manager_init", elapsed_ms=int((time.perf_counter() - _t0) * 1000))

        _t0 = time.perf_counter()
        project_workflow_service = ProjectWorkflowService(
            project_manager=project_manager,
            model_service=model_service,
            state_manager=state_manager,
            ui_coordinator=ui_coordinator,
            settings_obj=settings_obj,
        )
        log.info(
            "timing.project_workflow_service", elapsed_ms=int((time.perf_counter() - _t0) * 1000)
        )

        splash.update_status("Configurando detector...")

        # Detector service
        _t0 = time.perf_counter()
        from zebtrack.core.detector_service import DetectorService

        detector_service = DetectorService(
            state_manager=state_manager,
            project_manager=project_manager,
            weight_manager=weight_manager,
            model_service=model_service,
            settings_obj=settings_obj,
        )
        log.info("timing.detector_service", elapsed_ms=int((time.perf_counter() - _t0) * 1000))

        splash.update_status("Preparando processamento de vídeo...")

        # Video processing service
        _t0 = time.perf_counter()
        from zebtrack.core.video_processing_service import VideoProcessingService
        from zebtrack.io.recorder_factory import RecorderFactory

        # Create recorder factory (lazy-loads on first use)
        recorder_factory = RecorderFactory(settings_obj=settings_obj)
        log.info("timing.recorder_factory_init", elapsed_ms=int((time.perf_counter() - _t0) * 1000))

        splash.update_status("Criando interface gráfica...")

        _t0 = time.perf_counter()
        cancel_event = threading.Event()

        # VideoProcessingService is created before detector exists
        # The detector is lazy-initialized later via detector_service.initialize_detector()
        # when a project is created/loaded. This is by design to support different
        # detection methods (seg/det) and backends (YOLO/OpenVINO) per project.
        video_processing_service = VideoProcessingService(
            detector=None,  # Lazy-initialized by detector_service.initialize_detector()
            recorder=recorder_factory,  # Lazy-loads when first used
            project_manager=project_manager,
            state_manager=state_manager,
            ui_coordinator=ui_coordinator,
            ui_event_bus=event_bus,
            root=root,
            view=None,  # Set after ApplicationGUI is created
            cancel_event=cancel_event,
            settings_obj=settings_obj,
        )
        log.info(
            "timing.video_processing_service", elapsed_ms=int((time.perf_counter() - _t0) * 1000)
        )

        # Analysis service
        _t0 = time.perf_counter()
        from zebtrack.analysis.analysis_service import AnalysisService

        analysis_service = AnalysisService(settings_obj=settings_obj)
        log.info("timing.analysis_service", elapsed_ms=int((time.perf_counter() - _t0) * 1000))

        # ===== SUPER COORDINATORS (Phase 3 Consolidation) =====
        # Four super coordinators replace 20 legacy coordinators/orchestrators
        # Architecture: Zero MainViewModel dependency, pure dependency injection

        _t0 = time.perf_counter()
        from zebtrack.coordinators.hardware_coordinator import HardwareCoordinator
        from zebtrack.coordinators.processing_coordinator import ProcessingCoordinator
        from zebtrack.coordinators.project_lifecycle_coordinator import ProjectLifecycleCoordinator
        from zebtrack.coordinators.session_coordinator import SessionCoordinator

        # Additional services needed by coordinators
        from zebtrack.core.project_service import ProjectService
        from zebtrack.ui.project_workflow_adapter import ProjectWorkflowAdapter

        project_service = ProjectService()
        project_workflow_adapter = ProjectWorkflowAdapter(
            project_workflow_service=project_workflow_service,
            project_manager=project_manager,
            detector_service=detector_service,
            state_manager=state_manager,
            ui_event_bus=event_bus,
        )

        # 1. ProjectLifecycleCoordinator - Project & calibration workflows
        _t0_proj = time.perf_counter()
        project_lifecycle_coordinator = ProjectLifecycleCoordinator(
            state_manager=state_manager,
            project_manager=project_manager,
            project_workflow_service=project_workflow_service,
            project_workflow_adapter=project_workflow_adapter,
            settings_obj=settings_obj,
            event_bus=event_bus,
        )
        log.info(
            "timing.project_lifecycle_coordinator",
            elapsed_ms=int((time.perf_counter() - _t0_proj) * 1000),
        )

        # 2. HardwareCoordinator - Detector setup, zones, model diagnostics
        _t0_hw = time.perf_counter()
        hardware_coordinator = HardwareCoordinator(
            state_manager=state_manager,
            detector_service=detector_service,
            weight_manager=weight_manager,
            model_service=model_service,
            event_bus=event_bus,
            cancel_event=cancel_event,
            root=root,
            view=None,  # Set after ApplicationGUI is created
        )
        log.info(
            "timing.hardware_coordinator",
            elapsed_ms=int((time.perf_counter() - _t0_hw) * 1000),
        )

        # 3. ProcessingCoordinator - Video processing, analysis, zones/arena management
        _t0_proc = time.perf_counter()

        # Import additional services for ProcessingCoordinator
        from zebtrack.core.video_classification_service import VideoClassificationService
        from zebtrack.core.video_selection_service import VideoSelectionService
        from zebtrack.core.video_validation_service import VideoValidationService
        from zebtrack.orchestrators.ui_state_controller import UIStateController

        video_selection_service = VideoSelectionService()
        video_validation_service = VideoValidationService()
        video_classification_service = VideoClassificationService()
        ui_state_controller = UIStateController(
            root=root,
            ui_event_bus=event_bus,
            state_manager=state_manager,
            ui_coordinator=ui_coordinator,
            project_manager=project_manager,
            weight_manager=weight_manager,
            detector_service=detector_service,
            model_service=model_service,
            settings=settings_obj,
            detector_coordinator=hardware_coordinator,
            project_workflow_service=project_workflow_service,
        )

        processing_coordinator = ProcessingCoordinator(
            state_manager=state_manager,
            project_manager=project_manager,
            detector_service=detector_service,
            weight_manager=weight_manager,
            settings_obj=settings_obj,
            ui_coordinator=ui_coordinator,
            ui_state_controller=ui_state_controller,
            cancel_event=cancel_event,
            video_selection_service=video_selection_service,
            video_validation_service=video_validation_service,
            video_classification_service=video_classification_service,
            analysis_service=analysis_service,
            recorder_factory=recorder_factory,
            event_bus=event_bus,
            view=None,  # Set after ApplicationGUI is created
            root=root,
            detector=None,  # Set after detector is initialized
        )
        log.info(
            "timing.processing_coordinator",
            elapsed_ms=int((time.perf_counter() - _t0_proc) * 1000),
        )

        # 4. SessionCoordinator - Recording sessions, live camera, Arduino triggers
        _t0_sess = time.perf_counter()

        # RecordingService and LiveCameraService will be created by SessionCoordinator
        # Note: These are temporarily created here for backward compatibility
        # In future sprints, they should be created directly by SessionCoordinator
        from zebtrack.core.live_camera_service import LiveCameraService
        from zebtrack.core.recording_service import RecordingService

        # Create services (will be passed to SessionCoordinator)
        # Note: controller parameter is temporary - will be removed in future refactoring
        recording_service = RecordingService(
            controller=None,  # Will be set by MainViewModel for backward compatibility
            state_manager=state_manager,
            project_manager=project_manager,
            root=root,
        )

        live_camera_service = LiveCameraService(
            controller=None,  # Will be set by MainViewModel for backward compatibility
            state_manager=state_manager,
            project_manager=project_manager,
            recording_service=recording_service,
            detector_service=detector_service,
            root=root,
        )

        session_coordinator = SessionCoordinator(
            state_manager=state_manager,
            recording_service=recording_service,
            live_camera_service=live_camera_service,
            project_manager=project_manager,
            detector_service=detector_service,
            weight_manager=weight_manager,
            settings_obj=settings_obj,
            event_bus=event_bus,
            arduino_manager=None,  # Will be set when Arduino is initialized
            root=root,
            view=None,  # Set after ApplicationGUI is created
        )
        log.info(
            "timing.session_coordinator",
            elapsed_ms=int((time.perf_counter() - _t0_sess) * 1000),
        )

        log.info("timing.all_coordinators_init", elapsed_ms=int((time.perf_counter() - _t0) * 1000))

        splash.update_status("Finalizando inicialização...")

        # Create MainViewModel with all injected dependencies
        _t0 = time.perf_counter()
        from zebtrack.core.application_bootstrapper import ApplicationBootstrapper
        from zebtrack.core.dependency_container import MainViewModelDependencies
        from zebtrack.core.main_view_model import MainViewModel

        log.info("timing.import_mainviewmodel", elapsed_ms=int((time.perf_counter() - _t0) * 1000))

        _t0 = time.perf_counter()

        dependencies = MainViewModelDependencies(
            root=root,
            settings_obj=settings_obj,
            event_bus=event_bus,
            state_manager=state_manager,
            ui_coordinator=ui_coordinator,
            project_manager=project_manager,
            project_workflow_service=project_workflow_service,
            weight_manager=weight_manager,
            model_service=model_service,
            detector_service=detector_service,
            video_processing_service=video_processing_service,
            analysis_service=analysis_service,
            recording_service=recording_service,
            live_camera_service=live_camera_service,
            # Phase 3: Four super coordinators replace legacy coordinators
            project_lifecycle_coordinator=project_lifecycle_coordinator,
            hardware_coordinator=hardware_coordinator,
            processing_coordinator=processing_coordinator,
            session_coordinator=session_coordinator,
        )

        # Use Bootstrapper to complete initialization
        bootstrapper = ApplicationBootstrapper(dependencies)

        # Create controller proxy to handle circular dependencies in legacy code
        controller_proxy = MainViewModel.__new__(MainViewModel)

        # Initialize using bootstrapper
        bootstrap_result = bootstrapper.initialize(controller_proxy)

        # Complete MainViewModel initialization
        controller_proxy.__init__(dependencies, bootstrap_result)

        # Use the fully initialized controller
        controller = controller_proxy

        log.info("timing.mainviewmodel_init", elapsed_ms=int((time.perf_counter() - _t0) * 1000))

        # Set view reference in video_processing_service after view is created
        video_processing_service.view = controller.view
        ui_state_controller.view = controller.view
        ui_state_controller.main_view_model = controller

        # Bind events
        controller.bind_events()

        # Close splash and show main window
        splash.update_status("Pronto!")
        root.update()  # Force update to ensure all widgets are rendered

        # Delay to let user see "Pronto!" message before showing main window
        def close_splash_and_show_main():
            splash.destroy()
            maximize_window(root)
            root.deiconify()  # Show main window

        root.after(SPLASH_DISPLAY_DURATION_MS, close_splash_and_show_main)

        # Run main loop
        controller.run()

    except Exception:
        log.critical("unhandled.exception", exc_info=True)

        # Try to close splash if it exists
        try:
            if "splash" in locals():
                splash.destroy()
        except Exception:
            pass  # Ignore errors; app is already in fatal error state

        # Show main window if hidden
        try:
            if "root" in locals():
                root.deiconify()
        except Exception:
            pass  # Ignore errors; avoid cascading failures

        messagebox.showerror("Fatal Error", "A fatal error occurred. See analysis.log for details.")
    finally:
        log.info("application.finished", component="main")


if __name__ == "__main__":
    main()
