import numpy as np
import structlog
from shapely.geometry import Polygon
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

    def _calculate_iou(self, poly1_points, poly2_points) -> float:
        """Calculates the Intersection over Union (IoU) of two polygons."""
        try:
            poly1 = Polygon(poly1_points)
            poly2 = Polygon(poly2_points)

            if not poly1.is_valid or not poly2.is_valid:
                return 0.0

            intersection_area = poly1.intersection(poly2).area
            union_area = poly1.union(poly2).area

            if union_area == 0:
                return 0.0

            return intersection_area / union_area
        except Exception as e:
            log.warning(
                "aquarium_detector.iou_calculation_failed",
                error=str(e),
                exc_info=True,
            )
            return 0.0

    def detect_aquariums(self, video_path: str, stabilization_frames: int = 10) -> list:
        """
        Analyzes initial frames of a video to find the most stable aquarium polygon
        using a consensus-based approach.

        This method collects polygons from frames where only one object is detected,
        then uses the Intersection over Union (IoU) metric to find the most
        representative (stable) polygon among them.

        Args:
            video_path (str): The path to the video file.
            stabilization_frames (int): The number of initial frames to analyze.

        Returns:
            A list containing the single most stable polygon, or an empty list if
            no stable polygon could be found.
        """
        log.info("aquarium_detector.detect.start", video_path=video_path)
        source = None
        try:
            source = VideoFileSource(video_path)
            good_polygons = []
            for i in range(stabilization_frames):
                ret, frame = source.get_frame()
                if not ret:
                    log.warning("aquarium_detector.detect.frame_read_failed", frame=i)
                    break

                results = self.model.predict(frame, verbose=False)

                if results and results[0].masks and results[0].masks.xy:
                    polygons = results[0].masks.xy
                    # Filter for frames with only one detected polygon
                    if len(polygons) == 1:
                        good_polygons.append(polygons[0].astype(np.int32))
                        log.debug(
                            "aquarium_detector.detect.good_frame_found",
                            frame=i,
                        )

            if not good_polygons:
                log.warning("aquarium_detector.detect.no_good_polygons_found")
                return []

            if len(good_polygons) == 1:
                log.info("aquarium_detector.detect.only_one_good_polygon")
                return [good_polygons[0]]

            # Find the most stable polygon by consensus (average IoU)
            best_polygon = None
            max_avg_iou = -1.0

            for i, poly_a in enumerate(good_polygons):
                total_iou = 0.0
                for j, poly_b in enumerate(good_polygons):
                    if i == j:
                        continue
                    total_iou += self._calculate_iou(poly_a, poly_b)

                avg_iou = total_iou / (len(good_polygons) - 1)
                log.debug(
                    "aquarium_detector.detect.iou_check",
                    polygon_index=i,
                    avg_iou=avg_iou,
                )

                if avg_iou > max_avg_iou:
                    max_avg_iou = avg_iou
                    best_polygon = poly_a

            if best_polygon is not None:
                log.info(
                    "aquarium_detector.detect.finished",
                    best_polygon_iou=max_avg_iou,
                )
                return [best_polygon]
            else:
                log.warning("aquarium_detector.detect.consensus_failed")
                return []

        except Exception as e:
            log.error(
                "aquarium_detector.detect.failed", video_path=video_path, error=str(e)
            )
            return []
        finally:
            if source:
                source.release()
