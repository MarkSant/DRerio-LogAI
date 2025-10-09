import atexit
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
        self.model = YOLO(model_path)
        self.conf_threshold = settings.yolo_model.confidence_threshold
        self.nms_threshold = settings.yolo_model.nms_threshold

        # ByteTrack-related thresholds (used when running model.track)
        self.track_threshold = 0.25
        self.match_threshold = 0.6
        self.track_buffer = 30
        self._tracker_config_cache: dict[str, Any] | None = None
        self._tracker_config_path: Path | None = None

        # Context control for instance segmentation
        self._context = "tracking"  # 'tracking' or 'diagnostic'
        self._aquarium_region_defined = False

    def detect(self, frame: np.ndarray) -> List[Tuple[int, int, int, int, float, int]]:
        """
        Performs object tracking using the YOLOv8 model with ByteTrack.

        Returns:
            A list of tuples, where each tuple contains:
            (x1, y1, x2, y2, confidence, track_id).
        """
        # Dynamic class filtering based on context
        if self._context == "diagnostic":
            # Diagnostic mode: detect all classes
            classes_param = None
        elif self._context == "tracking" and not self._aquarium_region_defined:
            # Tracking before aquarium: detect all classes
            classes_param = None
        else:
            # Tracking after aquarium: only zebrafish
            # Accept both class 0 and 1 as zebrafish (different models may use
            # different indices)
            zebrafish_classes = []
            for class_id, class_name in self.model.names.items():
                if "zebrafish" in class_name.lower():
                    zebrafish_classes.append(class_id)
            # If no zebrafish found in names, assume class 0
            classes_param = zebrafish_classes if zebrafish_classes else [0]

        results = self.model.track(
            frame,
            persist=True,
            tracker=self._build_tracker_config(),
            verbose=False,
            conf=self.conf_threshold,
            iou=self.nms_threshold,
            classes=classes_param,  # Use dynamic parameter
        )

        predictions = []
        # Check if tracking IDs are available
        if results[0].boxes.id is not None:
            boxes = results[0].boxes
            xyxys = boxes.xyxy.cpu().numpy()
            confs = boxes.conf.cpu().numpy()
            track_ids = boxes.id.cpu().numpy()

            for i in range(len(xyxys)):
                x1, y1, x2, y2 = xyxys[i]
                confidence = confs[i]
                track_id = track_ids[i]
                predictions.append(
                    (
                        int(x1),
                        int(y1),
                        int(x2),
                        int(y2),
                        float(confidence),
                        int(track_id),
                    )
                )

        # Apply single animal mode if enabled
        if settings.video_processing.single_animal_per_aquarium and predictions:
            # Force all detections to have track_id=1 in single animal mode
            predictions = [
                (pred[0], pred[1], pred[2], pred[3], pred[4], 1) for pred in predictions
            ]

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

    def predict(
        self, frame: np.ndarray, conf_threshold: float = None
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
                    for i, box in enumerate(result.boxes):
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        class_id = int(box.cls)
                        confidence = float(box.conf)

                        # Check if corresponding mask exists
                        has_mask = (
                            result.masks is not None
                            and result.masks.xy is not None
                            and i < len(result.masks.xy)
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
                                "mask_points": len(result.masks.xy[i])
                                if has_mask
                                else 0,
                            }
                        )

                # Process orphan masks (without boxes)
                if result.masks is not None and result.masks.xy is not None:
                    num_boxes = len(result.boxes) if result.boxes else 0
                    for i in range(num_boxes, len(result.masks.xy)):
                        mask_xy = result.masks.xy[i]
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
