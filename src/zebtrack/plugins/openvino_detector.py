import glob
import json
import os
import time
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np
import structlog

from zebtrack.plugins.base import DetectorPlugin
from zebtrack.utils import IntegrityError, calculate_sha256

ov: Any | None

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
    torch = None  # type: ignore[assignment]  # conditional import fallback
    TORCH_AVAILABLE = False

# Compatible with ultralytics >=8.3 and >=8.4 (API moves between versions)
try:
    from ultralytics.utils.nms import non_max_suppression
    from ultralytics.utils.ops import process_mask, scale_boxes
except ImportError:
    from ultralytics.utils.ops import (  # type: ignore[attr-defined,no-redef]
        non_max_suppression,
        process_mask,
        scale_boxes,
    )


def _resolve_openvino_cache_dir(raw: str | os.PathLike[str] | None) -> str | None:
    """Resolve and validate the OpenVINO compiled-model cache directory.

    Accepts an absolute path, a path relative to the project root (the
    repo top-level, two parents above this file), or ``None``. Creates
    the directory and ensures it is writable. Falls back to
    ``<tempdir>/zebtrack_openvino_cache`` and logs a warning when the
    requested location is not writable.
    """
    log = structlog.get_logger()
    if not raw:
        return None
    cache_path = Path(raw)
    if not cache_path.is_absolute():
        # plugins/openvino_detector.py → src/zebtrack/plugins → src/zebtrack → src → repo root
        project_root = Path(__file__).resolve().parents[3]
        cache_path = project_root / cache_path
    try:
        cache_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        import tempfile

        fallback = Path(tempfile.gettempdir()) / "zebtrack_openvino_cache"
        log.warning(
            "openvino.cache_dir.fallback",
            requested=str(cache_path),
            fallback=str(fallback),
            error=str(exc),
        )
        fallback.mkdir(parents=True, exist_ok=True)
        return str(fallback)

    if not os.access(cache_path, os.W_OK):
        import tempfile

        fallback = Path(tempfile.gettempdir()) / "zebtrack_openvino_cache"
        log.warning(
            "openvino.cache_dir.not_writable",
            requested=str(cache_path),
            fallback=str(fallback),
        )
        fallback.mkdir(parents=True, exist_ok=True)
        return str(fallback)

    return str(cache_path)


def _scale_image(masks: np.ndarray, target_hw: tuple[int, int]) -> np.ndarray:
    """Resize masks (H, W, C) to target (H, W) using bilinear interpolation.

    Replaces ultralytics.utils.ops.scale_image removed in v8.4.
    """
    return cv2.resize(masks, (target_hw[1], target_hw[0]), interpolation=cv2.INTER_LINEAR)


log = structlog.get_logger()


class OpenVINOPlugin(DetectorPlugin):
    """A detector plugin that uses an OpenVINO-optimized model."""

    def __init__(  # noqa: C901
        self,
        model_path: Path | str,
        expected_hash: str | None = None,
        settings_obj: Any | None = None,
        mode: Literal["live", "batch"] = "live",
    ):
        """
        Initializes the plugin, verifies model integrity, and loads the model.

        Args:
            model_path: Path to the directory containing .xml and .bin files.
            expected_hash: The expected SHA256 hash of the .xml file.
                If provided, the file's integrity will be verified before loading.
            settings_obj: Settings instance (injected, uses global if None for backward compat).
            mode: Execution mode ('live' for camera, 'batch' for offline processing).

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
        self._settings = settings_obj
        if settings_obj is not None:
            self.conf_threshold = settings_obj.yolo_model.confidence_threshold
            self.nms_threshold = settings_obj.yolo_model.nms_threshold
        else:
            # Fallback defaults when settings not injected
            self.conf_threshold = 0.25
            self.nms_threshold = 0.45

        self._context: str = "tracking"
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

        # Log available devices
        available_devices = core.available_devices
        log.info("openvino.available_devices", devices=available_devices)

        self._use_embedded_preprocessing = False
        self._target_h, self._target_w = 640, 640  # Default backup

        try:
            # Just get shapes for target size
            input_node = model.input(0)
            shape = input_node.partial_shape
            if shape.rank.is_static and len(shape) == 4:
                self._target_h = int(shape[2].get_length())
                self._target_w = int(shape[3].get_length())

        except Exception as e:
            log.warning("openvino.shape_check.failed", error=str(e))

        # Determine device and configuration from settings or benchmark results
        device_name = "AUTO"
        performance_hint = "LATENCY"
        precision_hint = None
        cache_dir: str | None = None
        num_streams: int | None = None
        num_threads: int | None = None

        if self._settings is not None and hasattr(self._settings, "openvino"):
            ov_settings = self._settings.openvino

            if mode == "batch":
                device_name = ov_settings.device_batch
                performance_hint = ov_settings.performance_hint_batch
            else:
                device_name = ov_settings.device
                performance_hint = ov_settings.performance_hint_live

            # Enable model cache for faster subsequent loads. The raw path
            # may be relative; _resolve_openvino_cache_dir anchors it to
            # the project root and falls back to a tempdir if the chosen
            # location is not writable (read-only volume, OneDrive lock, …).
            if ov_settings.enable_model_cache:
                cache_dir = _resolve_openvino_cache_dir(ov_settings.cache_dir)

            # Set precision hint if not FP32
            if ov_settings.precision == "FP16":
                precision_hint = "f16"
            elif ov_settings.precision == "INT8":
                precision_hint = "i8"

            # Optional CPU/GPU tuning knobs (None → let OpenVINO autotune).
            num_streams = getattr(ov_settings, "num_streams", None)
            num_threads = getattr(ov_settings, "num_threads", None)

        # Verify requested device is available
        if device_name != "AUTO" and device_name not in available_devices:
            log.warning(
                "openvino.device_not_available",
                requested=device_name,
                available=available_devices,
                fallback="AUTO",
            )
            device_name = "AUTO"

        log.info(
            "openvino.compiling_model",
            target_device=device_name,
            hint=performance_hint,
            cache_enabled=cache_dir is not None,
            num_streams=num_streams,
            num_threads=num_threads,
        )

        # Build configuration
        config: dict[str, Any] = {"PERFORMANCE_HINT": performance_hint}
        if cache_dir:
            config["CACHE_DIR"] = cache_dir
        if precision_hint and ("GPU" in device_name or device_name == "NPU"):
            config["INFERENCE_PRECISION_HINT"] = precision_hint
        if num_streams is not None:
            config["NUM_STREAMS"] = str(num_streams)
        if num_threads is not None:
            # OpenVINO uses INFERENCE_NUM_THREADS only on CPU. Setting it on
            # AUTO/GPU is a no-op or rejected — pass it through anyway and
            # let the existing fallback handler recover if compilation fails.
            config["INFERENCE_NUM_THREADS"] = str(num_threads)

        # NPU-specific configuration
        if device_name == "NPU":
            # NPU works best with FP16 natively
            if not precision_hint:
                config["INFERENCE_PRECISION_HINT"] = "f16"
            # Enable turbo mode if configured
            if (
                self._settings is not None
                and hasattr(self._settings, "openvino")
                and self._settings.openvino.npu_turbo
            ):
                try:
                    config["NPU_TURBO"] = True
                except Exception:
                    log.debug("openvino.npu_turbo.not_supported")

        try:
            self.compiled_model = core.compile_model(
                model=model, device_name=device_name, config=config
            )
        except Exception as e:
            log.warning(
                "openvino.compilation.failed_on_target",
                target_device=device_name,
                error=str(e),
                fallback="CPU" if device_name == "NPU" else "AUTO",
            )
            # NPU failures fall back to CPU (more predictable than AUTO)
            fallback_device = "CPU" if device_name == "NPU" else "AUTO"
            fallback_config = {k: v for k, v in config.items() if k != "NPU_TURBO"}
            self.compiled_model = core.compile_model(
                model=model, device_name=fallback_device, config=fallback_config
            )

        # Log actual execution devices
        try:
            # Different OpenVINO versions use different property keys,
            # "EXECUTION_DEVICES" is standard for newer versions.
            execution_devices = self.compiled_model.get_property("EXECUTION_DEVICES")
            log.info("openvino.execution_devices", devices=execution_devices)
        except Exception as e:
            log.warning("openvino.execution_devices.query_failed", error=str(e))

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
                    log.debug("openvino.output_channels.parse_error", exc_info=True)

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

        # Phase 7: Model warm-up — eliminates first-inference latency
        self._warm_up()

    def _warm_up(self) -> None:
        """Run a single dummy inference to prime the OpenVINO infer request.

        The first inference through a compiled OpenVINO model is significantly
        slower because the runtime still needs to allocate internal buffers and
        optimise the execution graph for the target device.  Running a dummy
        frame during ``__init__`` moves that cost out of the real-time loop.
        """
        try:
            h, w = self._target_h, self._target_w
            dummy_frame = np.zeros((h, w, 3), dtype=np.uint8)
            input_tensor = self._preprocess(dummy_frame)
            t0 = time.perf_counter()
            self.infer_request.infer({self.input_layer.any_name: input_tensor})
            elapsed_ms = (time.perf_counter() - t0) * 1000
            log.info("openvino.warmup.complete", elapsed_ms=round(elapsed_ms, 1))
        except Exception as e:  # except Exception justified: warm-up is best-effort
            log.warning("openvino.warmup.failed", error=str(e))

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

    def set_context(self, context: str) -> None:
        """Set the execution context (tracking/analysis)."""
        self._context = context

    def set_aquarium_region_defined(self, defined: bool) -> None:
        """Update aquarium region flag for downstream logic."""
        self._aquarium_region_defined = bool(defined)

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

    def detect(
        self, frame: np.ndarray, conf_threshold: float | None = None
    ) -> list[tuple[int, int, int, int, float, int | None, int]]:
        """Run inference using the OpenVINO model and return raw detections."""
        if frame is None or frame.size == 0:
            return []

        # Temporarily override confidence threshold if provided
        old_conf = None
        if conf_threshold is not None:
            old_conf = self.conf_threshold
            self.conf_threshold = conf_threshold

        try:
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
        finally:
            if old_conf is not None:
                self.conf_threshold = old_conf

    # Phase 7 — AsyncInferQueue batch inference
    # =========================================================================

    def detect_batch(
        self,
        frames: list[np.ndarray],
        conf_threshold: float | None = None,
    ) -> list[list[tuple[int, int, int, int, float, int | None, int]]]:
        """Process multiple frames via OpenVINO AsyncInferQueue.

        Uses an ``AsyncInferQueue`` to pipeline N inference requests so that
        host-side preprocessing overlaps with device-side inference.  The
        compiled model keeps its original ``batch=1`` shape — no reshape or
        recompilation is needed.

        When the queue is unavailable or an error occurs the method falls
        back transparently to the sequential base-class implementation.

        Args:
            frames: List of BGR frames.
            conf_threshold: Optional confidence threshold override.

        Returns:
            List of detection lists, one per input frame.
        """
        if not frames:
            return []

        # Trivial case — avoid async overhead for a single frame
        if len(frames) == 1:
            return [self.detect(frames[0], conf_threshold=conf_threshold)]

        # Determine pool size from settings (capped at frame count)
        nireq = 4  # sensible default
        if (
            self._settings is not None
            and hasattr(self._settings, "openvino")
            and hasattr(self._settings.openvino, "batch_nireq")
        ):
            nireq = self._settings.openvino.batch_nireq
        nireq = max(1, min(nireq, len(frames)))

        # Temporarily override confidence threshold if provided
        old_conf = None
        if conf_threshold is not None:
            old_conf = self.conf_threshold
            self.conf_threshold = conf_threshold

        try:
            return self._run_async_batch(frames, nireq)
        except Exception as e:  # graceful fallback
            log.warning(
                "openvino.batch.async_failed_fallback_sequential",
                error=str(e),
                nireq=nireq,
                num_frames=len(frames),
            )
            return [self.detect(f, conf_threshold=conf_threshold) for f in frames]
        finally:
            if old_conf is not None:
                self.conf_threshold = old_conf

    def _run_async_batch(
        self,
        frames: list[np.ndarray],
        nireq: int,
    ) -> list[list[tuple[int, int, int, int, float, int | None, int]]]:
        """Execute frames through an AsyncInferQueue and collect results.

        This is the inner implementation separated from :meth:`detect_batch`
        so that the outer method can handle fallback and threshold management.
        """
        assert ov is not None

        num_frames = len(frames)

        # Pre-allocate storage for raw outputs indexed by frame position
        raw_outputs: list[dict | None] = [None] * num_frames
        frame_metadata: list[tuple[tuple, tuple] | None] = [None] * num_frames

        # Build the async queue -------------------------------------------------
        async_queue = ov.AsyncInferQueue(self.compiled_model, nireq)

        def _on_complete(request: Any, userdata: int) -> None:
            """Callback invoked when an individual request finishes.

            ``userdata`` carries the original frame index so results land in
            the correct position regardless of completion order.

            We **copy** the output tensors because the underlying memory is
            owned by the infer request and will be overwritten when the
            request is reused for the next frame.
            """
            idx: int = userdata
            results = request.results
            det_tensor = np.copy(results[self.output_det])
            proto_tensor = None
            if self.output_proto and self.output_proto in results:
                proto_tensor = np.copy(results[self.output_proto])
            raw_outputs[idx] = {"det": det_tensor, "proto": proto_tensor}

        async_queue.set_callback(_on_complete)

        # Submit all frames (the queue blocks automatically when full) ----------
        input_name = self.input_layer.any_name
        for idx, frame in enumerate(frames):
            if frame is None or frame.size == 0:
                # Store empty sentinel — will yield an empty detection list
                raw_outputs[idx] = {"det": None, "proto": None}
                frame_metadata[idx] = ((0, 0, 0), (0, 0))
                continue

            input_tensor = self._preprocess(frame)
            frame_metadata[idx] = (frame.shape, input_tensor.shape[2:])
            async_queue.start_async({input_name: input_tensor}, userdata=idx)

        async_queue.wait_all()

        # Post-process collected outputs ----------------------------------------
        all_detections: list[list[tuple[int, int, int, int, float, int | None, int]]] = []
        for idx in range(num_frames):
            outputs = raw_outputs[idx]
            meta = frame_metadata[idx]

            if outputs is None or meta is None or outputs["det"] is None:
                all_detections.append([])
                continue

            original_shape, input_shape = meta

            # Build a dict-like wrapper so _postprocess can index by Output keys
            results_proxy = _OutputProxy(
                det_tensor=outputs["det"],
                proto_tensor=outputs["proto"],
                det_key=self.output_det,
                proto_key=self.output_proto,
            )

            detections, _ = self._postprocess(
                results_proxy, original_shape, input_shape, decode_masks=False
            )

            predictions: list[tuple[int, int, int, int, float, int | None, int]] = []
            for det in detections:
                x1, y1, x2, y2, score, class_id = det[:6]
                predictions.append(
                    (int(x1), int(y1), int(x2), int(y2), float(score), None, int(class_id))
                )
            all_detections.append(predictions)

        log.debug(
            "openvino.batch.complete",
            num_frames=num_frames,
            nireq=nireq,
            total_detections=sum(len(d) for d in all_detections),
        )
        return all_detections

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
        # Use target dimensions set during initialization.
        # Fallback to input_layer.shape if not set, but handle rank properly.
        if hasattr(self, "_target_h") and hasattr(self, "_target_w"):
            w, h = self._target_w, self._target_h
        else:
            # Fallback for dynamic shape or legacy
            shape = self.input_layer.shape
            if len(shape) == 4:
                h, w = shape[2], shape[3]
            else:
                h, w = 640, 640  # Last resort fallback

        letterboxed_frame, _, _ = _letterbox(frame, new_shape=(w, h), auto=False)

        # Optimized path: Embedded preprocessing (GPU friendly)
        if getattr(self, "_use_embedded_preprocessing", False):
            # Input: [1, H, W, 3], uint8, BGR (from letterbox)
            # OpenVINO handles Color, Type, and Scale conversion on backend
            input_tensor = np.expand_dims(letterboxed_frame, axis=0)
            return input_tensor

        # Legacy path: Python preprocessing (CPU intensive)
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
            # proto_tensor is guaranteed not None here due to has_mask check, but mypy doesn't know
            assert proto_tensor is not None
            masks = process_mask(
                torch.from_numpy(proto_tensor[0]),
                det[:, 6:],
                det[:, :4],
                input_shape,
                upsample=True,
            )

            # Scale masks to original image size
            # expects numpy array in (H, W, C) format for resizing
            masks_np = masks.cpu().numpy()
            masks_np = np.transpose(masks_np, (1, 2, 0))

            masks_np = _scale_image(masks_np, original_frame_shape[:2])

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
            final_masks_contours = []

        # Scale boxes
        det[:, :4] = scale_boxes(input_shape, det[:, :4], original_frame_shape).round()

        final_detections = []
        for _, row in enumerate(det):
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


class _OutputProxy:
    """Lightweight proxy that mimics ``infer_request.results`` key access.

    ``_postprocess`` indexes the results dict with ``self.output_det`` and
    ``self.output_proto`` (``ov.Output`` objects).  When async callbacks
    copy tensors into plain numpy arrays we lose the original dict keying.
    This proxy re-establishes the mapping so ``_postprocess`` works
    unchanged.
    """

    __slots__ = ("_store",)

    def __init__(
        self,
        det_tensor: np.ndarray | None,
        proto_tensor: np.ndarray | None,
        det_key: Any,
        proto_key: Any | None,
    ) -> None:
        self._store: dict[Any, np.ndarray | None] = {det_key: det_tensor}
        if proto_key is not None:
            self._store[proto_key] = proto_tensor

    def __getitem__(self, key: Any) -> np.ndarray | None:
        return self._store[key]

    def __contains__(self, key: Any) -> bool:
        return key in self._store


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
