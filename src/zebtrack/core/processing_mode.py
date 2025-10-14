from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProcessingMode(str, Enum):
    """Enumerates the tracking pipelines available to the application."""

    MULTI_TRACK = "multi_track"
    SINGLE_SUBJECT = "single_subject"

    @property
    def display_name(self) -> str:
        if self is ProcessingMode.SINGLE_SUBJECT:
            return "Individual"
        return "Multi-indivíduos"


@dataclass(frozen=True)
class ProcessingReport:
    """Small payload shared between controller threads and the GUI."""

    mode: ProcessingMode
    source: str | None = None

    def is_single_subject(self) -> bool:
        return self.mode is ProcessingMode.SINGLE_SUBJECT
