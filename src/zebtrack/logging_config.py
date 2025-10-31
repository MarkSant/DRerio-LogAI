import logging
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from zebtrack.settings import Settings


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
        settings_obj: Settings instance (optional). If None, function returns immediately.

    Example:
        >>> # In __main__.py
        >>> configure_logging_levels()  # No-op, import only
        >>> settings_obj = load_settings()
        >>> configure_logging_levels(settings_obj)  # Apply levels from config.yaml
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
