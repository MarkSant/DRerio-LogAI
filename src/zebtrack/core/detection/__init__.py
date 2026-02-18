"""Detection sub-package — AI detection, tracking, and zone geometry.

Provides the core detection pipeline: data types, zone scaling, detection
post-processing, single-aquarium and multi-aquarium detectors, aquarium
boundary detection, and spatial calibration.

Phase 4.10 — Sub-packetize core/ into domain-specific sub-packages.
"""

from zebtrack.core.detection.calibration import Calibration
from zebtrack.core.detection.detection_post_processor import DetectionPostProcessor
from zebtrack.core.detection.detection_types import (
    AquariumData,
    MultiAquariumZoneData,
    ZoneData,
)
from zebtrack.core.detection.multi_aquarium_detector import MultiAquariumDetector
from zebtrack.core.detection.single_detector import SingleDetector
from zebtrack.core.detection.single_subject_tracker import SingleSubjectTracker
from zebtrack.core.detection.zone_scaler import ZoneScaler

# Backward-compatible alias
Detector = SingleDetector
"""Legacy alias kept for call-sites that import ``Detector``."""

__all__ = [
    "AquariumData",
    "Calibration",
    "DetectionPostProcessor",
    "Detector",
    "MultiAquariumDetector",
    "MultiAquariumZoneData",
    "SingleDetector",
    "SingleSubjectTracker",
    "ZoneData",
    "ZoneScaler",
]
