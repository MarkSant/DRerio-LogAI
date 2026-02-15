"""
Frame source factory for unified video file and camera input.

This module provides a factory for creating FrameSource instances
from various input types (file paths, camera indices, or live streams).
"""

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from zebtrack.io.frame_source import FrameSource
from zebtrack.io.live_stream_source import LiveStreamSource
from zebtrack.io.video_source import VideoFileSource

if TYPE_CHECKING:
    from zebtrack.settings import Settings

log = structlog.get_logger()


class FrameSourceFactory:
    """
    Factory for creating FrameSource instances.

    Supports:
    - Video files (via VideoFileSource)
    - Live camera streams (via LiveStreamSource)
    - Camera with duration limits (via LiveStreamSource)
    """

    @staticmethod
    def create_from_path(
        video_path: Path | str, settings_obj: "Settings | None" = None
    ) -> FrameSource:
        """
        Create a VideoFileSource from a file path.

        Args:
            video_path: Path to video file
            settings_obj: Settings instance (optional for VideoFileSource)

        Returns:
            VideoFileSource instance

        Raises:
            FileNotFoundError: If video file doesn't exist
        """
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        log.info("frame_source_factory.create_video", path=str(video_path))
        return VideoFileSource(video_path)

    @staticmethod
    def create_from_camera(
        camera_index: int,
        max_duration_s: float | None = None,
        settings_obj: "Settings | None" = None,
    ) -> FrameSource:
        """
        Create a camera-based source with optional duration limit.

        Args:
            camera_index: Camera device index
            max_duration_s: Maximum capture duration in seconds (None for unlimited)
            settings_obj: Settings instance (required for Camera)

        Returns:
            LiveStreamSource if max_duration_s provided, otherwise Camera

        Raises:
            RuntimeError: If settings_obj not provided
            OSError: If camera cannot be opened
        """
        if settings_obj is None:
            raise RuntimeError(
                "FrameSourceFactory: settings_obj required for camera sources. "
                "Use: create_from_camera(camera_index, settings_obj=load_settings())"
            )

        if max_duration_s is not None and max_duration_s > 0:
            log.info(
                "frame_source_factory.create_live_stream",
                camera_index=camera_index,
                max_duration_s=max_duration_s,
            )
            return LiveStreamSource(
                camera_index=camera_index,
                max_duration_s=max_duration_s,
                settings_obj=settings_obj,
            )
        else:
            # Unlimited duration - use Camera directly
            from zebtrack.io.camera import Camera

            log.info(
                "frame_source_factory.create_camera",
                camera_index=camera_index,
                duration="unlimited",
            )

            # ✅ Create modified settings with correct camera index
            temp_settings = settings_obj.model_copy(deep=True)
            temp_settings.camera.index = camera_index
            return Camera(settings_obj=temp_settings)

    @staticmethod
    def create(
        source: str | Path | int | dict,
        settings_obj: "Settings | None" = None,
    ) -> FrameSource:
        """
        Create a FrameSource from various input types.

        Args:
            source: One of:
                - str/Path: Video file path
                - int: Camera index
                - dict: {"type": "camera", "index": int, "max_duration_s": float}
                       or {"type": "file", "path": str}
            settings_obj: Settings instance

        Returns:
            Appropriate FrameSource instance

        Raises:
            ValueError: If source type is invalid
            RuntimeError: If settings required but not provided
            FileNotFoundError: If video file doesn't exist
            OSError: If camera cannot be opened
        """
        # Handle dictionary configuration
        if isinstance(source, dict):
            source_type = source.get("type", "").lower()

            if source_type == "camera":
                camera_index = source.get("index", 0)
                max_duration_s = source.get("max_duration_s")
                return FrameSourceFactory.create_from_camera(
                    camera_index=camera_index,
                    max_duration_s=max_duration_s,
                    settings_obj=settings_obj,
                )

            elif source_type == "file":
                video_path = source.get("path")
                if not video_path:
                    raise ValueError("File source requires 'path' key")
                return FrameSourceFactory.create_from_path(
                    video_path=video_path, settings_obj=settings_obj
                )

            else:
                raise ValueError(
                    f"Invalid source type in dict: '{source_type}'. Must be 'camera' or 'file'"
                )

        # Handle camera index (integer)
        elif isinstance(source, int):
            return FrameSourceFactory.create_from_camera(
                camera_index=source, settings_obj=settings_obj
            )

        # Handle file path (string or Path)
        elif isinstance(source, str | Path):
            return FrameSourceFactory.create_from_path(video_path=source, settings_obj=settings_obj)

        else:
            raise ValueError(
                f"Invalid source type: {type(source).__name__}. Expected str, Path, int, or dict"
            )


if __name__ == "__main__":
    """Test FrameSourceFactory."""
    import os

    from zebtrack.settings import load_settings

    print("Testing FrameSourceFactory...")

    # Test 1: Create from camera index
    print("\n1. Creating camera source (5 second limit)...")
    try:
        settings = load_settings()
        camera_source = FrameSourceFactory.create(
            source=0,
            settings_obj=settings,  # Camera index 0
        )
        print(f"   Created: {type(camera_source).__name__}")
        print(f"   Properties: {camera_source.get_properties()}")
        camera_source.release()
    except Exception as e:
        print(f"   Error: {e}")

    # Test 2: Create from dict config (camera with duration)
    print("\n2. Creating live stream from dict config...")
    try:
        settings = load_settings()
        live_source = FrameSourceFactory.create(
            source={"type": "camera", "index": 0, "max_duration_s": 10.0},
            settings_obj=settings,
        )
        print(f"   Created: {type(live_source).__name__}")
        print(f"   Properties: {live_source.get_properties()}")
        live_source.release()
    except Exception as e:
        print(f"   Error: {e}")

    # Test 3: Create from video file (if test video exists)
    print("\n3. Creating video file source...")
    test_video = "test_video.mp4"
    if os.path.exists(test_video):
        try:
            video_source = FrameSourceFactory.create(source=test_video)
            print(f"   Created: {type(video_source).__name__}")
            print(f"   Properties: {video_source.get_properties()}")
            video_source.release()
        except Exception as e:
            print(f"   Error: {e}")
    else:
        print(f"   Skipped (test video not found: {test_video})")

    # Test 4: Error handling
    print("\n4. Testing error handling...")
    try:
        FrameSourceFactory.create(source={"type": "invalid"})
    except ValueError as e:
        print(f"   ✓ Caught expected ValueError: {e}")

    print("\nFrameSourceFactory test finished.")
