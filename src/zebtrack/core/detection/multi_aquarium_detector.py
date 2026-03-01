"""Multi-aquarium detection and tracking for zebrafish.

Handles partitioned detection where multiple aquariums exist in a single
video frame. Each aquarium gets independent tracking with offset track IDs.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from types import SimpleNamespace
from typing import TYPE_CHECKING

import cv2
import numpy as np
import structlog

from zebtrack.core.detection.detection_post_processor import DetectionPostProcessor
from zebtrack.core.detection.detection_types import AquariumData, MultiAquariumZoneData, ZoneData
from zebtrack.core.detection.single_subject_tracker import SingleSubjectTracker
from zebtrack.core.detection.zone_scaler import ZoneScaler
from zebtrack.plugins.base import DetectorPlugin
from zebtrack.tracker.byte_tracker import BYTETracker

if TYPE_CHECKING:
    from zebtrack.settings import Settings

log = structlog.get_logger()

__all__ = ["MultiAquariumDetector"]


class MultiAquariumDetector:
    """Manages detection across multiple aquariums with independent tracking.

    Each aquarium gets its own tracker (ByteTracker or SingleSubjectTracker)
    and track IDs are offset by ``aquarium_id * 1000`` to avoid collisions.

    Args:
        plugin: An instantiated detector plugin.
        zone_scaler: ZoneScaler instance for coordinate scaling.
        post_processor: DetectionPostProcessor for utilities.
        base_width: The reference width zones were defined on.
        base_height: The reference height zones were defined on.
        settings_obj: Settings instance (injected, optional for backward compat).
    """

    def __init__(
        self,
        plugin: DetectorPlugin,
        zone_scaler: ZoneScaler,
        post_processor: DetectionPostProcessor,
        base_width: int = 1280,
        base_height: int = 720,
        settings_obj: "Settings | None" = None,
    ) -> None:
        self.plugin = plugin
        if not self.plugin:
            log.error("multi_aquarium_detector.init.no_plugin")
            raise ValueError("MultiAquariumDetector must be initialized with a valid plugin.")

        self.settings = settings_obj
        self.zone_scaler = zone_scaler
        self.post_processor = post_processor
        self.base_width = base_width
        self.base_height = base_height

        # Dynamic class ID resolution
        self.aquarium_class_id, self.animal_class_id = DetectionPostProcessor.resolve_class_ids(
            plugin
        )

        # Multi-aquarium state
        self._multi_aquarium_mode: bool = False
        self._aquariums: list[AquariumData] = []
        self._byte_trackers_multi: dict[int, BYTETracker] = {}
        self._single_subject_trackers_multi: dict[int, SingleSubjectTracker] = {}
        self._scaled_aquarium_polygons: dict[int, np.ndarray] = {}
        self._scaled_aquarium_roi_polygons: dict[int, list[np.ndarray]] = {}
        self._multi_tracker_params: tuple | None = None

        # Frame tracking
        self._zones_configured = False
        self._last_width: int | None = None
        self._last_height: int | None = None

        log.info(
            "multi_aquarium_detector.init.success",
            plugin=self.plugin.get_name(),
        )

    # =========================================================================
    # Zone configuration
    # =========================================================================

    def set_multi_aquarium_zones(
        self,
        aquariums: list[AquariumData],
        actual_width: int,
        actual_height: int,
    ) -> None:
        """Configure zones for multiple aquariums with independent tracking.

        Sets up separate trackers (ByteTracker or SingleSubjectTracker) for
        each aquarium to enable independent tracking. Track IDs are offset
        by ``aquarium_id * 1000``.

        Args:
            aquariums: List of AquariumData objects (max 2).
            actual_width: Actual video frame width for scaling.
            actual_height: Actual video frame height for scaling.

        Raises:
            ValueError: If more than 2 aquariums or invalid dimensions.
        """
        if len(aquariums) > 2:
            raise ValueError("Maximum of 2 aquariums supported")

        if actual_width <= 0 or actual_height <= 0:
            raise ValueError(f"Invalid dimensions: width={actual_width}, height={actual_height}")

        self._multi_aquarium_mode = True
        self._aquariums = aquariums

        # Calculate scaling factors
        scale_x = actual_width / self.base_width
        scale_y = actual_height / self.base_height

        # Validate all aquarium polygons before proceeding
        for aq in aquariums:
            if not aq.polygon or len(aq.polygon) < 3:
                polygon_count = len(aq.polygon) if aq.polygon else 0
                log.error(
                    "multi_aquarium_detector.invalid_polygon",
                    aquarium_id=aq.id,
                    polygon_points=polygon_count,
                )
                raise ValueError(
                    f"Aquário {aq.id} possui polígono inválido: "
                    f"mínimo 3 pontos, encontrado {polygon_count}"
                )

        # Sync scaled polygons into ZoneScaler so delegation methods
        # (e.g. crop_aquarium_region) work correctly.
        self.zone_scaler.scale_multi_aquarium_zones(aquariums, actual_width, actual_height)

        pp = DetectionPostProcessor
        use_bytetrack = pp.should_use_bytetrack(self.settings)

        # Initialize trackers for each aquarium
        for aq in aquariums:
            if use_bytetrack:
                self._init_bytetracker_for_aquarium(aq)
            else:
                self._init_simple_tracker_for_aquarium(aq)

            # Scale the main polygon
            if aq.polygon:
                polygon_np = np.array(aq.polygon, dtype=np.float32)
                self._scaled_aquarium_polygons[aq.id] = (polygon_np * [scale_x, scale_y]).astype(
                    np.int32
                )
            else:
                self._scaled_aquarium_polygons[aq.id] = np.array([], dtype=np.int32)

            # Scale ROI polygons
            scaled_rois = []
            for roi in aq.roi_polygons:
                roi_np = np.array(roi, dtype=np.float32)
                scaled_roi = (roi_np * [scale_x, scale_y]).astype(np.int32)
                scaled_rois.append(scaled_roi)
            self._scaled_aquarium_roi_polygons[aq.id] = scaled_rois

        self._zones_configured = True
        self._last_width = actual_width
        self._last_height = actual_height

        log.info(
            "multi_aquarium_detector.zones_set",
            aquarium_count=len(aquariums),
            dimensions=(actual_width, actual_height),
            aquarium_ids=[aq.id for aq in aquariums],
            tracker_type="ByteTrack" if use_bytetrack else "Simple",
        )

    def _init_bytetracker_for_aquarium(self, aq: AquariumData) -> None:
        """Create an independent ByteTracker for one aquarium.

        Args:
            aq: The aquarium to create a tracker for.

        Raises:
            RuntimeError: If tracker creation fails.
        """
        pp = DetectionPostProcessor
        tracker_args = SimpleNamespace(
            track_thresh=pp.get_track_threshold(self.settings, self.plugin),
            match_thresh=pp.get_match_threshold(self.settings, self.plugin),
            track_buffer=pp.get_track_buffer(self.settings, self.plugin),
            mot20=False,
        )

        processing_interval = pp.get_processing_interval(self.settings)
        frame_rate = pp.get_fps(self.settings)

        try:
            self._byte_trackers_multi[aq.id] = BYTETracker(
                args=tracker_args,
                frame_rate=frame_rate,
                use_hybrid_matching=True,
                max_center_distance=pp.get_max_center_distance(self.settings),
                processing_interval=processing_interval,
                iou_threshold=pp.get_iou_threshold(self.settings),
                single_animal_mode=True,  # Each aquarium has exactly 1 animal
            )
            # Clear simple tracker if exists
            if aq.id in self._single_subject_trackers_multi:
                del self._single_subject_trackers_multi[aq.id]

        # except Exception justified: ByteTrack init — heterogeneous errors
        except Exception as e:
            log.error(
                "multi_aquarium_detector.bytetracker_init_failed",
                aquarium_id=aq.id,
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError(f"Falha ao inicializar ByteTracker para aquário {aq.id}: {e}") from e

        log.debug(
            "multi_aquarium_detector.tracker_created",
            aquarium_id=aq.id,
            type="ByteTracker",
            single_animal_mode=True,
        )

    def _init_simple_tracker_for_aquarium(self, aq: AquariumData) -> None:
        """Create a SingleSubjectTracker for one aquarium.

        Args:
            aq: The aquarium to create a tracker for.
        """
        pp = DetectionPostProcessor
        iou_thresh = pp.get_iou_threshold(self.settings)
        max_dist = pp.get_max_center_distance(self.settings)

        self._single_subject_trackers_multi[aq.id] = SingleSubjectTracker(
            track_id=1,
            iou_threshold=iou_thresh,
            max_center_distance=max_dist,
        )
        # Clear ByteTracker if exists
        if aq.id in self._byte_trackers_multi:
            del self._byte_trackers_multi[aq.id]

        log.debug(
            "multi_aquarium_detector.tracker_created",
            aquarium_id=aq.id,
            type="SingleSubjectTracker",
            iou=iou_thresh,
            dist=max_dist,
        )

    # =========================================================================
    # Tracker maintenance
    # =========================================================================

    def _ensure_multi_trackers(self) -> None:
        """Ensure multi-aquarium trackers are up to date with current settings.

        This method is exception-safe: if tracker creation fails mid-loop,
        the state remains consistent (old trackers are preserved).
        """
        pp = DetectionPostProcessor
        use_bytetrack = pp.should_use_bytetrack(self.settings)
        track_thresh = pp.get_track_threshold(self.settings, self.plugin)
        match_thresh = pp.get_match_threshold(self.settings, self.plugin)
        track_buffer = pp.get_track_buffer(self.settings, self.plugin)
        max_dist = pp.get_max_center_distance(self.settings)
        iou_thresh = pp.get_iou_threshold(self.settings)

        params = (
            use_bytetrack,
            track_thresh,
            match_thresh,
            track_buffer,
            max_dist,
            iou_thresh,
        )

        if self._multi_tracker_params == params:
            return

        log.info(
            "multi_aquarium_detector.trackers.updating",
            use_bytetrack=use_bytetrack,
        )

        # Clean up orphaned trackers
        current_aq_ids = {aq.id for aq in self._aquariums}
        for aq_id in [k for k in self._byte_trackers_multi if k not in current_aq_ids]:
            del self._byte_trackers_multi[aq_id]
        for aq_id in [k for k in self._single_subject_trackers_multi if k not in current_aq_ids]:
            del self._single_subject_trackers_multi[aq_id]

        # Create new trackers atomically
        new_byte: dict[int, BYTETracker] = {}
        new_single: dict[int, SingleSubjectTracker] = {}

        try:
            for aq in self._aquariums:
                if use_bytetrack:
                    interval = pp.get_processing_interval(self.settings)
                    fps = pp.get_fps(self.settings)
                    new_byte[aq.id] = BYTETracker(
                        args=SimpleNamespace(
                            track_thresh=track_thresh,
                            match_thresh=match_thresh,
                            track_buffer=track_buffer,
                            mot20=False,
                        ),
                        frame_rate=fps,
                        use_hybrid_matching=True,
                        max_center_distance=max_dist,
                        processing_interval=interval,
                        iou_threshold=iou_thresh,
                        single_animal_mode=True,
                    )
                else:
                    new_single[aq.id] = SingleSubjectTracker(
                        track_id=1,
                        iou_threshold=iou_thresh,
                        max_center_distance=max_dist,
                    )

            # Commit only after all succeed
            if use_bytetrack:
                self._byte_trackers_multi.update(new_byte)
                for aq_id in new_byte:
                    self._single_subject_trackers_multi.pop(aq_id, None)
            else:
                self._single_subject_trackers_multi.update(new_single)
                for aq_id in new_single:
                    self._byte_trackers_multi.pop(aq_id, None)

            self._multi_tracker_params = params

        # except Exception justified: YOLO inference — heterogeneous ML errors
        except Exception as e:
            new_byte.clear()
            new_single.clear()
            log.error(
                "multi_aquarium_detector.trackers.creation_failed",
                error=str(e),
                aquariums=[aq.id for aq in self._aquariums],
            )
            raise

    # =========================================================================
    # Detection — full-frame partitioned
    # =========================================================================

    def detect_partitioned(
        self,
        frame: np.ndarray,
        project_type: str = "multi_aquarium",
    ) -> dict[int, list[tuple]]:
        """Execute detection and partition results by aquarium.

        Runs detection on the full frame, then assigns detections to
        aquariums based on centroid location. Each aquarium has independent
        tracking with offset track IDs.

        Args:
            frame: Input BGR frame.
            project_type: Project type string (API compatibility).

        Returns:
            Dictionary mapping aquarium_id to list of detection tuples.
            Track IDs are offset: ``aquarium_id * 1000 + local_track_id``.

        Raises:
            RuntimeError: If detector not in multi-aquarium mode.
            ValueError: If frame is invalid.
        """
        if not self._multi_aquarium_mode:
            raise RuntimeError(
                "Detector is not in multi-aquarium mode. Call set_multi_aquarium_zones() first."
            )

        self._ensure_multi_trackers()
        DetectionPostProcessor.validate_frame(frame)

        # Execute detection on full frame
        raw_detections = self.plugin.detect(frame)

        log.info(
            "multi_aquarium_detector.raw_detections",
            count=len(raw_detections),
            detections=str([str(d) for d in raw_detections[:3]]),
        )

        # Partition detections by aquarium
        partitioned: dict[int, list] = {aq.id: [] for aq in self._aquariums}

        for raw_det in raw_detections:
            det = DetectionPostProcessor.ensure_track_tuple(raw_det)
            x1, y1, x2, y2, conf, _, class_id = det
            centroid = ((x1 + x2) / 2, (y1 + y2) / 2)

            for aq in self._aquariums:
                polygon = self._scaled_aquarium_polygons.get(aq.id)
                if polygon is not None and polygon.size > 0:
                    if ZoneScaler.point_in_polygon(centroid, polygon):
                        partitioned[aq.id].append(det)
                        break
            else:
                log.warning(
                    "multi_aquarium_detector.detection_unassigned",
                    centroid=centroid,
                    confidence=conf,
                    aquariums_checked=len(self._aquariums),
                )

        partition_counts = {aqid: len(dets) for aqid, dets in partitioned.items()}
        log.info("multi_aquarium_detector.partitioning", counts=partition_counts)

        # Apply independent tracking per aquarium
        return self._track_partitioned(partitioned)

    # =========================================================================
    # Detection — optimized with per-aquarium cropping
    # =========================================================================

    def detect_partitioned_optimized(
        self,
        frame: np.ndarray,
        use_cropping: bool = True,
    ) -> dict[int, list[tuple]]:
        """Execute optimized detection with per-aquarium cropping.

        Crops each aquarium region before running inference, reducing
        the number of pixels processed by ~50% for dual-aquarium setups.

        Args:
            frame: Input BGR frame.
            use_cropping: If True, crop each aquarium before inference.
                         If False, falls back to full-frame detection.

        Returns:
            Dictionary mapping aquarium_id to list of detection tuples.

        Raises:
            RuntimeError: If detector not in multi-aquarium mode.
            ValueError: If frame is invalid.
        """
        if not self._multi_aquarium_mode:
            raise RuntimeError(
                "Detector is not in multi-aquarium mode. Call set_multi_aquarium_zones() first."
            )

        self._ensure_multi_trackers()
        DetectionPostProcessor.validate_frame(frame)

        if not use_cropping:
            return self.detect_partitioned(frame)

        # Process each aquarium with cropped regions
        partitioned: dict[int, list] = {}
        for aq in self._aquariums:
            cropped, (offset_x, offset_y, _w, _h) = self.zone_scaler.crop_aquarium_region(
                frame,
                aq.id,
                padding=10,
            )

            raw_detections = self.plugin.detect(cropped)

            log.debug(
                "multi_aquarium_detector.optimized.raw_crop",
                aquarium_id=aq.id,
                count=len(raw_detections),
            )

            adjusted: list[tuple] = []
            for raw_det in raw_detections:
                det = DetectionPostProcessor.ensure_track_tuple(raw_det)
                x1, y1, x2, y2, conf, _, class_id = det

                x1_g = x1 + offset_x
                y1_g = y1 + offset_y
                x2_g = x2 + offset_x
                y2_g = y2 + offset_y

                # Filter: class ID
                if self.animal_class_id is not None and class_id != self.animal_class_id:
                    continue

                # Filter: centroid within polygon (padding may capture outside)
                centroid = ((x1_g + x2_g) / 2, (y1_g + y2_g) / 2)
                polygon = self._scaled_aquarium_polygons.get(aq.id)
                if polygon is not None and polygon.size > 0:
                    if not ZoneScaler.point_in_polygon(centroid, polygon):
                        continue

                adjusted.append((x1_g, y1_g, x2_g, y2_g, conf, None, class_id))

            partitioned[aq.id] = adjusted

        return self._track_partitioned(partitioned)

    # =========================================================================
    # Detection — parallel
    # =========================================================================

    def detect_partitioned_parallel(
        self,
        frame: np.ndarray,
        max_workers: int = 2,
    ) -> dict[int, list[tuple]]:
        """Execute parallel detection for multi-aquarium mode.

        Uses ThreadPoolExecutor to process aquariums in parallel,
        providing ~30-40% speedup on multi-core systems.

        Note: Due to Python's GIL, actual parallel execution depends on the
        detection plugin releasing the GIL (e.g., during C++/CUDA operations).

        Args:
            frame: Input BGR frame.
            max_workers: Maximum number of parallel workers (default: 2).

        Returns:
            Dictionary mapping aquarium_id to list of detection tuples.

        Raises:
            RuntimeError: If detector not in multi-aquarium mode.
        """
        if not self._multi_aquarium_mode:
            raise RuntimeError(
                "Detector is not in multi-aquarium mode. Call set_multi_aquarium_zones() first."
            )

        if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
            raise ValueError("Frame must be a valid non-empty numpy array")

        results: dict[int, list[tuple]] = {}
        errors: dict[int, str] = {}

        def process_aquarium(
            aq_id: int,
        ) -> tuple[int, list[tuple], str | None]:
            """Process a single aquarium region with error recovery."""
            try:
                aq = next((a for a in self._aquariums if a.id == aq_id), None)
                if aq is None:
                    return (
                        aq_id,
                        [],
                        f"Aquarium {aq_id} not found in configuration",
                    )

                cropped, (offset_x, offset_y, _, _) = self.zone_scaler.crop_aquarium_region(
                    frame,
                    aq_id,
                    padding=10,
                )

                if cropped is None or cropped.size == 0:
                    return aq_id, [], f"Aquarium {aq_id}: Empty crop region"

                raw_detections = self.plugin.detect(cropped)

                adjusted = []
                polygon = self._scaled_aquarium_polygons.get(aq_id)

                for raw_det in raw_detections:
                    det = DetectionPostProcessor.ensure_track_tuple(raw_det)
                    x1_f, y1_f, x2_f, y2_f, conf, _, class_id = det
                    x1 = int(x1_f) + offset_x
                    y1 = int(y1_f) + offset_y
                    x2 = int(x2_f) + offset_x
                    y2 = int(y2_f) + offset_y

                    if self.animal_class_id is not None and class_id != self.animal_class_id:
                        continue

                    centroid = ((x1 + x2) / 2, (y1 + y2) / 2)
                    if polygon is not None and polygon.size > 0:
                        if not ZoneScaler.point_in_polygon(centroid, polygon):
                            continue

                    adjusted.append((x1, y1, x2, y2, conf, None, class_id))

                return aq_id, adjusted, None
            # except Exception justified: zone/ROI — heterogeneous geometry errors
            except Exception as e:
                log.warning(
                    "multi_aquarium_detector.parallel.aquarium_error",
                    aquarium_id=aq_id,
                    error=str(e),
                )
                return aq_id, [], f"Aquarium {aq_id}: {e!s}"

        start_time = time.perf_counter()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_aquarium, aq.id): aq.id for aq in self._aquariums}
            for future in as_completed(futures):
                try:
                    aq_id, detections, error_msg = future.result()

                    if error_msg:
                        errors[aq_id] = error_msg
                        results[aq_id] = []
                        continue

                    # Tracking must be sequential (ByteTracker is not thread-safe)
                    if detections:
                        tracker = self._byte_trackers_multi.get(aq_id)
                        if tracker is None:
                            log.error(
                                "multi_aquarium_detector.parallel.tracker_missing",
                                aquarium_id=aq_id,
                            )
                            errors[aq_id] = f"ByteTracker não inicializado para aquário {aq_id}"
                            results[aq_id] = []
                            continue

                        tracked = self._apply_byte_tracking_multi(detections, tracker)
                        results[aq_id] = self._offset_track_ids(tracked, aq_id)
                    else:
                        results[aq_id] = []
                # except Exception justified: zone/ROI — heterogeneous errors
                except Exception as e:
                    aq_id = futures[future]
                    log.error(
                        "multi_aquarium_detector.parallel.future_error",
                        aquarium_id=aq_id,
                        error=str(e),
                    )
                    errors[aq_id] = f"Executor error: {e!s}"
                    results[aq_id] = []

        elapsed = time.perf_counter() - start_time
        log.debug(
            "multi_aquarium_detector.parallel.complete",
            elapsed_ms=round(elapsed * 1000, 2),
            aquarium_counts={aq_id: len(dets) for aq_id, dets in results.items()},
            errors=errors if errors else None,
        )

        return results

    # =========================================================================
    # Shared tracking helpers
    # =========================================================================

    def _track_partitioned(self, partitioned: dict[int, list]) -> dict[int, list[tuple]]:
        """Apply independent tracking per aquarium and offset track IDs.

        Args:
            partitioned: Raw detections partitioned by aquarium_id.

        Returns:
            Dictionary of tracked detections with offset IDs.
        """
        pp = DetectionPostProcessor
        use_bytetrack = pp.should_use_bytetrack(self.settings)
        results: dict[int, list[tuple]] = {}

        for aq_id, detections in partitioned.items():
            if detections:
                if use_bytetrack:
                    tracker = self._byte_trackers_multi.get(aq_id)
                    if tracker is None:
                        log.error(
                            "multi_aquarium_detector.tracker_missing",
                            aquarium_id=aq_id,
                            available=list(self._byte_trackers_multi.keys()),
                        )
                        raise RuntimeError(
                            f"ByteTracker não inicializado para aquário {aq_id}. "
                            "Chame set_multi_aquarium_zones() primeiro."
                        )
                    tracked = self._apply_byte_tracking_multi(detections, tracker)
                else:
                    simple = self._single_subject_trackers_multi.get(aq_id)
                    if simple is None:
                        log.error(
                            "multi_aquarium_detector.simple_tracker_missing",
                            aq_id=aq_id,
                        )
                        tracked = detections
                    else:
                        tracked = self._apply_simple_tracking_multi(detections, simple)

                results[aq_id] = self._offset_track_ids(tracked, aq_id)
            else:
                results[aq_id] = []

        log.debug(
            "multi_aquarium_detector.tracked_results",
            aquarium_counts={aq_id: len(dets) for aq_id, dets in results.items()},
        )
        return results

    @staticmethod
    def _offset_track_ids(tracked: list[tuple], aq_id: int) -> list[tuple]:
        """Apply ``aquarium_id * 1000 + local_track_id`` offset.

        Args:
            tracked: Detection tuples with local track IDs.
            aq_id: Aquarium ID for offset.

        Returns:
            Detections with globally-unique track IDs.
        """
        offset_tracked = []
        for det in tracked:
            x1, y1, x2, y2, conf, track_id, class_id = det
            if track_id is not None:
                if track_id >= 1000:
                    log.error(
                        "multi_aquarium_detector.track_id_overflow",
                        aquarium_id=aq_id,
                        local_track_id=track_id,
                        msg="local_track_id >= 1000 causa colisão de IDs",
                    )
                    offset_id = aq_id * 1000 + (track_id % 1000)
                else:
                    offset_id = aq_id * 1000 + track_id
            else:
                offset_id = None
            offset_tracked.append((x1, y1, x2, y2, conf, offset_id, class_id))
        return offset_tracked

    def _apply_byte_tracking_multi(
        self,
        detections: list[tuple],
        tracker: BYTETracker,
    ) -> list[tuple]:
        """Apply ByteTracker to detections for one aquarium.

        Args:
            detections: List of detection tuples.
            tracker: ByteTracker instance for this aquarium.

        Returns:
            List of detections with updated track_ids.
        """
        if not detections:
            return []

        det_array = np.array([[d[0], d[1], d[2], d[3], d[4]] for d in detections])

        online_targets = tracker.update(
            det_array,
            [self._last_height or 720, self._last_width or 1280],
            [self._last_height or 720, self._last_width or 1280],
        )

        tracked = []
        for track in online_targets:
            tlbr = track.tlbr
            x1, y1, x2, y2 = (
                int(tlbr[0]),
                int(tlbr[1]),
                int(tlbr[2]),
                int(tlbr[3]),
            )
            track_id = track.track_id
            conf = track.score

            # Find original class_id from closest detection
            class_id = self.animal_class_id
            for det in detections:
                if abs(det[0] - x1) < 10 and abs(det[1] - y1) < 10:
                    class_id = det[6]
                    break

            tracked.append((x1, y1, x2, y2, conf, track_id, class_id))

        return tracked

    @staticmethod
    def _apply_simple_tracking_multi(
        detections: list[tuple],
        tracker: SingleSubjectTracker,
    ) -> list[tuple]:
        """Apply SingleSubjectTracker for one aquarium.

        Args:
            detections: Detection tuples.
            tracker: The SingleSubjectTracker for this aquarium.

        Returns:
            Tracked detection tuples (usually 1 item).
        """
        if not detections:
            tracker.reset()
            return []
        return tracker.assign(detections)

    # =========================================================================
    # Tracking reset
    # =========================================================================

    def reset_multi_aquarium_tracking(
        self,
        aquarium_id: int | None = None,
    ) -> None:
        """Reset tracking state for one or all aquariums.

        Args:
            aquarium_id: Specific aquarium to reset, or None for all.
        """
        pp = DetectionPostProcessor
        tracker_args = SimpleNamespace(
            track_thresh=pp.get_track_threshold(self.settings, self.plugin),
            match_thresh=pp.get_match_threshold(self.settings, self.plugin),
            track_buffer=pp.get_track_buffer(self.settings, self.plugin),
            mot20=False,
        )
        processing_interval = pp.get_processing_interval(self.settings)
        frame_rate = pp.get_fps(self.settings)

        if aquarium_id is not None:
            if aquarium_id in self._byte_trackers_multi:
                self._byte_trackers_multi[aquarium_id] = BYTETracker(
                    args=tracker_args,
                    frame_rate=frame_rate,
                    use_hybrid_matching=True,
                    max_center_distance=pp.get_max_center_distance(self.settings),
                    processing_interval=processing_interval,
                    iou_threshold=pp.get_iou_threshold(self.settings),
                    single_animal_mode=True,
                )
                log.debug(
                    "multi_aquarium_detector.tracking_reset",
                    aquarium_id=aquarium_id,
                )
        else:
            for aq_id in list(self._byte_trackers_multi.keys()):
                self._byte_trackers_multi[aq_id] = BYTETracker(
                    args=tracker_args,
                    frame_rate=frame_rate,
                    use_hybrid_matching=True,
                    max_center_distance=pp.get_max_center_distance(self.settings),
                    processing_interval=processing_interval,
                    iou_threshold=pp.get_iou_threshold(self.settings),
                    single_animal_mode=True,
                )
            log.debug(
                "multi_aquarium_detector.tracking_reset_all",
                aquarium_count=len(self._byte_trackers_multi),
            )

    # =========================================================================
    # Overlay drawing
    # =========================================================================

    def draw_multi_aquarium_overlay(
        self,
        frame: np.ndarray,
        partitioned_detections: dict[int, list[tuple]],
    ) -> np.ndarray:
        """Draw detection overlays for multi-aquarium mode.

        Draws each aquarium's polygon and ROIs with distinct colors,
        plus detection bounding boxes.

        Args:
            frame: Input BGR frame (modified in-place).
            partitioned_detections: Detection results from detect_partitioned().

        Returns:
            Frame with overlays drawn.
        """
        aquarium_colors = {
            0: (0, 255, 0),  # Green for aquarium 0 (left)
            1: (255, 165, 0),  # Orange for aquarium 1 (right)
        }

        for aq in self._aquariums:
            aq_color = aquarium_colors.get(aq.id, (255, 255, 255))

            # Draw aquarium polygon
            polygon = self._scaled_aquarium_polygons.get(aq.id)
            if polygon is not None and polygon.size > 0:
                cv2.polylines(
                    frame,
                    [polygon],
                    isClosed=True,
                    color=aq_color,
                    thickness=2,
                )

                if polygon.size > 0:
                    x, y = polygon[0]
                    label = f"Aquario {aq.id + 1}"
                    if aq.group:
                        label += f" ({aq.group})"
                    cv2.putText(
                        frame,
                        label,
                        (int(x), int(y) - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        aq_color,
                        2,
                    )

            # Draw ROI polygons
            roi_polygons = self._scaled_aquarium_roi_polygons.get(aq.id, [])
            for i, roi_polygon in enumerate(roi_polygons):
                roi_color = aq.roi_colors[i] if i < len(aq.roi_colors) else aq_color
                cv2.polylines(
                    frame,
                    [roi_polygon],
                    isClosed=True,
                    color=roi_color,
                    thickness=1,
                )

            # Draw detections for this aquarium
            detections = partitioned_detections.get(aq.id, [])
            for det in detections:
                if len(det) >= 6:
                    x1, y1, x2, y2, conf, track_id = det[:6]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), aq_color, 2)
                    label = f"ID:{track_id}" if track_id else f"{conf:.0%}"
                    cv2.putText(
                        frame,
                        label,
                        (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        aq_color,
                        1,
                    )

        return frame

    # =========================================================================
    # Data accessors
    # =========================================================================

    def is_multi_aquarium_mode(self) -> bool:
        """Check if detector is in multi-aquarium mode."""
        return self._multi_aquarium_mode

    def get_aquarium_polygon(self, aquarium_id: int) -> np.ndarray | None:
        """Get scaled polygon for a specific aquarium."""
        return self._scaled_aquarium_polygons.get(aquarium_id)

    def get_aquarium_roi_polygons(self, aquarium_id: int) -> list[np.ndarray]:
        """Get scaled ROI polygons for a specific aquarium."""
        return self._scaled_aquarium_roi_polygons.get(aquarium_id, [])

    def get_multi_aquarium_data(self) -> list[AquariumData]:
        """Get the configured aquarium data."""
        return self._aquariums

    def get_multi_aquarium_zone_data(self) -> MultiAquariumZoneData:
        """Build ``MultiAquariumZoneData`` from current configuration."""
        return MultiAquariumZoneData(
            aquariums=self._aquariums,
            video_width=self._last_width or self.base_width,
            video_height=self._last_height or self.base_height,
        )

    def get_zone_data(self) -> ZoneData:
        """Helper for backward compat: returns first aquarium as ZoneData."""
        if self._aquariums:
            return self._aquariums[0].to_zone_data()
        return ZoneData()

    # =========================================================================
    # Backward-compat delegation helpers
    # =========================================================================

    def _point_in_polygon(self, point: tuple[float, float], polygon: np.ndarray) -> bool:
        """Delegate to ``ZoneScaler.point_in_polygon`` (backward compat)."""
        return ZoneScaler.point_in_polygon(point, polygon)

    def _crop_aquarium_region(
        self,
        frame: np.ndarray,
        aquarium_id: int,
        padding: int = 10,
    ) -> tuple[np.ndarray, tuple[int, int, int, int]]:
        """Delegate to ``zone_scaler.crop_aquarium_region`` (backward compat)."""
        return self.zone_scaler.crop_aquarium_region(frame, aquarium_id, padding)
