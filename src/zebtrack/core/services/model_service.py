"""
Model Service for DRerio LogAI.

Phase 2.1: Service layer for AI model management.
Phase 2.4: Expanded with configuration management and validation.

Handles model selection, conversion, detector setup, parameter configuration,
and weight management operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.i18n import _

if TYPE_CHECKING:
    from zebtrack.core.services.weight_manager import WeightManager

log = structlog.get_logger()


class ModelService:
    """
    Service for managing AI models and detectors.

    Phase 2.1: Extracted from MainViewModel to separate model management
    concerns from UI presentation logic.

    Phase 2.4: Expanded with configuration management to consolidate
    weight management, OpenVINO operations, and configuration helpers.

    Responsibilities:
    - Model selection and validation
    - Weight listing and configuration
    - OpenVINO conversion and status management
    - Detector instantiation and configuration
    - Parameter updates
    - Configuration validation and resolution
    """

    def __init__(self, weight_manager: WeightManager):
        """
        Initialize ModelService.

        Args:
            weight_manager: WeightManager instance for weight file operations
        """
        self.weight_manager = weight_manager
        log.info("model_service.initialized")

    def convert_to_openvino(self, weight_name: str) -> bool:
        """
        Convert a weight file to OpenVINO format.

        Phase 2.1: Moved from MainViewModel.convert_active_weight_to_openvino()

        Args:
            weight_name: Name of the weight file to convert

        Returns:
            bool: True if conversion succeeded, False otherwise

        Raises:
            ValueError: If weight_name is invalid or not found
        """
        if not weight_name:
            raise ValueError("weight_name cannot be empty")

        log.info("model_service.convert_start", weight=weight_name)

        try:
            self.weight_manager.convert_to_openvino(weight_name)
            log.info("model_service.convert_success", weight=weight_name)
            return True
        # except Exception justified: YOLO/OpenVINO model operations — heterogeneous ML errors
        except Exception as e:
            log.error(
                "model_service.convert_failed",
                weight=weight_name,
                error=str(e),
                exc_info=True,
            )
            return False

    def get_weight_details(self, weight_name: str) -> dict[str, Any] | None:
        """
        Get details about a weight file.

        Args:
            weight_name: Name of the weight file

        Returns:
            dict: Weight details or None if not found
        """
        return self.weight_manager.get_weight_details(weight_name)

    def get_openvino_status(self, weight_name: str, use_openvino: bool) -> str:
        """
        Get OpenVINO status text for a weight.

        Phase 2.1: Moved from MainViewModel.get_openvino_status()

        Args:
            weight_name: Name of the weight file
            use_openvino: Whether OpenVINO is enabled

        Returns:
            str: Human-readable status message
        """
        if not weight_name:
            return _("No weight selected.")

        details = self.weight_manager.get_weight_details(weight_name)
        if not details:
            return _("Weight details not found.")

        if use_openvino:
            openvino_path = details.get("openvino_path")
            if openvino_path and Path(openvino_path).exists():
                return _("The OpenVINO model is ready.")
            else:
                return _("Conversion to OpenVINO is required.")
        else:
            return _("OpenVINO is disabled.")

    def get_default_weight(self) -> tuple[str, dict] | tuple[None, None]:
        """
        Get the default weight configuration.

        Returns:
            tuple: (weight_name, weight_details) or (None, None)
        """
        return self.weight_manager.get_default_weight()

    # === Phase 2.4: Configuration Management Methods ===

    def get_all_weight_names(self) -> list[str]:
        """
        Get names of all available weights.

        Phase 2.4: Consolidated weight listing method.

        Returns:
            list[str]: List of all weight names
        """
        return self.weight_manager.get_all_weights()

    def is_openvino_ready(self, weight_name: str) -> bool:
        """
        Check if OpenVINO model is ready for a given weight.

        Phase 2.4: Consolidated OpenVINO readiness check.

        Args:
            weight_name: Name of the weight file

        Returns:
            bool: True if OpenVINO model exists and is ready
        """
        details = self.weight_manager.get_weight_details(weight_name)
        if not details:
            return False

        openvino_path = details.get("openvino_path")
        if not openvino_path:
            return False

        return Path(openvino_path).exists()

    def check_openvino_conversion_status(self, weight_name: str) -> dict[str, Any]:
        """
        Get detailed OpenVINO conversion status for a weight.

        Phase 2.4: Detailed status checking for configuration validation.

        Args:
            weight_name: Name of the weight file

        Returns:
            dict: Status information with keys:
                - status: "not_converted", "converting", "ready", "failed", "unknown"
                - ready: bool, True if model is ready to use
                - path: str or None, path to OpenVINO model if ready
                - error: str or None, last conversion error if any
        """
        details = self.weight_manager.get_weight_details(weight_name)
        if not details:
            return {
                "status": "unknown",
                "ready": False,
                "path": None,
                "error": "Weight not found",
            }

        status = details.get("openvino_status", "unknown")
        openvino_path = details.get("openvino_path")
        last_error = details.get("last_conversion_error")

        # Verify path exists even if status is "ready"
        ready = False
        if status == "ready" and openvino_path:
            ready = Path(openvino_path).exists()
            if not ready:
                status = "not_converted"
                log.warning(
                    "model_service.openvino_status.path_missing",
                    weight=weight_name,
                    path=openvino_path,
                )
            elif self._openvino_export_is_stale(weight_name):
                # The folder exists but is not provably the export of THIS .pt
                # (a 7.2 folder without a recorded sha, or a weight retrained
                # under the same name). Loading it would serve the old model.
                ready = False
                status = "not_converted"
                log.warning(
                    "model_service.openvino_status.stale_export",
                    weight=weight_name,
                    path=openvino_path,
                )

        return {
            "status": status,
            "ready": ready,
            "path": openvino_path if ready else None,
            "error": last_error,
        }

    def _openvino_export_is_stale(self, weight_name: str) -> bool:
        """``True`` only when the weight manager PROVES the export is stale.

        Checked with ``is False`` so a stub manager without the check (or a
        ``MagicMock`` answering with a mock) never blocks a conversion that
        the old status logic considered ready.
        """
        checker = getattr(self.weight_manager, "openvino_cache_is_current", None)
        if not callable(checker):
            return False
        return checker(weight_name) is False

    def find_weight_by_path(
        self, weight_path: Path | str
    ) -> tuple[str, dict[str, Any]] | tuple[None, None]:
        """
        Find a weight by its file path.

        Phase 2.4: Helper for path-based weight lookup.

        Args:
            weight_path: Path to the weight file

        Returns:
            tuple: (weight_name, weight_details) or (None, None) if not found
        """
        weight_path = Path(weight_path) if isinstance(weight_path, str) else weight_path
        if not weight_path:
            return None, None

        # Compare paths as Path objects to handle cross-platform differences
        for name, details in self.weight_manager.weights.items():
            stored_path = details.get("path")
            if stored_path and Path(stored_path) == weight_path:
                return name, details

        log.warning("model_service.weight_not_found_by_path", path=weight_path)
        return None, None

    def get_model_path_for_inference(
        self, weight_name: str, use_openvino: bool
    ) -> tuple[str, dict[str, Any]] | tuple[None, None]:
        """
        Get the appropriate model path for inference.

        Phase 2.4: Consolidates logic for selecting correct model path
        based on OpenVINO settings.

        Args:
            weight_name: Name of the weight
            use_openvino: Whether to use OpenVINO

        Returns:
            tuple: (model_path, weight_details) or (None, None) on error
        """
        details = self.weight_manager.get_weight_details(weight_name)
        if not details:
            log.error("model_service.model_path.weight_not_found", weight=weight_name)
            return None, None

        if use_openvino:
            ov_status = self.check_openvino_conversion_status(weight_name)
            if not ov_status["ready"]:
                log.error(
                    "model_service.model_path.openvino_not_ready",
                    weight=weight_name,
                    status=ov_status["status"],
                )
                return None, None
            return ov_status["path"], details
        else:
            # Use regular .pt file
            pt_path = details.get("path")
            if not pt_path or not Path(pt_path).exists():
                log.error("model_service.model_path.pt_not_found", weight=weight_name)
                return None, None
            return pt_path, details

    def inspect_model(self, weight_name: str) -> dict[str, Any]:
        """
        Inspect a YOLO model and return detailed information.

        MELHORIA #4: Model inspection for debugging and validation.

        Args:
            weight_name: Name of the weight to inspect

        Returns:
            dict: Model information with keys:
                - weight_name: str, name of the weight
                - weight_type: str, type of weight (seg/det)
                - model_task: str, YOLO task (segment/detect)
                - class_names: dict, class ID to name mapping
                - num_classes: int, number of classes
                - input_shape: int or tuple, model input dimensions
                - model_path: str, path to model file
                - is_available: bool, whether model file exists

        Raises:
            ValueError: If weight not found
            ImportError: If Ultralytics not available
        """
        details = self.weight_manager.get_weight_details(weight_name)
        if not details:
            raise ValueError(
                _("Weight '{name}' not found in the configuration.").format(name=weight_name)
            )

        model_path = details.get("path")
        weight_type = details.get("type", "unknown")
        is_available = bool(model_path and Path(model_path).exists())

        if not is_available:
            log.warning(
                "model_service.inspect.file_not_found",
                weight=weight_name,
                path=model_path,
            )
            return {
                "weight_name": weight_name,
                "weight_type": weight_type,
                "model_task": "unknown",
                "class_names": {},
                "num_classes": 0,
                "input_shape": None,
                "model_path": model_path,
                "is_available": False,
                "error": f"Model file not found: {model_path}",
            }

        # Import YOLO temporarily for inspection
        try:
            from ultralytics import YOLO
        except ImportError as e:
            log.error("model_service.inspect.ultralytics_unavailable", error=str(e))
            raise ImportError(
                "Ultralytics package is required for model inspection. "
                "Please install ultralytics package."
            ) from e

        try:
            # Load model
            model = YOLO(model_path)  # type: ignore[arg-type]

            # Extract model information
            class_names = dict(model.names)
            num_classes = len(class_names)
            model_task = model.task  # 'detect', 'segment', 'classify', etc.

            # Get input shape (imgsz can be int or tuple)
            input_shape = model.model.args.get("imgsz", 640) if hasattr(model, "model") else 640  # type: ignore[union-attr]

            result = {
                "weight_name": weight_name,
                "weight_type": weight_type,
                "model_task": model_task,
                "class_names": class_names,
                "num_classes": num_classes,
                "input_shape": input_shape,
                "model_path": model_path,
                "is_available": True,
            }

            log.info(
                "model_service.inspect.success",
                weight=weight_name,
                task=model_task,
                classes=class_names,
            )

            return result

        # except Exception justified: YOLO/OpenVINO model operations — heterogeneous ML errors
        except Exception as e:
            log.error(
                "model_service.inspect.failed",
                weight=weight_name,
                path=model_path,
                error=str(e),
                exc_info=True,
            )
            return {
                "weight_name": weight_name,
                "weight_type": weight_type,
                "model_task": "unknown",
                "class_names": {},
                "num_classes": 0,
                "input_shape": None,
                "model_path": model_path,
                "is_available": is_available,
                "error": f"Failed to inspect model: {e}",
            }
