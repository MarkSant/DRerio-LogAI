import argparse
import logging
import logging.handlers
import sys
import threading
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
        # Create Tkinter root
        root = tk.Tk()

        # Set application icon
        from zebtrack.ui.icon_utils import set_window_icon

        set_window_icon(root)
        maximize_window(root)

        # ===== DEPENDENCY INJECTION: Create all services =====

        # Core infrastructure
        from zebtrack.core.state_manager import StateManager
        from zebtrack.core.ui_coordinator import UICoordinator
        from zebtrack.ui.event_bus import EventBus

        event_bus = EventBus()
        state_manager = StateManager(enable_history=True, max_history_size=100)
        ui_coordinator = UICoordinator(root=root, event_bus=event_bus)

        # Model and weight management
        from zebtrack.core.model_service import ModelService
        from zebtrack.core.weight_manager import WeightManager

        weight_manager = WeightManager(settings_obj=settings_obj)
        model_service = ModelService(weight_manager)

        # Project management
        from zebtrack.core.project_manager import ProjectManager
        from zebtrack.core.project_workflow_service import ProjectWorkflowService

        project_manager = ProjectManager(state_manager=state_manager, settings_obj=settings_obj)
        project_workflow_service = ProjectWorkflowService(
            project_manager=project_manager,
            model_service=model_service,
            state_manager=state_manager,
            ui_coordinator=ui_coordinator,
            settings_obj=settings_obj,
        )

        # Detector service
        from zebtrack.core.detector_service import DetectorService

        detector_service = DetectorService(
            state_manager=state_manager,
            project_manager=project_manager,
            weight_manager=weight_manager,
            model_service=model_service,
            settings_obj=settings_obj,
        )

        # Video processing service
        from zebtrack.core.video_processing_service import VideoProcessingService
        from zebtrack.io.recorder import Recorder

        # Initialize recorder with settings
        recorder = Recorder(settings_obj=settings_obj)
        cancel_event = threading.Event()

        # VideoProcessingService is created before detector exists
        # The detector is lazy-initialized later via detector_service.initialize_detector()
        # when a project is created/loaded. This is by design to support different
        # detection methods (seg/det) and backends (YOLO/OpenVINO) per project.
        video_processing_service = VideoProcessingService(
            detector=None,  # Lazy-initialized by detector_service.initialize_detector()
            recorder=recorder,
            project_manager=project_manager,
            state_manager=state_manager,
            ui_coordinator=ui_coordinator,
            root=root,
            view=None,  # Set after ApplicationGUI is created
            cancel_event=cancel_event,
        )

        # Analysis service
        from zebtrack.analysis.analysis_service import AnalysisService

        analysis_service = AnalysisService(settings_obj=settings_obj)

        # Create MainViewModel with all injected dependencies
        from zebtrack.core.main_view_model import MainViewModel

        controller = MainViewModel(
            root=root,
            event_bus=event_bus,
            state_manager=state_manager,
            ui_coordinator=ui_coordinator,
            settings_obj=settings_obj,
            project_manager=project_manager,
            project_workflow_service=project_workflow_service,
            weight_manager=weight_manager,
            model_service=model_service,
            detector_service=detector_service,
            video_processing_service=video_processing_service,
            analysis_service=analysis_service,
            recording_service=None,  # Will be created by MainViewModel for now
        )

        # Set view reference in video_processing_service after view is created
        video_processing_service.view = controller.view

        # Bind events and run
        controller.bind_events()
        controller.run()

    except Exception:
        log.critical("unhandled.exception", exc_info=True)
        messagebox.showerror("Fatal Error", "A fatal error occurred. See analysis.log for details.")
    finally:
        log.info("application.finished", component="main")


if __name__ == "__main__":
    main()
