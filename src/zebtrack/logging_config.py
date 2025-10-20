import logging

import structlog

from zebtrack.settings import settings


def configure_logging_levels():
    """Apply per-module log levels from settings."""
    if not hasattr(settings, "logging") or not hasattr(settings.logging, "levels"):
        return

    for module_name, level_str in settings.logging.levels.items():
        level = getattr(logging, level_str.upper(), logging.INFO)
        logger = logging.getLogger(module_name)
        logger.setLevel(level)
        structlog.get_logger().info(
            "logging.level.set",
            module=module_name,
            level=level_str,
        )
