"""Decorators for UI layer components.

This module provides decorators for marking and documenting UI component interfaces.
"""

from collections.abc import Callable
from functools import wraps
from typing import TypeVar

F = TypeVar("F", bound=Callable)


def public_api[F: Callable](func: F) -> F:
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
    func.__public_api__ = True  # type: ignore[attr-defined]

    # Preserve original function metadata
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    # Copy the marker to wrapper
    wrapper.__public_api__ = True  # type: ignore[attr-defined]

    return wrapper  # type: ignore[return-value]


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

    def decorator(func: F) -> F:
        func.__deprecated__ = True  # type: ignore[attr-defined]
        func.__deprecation_info__ = {  # type: ignore[attr-defined]
            "reason": reason,
            "version": version,
            "alternative": alternative,
        }

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Could add logging warning here in future
            return func(*args, **kwargs)

        wrapper.__deprecated__ = True  # type: ignore[attr-defined]
        wrapper.__deprecation_info__ = func.__deprecation_info__  # type: ignore[attr-defined]

        return wrapper  # type: ignore[return-value]

    return decorator
