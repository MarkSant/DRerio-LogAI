from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np


@dataclass
class ZoneData:
    """Holds the configuration for detection zones."""

    polygon: List[List[int]] = field(default_factory=list)
    roi_polygons: List[List[List[int]]] = field(default_factory=list)
    roi_names: List[str] = field(default_factory=list)
    roi_colors: List[Tuple[int, int, int]] = field(default_factory=list)


@dataclass
class Detection:
    """Holds all data for a single detection event."""

    box: np.ndarray
    mask: np.ndarray | None
    confidence: float
    class_id: int
    class_name: str
