import time
from pathlib import Path
from typing import Any

import numpy as np

from zebtrack.plugins.base import DetectorPlugin
from zebtrack.utils.hardware_detection import is_cuda_available

YOLO: Any | None

try:
    from ultralytics import YOLO as _YOLO

    YOLO = _YOLO
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False


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
            # Phase 3 / M2: optional explicit device override.
            # None → Ultralytics auto-select (CUDA if available, else CPU).
            self._device = getattr(settings_obj.yolo_model, "device", None)
        else:
            # Fallback defaults when settings not injected
            self.conf_threshold = 0.25
            self.nms_threshold = 0.45
            self.track_threshold = 0.25
            self.match_threshold = 0.95  # Higher default for stable tracking (avoid ID jumps)
            self._use_half = True
            self._imgsz = 640
            self._device = None

        # FP16 only benefits real GPUs. Disable when:
        #   • the user explicitly forced device="cpu" (or any non-CUDA value), or
        #   • CUDA is not available at runtime (auto-detection).
        # This prevents Ultralytics from emitting half-precision warnings on
        # CPU paths and avoids confusing logs on Apple Silicon (mps).
        cuda_implied = self._device is None or "cuda" in self._device.lower()
        self._half_enabled = self._use_half and cuda_implied and is_cuda_available()
        log.info(
            "ultralytics.half_precision.resolved",
            enabled=self._half_enabled,
            use_half_setting=self._use_half,
            device=self._device,
            cuda_available=is_cuda_available(),
        )

        # ByteTrack buffer size
        self.track_buffer = 60

        # Phase 7: Model warm-up — eliminates JIT compilation latency on first real frame
        self._warm_up(log)

    def _warm_up(self, log: Any) -> None:
        """Run a single dummy inference to trigger JIT compilation and cache allocation.

        First YOLO inference is significantly slower due to internal graph optimisation
        and CUDA kernel compilation.  Running a dummy frame during ``__init__`` moves
        that latency out of the real-time processing loop.

        The dummy frame uses the same ``half``/``imgsz`` settings as production
        inference so that all kernel variants are compiled ahead of time.
        """
        try:
            h, w = self._imgsz, self._imgsz
            dummy_frame = np.zeros((h, w, 3), dtype=np.uint8)
            t0 = time.perf_counter()
            predict_kwargs: dict[str, Any] = {
                "verbose": False,
                "conf": self.conf_threshold,
                "iou": self.nms_threshold,
                "half": self._half_enabled,
                "imgsz": self._imgsz,
            }
            if self._device is not None:
                predict_kwargs["device"] = self._device
            self.model.predict(dummy_frame, **predict_kwargs)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            log.info(
                "ultralytics.warmup.complete",
                elapsed_ms=round(elapsed_ms, 1),
                device=self._device,
            )
        except Exception as e:  # except Exception justified: warm-up is best-effort
            log.warning("ultralytics.warmup.failed", error=str(e))

    def detect(
        self, frame: np.ndarray, conf_threshold: float | None = None
    ) -> list[tuple[int, int, int, int, float, int | None, int]]:
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

        # Use provided threshold or instance default
        conf = conf_threshold if conf_threshold is not None else self.conf_threshold

        import structlog

        log = structlog.get_logger()

        # ✅ DEBUG: Log detection parameters
        log.debug(
            "ultralytics.detect.start",
            frame_shape=frame.shape,
            conf_threshold=conf,
            iou_threshold=self.nms_threshold,
            imgsz=self._imgsz,
            half_enabled=self._half_enabled,
            device=self._device,
        )

        predict_kwargs: dict[str, Any] = {
            "verbose": False,
            "conf": conf,
            "iou": self.nms_threshold,
            "classes": None,
            "half": self._half_enabled,
            "imgsz": self._imgsz,
        }
        if self._device is not None:
            predict_kwargs["device"] = self._device

        results = self.model.predict(frame, **predict_kwargs)

        predictions: list[tuple[int, int, int, int, float, int | None, int]] = []
        if results and results[0].boxes is not None:
            boxes = results[0].boxes
            if boxes.xyxy is None or boxes.conf is None or boxes.cls is None:
                return predictions
            xyxys = boxes.xyxy.cpu().numpy()  # type: ignore[union-attr]
            confs = boxes.conf.cpu().numpy()  # type: ignore[union-attr]
            classes = boxes.cls.cpu().numpy()  # type: ignore[union-attr]

            # ✅ DEBUG: Log raw boxes from model
            log.debug(
                "ultralytics.detect.raw_boxes",
                num_boxes=len(xyxys),
                confidences=confs.tolist() if len(confs) > 0 else [],
                classes=classes.tolist() if len(classes) > 0 else [],
            )

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
        else:
            # ✅ DEBUG: Log when model returns no boxes
            log.debug(
                "ultralytics.detect.no_boxes",
                has_results=results is not None,
                has_boxes=results[0].boxes is not None if results else False,
                frame_shape=frame.shape,
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

        seg_kwargs: dict[str, Any] = {"conf": conf, "verbose": False}
        if self._device is not None:
            seg_kwargs["device"] = self._device
        results = self.model.predict(frame, **seg_kwargs)
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

                    mask_points = 0
                    if has_mask and result.masks is not None and result.masks.xy is not None:
                        mask_points = len(result.masks.xy[i])

                    formatted_results.append(
                        {
                            "box": [int(x1), int(y1), int(x2), int(y2)],
                            "confidence": confidence,
                            "class_id": class_id,
                            "class_name": result.names.get(class_id, f"class_{class_id}"),
                            "has_mask": has_mask,
                            "mask_points": mask_points,
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

    # Phase 7.2 — Batch inference
    # =========================================================================

    def detect_batch(
        self,
        frames: list[np.ndarray],
        conf_threshold: float | None = None,
    ) -> list[list[tuple[int, int, int, int, float, int | None, int]]]:
        """Process multiple frames via Ultralytics native batch predict.

        Passes the list of frames directly to ``model.predict()``, which
        stacks them internally for GPU-efficient batch inference.

        Args:
            frames: List of BGR frames.
            conf_threshold: Optional confidence threshold override.

        Returns:
            List of detection lists, one per input frame.
        """
        if not frames:
            return []

        conf = conf_threshold if conf_threshold is not None else self.conf_threshold

        batch_kwargs: dict[str, Any] = {
            "verbose": False,
            "conf": conf,
            "iou": self.nms_threshold,
            "classes": None,
            "half": self._half_enabled,
            "imgsz": self._imgsz,
        }
        if self._device is not None:
            batch_kwargs["device"] = self._device

        results = self.model.predict(frames, **batch_kwargs)

        all_detections: list[list[tuple[int, int, int, int, float, int | None, int]]] = []
        for result in results:
            frame_predictions: list[tuple[int, int, int, int, float, int | None, int]] = []
            if result.boxes is not None:
                if (
                    result.boxes.xyxy is None
                    or result.boxes.conf is None
                    or result.boxes.cls is None
                ):
                    all_detections.append(frame_predictions)
                    continue
                xyxys = result.boxes.xyxy.cpu().numpy()  # type: ignore[union-attr]
                confs = result.boxes.conf.cpu().numpy()  # type: ignore[union-attr]
                classes = result.boxes.cls.cpu().numpy()  # type: ignore[union-attr]
                for i in range(len(xyxys)):
                    x1, y1, x2, y2 = xyxys[i]
                    frame_predictions.append(
                        (
                            int(x1),
                            int(y1),
                            int(x2),
                            int(y2),
                            float(confs[i]),
                            None,
                            int(classes[i]),
                        )
                    )
            all_detections.append(frame_predictions)

        return all_detections
