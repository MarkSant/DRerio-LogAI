import argparse
import logging
import logging.handlers
import sys
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

    # Redirect Python warnings to logging system (will be formatted by structlog)
    logging.captureWarnings(True)
    warnings_logger = logging.getLogger("py.warnings")
    warnings_logger.addHandler(console_handler)
    warnings_logger.addHandler(file_handler)


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

    # Import zebtrack modules after logging is configured to use compact format
    from zebtrack.core.main_view_model import MainViewModel
    from zebtrack.settings import settings
    from zebtrack.ui.window_utils import maximize_window
    from zebtrack.utils import set_seed

    # --- Critical Check for Settings ---
    # If settings failed to load, the `settings` object will be None.
    # We must handle this case gracefully before attempting to start the GUI.
    if settings is None:
        log.critical("settings.load.fatal")
        # Hide the blank root window that can sometimes appear
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Fatal Configuration Error",
            "Could not load or validate 'config.yaml'. The application cannot start.\n"
            "\nPlease ensure the file exists and is correctly formatted.",
        )
        sys.exit(1)

    # Set seed for reproducibility before anything else
    if settings.reproducibility and settings.reproducibility.seed:
        set_seed(settings.reproducibility.seed)
        log.info("reproducibility.seed.set", seed=settings.reproducibility.seed)

    log.info("application.starting", component="main")

    try:
        root = tk.Tk()

        # Set application icon
        from zebtrack.ui.icon_utils import set_window_icon

        set_window_icon(root)

        maximize_window(root)

        # Create the EventBus instance
        from zebtrack.ui.event_bus import EventBus

        event_bus = EventBus()

        controller = MainViewModel(root, event_bus=event_bus)
        controller.bind_events()  # Bind events after full initialization
        controller.run()
    except Exception:
        log.critical("unhandled.exception", exc_info=True)
        # Optionally, show a message to the user
        # import tkinter.messagebox as messagebox
        # messagebox.showerror(
        #     "Fatal Error",
        #     "A fatal error occurred. See analysis.log for details."
        # )
    finally:
        log.info("application.finished", component="main")


if __name__ == "__main__":
    main()
