"""Video utility functions for ZebTrack-AI.

Common video operations extracted to avoid code duplication.
"""

import cv2
import structlog

log = structlog.get_logger()


def get_video_dimensions(path: str) -> tuple[int, int] | None:
    """Safely get video dimensions (width, height).

    Args:
        path: Path to video file

    Returns:
        Tuple of (width, height) in pixels, or None if video cannot be opened

    Example:
        >>> dimensions = get_video_dimensions("/path/to/video.mp4")
        >>> if dimensions:
        >>>     width, height = dimensions
        >>>     print(f"Video is {width}x{height}")
    """
    cap = None
    try:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            log.warning("video.get_dimensions.failed_to_open", path=path)
            return None

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if width <= 0 or height <= 0:
            log.warning("video.get_dimensions.invalid_dimensions", path=path, width=width, height=height)
            return None

        return width, height
    except (cv2.error, OSError, ValueError) as exc:
        log.error("video.get_dimensions.error", path=path, error=str(exc), exc_info=True)
        return None
    finally:
        if cap is not None:
            cap.release()
