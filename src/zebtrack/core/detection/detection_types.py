"""Detection data types for zebrafish tracking.

Contains the shared data structures used across the detection subsystem:
ZoneData, AquariumData, and MultiAquariumZoneData.

These types are imported by 40+ files across the codebase and are re-exported
from ``zebtrack.core.detector`` for backward compatibility.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = ["AquariumData", "MultiAquariumZoneData", "ZoneData"]


@dataclass
class ZoneData:
    """Holds the configuration for detection zones."""

    polygon: Sequence[Sequence[int]] = field(default_factory=list)
    roi_polygons: Sequence[Sequence[Sequence[int]]] = field(default_factory=list)
    roi_names: Sequence[str] = field(default_factory=list)
    roi_colors: Sequence[tuple[int, int, int]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AquariumData:
    """Zone data for a single aquarium with metadata.

    Used in multi-aquarium mode to store configuration specific
    to each aquarium, including experimental metadata.
    """

    id: int  # 0 ou 1 para vídeos com 2 aquários
    polygon: Sequence[Sequence[int]] = field(default_factory=list)  # Polígono da arena
    roi_polygons: Sequence[Sequence[Sequence[int]]] = field(
        default_factory=list
    )  # ROIs within this aquarium
    roi_names: Sequence[str] = field(default_factory=list)
    roi_colors: Sequence[tuple[int, int, int]] = field(default_factory=list)
    group: str = ""  # Grupo (ex: "Controle", "Tratamento")
    subject_id: str = ""  # Identificador do sujeito
    day: int = 0  # Dia do experimento
    roi_mode: str = ""  # Modo de ROI (ex: "grid", "freehand")
    roi_data: dict[str, Any] = field(
        default_factory=dict
    )  # Dados extras de ROI (ex: grid_rows, grid_cols)

    def to_zone_data(self) -> ZoneData:
        """Helper to get current zone configuration as ZoneData object."""
        return ZoneData(
            polygon=self.polygon,
            roi_polygons=self.roi_polygons,
            roi_names=self.roi_names,
            roi_colors=self.roi_colors,
        )


@dataclass
class MultiAquariumZoneData:
    """Zone data for videos with multiple aquariums.

    Encapsulates configurations for 2 aquariums in a single video,
    enabling independent tracking and analysis.

    Attributes:
        aquariums: List of per-aquarium configurations.
        video_width: Video width in pixels.
        video_height: Video height in pixels.
        sequential_processing: If True (default), processes each aquarium separately
            (2 video passes). If False, processes both simultaneously
            (1 pass). Default changed to True for better precision.
    """

    aquariums: list[AquariumData] = field(default_factory=list)
    video_width: int = 0
    video_height: int = 0
    sequential_processing: bool = True

    def get_aquarium(self, aquarium_id: int) -> AquariumData | None:
        """Return aquarium data by ID.

        Args:
            aquarium_id: Aquarium ID (0 or 1).

        Returns:
            AquariumData if found, None otherwise.
        """
        for aquarium in self.aquariums:
            if aquarium.id == aquarium_id:
                return aquarium
        return None

    def to_zone_data(self, aquarium_id: int = 0) -> ZoneData:
        """Convert a specific aquarium to ZoneData.

        Args:
            aquarium_id: Aquarium ID to convert (default: 0).

        Returns:
            ZoneData for the specified aquarium, or empty ZoneData if not found.
        """
        aquarium = self.get_aquarium(aquarium_id)
        if aquarium:
            return aquarium.to_zone_data()
        return ZoneData()

    @property
    def aquarium_count(self) -> int:
        """Return the number of configured aquariums."""
        return len(self.aquariums)

    @property
    def is_multi_aquarium(self) -> bool:
        """Return True if more than one aquarium is configured."""
        return len(self.aquariums) > 1
