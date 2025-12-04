import glob
import json
import os
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import structlog

try:
    import openvino as ov

    OPENVINO_AVAILABLE = True
except ImportError:
    ov = None
    OPENVINO_AVAILABLE = False

try:
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    torch = None
    TORCH_AVAILABLE = False

# Substitui imports diretos por bloco compatível com múltiplas versões do ultralytics
try:
    # Versões onde non_max_suppression está em ops
    from ultralytics.utils.ops import (
        non_max_suppression,
        process_mask,
        scale_boxes,
        scale_image,
    )
except ImportError:
    try:
        # Fallback para versões que expõem non_max_suppression em utils.nms
        from ultralytics.utils.nms import non_max_suppression  # type: ignore
        from ultralytics.utils.ops import (
            process_mask,
            scale_boxes,
            scale_image,
        )
    except ImportError as e:
        raise ImportError(
            "Falha ao importar utilitários da biblioteca ultralytics. "
            "Atualize a dependência ou ajuste o caminho do import."
        ) from e

from zebtrack.plugins.base import DetectorPlugin
from zebtrack.utils import IntegrityError, calculate_sha256

log = structlog.get_logger()


class OpenVINOPlugin(DetectorPlugin):
    """A detector plugin that uses an OpenVINO-optimized model."""

    def __init__(
        self,
        model_path: Path | str,
        expected_hash: str | None = None,
        settings_obj: Any | None = None,
    ):
        """
        Initializes the plugin, verifies model integrity, and loads the model.

        Args:
            model_path: Path to the directory containing .xml and .bin files.
            expected_hash: The expected SHA256 hash of the .xml file.
                If provided, the file's integrity will be verified before loading.
            settings_obj: Settings instance (injected, uses global if None for backward compat).

        Raises:
            FileNotFoundError: If the model's .xml file cannot be found.
            IntegrityError: If the model's hash does not match the expected hash.
        """
        model_path = Path(model_path) if isinstance(model_path, str) else model_path
        if not OPENVINO_AVAILABLE:
            raise ImportError("OpenVINO is not available. Please install openvino package.")
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch is required for OpenVINO detection post-processing.")
        assert ov is not None

        # Use injected settings or sensible defaults
        if settings_obj is not None:
            self.conf_threshold = settings_obj.yolo_model.confidence_threshold
            self.nms_threshold = settings_obj.yolo_model.nms_threshold
        else:
            # Fallback defaults when settings not injected
            self.conf_threshold = 0.25
            self.nms_threshold = 0.45

        xml_files = glob.glob(os.path.join(model_path, "*.xml"))
        if not xml_files:
            raise FileNotFoundError(f"Could not find a .xml model file in directory: {model_path}")

        model_xml_path = xml_files[0]

        # --- Security Check: File Integrity ---
        if expected_hash:
            actual_hash = calculate_sha256(model_xml_path)
            if actual_hash != expected_hash:
                log.error(
                    "openvino.load.hash_mismatch",
                    path=model_xml_path,
                    expected=expected_hash,
                    actual=actual_hash,
                )
                raise IntegrityError(
                    f"A integridade do arquivo de modelo "
                    f"'{os.path.basename(model_xml_path)}' não pôde ser verificada. "
                    f"O arquivo pode estar corrompido ou ter sido adulterado."
                )
        # --- End Security Check ---

        core = ov.Core()
        model = core.read_model(model_xml_path)
        self.compiled_model = core.compile_model(model=model, device_name="AUTO")

        # Identify outputs for detection and segmentation masks
        self.output_det = None
        self.output_proto = None

        for output in self.compiled_model.outputs:
            shape = output.partial_shape
            # [1, 4+nc+nm, 8400] -> rank 3
            if len(shape) == 3:
                self.output_det = output
            # [1, 32, 160, 160] -> rank 4
            elif len(shape) == 4:
                self.output_proto = output

        if self.output_det is None:
            # Fallback: assume output 0 is detection
            self.output_det = self.compiled_model.output(0)

        self.input_layer = self.compiled_model.input(0)
        self.infer_request = self.compiled_model.create_infer_request()

        # ByteTrack threshold hints consumed by core.detector.Detector
        # Read from settings if available, otherwise use sensible defaults
        if settings_obj is not None and hasattr(settings_obj, "bytetrack"):
            self.track_threshold = getattr(settings_obj.bytetrack, "track_threshold", 0.25)
            self.match_threshold = getattr(settings_obj.bytetrack, "match_threshold", 0.80)
        else:
            self.track_threshold = 0.25
            self.match_threshold = 0.80  # Higher default for stable tracking
        self.track_buffer = 60

        # Load metadata if exists (Bug Fix: improved fallback)
        metadata_path = os.path.join(model_path, "metadata.json")
        self.class_names = {}
        metadata_loaded = False

        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, encoding="utf-8") as f:
                    metadata = json.load(f)
                    if "class_names" in metadata:
                        self.class_names = {int(k): v for k, v in metadata["class_names"].items()}
                        metadata_loaded = True
                        log.info(
                            "openvino.metadata.loaded",
                            classes=self.class_names,
                            path=metadata_path,
                        )
            except Exception as e:
                log.warning("openvino.metadata.load_failed", error=str(e), path=metadata_path)

        # Fallback: Use generic class names if metadata not available
        if not metadata_loaded:
            # Infer number of classes from output shape if possible
            num_classes = 2  # Default assumption for ZebTrack-AI
            if self.output_det:
                try:
                    # Detection output shape: [1, 4+nc+nm, 8400]
                    # For segmentation: nc=2 (classes), nm=32 (mask coeffs)
                    # So dim[1] = 4 + nc + 32 = 38 for 2 classes
                    output_channels = self.output_det.partial_shape[1]
                    if output_channels.is_static:
                        # Solve: output_channels = 4 (bbox) + nc + 32 (masks)
                        # For detection only: output_channels = 4 + nc
                        has_masks = self.output_proto is not None
                        if has_masks:
                            num_classes = int(output_channels) - 4 - 32
                        else:
                            num_classes = int(output_channels) - 4
                        num_classes = max(1, num_classes)  # At least 1 class
                except Exception:
                    pass  # Keep default

            self.class_names = {i: f"class_{i}" for i in range(num_classes)}
            log.warning(
                "openvino.metadata.missing_using_generic",
                num_classes=num_classes,
                class_names=self.class_names,
                message=(
                    "Consider regenerating OpenVINO model to include metadata.json "
                    "with proper class names"
                ),
            )

    def get_context_info(self) -> dict:
        """Get current context and aquarium region status for debugging."""
        return {
            "conf_threshold": self.conf_threshold,
            "nms_threshold": self.nms_threshold,
            "track_threshold": self.track_threshold,
            "match_threshold": self.match_threshold,
        }

    def set_tracking_parameters(
        self,
        *,
        track_threshold: float | None = None,
        match_threshold: float | None = None,
    ) -> None:
        """Update ByteTrack threshold hints consumed by the detector."""

        if track_threshold is not None and track_threshold > 0:
            self.track_threshold = track_threshold
        if match_threshold is not None and match_threshold > 0:
            self.match_threshold = match_threshold

    def detect(self, frame: np.ndarray) -> list[tuple[int, int, int, int, float, int | None, int]]:
        """Run inference using the OpenVINO model and return raw detections."""

        input_tensor = self._preprocess(frame)
        self.infer_request.infer({self.input_layer.any_name: input_tensor})

        results = self.infer_request.results
        input_shape = input_tensor.shape[2:]

        # Optimization: Skip mask decoding for tracking (performance)
        detections, _ = self._postprocess(results, frame.shape, input_shape, decode_masks=False)

        predictions: list[tuple[int, int, int, int, float, int | None, int]] = []
        for det in detections:
            x1, y1, x2, y2, score, class_id = det[:6]
            predictions.append(
                (
                    int(x1),
                    int(y1),
                    int(x2),
                    int(y2),
                    float(score),
                    None,
                    int(class_id),
                )
            )

        return predictions

    def predict(
        self, frame: np.ndarray, conf_threshold: float | None = None
    ) -> list[dict[str, Any]]:
        """
        Compatibility method for diagnostic workflow.
        Returns raw detections without tracking, formatted for diagnostic reporting.
        """
        # Store original values
        old_conf = None

        if conf_threshold is not None:
            # Temporarily override confidence threshold for this prediction
            old_conf = self.conf_threshold
            self.conf_threshold = conf_threshold

        try:
            # 1. Preprocess and get detections from OpenVINO
            input_tensor = self._preprocess(frame)
            self.infer_request.infer({self.input_layer.any_name: input_tensor})

            results = self.infer_request.results
            input_shape = input_tensor.shape[2:]

            # Enable mask decoding for diagnostics
            detections, masks = self._postprocess(
                results, frame.shape, input_shape, decode_masks=True
            )

            # 2. Format results for diagnostic reporting
            formatted_results = []
            for i, det in enumerate(detections):
                x1, y1, x2, y2, conf = det[:5]  # Extract first 5 elements
                # Include class_id if available, or assume class 1 for compatibility
                class_id = det[5] if len(det) > 5 else 1
                # Use metadata class names if available
                class_name = self.class_names.get(int(class_id), f"class_{class_id}")

                mask_points = 0
                has_mask = False

                if masks is not None and i < len(masks) and masks[i] is not None:
                    mask_points = len(masks[i])
                    has_mask = True

                formatted_results.append(
                    {
                        "box": [int(x1), int(y1), int(x2), int(y2)],
                        "confidence": float(conf),
                        "class_id": int(class_id),
                        "class_name": class_name,
                        "has_mask": has_mask,
                        "mask_points": mask_points,
                    }
                )
            return formatted_results

        finally:
            # Restore original values
            if old_conf is not None:
                self.conf_threshold = old_conf

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        """Prepares a frame for OpenVINO inference using letterboxing."""
        _, _, h, w = self.input_layer.shape
        letterboxed_frame, _, _ = _letterbox(frame, new_shape=(w, h), auto=False)
        rgb_frame = cv2.cvtColor(letterboxed_frame, cv2.COLOR_BGR2RGB)
        input_tensor = rgb_frame.transpose(2, 0, 1) / 255.0
        input_tensor = np.expand_dims(input_tensor, axis=0).astype(np.float32)
        return input_tensor

    def _postprocess(
        self,
        results: Any,
        original_frame_shape: tuple,
        input_shape: tuple,
        decode_masks: bool = True,
    ) -> tuple[np.ndarray, list | None]:
        """Postprocesses the OpenVINO model's output."""
        output_tensor = results[self.output_det]
        proto_tensor = (
            results[self.output_proto]
            if self.output_proto and self.output_proto in results
            else None
        )

        has_mask = proto_tensor is not None

        assert torch is not None  # mypy: ensure torch is available
        preds = non_max_suppression(
            prediction=torch.from_numpy(output_tensor),
            conf_thres=self.conf_threshold,
            iou_thres=self.nms_threshold,
            agnostic=True,
            nc=len(self.class_names),  # Explicitly pass number of classes so NMS can infer nm
        )

        det = preds[0]
        if det is None or len(det) == 0:
            log.debug("openvino.postprocess.no_detections_after_nms")
            return np.empty((0, 6)), None

        # Handle masks if present and requested
        final_masks_contours = []
        if has_mask and decode_masks and len(det) > 0:
            # Process masks using Ultralytics ops
            # process_mask returns [N, H, W] masks in input_shape
            masks = process_mask(
                torch.from_numpy(proto_tensor[0]),
                det[:, 6:],
                det[:, :4],
                input_shape,
                upsample=True,
            )

            # Scale masks to original image size
            # scale_image (ultralytics) expects numpy array in (H, W, C) format for resizing
            masks_np = masks.cpu().numpy()
            masks_np = np.transpose(masks_np, (1, 2, 0))

            masks_np = scale_image(masks_np, original_frame_shape[:2])

            # Handle single mask case where resize might drop the channel dim
            if len(masks_np.shape) == 2:
                masks_np = masks_np[:, :, None]

            # Transpose back to (N, H, W)
            masks_np = np.transpose(masks_np, (2, 0, 1))

            # Convert binary masks to contours
            for i in range(len(masks_np)):
                # mask is float in [0, 1], threshold to binary
                m = (masks_np[i] > 0.5).astype("uint8") * 255
                contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    # Take largest contour
                    c = max(contours, key=cv2.contourArea)
                    final_masks_contours.append(c.reshape(-1, 2))
                else:
                    final_masks_contours.append(None)
        else:
            final_masks_contours = None

        # Scale boxes
        det[:, :4] = scale_boxes(input_shape, det[:, :4], original_frame_shape).round()

        final_detections = []
        for i, row in enumerate(det):
            # Ultralytics NMS returns [x1, y1, x2, y2, conf, cls]
            # (plus masks if not consumed by process_mask?)
            # Actually process_mask consumes the mask coeffs if passed separately?
            # det has shape [N, 6 + 32] before we sliced it? No, det comes from NMS.
            # If nm=32, det[:, 6:] are mask coeffs. det[:, :6] are box+conf+cls.

            xyxy = row[:4].cpu().numpy()
            conf = float(row[4])
            cls = int(row[5])

            class_id = int(cls)

            # Log unexpected class IDs
            if class_id not in self.class_names:
                log.warning(
                    "openvino.postprocess.unexpected_class",
                    class_id=class_id,
                    expected_classes=list(self.class_names.keys()),
                    confidence=float(conf),
                )

            # Return detection tuple
            final_detections.append(
                [
                    int(xyxy[0]),
                    int(xyxy[1]),
                    int(xyxy[2]),
                    int(xyxy[3]),
                    float(conf),
                    class_id,
                ]
            )

        return np.array(final_detections), final_masks_contours

    @staticmethod
    def get_name() -> str:
        return "OpenVINO"

    @property
    def model_input_shape(self) -> tuple[int, int]:
        return self.input_layer.shape[2], self.input_layer.shape[3]  # (h, w)


def _letterbox(
    img: np.ndarray,
    new_shape: tuple = (640, 640),
    color: tuple = (114, 114, 114),
    auto: bool = True,
    scaleFill: bool = False,
    scaleup: bool = True,
    stride: int = 32,
):
    """
    Standard letterboxing function from ultralytics.
    Resizes and pads image while meeting stride-multiple constraints.
    """
    # Task 1.5: Validate image to prevent division by zero
    if img is None or img.size == 0:
        raise ValueError("Image cannot be None or empty")

    if len(img.shape) < 2:
        raise ValueError(f"Image must have at least 2 dimensions, got {len(img.shape)}")

    shape = img.shape[:2]

    if shape[0] == 0 or shape[1] == 0:
        raise ValueError(f"Image dimensions cannot be zero: height={shape[0]}, width={shape[1]}")

    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)

    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    if not scaleup:
        r = min(r, 1.0)

    ratio = r, r
    new_unpad = round(shape[1] * r), round(shape[0] * r)
    dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]
    if auto:
        dw, dh = np.mod(dw, stride), np.mod(dh, stride)
    elif scaleFill:
        dw, dh = 0.0, 0.0
        new_unpad = (new_shape[1], new_shape[0])
        ratio = new_shape[1] / shape[1], new_shape[0] / shape[0]

    dw /= 2
    dh /= 2

    if shape[::-1] != new_unpad:
        img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = round(dh - 0.1), round(dh + 0.1)
    left, right = round(dw - 0.1), round(dw + 0.1)
    img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)
    return img, ratio, (dw, dh)
