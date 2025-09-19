import cv2
import numpy as np
import structlog
from shapely.geometry import Polygon

try:
    from ultralytics import YOLO

    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False

from zebtrack.io.video_source import VideoFileSource

log = structlog.get_logger()


class AquariumDetector:
    """
    Detects aquariums in a video using a YOLO segmentation model.
    """

    def __init__(self, model_path: str, mode: str = "seg"):
        """
        Initializes the AquariumDetector.

        Args:
            model_path (str): Path to the YOLO model (.pt file).
            mode (str): Detection mode - "seg" for segmentation, "det" for detection.
        """
        if not ULTRALYTICS_AVAILABLE:
            raise ImportError(
                "Ultralytics is not available. Please install ultralytics package."
            )

        self.mode = mode
        if mode not in ["seg", "det"]:
            raise ValueError(f"Invalid mode '{mode}'. Must be 'seg' or 'det'.")

        try:
            self.model = YOLO(model_path)
            log.info("aquarium_detector.init.success", model_path=model_path, mode=mode)
        except Exception as e:
            log.error(
                "aquarium_detector.init.failed", model_path=model_path, mode=mode, error=str(e)
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

    def _extract_polygon_from_detection(self, frame, results) -> np.ndarray | None:
        """
        Extracts a polygon from detection results (bounding boxes).
        
        Args:
            frame: The frame from which detection was performed
            results: YOLO detection results
            
        Returns:
            Polygon as numpy array of shape (N, 2) or None if no valid detection
        """
        if not results or not results[0].boxes:
            return None
            
        boxes = results[0].boxes
        confidences = [float(box.conf) for box in boxes]
        
        if not confidences:
            return None
            
        # Find the box with highest confidence
        best_idx = confidences.index(max(confidences))
        best_box = boxes[best_idx]
        best_conf = confidences[best_idx]
        
        # Convert box to polygon (rectangle)
        x1, y1, x2, y2 = best_box.xyxy[0].cpu().numpy()
        
        # Create rectangular polygon from bounding box
        polygon = np.array([
            [int(x1), int(y1)],  # top-left
            [int(x2), int(y1)],  # top-right  
            [int(x2), int(y2)],  # bottom-right
            [int(x1), int(y2)],  # bottom-left
        ], dtype=np.int32)
        
        # Validate size - should be reasonable portion of frame
        frame_area = frame.shape[0] * frame.shape[1]
        box_area = (x2 - x1) * (y2 - y1)
        area_ratio = box_area / frame_area
        
        if area_ratio < 0.1:  # Too small
            log.warning("aquarium_detector.detection_too_small", 
                       confidence=best_conf, area_ratio=area_ratio)
            return None
            
        if area_ratio > 0.95:  # Almost entire frame, likely false positive
            log.warning("aquarium_detector.detection_too_large", 
                       confidence=best_conf, area_ratio=area_ratio)
            return None
            
        log.info("aquarium_detector.detection_polygon_extracted", 
                confidence=best_conf, area_ratio=area_ratio,
                bbox=[int(x1), int(y1), int(x2), int(y2)])
        
        return polygon

    def _process_segmentation_results(self, frame, results, frame_index: int) -> np.ndarray | None:
        """
        Processes segmentation results to extract a valid aquarium polygon.
        
        Args:
            frame: Video frame
            results: YOLO results
            frame_index: Frame number for logging
            
        Returns:
            Valid polygon or None
        """
        if results and results[0].masks and results[0].masks.xy:
            polygons = results[0].masks.xy

            # Collect confidence information for logging
            confidences = []
            if results[0].boxes:
                confidences = [float(box.conf) for box in results[0].boxes]

            # Log confidence information
            if confidences:
                avg_conf = sum(confidences) / len(confidences)
                max_conf = max(confidences)
                log.info(
                    "aquarium_detector.confidence_check",
                    frame=frame_index,
                    num_detections=len(polygons),
                    confidences=[f"{c:.3f}" for c in confidences],
                    avg_conf=f"{avg_conf:.3f}",
                    max_conf=f"{max_conf:.3f}",
                )

            # Log all masks found
            for j, poly in enumerate(polygons):
                x_min, y_min = poly[:, 0].min(), poly[:, 1].min()
                x_max, y_max = poly[:, 0].max(), poly[:, 1].max()
                area = (x_max - x_min) * (y_max - y_min)

                # Check if there's corresponding box to know the class
                class_id = -1
                if results[0].boxes and j < len(results[0].boxes):
                    class_id = int(results[0].boxes[j].cls)

                log.info(
                    "aquarium_detector.mask_found",
                    frame=frame_index,
                    mask_index=j,
                    class_id=class_id,
                    num_points=len(poly),
                    area=int(area),
                    bbox=[int(x_min), int(y_min), int(x_max), int(y_max)],
                )

            # Accept frames with exactly one large mask
            if len(polygons) == 1:
                polygon = polygons[0].astype(np.int32)

                # Validate that it's large enough (more than 30% of frame)
                frame_area = frame.shape[0] * frame.shape[1]
                x_min, y_min = polygon[:, 0].min(), polygon[:, 1].min()
                x_max, y_max = polygon[:, 0].max(), polygon[:, 1].max()
                poly_area = (x_max - x_min) * (y_max - y_min)

                area_valid = poly_area > frame_area * 0.3

                # Additional confidence validation (if there are boxes)
                # But doesn't block if there aren't - maintains robustness
                conf_valid = True
                conf_info = "sem_box"
                if confidences:
                    max_conf = max(confidences)
                    conf_valid = max_conf > 0.05  # Low but present threshold
                    conf_info = f"{max_conf:.3f}"

                if area_valid and conf_valid:
                    log.info(
                        "aquarium_detector.good_polygon",
                        frame=frame_index,
                        area_ratio=poly_area / frame_area,
                        confidence=conf_info,
                    )
                    return polygon
                elif not area_valid:
                    log.warning(
                        "aquarium_detector.polygon_too_small",
                        frame=frame_index,
                        area_ratio=poly_area / frame_area,
                        confidence=conf_info,
                    )
                elif not conf_valid:
                    log.warning(
                        "aquarium_detector.confidence_too_low",
                        frame=frame_index,
                        area_ratio=poly_area / frame_area,
                        confidence=conf_info,
                        threshold=0.05,
                    )
            else:
                log.warning(
                    "aquarium_detector.wrong_mask_count",
                    frame=frame_index,
                    num_masks=len(polygons),
                    expected=1,
                )
        else:
            # If didn't find aquarium, try alternative strategy
            log.info("aquarium_detector.trying_fallback", frame=frame_index)
            results_all = self.model.predict(frame, verbose=False, conf=0.01)

            if results_all and results_all[0].masks and results_all[0].masks.xy:
                all_polygons = results_all[0].masks.xy
                log.info(
                    "aquarium_detector.fallback_masks_found",
                    frame=frame_index,
                    num_masks=len(all_polygons),
                )

                # Look for the largest mask (likely aquarium)
                if all_polygons:
                    largest_area = 0
                    largest_polygon = None

                    for j, poly in enumerate(all_polygons):
                        x_min, y_min = poly[:, 0].min(), poly[:, 1].min()
                        x_max, y_max = poly[:, 0].max(), poly[:, 1].max()
                        area = (x_max - x_min) * (y_max - y_min)

                        if area > largest_area:
                            largest_area = area
                            largest_polygon = poly

                        log.info(
                            "aquarium_detector.fallback_mask",
                            frame=frame_index,
                            mask_index=j,
                            area=int(area),
                        )

                    # If the largest mask is large enough, accept it
                    if largest_polygon is not None:
                        frame_area = frame.shape[0] * frame.shape[1]
                        area_ratio = largest_area / frame_area

                        if area_ratio > 0.1:  # At least 10% of frame
                            log.info(
                                "aquarium_detector.fallback_polygon_accepted",
                                frame=frame_index,
                                area_ratio=area_ratio,
                            )
                            return largest_polygon.astype(np.int32)
                        else:
                            log.warning(
                                "aquarium_detector.fallback_polygon_too_small",
                                frame=frame_index,
                                area_ratio=area_ratio,
                            )
        return None

    def _find_consensus_polygon(self, good_polygons: list, source) -> list:
        """
        Finds the most stable polygon using consensus approach.
        
        Args:
            good_polygons: List of candidate polygons
            source: Video source for fallback default polygon
            
        Returns:
            List containing the best polygon, or empty list
        """
        if not good_polygons:
            log.warning("aquarium_detector.detect.no_good_polygons_found")
            log.info("aquarium_detector.generating_default_polygon")

            # As last resort, create a default polygon based on frame size
            # Assumes aquarium in center with 80% of frame area
            try:
                cap_temp = source._cap if hasattr(source, "_cap") else None
                if cap_temp:
                    w = int(cap_temp.get(cv2.CAP_PROP_FRAME_WIDTH))
                    h = int(cap_temp.get(cv2.CAP_PROP_FRAME_HEIGHT))

                    margin_x = int(w * 0.1)  # 10% margin
                    margin_y = int(h * 0.1)

                    default_polygon = np.array(
                        [
                            [margin_x, margin_y],
                            [w - margin_x, margin_y],
                            [w - margin_x, h - margin_y],
                            [margin_x, h - margin_y],
                        ],
                        dtype=np.int32,
                    )

                    log.info(
                        "aquarium_detector.default_polygon_created",
                        bbox=[margin_x, margin_y, w - margin_x, h - margin_y],
                    )
                    return [default_polygon]
            except Exception as e:
                log.error("aquarium_detector.default_polygon_failed", error=str(e))

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

    def detect_aquariums(self, video_path: str, stabilization_frames: int = 10) -> list:
        """
        Analyzes initial frames of a video to find the most stable aquarium polygon.
        
        Supports both segmentation and detection modes:
        - "seg": Uses segmentation masks (original behavior)
        - "det": Uses bounding box detections converted to rectangular polygons

        Args:
            video_path (str): The path to the video file.
            stabilization_frames (int): The number of initial frames to analyze.

        Returns:
            A list containing the single most stable polygon, or an empty list if
            no stable polygon could be found.
        """
        log.info("aquarium_detector.detect.start", video_path=video_path, mode=self.mode)
        source = None
        try:
            source = VideoFileSource(video_path)
            good_polygons = []
            
            for i in range(stabilization_frames):
                ret, frame = source.get_frame()
                if not ret:
                    log.warning("aquarium_detector.detect.frame_read_failed", frame=i)
                    break

                # Detect aquarium (class 0) with optimized threshold
                results = self.model.predict(
                    frame, verbose=False, classes=[0], conf=0.05
                )

                # Debug detailed results
                log.info(
                    "aquarium_detector.frame_analysis",
                    frame=i,
                    mode=self.mode,
                    has_results=bool(results),
                    has_masks=bool(results and results[0].masks),
                    has_boxes=bool(results and results[0].boxes),
                )

                polygon = None
                
                if self.mode == "seg":
                    # Segmentation mode - use existing logic
                    polygon = self._process_segmentation_results(frame, results, i)
                elif self.mode == "det":
                    # Detection mode - extract polygon from bounding boxes
                    polygon = self._extract_polygon_from_detection(frame, results)
                    if polygon is not None:
                        log.info("aquarium_detector.detection_polygon_accepted", frame=i)

                if polygon is not None:
                    good_polygons.append(polygon)

            # Apply the same consensus logic regardless of mode
            return self._find_consensus_polygon(good_polygons, source)
            
        except Exception as e:
            log.error(
                "aquarium_detector.detect.failed", video_path=video_path, error=str(e)
            )
            return []
        finally:
            if source:
                source.release()
