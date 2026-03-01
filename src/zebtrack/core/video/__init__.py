"""Video processing sub-package — processing pipeline, workers, and video services.

Provides the video processing service, multiprocessing worker, processing mode
definitions, and video classification/selection/validation/metadata services.

Phase 4.10 — Sub-packetize core/ into domain-specific sub-packages.
"""

from zebtrack.core.video.processing_mode import ProcessingMode, ProcessingReport
from zebtrack.core.video.video_processing_service import VideoProcessingService

__all__ = [
    "ProcessingMode",
    "ProcessingReport",
    "VideoProcessingService",
]
