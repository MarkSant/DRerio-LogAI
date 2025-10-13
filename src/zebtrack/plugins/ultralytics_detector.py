import atexit
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml

try:
    from ultralytics import YOLO

    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False

from zebtrack.plugins.base import DetectorPlugin
from zebtrack.settings import settings


class UltralyticsDetectorPlugin(DetectorPlugin):
    """A detector plugin that uses the ultralytics YOLO model."""

    def __init__(self, model_path: str):
        """
        Initializes the YOLO model.

        Args:
            model_path (str): The path to the .pt model file.
        """
        if not ULTRALYTICS_AVAILABLE:
            raise ImportError(
                "Ultralytics is not available. Please install ultralytics package."
            )
        assert YOLO is not None
        self.model = YOLO(model_path)
        self.conf_threshold = settings.yolo_model.confidence_threshold
        self.nms_threshold = settings.yolo_model.nms_threshold

        # ByteTrack-related thresholds (used when running model.track)
        self.track_threshold = 0.25
        self.match_threshold = 0.15
        self.track_buffer = 60
        self._tracker_config_cache: dict[str, Any] | None = None
        self._tracker_config_path: Path | None = None

        # Context control for instance segmentation
        self._context = "tracking"  # 'tracking' or 'diagnostic'
        self._aquarium_region_defined = False
        self._use_single_subject_mode = False

    def detect(
        self, frame: np.ndarray
    ) -> List[Tuple[int, int, int, int, float, Optional[int]]]:
        """
        Performs object tracking using the YOLOv8 model with ByteTrack.

        Returns:
            A list of tuples, where each tuple contains:
            (x1, y1, x2, y2, confidence, track_id).
        """
        classes_param = self._resolve_detection_classes()

        if self._use_single_subject_mode:
            results = self.model.predict(
                frame,
                verbose=False,
                conf=self.conf_threshold,
                iou=self.nms_threshold,
                classes=classes_param,
            )

            predictions: List[Tuple[int, int, int, int, float, Optional[int]]] = []
            if results and results[0].boxes is not None:
                boxes = results[0].boxes
                xyxys = boxes.xyxy.cpu().numpy()  # type: ignore[attr-defined]
                confs = boxes.conf.cpu().numpy()  # type: ignore[attr-defined]

                for i in range(len(xyxys)):
                    x1, y1, x2, y2 = xyxys[i]
                    confidence = confs[i]
                    predictions.append(
                        (
                            int(x1),
                            int(y1),
                            int(x2),
                            int(y2),
                            float(confidence),
                            None,
                        )
                    )

            return predictions

        results = self.model.track(
            frame,
            persist=True,
            tracker=self._build_tracker_config(),
            verbose=False,
            conf=self.conf_threshold,
            iou=self.nms_threshold,
            classes=classes_param,
        )

        predictions: List[Tuple[int, int, int, int, float, Optional[int]]] = []
        if results and results[0].boxes is not None:
            boxes = results[0].boxes
            xyxys = boxes.xyxy.cpu().numpy()  # type: ignore[attr-defined]
            confs = boxes.conf.cpu().numpy()  # type: ignore[attr-defined]
            if boxes.id is not None:
                raw_track_ids = boxes.id.cpu().numpy()  # type: ignore[attr-defined]
                track_id_values: List[Optional[int]] = [int(t) for t in raw_track_ids]
            else:
                track_id_values = [None] * len(xyxys)

            for i in range(len(xyxys)):
                x1, y1, x2, y2 = xyxys[i]
                confidence = confs[i]
                track_id_value = track_id_values[i]
                predictions.append(
                    (
                        int(x1),
                        int(y1),
                        int(x2),
                        int(y2),
                        float(confidence),
                        track_id_value,
                    )
                )

        return predictions

    def set_context(self, context: str):
        """
        Set the detection context.

        Args:
            context (str): 'tracking' or 'diagnostic'
        """
        if context in ("tracking", "diagnostic"):
            self._context = context

    def set_aquarium_region_defined(self, defined: bool = True):
        """
        Set whether aquarium region has been defined.

        Args:
            defined (bool): True if aquarium region is defined
        """
        self._aquarium_region_defined = bool(defined)

    def set_use_single_subject_mode(self, enabled: bool) -> None:
        """Switch between ByteTrack and raw detections."""

        self._use_single_subject_mode = bool(enabled)
        self.reset_tracking_state()

    def predict(
        self, frame: np.ndarray, conf_threshold: float | None = None
    ) -> List[Dict[str, Any]]:
        """
        Method for diagnostic with instance segmentation support.

        Args:
            frame (np.ndarray): Input frame
            conf_threshold (float, optional): Confidence threshold override

        Returns:
            List[Dict]: Detection results with mask information
        """
        conf = conf_threshold if conf_threshold is not None else self.conf_threshold

        # Force diagnostic context
        old_context = self._context
        self._context = "diagnostic"

        try:
            results = self.model.predict(frame, conf=conf, verbose=False)
            formatted_results = []

            if results and results[0]:
                result = results[0]

                # Process boxes and masks together
                if result.boxes is not None:
                    for i, box in enumerate(result.boxes):  # type: ignore[arg-type]
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        class_id = int(box.cls)
                        confidence = float(box.conf)

                        # Check if corresponding mask exists
                        has_mask = (
                            result.masks is not None
                            and result.masks.xy is not None  # type: ignore[union-attr]
                            and i < len(result.masks.xy)  # type: ignore[union-attr]
                        )

                        formatted_results.append(
                            {
                                "box": [int(x1), int(y1), int(x2), int(y2)],
                                "confidence": confidence,
                                "class_id": class_id,
                                "class_name": result.names.get(
                                    class_id, f"class_{class_id}"
                                ),
                                "has_mask": has_mask,
                                "mask_points": len(result.masks.xy[i])  # type: ignore[union-attr]
                                if has_mask
                                else 0,
                            }
                        )

                # Process orphan masks (without boxes)
                if result.masks is not None and result.masks.xy is not None:  # type: ignore[union-attr]
                    num_boxes = len(result.boxes) if result.boxes else 0
                    for i in range(num_boxes, len(result.masks.xy)):  # type: ignore[union-attr]
                        mask_xy = result.masks.xy[i]  # type: ignore[union-attr]
                        x_min = int(mask_xy[:, 0].min())
                        y_min = int(mask_xy[:, 1].min())
                        x_max = int(mask_xy[:, 0].max())
                        y_max = int(mask_xy[:, 1].max())

                        formatted_results.append(
                            {
                                "box": [x_min, y_min, x_max, y_max],
                                "confidence": 0.99,
                                "class_id": 0,  # Assume aquarium for orphan masks
                                "class_name": "aquarium",
                                "has_mask": True,
                                "mask_points": len(mask_xy),
                            }
                        )

            return formatted_results

        finally:
            self._context = old_context

    @staticmethod
    def get_name() -> str:
        return "YOLO (Ultralytics)"

    @property
    def model_input_shape(self) -> Tuple[int, int]:
        # This is a bit of a simplification. YOLOv8 can handle various input sizes,
        # but 640 is the default and what's implicitly used.
        # For a more robust implementation, one might inspect the model's properties.
        return (640, 640)

    def set_tracking_parameters(
        self,
        *,
        track_threshold: float | None = None,
        match_threshold: float | None = None,
    ) -> None:
        """Update internal ByteTrack thresholds used during tracking."""

        updated = False
        if track_threshold is not None and track_threshold > 0:
            self.track_threshold = track_threshold
            updated = True
        if match_threshold is not None and match_threshold > 0:
            self.match_threshold = match_threshold
            updated = True

        if updated:
            self._tracker_config_cache = None

    def _build_tracker_config(self) -> str:
        """Return the YAML tracker config path expected by Ultralytics ByteTrack."""

        config: dict[str, Any] = {
            "tracker_type": "bytetrack",
            "track_high_thresh": self.track_threshold,
            "track_low_thresh": min(self.track_threshold, 0.1),
            "new_track_thresh": self.track_threshold,
            "track_buffer": self.track_buffer,
            "match_thresh": self.match_threshold,
            "fuse_score": True,
        }

        path_missing = (
            self._tracker_config_path is None
            or not self._tracker_config_path.exists()
        )

        if config != self._tracker_config_cache or path_missing:
            self._tracker_config_cache = dict(config)
            self._tracker_config_path = self._write_tracker_config(config)

        return str(self._tracker_config_path)

    def reset_tracking_state(self) -> None:
        """Clear internal tracker state."""

        try:
            self.model.tracker = None  # type: ignore[attr-defined]
        except AttributeError:
            pass

    def _write_tracker_config(self, config: dict[str, Any]) -> Path:
        temp_dir = Path(tempfile.gettempdir()) / "zebtrack_bytetrack"
        temp_dir.mkdir(exist_ok=True)

        if self._tracker_config_path is not None:
            try:
                self._tracker_config_path.unlink(missing_ok=True)
            except OSError:
                pass
            finally:
                _TRACKER_TEMP_FILES.discard(self._tracker_config_path)

        fd, path_str = tempfile.mkstemp(
            dir=temp_dir, prefix="tracker_", suffix=".yaml"
        )
        path = Path(path_str)
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            yaml.safe_dump(config, tmp_file, sort_keys=False)

        _TRACKER_TEMP_FILES.add(path)
        return path

    def _resolve_detection_classes(self) -> list[int] | None:
        if self._context == "diagnostic":
            return None
        if self._context == "tracking" and not self._aquarium_region_defined:
            return None

        zebrafish_classes: list[int] = []
        for class_id, class_name in self.model.names.items():
            if "zebrafish" in class_name.lower():
                zebrafish_classes.append(class_id)

        return zebrafish_classes if zebrafish_classes else [0]


_TRACKER_TEMP_FILES: set[Path] = set()


def _cleanup_tracker_temp_files() -> None:
    for path in list(_TRACKER_TEMP_FILES):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        finally:
            _TRACKER_TEMP_FILES.discard(path)


atexit.register(_cleanup_tracker_temp_files)
