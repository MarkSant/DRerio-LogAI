"""
Model Service for ZebTrack-AI.

Phase 2.1: Service layer for AI model management.
Phase 2.4: Expanded with configuration management and validation.

Handles model selection, conversion, detector setup, parameter configuration,
and weight management operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from zebtrack.core.weight_manager import WeightManager

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
        except Exception as e:
            log.error(
                "model_service.convert_failed",
                weight=weight_name,
                error=str(e),
                exc_info=True,
            )
            return False

    def get_weight_details(self, weight_name: str) -> dict | None:
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
            return "Nenhum peso selecionado."

        details = self.weight_manager.get_weight_details(weight_name)
        if not details:
            return "Detalhes do peso não encontrados."

        if use_openvino:
            openvino_path = details.get("openvino_path")
            if openvino_path and Path(openvino_path).exists():
                return "O modelo OpenVINO está pronto."
            else:
                return "Necessita de conversão para OpenVINO."
        else:
            return "O OpenVINO está desativado."

    def list_available_weights(self) -> list[str]:
        """
        List all available weight files.

        Returns:
            list[str]: List of weight file names
        """
        # Weight manager stores weights as dict, extract names
        weights_dict = getattr(self.weight_manager, "weights", {})
        return list(weights_dict.keys()) if weights_dict else []

    def validate_weight(self, weight_name: str) -> bool:
        """
        Validate that a weight file exists and is usable.

        Args:
            weight_name: Name of the weight file

        Returns:
            bool: True if weight is valid
        """
        details = self.weight_manager.get_weight_details(weight_name)
        if not details:
            return False

        weight_path = details.get("path")
        if not weight_path:
            return False
        return Path(weight_path).exists()

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

    def get_weight_type(self, weight_name: str) -> str | None:
        """
        Get the type of a weight (seg or det).

        Phase 2.4: Helper for weight type queries.

        Args:
            weight_name: Name of the weight file

        Returns:
            str: "seg" or "det", or None if weight not found
        """
        details = self.weight_manager.get_weight_details(weight_name)
        return details.get("type") if details else None

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

    def check_openvino_conversion_status(self, weight_name: str) -> dict:
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

        return {
            "status": status,
            "ready": ready,
            "path": openvino_path if ready else None,
            "error": last_error,
        }

    def validate_model_configuration(self, weight_name: str | None, use_openvino: bool) -> dict:
        """
        Validate a complete model configuration.

        Phase 2.4: Comprehensive configuration validation.

        Args:
            weight_name: Name of the weight to validate
            use_openvino: Whether OpenVINO usage is requested

        Returns:
            dict: Validation result with keys:
                - valid: bool, True if configuration is valid
                - weight_exists: bool, True if weight file exists
                - weight_valid: bool, True if weight is usable
                - openvino_ready: bool, True if OpenVINO is ready (if requested)
                - errors: list[str], list of validation error messages
                - warnings: list[str], list of validation warnings
        """
        result = {
            "valid": True,
            "weight_exists": False,
            "weight_valid": False,
            "openvino_ready": False,
            "errors": [],
            "warnings": [],
        }

        # Validate weight
        if not weight_name:
            result["valid"] = False
            result["errors"].append("No weight specified")
            return result

        details = self.weight_manager.get_weight_details(weight_name)
        if not details:
            result["valid"] = False
            result["errors"].append(f"Weight '{weight_name}' not found in configuration")
            return result

        result["weight_exists"] = True

        # Validate weight file
        weight_path = details.get("path")
        if not weight_path or not Path(weight_path).exists():
            result["valid"] = False
            result["errors"].append(f"Weight file not found: {weight_path}")
        else:
            result["weight_valid"] = True

        # Validate OpenVINO if requested
        if use_openvino:
            ov_status = self.check_openvino_conversion_status(weight_name)
            result["openvino_ready"] = ov_status["ready"]

            if not ov_status["ready"]:
                if ov_status["status"] == "not_converted":
                    result["warnings"].append(
                        "OpenVINO model not converted. Conversion will be required."
                    )
                elif ov_status["status"] == "failed":
                    result["valid"] = False
                    error_msg = f"OpenVINO conversion failed: {ov_status['error']}"
                    result["errors"].append(error_msg)
                elif ov_status["status"] == "converting":
                    result["valid"] = False
                    result["errors"].append("OpenVINO conversion in progress")

        log.info(
            "model_service.config_validation",
            weight=weight_name,
            use_openvino=use_openvino,
            valid=result["valid"],
        )

        return result

    def get_weight_configuration_summary(self, weight_name: str | None) -> dict:
        """
        Get a summary of weight configuration details.

        Phase 2.4: Helper for displaying weight configuration.

        Args:
            weight_name: Name of the weight

        Returns:
            dict: Configuration summary with keys:
                - name: str or None
                - type: str or None ("seg" or "det")
                - path: str or None
                - exists: bool
                - openvino_available: bool
                - openvino_status: str
        """
        if not weight_name:
            return {
                "name": None,
                "type": None,
                "path": None,
                "exists": False,
                "openvino_available": False,
                "openvino_status": "unknown",
            }

        details = self.weight_manager.get_weight_details(weight_name)
        if not details:
            return {
                "name": weight_name,
                "type": None,
                "path": None,
                "exists": False,
                "openvino_available": False,
                "openvino_status": "unknown",
            }

        weight_path = details.get("path")
        weight_exists = bool(weight_path and Path(weight_path).exists())
        ov_status = self.check_openvino_conversion_status(weight_name)

        return {
            "name": weight_name,
            "type": details.get("type"),
            "path": weight_path,
            "exists": weight_exists,
            "openvino_available": ov_status["ready"],
            "openvino_status": ov_status["status"],
        }

    def find_weight_by_path(self, weight_path: Path | str) -> tuple[str, dict] | tuple[None, None]:
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
    ) -> tuple[str, dict] | tuple[None, None]:
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
