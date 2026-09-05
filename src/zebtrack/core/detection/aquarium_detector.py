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

from zebtrack.core.detection.arena_candidate_selection import (
    is_degenerate_outline,
    rank_box_indices,
)
from zebtrack.io.video_source import VideoFileSource
from zebtrack.utils.geometry import DEFAULT_POLYGON_EPSILON_FACTOR, simplify_polygon

YOLO: Any | None

try:
    from ultralytics import YOLO as _YOLO

    YOLO = _YOLO
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False

log = structlog.get_logger()


#: What the last completed detection actually produced. Read it through
#: :meth:`AquariumDetector.get_last_detection_provenance` — callers need it to
#: tell a real arena from a placeholder, which the return value alone cannot say.
PROVENANCE_NONE = "none"
PROVENANCE_MASK = "mask"
PROVENANCE_BBOX = "bbox"
PROVENANCE_SYNTHETIC_DEFAULT = "synthetic_default"


def _clamp_confidence(value: float | None, *, default: float) -> float:
    """Clamp a confidence value to ``[0.01, 0.95]``.

    Centralized so all entry points (``detect_aquariums``, callers in
    ``LiveCalibrationCoordinator``) share the same bounds. ``None`` resolves
    to the supplied default.
    """
    if value is None:
        value = default
    return max(0.01, min(0.95, float(value)))


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
        self._last_provenance = PROVENANCE_NONE
        if mode not in ["seg", "det"]:
            raise ValueError(f"Invalid mode '{mode}'. Must be 'seg' or 'det'.")

        assert YOLO is not None
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

    @staticmethod
    def _as_valid_polygon(points: Any) -> Polygon | None:
        """Build a Shapely polygon, repairing self-intersections.

        Mask outlines run through ``approxPolyDP`` self-intersect routinely — on a
        real 2026-09-05 run, three of the four frames did. Shapely reports those
        as invalid and every area operation on them returns 0, which used to make
        :meth:`_calculate_iou` answer 0.0 for every pair and left the consensus
        picking whichever frame happened to come first.

        ``buffer(0)`` is the standard repair: it re-polygonizes the self-crossing
        ring. It can yield several disjoint pieces, in which case the largest is
        the arena and the rest are the slivers the crossing created.

        Returns ``None`` when nothing usable survives — callers degrade to 0.0
        rather than raising.
        """
        try:
            polygon = Polygon(points)
            if polygon.is_valid:
                return polygon

            repaired = polygon.buffer(0)
            if repaired.is_empty:
                return None
            if repaired.geom_type == "MultiPolygon":
                repaired = max(repaired.geoms, key=lambda part: part.area)
            if repaired.is_valid and repaired.area > 0:
                return repaired
        # except Exception justified: Shapely raises heterogeneous topology errors
        # on degenerate input; an unusable polygon is not a reason to lose the run.
        except Exception:
            log.debug("aquarium_detector.polygon_repair_failed", exc_info=True)
        return None

    def _calculate_iou(self, poly1_points, poly2_points) -> float:
        """Calculate the Intersection over Union (IoU) of two polygons."""
        try:
            poly1 = self._as_valid_polygon(poly1_points)
            poly2 = self._as_valid_polygon(poly2_points)

            if poly1 is None or poly2 is None:
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

    @staticmethod
    def _normalize_boxes(results: list[Any]) -> tuple[list[float] | None, list[list[float]]]:
        """Extract ``(confidences, xyxy_boxes)`` from a YOLO result.

        Kept separate from ``arena_candidate_selection`` on purpose: the ranking
        RULE is shared with the live flow, but the two flows hand it different
        containers. This is the pre-recorded side's adapter, and it tolerates the
        MagicMock boxes the test suite builds — a box whose ``conf`` or ``xyxy``
        cannot be read yields ``None`` confidences and a zero box, which the
        ranking treats as "unrankable" rather than crashing the detection.
        """
        boxes_attr = results[0].boxes if results else None
        if not boxes_attr:
            return None, []

        confidences: list[float] = []
        boxes: list[list[float]] = []
        confidences_usable = True

        for box in boxes_attr:
            try:
                confidences.append(float(box.conf))
            except (AttributeError, TypeError, ValueError):
                confidences_usable = False
                confidences.append(0.0)

            try:
                xyxy_data = box.xyxy[0]
                if hasattr(xyxy_data, "cpu"):
                    xyxy_data = xyxy_data.cpu().numpy()
                boxes.append([float(v) for v in xyxy_data[:4]])
            except (AttributeError, IndexError, TypeError, ValueError):
                boxes.append([0.0, 0.0, 0.0, 0.0])

        return (confidences if confidences_usable else None), boxes

    def _choose_mask_index(
        self,
        polygons: Any,
        usable: list[int],
        results: list[Any],
        frame: np.ndarray,
        *,
        preferred_index: int | None,
    ) -> int:
        """Pick WHICH mask of a multi-mask frame is the arena.

        ``usable`` is already filtered of degenerate outlines and is never empty.

        Precedence: an index the caller already resolved, then the highest-
        confidence box that both passes the area gate and has a usable mask, then
        the largest remaining outline. The last step matters because the box
        ranking can be unavailable (a model that exposes no ``conf``, a stub, or
        boxes whose geometry does not line up with the masks) — and "unavailable
        ranking" must still yield an arena.
        """
        if preferred_index is not None and preferred_index in usable:
            return preferred_index

        confidences, boxes = self._normalize_boxes(results)
        frame_height, frame_width = frame.shape[:2]
        for idx in rank_box_indices(confidences, boxes, frame_width, frame_height):
            if idx in usable:
                return idx

        return max(usable, key=lambda j: self._outline_bbox_area(polygons[j]))

    @staticmethod
    def _outline_bbox_area(polygon: Any) -> float:
        """Area of an outline's bounding box, or ``0.0`` when unreadable."""
        try:
            xs = [float(point[0]) for point in polygon]
            ys = [float(point[1]) for point in polygon]
        except (IndexError, TypeError, ValueError):
            return 0.0
        return (max(xs) - min(xs)) * (max(ys) - min(ys))

    def _process_segmentation_results(
        self,
        frame: np.ndarray,
        results: list[Any],
        frame_index: int,
        min_area_ratio: float = 0.1,
        max_area_ratio: float = 0.98,
        confidence_threshold: float = 0.05,
        fallback_confidence: float = 0.01,
        *,
        preferred_index: int | None = None,
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

            # Pick the arena among however many masks came back.
            #
            # This used to require EXACTLY ONE mask and discard the frame
            # otherwise. On 2026-08-31 that gate turned a 413-vertex tank mask at
            # 0.928 confidence into a full-frame bounding box, because the model
            # also emitted a zero-height sliver on the bottom edge at 0.272. The
            # sliver is now filtered as degenerate, and a genuine second
            # detection is resolved by confidence instead of aborting the frame.
            usable = [j for j, poly in enumerate(polygons) if not is_degenerate_outline(poly)]
            if not usable:
                log.warning(
                    "aquarium_detector.all_masks_degenerate",
                    frame=frame_index,
                    num_masks=len(polygons),
                )
                return None

            chosen_index = self._choose_mask_index(
                polygons,
                usable,
                results,
                frame,
                preferred_index=preferred_index,
            )
            if len(polygons) > 1:
                log.info(
                    "aquarium_detector.mask_selected",
                    frame=frame_index,
                    num_masks=len(polygons),
                    num_usable=len(usable),
                    chosen_index=chosen_index,
                )

            polygon = polygons[chosen_index].astype(np.int32)

            # Validate that it's large enough (more than min_area_ratio of frame)
            frame_area = frame.shape[0] * frame.shape[1]
            x_min, y_min = polygon[:, 0].min(), polygon[:, 1].min()
            x_max, y_max = polygon[:, 0].max(), polygon[:, 1].max()
            poly_area = (x_max - x_min) * (y_max - y_min)

            area_ratio = poly_area / frame_area
            area_valid = min_area_ratio <= area_ratio <= max_area_ratio

            # Additional confidence validation (if there are boxes)
            # But doesn't block if there aren't - maintains robustness.
            # Uses the CHOSEN detection's confidence, not the frame maximum: with
            # several masks those are different numbers, and validating the
            # polygon we are about to return against another detection's score
            # would let a strong false positive vouch for a weak real one.
            conf_valid = True
            conf_info = "sem_box"
            if confidences:
                chosen_conf = (
                    confidences[chosen_index]
                    if chosen_index < len(confidences)
                    else max(confidences)
                )
                conf_valid = chosen_conf > confidence_threshold
                conf_info = f"{chosen_conf:.3f}"

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
                    threshold=confidence_threshold,
                )
        else:
            # If didn't find aquarium, try alternative strategy
            log.info(
                "aquarium_detector.trying_fallback",
                frame=frame_index,
                fallback_conf=fallback_confidence,
            )
            # ``classes=[0]`` is NOT optional here. Without it this retry accepted
            # the largest mask of ANY class, so on a multi-class weight the arena
            # could come back as whatever object happened to be biggest.
            results_all = self.model.predict(
                frame, verbose=False, classes=[0], conf=fallback_confidence
            )

            if results_all and results_all[0].masks and results_all[0].masks.xy:
                all_polygons = results_all[0].masks.xy
                log.info(
                    "aquarium_detector.fallback_masks_found",
                    frame=frame_index,
                    num_masks=len(all_polygons),
                )

                # Look for the largest mask (likely aquarium)
                if all_polygons:
                    largest_area = 0.0
                    largest_polygon = None

                    for j, poly in enumerate(all_polygons):
                        if is_degenerate_outline(poly):
                            log.info(
                                "aquarium_detector.fallback_mask_degenerate",
                                frame=frame_index,
                                mask_index=j,
                            )
                            continue

                        area = self._outline_bbox_area(poly)

                        if area > largest_area:
                            largest_area = area
                            largest_polygon = poly

                        log.info(
                            "aquarium_detector.fallback_mask",
                            frame=frame_index,
                            mask_index=j,
                            area=int(area),
                        )

                    # Accept only inside the SAME area gate the primary pass uses.
                    # This branch used to check ``> 0.1`` with no ceiling, so a
                    # mask covering the whole field of view was accepted as the
                    # arena — one of the ways this flow returned "the screen".
                    if largest_polygon is not None:
                        frame_area = frame.shape[0] * frame.shape[1]
                        area_ratio = largest_area / frame_area

                        if min_area_ratio <= area_ratio <= max_area_ratio:
                            log.info(
                                "aquarium_detector.fallback_polygon_accepted",
                                frame=frame_index,
                                area_ratio=area_ratio,
                            )
                            return largest_polygon.astype(np.int32)
                        else:
                            log.warning(
                                "aquarium_detector.fallback_polygon_rejected",
                                frame=frame_index,
                                area_ratio=area_ratio,
                                min_ratio=min_area_ratio,
                                max_ratio=max_area_ratio,
                            )
        return None

    def _shape_segmentation_polygon(
        self,
        polygon: np.ndarray,
        *,
        preserve_real_shape: bool,
        epsilon_factor: float,
    ) -> np.ndarray:
        """Decide what a segmentation mask outline becomes downstream.

        This is the ONLY place the pre-recorded pipeline turns a mask into an
        arena, and it deliberately mirrors ``LiveCalibrationCoordinator._burst_pass``
        so the same tank yields the same outline in both flows:

        * ``preserve_real_shape=False`` — collapse to the 4-corner bounding box.
          The historical behaviour, and correct for a rectangular tank whose ROIs
          are drawn against straight edges.
        * ``preserve_real_shape=True`` — keep the mask, simplified. Raw YOLO
          contours carry one vertex per boundary pixel; handing 200+ points to the
          editable canvas and the ArenaROI parquet is unusable.

        Never raises: ``simplify_polygon`` degrades to the raw outline, and the
        bbox branch is pure arithmetic on values we already validated.
        """
        if preserve_real_shape:
            simplified = simplify_polygon(polygon, epsilon_factor=epsilon_factor)
            return np.array(simplified, dtype=np.int32)

        x_min, y_min = int(polygon[:, 0].min()), int(polygon[:, 1].min())
        x_max, y_max = int(polygon[:, 0].max()), int(polygon[:, 1].max())
        log.info(
            "aquarium_detector.mask_collapsed_to_bbox",
            raw_vertices=len(polygon),
            bbox=[x_min, y_min, x_max, y_max],
        )
        return np.array(
            [[x_min, y_min], [x_max, y_min], [x_max, y_max], [x_min, y_max]],
            dtype=np.int32,
        )

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
        confidence_threshold: float | None = None,
        fallback_confidence: float | None = None,
        preserve_real_shape: bool = False,
        polygon_epsilon_factor: float = DEFAULT_POLYGON_EPSILON_FACTOR,
    ) -> list[np.ndarray]:
        """
        Analyzes initial frames of a video to find the most stable aquarium polygon.

        Supports both segmentation and detection modes:
        - "seg": Uses segmentation masks, shaped by ``preserve_real_shape``
        - "det": Uses bounding box detections converted to rectangular polygons

        Args:
            video_path: The path to the video file.
            stabilization_frames: The number of initial frames to analyze.
            min_area_ratio: Minimum area ratio relative to frame size.
            max_area_ratio: Maximum area ratio relative to frame size.
            confidence_threshold: YOLO prediction + validation confidence.
                ``None`` falls back to the historical 0.05. Clamped to ``[0.01, 0.95]``.
            fallback_confidence: Low-confidence retry used inside
                ``_process_segmentation_results`` when the primary pass produces
                no usable mask. ``None`` falls back to 0.01.
            preserve_real_shape: In ``"seg"`` mode, keep the mask outline
                (simplified to ~6-12 vertices) instead of collapsing it to a
                4-corner bounding box. Ignored in ``"det"`` mode, which has no
                mask to preserve. Resolve it with
                ``core.services.arena_detection_policy.resolve_arena_detection``
                rather than deciding at the call site — the live and
                pre-recorded flows must agree.
            polygon_epsilon_factor: Douglas-Peucker epsilon as a fraction of the
                outline perimeter, applied only when the mask shape is kept.
                Callers pass ``settings.yolo_model.aquarium_polygon_epsilon``.

        Returns:
            A list containing the single most stable polygon, or an empty list if
            no stable polygon could be found.
        """
        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        conf = _clamp_confidence(confidence_threshold, default=0.05)
        fallback_conf = _clamp_confidence(fallback_confidence, default=0.01)
        self._last_provenance = PROVENANCE_NONE
        log.info(
            "aquarium_detector.detect.start",
            video_path=video_path,
            mode=self.mode,
            min_ratio=min_area_ratio,
            confidence_threshold=conf,
            fallback_confidence=fallback_conf,
            preserve_real_shape=preserve_real_shape,
        )
        source = None
        try:
            source = VideoFileSource(video_path)
            mask_polygons: list[np.ndarray] = []
            bbox_polygons: list[np.ndarray] = []

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

                # Detect aquarium (class 0) using configured threshold
                results = self.model.predict(frame, verbose=False, classes=[0], conf=conf)

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
                from_mask = False

                if self.mode == "seg":
                    # Segmentation mode - use existing logic
                    polygon = self._process_segmentation_results(
                        frame,
                        results,
                        i,
                        min_area_ratio,
                        max_area_ratio,
                        confidence_threshold=conf,
                        fallback_confidence=fallback_conf,
                    )
                    if polygon is None:
                        # DEGRADE, never lose the detection: a "seg" weight slot
                        # pointing at a box model (or a frame where the mask head
                        # produced nothing) still has usable boxes. Falling through
                        # to them costs the exact outline; returning nothing sends
                        # the user to manual drawing for a tank the model found.
                        polygon = self._extract_polygon_from_detection(
                            frame, results, min_area_ratio, max_area_ratio
                        )
                        if polygon is not None:
                            log.warning(
                                "aquarium_detector.mask_unavailable_fallback",
                                frame=i,
                                message="Segmentation requested but no mask; using bbox.",
                            )
                    else:
                        # Only a KEPT mask outline counts as mask provenance. With
                        # ``preserve_real_shape=False`` the call below collapses it
                        # to a rectangle, which must compete with the other
                        # rectangles, not against them.
                        from_mask = preserve_real_shape
                        polygon = self._shape_segmentation_polygon(
                            polygon,
                            preserve_real_shape=preserve_real_shape,
                            epsilon_factor=polygon_epsilon_factor,
                        )
                elif self.mode == "det":
                    # Detection mode - extract polygon from bounding boxes
                    polygon = self._extract_polygon_from_detection(
                        frame, results, min_area_ratio, max_area_ratio
                    )
                    if polygon is not None:
                        log.info("aquarium_detector.detection_polygon_accepted", frame=i)

                if polygon is not None:
                    if from_mask:
                        mask_polygons.append(polygon)
                    else:
                        bbox_polygons.append(polygon)

                    # MELHORIA: Early exit if we have enough consistent data
                    accepted = len(mask_polygons) + len(bbox_polygons)
                    if accepted >= 4:
                        log.info("aquarium_detector.detect.early_exit", count=accepted)
                        break

            # Consensus runs over ONE population, never a mixture.
            #
            # Rectangles agree with each other at IoU ~0.99 while real mask
            # outlines jitter from frame to frame, so a bbox fallback dropped into
            # the same pool systematically out-votes the very shapes the user
            # asked to preserve — and one degraded frame would be enough to send
            # the arena back to a rectangle. When ``preserve_real_shape`` is off,
            # ``mask_polygons`` stays empty and this is byte-for-byte the previous
            # behaviour.
            good_polygons = mask_polygons or bbox_polygons
            self._last_provenance = PROVENANCE_MASK if mask_polygons else PROVENANCE_BBOX
            if mask_polygons and bbox_polygons:
                log.info(
                    "aquarium_detector.detect.population_split",
                    mask_polygons=len(mask_polygons),
                    bbox_polygons=len(bbox_polygons),
                    used="mask",
                )

            consensus = self._find_consensus_polygon(good_polygons, source)
            if not good_polygons:
                self._last_provenance = (
                    PROVENANCE_SYNTHETIC_DEFAULT if consensus else PROVENANCE_NONE
                )
            return consensus

        # except Exception justified: cv2/numpy aquarium detection pipeline — heterogeneous failures
        except Exception as e:
            log.error("aquarium_detector.detect.failed", video_path=video_path, error=str(e))
            self._last_provenance = PROVENANCE_NONE
            return []
        finally:
            if source:
                source.release()

    @staticmethod
    def _multi_aquarium_outline(
        box_xyxy: tuple[float, float, float, float],
        *,
        mask_xy: Any,
        box_index: int,
        frame_index: int,
        epsilon_factor: float,
    ) -> np.ndarray:
        """Outline for ONE accepted aquarium box: its mask when usable, else its box.

        ``mask_xy`` is ``None`` whenever masks were not requested or the model is
        not a segmentation one, which is why the rectangle stays the default and
        the historical behaviour is untouched when nothing asked for shapes.
        """
        x1, y1, x2, y2 = box_xyxy

        if mask_xy is not None and box_index < len(mask_xy):
            raw_mask = mask_xy[box_index]
            if not is_degenerate_outline(raw_mask):
                return np.array(
                    simplify_polygon(raw_mask, epsilon_factor=epsilon_factor),
                    dtype=np.int32,
                )
            log.warning(
                "aquarium_detector.detect_multiple.mask_degenerate",
                frame=frame_index,
                box_index=box_index,
            )

        return np.array(
            [
                [int(x1), int(y1)],
                [int(x2), int(y1)],
                [int(x2), int(y2)],
                [int(x1), int(y2)],
            ],
            dtype=np.int32,
        )

    def detect_multiple_aquariums(
        self,
        video_path: Path | str,
        expected_count: int = 2,
        stabilization_frames: int = 10,
        min_area_ratio: float = 0.1,
        max_area_ratio: float = 0.98,
        confidence_threshold: float | None = None,
        preserve_real_shape: bool = False,
        polygon_epsilon_factor: float = DEFAULT_POLYGON_EPSILON_FACTOR,
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
            confidence_threshold: YOLO prediction confidence. ``None`` falls back
                to the historical 0.05. Clamped to ``[0.01, 0.95]``.
            preserve_real_shape: In ``"seg"`` mode, keep each aquarium's mask
                outline instead of its bounding box. Ignored in ``"det"`` mode.
                Resolve it with ``resolve_arena_detection`` — this method used to
                take no such argument at all, so a two-aquarium project could not
                honour "preserve the real shape" no matter what it configured.
            polygon_epsilon_factor: Douglas-Peucker epsilon as a fraction of the
                outline perimeter, applied only when the mask shape is kept.

        Returns:
            List of polygon numpy arrays (shape: Nx2), sorted by X position.
            Returns empty list if detection fails.

        Raises:
            ValueError: If expected_count != 2.
        """
        if expected_count != 2:
            # Internal API contract, not operator copy: the wizard already
            # validates this count with a translated message. English without
            # _(), like the other developer-facing guards.
            raise ValueError("Only 2 aquariums are supported")

        video_path_str = str(Path(video_path) if isinstance(video_path, str) else video_path)
        conf = _clamp_confidence(confidence_threshold, default=0.05)
        log.info(
            "aquarium_detector.detect_multiple.start",
            video_path=video_path_str,
            expected_count=expected_count,
            confidence_threshold=conf,
            mode=self.mode,
            preserve_real_shape=preserve_real_shape,
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

                # Detect all aquariums (class 0) using configured threshold
                results = self.model.predict(frame, verbose=False, classes=[0], conf=conf)

                if results and results[0].boxes:
                    # Get all detections for this frame
                    boxes = results[0].boxes
                    frame_polygons = []

                    # Masks are read at the SAME index as the accepted box, which
                    # is what keeps each outline paired with the aquarium it
                    # belongs to. Without this the method was box-only and a
                    # two-aquarium project could never preserve a real shape.
                    use_masks = preserve_real_shape and self.mode == "seg"
                    mask_xy = None
                    if use_masks:
                        masks = getattr(results[0], "masks", None)
                        mask_xy = getattr(masks, "xy", None) if masks is not None else None

                    for _j, box in enumerate(boxes):
                        box_conf = float(box.conf)
                        if box_conf < conf:
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
                            polygon = self._multi_aquarium_outline(
                                (x1, y1, x2, y2),
                                mask_xy=mask_xy,
                                box_index=_j,
                                frame_index=i,
                                epsilon_factor=polygon_epsilon_factor,
                            )

                            # center_x always comes from the BOX, never the mask:
                            # the left-to-right ordering below must not shift just
                            # because an outline is asymmetric.
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

    def get_last_detection_provenance(self) -> str:
        """What the last :meth:`detect_aquariums` call actually produced.

        One of ``"mask"``, ``"bbox"``, ``"synthetic_default"`` or ``"none"``.

        The return value of ``detect_aquariums`` cannot express this on its own: a
        placeholder rectangle built from the frame size and a real segmentation
        outline are both "a list with one polygon". Callers need the difference to
        decide whether they may report success — until this existed, a run where
        NOTHING was detected still logged ``single_success`` and drew an arena the
        researcher had no reason to distrust.

        Mirrors :meth:`get_last_source_dimensions`: out-of-band metadata about the
        last run, exposed through an accessor rather than widening the return type
        of a method with several call sites.
        """
        return self._last_provenance


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
            # Internal API contract, not operator copy: the wizard already
            # validates this count with a translated message. English without
            # _(), like the other developer-facing guards.
            raise ValueError("Only 2 aquariums are supported")

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
            # Internal API contract, not operator copy: the wizard already
            # validates this count with a translated message. English without
            # _(), like the other developer-facing guards.
            raise ValueError("Only 2 aquariums are supported")

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
