"""Decorators for UI layer components.

This module provides decorators for marking and documenting UI component interfaces.
"""

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

# Attribute name constants — stored in variables so ruff B010 won't
# convert setattr() calls back to direct attribute assignment.
_PUBLIC_API_ATTR = "__public_api__"
_DEPRECATED_ATTR = "__deprecated__"
_DEPRECATION_INFO_ATTR = "__deprecation_info__"


def public_api(func: Callable[P, R]) -> Callable[P, R]:
    """Mark a method as part of the public GUI API.

    Methods decorated with @public_api are considered stable interfaces that:
    - Are called from outside the GUI class (components, orchestrators, services)
    - Should not be removed or changed without careful impact analysis
    - Form the coordination layer between GUI and its components

    This decorator:
    - Adds metadata for documentation generation
    - Helps identify breaking changes during refactoring
    - Documents architectural dependencies

    Usage:
        @public_api
        def refresh_project_views(self, reason: str | None = None) -> None:
            '''Refresh project overview and reports (PUBLIC API).'''
            ...

    See Also:
        - docs/API_STABILITY.md - Public API stability guarantees
        - RELATORIO_REMOCAO_WRAPPERS_FINAL.md - List of all public API methods
    """
    # Mark the function as public API
    func.__public_api__ = True

    # Preserve original function metadata
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return func(*args, **kwargs)

    # Copy the marker to wrapper
    wrapper.__public_api__ = True

    return wrapper


def deprecated(reason: str, version: str, alternative: str | None = None):
    """Mark a method as deprecated with migration guidance.

    Args:
        reason: Why this method is deprecated
        version: Version when deprecation was introduced (e.g., "v3.0")
        alternative: Suggested replacement method or pattern

    Usage:
        @deprecated(
            reason="Replaced by component-based architecture",
            version="v3.0",
            alternative="Use self.widget_factory.create_welcome_frame() directly"
        )
        def _create_welcome_frame(self):
            '''DEPRECATED: Will be removed in v4.0.'''
            return self.widget_factory.create_welcome_frame()
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        setattr(func, _DEPRECATED_ATTR, True)
        setattr(
            func,
            _DEPRECATION_INFO_ATTR,
            {
                "reason": reason,
                "version": version,
                "alternative": alternative,
            },
        )

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # Could add logging warning here in future
            return func(*args, **kwargs)

        setattr(wrapper, _DEPRECATED_ATTR, True)
        setattr(wrapper, _DEPRECATION_INFO_ATTR, getattr(func, _DEPRECATION_INFO_ATTR))

        return wrapper

    return decorator
