"""Aquarium detection module using YOLO segmentation models.

Provides the AquariumDetector class for detecting and segmenting aquarium boundaries
in video frames for perspective correction and calibration.

Also includes ContourBasedMultiAquariumDetector for detecting multiple aquariums
using computer vision contour analysis when YOLO models are not available or
for videos with 2 aquariums.
"""

from pathlib import Path
from typing import Any

import cv2
import numpy as np
import structlog
from shapely.geometry import Polygon

try:
    from ultralytics import YOLO

    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None  # type: ignore[misc,assignment]
    ULTRALYTICS_AVAILABLE = False

from zebtrack.io.video_source import VideoFileSource

log = structlog.get_logger()


class AquariumDetector:
    """Detects aquariums in a video using a YOLO segmentation model."""

    def __init__(self, model_path: Path | str, mode: str = "seg"):
        """
        Initialize the AquariumDetector.

        Args:
            model_path: Path to the YOLO model (.pt file).
            mode: Detection mode - "seg" for segmentation, "det" for detection.
        """
        model_path = str(Path(model_path) if isinstance(model_path, str) else model_path)
        if not ULTRALYTICS_AVAILABLE:
            raise ImportError("Ultralytics is not available. Please install ultralytics package.")

        self.mode = mode
        self._last_source_width = 0
        self._last_source_height = 0
        if mode not in ["seg", "det"]:
            raise ValueError(f"Invalid mode '{mode}'. Must be 'seg' or 'det'.")

        try:
            self.model = YOLO(model_path)
            log.info("aquarium_detector.init.success", model_path=model_path, mode=mode)
        # except Exception justified: Ultralytics YOLO model initialization can raise
        # heterogeneous exceptions (path/weights/config issues); log and re-raise.
        except Exception as e:
            log.error(
                "aquarium_detector.init.failed",
                model_path=model_path,
                mode=mode,
                error=str(e),
            )
            raise

    def _calculate_iou(self, poly1_points, poly2_points) -> float:
        """Calculate the Intersection over Union (IoU) of two polygons."""
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
        # except Exception justified: Shapely polygon geometry operations can raise
        # heterogeneous exceptions (invalid geometry, topology errors); fallback to 0.
        except Exception as e:
            log.warning(
                "aquarium_detector.iou_calculation_failed",
                error=str(e),
                exc_info=True,
            )
            return 0.0

    def _extract_polygon_from_detection(
        self,
        frame: np.ndarray,
        results: list[Any],
        min_area_ratio: float = 0.1,
        max_area_ratio: float = 0.98,
    ) -> np.ndarray | None:
        """
        Extract a polygon from detection results (bounding boxes).

        Args:
            frame: The frame from which detection was performed
            results: YOLO detection results
            min_area_ratio: Minimum area ratio for validation
            max_area_ratio: Maximum area ratio for validation

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
        # Handle both PyTorch tensors and numpy arrays
        xyxy_data = best_box.xyxy[0]
        if hasattr(xyxy_data, "cpu"):
            # PyTorch tensor
            x1, y1, x2, y2 = xyxy_data.cpu().numpy()
        else:
            # Already numpy array
            x1, y1, x2, y2 = xyxy_data

        # Create rectangular polygon from bounding box
        polygon = np.array(
            [
                [int(x1), int(y1)],  # top-left
                [int(x2), int(y1)],  # top-right
                [int(x2), int(y2)],  # bottom-right
                [int(x1), int(y2)],  # bottom-left
            ],
            dtype=np.int32,
        )

        # Validate size - should be reasonable portion of frame
        frame_area = frame.shape[0] * frame.shape[1]
        box_area = (x2 - x1) * (y2 - y1)
        area_ratio = box_area / frame_area

        if area_ratio < min_area_ratio:  # Too small
            log.warning(
                "aquarium_detector.detection_too_small",
                confidence=best_conf,
                area_ratio=area_ratio,
                min_ratio=min_area_ratio,
            )
            return None

        if area_ratio > max_area_ratio:  # Almost entire frame, likely false positive
            log.warning(
                "aquarium_detector.detection_too_large",
                confidence=best_conf,
                area_ratio=area_ratio,
                max_ratio=max_area_ratio,
            )
            return None

        log.info(
            "aquarium_detector.detection_polygon_extracted",
            confidence=best_conf,
            area_ratio=area_ratio,
            bbox=[int(x1), int(y1), int(x2), int(y2)],
        )

        return polygon

    def _process_segmentation_results(
        self,
        frame: np.ndarray,
        results: list[Any],
        frame_index: int,
        min_area_ratio: float = 0.1,
        max_area_ratio: float = 0.98,
    ) -> np.ndarray | None:
        """
        Process segmentation results to extract a valid aquarium polygon.

        Args:
            frame: Video frame
            results: YOLO results
            frame_index: Frame number for logging
            min_area_ratio: Minimum area ratio for validation
            max_area_ratio: Maximum area ratio for validation

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

                # Validate that it's large enough (more than min_area_ratio of frame)
                frame_area = frame.shape[0] * frame.shape[1]
                x_min, y_min = polygon[:, 0].min(), polygon[:, 1].min()
                x_max, y_max = polygon[:, 0].max(), polygon[:, 1].max()
                poly_area = (x_max - x_min) * (y_max - y_min)

                area_ratio = poly_area / frame_area
                area_valid = min_area_ratio <= area_ratio <= max_area_ratio

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
                        area_ratio=area_ratio,
                        confidence=conf_info,
                        min_ratio=min_area_ratio,
                    )
                    return polygon
                elif not area_valid:
                    log.warning(
                        "aquarium_detector.polygon_size_invalid",
                        frame=frame_index,
                        area_ratio=area_ratio,
                        confidence=conf_info,
                        min_ratio=min_area_ratio,
                        max_ratio=max_area_ratio,
                    )
                elif not conf_valid:
                    log.warning(
                        "aquarium_detector.confidence_too_low",
                        frame=frame_index,
                        area_ratio=area_ratio,
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

    def _find_consensus_polygon(
        self,
        good_polygons: list[np.ndarray],
        source: Any,
    ) -> list[np.ndarray]:
        """
        Find the most stable polygon using consensus approach.

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
            except (ValueError, TypeError) as e:
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

    def detect_aquariums(
        self,
        video_path: Path | str,
        stabilization_frames: int = 10,
        min_area_ratio: float = 0.1,
        max_area_ratio: float = 0.98,
    ) -> list[np.ndarray]:
        """
        Analyzes initial frames of a video to find the most stable aquarium polygon.

        Supports both segmentation and detection modes:
        - "seg": Uses segmentation masks (original behavior)
        - "det": Uses bounding box detections converted to rectangular polygons

        Args:
            video_path: The path to the video file.
            stabilization_frames: The number of initial frames to analyze.
            min_area_ratio: Minimum area ratio relative to frame size.
            max_area_ratio: Maximum area ratio relative to frame size.
            frame_skip: Frames to skip between analysis attempts (default 5).

        Returns:
            A list containing the single most stable polygon, or an empty list if
            no stable polygon could be found.
        """
        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        log.info(
            "aquarium_detector.detect.start",
            video_path=video_path,
            mode=self.mode,
            min_ratio=min_area_ratio,
        )
        source = None
        try:
            source = VideoFileSource(video_path)
            good_polygons = []

            # MELHORIA: Unified logic with LiveCameraService (frame skip + early exit)
            frame_skip = 5
            max_frames_to_check = stabilization_frames * frame_skip  # e.g. 10 * 5 = 50 frames

            analyzed_count = 0

            for i in range(max_frames_to_check):
                ret, frame = source.get_frame()
                if not ret:
                    if i == 0:
                        log.warning("aquarium_detector.detect.frame_read_failed", frame=i)
                    break

                # Frame skip logic
                if i % frame_skip != 0:
                    continue

                analyzed_count += 1
                if analyzed_count > stabilization_frames:
                    break

                if frame is None:
                    continue

                # Detect aquarium (class 0) with optimized threshold
                results = self.model.predict(frame, verbose=False, classes=[0], conf=0.05)

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
                    polygon = self._process_segmentation_results(
                        frame, results, i, min_area_ratio, max_area_ratio
                    )
                elif self.mode == "det":
                    # Detection mode - extract polygon from bounding boxes
                    polygon = self._extract_polygon_from_detection(
                        frame, results, min_area_ratio, max_area_ratio
                    )
                    if polygon is not None:
                        log.info("aquarium_detector.detection_polygon_accepted", frame=i)

                if polygon is not None:
                    good_polygons.append(polygon)

                    # MELHORIA: Early exit if we have enough consistent data
                    if len(good_polygons) >= 4:
                        log.info("aquarium_detector.detect.early_exit", count=len(good_polygons))
                        break

            # Apply the same consensus logic regardless of mode
            return self._find_consensus_polygon(good_polygons, source)

        # except Exception justified: cv2/numpy aquarium detection pipeline — heterogeneous failures
        except Exception as e:
            log.error("aquarium_detector.detect.failed", video_path=video_path, error=str(e))
            return []
        finally:
            if source:
                source.release()

    def detect_multiple_aquariums(
        self,
        video_path: Path | str,
        expected_count: int = 2,
        stabilization_frames: int = 10,
        min_area_ratio: float = 0.1,
        max_area_ratio: float = 0.98,
    ) -> list[np.ndarray]:
        """Detect multiple aquariums in a video.

        This method attempts to detect multiple aquariums using YOLO first,
        and falls back to contour-based detection if YOLO doesn't find
        the expected count.

        Args:
            video_path: Path to the video file.
            expected_count: Expected number of aquariums (must be 2).
            stabilization_frames: Number of frames to analyze.
            min_area_ratio: Minimum area ratio per aquarium.
            max_area_ratio: Maximum area ratio per aquarium.

        Returns:
            List of polygon numpy arrays (shape: Nx2), sorted by X position.
            Returns empty list if detection fails.

        Raises:
            ValueError: If expected_count != 2.
        """
        if expected_count != 2:
            raise ValueError("Apenas 2 aquários são suportados")

        video_path_str = str(Path(video_path) if isinstance(video_path, str) else video_path)
        log.info(
            "aquarium_detector.detect_multiple.start",
            video_path=video_path_str,
            expected_count=expected_count,
        )

        # Try YOLO-based detection first
        source = None
        try:
            source = VideoFileSource(video_path_str)
            self._last_source_width = int(getattr(source, "width", 0) or 0)
            self._last_source_height = int(getattr(source, "height", 0) or 0)
            all_polygons = []

            # MELHORIA: Unified logic with LiveCameraService (frame skip + early exit)
            frame_skip = 5
            max_frames_to_check = stabilization_frames * frame_skip
            analyzed_count = 0

            for i in range(max_frames_to_check):
                ret, frame = source.get_frame()
                if not ret:
                    break

                # Frame skip logic
                if i % frame_skip != 0:
                    continue

                analyzed_count += 1
                if analyzed_count > stabilization_frames:
                    break

                if frame is None:
                    continue

                self._last_source_width = int(frame.shape[1])
                self._last_source_height = int(frame.shape[0])

                # Detect all aquariums (class 0) with lower threshold
                results = self.model.predict(frame, verbose=False, classes=[0], conf=0.05)

                if results and results[0].boxes:
                    # Get all detections for this frame
                    boxes = results[0].boxes
                    frame_polygons = []

                    for _j, box in enumerate(boxes):
                        conf = float(box.conf)
                        if conf < 0.05:
                            continue

                        xyxy_data = box.xyxy[0]
                        if hasattr(xyxy_data, "cpu"):
                            x1, y1, x2, y2 = xyxy_data.cpu().numpy()
                        else:
                            x1, y1, x2, y2 = xyxy_data

                        # Validate area
                        if frame is None:
                            continue
                        frame_area = frame.shape[0] * frame.shape[1]
                        box_area = (x2 - x1) * (y2 - y1)
                        area_ratio = box_area / frame_area

                        if min_area_ratio <= area_ratio <= 0.50:  # Cap max at 50 for multi
                            polygon = np.array(
                                [
                                    [int(x1), int(y1)],
                                    [int(x2), int(y1)],
                                    [int(x2), int(y2)],
                                    [int(x1), int(y2)],
                                ],
                                dtype=np.int32,
                            )
                            frame_polygons.append((polygon, (x1 + x2) / 2))  # polygon, center_x

                    # If we found exactly 2 in this frame, add them
                    if len(frame_polygons) == expected_count:
                        all_polygons.append(frame_polygons)

                        # MELHORIA: Early exit if we have enough consistent data
                        if len(all_polygons) >= 4:
                            log.info(
                                "aquarium_detector.detect_multiple.early_exit",
                                count=len(all_polygons),
                            )
                            break

            # If we consistently found 2 aquariums, use those
            if all_polygons:
                log.info(
                    "aquarium_detector.detect_multiple.yolo_success",
                    frames_with_2=len(all_polygons),
                )
                # Take the most recent frame with 2 detections
                best_frame = all_polygons[-1]
                # Sort by X position
                best_frame.sort(key=lambda x: x[1])
                return [p[0] for p in best_frame]

        # except Exception justified: cv2 image filtering + contour analysis pipeline
        except Exception as e:
            log.warning(
                "aquarium_detector.detect_multiple.yolo_failed",
                error=str(e),
            )
        finally:
            if source:
                source.release()

        # Fall back to contour-based detection
        log.info("aquarium_detector.detect_multiple.fallback_to_contours")
        contour_detector = ContourBasedMultiAquariumDetector()
        return contour_detector.detect_multiple_aquariums(
            video_path_str, expected_count, stabilization_frames
        )

    def get_last_source_dimensions(self) -> tuple[int, int] | None:
        """Return dimensions of the source frame used in the last detection run."""
        if self._last_source_width > 0 and self._last_source_height > 0:
            return (self._last_source_width, self._last_source_height)
        return None


class ContourBasedMultiAquariumDetector:
    """Detects multiple aquariums using computer vision contour analysis.

    This detector uses traditional CV techniques (thresholding, edge detection,
    contour analysis) to find 2 separate aquarium regions in a video frame.
    It's designed as a fallback when YOLO models are not available or for
    specific multi-aquarium detection scenarios.
    """

    def __init__(self) -> None:
        """Initialize the ContourBasedMultiAquariumDetector."""
        log.info("contour_detector.init.success")

    def detect_multiple_aquariums(
        self,
        video_path: Path | str,
        expected_count: int = 2,
        stabilization_frames: int = 10,
    ) -> list[np.ndarray]:
        """Detect multiple aquariums using contour analysis.

        Algorithm:
        1. Read stabilization frames and calculate average frame
        2. Convert to grayscale
        3. Apply adaptive threshold
        4. Edge detection (Canny)
        5. Find contours and approximate to polygons (approxPolyDP)
        6. Filter by area (each aquarium should be ~15-45% of frame)
        7. Filter by shape (aspect ratio close to rectangle)
        8. Validate no significant overlap
        9. Sort by X position (left aquarium = index 0)

        Args:
            video_path: Path to the video file.
            expected_count: Expected number of aquariums (must be 2).
            stabilization_frames: Number of frames to analyze for stability.

        Returns:
            List of 2 polygon numpy arrays (shape: Nx2) or empty list if failed.

        Raises:
            ValueError: If expected_count != 2.
        """
        if expected_count != 2:
            raise ValueError("Apenas 2 aquários são suportados")

        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        log.info(
            "contour_detector.detect.start",
            video_path=video_path,
            stabilization_frames=stabilization_frames,
        )

        source = None
        try:
            source = VideoFileSource(video_path)

            # Collect frames for averaging
            frames = []
            for i in range(stabilization_frames):
                ret, frame = source.get_frame()
                if not ret:
                    log.warning("contour_detector.frame_read_failed", frame=i)
                    break
                if frame is not None:
                    frames.append(frame)

            if not frames:
                log.error("contour_detector.no_frames_read")
                return []

            # Calculate average frame for stability
            avg_frame = np.mean(frames, axis=0).astype(np.uint8)

            # Detect aquariums in averaged frame
            polygons = self._detect_aquariums_by_contours(avg_frame, expected_count)

            if len(polygons) == expected_count:
                log.info(
                    "contour_detector.detect.success",
                    aquarium_count=len(polygons),
                )
                return polygons
            else:
                log.warning(
                    "contour_detector.detect.wrong_count",
                    expected=expected_count,
                    found=len(polygons),
                )
                return []

        # except Exception justified: cv2 multi-aquarium detection — heterogeneous failures
        except Exception as e:
            log.error("contour_detector.detect.failed", video_path=video_path, error=str(e))
            return []
        finally:
            if source:
                source.release()

    def detect_multiple_aquariums_from_frame(
        self,
        frame: np.ndarray,
        expected_count: int = 2,
    ) -> list[np.ndarray]:
        """Detect multiple aquariums from a single frame.

        Args:
            frame: Video frame as numpy array (BGR format).
            expected_count: Expected number of aquariums (must be 2).

        Returns:
            List of polygon numpy arrays or empty list if failed.

        Raises:
            ValueError: If expected_count != 2.
        """
        if expected_count != 2:
            raise ValueError("Apenas 2 aquários são suportados")

        return self._detect_aquariums_by_contours(frame, expected_count)

    def _detect_aquariums_by_contours(
        self,
        frame: np.ndarray,
        expected_count: int = 2,
    ) -> list[np.ndarray]:
        """Implementation of contour-based aquarium detection algorithm.

        Args:
            frame: Video frame to analyze.
            expected_count: Number of aquariums to detect.

        Returns:
            List of polygon numpy arrays sorted by X position.
        """
        frame_height, frame_width = frame.shape[:2]
        frame_area = frame_height * frame_width

        # 1. Pre-processing
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # 2. Adaptive threshold
        thresh = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            11,
            2,
        )

        # 3. Morphological operations to clean noise
        kernel = np.ones((5, 5), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

        # 4. Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        log.debug("contour_detector.contours_found", count=len(contours))

        # 5. Filter and collect candidates
        candidates = []

        for contour in contours:
            area = cv2.contourArea(contour)

            # Filter by area: each aquarium should be 10-50% of frame
            area_ratio = area / frame_area
            if area_ratio < 0.10 or area_ratio > 0.50:
                continue

            # Get bounding box
            x, y, w, h = cv2.boundingRect(contour)

            # Calculate aspect ratio (width/height)
            aspect_ratio = w / h if h > 0 else 0

            # Filter by aspect ratio: should be reasonably rectangular (0.5 to 2.0)
            if aspect_ratio < 0.3 or aspect_ratio > 3.0:
                continue

            # Calculate solidity (area / convex hull area)
            hull = cv2.convexHull(contour)
            hull_area = cv2.contourArea(hull)
            solidity = area / hull_area if hull_area > 0 else 0

            # Filter by solidity: should be fairly solid (> 0.7)
            if solidity < 0.6:
                continue

            # Approximate polygon
            epsilon = 0.02 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)

            # Calculate center X for sorting
            center_x = x + w / 2

            candidates.append(
                {
                    "contour": approx,
                    "area": area,
                    "area_ratio": area_ratio,
                    "bbox": (x, y, w, h),
                    "center_x": center_x,
                    "aspect_ratio": aspect_ratio,
                    "solidity": solidity,
                }
            )

            log.debug(
                "contour_detector.candidate_found",
                area_ratio=f"{area_ratio:.3f}",
                aspect_ratio=f"{aspect_ratio:.2f}",
                solidity=f"{solidity:.2f}",
                center_x=int(center_x),
            )

        # 6. Select the best candidates
        if len(candidates) < expected_count:
            log.warning(
                "contour_detector.insufficient_candidates",
                found=len(candidates),
                expected=expected_count,
            )
            return []

        # Sort by area (largest first) and take top candidates
        candidates.sort(key=lambda c: c["area"], reverse=True)
        selected = candidates[:expected_count]

        # 7. Validate no significant overlap
        if len(selected) >= 2:
            if self._check_overlap(selected[0]["bbox"], selected[1]["bbox"]):
                log.warning("contour_detector.overlapping_detections")
                return []

        # 8. Sort by X position (left aquarium first)
        selected.sort(key=lambda c: c["center_x"])

        result = [c["contour"].reshape(-1, 2) for c in selected]

        log.info(
            "contour_detector.candidates_selected",
            count=len(result),
            positions=[int(c["center_x"]) for c in selected],
        )

        return result

    def _check_overlap(self, bbox1: tuple, bbox2: tuple, threshold: float = 0.1) -> bool:
        """Check if two bounding boxes overlap significantly.

        Args:
            bbox1: First bounding box (x, y, w, h).
            bbox2: Second bounding box (x, y, w, h).
            threshold: Maximum allowed overlap ratio.

        Returns:
            True if boxes overlap more than threshold, False otherwise.
        """
        x1, y1, w1, h1 = bbox1
        x2, y2, w2, h2 = bbox2

        # Calculate intersection
        x_left = max(x1, x2)
        y_top = max(y1, y2)
        x_right = min(x1 + w1, x2 + w2)
        y_bottom = min(y1 + h1, y2 + h2)

        if x_right < x_left or y_bottom < y_top:
            return False

        intersection = (x_right - x_left) * (y_bottom - y_top)
        min_area = min(w1 * h1, w2 * h2)

        overlap_ratio = intersection / min_area if min_area > 0 else 0

        log.debug(
            "contour_detector.overlap_check",
            overlap_ratio=f"{overlap_ratio:.3f}",
            threshold=threshold,
        )

        return overlap_ratio > threshold

    def _validate_aquarium_pair(
        self,
        polygons: list[np.ndarray],
        frame_width: int,
    ) -> bool:
        """Validate that detected aquariums form a valid pair.

        Checks:
        - Aquariums are on opposite sides of the frame
        - Aquariums have similar sizes (within 50%)
        - Aquariums don't overlap

        Args:
            polygons: List of 2 polygon arrays.
            frame_width: Width of the video frame.

        Returns:
            True if valid pair, False otherwise.
        """
        if len(polygons) != 2:
            return False

        # Get bounding boxes
        x1_min, x1_max = polygons[0][:, 0].min(), polygons[0][:, 0].max()
        x2_min, x2_max = polygons[1][:, 0].min(), polygons[1][:, 0].max()

        # Check that aquariums are on different sides
        center1 = (x1_min + x1_max) / 2
        center2 = (x2_min + x2_max) / 2
        mid_frame = frame_width / 2

        # One should be on left half, other on right half
        if not (
            (center1 < mid_frame and center2 > mid_frame)
            or (center1 > mid_frame and center2 < mid_frame)
        ):
            log.warning("contour_detector.aquariums_not_opposite_sides")
            return False

        # Check similar sizes
        area1 = cv2.contourArea(polygons[0])
        area2 = cv2.contourArea(polygons[1])
        size_ratio = min(area1, area2) / max(area1, area2) if max(area1, area2) > 0 else 0

        if size_ratio < 0.5:
            log.warning(
                "contour_detector.aquariums_size_mismatch",
                size_ratio=f"{size_ratio:.2f}",
            )
            return False

        return True
