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
    """Dados de zona para um único aquário com metadados.

    Usado em modo multi-aquário para armazenar configurações específicas
    de cada aquário, incluindo metadados experimentais.
    """

    id: int  # 0 ou 1 para vídeos com 2 aquários
    polygon: Sequence[Sequence[int]] = field(default_factory=list)  # Polígono da arena
    roi_polygons: Sequence[Sequence[Sequence[int]]] = field(
        default_factory=list
    )  # ROIs dentro deste aquário
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
    """Dados de zona para vídeos com múltiplos aquários.

    Encapsula configurações para 2 aquários em um único vídeo,
    permitindo tracking e análise independentes.

    Attributes:
        aquariums: Lista de configurações por aquário.
        video_width: Largura do vídeo em pixels.
        video_height: Altura do vídeo em pixels.
        sequential_processing: Se True (padrão), processa cada aquário separadamente
            (2 passagens pelo vídeo). Se False, processa ambos simultaneamente
            (1 passagem). Padrão alterado para True pois oferece melhor precisão.
    """

    aquariums: list[AquariumData] = field(default_factory=list)
    video_width: int = 0
    video_height: int = 0
    sequential_processing: bool = True

    def get_aquarium(self, aquarium_id: int) -> AquariumData | None:
        """Retorna dados do aquário pelo ID.

        Args:
            aquarium_id: ID do aquário (0 ou 1).

        Returns:
            AquariumData se encontrado, None caso contrário.
        """
        for aquarium in self.aquariums:
            if aquarium.id == aquarium_id:
                return aquarium
        return None

    def to_zone_data(self, aquarium_id: int = 0) -> ZoneData:
        """Converte um aquário específico para ZoneData.

        Args:
            aquarium_id: ID do aquário a converter (padrão: 0).

        Returns:
            ZoneData do aquário especificado, ou ZoneData vazio se não encontrado.
        """
        aquarium = self.get_aquarium(aquarium_id)
        if aquarium:
            return aquarium.to_zone_data()
        return ZoneData()

    @property
    def aquarium_count(self) -> int:
        """Retorna o número de aquários configurados."""
        return len(self.aquariums)

    @property
    def is_multi_aquarium(self) -> bool:
        """Retorna True se há mais de um aquário configurado."""
        return len(self.aquariums) > 1
