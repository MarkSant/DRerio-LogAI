import logging
import logging.handlers
import os
import sys
from pathlib import Path
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


def resolve_log_path(log_file: str) -> str:
    """Resolve the effective path for a log file.

    - If `log_file` already includes a directory, it is used as-is.
    - Otherwise, logs are written to a fixed directory under the project root.
    - The directory can be overridden via the `ZEBTRACK_LOG_DIR` env var.
    """
    def _find_project_root() -> Path:
        # Prefer finding a repository/project root (pyproject.toml) relative to this file.
        here = Path(__file__).resolve()
        for parent in [here.parent, *here.parents]:
            if (parent / "pyproject.toml").exists():
                return parent
        # Fallback to current working directory.
        return Path.cwd()

    log_path = Path(log_file)
    if log_path.parent != Path("."):
        return str(log_path)

    override_dir = os.environ.get("ZEBTRACK_LOG_DIR")
    if override_dir:
        base_dir = Path(override_dir)
    else:
        base_dir = _find_project_root() / "logs"

    return str(base_dir / log_path.name)


def configure_logging(log_file: str = "analysis.log"):
    """
    Configures logging for the application.

    This function sets up structlog to process logs with a consistent format
    for both application logs and standard library/third-party logs.
    Uses CompactConsoleRenderer for minimal spacing in output.

    Args:
        log_file: Path to the log file. Defaults to "analysis.log".
                  Worker processes should use a different file to avoid locking issues.
                  Default logs are overwritten on each application start.
    """
    # Requirement: keep only the current execution in the default log files.
    # - Always truncate analysis.log on start
    # - Also truncate analysis_worker.log on start (even if the worker never runs)
    effective_log_file = resolve_log_path(log_file)
    log_name = Path(log_file).name
    overwrite_each_run_files = {"analysis.log", "analysis_worker.log"}

    def _truncate_file(path: str) -> None:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        try:
            with open(path, "w", encoding="utf-8"):
                pass
        except Exception:
            # Best-effort: do not crash the app if the filesystem is read-only/locked.
            pass

    def _truncate_if_exists_in_cwd(filename: str) -> None:
        cwd_path = str(Path.cwd() / filename)
        if os.path.exists(cwd_path):
            _truncate_file(cwd_path)

    if log_name == "analysis.log":
        _truncate_file(effective_log_file)
        _truncate_file(resolve_log_path("analysis_worker.log"))
        _truncate_if_exists_in_cwd("analysis.log")
        _truncate_if_exists_in_cwd("analysis_worker.log")
        # Compatibility: some user environments might have used a different filename.
        if os.path.exists("analysis]-worker.log"):
            _truncate_file("analysis]-worker.log")
        compat_effective = resolve_log_path("analysis]-worker.log")
        if os.path.exists(compat_effective):
            _truncate_file(compat_effective)
    elif log_name in overwrite_each_run_files:
        _truncate_file(effective_log_file)
        _truncate_if_exists_in_cwd(log_name)
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

    # File handler
    # For default logs, avoid rotation and overwrite per execution.
    if log_name in overwrite_each_run_files:
        file_handler = logging.FileHandler(effective_log_file, mode="w", encoding="utf-8")
    else:
        # For any non-default log files, keep rotation as a safeguard.
        file_handler = logging.handlers.RotatingFileHandler(
            effective_log_file, maxBytes=10 * 1024 * 1024, backupCount=1, mode="a"
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

    # Clear existing handlers to avoid duplication if called multiple times.
    # Close them first to reduce Windows file locking issues.
    if root_logger.hasHandlers():
        for handler in list(root_logger.handlers):
            try:
                handler.close()
            except Exception:
                pass
        root_logger.handlers.clear()

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Log session start marker to track execution count
    logger = structlog.get_logger()
    logger.info("logging.session.start")
    logger.info(
        "logging.configured",
        log_file=effective_log_file,
        cwd=str(Path.cwd()),
    )


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
