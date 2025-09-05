import numpy as np
import structlog
from ultralytics import YOLO

from zebtrack.io.video_source import VideoFileSource

log = structlog.get_logger()


class AquariumDetector:
    """
    Detects aquariums in a video using a YOLO segmentation model.
    """

    def __init__(self, model_path: str):
        """
        Initializes the AquariumDetector.

        Args:
            model_path (str): Path to the YOLO segmentation model (.pt file).
        """
        try:
            self.model = YOLO(model_path)
            log.info("aquarium_detector.init.success", model_path=model_path)
        except Exception as e:
            log.error(
                "aquarium_detector.init.failed", model_path=model_path, error=str(e)
            )
            raise

    def detect_aquariums(self, video_path: str, stabilization_frames: int = 30) -> list:
        """
        Analyzes initial frames of a video to find stable aquarium polygons.

        This method processes a set number of frames from the start of the video,
        runs segmentation, and returns the polygons detected in the last valid frame.
        A more complex stabilization logic could be added here in the future.

        Args:
            video_path (str): The path to the video file.
            stabilization_frames (int): The number of initial frames to analyze.

        Returns:
            A list of polygons (as numpy arrays) for the detected aquariums.
        """
        log.info("aquarium_detector.detect.start", video_path=video_path)
        source = None
        try:
            source = VideoFileSource(video_path)
            if not source.is_opened():
                log.error(
                    "aquarium_detector.detect.video_open_failed", video_path=video_path
                )
                return []

            detected_polygons = []
            for i in range(stabilization_frames):
                ret, frame = source.get_frame()
                if not ret:
                    log.warning("aquarium_detector.detect.frame_read_failed", frame=i)
                    break

                # Perform segmentation
                results = self.model.predict(frame, verbose=False)

                # Extract polygons if masks are found
                if results and results[0].masks and results[0].masks.xy:
                    # .xy gives a list of (N, 2) numpy arrays, one for each detected object
                    polygons = results[0].masks.xy
                    detected_polygons = [p.astype(np.int32) for p in polygons]
                    log.info(
                        "aquarium_detector.detect.found_polygons",
                        frame=i,
                        count=len(polygons),
                    )

            if detected_polygons:
                log.info(
                    "aquarium_detector.detect.finished", count=len(detected_polygons)
                )
                return detected_polygons
            else:
                log.warning("aquarium_detector.detect.no_polygons_found")
                return []

        except Exception as e:
            log.error(
                "aquarium_detector.detect.failed", video_path=video_path, error=str(e)
            )
            return []
        finally:
            if source:
                source.release()
