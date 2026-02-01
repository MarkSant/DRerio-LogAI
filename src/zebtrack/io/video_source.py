"""
Este módulo fornece a classe VideoFileSource, um wrapper conveniente em torno
do `cv2.VideoCapture` para lidar com arquivos de vídeo como fontes de quadros.
"""

import os
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import structlog

from zebtrack.io.frame_source import FrameSource

log = structlog.get_logger()


class VideoFileSource(FrameSource):
    """
    Representa um arquivo de vídeo como uma fonte de quadros.
    """

    def __init__(self, video_path: Path | str):
        """
        Inicializa a fonte de vídeo a partir de um caminho de arquivo.
        """
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found at: {video_path}")

        self.video_path = str(video_path)
        self.cap = cv2.VideoCapture(str(video_path))

        if not self.cap.isOpened():
            raise OSError(f"Cannot open video file: {video_path}")

        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.fps == 0:
            log.warning("video.fps.zero", path=video_path)
            self.fps = 30
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

        log.info(
            "video.source.loaded",
            path=video_path,
            width=self.width,
            height=self.height,
            fps=self.fps,
            frame_count=self.frame_count,
        )

    def get_frame(self) -> tuple[bool, np.ndarray | None]:
        """Reads the next frame from the video file."""
        ret, frame = self.cap.read()
        if not ret:
            return False, None
        return ret, frame

    def get_current_frame_number(self) -> float:
        """Returns the index of the next frame to be decoded."""
        return self.cap.get(cv2.CAP_PROP_POS_FRAMES)

    def get_properties(self) -> dict[str, Any]:
        """Returns a dictionary with the video properties."""
        return {
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "frame_count": self.frame_count,
        }

    def release(self) -> None:
        """Releases the video file resource."""
        if self.cap.isOpened():
            self.cap.release()
            log.info("video.source.released", path=self.video_path)


if __name__ == "__main__":
    print("Testing VideoFileSource...")

    test_video_path = "test_video.mp4"
    frame_width, frame_height = 640, 480
    fps = 30

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # type: ignore[attr-defined]
    writer = cv2.VideoWriter(test_video_path, fourcc, fps, (frame_width, frame_height))

    if not writer.isOpened():
        print("Failed to create a dummy video writer.")
    else:
        for i in range(100):
            dummy_frame = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)
            text = f"Frame {i + 1}"
            cv2.putText(
                dummy_frame, text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2
            )
            writer.write(dummy_frame)
        writer.release()
        print(f"Created a dummy video file: {test_video_path}")

        try:
            video_source = VideoFileSource(test_video_path)
            frame_counter = 0
            frame: np.ndarray | None = None
            while True:
                ret, frame = video_source.get_frame()
                if not ret:
                    print("\nEnd of video reached.")
                    break
                frame_counter += 1
                if frame_counter <= 5 or frame_counter >= 95:
                    reported_frame = video_source.get_current_frame_number()
                    print(f"Read frame number: {frame_counter} (reported: {reported_frame})")

            print(f"\nTotal frames read: {frame_counter}")
            video_source.release()
        except (OSError, FileNotFoundError) as e:
            print(f"Error: {e}")
        finally:
            if os.path.exists(test_video_path):
                os.remove(test_video_path)
                print(f"Cleaned up dummy video file: {test_video_path}")

    print("\nVideoFileSource test finished.")
