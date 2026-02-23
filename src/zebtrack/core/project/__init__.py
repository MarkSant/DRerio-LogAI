"""Project management sub-package — project data, zones, assets, and persistence.

Provides the central project facade (ProjectManager), zone management, video
management, asset management, ROI templates, parquet I/O, and project lifecycle
operations.

Phase 4.10 — Sub-packetize core/ into domain-specific sub-packages.
"""

from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.core.project.project_service import ProjectService
from zebtrack.core.project.schemas import AssetType as SchemaAssetType
from zebtrack.core.project.schemas import ROITemplateSchema
from zebtrack.core.project.types import AssetType
from zebtrack.core.project.video_manager import VideoManager
from zebtrack.core.project.zone_manager import ZoneManager

__all__ = [
    "AssetType",
    "ProjectManager",
    "ProjectService",
    "ROITemplateSchema",
    "SchemaAssetType",
    "VideoManager",
    "ZoneManager",
]
