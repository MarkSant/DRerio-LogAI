"""Video frame extraction utilities.

Phase 5.6a: Extracted cv2 frame-reading and image-saving logic from
coordinators so that coordinators no longer import cv2 directly.

This module provides a thin, testable wrapper around OpenCV's VideoCapture
for reading single frames and cropping/saving them.
"""

from __future__ import annotations

from typing import Any

import cv2
import structlog

log = structlog.get_logger()


class VideoFrameExtractor:
    """Stateless helper for extracting and saving video frames.

    All methods are static or class-level — no instance state is needed.
    Coordinators should receive an instance via DI so they can be mocked
    in tests.
    """

    @staticmethod
    def extract_frame(video_path: str, frame_index: int = 0) -> Any | None:
        """Read a single frame from a video file.

        Args:
            video_path: Path to the video file.
            frame_index: 0-based frame index to extract (default: first frame).

        Returns:
            A numpy ndarray (BGR) or ``None`` if the read failed.
        """
        cap = cv2.VideoCapture(video_path)
        try:
            if not cap.isOpened():
                log.warning(
                    "video_frame_extractor.open_failed",
                    video_path=video_path,
                )
                return None
            if frame_index > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ret, frame = cap.read()
            if not ret or frame is None:
                log.warning(
                    "video_frame_extractor.read_failed",
                    video_path=video_path,
                    frame_index=frame_index,
                )
                return None
            return frame
        finally:
            cap.release()

    @staticmethod
    def extract_and_crop_frame(
        video_path: str,
        crop_box: tuple[int, int, int, int],
        frame_index: int = 0,
    ) -> Any | None:
        """Extract a frame and crop it to *crop_box*.

        The crop box is clamped to the frame dimensions so out-of-bounds
        values are silently adjusted rather than crashing.

        Args:
            video_path: Path to the video file.
            crop_box: ``(x, y, width, height)`` in pixels.
            frame_index: 0-based frame index (default: first frame).

        Returns:
            Cropped numpy ndarray (BGR) or ``None`` on failure.
        """
        frame = VideoFrameExtractor.extract_frame(video_path, frame_index)
        if frame is None:
            return None

        frame_h, frame_w = frame.shape[:2]
        x, y, w, h = map(int, crop_box)

        original_crop = (x, y, w, h)
        x = max(0, min(x, frame_w - 1))
        y = max(0, min(y, frame_h - 1))
        w = min(w, frame_w - x)
        h = min(h, frame_h - y)

        if w <= 0 or h <= 0:
            log.warning(
                "video_frame_extractor.crop_box_invalid",
                original_crop=original_crop,
                frame_size=(frame_w, frame_h),
                reason="crop_box results in empty region after clamping",
            )
            return None

        if (x, y, w, h) != original_crop:
            log.info(
                "video_frame_extractor.crop_box_adjusted",
                original=original_crop,
                adjusted=(x, y, w, h),
                frame_size=(frame_w, frame_h),
            )

        return frame[y : y + h, x : x + w].copy()

    @staticmethod
    def save_frame(frame: Any, path: str) -> bool:
        """Write a frame (numpy ndarray) to disk as an image.

        Args:
            frame: BGR numpy ndarray.
            path: Destination file path (e.g. ``*.png``).

        Returns:
            ``True`` if the write succeeded, ``False`` otherwise.
        """
        try:
            success: bool = cv2.imwrite(path, frame)
            if success:
                log.debug("video_frame_extractor.save_ok", path=path)
            else:
                log.warning("video_frame_extractor.save_failed", path=path)
            return success
        except OSError:
            log.warning(
                "video_frame_extractor.save_error",
                path=path,
                exc_info=True,
            )
            return False
