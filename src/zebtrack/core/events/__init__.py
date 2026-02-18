"""Event payload definitions for the EventBus system."""

from zebtrack.core.events.payloads import (
    AnalysisStartedEvent,
    BaseEventPayload,
    FrameProcessedEvent,
    VideoLoadedEvent,
)

__all__ = [
    "AnalysisStartedEvent",
    "BaseEventPayload",
    "FrameProcessedEvent",
    "VideoLoadedEvent",
]
