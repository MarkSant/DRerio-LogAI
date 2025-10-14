"""
Model Service for ZebTrack-AI.

Phase 2.1: Service layer for AI model management.
Handles model selection, conversion, detector setup, and parameter configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from zebtrack.core.weight_manager import WeightManager
    from zebtrack.plugins.base import DetectorPlugin

log = structlog.get_logger()


class ModelService:
    """
    Service for managing AI models and detectors.
    
    Phase 2.1: Extracted from MainViewModel to separate model management
    concerns from UI presentation logic.
    
    Responsibilities:
    - Model selection and validation
    - OpenVINO conversion
    - Detector instantiation and configuration
    - Parameter updates
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
