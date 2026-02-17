"""Shared types for the processing coordinator family.

Phase 4: Extracted from the monolithic ProcessingCoordinator to be shared
across the 5 decomposed coordinators:
    - VideoProcessingCoordinator
    - MultiAquariumCoordinator
    - SequentialProcessingCoordinator
    - ReportGenerationCoordinator
    - ProgressTrackingCoordinator
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationResult:
    """Result of a processing validation check.

    Used by VideoProcessingCoordinator.validate_can_start_processing()
    and consumed by callers to decide whether to proceed.
    """

    is_valid: bool
    error_code: str | None = None
    error_message: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls) -> ValidationResult:
        return cls(is_valid=True)

    @classmethod
    def failure(
        cls,
        error_code: str,
        error_message: str,
        context: dict[str, Any] | None = None,
    ) -> ValidationResult:
        return cls(
            is_valid=False,
            error_code=error_code,
            error_message=error_message,
            context=context or {},
        )


class ProcessingCoordinatorError(Exception):
    """Base exception for processing coordinator errors.

    Phase 4: Retained for backward compatibility. All 5 sub-coordinators
    raise this same exception type so existing callers are unaffected.
    """

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.context = context or {}
