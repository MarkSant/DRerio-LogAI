from typing import Any, Optional

import numpy as np

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
            raise ImportError("Ultralytics is not available. Please install ultralytics package.")
        assert YOLO is not None
        self.model = YOLO(model_path)
        self.conf_threshold = settings.yolo_model.confidence_threshold
        self.nms_threshold = settings.yolo_model.nms_threshold

        # ByteTrack threshold hints consumed by core.detector.Detector
        self.track_threshold = 0.25
        self.match_threshold = 0.15
        self.track_buffer = 60

        # Context control for instance segmentation
        self._context = "tracking"  # 'tracking' or 'diagnostic'
        self._aquarium_region_defined = False
        self._use_single_subject_mode = False

    def detect(self, frame: np.ndarray) -> list[tuple[int, int, int, int, float, Optional[int]]]:
        """
        Run the Ultralytics model and return raw detection boxes.

        Returns:
            A list of tuples, where each tuple contains:
            (x1, y1, x2, y2, confidence, track_id).
            track_id remains ``None`` so Detector can run BYTETracker centrally.
        """
        classes_param = self._resolve_detection_classes()

        results = self.model.predict(
            frame,
            verbose=False,
            conf=self.conf_threshold,
            iou=self.nms_threshold,
            classes=classes_param,
        )

        predictions: list[tuple[int, int, int, int, float, Optional[int]]] = []
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
        """Switch between single-subject heuristics and default tracking."""

        self._use_single_subject_mode = bool(enabled)
        self.reset_tracking_state()

    def predict(
        self, frame: np.ndarray, conf_threshold: float | None = None
    ) -> list[dict[str, Any]]:
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
                                "class_name": result.names.get(class_id, f"class_{class_id}"),
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
    def model_input_shape(self) -> tuple[int, int]:
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

        if track_threshold is not None and track_threshold > 0:
            self.track_threshold = track_threshold
        if match_threshold is not None and match_threshold > 0:
            self.match_threshold = match_threshold

    def reset_tracking_state(self) -> None:
        """Compatibility shim for detector.reset_tracking_state."""

        # Ultralytics YOLO keeps minimal state across predict() calls, so no-op.
        pass

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
