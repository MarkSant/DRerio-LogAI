"""Services sub-package — domain services for detection, models, and wizard.

Provides the detector service (detector initialization and zone configuration),
model service (AI model management), weight manager (model catalog and conversion),
and wizard service (project wizard business logic).

Phase 4.10 — Sub-packetize core/ into domain-specific sub-packages.
"""

from zebtrack.core.services.detector_service import DetectorService
from zebtrack.core.services.model_service import ModelService
from zebtrack.core.services.weight_manager import WeightManager
from zebtrack.core.services.wizard_service import WizardService

__all__ = [
    "DetectorService",
    "ModelService",
    "WeightManager",
    "WizardService",
]
