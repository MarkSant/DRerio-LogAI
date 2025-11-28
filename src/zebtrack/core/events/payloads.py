"""Strict event payloads using Pydantic models."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BaseEventPayload(BaseModel):
    """Base class for all event payloads."""

    model_config = ConfigDict(frozen=True)


class AnalysisStartedEvent(BaseEventPayload):
    """Payload for ANALYSIS_STARTED event."""

    experiment_id: str
    video_path: str
    total_frames: int = Field(..., ge=0)
    settings_snapshot: dict[str, Any] = Field(default_factory=dict)


class FrameProcessedEvent(BaseEventPayload):
    """Payload for FRAME_PROCESSED event."""

    experiment_id: str
    frame_number: int = Field(..., ge=0)
    timestamp: float = Field(..., ge=0.0)
    detections_count: int = Field(..., ge=0)
    processing_time_ms: float = Field(..., ge=0.0)


class VideoLoadedEvent(BaseEventPayload):
    """Payload for VIDEO_LOADED event."""

    video_path: str
    width: int = Field(..., gt=0)
    height: int = Field(..., gt=0)
    fps: float = Field(..., gt=0.0)
    frame_count: int = Field(..., ge=0)
    duration_seconds: float = Field(..., ge=0.0)
