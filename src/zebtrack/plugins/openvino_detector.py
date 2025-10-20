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
    from ultralytics.utils.ops import non_max_suppression, scale_boxes
except ImportError:
    try:
        # Fallback para versões que expõem non_max_suppression em utils.nms
        from ultralytics.utils.nms import non_max_suppression  # type: ignore
        from ultralytics.utils.ops import scale_boxes
    except ImportError as e:
        raise ImportError(
            "Falha ao importar non_max_suppression da biblioteca ultralytics. "
            "Atualize a dependência ou ajuste o caminho do import."
        ) from e

from zebtrack.plugins.base import DetectorPlugin
from zebtrack.settings import settings
from zebtrack.utils import IntegrityError, calculate_sha256

log = structlog.get_logger()


class OpenVINOPlugin(DetectorPlugin):
    """A detector plugin that uses an OpenVINO-optimized model."""

    def __init__(self, model_path: Path | str, expected_hash: str | None = None):
        """
        Initializes the plugin, verifies model integrity, and loads the model.

        Args:
            model_path: Path to the directory containing .xml and .bin files.
            expected_hash: The expected SHA256 hash of the .xml file.
                If provided, the file's integrity will be verified before loading.

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

        self.conf_threshold = settings.yolo_model.confidence_threshold
        self.nms_threshold = settings.yolo_model.nms_threshold

        # Context control for class filtering
        self._context: str = "tracking"  # 'tracking' or 'diagnostic'
        self._aquarium_region_defined: bool = False

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
        self.input_layer = self.compiled_model.input(0)
        self.output_layer = self.compiled_model.output(0)
        self.infer_request = self.compiled_model.create_infer_request()

        # ByteTrack threshold hints consumed by core.detector.Detector
        self.track_threshold = 0.25
        self.match_threshold = 0.15
        self.track_buffer = 60

        # Carrega metadata se existir
        metadata_path = os.path.join(model_path, "metadata.json")
        self.class_names = {0: "aquarium", 1: "zebrafish"}  # Default
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, encoding="utf-8") as f:
                    metadata = json.load(f)
                    if "class_names" in metadata:
                        self.class_names = {int(k): v for k, v in metadata["class_names"].items()}
                    log.info("openvino.metadata.loaded", classes=self.class_names)
            except Exception as e:
                log.warning("openvino.metadata.load_failed", error=str(e))

    def set_context(self, context: str):
        """
        Define o contexto de uso do plugin.
        'diagnostic' => não filtra classes (mostra todas)
        'tracking'   => aplica filtragem condicional (apenas classe 1 depois do
                        aquário definido)
        """
        if context not in ("tracking", "diagnostic"):
            return
        self._context = context

    def set_aquarium_region_defined(self, defined: bool = True):
        """Informar que a região do aquário já está válida"""
        self._aquarium_region_defined = bool(defined)

    def get_context_info(self) -> dict:
        """Get current context and aquarium region status for debugging."""
        return {
            "context": self._context,
            "aquarium_region_defined": self._aquarium_region_defined,
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

    def detect(self, frame: np.ndarray) -> list[tuple[int, int, int, int, float, int | None]]:
        """Run inference using the OpenVINO model and return raw detections."""

        input_tensor = self._preprocess(frame)
        self.infer_request.infer({self.input_layer.any_name: input_tensor})
        results = self.infer_request.results
        detections = self._postprocess(results, frame.shape)

        predictions: list[tuple[int, int, int, int, float, int | None]] = []
        for det in detections:
            x1, y1, x2, y2, score = det[:5]
            predictions.append(
                (
                    int(x1),
                    int(y1),
                    int(x2),
                    int(y2),
                    float(score),
                    None,
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
        old_context = self._context

        if conf_threshold is not None:
            # Temporarily override confidence threshold for this prediction
            old_conf = self.conf_threshold
            self.conf_threshold = conf_threshold

        # Ensure diagnostic context for this prediction (shows all classes)
        self.set_context("diagnostic")

        try:
            # 1. Preprocess and get detections from OpenVINO
            input_tensor = self._preprocess(frame)
            self.infer_request.infer({self.input_layer.any_name: input_tensor})
            results = self.infer_request.results
            detections = self._postprocess(results, frame.shape)

            # 2. Format results for diagnostic reporting
            formatted_results = []
            for det in detections:
                x1, y1, x2, y2, conf = det[:5]  # Extract first 5 elements
                # Include class_id if available, or assume class 1 for compatibility
                class_id = det[5] if len(det) > 5 else 1
                # Use metadata class names if available
                class_name = self.class_names.get(int(class_id), f"class_{class_id}")
                formatted_results.append(
                    {
                        "box": [int(x1), int(y1), int(x2), int(y2)],
                        "confidence": float(conf),
                        "class_id": int(class_id),
                        "class_name": class_name,
                    }
                )
            return formatted_results

        finally:
            # Restore original values
            if old_conf is not None:
                self.conf_threshold = old_conf
            # Restore original context
            self._context = old_context

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        """Prepares a frame for OpenVINO inference using letterboxing."""
        n, c, h, w = self.input_layer.shape
        letterboxed_frame, _, _ = _letterbox(frame, new_shape=(w, h), auto=False)
        rgb_frame = cv2.cvtColor(letterboxed_frame, cv2.COLOR_BGR2RGB)
        input_tensor = rgb_frame.transpose(2, 0, 1) / 255.0
        input_tensor = np.expand_dims(input_tensor, axis=0).astype(np.float32)
        return input_tensor

    def _postprocess(self, result: Any, original_frame_shape: tuple) -> list:
        """Postprocesses the OpenVINO model's output."""
        output_tensor = result[self.output_layer]
        assert torch is not None  # mypy: ensure torch is available
        preds = non_max_suppression(
            prediction=torch.from_numpy(output_tensor),
            conf_thres=self.conf_threshold,
            iou_thres=self.nms_threshold,
            agnostic=True,
        )
        detections = preds[0]
        if detections is None or len(detections) == 0:
            log.debug("openvino.postprocess.no_detections_after_nms")
            return []

        detections[:, :4] = scale_boxes(
            self.model_input_shape, detections[:, :4], original_frame_shape
        ).round()

        final_detections = []
        filtered_count = 0
        for *xyxy, conf, cls in detections:
            class_id = int(cls)

            # Log unexpected class IDs
            if class_id not in self.class_names:
                log.warning(
                    "openvino.postprocess.unexpected_class",
                    class_id=class_id,
                    expected_classes=list(self.class_names.keys()),
                    confidence=float(conf),
                )

            # LÓGICA DE FILTRO ATUALIZADA:
            if self._context == "diagnostic":
                # Em modo diagnóstico NUNCA filtra: inclui todas as classes retornadas
                final_detections.append(
                    (
                        int(xyxy[0]),
                        int(xyxy[1]),
                        int(xyxy[2]),
                        int(xyxy[3]),
                        float(conf),
                        class_id,
                    )
                )
            else:
                # Modo tracking:
                # Antes do aquário estar definido: não filtra (permite aparecer
                # classe 0 ou outras)
                # Após definição do aquário: filtra para somente peixe
                # IMPORTANTE: Aceita tanto classe 0 quanto classe 1 como zebrafish,
                # pois modelos diferentes podem usar índices diferentes
                if self._aquarium_region_defined:
                    # Check if this is a zebrafish class
                    class_name = self.class_names.get(class_id, "")
                    is_zebrafish = "zebrafish" in class_name.lower() or class_id == 0

                    if not is_zebrafish:
                        filtered_count += 1
                        continue

                final_detections.append(
                    (
                        int(xyxy[0]),
                        int(xyxy[1]),
                        int(xyxy[2]),
                        int(xyxy[3]),
                        float(conf),
                        class_id,
                    )
                )
        return final_detections

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
    shape = img.shape[:2]
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
