import logging
import logging.handlers
import os
import sys
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from zebtrack.settings import Settings


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


def configure_logging(log_file: str = "analysis.log"):
    """
    Configures logging for the application.

    This function sets up structlog to process logs with a consistent format
    for both application logs and standard library/third-party logs.
    Uses CompactConsoleRenderer for minimal spacing in output.

    Args:
        log_file: Path to the log file. Defaults to "analysis.log".
                  Worker processes should use a different file to avoid locking issues.
                  Logs are cleared after every 2 executions to prevent infinite growth.
    """
    # Logic to limit logs to 2 executions:
    # If the file already contains 2 start markers, clear it (mode='w').
    # Otherwise, append (mode='a').
    mode = "a"
    session_marker = '"event": "logging.session.start"'

    if os.path.exists(log_file):
        try:
            with open(log_file, encoding="utf-8", errors="ignore") as f:
                content = f.read()
                if content.count(session_marker) >= 2:
                    mode = "w"
        except Exception:
            pass

    # Synchronize worker log: if main log is reset, reset worker log too
    if log_file == "analysis.log" and mode == "w":
        worker_log = "analysis_worker.log"
        if os.path.exists(worker_log):
            try:
                with open(worker_log, "w") as f:
                    pass
            except Exception:
                pass
    # Shared processors for both structlog and stdlib logging
    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.processors.StackInfoRenderer(),
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

    # File handler with rotation (limited to 2 sessions via mode, plus 1 backup for safety)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=1, mode=mode
    )
    file_handler.setFormatter(file_formatter)

    # Console handler for development
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)

    # Configure root logger to route ALL logs (including stdlib/libs) through structlog
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Configure handlers levels
    file_handler.setLevel(logging.DEBUG)  # All levels in file
    console_handler.setLevel(logging.INFO)  # INFO and above in console (hides DEBUG)

    # Clear existing handlers to avoid duplication if called multiple times
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Log session start marker to track execution count
    structlog.get_logger().info("logging.session.start")


def configure_logging_levels(settings_obj: "Settings | None" = None):
    """Apply per-module log levels from settings.

    **Double Call Pattern**: This function is intentionally called twice during
    application startup in __main__.py:

    1. **First call (before settings load)**: `configure_logging_levels(None)`
       - Purpose: Import must happen before load_settings() to avoid circular imports
       - Behavior: No-op when settings_obj is None, returns immediately
       - Location: __main__.py line 122

    2. **Second call (after settings load)**: `configure_logging_levels(settings_obj)`
       - Purpose: Apply per-module log levels from config.yaml
       - Behavior: Sets logging levels for configured modules
       - Location: __main__.py line 160

    This pattern ensures:
    - Import order is correct (no circular dependencies)
    - Logging levels from config.yaml are applied once settings are loaded
    - CLI overrides (--log-level) can be applied after settings

    Args:
        settings_obj: Settings instance (optional). If None, warnings are still captured
                     but no per-module log levels are applied.

    Example:
        >>> # In __main__.py
        >>> configure_logging_levels()  # Capture warnings, no module levels
        >>> settings_obj = load_settings()
        >>> configure_logging_levels(settings_obj)  # Apply levels from config.yaml
    """
    # Configure warning capture - this should always happen to redirect Python warnings
    # to the logging system, regardless of whether settings are available
    logging.captureWarnings(True)

    if settings_obj is None:
        return

    if not hasattr(settings_obj, "logging") or not hasattr(settings_obj.logging, "levels"):
        return

    for module_name, level_str in settings_obj.logging.levels.items():
        level = getattr(logging, level_str.upper(), logging.INFO)
        logger = logging.getLogger(module_name)
        logger.setLevel(level)
        structlog.get_logger().info(
            "logging.level.set",
            module=module_name,
            level=level_str,
        )
