"""Detection post-processing utilities for zebrafish tracking.

Stateless utility functions for frame validation, detection tuple normalization,
coordinate offset, IoU calculation, class ID resolution, and settings extraction.
Used by both SingleDetector and MultiAquariumDetector.
"""

from typing import TYPE_CHECKING, Any

import cv2
import numpy as np
import structlog

from zebtrack.core.detection.class_aliases import ClassAliases
from zebtrack.core.detection.class_aliases import resolve_class_ids as _resolve_by_name
from zebtrack.core.detection.class_roles import ClassRole, ClassRoleMap
from zebtrack.settings import (
    DEFAULT_IOU_THRESHOLD,
    DEFAULT_MATCH_THRESHOLD,
    DEFAULT_MAX_CENTER_DISTANCE,
    DEFAULT_TRACK_BUFFER,
    DEFAULT_TRACK_THRESHOLD,
)

if TYPE_CHECKING:
    from zebtrack.plugins.base import DetectorPlugin
    from zebtrack.settings import Settings

#: ``model_selection.context_inference_scope`` values (ADR-009).
CONTEXT_SCOPES = ("arena_crop", "arena_crop_margin", "full_frame")
_DEFAULT_CONTEXT_SCOPE = "arena_crop_margin"
_DEFAULT_CONTEXT_MARGIN = 0.15

log = structlog.get_logger()

__all__ = ["DetectionPostProcessor"]


class DetectionPostProcessor:
    """Stateless post-processing utilities for detection pipeline.

    All methods are static — no instance state is needed. This class groups
    related utilities for frame validation, tuple normalization, coordinate
    adjustment, IoU math, class ID resolution, and settings extraction.
    """

    @staticmethod
    def validate_frame(frame: np.ndarray) -> None:
        """Validate that a frame is a valid BGR numpy array.

        Args:
            frame: Input frame to validate.

        Raises:
            ValueError: If frame is None, empty, or not HxWx3.
        """
        if frame is None or not isinstance(frame, np.ndarray):
            raise ValueError("Frame must be a valid numpy array")
        if frame.size == 0:
            raise ValueError("Frame cannot be empty")
        if len(frame.shape) != 3 or frame.shape[2] != 3:
            raise ValueError(f"Frame must be HxWx3, got {frame.shape}")

    @staticmethod
    def ensure_track_tuple(
        detection: tuple,
    ) -> tuple[float, float, float, float, float, int | None, int]:
        """Normalize a detection tuple to 7-element format.

        Handles 5-element (no track_id, no class_id), 6-element (no class_id),
        and 7+ element detection tuples.

        Args:
            detection: Detection tuple of varying length.

        Returns:
            Normalized 7-element tuple: (x1, y1, x2, y2, confidence, track_id, class_id).
        """
        if len(detection) == 5:
            x1, y1, x2, y2, confidence = detection
            track_id = None
            class_id = 0  # Default class if not provided
        elif len(detection) == 6:
            x1, y1, x2, y2, confidence, track_id = detection
            class_id = 0  # Default class if not provided
        else:
            x1, y1, x2, y2, confidence, track_id, class_id = detection[:7]
        return (
            float(x1),
            float(y1),
            float(x2),
            float(y2),
            float(confidence),
            track_id,
            int(class_id),
        )

    @staticmethod
    def offset_detections(
        raw_detections: list,
        dx: int,
        dy: int,
    ) -> list[tuple[float, float, float, float, float, int, int]]:
        """Offset detection coordinates by (dx, dy).

        Used after cropping a frame sub-region to adjust coordinates
        back to the full frame coordinate system.

        Args:
            raw_detections: List of raw detection tuples.
            dx: Horizontal offset.
            dy: Vertical offset.

        Returns:
            List of offset detection tuples in 7-element format.
        """
        preds: list[tuple[float, float, float, float, float, int, int]] = []
        for det in raw_detections:
            x1_c, y1_c, x2_c, y2_c, conf, tid, cid = DetectionPostProcessor.ensure_track_tuple(det)
            preds.append(
                (
                    float(x1_c + dx),
                    float(y1_c + dy),
                    float(x2_c + dx),
                    float(y2_c + dy),
                    float(conf),
                    int(tid) if tid is not None else -1,
                    int(cid),
                )
            )
        return preds

    @staticmethod
    def calculate_iou(
        x1_a: float,
        y1_a: float,
        x2_a: float,
        y2_a: float,
        x1_b: float,
        y1_b: float,
        x2_b: float,
        y2_b: float,
    ) -> float:
        """Calculate Intersection over Union (IoU) between two bounding boxes.

        Args:
            x1_a: Left x of box A.
            y1_a: Top y of box A.
            x2_a: Right x of box A.
            y2_a: Bottom y of box A.
            x1_b: Left x of box B.
            y1_b: Top y of box B.
            x2_b: Right x of box B.
            y2_b: Bottom y of box B.

        Returns:
            IoU value between 0.0 and 1.0.
        """
        # Calculate intersection
        inter_x1 = max(x1_a, x1_b)
        inter_y1 = max(y1_a, y1_b)
        inter_x2 = min(x2_a, x2_b)
        inter_y2 = min(y2_a, y2_b)

        if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
            return 0.0

        inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)

        # Calculate union
        area_a = (x2_a - x1_a) * (y2_a - y1_a)
        area_b = (x2_b - x1_b) * (y2_b - y1_b)
        union_area = area_a + area_b - inter_area

        if union_area <= 0:
            return 0.0

        return inter_area / union_area

    @staticmethod
    def apply_class_mismatch_fallback(
        detections: list[tuple],
        scaled_polygon: np.ndarray,
        aquarium_class_id: int | None,
        animal_class_id: int | None,
    ) -> list[tuple]:
        """Convert small aquarium-class detections into animal-class detections.

        When the model detects an object as "aquarium" but it's small relative
        to the arena, it's likely actually a fish. This corrects the class ID.

        Args:
            detections: List of detection tuples.
            scaled_polygon: Scaled arena polygon for area comparison.
            aquarium_class_id: Class ID for aquarium detections.
            animal_class_id: Class ID for animal detections.

        Returns:
            List of detections with corrected class IDs.
        """
        if (
            not detections
            or scaled_polygon.size == 0
            or aquarium_class_id is None
            or animal_class_id is None
        ):
            return detections

        arena_area = cv2.contourArea(scaled_polygon)
        if arena_area <= 0:
            return detections

        adjusted: list[tuple] = []
        for det in detections:
            x1, y1, x2, y2, conf, track_id, class_id = det
            if class_id == aquarium_class_id:
                det_area = max(0.0, float(x2 - x1)) * max(0.0, float(y2 - y1))
                if det_area / arena_area < 0.5:
                    class_id = animal_class_id
            adjusted.append((x1, y1, x2, y2, conf, track_id, class_id))

        return adjusted

    @staticmethod
    def validate_track_continuity(detections: list[tuple]) -> None:
        """Validate track_id continuity and log warnings for gaps.

        Detects missing track IDs which may indicate tracking issues
        or object loss. This helps identify potential problems with ByteTracker.

        Args:
            detections: List of (x1, y1, x2, y2, confidence, track_id, class_id) tuples.
        """
        if not detections:
            return

        # Extract track_ids, filtering out None values
        track_ids = [d[5] for d in detections if d[5] is not None]

        if not track_ids:
            return  # No valid track_ids to validate

        # Check for gaps in track_id sequence
        min_id, max_id = min(track_ids), max(track_ids)
        expected_ids = set(range(min_id, max_id + 1))
        actual_ids = set(track_ids)
        missing_ids = expected_ids - actual_ids

        if missing_ids:
            log.warning(
                "post_processor.track_id_gaps_detected",
                missing_track_ids=sorted(missing_ids),
                present_track_ids=sorted(actual_ids),
                total_detections=len(detections),
                message=(
                    "Gaps in track_id sequence detected. This may indicate: "
                    "(1) Objects temporarily lost by tracker, "
                    "(2) Objects left the frame, or "
                    "(3) ByteTracker configuration issues."
                ),
            )

        # Additional validation: Check for duplicate track_ids
        if len(track_ids) != len(actual_ids):
            duplicate_ids = [tid for tid in actual_ids if track_ids.count(tid) > 1]
            log.error(
                "post_processor.duplicate_track_ids",
                duplicate_track_ids=duplicate_ids,
                total_detections=len(detections),
                message="Multiple detections with same track_id in single frame!",
            )

    @staticmethod
    def resolve_class_ids(
        plugin: "DetectorPlugin",
        aliases: ClassAliases | None = None,
    ) -> tuple[int, int]:
        """Resolve class IDs from plugin metadata, by class NAME.

        Delegates to :func:`zebtrack.core.detection.class_aliases.resolve_class_ids`,
        the single place that knows which names mean "arena" and which mean
        "animal" — for zebrafish, rodents or any name added through
        ``model_selection.class_aliases``. Without names the legacy ``(0, 1)``
        is returned unchanged.

        Args:
            plugin: Detector plugin instance with class_names attribute.
            aliases: Role vocabularies; built-in ones when ``None``.

        Returns:
            Tuple of (aquarium_class_id, animal_class_id).
        """
        class_names = getattr(plugin, "class_names", None)
        return _resolve_by_name(class_names, aliases).as_tuple()

    # =========================================================================
    # Class roles: context crop, per-role confidence, class observations
    # =========================================================================

    @staticmethod
    def context_settings(settings: Any) -> tuple[str, float, float | None]:
        """``(scope, margin_frac, context_min_confidence)`` read defensively.

        Stubs and ``MagicMock`` settings answer every attribute, so each value is
        type-checked; anything unusable falls back to the ADR-009 default.
        """
        section = getattr(settings, "model_selection", None)
        scope = getattr(section, "context_inference_scope", _DEFAULT_CONTEXT_SCOPE)
        if scope not in CONTEXT_SCOPES:
            scope = _DEFAULT_CONTEXT_SCOPE
        margin = getattr(section, "context_crop_margin_frac", _DEFAULT_CONTEXT_MARGIN)
        if not isinstance(margin, int | float) or isinstance(margin, bool) or not 0 <= margin <= 1:
            margin = _DEFAULT_CONTEXT_MARGIN
        floor = getattr(section, "context_min_confidence", None)
        if not isinstance(floor, int | float) or isinstance(floor, bool) or not 0 < floor < 1:
            floor = None
        return str(scope), float(margin), None if floor is None else float(floor)

    @staticmethod
    def context_crop_box(
        polygon: np.ndarray,
        frame_shape: tuple[int, ...],
        *,
        scope: str,
        margin_frac: float,
        padding: int = 0,
    ) -> tuple[int, int, int, int] | None:
        """Inference rectangle ``(x1, y1, x2, y2)`` when the map has context classes.

        The experimenter and the start box live AROUND the arena, so the plain
        arena crop never shows them. ``arena_crop_margin`` widens the arena
        bounding box by ``margin_frac`` of its own size on every side (never by
        less than the detector's legacy ``padding``); ``full_frame`` uses the
        whole frame; ``arena_crop`` keeps the legacy rectangle.

        Args:
            polygon: Scaled arena polygon.
            frame_shape: ``frame.shape``.
            scope: One of :data:`CONTEXT_SCOPES`.
            margin_frac: Fraction of the arena box added per side.
            padding: The detector's legacy padding in pixels.

        Returns:
            The clamped rectangle, or ``None`` when it is empty.
        """
        img_h, img_w = int(frame_shape[0]), int(frame_shape[1])
        if scope == "full_frame" or polygon.size == 0:
            return 0, 0, img_w, img_h
        x, y, w, h = cv2.boundingRect(polygon)
        pad_x = pad_y = padding
        if scope == "arena_crop_margin":
            pad_x = max(padding, round(w * margin_frac))
            pad_y = max(padding, round(h * margin_frac))
        x1, y1 = max(0, x - pad_x), max(0, y - pad_y)
        x2, y2 = min(img_w, x + w + pad_x), min(img_h, y + h + pad_y)
        if x2 <= x1 or y2 <= y1:
            return None
        return x1, y1, x2, y2

    @staticmethod
    def role_confidence_floors(
        subject_floor: float,
        context_floor: float | None,
    ) -> tuple[float, float, float]:
        """``(inference_floor, subject_floor, context_floor)`` for a context map.

        The plugin must infer with the LOWER of the two floors -- otherwise a
        context class with a permissive floor is cut by the subject's -- and the
        per-role floors are re-applied afterwards by
        :meth:`filter_by_role_confidence`. ``context_floor`` ``None`` means the
        subject floor (``resolve_animal_confidence``).
        """
        ctx = subject_floor if context_floor is None else context_floor
        return min(subject_floor, ctx), subject_floor, ctx

    @staticmethod
    def filter_by_role_confidence(
        detections: list[tuple],
        role_map: ClassRoleMap,
        subject_floor: float,
        context_floor: float,
    ) -> list[tuple]:
        """Drop detections below the floor of THEIR role.

        Context classes answer to ``context_floor``; every other class keeps
        the subject floor it always had, so lowering the inference floor for
        context never lets a weak subject (or arena) box through.
        """
        kept: list[tuple] = []
        for det in detections:
            floor = context_floor if int(det[6]) in role_map.context_ids else subject_floor
            if float(det[4]) >= floor:
                kept.append(det)
        return kept

    @staticmethod
    def class_observations(
        detections: list[tuple],
        role_map: ClassRoleMap,
        aquarium_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Subject and context detections of one frame, as plain records.

        Captured right after the crop offset -- before the polygon filter and
        the tracker -- because a context object (the experimenter's hand, the
        start box) is exactly what the subject pipeline throws away.

        Returns:
            ``[{"class_id", "class_name", "role", "bbox", "confidence",
            "aquarium_id"}]`` with ``bbox`` in full-frame pixels.
        """
        observed: list[dict[str, Any]] = []
        for det in detections:
            class_id = int(det[6])
            role = role_map.role_of_id(class_id)
            if role not in (ClassRole.SUBJECT, ClassRole.CONTEXT):
                continue
            observed.append(
                {
                    "class_id": class_id,
                    "class_name": role_map.class_name_of(class_id),
                    "role": role.value,
                    "bbox": (float(det[0]), float(det[1]), float(det[2]), float(det[3])),
                    "confidence": float(det[4]),
                    "aquarium_id": aquarium_id,
                }
            )
        return observed

    # =========================================================================
    # Settings resolution helpers
    # =========================================================================

    @staticmethod
    def _configured_threshold(
        name: str,
        settings: "Settings | None",
        plugin: "DetectorPlugin | None",
        default: float,
    ) -> float:
        """Resolve one ByteTrack threshold: settings > plugin attribute > ``default``.

        The settings are what the UI, the project overrides (``DetectorService``)
        and ``config.yaml`` write, so they win; the plugin's copy is only a
        fallback for a caller with no settings. An unusable value logs and falls
        through to the next source instead of short-circuiting to the default.
        """
        for source in (getattr(settings, "bytetrack", None), plugin):
            value = getattr(source, name, None) if source is not None else None
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                log.warning(f"detection_post_processor.{name}.invalid", value=repr(value))
        return default

    @staticmethod
    def get_track_threshold(settings: "Settings | None", plugin: "DetectorPlugin | None") -> float:
        """Resolve ByteTrack's track threshold.

        Precedence (#698): ``settings.bytetrack.track_threshold`` > a
        ``track_threshold`` attribute on the plugin > ``DEFAULT_TRACK_THRESHOLD``.
        Both plugins copy the settings when they are built; until #698 that copy
        came first, so a value written afterwards (panel, project restore,
        factory reset) never reached the tracker.

        Args:
            settings: Application settings (optional).
            plugin: Detector plugin (optional).

        Returns:
            Track threshold value.
        """
        return DetectionPostProcessor._configured_threshold(
            "track_threshold", settings, plugin, DEFAULT_TRACK_THRESHOLD
        )

    @staticmethod
    def get_match_threshold(settings: "Settings | None", plugin: "DetectorPlugin | None") -> float:
        """Resolve ByteTrack's match threshold (same precedence as the track threshold, #698).

        Args:
            settings: Application settings (optional).
            plugin: Detector plugin (optional).

        Returns:
            Match threshold value.
        """
        return DetectionPostProcessor._configured_threshold(
            "match_threshold", settings, plugin, DEFAULT_MATCH_THRESHOLD
        )

    @staticmethod
    def get_track_buffer(settings: "Settings | None", plugin: "DetectorPlugin | None") -> int:
        """Resolve ByteTrack's lost-track buffer (frames at the 30 fps reference).

        Precedence (#666): ``settings.bytetrack.track_buffer`` > a ``track_buffer``
        attribute on the plugin > ``DEFAULT_TRACK_BUFFER``. The settings are what
        the UI, the project overrides (``DetectorService``) and ``config.yaml``
        write, so they must win; the plugin is only a fallback for a caller with
        no settings. Until #666 the plugin came first, and both production plugins
        pinned 60, so every lost track lived 2 s whatever had been configured.

        Args:
            settings: Application settings (optional).
            plugin: Detector plugin (optional).

        Returns:
            Track buffer size in frames at 30 fps.
        """
        for source in (getattr(settings, "bytetrack", None), plugin):
            value = getattr(source, "track_buffer", None) if source is not None else None
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                log.warning("detection_post_processor.track_buffer.invalid", value=repr(value))
        return DEFAULT_TRACK_BUFFER

    @staticmethod
    def get_max_center_distance(settings: "Settings | None") -> float:
        """Get max center distance for hybrid matching.

        This parameter controls how far (in pixels) a detection can be from
        the predicted track position and still be considered a match.

        Args:
            settings: Application settings (optional).

        Returns:
            Max center distance in pixels (``DEFAULT_MAX_CENTER_DISTANCE`` without settings).
        """
        if settings and hasattr(settings, "bytetrack"):
            return float(
                getattr(settings.bytetrack, "max_center_distance", DEFAULT_MAX_CENTER_DISTANCE)
            )
        return DEFAULT_MAX_CENTER_DISTANCE

    @staticmethod
    def get_iou_threshold(settings: "Settings | None") -> float:
        """Get IoU threshold for hybrid matching.

        Lower values make the tracker prefer center distance over IoU,
        which is better for small, fast-moving objects.

        Args:
            settings: Application settings (optional).

        Returns:
            IoU threshold (``DEFAULT_IOU_THRESHOLD`` without settings).
        """
        if settings and hasattr(settings, "bytetrack"):
            return float(getattr(settings.bytetrack, "iou_threshold", DEFAULT_IOU_THRESHOLD))
        return DEFAULT_IOU_THRESHOLD

    @staticmethod
    def should_use_bytetrack(settings: "Settings | None") -> bool:
        """Check if ByteTrack should be used based on settings.

        Args:
            settings: Application settings (optional).

        Returns:
            True if ByteTrack is enabled (default: True).
        """
        if settings and hasattr(settings, "tracking"):
            return settings.tracking.use_bytetrack
        return True

    @staticmethod
    def get_processing_interval(settings: "Settings | None", declared: int | None = None) -> int:
        """Resolve the detection cadence ByteTrack runs at (its Kalman ``dt``).

        Precedence (#667): the interval the caller DECLARED for this run
        (``set_processing_interval``: the session's resolved
        ``analysis_interval_frames``) > ``settings.video_processing.processing_interval``
        > 1. The settings value is only the fallback: a live project session
        detects at the project's interval and never writes it to the settings,
        so reading the settings alone gave the Kalman filter the wrong ``dt``.

        Args:
            settings: Application settings (optional).
            declared: Interval declared for the current run, or ``None``.

        Returns:
            Processing interval in frames, at least 1.
        """
        for value in (
            declared,
            getattr(getattr(settings, "video_processing", None), "processing_interval", None),
        ):
            try:
                interval = int(value) if value is not None else 0
            except (TypeError, ValueError):
                log.warning(
                    "detection_post_processor.processing_interval.invalid", value=repr(value)
                )
                continue
            if interval >= 1:
                return interval
        return 1

    @staticmethod
    def get_fps(settings: "Settings | None") -> int:
        """Get FPS from settings.

        Args:
            settings: Application settings (optional).

        Returns:
            Frames per second (default: 30).
        """
        if settings and hasattr(settings, "video_processing"):
            return getattr(settings.video_processing, "fps", 30) or 30
        return 30

    @staticmethod
    def resolve_tracker_fps(
        settings: "Settings | None", source_fps: float | None
    ) -> tuple[float, str]:
        """Frame rate the ByteTrack lost-track buffer must be scaled with (issue #630).

        When the caller declares each frame's instant (``set_frame_time``, #654)
        ``BYTETracker`` ages lost tracks in seconds and this rate no longer sets
        their lifetime. Without an instant it counts updates and converts
        ``track_buffer`` (configured as frames at 30 fps) with ``frame_rate / 30``. Feeding it the
        nominal ``settings.video_processing.fps`` instead of the source's real
        rate makes the buffer cover ``30 / real_fps`` times the intended real
        time: a 9.9 fps Barnes video kept a lost track alive ~3x too long, long
        enough to hand its id to another detection.

        Args:
            settings: Application settings, used only as the fallback.
            source_fps: Real rate of the frame source -- ``CAP_PROP_FPS`` of the
                video, or the camera's reported rate live. ``None``, zero,
                negative, NaN or infinite values are treated as unknown.

        Returns:
            ``(fps, origin)`` where ``origin`` is ``"source"`` when the real rate
            was used and ``"settings"`` when it fell back to the nominal value.
            The caller logs the fallback once, when it builds the tracker.
        """
        if source_fps is not None:
            try:
                value = float(source_fps)
            except (TypeError, ValueError):
                value = 0.0
            if np.isfinite(value) and value > 0:
                return value, "source"
        return float(DetectionPostProcessor.get_fps(settings)), "settings"

    @staticmethod
    def get_single_animal_mode(settings: "Settings | None", explicit_mode: bool) -> bool:
        """Determine single_animal_mode for ByteTracker.

        Priority: explicit mode flag > global settings.

        Args:
            settings: Application settings (optional).
            explicit_mode: Explicit single-subject mode flag.

        Returns:
            True if single animal mode should be enabled.
        """
        if explicit_mode:
            return True
        if settings and hasattr(settings, "video_processing"):
            return getattr(settings.video_processing, "single_animal_per_aquarium", False)
        return False
