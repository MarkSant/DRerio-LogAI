import argparse
import logging
import logging.handlers
import sys
import tkinter as tk
from tkinter import messagebox

import structlog

from zebtrack.core.main_view_model import MainViewModel
from zebtrack.settings import settings
from zebtrack.ui.window_utils import maximize_window
from zebtrack.utils import set_seed


def configure_logging():
    """
    Configures logging for the application.

    This function sets up structlog to process logs and configures handlers
    for both console and file output.
    """
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="%H:%M:%S", utc=False),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        "analysis.log", maxBytes=5 * 1024 * 1024, backupCount=5, mode="a"
    )
    # Console handler for development
    console_handler = logging.StreamHandler(sys.stdout)

    # Basic config for routing standard logs to structlog
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[file_handler, console_handler],
    )


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
