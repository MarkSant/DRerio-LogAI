import logging
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from zebtrack.settings import Settings


def configure_logging_levels(settings_obj: "Settings | None" = None):
    """Apply per-module log levels from settings.

    Args:
        settings_obj: Settings instance (optional). If None, does nothing.
    """
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
