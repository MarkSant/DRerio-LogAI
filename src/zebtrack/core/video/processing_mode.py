"""Processing mode definitions for tracking pipelines.

Defines enumeration for multi-subject and single-subject tracking modes
and related data structures for processing reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProcessingMode(str, Enum):
    """Enumerates the tracking pipelines available to the application."""

    MULTI_TRACK = "multi_track"
    SINGLE_SUBJECT = "single_subject"

    @property
    def display_name(self) -> str:
        """Return the human-readable display name for this processing mode.

        Returns:
            Localized string representation of the processing mode.
        """
        if self is ProcessingMode.SINGLE_SUBJECT:
            return "Individual"
        return "Multi-indivíduos"


@dataclass(frozen=True)
class ProcessingReport:
    """Small payload shared between controller threads and the GUI."""

    mode: ProcessingMode
    source: str | None = None

    def is_single_subject(self) -> bool:
        """Check if this report represents single-subject processing mode.

        Returns:
            True if mode is SINGLE_SUBJECT, False otherwise.
        """
        return self.mode is ProcessingMode.SINGLE_SUBJECT
