"""Detection coordination module for zebrafish tracking.

.. deprecated::
    This module is a backward-compatibility shim.  All production code now
    lives in the decomposed sub-modules:

    - ``detection_types``   data classes (ZoneData, AquariumData, MultiAquariumZoneData)
    - ``zone_scaler``       zone polygon scaling and geometric helpers
    - ``detection_post_processor``  stateless detection utilities
    - ``single_detector``   single-aquarium detection & tracking (SingleDetector)
    - ``multi_aquarium_detector``   multi-aquarium detection & tracking

    The ``Detector`` name is kept as an alias for ``SingleDetector`` so that
    existing call-sites (``detector_service``, ``processing_worker``,
    test helpers) continue to work without modification.

Phase 4.3 - Decompose Detector God Class (2607 lines to 5 focused modules).
"""

# Re-export data classes so that every existing
#   ``from zebtrack.core.detector import ZoneData``
# continues to resolve.
from zebtrack.core.detection_types import (
    AquariumData,
    MultiAquariumZoneData,
    ZoneData,
)

# Re-export MultiAquariumDetector so callers can import from the old path.
from zebtrack.core.multi_aquarium_detector import MultiAquariumDetector

# Re-export SingleDetector under both its new name and the legacy alias.
from zebtrack.core.single_detector import SingleDetector

# Backward-compatible alias --------------------------------------------------
Detector = SingleDetector
"""Legacy alias kept for call-sites that import ``Detector``."""

__all__ = [
    "AquariumData",
    "Detector",
    "MultiAquariumDetector",
    "MultiAquariumZoneData",
    "SingleDetector",
    "ZoneData",
]
