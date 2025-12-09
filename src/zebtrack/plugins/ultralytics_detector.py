from pathlib import Path
from typing import Any

import numpy as np

try:
    from ultralytics import YOLO

    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False

from zebtrack.plugins.base import DetectorPlugin

# OPTIMIZATION: Import hardware detection for CUDA check
try:
    from zebtrack.utils.hardware_detection import is_cuda_available
except ImportError:
    def is_cuda_available() -> bool:
        """Fallback if hardware_detection module is not available."""
        return False


class UltralyticsDetectorPlugin(DetectorPlugin):
    """A detector plugin that uses the ultralytics YOLO model."""

    def __init__(self, model_path: Path | str, settings_obj: Any | None = None):
        """
        Initializes the YOLO model.

        Args:
            model_path: The path to the .pt model file.
            settings_obj: Settings instance (injected, uses global if None for backward compat).
        """
        model_path = str(Path(model_path) if isinstance(model_path, str) else model_path)
        if not ULTRALYTICS_AVAILABLE:
            raise ImportError("Ultralytics is not available. Please install ultralytics package.")
        assert YOLO is not None
        self.model = YOLO(model_path)

        # Extract class names directly from the model (Bug Fix #1)
        self.class_names = dict(self.model.names)  # {0: 'aqua', 1: 'zebrafish', ...}
        import structlog

        log = structlog.get_logger()
        log.info("ultralytics.class_names.loaded", names=self.class_names, path=model_path)

        # Use injected settings or sensible defaults
        if settings_obj is not None:
            self.conf_threshold = settings_obj.yolo_model.confidence_threshold
            self.nms_threshold = settings_obj.yolo_model.nms_threshold
            # Read ByteTrack thresholds from settings
            self.track_threshold = getattr(settings_obj.bytetrack, "track_threshold", 0.25)
            self.match_threshold = getattr(settings_obj.bytetrack, "match_threshold", 0.95)
            # OPTIMIZATION: Read inference performance settings
            self._use_half = getattr(settings_obj.yolo_model, "use_half_precision", True)
            self._imgsz = getattr(settings_obj.yolo_model, "inference_size", 640)
        else:
            # Fallback defaults when settings not injected
            self.conf_threshold = 0.25
            self.nms_threshold = 0.45
            self.track_threshold = 0.25
            self.match_threshold = 0.95  # Higher default for stable tracking (avoid ID jumps)
            self._use_half = True
            self._imgsz = 640

        # OPTIMIZATION: Enable half precision only if CUDA is available
        # FP16 provides ~2x speedup on modern NVIDIA GPUs with minimal accuracy loss
        self._half_enabled = self._use_half and is_cuda_available()
        if self._half_enabled:
            log.info("ultralytics.half_precision.enabled", device="cuda")
        else:
            log.info(
                "ultralytics.half_precision.disabled",
                use_half_setting=self._use_half,
                cuda_available=is_cuda_available(),
            )

        # ByteTrack buffer size
        self.track_buffer = 60

    def detect(self, frame: np.ndarray) -> list[tuple[int, int, int, int, float, int | None, int]]:
        """
        Run the Ultralytics model and return raw detection boxes.

        Returns:
            A list of tuples, where each tuple contains:
            (x1, y1, x2, y2, confidence, track_id, class_id).
            track_id remains ``None`` so Detector can run BYTETracker centrally.
        """
        # OPTIMIZATION: Use half precision (FP16) and configurable image size
        # half=True provides ~2x speedup on CUDA GPUs with minimal accuracy impact
        # imgsz controls input resolution (smaller = faster, larger = more accurate)
        results = self.model.predict(
            frame,
            verbose=False,
            conf=self.conf_threshold,
            iou=self.nms_threshold,
            classes=None,
            half=self._half_enabled,
            imgsz=self._imgsz,
        )

        predictions: list[tuple[int, int, int, int, float, int | None, int]] = []
        if results and results[0].boxes is not None:
            boxes = results[0].boxes
            xyxys = boxes.xyxy.cpu().numpy()  # type: ignore[attr-defined]
            confs = boxes.conf.cpu().numpy()  # type: ignore[attr-defined]
            classes = boxes.cls.cpu().numpy()  # type: ignore[attr-defined]

            for i in range(len(xyxys)):
                x1, y1, x2, y2 = xyxys[i]
                confidence = confs[i]
                class_id = int(classes[i])
                predictions.append(
                    (
                        int(x1),
                        int(y1),
                        int(x2),
                        int(y2),
                        float(confidence),
                        None,
                        class_id,
                    )
                )

        return predictions

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

                    # Bug Fix: Use dynamic class names from model
                    orphan_class_id = 0  # Assume first class (typically aquarium/tank)
                    orphan_class_name = self.class_names.get(
                        orphan_class_id, f"class_{orphan_class_id}"
                    )

                    formatted_results.append(
                        {
                            "box": [x_min, y_min, x_max, y_max],
                            "confidence": 0.99,
                            "class_id": orphan_class_id,
                            "class_name": orphan_class_name,
                            "has_mask": True,
                            "mask_points": len(mask_xy),
                        }
                    )

        return formatted_results

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
