"""Detection coordination module for zebrafish tracking.

Manages the detection process by delegating to detector plugins and handling
stateful logic for zone tracking, ROI filtering, and overlay rendering.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np
import structlog

from zebtrack.core.single_subject_tracker import SingleSubjectTracker
from zebtrack.plugins.base import DetectorPlugin
from zebtrack.tracker.byte_tracker import BYTETracker

if TYPE_CHECKING:
    from zebtrack.settings import Settings

log = structlog.get_logger()


@dataclass
class ZoneData:
    """Holds the configuration for detection zones."""

    polygon: list[list[int]] = field(default_factory=list)
    roi_polygons: list[list[list[int]]] = field(default_factory=list)
    roi_names: list[str] = field(default_factory=list)
    roi_colors: list[tuple[int, int, int]] = field(default_factory=list)


@dataclass
class AquariumData:
    """Dados de zona para um único aquário com metadados.

    Usado em modo multi-aquário para armazenar configurações específicas
    de cada aquário, incluindo metadados experimentais.
    """

    id: int  # 0 ou 1 para vídeos com 2 aquários
    polygon: list[list[int]] = field(default_factory=list)  # Polígono da arena
    roi_polygons: list[list[list[int]]] = field(default_factory=list)  # ROIs dentro deste aquário
    roi_names: list[str] = field(default_factory=list)
    roi_colors: list[tuple[int, int, int]] = field(default_factory=list)
    group: str = ""  # Grupo (ex: "Controle", "Tratamento")
    subject_id: str = ""  # Identificador do sujeito
    day: int = 0  # Dia do experimento

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


class Detector:
    """
    Manages the detection process by delegating to a plugin and handling
    stateful logic for zone tracking.

    Nota de Otimização:
    O rastreamento de objetos é baseado nos bounding boxes. Se o modelo de IA
    carregado for um modelo de segmentação (*_seg.pt), ele realizará a
    tarefa computacionalmente mais custosa de encontrar máscaras de pixel,
    mesmo que apenas os bounding boxes sejam usados. Para um desempenho
    ótimo no rastreamento, um modelo treinado apenas para DETECÇÃO (que
    gera somente bounding boxes) deve ser usado em futuras versões.
    """

    def __init__(
        self,
        plugin: DetectorPlugin,
        base_width: int = 1280,
        base_height: int = 720,
        settings_obj: "Settings | None" = None,
    ) -> None:
        """
        Initialize the detector with a specific plugin.

        Args:
            plugin (DetectorPlugin): An instantiated detector plugin.
            base_width (int): The reference width the zones were defined on.
            base_height (int): The reference height the zones were defined on.
            settings_obj: Settings instance (injected, optional for backward compatibility).
        """
        self.plugin = plugin
        if not self.plugin:
            log.error("detector.init.no_plugin")
            raise ValueError("Detector must be initialized with a valid plugin.")

        self.settings = settings_obj
        self.base_width = base_width
        self.base_height = base_height
        log.info("detector.init.success", plugin=self.plugin.get_name())

        # Zone configuration is now set dynamically via set_zones()
        self.zones: ZoneData | MultiAquariumZoneData = ZoneData()
        self.scaled_polygon: np.ndarray = np.array([])
        self.scaled_roi_polygons: list[np.ndarray] = []
        self._scaling_cache: dict = {}
        """Caches scaled zone polygons to avoid recalculation for each frame of the same size."""
        self._single_subject_mode = False
        self._single_subject_tracker = SingleSubjectTracker()
        self._byte_tracker: BYTETracker | None = None
        self._byte_tracker_params: tuple[float, float, int] | None = None
        self._zones_configured = False
        self._last_width: int | None = None
        self._last_height: int | None = None
        self._context: str = "tracking"
        self._aquarium_region_defined: bool = False

        # Multi-aquarium mode state
        self._multi_aquarium_mode: bool = False
        self._aquariums: list[AquariumData] = []
        self._byte_trackers_multi: dict[int, BYTETracker] = {}
        self._single_subject_trackers_multi: dict[int, SingleSubjectTracker] = {}
        self._scaled_aquarium_polygons: dict[int, np.ndarray] = {}
        self._scaled_aquarium_roi_polygons: dict[int, list[np.ndarray]] = {}

        # Dynamic class ID resolution
        self.aquarium_class_id = 0
        self.animal_class_id = 1
        self._resolve_class_ids()

    def _resolve_class_ids(self) -> None:
        """Resolve class IDs from plugin metadata."""
        if hasattr(self.plugin, "class_names") and self.plugin.class_names:
            aquarium_names = ["aqua", "aquarium", "tank", "agua"]
            animal_names = ["zebrafish", "fish", "peixe"]

            found_aquarium = False
            found_animal = False

            for cid, name in self.plugin.class_names.items():
                name_lower = name.lower()
                if name_lower in aquarium_names:
                    self.aquarium_class_id = cid
                    found_aquarium = True
                if name_lower in animal_names:
                    self.animal_class_id = cid
                    found_animal = True

            # If we found an animal class at 0 but no aquarium class, likely a single-class model
            if found_animal and not found_aquarium and self.animal_class_id == 0:
                # Ensure we don't overlap if we default aquarium to 0
                self.aquarium_class_id = -1  # effectively disable aquarium detection by ID

            log.info(
                "detector.class_ids.resolved",
                aquarium_id=self.aquarium_class_id,
                animal_id=self.animal_class_id,
                plugin_classes=self.plugin.class_names,
            )

    @property
    def polygon(self) -> list[list[int]]:
        """Delegate to zones.polygon for backward compatibility."""
        if isinstance(self.zones, ZoneData):
            return self.zones.polygon
        return []

    @property
    def roi_polygons(self) -> list[list[list[int]]]:
        """Delegate to zones.roi_polygons for backward compatibility."""
        if isinstance(self.zones, ZoneData):
            return self.zones.roi_polygons
        return []

    @property
    def roi_names(self) -> list[str]:
        """Delegate to zones.roi_names for backward compatibility."""
        if isinstance(self.zones, ZoneData):
            return self.zones.roi_names
        return []

    @property
    def roi_colors(self) -> list[tuple[int, int, int]]:
        """Delegate to zones.roi_colors for backward compatibility."""
        if isinstance(self.zones, ZoneData):
            return self.zones.roi_colors
        return []

    def set_zones(
        self, zones: ZoneData | MultiAquariumZoneData, actual_width: int, actual_height: int
    ) -> None:
        """
        Set the detection zones and scales them to the current video resolution.

        Args:
            zones (ZoneData): The zone configuration object.
            actual_width (int): The width of the video/camera frame to scale to.
            actual_height (int): The height of the video/camera frame to scale to.
        """
        if actual_width <= 0 or actual_height <= 0:
            raise ValueError(
                "Actual dimensions must be positive. "
                f"set_zones(zones, actual_width={actual_width}, actual_height={actual_height})"
            )

        self.zones = zones
        # Clear cache if zones are redefined, as scaling depends on zone data
        self._scaling_cache.clear()

        # Handle MultiAquariumZoneData vs ZoneData
        has_polygon = False
        polygon_points = 0
        roi_count = 0
        polygon_sample = "empty"
        is_multi = hasattr(self.zones, "aquariums")

        self._multi_aquarium_mode = is_multi

        if is_multi and hasattr(self.zones, "aquariums"):
            self._aquariums = self.zones.aquariums
            # Initialize trackers for each aquarium if not already present
            for aq in self._aquariums:
                if aq.id not in self._byte_trackers_multi:
                    if self.settings and hasattr(self.settings, "bytetrack"):
                        bt = self.settings.bytetrack
                        track_thresh = float(bt.track_threshold)
                        track_buffer = int(bt.track_buffer)
                        match_thresh = float(bt.match_threshold)
                        max_dist = float(getattr(bt, "max_center_distance", 400.0))
                        iou_thresh = float(getattr(bt, "iou_threshold", 0.05))
                    else:
                        # Defaults matching config.yaml
                        track_thresh = 0.25
                        track_buffer = 150
                        match_thresh = 0.95
                        max_dist = 400.0
                        iou_thresh = 0.05

                    # Get processing interval for correct Kalman filter dt
                    interval = 1
                    fps = 30
                    if self.settings and hasattr(self.settings, "video_processing"):
                        interval = (
                            getattr(self.settings.video_processing, "processing_interval", 1) or 1
                        )
                        fps = getattr(self.settings.video_processing, "fps", 30) or 30

                    # Create Args Namespace
                    tracker_args = SimpleNamespace(
                        track_thresh=track_thresh,
                        track_buffer=track_buffer,
                        match_thresh=match_thresh,
                        mot20=False,
                    )

                    # Create Tracker with all required parameters
                    try:
                        self._byte_trackers_multi[aq.id] = BYTETracker(
                            args=tracker_args,
                            frame_rate=fps,
                            use_hybrid_matching=True,
                            max_center_distance=max_dist,
                            processing_interval=interval,
                            iou_threshold=iou_thresh,
                            single_animal_mode=True,
                        )
                    except Exception as e:
                        log.error(
                            "detector.bytetracker_init_failed",
                            aquarium_id=aq.id,
                            error=str(e),
                            exc_info=True,
                        )
                        raise RuntimeError(
                            f"Falha ao inicializar ByteTracker para aquário {aq.id}: {e}"
                        ) from e
        else:
            self._aquariums = []

        self._update_scaling(actual_width, actual_height)

        # Collect stats for logging
        if is_multi and isinstance(self.zones, MultiAquariumZoneData):
            # Strict type check for MyPy
            multi_zones = self.zones
            polygon_points = sum(len(aq.polygon) for aq in multi_zones.aquariums)
            roi_count = sum(len(aq.roi_polygons) for aq in multi_zones.aquariums)
            has_polygon = bool(multi_zones.aquariums)
            if has_polygon:
                # Sample first aquarium
                polygon_sample = str(multi_zones.aquariums[0].polygon[:3])
        elif isinstance(self.zones, ZoneData):
            # Standard ZoneData
            single_zone = self.zones
            has_polygon = bool(single_zone.polygon)
            polygon_points = len(single_zone.polygon) if single_zone.polygon else 0
            roi_count = len(single_zone.roi_polygons) if single_zone.roi_polygons else 0
            if has_polygon:
                # Handle list of tuples or numpy array
                poly_np = np.array(single_zone.polygon)
                polygon_sample = poly_np[:3].tolist() if poly_np.size > 0 else "empty"
        else:
            # Fallback for unexpected state
            log.warning("detector.zones.unknown_type", type=type(self.zones))
            roi_count = 0
            polygon_points = 0
            has_polygon = False

        # DEBUG: Log zone setup with polygon details
        log.info(
            "detector.zones.set",
            roi_count=roi_count,
            polygon_points=polygon_points,
            has_polygon=has_polygon,
            scaled_polygon_sample=polygon_sample,
            actual_dimensions=(actual_width, actual_height),
            base_dimensions=(self.base_width, self.base_height),
            is_multi_aquarium=is_multi,
        )

        self._zones_configured = True
        self._last_width = actual_width
        self._last_height = actual_height
        self._single_subject_tracker.reset()

    def set_context(self, context: str) -> None:
        """
        Set the detection context.

        Args:
            context (str): 'tracking' or 'diagnostic'
        """
        if context in ("tracking", "diagnostic"):
            self._context = context
            log.info("detector.context.set", context=context)

    def set_aquarium_region_defined(self, defined: bool = True) -> None:
        """
        Set whether aquarium region has been defined.

        Args:
            defined (bool): True if aquarium region is defined
        """
        self._aquarium_region_defined = bool(defined)
        log.info("detector.aquarium_region_defined.set", defined=defined)

    def _update_scaling(self, actual_width: int, actual_height: int) -> None:
        """
        Update the coordinates of the polygon and squares based on the actual video resolution.

        Uses a cache to avoid redundant calculations.
        """
        cache_key = (actual_width, actual_height)
        if cache_key in self._scaling_cache:
            cached_data = self._scaling_cache[cache_key]
            self.scaled_polygon = cached_data["polygon"]
            self.scaled_roi_polygons = cached_data["roi_polygons"]
            log.debug("detector.scaling.cache.hit", key=cache_key)
            return

        # Handle MultiAquariumZoneData
        if hasattr(self.zones, "aquariums"):
            self._scaled_aquarium_polygons = {}
            scale_x = actual_width / self.base_width
            scale_y = actual_height / self.base_height

            # Scale each aquarium's polygon
            for aq in self.zones.aquariums:
                base_poly = np.array(aq.polygon, dtype=np.int32)
                if base_poly.size > 0:
                    if actual_width == self.base_width and actual_height == self.base_height:
                        scaled_poly = base_poly
                    else:
                        scaled_poly = (base_poly * [scale_x, scale_y]).astype(np.int32)
                    self._scaled_aquarium_polygons[aq.id] = scaled_poly

            # For backward compatibility / safe default, set main scaled_polygon to empty
            # or to the bounding box of all aquariums if needed.
            # For now, let's keep it empty to avoid confusion with single zone logic
            self.scaled_polygon = np.array([], dtype=np.int32)
            self.scaled_roi_polygons = []

            return

        # Single ZoneData Logic
        # Convert base polygons to numpy arrays for scaling
        base_polygon = np.array(self.zones.polygon, dtype=np.int32)
        base_roi_polygons = [np.array(p, dtype=np.int32) for p in self.zones.roi_polygons]

        # Handle empty polygon case (no zones defined)
        if base_polygon.size == 0:
            self.scaled_polygon = base_polygon
            self.scaled_roi_polygons = base_roi_polygons
        elif actual_width == self.base_width and actual_height == self.base_height:
            self.scaled_polygon = base_polygon
            self.scaled_roi_polygons = base_roi_polygons
        else:
            scale_x = actual_width / self.base_width
            scale_y = actual_height / self.base_height
            self.scaled_polygon = (base_polygon * [scale_x, scale_y]).astype(np.int32)
            self.scaled_roi_polygons = [
                (p * [scale_x, scale_y]).astype(np.int32) for p in base_roi_polygons
            ]

        # Store the newly calculated values in the cache
        self._scaling_cache[cache_key] = {
            "polygon": self.scaled_polygon,
            "roi_polygons": self.scaled_roi_polygons,
        }
        log.info(
            "detector.scaling.updated_and_cached",
            width=actual_width,
            height=actual_height,
        )

    def _is_inside_polygon(self, x1: int, y1: int, x2: int, y2: int, polygon: np.ndarray) -> bool:
        """
        Check if any of the 4 corners OR the center of the bounding box is inside the polygon.

        Returns False if the polygon is empty or invalid.
        """
        if polygon.size == 0:
            return False

        # Calculate all 5 points: 4 corners + center
        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2

        points_to_test = [
            (x1, y1),  # top-left
            (x2, y1),  # top-right
            (x2, y2),  # bottom-right
            (x1, y2),  # bottom-left
            (center_x, center_y),  # center
        ]

        # Return True if ANY of the 5 points is inside the polygon
        for point in points_to_test:
            if cv2.pointPolygonTest(polygon, point, False) >= 0:
                return True

        return False

    def bbox_hits_roi_polygon(
        self, x1: int, y1: int, x2: int, y2: int, roi_polygon: np.ndarray
    ) -> bool:
        """
        Return True if 4 corners OR center of bbox falls within roi_polygon
        (cv2.pointPolygonTest >= 0).

        This is a utility helper for future live ROI checking functionality.
        """
        if roi_polygon.size == 0:
            return False

        # Calculate all 5 points: 4 corners + center
        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2

        points_to_test = [
            (x1, y1),  # top-left
            (x2, y1),  # top-right
            (x2, y2),  # bottom-right
            (x1, y2),  # bottom-left
            (center_x, center_y),  # center
        ]

        # Return True if ANY of the 5 points is inside the polygon
        for point in points_to_test:
            if cv2.pointPolygonTest(roi_polygon, point, False) >= 0:
                return True

        return False

    def _draw_zones(self, frame: np.ndarray) -> None:
        # Core drawing logic shifted to CanvasRenderer for UI
        # This keeps a lightweight version for diagnostic output
        if isinstance(self.zones, MultiAquariumZoneData):
            for aq in self.zones.aquariums:
                colors = getattr(aq, "roi_colors", [])
                log.debug("detector.drawing.multi", aq_id=aq.id, rois=len(colors))
        elif isinstance(self.zones, ZoneData):
            colors = getattr(self.zones, "roi_colors", [])
            log.debug("detector.drawing.single", rois=len(colors))

    def detect(
        self, frame: np.ndarray, project_type: str, conf_threshold: float | None = None
    ) -> tuple[list[tuple], str | None]:
        """Process a single frame for object detection and state tracking."""
        # Task 1.3: Frame validation to prevent crashes with invalid input
        if frame is None or not isinstance(frame, np.ndarray):
            raise ValueError("Frame must be a valid numpy array")

        if frame.size == 0:
            raise ValueError("Frame cannot be empty")

        if len(frame.shape) != 3 or frame.shape[2] != 3:
            raise ValueError(f"Frame must be HxWx3 (BGR image), got shape {frame.shape}")

        if not self._zones_configured:
            raise RuntimeError(
                "Must call set_zones() before detect(). "
                "Zones need video dimensions for proper scaling."
            )

        if self._last_width is not None and frame.shape[:2] != (
            self._last_height,
            self._last_width,
        ):
            log.warning(
                "detector.dimension_mismatch",
                expected=(self._last_width, self._last_height),
                actual=(frame.shape[1], frame.shape[0]),
                message=(
                    "Frame dimensions differ from dimensions used to set zones. "
                    "This may cause inaccurate detection scaling."
                ),
            )
        start_time = time.perf_counter()

        # Optimization: Crop the frame to the bounding box of the arena polygon
        if self.scaled_polygon.size > 0:
            x, y, w, h = cv2.boundingRect(self.scaled_polygon)

            # Clip to frame boundaries to avoid empty crops with negative coordinates
            img_h, img_w = frame.shape[:2]
            crop_x1 = max(0, x)
            crop_y1 = max(0, y)
            crop_x2 = min(img_w, x + w)
            crop_y2 = min(img_h, y + h)

            if crop_x2 <= crop_x1 or crop_y2 <= crop_y1:
                log.warning(
                    "detector.invalid_crop",
                    bbox=(x, y, w, h),
                    frame_size=(img_w, img_h),
                    message="Arena polygon bounding box is outside frame boundaries.",
                )
                return [], None

            cropped_frame = frame[crop_y1:crop_y2, crop_x1:crop_x2]

            # ✅ DEBUG: Log crop dimensions to verify detection area
            log.debug(
                "detector.frame_crop_applied",
                original_size=(frame.shape[1], frame.shape[0]),
                crop_bbox=(crop_x1, crop_y1, crop_x2 - crop_x1, crop_y2 - crop_y1),
                cropped_size=(cropped_frame.shape[1], cropped_frame.shape[0]),
                conf_threshold=conf_threshold,
            )

            # 1. Delegate actual detection to the loaded plugin on the cropped frame
            raw_detections = self.plugin.detect(cropped_frame, conf_threshold=conf_threshold)

            # ✅ DEBUG: Log raw detections from plugin
            if raw_detections:
                log.debug(
                    "detector.plugin_raw_detections",
                    count=len(raw_detections),
                    sample=str(raw_detections[:2]) if len(raw_detections) > 0 else "[]",
                )
            else:
                log.debug(
                    "detector.plugin_no_detections",
                    crop_size=(crop_x2 - crop_x1, crop_y2 - crop_y1),
                    conf_threshold=conf_threshold,
                )

            predictions: list[tuple[float, float, float, float, float, int, int]] = []
            for det in raw_detections:
                (
                    x1_crop,
                    y1_crop,
                    x2_crop,
                    y2_crop,
                    conf,
                    track_id,
                    class_id,
                ) = self._ensure_track_tuple(det)
                x1 = x1_crop + crop_x1
                y1 = y1_crop + crop_y1
                x2 = x2_crop + crop_x1
                y2 = y2_crop + crop_y1
                predictions.append(
                    (
                        float(x1),
                        float(y1),
                        float(x2),
                        float(y2),
                        float(conf),
                        int(track_id if track_id is not None else -1),
                        int(class_id),
                    )
                )
        else:
            # Fallback to detecting on the full frame if no polygon is defined
            predictions = []
            for det in self.plugin.detect(frame, conf_threshold=conf_threshold):
                x1, y1, x2, y2, conf, track_id, class_id = self._ensure_track_tuple(det)
                predictions.append(
                    (
                        float(x1),
                        float(y1),
                        float(x2),
                        float(y2),
                        float(conf),
                        int(track_id if track_id is not None else -1),
                        int(class_id),
                    )
                )

        # 2. Filter detections to only those inside the main polygon
        # This is still necessary for non-rectangular polygons
        # ✅ FIX: In diagnostic mode without polygon, accept ALL detections
        detections_in_polygon = []
        has_polygon = self.scaled_polygon.size > 0

        if len(predictions) > 0:
            log.debug(
                "detector.predictions_before_polygon_filter",
                count=len(predictions),
                has_polygon=has_polygon,
                sample=str(predictions[:3]),
            )

            # 🔍 DEBUG: Log decision flags for polygon filtering
            log.debug(
                "detector.polygon_filter_decision_flags",
                has_polygon=has_polygon,
                context=self._context,
                aquarium_defined=self._aquarium_region_defined,
                polygon_size=self.scaled_polygon.size,
                is_multi=self._multi_aquarium_mode,
            )

            # ✅ If no polygon defined and in diagnostic mode OR detecting aquarium,
            # accept all detections.
            # In multi-mode, we generally enforce polygon constraints
            # unless specifically detecting aquariums.
            should_filter = True
            if not has_polygon and not self._multi_aquarium_mode:
                if self._context == "diagnostic" or not self._aquarium_region_defined:
                    should_filter = False

            if not should_filter:
                log.debug(
                    "detector.no_polygon_accept_all",
                    accepting_all_detections=len(predictions),
                    reason="diagnostic_mode"
                    if self._context == "diagnostic"
                    else "aquarium_detection_phase",
                    context=self._context,
                    aquarium_defined=self._aquarium_region_defined,
                )
                detections_in_polygon = [
                    (x1, y1, x2, y2, confidence, int(track_id or -1), class_id)
                    for x1, y1, x2, y2, confidence, track_id, class_id in predictions
                ]
            else:
                # Normal polygon filtering - MUST filter by polygon
                # Support Multi-Aquarium Filtering
                for pred_tuple in predictions:
                    # predictions contains tuples: (x1, y1, x2, y2, confidence, track_id, class_id)
                    x1, y1, x2, y2, confidence, track_id, class_id = pred_tuple  # type: ignore
                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                    confidence = float(confidence)

                    is_inside = False

                    if self._multi_aquarium_mode and hasattr(self, "_scaled_aquarium_polygons"):
                        # Check against all aquarium polygons
                        for aq_id, poly in self._scaled_aquarium_polygons.items():
                            if self._is_inside_polygon(x1, y1, x2, y2, poly):
                                is_inside = True
                                # TODO (Phase 5): Attach aquarium ID to detection if tracking
                                # architecture supports it
                                break
                    elif self.scaled_polygon.size > 0:
                        # Check against main polygon
                        is_inside = self._is_inside_polygon(x1, y1, x2, y2, self.scaled_polygon)
                    else:
                        # No polygon defined but filtering required? Use default bound or skip?
                        # If we are here, should_filter is True but no polygon exists?
                        # This implies we should filter out EVERYTHING or logic error.
                        # Assuming strict constraint: if filtering is on and no polygon, reject.
                        is_inside = False

                    if is_inside:
                        detections_in_polygon.append(
                            (x1, y1, x2, y2, confidence, track_id, class_id)
                        )
                    else:
                        log.info(
                            "detector.filtered_outside_polygon",
                            bbox=(x1, y1, x2, y2),
                            track_id=track_id,
                            class_id=class_id,
                            is_multi=self._multi_aquarium_mode,
                        )

                # Log summary of polygon filtering
                log.debug(
                    "detector.polygon_filter_summary",
                    predictions_count=len(predictions),
                    passed_filter=len(detections_in_polygon),
                    filtered_out=len(predictions) - len(detections_in_polygon),
                    is_multi=self._multi_aquarium_mode,
                )
        else:
            log.info(
                "detector.no_predictions_from_model",
                has_polygon=has_polygon,
            )

        # Centralized filtering logic based on context
        # 🔍 DEBUG: Log current context during filtering
        log.debug(
            "detector.filtering_context_check",
            current_context=self._context,
            detections_in_polygon=len(detections_in_polygon),
            aquarium_defined=self._aquarium_region_defined,
        )

        filtered_detections = []
        if self._context == "diagnostic":
            # Diagnostic mode shows everything
            filtered_detections = detections_in_polygon
            log.debug(
                "detector.diagnostic_mode",
                detections_count=len(filtered_detections),
            )
        else:
            # Tracking mode
            # Tracking mode
            aquarium_class_id = self.aquarium_class_id
            zebrafish_class_id = self.animal_class_id

            target_class = (
                f"zebrafish({zebrafish_class_id})"
                if self._aquarium_region_defined
                else f"aquarium({aquarium_class_id})"
            )

            log.debug(
                "detector.filtering_by_class",
                detections_in_polygon=len(detections_in_polygon),
                aquarium_defined=self._aquarium_region_defined,
                target_class=target_class,
            )

            if not self._aquarium_region_defined:
                # Before arena is defined, show only aquarium detections (class_id 0)
                # ✅ FIX: Also accept Class 1 (Fish) if it's "huge" (likely misclassified tank)
                frame_area = 1280 * 720  # Default fallback
                if self._last_width and self._last_height:
                    frame_area = self._last_width * self._last_height

                for det_tuple in detections_in_polygon:
                    # det format: (x1, y1, x2, y2, confidence, track_id, class_id)
                    x1, y1, x2, y2, conf, track_id, class_id = det_tuple
                    det_area = (x2 - x1) * (y2 - y1)

                    is_valid_aquarium = False
                    if class_id == aquarium_class_id:
                        is_valid_aquarium = True
                    elif class_id == zebrafish_class_id:
                        # If it's class 1 but HUGE (> 10% of frame), it's likely the tank
                        # Lowered from 30% to 10% based on user logs showing tank is ~15%
                        if det_area > (frame_area * 0.10):
                            is_valid_aquarium = True
                            log.debug(
                                "detector.class_fallback_aquarium",
                                bbox=(x1, y1, x2, y2),
                                original_class=class_id,
                                new_class=aquarium_class_id,
                                det_area=det_area,
                                frame_area=frame_area,
                                ratio=det_area / frame_area,
                            )
                            # Morph to aquarium class
                            class_id = aquarium_class_id
                            det_tuple = (x1, y1, x2, y2, conf, track_id, class_id)

                    if is_valid_aquarium:
                        filtered_detections.append(det_tuple)
                    else:
                        log.debug(
                            "detector.filtered_by_class",
                            bbox=(det_tuple[0], det_tuple[1], det_tuple[2], det_tuple[3]),
                            class_id=class_id,
                            conf=det_tuple[4],
                            reason="aquarium_not_defined_target_class_0",
                            det_area=det_area,
                            ratio=det_area / frame_area,
                        )
            else:
                # After arena is defined, show only zebrafish detections (class_id 1)
                # ✅ FIX: Handle models that output class 0 for animals
                # If a detection is class 0 BUT is significantly smaller than the arena,
                # treat it as an animal (class 1).

                # Calculate arena area for comparison
                arena_area: float = 0.0
                if self.scaled_polygon.size > 0:
                    arena_area = float(cv2.contourArea(self.scaled_polygon))

                for det in detections_in_polygon:
                    # Cast to ensure int types for unpacking
                    x1_f, y1_f, x2_f, y2_f, conf, track_id, class_id = det  # type: ignore[misc]
                    x1, y1, x2, y2 = int(x1_f), int(y1_f), int(x2_f), int(y2_f)

                    # Calculate detection area
                    det_area = (x2 - x1) * (y2 - y1)

                    # Check if it's a "fake" aquarium (actually an animal)
                    # Criteria: Class 0 AND Area < 50% of arena
                    if class_id == aquarium_class_id and arena_area > 0:
                        if det_area < (arena_area * 0.5):
                            log.debug(
                                "detector.class_fallback_applied",
                                bbox=(x1, y1, x2, y2),
                                original_class=aquarium_class_id,
                                new_class=zebrafish_class_id,
                                det_area=det_area,
                                arena_area=arena_area,
                                ratio=det_area / arena_area,
                            )
                            # Modify class_id to zebrafish_class_id for this detection
                            class_id = zebrafish_class_id
                            # Update the tuple in the list
                            # (tuples are immutable, so we create new one)
                            det = (
                                float(x1),
                                float(y1),
                                float(x2),
                                float(y2),
                                float(conf),
                                track_id,
                                int(class_id),
                            )

                    if class_id == zebrafish_class_id:
                        filtered_detections.append(det)
                    else:
                        log.debug(
                            "detector.filtered_by_class",
                            bbox=(det[0], det[1], det[2], det[3]),
                            class_id=class_id,
                            reason="arena_defined",
                        )

        # Apply tracking based on mode
        if self._context == "diagnostic" or not self._aquarium_region_defined:
            # Diagnostic mode OR aquarium detection phase:
            # No tracking, preserve all detections as-is
            # - Diagnostic: single video analysis where we want raw detections
            # - Aquarium detection: need raw aquarium bboxes, ByteTracker would reject
            filtered_detections = [
                (
                    float(x1),
                    float(y1),
                    float(x2),
                    float(y2),
                    float(confidence),
                    int(track_id if track_id is not None else -1),
                    int(class_id),
                )
                for x1, y1, x2, y2, confidence, track_id, class_id in filtered_detections
            ]
            log.debug(
                "detector.skip_tracking",
                num_detections=len(filtered_detections),
                reason="diagnostic_mode"
                if self._context == "diagnostic"
                else "aquarium_detection_phase",
                context=self._context,
                aquarium_defined=self._aquarium_region_defined,
            )
        else:
            # Tracking Mode
            # Switch between ByteTrack and Simple SingleSubjectTracker
            use_bytetrack = self._should_use_bytetrack()

            if filtered_detections:
                confidences = [d[4] for d in filtered_detections]
                log.debug(
                    "detector.tracking.input",
                    confidences=confidences,
                    strategy="bytetrack" if use_bytetrack else "simple_hybrid",
                )

            if use_bytetrack:
                filtered_detections = self._apply_byte_tracking(filtered_detections, frame.shape)
                # BUG FIX #1: Validate track_id continuity after tracking
                self._validate_track_continuity(filtered_detections)
            else:
                # Use simple hybrid tracker (IoU + Distance)
                self._ensure_simple_tracker()
                filtered_detections = self._apply_simple_tracking(filtered_detections)

            log.debug(
                "detector.tracking.applied",
                num_detections=len(filtered_detections),
            )

        end_time = time.perf_counter()
        log.debug(
            "frame.processing.time",
            duration_ms=(end_time - start_time) * 1000,
            plugin=self.plugin.get_name(),
        )

        # 🔍 INFO: Log final detection count before return
        log.debug(
            "detector.detect.final_result",
            num_detections=len(filtered_detections),
            context=self._context,
            single_subject_mode=self._single_subject_mode,
        )

        # The command logic has been removed as it was tied to the old square ROIs
        command_to_send = None
        return filtered_detections, command_to_send

    def set_single_subject_mode(self, enabled: bool) -> None:
        """
        Toggle Single Animal Mode.

        When enabled, this now configures the ByteTracker to use the robust
        'Single Animal' logic (ID Resurrection + Immediate Activation) instead
        of switching to the legacy SingleSubjectTracker.
        """
        enabled = bool(enabled)
        if self._single_subject_mode == enabled:
            return

        self._single_subject_mode = enabled
        # Force re-init of ByteTracker to pick up the new mode
        self._byte_tracker = None
        self._byte_tracker_params = None

        log.info(
            "detector.single_subject_mode.changed",
            enabled=enabled,
            strategy="robust_bytetrack_single_animal",
        )

        if hasattr(self.plugin, "set_use_single_subject_mode"):
            try:
                self.plugin.set_use_single_subject_mode(enabled)
            except Exception:  # pragma: no cover - defensive
                log.warning("detector.plugin_update_failed", exc_info=True)

    def is_single_subject_mode(self) -> bool:
        """Expose the current single-subject tracking flag."""
        return self._single_subject_mode

    def reset_tracking_state(self) -> None:
        """Reset tracker state between videos.

        This resets:
        - Plugin tracking state
        - Single subject tracker
        - ByteTracker instance (single and multi-aquarium)
        - Multi-aquarium tracker dictionaries
        - Global track ID counter (so IDs start from 1 for each new video)
        """
        if hasattr(self.plugin, "reset_tracking_state"):
            try:
                self.plugin.reset_tracking_state()
            except Exception:  # pragma: no cover - defensive
                log.warning("detector.reset_tracking_state.plugin_failed", exc_info=True)
        self._single_subject_tracker.reset()
        self._byte_tracker = None
        self._byte_tracker_params = None

        # Clear multi-aquarium trackers
        self._byte_trackers_multi.clear()
        self._single_subject_trackers_multi.clear()
        if hasattr(self, "_multi_tracker_params"):
            self._multi_tracker_params = None

        # Reset global track ID counter so new videos start with ID=1
        from zebtrack.tracker.basetrack import BaseTrack

        BaseTrack.reset_id_counter()
        log.debug("detector.reset_tracking_state.id_counter_reset")

    def clear_cache(self) -> None:
        """Clear the internal scaling cache to free memory."""
        self._scaling_cache.clear()
        log.debug("detector.cache.cleared")

    @staticmethod
    def _ensure_track_tuple(
        detection: tuple,
    ) -> tuple[float, float, float, float, float, int | None, int]:
        if len(detection) == 5:
            x1, y1, x2, y2, confidence = detection
            track_id = None
            class_id = 0  # Default class if not provided
        elif len(detection) == 6:
            x1, y1, x2, y2, confidence, track_id = detection
            class_id = 0  # Default class if not provided
        else:
            x1, y1, x2, y2, confidence, track_id, class_id = detection[:7]
        return (
            float(x1),
            float(y1),
            float(x2),
            float(y2),
            float(confidence),
            track_id,
            int(class_id),
        )

    def _apply_simple_tracking(self, detections: list[tuple]) -> list[tuple]:
        """Apply simple SingleSubjectTracker (IoU+Distance) to detections.

        Used when ByteTrack is disabled. Assigns ID=1 to the best detection.
        """
        if not detections:
            self._single_subject_tracker.reset()
            return []

        # Convert to expected format for SingleSubjectTracker if needed
        # SingleSubjectTracker.assign takes sequence of detections and returns tracked
        tracked = self._single_subject_tracker.assign(detections)

        # If SingleSubjectTracker returned something, it's just the best match
        # We might want to pass through other detections as untracked?
        # Typically SingleSubjectTracker returns a list with 1 item or empty.

        return tracked

    def _apply_simple_tracking_multi(
        self,
        detections: list[tuple],
        tracker: SingleSubjectTracker,
    ) -> list[tuple]:
        """Apply SingleSubjectTracker for multi-aquarium mode (one per aquarium).

        Args:
            detections: List of detection tuples.
            tracker: The SingleSubjectTracker instance for this aquarium.

        Returns:
            List of tracked detection tuples (usually 1 item).
        """
        if not detections:
            tracker.reset()
            return []

        return tracker.assign(detections)

    def _apply_byte_tracking(
        self, detections: list[tuple], frame_shape: tuple[int, int, int]
    ) -> list[tuple]:
        log.debug(
            "detector.bytetrack.input",
            num_detections=len(detections),
            frame_shape=frame_shape,
        )

        if not detections:
            tracker = self._ensure_byte_tracker()
            if tracker is not None:
                empty = np.empty((0, 5), dtype=np.float32)
                frame_dims = (frame_shape[0], frame_shape[1])
                tracker.update(
                    empty,
                    frame_dims,
                    frame_dims,  # Same dimensions to avoid scaling
                )
            log.debug("detector.bytetrack.output", num_tracks=0, reason="no_input_detections")
            return []

        tracker = self._ensure_byte_tracker()
        if tracker is None:
            log.warning("detector.bytetrack.tracker_init_failed")
            return [
                (
                    int(x1),
                    int(y1),
                    int(x2),
                    int(y2),
                    float(confidence),
                    None,
                    int(class_id),
                )
                for x1, y1, x2, y2, confidence, track_id, class_id in detections
            ]

        det_array = np.array(
            [
                [float(x1), float(y1), float(x2), float(y2), float(confidence)]
                for x1, y1, x2, y2, confidence, _, _ in detections
            ],
            dtype=np.float32,
        )

        # CRITICAL FIX: Pass the same dimensions for both img_info and img_size
        # ByteTracker internally divides bboxes by scale = min(img_size/img_info)
        # Since our detections are ALREADY in frame coordinates (not model coordinates),
        # we must pass identical values to get scale=1.0 (no scaling)
        #
        # Bug history: Previously passed model_input_shape=(640,640) which caused
        # scale = min(640/720, 640/1280) = 0.5, so bboxes /= 0.5 → multiplied by 2!
        # This made detection (642,360) become (1284,720) - completely wrong!
        frame_dims = (frame_shape[0], frame_shape[1])  # (height, width)

        log.debug(
            "detector.bytetrack.calling_update",
            det_array_shape=det_array.shape,
            frame_dims=frame_dims,
            img_size_passed=frame_dims,
        )

        tracks = tracker.update(
            det_array,
            frame_dims,
            frame_dims,  # Pass same dimensions to avoid scaling (scale=1.0)
        )

        log.debug(
            "detector.bytetrack.update_result",
            num_input_detections=len(detections),
            num_output_tracks=len(tracks),
        )

        # Create a proper mapping of tracks to class_ids based on IoU with original detections
        # Build a mapping: track bbox -> best matching detection's class_id
        # IMPORTANT: We use the ORIGINAL detection coordinates (not track.tlbr)
        # because the Kalman filter can drift the position outside the polygon.
        # We only take the track_id from ByteTracker.
        results: list[tuple] = []
        for track in tracks:
            track_bbox = track.tlbr  # (x1, y1, x2, y2) - Kalman-filtered position

            # Find the detection with highest IoU overlap with this track
            best_iou = 0.0
            best_class_id = 0  # Default class
            best_det = None

            for det in detections:
                det_x1, det_y1, det_x2, det_y2, _det_conf, _, det_class_id = det

                # Calculate IoU between track bbox and detection bbox
                iou = self._calculate_iou(
                    track_bbox[0],
                    track_bbox[1],
                    track_bbox[2],
                    track_bbox[3],
                    det_x1,
                    det_y1,
                    det_x2,
                    det_y2,
                )

                if iou > best_iou:
                    best_iou = iou
                    best_class_id = det_class_id
                    best_det = det

            # Use ORIGINAL detection coordinates, not Kalman-filtered track position
            # This prevents polygon filtering issues when Kalman drifts outside
            if best_det is not None and best_iou > 0.1:
                # Use original detection bbox
                x1, y1, x2, y2 = best_det[0], best_det[1], best_det[2], best_det[3]
                confidence = best_det[4]

                log.debug(
                    "detector.bytetrack.using_original_detection",
                    track_bbox=(
                        int(track_bbox[0]),
                        int(track_bbox[1]),
                        int(track_bbox[2]),
                        int(track_bbox[3]),
                    ),
                    original_det=(x1, y1, x2, y2),
                    iou=best_iou,
                    track_id=track.track_id,
                )
            else:
                # Fallback to track bbox if no matching detection (shouldn't happen often)
                x1, y1, x2, y2 = track_bbox
                confidence = track.score

                log.warning(
                    "detector.bytetrack.no_matching_detection",
                    track_bbox=(int(x1), int(y1), int(x2), int(y2)),
                    best_iou=best_iou,
                    track_id=track.track_id,
                )

            results.append(
                (
                    int(x1),
                    int(y1),
                    int(x2),
                    int(y2),
                    float(confidence),
                    int(track.track_id),
                    int(best_class_id),
                )
            )

        # Log final ByteTrack output
        log.debug(
            "detector.bytetrack.output",
            num_input_detections=len(detections),
            num_output_tracks=len(tracks),
            num_results=len(results),
        )

        # 🔧 FIX: When ByteTracker returns no tracks but we have detections,
        # return the detections with track_id=None to preserve detection data.
        # This happens when:
        # 1. Frame skip is too high (e.g., processing every 10th frame)
        # 2. Object moves too fast between frames for IoU matching
        # 3. Track is in "unconfirmed" state waiting for confirmation
        if len(results) == 0 and len(detections) > 0:
            # In single-subject mode we must always emit an ID;
            # fall back to best detection with ID=1
            if self._single_subject_mode:
                best_det = max(detections, key=lambda d: d[4])
                log.debug(
                    "detector.bytetrack.single_subject_fallback_id1",
                    num_detections=len(detections),
                    chosen_confidence=float(best_det[4]),
                    message="ByteTracker returned no tracks; forcing ID=1 on best detection",
                )
                results = [
                    (
                        int(best_det[0]),
                        int(best_det[1]),
                        int(best_det[2]),
                        int(best_det[3]),
                        float(best_det[4]),
                        1,
                        int(best_det[6]),
                    )
                ]
            else:
                log.debug(
                    "detector.bytetrack.passthrough_untracked",
                    num_detections=len(detections),
                    reason="bytetracker_returned_no_tracks_but_detections_exist",
                )
                # Return detections with track_id=None (untracked but valid detections)
                results = [
                    (
                        int(det[0]),  # x1
                        int(det[1]),  # y1
                        int(det[2]),  # x2
                        int(det[3]),  # y2
                        float(det[4]),  # confidence
                        None,  # track_id = None (untracked)
                        int(det[6]),  # class_id
                    )
                    for det in detections
                ]

        # 🔧 FIX: Re-filter tracked positions by polygon
        # ByteTracker's Kalman filter can predict positions OUTSIDE the arena,
        # so we must re-validate that track positions are still inside the polygon
        if self.scaled_polygon.size > 0:
            results_before_filter = len(results)
            filtered_results = []
            for det in results:
                x1, y1, x2, y2 = det[0], det[1], det[2], det[3]
                is_inside = self._is_inside_polygon(x1, y1, x2, y2, self.scaled_polygon)
                if is_inside:
                    filtered_results.append(det)
                else:
                    # Log detailed info about filtered detections for debugging
                    center_x, center_y = (x1 + x2) / 2, (y1 + y2) / 2
                    log.warning(
                        "detector.bytetrack.post_filter_rejected",
                        bbox=(x1, y1, x2, y2),
                        center=(center_x, center_y),
                        track_id=det[5],
                        reason="track_outside_polygon",
                    )

            results = filtered_results
            filtered_count = results_before_filter - len(results)
            if filtered_count > 0:
                log.info(
                    "detector.bytetrack.post_filter_applied",
                    before=results_before_filter,
                    after=len(results),
                    filtered_out=filtered_count,
                    reason="tracks_moved_outside_polygon_by_kalman_filter",
                )

        return results

    def _validate_track_continuity(self, detections: list[tuple]) -> None:
        """
        Validate track_id continuity and log warnings for gaps.

        BUG FIX #1: Detects missing track IDs which may indicate tracking issues
        or object loss. This helps identify potential problems with ByteTracker.

        Args:
            detections: List of (x1, y1, x2, y2, confidence, track_id, class_id) tuples
        """
        if not detections:
            return

        # Extract track_ids, filtering out None values
        track_ids = [d[5] for d in detections if d[5] is not None]

        if not track_ids:
            return  # No valid track_ids to validate

        # Check for gaps in track_id sequence
        min_id, max_id = min(track_ids), max(track_ids)
        expected_ids = set(range(min_id, max_id + 1))
        actual_ids = set(track_ids)
        missing_ids = expected_ids - actual_ids

        if missing_ids:
            log.warning(
                "detector.track_id_gaps_detected",
                missing_track_ids=sorted(missing_ids),
                present_track_ids=sorted(actual_ids),
                total_detections=len(detections),
                message=(
                    "Gaps in track_id sequence detected. This may indicate: "
                    "(1) Objects temporarily lost by tracker, "
                    "(2) Objects left the frame, or "
                    "(3) ByteTracker configuration issues."
                ),
            )

        # Additional validation: Check for duplicate track_ids (shouldn't happen)
        if len(track_ids) != len(actual_ids):
            duplicate_ids = [tid for tid in actual_ids if track_ids.count(tid) > 1]
            log.error(
                "detector.duplicate_track_ids",
                duplicate_track_ids=duplicate_ids,
                total_detections=len(detections),
                message="Multiple detections with same track_id in single frame!",
            )

    def _calculate_iou(
        self,
        x1_a: float,
        y1_a: float,
        x2_a: float,
        y2_a: float,
        x1_b: float,
        y1_b: float,
        x2_b: float,
        y2_b: float,
    ) -> float:
        """Calculate Intersection over Union (IoU) between two bounding boxes."""
        # Calculate intersection
        inter_x1 = max(x1_a, x1_b)
        inter_y1 = max(y1_a, y1_b)
        inter_x2 = min(x2_a, x2_b)
        inter_y2 = min(y2_a, y2_b)

        if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
            return 0.0

        inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)

        # Calculate union
        area_a = (x2_a - x1_a) * (y2_a - y1_a)
        area_b = (x2_b - x1_b) * (y2_b - y1_b)
        union_area = area_a + area_b - inter_area

        if union_area <= 0:
            return 0.0

        return inter_area / union_area

    def _ensure_simple_tracker(self) -> SingleSubjectTracker:
        """Ensure SingleSubjectTracker is up to date with settings."""
        iou_thresh = self._get_iou_threshold()
        max_dist = self._get_max_center_distance()

        # Re-initialize if params changed
        if (
            self._single_subject_tracker.iou_threshold != iou_thresh
            or self._single_subject_tracker.max_center_distance != max_dist
        ):
            log.info("detector.simple_tracker.updating", iou=iou_thresh, dist=max_dist)
            self._single_subject_tracker = SingleSubjectTracker(
                track_id=1, iou_threshold=iou_thresh, max_center_distance=max_dist
            )
        return self._single_subject_tracker

    def _ensure_byte_tracker(self) -> BYTETracker | None:
        track_thresh = self._get_track_threshold()
        match_thresh = self._get_match_threshold()
        track_buffer = self._get_track_buffer()
        max_center_distance = self._get_max_center_distance()
        iou_threshold = self._get_iou_threshold()
        use_bytetrack = self._should_use_bytetrack()

        # Determine single_animal_mode:
        # 1. Priority: Explicit mode set via set_single_subject_mode()
        # 2. Fallback: Global settings from config.yaml
        single_animal_mode = self._single_subject_mode
        if not single_animal_mode and self.settings and hasattr(self.settings, "video_processing"):
            single_animal_mode = getattr(
                self.settings.video_processing, "single_animal_per_aquarium", False
            )

        # Include single_animal_mode and use_bytetrack in params to trigger re-init if it changes
        params = (
            track_thresh,
            match_thresh,
            track_buffer,
            max_center_distance,
            iou_threshold,
            single_animal_mode,
            use_bytetrack,
        )
        if self._byte_tracker is not None and self._byte_tracker_params == params:
            return self._byte_tracker

        if not use_bytetrack:
            return None

        try:
            args = SimpleNamespace(
                track_thresh=track_thresh,
                match_thresh=match_thresh,
                track_buffer=track_buffer,
                mot20=False,
            )

            # Get processing_interval from settings (critical for Kalman filter dt)
            if self.settings and hasattr(self.settings, "video_processing"):
                processing_interval = (
                    getattr(self.settings.video_processing, "processing_interval", 1) or 1
                )
            else:
                processing_interval = 1

            log.info(
                "detector.bytetrack.initializing",
                track_thresh=track_thresh,
                match_thresh=match_thresh,
                track_buffer=track_buffer,
                max_center_distance=max_center_distance,
                iou_threshold=iou_threshold,
                use_hybrid_matching=True,
                processing_interval=processing_interval,
                single_animal_mode=single_animal_mode,
            )

            # Get FPS from settings or use default
            if self.settings and hasattr(self.settings, "video_processing"):
                frame_rate = getattr(self.settings.video_processing, "fps", 30) or 30
            else:
                frame_rate = 30

            # Enable hybrid matching for sparse frame processing
            # Pass processing_interval to ByteTracker for correct Kalman filter dt
            # This is CRITICAL for stable track IDs when processing every N frames
            self._byte_tracker = BYTETracker(
                args=args,
                frame_rate=frame_rate,
                use_hybrid_matching=True,
                max_center_distance=max_center_distance,
                processing_interval=processing_interval,
                iou_threshold=iou_threshold,
                single_animal_mode=single_animal_mode,
            )
            self._byte_tracker_params = params
        except Exception:  # pragma: no cover - defensive
            log.warning("detector.bytetrack.init_failed", exc_info=True)
            self._byte_tracker = None
            self._byte_tracker_params = None

        return self._byte_tracker

    def _get_max_center_distance(self) -> float:
        """Get max center distance for hybrid matching.

        This parameter controls how far (in pixels) a detection can be from
        the predicted track position and still be considered a match.

        Default: 400.0 pixels (~13 body lengths for 30px zebrafish) - matches config.yaml
        """
        if self.settings and hasattr(self.settings, "bytetrack"):
            return float(getattr(self.settings.bytetrack, "max_center_distance", 400.0))
        return 400.0

    def _get_track_threshold(self) -> float:
        value = getattr(self.plugin, "track_threshold", None)
        if value is None:
            if self.settings and hasattr(self.settings, "bytetrack"):
                return float(getattr(self.settings.bytetrack, "track_threshold", 0.25))
            return 0.25  # Default matching config.yaml
        return float(value)

    def _get_match_threshold(self) -> float:
        value = getattr(self.plugin, "match_threshold", None)
        if value is None:
            if self.settings and hasattr(self.settings, "bytetrack"):
                return float(getattr(self.settings.bytetrack, "match_threshold", 0.95))
            return 0.95  # Default matches config.yaml - higher = more permissive
        return float(value)

    def _get_track_buffer(self) -> int:
        """Get track buffer size from settings or plugin."""
        value = getattr(self.plugin, "track_buffer", None)
        if value is None:
            if self.settings and hasattr(self.settings, "bytetrack"):
                return int(getattr(self.settings.bytetrack, "track_buffer", 150))
            return 150  # Default matches config.yaml - survives ~50 detection cycles
        try:
            return int(value)
        except (TypeError, ValueError):
            return 150

    def _get_iou_threshold(self) -> float:
        """Get IoU threshold for hybrid matching.

        Lower values make the tracker prefer center distance over IoU,
        which is better for small, fast-moving objects.
        """
        if self.settings and hasattr(self.settings, "bytetrack"):
            return float(getattr(self.settings.bytetrack, "iou_threshold", 0.05))
        return 0.05  # Low default for small objects

    def _resolve_model_input_shape(self) -> tuple[int, int]:
        try:
            shape = getattr(self.plugin, "model_input_shape", None)
            if shape and len(shape) == 2:
                return int(shape[0]), int(shape[1])
        except Exception:  # pragma: no cover - defensive
            log.debug("detector.model_input_shape.fallback", exc_info=True)
        return int(self.base_height), int(self.base_width)

    def _restore_trackers(self, previous_state: dict[str, Any]) -> None:
        """
        Restore tracker states from a previous state dictionary.

        This is used when switching between single and multi-aquarium modes
        or when re-initializing the detector without losing tracking history.
        """
        # Restore single subject tracker state
        # NOTE: SingleSubjectTracker does not currently support restore_state
        # Commenting out until the method is implemented or state tracking is removed
        # if "single_subject_tracker_state" in previous_state:
        #     self._single_subject_tracker.restore_state(
        #         previous_state["single_subject_tracker_state"]
        #     )
        #     log.debug("detector.restore_trackers.single_subject_tracker_restored")

        # Restore ByteTracker state
        if "byte_tracker_state" in previous_state and self._byte_tracker is not None:
            # NOTE: BYTETracker does not currently implement restore_state
            if hasattr(self._byte_tracker, "restore_state"):
                self._byte_tracker.restore_state(previous_state["byte_tracker_state"])  # type: ignore[attr-defined]
            log.debug("detector.restore_trackers.byte_tracker_restored")

        # Restore multi-aquarium trackers
        if "byte_trackers_multi_state" in previous_state:
            for aq_id, state in previous_state["byte_trackers_multi_state"].items():
                if aq_id in self._byte_trackers_multi:
                    tracker = self._byte_trackers_multi[aq_id]
                    if hasattr(tracker, "restore_state"):
                        tracker.restore_state(state)  # type: ignore[attr-defined]
                    log.debug("detector.restore_trackers.multi_byte_tracker_restored", aq_id=aq_id)
                else:
                    log.warning("detector.restore_trackers.multi_byte_tracker_missing", aq_id=aq_id)

        if "single_subject_trackers_multi_state" in previous_state:
            for aq_id, state in previous_state["single_subject_trackers_multi_state"].items():
                if aq_id in self._single_subject_trackers_multi:
                    tracker = self._single_subject_trackers_multi[aq_id]
                    if hasattr(tracker, "restore_state"):
                        tracker.restore_state(state)  # type: ignore[attr-defined]
                    log.debug(
                        "detector.restore_trackers.multi_simple_tracker_restored", aq_id=aq_id
                    )
                else:
                    log.warning(
                        "detector.restore_trackers.multi_simple_tracker_missing", aq_id=aq_id
                    )

        # Restore global track ID counter
        if "basetrack_id_counter" in previous_state:
            from zebtrack.tracker.basetrack import BaseTrack

            BaseTrack.set_id_counter(previous_state["basetrack_id_counter"])
            log.debug(
                "detector.restore_trackers.basetrack_id_counter_restored",
                counter=previous_state["basetrack_id_counter"],
            )

        log.info("detector.restore_trackers.completed")

    def draw_overlay(self, frame: np.ndarray, detections: list[tuple]) -> None:
        """Draws detection overlays on the frame."""
        # Draw the ROI polygons
        for i, polygon in enumerate(self.scaled_roi_polygons):
            # Use property delegate to access roi_colors
            if i < len(self.roi_colors):
                color = self.roi_colors[i]
                cv2.polylines(frame, [polygon], isClosed=True, color=color, thickness=2)

        # Draw the processing area polygon
        if self.scaled_polygon.size > 0:
            cv2.polylines(
                frame,
                [self.scaled_polygon],
                isClosed=True,
                color=(0, 0, 0),
                thickness=1,
            )

        # Draw the bounding boxes for detections
        for detection in detections:
            # Handle both 6-element (old) and 7-element (new) tuples
            if len(detection) == 6:
                x1, y1, x2, y2, confidence, track_id = detection
            else:
                x1, y1, x2, y2, confidence, track_id, _ = detection
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 255), 2)
            label = f"ID: {track_id} ({int(confidence * 100)}%)"
            cv2.putText(
                frame,
                label,
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 0, 255),
                2,
            )

    # =========================================================================
    # Multi-Aquarium Mode Methods
    # =========================================================================

    def _should_use_bytetrack(self) -> bool:
        """Check if ByteTrack should be used based on settings."""
        if self.settings and hasattr(self.settings, "tracking"):
            return self.settings.tracking.use_bytetrack
        return True

    def set_multi_aquarium_zones(
        self,
        aquariums: list[AquariumData],
        actual_width: int,
        actual_height: int,
    ) -> None:
        """Configure zones for multiple aquariums with independent tracking.

        Sets up separate trackers (ByteTracker or SingleSubjectTracker) for each
        aquarium to enable independent tracking. Track IDs are offset by
        aquarium_id * 1000.

        Args:
            aquariums: List of AquariumData objects (max 2).
            actual_width: Actual video frame width for scaling.
            actual_height: Actual video frame height for scaling.

        Raises:
            ValueError: If more than 2 aquariums or invalid dimensions.
        """
        if len(aquariums) > 2:
            raise ValueError("Maximum of 2 aquariums supported")

        if actual_width <= 0 or actual_height <= 0:
            raise ValueError(f"Invalid dimensions: width={actual_width}, height={actual_height}")

        self._multi_aquarium_mode = True
        self._aquariums = aquariums

        # Calculate scaling factors
        scale_x = actual_width / self.base_width
        scale_y = actual_height / self.base_height

        # Validate all aquarium polygons before proceeding
        for aq in aquariums:
            if not aq.polygon or len(aq.polygon) < 3:
                log.error(
                    "detector.multi_aquarium.invalid_polygon",
                    aquarium_id=aq.id,
                    polygon_points=len(aq.polygon) if aq.polygon else 0,
                )
                polygon_count = len(aq.polygon) if aq.polygon else 0
                raise ValueError(
                    f"Aquário {aq.id} possui polígono inválido: "
                    f"mínimo 3 pontos, encontrado {polygon_count}"
                )

        use_bytetrack = self._should_use_bytetrack()

        # Initialize trackers for each aquarium
        for aq in aquariums:
            if use_bytetrack:
                # Create independent ByteTracker for this aquarium
                tracker_args = SimpleNamespace(
                    track_thresh=self._get_track_threshold(),
                    match_thresh=self._get_match_threshold(),
                    track_buffer=self._get_track_buffer(),
                    mot20=False,
                )

                # Get processing_interval (critical for Kalman filter dt)
                if self.settings and hasattr(self.settings, "video_processing"):
                    processing_interval = (
                        getattr(self.settings.video_processing, "processing_interval", 1) or 1
                    )
                else:
                    processing_interval = 1

                # Get FPS
                if self.settings and hasattr(self.settings, "video_processing"):
                    frame_rate = getattr(self.settings.video_processing, "fps", 30) or 30
                else:
                    frame_rate = 30

                try:
                    self._byte_trackers_multi[aq.id] = BYTETracker(
                        args=tracker_args,
                        frame_rate=frame_rate,
                        use_hybrid_matching=True,
                        max_center_distance=self._get_max_center_distance(),
                        processing_interval=processing_interval,
                        iou_threshold=self._get_iou_threshold(),
                        single_animal_mode=True,  # Each aquarium has exactly 1 animal
                    )
                    # Clear simple tracker if exists
                    if aq.id in self._single_subject_trackers_multi:
                        del self._single_subject_trackers_multi[aq.id]

                except Exception as e:
                    log.error(
                        "detector.multi_aquarium.bytetracker_init_failed",
                        aquarium_id=aq.id,
                        error=str(e),
                        exc_info=True,
                    )
                    raise RuntimeError(
                        f"Falha ao inicializar ByteTracker para aquário {aq.id}: {e}"
                    ) from e

                log.debug(
                    "detector.multi_aquarium.tracker_created",
                    aquarium_id=aq.id,
                    type="ByteTracker",
                    single_animal_mode=True,
                )
            else:
                # Initialize SingleSubjectTracker
                iou_thresh = self._get_iou_threshold()
                max_dist = self._get_max_center_distance()

                self._single_subject_trackers_multi[aq.id] = SingleSubjectTracker(
                    track_id=1, iou_threshold=iou_thresh, max_center_distance=max_dist
                )
                # Clear ByteTracker if exists
                if aq.id in self._byte_trackers_multi:
                    del self._byte_trackers_multi[aq.id]

                log.debug(
                    "detector.multi_aquarium.tracker_created",
                    aquarium_id=aq.id,
                    type="SingleSubjectTracker",
                    iou=iou_thresh,
                    dist=max_dist,
                )

            # Scale the main polygon
            if aq.polygon:
                polygon_np = np.array(aq.polygon, dtype=np.float32)
                self._scaled_aquarium_polygons[aq.id] = (polygon_np * [scale_x, scale_y]).astype(
                    np.int32
                )
            else:
                self._scaled_aquarium_polygons[aq.id] = np.array([], dtype=np.int32)

            # Scale ROI polygons
            scaled_rois = []
            for roi in aq.roi_polygons:
                roi_np = np.array(roi, dtype=np.float32)
                scaled_roi = (roi_np * [scale_x, scale_y]).astype(np.int32)
                scaled_rois.append(scaled_roi)
            self._scaled_aquarium_roi_polygons[aq.id] = scaled_rois

        self._zones_configured = True
        self._last_width = actual_width
        self._last_height = actual_height
        self._aquarium_region_defined = True

        log.info(
            "detector.multi_aquarium.zones_set",
            aquarium_count=len(aquariums),
            dimensions=(actual_width, actual_height),
            aquarium_ids=[aq.id for aq in aquariums],
            tracker_type="ByteTrack" if use_bytetrack else "Simple",
        )

    def _ensure_multi_trackers(self) -> None:
        """Ensure multi-aquarium trackers are up to date with current settings.

        This method is exception-safe: if tracker creation fails mid-loop,
        the state remains consistent (old trackers are preserved).
        """
        use_bytetrack = self._should_use_bytetrack()

        # We use a combined params tuple to detect changes
        track_thresh = self._get_track_threshold()
        match_thresh = self._get_match_threshold()
        track_buffer = self._get_track_buffer()
        max_dist = self._get_max_center_distance()
        iou_thresh = self._get_iou_threshold()

        params = (use_bytetrack, track_thresh, match_thresh, track_buffer, max_dist, iou_thresh)

        if hasattr(self, "_multi_tracker_params") and self._multi_tracker_params == params:
            return

        log.info("detector.multi_trackers.updating", use_bytetrack=use_bytetrack)

        # Clean up orphaned trackers (aquariums no longer in list)
        current_aq_ids = {aq.id for aq in self._aquariums}
        orphaned_byte = [k for k in self._byte_trackers_multi if k not in current_aq_ids]
        orphaned_single = [
            k for k in self._single_subject_trackers_multi if k not in current_aq_ids
        ]
        for aq_id in orphaned_byte:
            del self._byte_trackers_multi[aq_id]
        for aq_id in orphaned_single:
            del self._single_subject_trackers_multi[aq_id]

        # Create new trackers in a temporary dict, then commit if all succeed
        new_byte_trackers: dict[int, BYTETracker] = {}
        new_single_trackers: dict[int, SingleSubjectTracker] = {}

        try:
            for aq in self._aquariums:
                if use_bytetrack:
                    tracker_args = SimpleNamespace(
                        track_thresh=track_thresh,
                        match_thresh=match_thresh,
                        track_buffer=track_buffer,
                        mot20=False,
                    )

                    # Contextual params
                    interval = 1
                    fps = 30
                    if self.settings and hasattr(self.settings, "video_processing"):
                        interval = (
                            getattr(self.settings.video_processing, "processing_interval", 1) or 1
                        )
                        fps = getattr(self.settings.video_processing, "fps", 30) or 30

                    new_byte_trackers[aq.id] = BYTETracker(
                        args=tracker_args,
                        frame_rate=fps,
                        use_hybrid_matching=True,
                        max_center_distance=max_dist,
                        processing_interval=interval,
                        iou_threshold=iou_thresh,
                        single_animal_mode=True,
                    )
                else:
                    new_single_trackers[aq.id] = SingleSubjectTracker(
                        track_id=1, iou_threshold=iou_thresh, max_center_distance=max_dist
                    )

            # All trackers created successfully - commit the changes
            if use_bytetrack:
                self._byte_trackers_multi.update(new_byte_trackers)
                for aq_id in new_byte_trackers:
                    if aq_id in self._single_subject_trackers_multi:
                        del self._single_subject_trackers_multi[aq_id]
            else:
                self._single_subject_trackers_multi.update(new_single_trackers)
                for aq_id in new_single_trackers:
                    if aq_id in self._byte_trackers_multi:
                        del self._byte_trackers_multi[aq_id]

            self._multi_tracker_params = dict(params) if params is not None else None

        except Exception as e:
            # Rollback: clear partially created trackers
            new_byte_trackers.clear()
            new_single_trackers.clear()
            log.error(
                "detector.multi_trackers.creation_failed",
                error=str(e),
                aquariums=[aq.id for aq in self._aquariums],
            )
            raise

    def detect_partitioned(
        self,
        frame: np.ndarray,
        project_type: str = "multi_aquarium",
    ) -> dict[int, list[tuple]]:
        """Execute detection and partition results by aquarium.

        Runs detection on the full frame, then assigns detections to
        aquariums based on centroid location. Each aquarium has independent
        tracking with offset track IDs.

        Args:
            frame: Input BGR frame.
            project_type: Project type string (not used, for API compatibility).

        Returns:
            Dictionary mapping aquarium_id to list of detection tuples:
            {aquarium_id: [(x1, y1, x2, y2, conf, track_id, class_id), ...]}
            Track IDs are offset: aquarium_id * 1000 + local_track_id

        Raises:
            RuntimeError: If detector not in multi-aquarium mode.
            ValueError: If frame is invalid.
        """
        if not self._multi_aquarium_mode:
            raise RuntimeError(
                "Detector is not in multi-aquarium mode. Call set_multi_aquarium_zones() first."
            )

        # Ensure trackers are synced with settings
        self._ensure_multi_trackers()

        # Validate frame
        if frame is None or not isinstance(frame, np.ndarray):
            raise ValueError("Frame must be a valid numpy array")

        if frame.size == 0:
            raise ValueError("Frame cannot be empty")

        if len(frame.shape) != 3 or frame.shape[2] != 3:
            raise ValueError(f"Frame must be HxWx3 (BGR), got shape {frame.shape}")

        # Execute detection on full frame
        raw_detections = self.plugin.detect(frame)

        # DEBUG: Log raw detections
        log.info(
            "detector.multi.raw_detections",
            count=len(raw_detections),
            detections=str([str(d) for d in raw_detections[:3]]),  # First 3 only
        )

        # Partition detections by aquarium
        partitioned: dict[int, list] = {aq.id: [] for aq in self._aquariums}

        for raw_det in raw_detections:
            det = self._ensure_track_tuple(raw_det)
            x1, y1, x2, y2, conf, _, class_id = det

            # Calculate centroid
            centroid = ((x1 + x2) / 2, (y1 + y2) / 2)

            # Find which aquarium contains this detection
            for aq in self._aquariums:
                polygon = self._scaled_aquarium_polygons.get(aq.id)
                if polygon is not None and polygon.size > 0:
                    if self._point_in_polygon(centroid, polygon):
                        partitioned[aq.id].append(det)
                        break
            else:
                # Detection not assigned to any aquarium - log warning
                log.warning(
                    "detector.partitioned.detection_unassigned",
                    centroid=centroid,
                    confidence=conf,
                    aquariums_checked=len(self._aquariums),
                )

        # DEBUG: Log partitioning results
        partition_counts = {aqid: len(dets) for aqid, dets in partitioned.items()}
        log.info("detector.multi.partitioning", counts=partition_counts)

        # Apply independent tracking per aquarium
        results: dict[int, list[tuple]] = {}
        use_bytetrack = self._should_use_bytetrack()

        for aq_id, detections in partitioned.items():
            if detections:
                if use_bytetrack:
                    # ByteTrack path
                    tracker = self._byte_trackers_multi.get(aq_id)
                    if tracker is None:
                        log.error(
                            "detector.partitioned.tracker_missing",
                            aquarium_id=aq_id,
                            available_trackers=list(self._byte_trackers_multi.keys()),
                        )
                        raise RuntimeError(
                            f"ByteTracker não inicializado para aquário {aq_id}. "
                            "Chame set_multi_aquarium_zones() primeiro."
                        )
                    tracked = self._apply_byte_tracking_multi(detections, tracker)
                else:
                    # Simple tracker path
                    simple_tracker = self._single_subject_trackers_multi.get(aq_id)
                    if simple_tracker is None:
                        # Fallback: maybe it was never initialized?
                        # Should have been in set_multi_aquarium_zones
                        log.error("detector.partitioned.simple_tracker_missing", aq_id=aq_id)
                        tracked = detections  # Just passthrough
                    else:
                        tracked = self._apply_simple_tracking_multi(detections, simple_tracker)

                # Offset track_id: aquarium_id * 1000 + local_track_id
                # CRITICAL: local_track_id must be < 1000 to prevent ID collisions
                offset_tracked = []
                for det in tracked:
                    x1, y1, x2, y2, conf, track_id, class_id = det
                    if track_id is not None:
                        if track_id >= 1000:
                            log.error(
                                "detector.partitioned.track_id_overflow",
                                aquarium_id=aq_id,
                                local_track_id=track_id,
                                msg="local_track_id >= 1000 causa colisão de IDs",
                            )
                            # Use modulo to prevent collision while preserving tracking
                            offset_id = aq_id * 1000 + (track_id % 1000)
                        else:
                            offset_id = aq_id * 1000 + track_id
                    else:
                        offset_id = None
                    offset_tracked.append((x1, y1, x2, y2, conf, offset_id, class_id))
                results[aq_id] = offset_tracked
            else:
                results[aq_id] = []

        log.debug(
            "detector.partitioned.results",
            aquarium_counts={aq_id: len(dets) for aq_id, dets in results.items()},
        )

        return results

    def _crop_aquarium_region(
        self,
        frame: np.ndarray,
        aquarium_id: int,
        padding: int = 10,
    ) -> tuple[np.ndarray, tuple[int, int, int, int]]:
        """Crop frame to aquarium bounding box for efficient inference.

        This optimization reduces the number of pixels processed by the
        detection model, improving performance by ~40% for dual-aquarium setups.

        Args:
            frame: Full input frame (BGR).
            aquarium_id: ID of the aquarium to crop.
            padding: Extra pixels around the bounding box (default: 10).

        Returns:
            Tuple of (cropped_frame, (x_offset, y_offset, crop_width, crop_height)).
            The offsets are used to adjust detection coordinates back to original frame.
        """
        polygon = self._scaled_aquarium_polygons.get(aquarium_id)
        if polygon is None or polygon.size == 0:
            # No polygon defined, return full frame
            h, w = frame.shape[:2]
            return frame, (0, 0, w, h)

        # Get bounding rectangle of the polygon
        x, y, w, h = cv2.boundingRect(polygon)

        # Add padding (clamp to frame bounds)
        frame_h, frame_w = frame.shape[:2]
        x1 = max(0, x - padding)
        y1 = max(0, y - padding)
        x2 = min(frame_w, x + w + padding)
        y2 = min(frame_h, y + h + padding)

        # Crop the frame
        cropped = frame[y1:y2, x1:x2]

        log.debug(
            "detector.crop_aquarium",
            aquarium_id=aquarium_id,
            original_size=(frame_w, frame_h),
            crop_box=(x1, y1, x2 - x1, y2 - y1),
            reduction_percent=round((1 - (x2 - x1) * (y2 - y1) / (frame_w * frame_h)) * 100, 1),
        )

        return cropped, (x1, y1, x2 - x1, y2 - y1)

    def detect_partitioned_optimized(
        self,
        frame: np.ndarray,
        use_cropping: bool = True,
    ) -> dict[int, list[tuple]]:
        """Execute optimized detection with per-aquarium cropping.

        This is an optimized version of detect_partitioned() that crops
        each aquarium region before running inference, reducing the
        number of pixels processed by ~50% for dual-aquarium setups.

        Args:
            frame: Input BGR frame.
            use_cropping: If True, crop each aquarium before inference.
                         If False, falls back to full-frame detection.

        Returns:
            Dictionary mapping aquarium_id to list of detection tuples:
            {aquarium_id: [(x1, y1, x2, y2, conf, track_id, class_id), ...]}
            Track IDs are offset: aquarium_id * 1000 + local_track_id

        Raises:
            RuntimeError: If detector not in multi-aquarium mode.
            ValueError: If frame is invalid.
        """
        if not self._multi_aquarium_mode:
            raise RuntimeError(
                "Detector is not in multi-aquarium mode. Call set_multi_aquarium_zones() first."
            )

        # Ensure trackers are synced with settings
        self._ensure_multi_trackers()

        # Validate frame
        if frame is None or not isinstance(frame, np.ndarray):
            raise ValueError("Frame must be a valid numpy array")

        if frame.size == 0:
            raise ValueError("Frame cannot be empty")

        if len(frame.shape) != 3 or frame.shape[2] != 3:
            raise ValueError(f"Frame must be HxWx3 (BGR), got shape {frame.shape}")

        if not use_cropping:
            # Fall back to original full-frame detection
            return self.detect_partitioned(frame)

        # Process each aquarium with cropped regions
        results: dict[int, list[tuple]] = {}
        use_bytetrack = self._should_use_bytetrack()

        for aq in self._aquariums:
            # Crop to aquarium region
            cropped, (offset_x, offset_y, _crop_w, _crop_h) = self._crop_aquarium_region(
                frame, aq.id
            )

            # Run detection on cropped region
            raw_detections = self.plugin.detect(cropped)

            # DEBUG: Log raw detections on crop
            log.debug(
                "detector.optimized.raw_crop",
                aquarium_id=aq.id,
                count=len(raw_detections),
                detections=str([str(d) for d in raw_detections[:3]]),
            )

            # Adjust coordinates back to original frame
            adjusted_detections = []
            for raw_det in raw_detections:
                det = self._ensure_track_tuple(raw_det)
                x1, y1, x2, y2, conf, _, class_id = det

                # Offset coordinates to original frame space
                x1_global = x1 + offset_x
                y1_global = y1 + offset_y
                x2_global = x2 + offset_x
                y2_global = y2 + offset_y

                # FILTER 1: Class ID Check
                if self.animal_class_id is not None and class_id != self.animal_class_id:
                    continue

                # FILTER: Ensure centroid is within the aquarium polygon
                # Cropping includes padding, so we might pick up objects just outside the zone
                centroid = ((x1_global + x2_global) / 2, (y1_global + y2_global) / 2)
                polygon = self._scaled_aquarium_polygons.get(aq.id)

                if polygon is not None and polygon.size > 0:
                    if not self._point_in_polygon(centroid, polygon):
                        continue

                adjusted_detections.append(
                    (x1_global, y1_global, x2_global, y2_global, conf, None, class_id)
                )

            # Apply tracking
            if adjusted_detections:
                if use_bytetrack:
                    # ByteTrack path
                    tracker = self._byte_trackers_multi.get(aq.id)
                    if tracker is None:
                        log.error(
                            "detector.partitioned_optimized.tracker_missing",
                            aquarium_id=aq.id,
                            available_trackers=list(self._byte_trackers_multi.keys()),
                        )
                        raise RuntimeError(
                            f"ByteTracker não inicializado para aquário {aq.id}. "
                            "Chame set_multi_aquarium_zones() primeiro."
                        )
                    tracked = self._apply_byte_tracking_multi(adjusted_detections, tracker)
                else:
                    # Simple tracker path
                    simple_tracker = self._single_subject_trackers_multi.get(aq.id)
                    if simple_tracker is None:
                        log.error(
                            "detector.partitioned_optimized.simple_tracker_missing", aq_id=aq.id
                        )
                        tracked = adjusted_detections
                    else:
                        tracked = self._apply_simple_tracking_multi(
                            adjusted_detections, simple_tracker
                        )

                # Offset track_id
                offset_tracked = []
                for det in tracked:
                    x1, y1, x2, y2, conf, track_id, class_id = det
                    if track_id is not None:
                        if track_id >= 1000:
                            log.error(
                                "detector.partitioned_optimized.track_id_overflow",
                                aquarium_id=aq.id,
                                local_track_id=track_id,
                                msg="local_track_id >= 1000 causa colisão de IDs",
                            )
                            # Use modulo to prevent collision while preserving tracking
                            offset_id = aq.id * 1000 + (track_id % 1000)
                        else:
                            offset_id = aq.id * 1000 + track_id
                    else:
                        offset_id = None
                    offset_tracked.append((x1, y1, x2, y2, conf, offset_id, class_id))
                results[aq.id] = offset_tracked
            else:
                results[aq.id] = []

        log.debug(
            "detector.partitioned_optimized.results",
            aquarium_counts={aq_id: len(dets) for aq_id, dets in results.items()},
            cropping_enabled=use_cropping,
            strategy="bytetrack" if use_bytetrack else "simple",
        )

        return results

    def detect_partitioned_parallel(
        self,
        frame: np.ndarray,
        max_workers: int = 2,
    ) -> dict[int, list[tuple]]:
        """Execute parallel detection for multi-aquarium mode.

        Phase 2.1: Uses ThreadPoolExecutor to process aquariums in parallel,
        providing ~30-40% speedup on multi-core systems.

        Note: Due to Python's GIL, actual parallel execution depends on the
        detection plugin releasing the GIL (e.g., during C++/CUDA operations).

        Args:
            frame: Input BGR frame.
            max_workers: Maximum number of parallel workers (default: 2 for dual-aquarium).

        Returns:
            Dictionary mapping aquarium_id to list of detection tuples.

        Raises:
            RuntimeError: If detector not in multi-aquarium mode.
        """
        if not self._multi_aquarium_mode:
            raise RuntimeError(
                "Detector is not in multi-aquarium mode. Call set_multi_aquarium_zones() first."
            )

        if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
            raise ValueError("Frame must be a valid non-empty numpy array")

        results: dict[int, list[tuple]] = {}
        errors: dict[int, str] = {}

        def process_aquarium(aq_id: int) -> tuple[int, list[tuple], str | None]:
            """Process a single aquarium region with error recovery.

            Returns:
                Tuple of (aquarium_id, detections, error_message or None)
            """
            try:
                aq = next((a for a in self._aquariums if a.id == aq_id), None)
                if aq is None:
                    return aq_id, [], f"Aquarium {aq_id} not found in configuration"

                # Crop and detect
                cropped, (offset_x, offset_y, _, _) = self._crop_aquarium_region(frame, aq_id)

                # Validate cropped region
                if cropped is None or cropped.size == 0:
                    return aq_id, [], f"Aquarium {aq_id}: Empty crop region"

                raw_detections = self.plugin.detect(cropped)

                # Adjust coordinates
                adjusted = []
                # Get aquarium polygon for filtering
                polygon = self._scaled_aquarium_polygons.get(aq_id)

                for raw_det in raw_detections:
                    det = self._ensure_track_tuple(raw_det)
                    # Cast to ensure int types for unpacking
                    x1_f, y1_f, x2_f, y2_f, conf, _, class_id = det
                    x1, y1, x2, y2 = int(x1_f), int(y1_f), int(x2_f), int(y2_f)

                    x1_global = x1 + offset_x
                    y1_global = y1 + offset_y
                    x2_global = x2 + offset_x
                    y2_global = y2 + offset_y

                    # FILTER 1: Class ID Check
                    if self.animal_class_id is not None and class_id != self.animal_class_id:
                        continue

                    # FILTER 2: Ensure centroid is within the aquarium polygon
                    centroid = ((x1_global + x2_global) / 2, (y1_global + y2_global) / 2)
                    if polygon is not None and polygon.size > 0:
                        if not self._point_in_polygon(centroid, polygon):
                            continue

                    adjusted.append(
                        (x1_global, y1_global, x2_global, y2_global, conf, None, class_id)
                    )

                return aq_id, adjusted, None
            except Exception as e:
                # Log but don't raise - allow other aquariums to continue
                log.warning(
                    "detector.partitioned_parallel.aquarium_error",
                    aquarium_id=aq_id,
                    error=str(e),
                )
                return aq_id, [], f"Aquarium {aq_id}: {e!s}"

        # Process aquariums in parallel with error recovery
        start_time = time.perf_counter()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_aquarium, aq.id): aq.id for aq in self._aquariums}
            for future in as_completed(futures):
                try:
                    aq_id, detections, error_msg = future.result()

                    # Track errors but continue processing
                    if error_msg:
                        errors[aq_id] = error_msg
                        results[aq_id] = []
                        continue

                    # Apply tracking (must be sequential - ByteTracker is not thread-safe)
                    if detections:
                        # Safe tracker access with validation
                        tracker = self._byte_trackers_multi.get(aq_id)
                        if tracker is None:
                            log.error(
                                "detector.partitioned_parallel.tracker_missing",
                                aquarium_id=aq_id,
                                available_trackers=list(self._byte_trackers_multi.keys()),
                            )
                            errors[aq_id] = f"ByteTracker não inicializado para aquário {aq_id}"
                            results[aq_id] = []
                            continue

                        tracked = self._apply_byte_tracking_multi(detections, tracker)
                        offset_tracked = []
                        for det in tracked:
                            x1, y1, x2, y2, conf, track_id, class_id = det
                            if track_id is not None:
                                if track_id >= 1000:
                                    log.error(
                                        "detector.partitioned_parallel.track_id_overflow",
                                        aquarium_id=aq_id,
                                        local_track_id=track_id,
                                        msg="local_track_id >= 1000 causa colisão de IDs",
                                    )
                                    offset_id = aq_id * 1000 + (track_id % 1000)
                                else:
                                    offset_id = aq_id * 1000 + track_id
                            else:
                                offset_id = None
                            offset_tracked.append((x1, y1, x2, y2, conf, offset_id, class_id))
                        results[aq_id] = offset_tracked
                    else:
                        results[aq_id] = []
                except Exception as e:
                    # Handle executor-level failures
                    aq_id = futures[future]
                    log.error(
                        "detector.partitioned_parallel.future_error",
                        aquarium_id=aq_id,
                        error=str(e),
                    )
                    errors[aq_id] = f"Executor error: {e!s}"
                    results[aq_id] = []

        elapsed = time.perf_counter() - start_time
        log.debug(
            "detector.partitioned_parallel.complete",
            elapsed_ms=round(elapsed * 1000, 2),
            aquarium_counts={aq_id: len(dets) for aq_id, dets in results.items()},
            errors=errors if errors else None,
        )

        return results

    def detect_batch(
        self,
        frames: list[np.ndarray],
        batch_size: int = 4,
    ) -> list[list[tuple]]:
        """Process multiple frames in batches for offline analysis.

        Phase 2.2: Batch processing can be more efficient for offline analysis
        as it allows the GPU to process multiple frames simultaneously.

        Note: This method is for single-aquarium mode. For multi-aquarium,
        use detect_partitioned_optimized() per frame.

        Args:
            frames: List of BGR frames to process.
            batch_size: Number of frames to process per batch.

        Returns:
            List of detection lists, one per input frame.
            Each detection is (x1, y1, x2, y2, conf, track_id, class_id).

        Example:
            detector = Detector(plugin, 1280, 720)
            frames = [frame1, frame2, frame3, frame4]
            all_detections = detector.detect_batch(frames, batch_size=2)
            # Process batch 1: frame1, frame2
            # Process batch 2: frame3, frame4
        """
        if not frames:
            return []

        all_results: list[list[tuple]] = []
        start_time = time.perf_counter()

        # Process in batches
        for i in range(0, len(frames), batch_size):
            batch = frames[i : i + batch_size]

            # Check if plugin supports batch inference (callable, not just MagicMock)
            if hasattr(self.plugin, "detect_batch") and callable(
                getattr(self.plugin, "detect_batch", None)
            ):
                # Use native batch inference if available
                batch_detections = self.plugin.detect_batch(batch)
            else:
                # Fall back to sequential processing
                batch_detections = [self.plugin.detect(frame) for frame in batch]

            # Apply tracking to each frame's detections
            for frame_detections in batch_detections:
                processed = []
                for det in frame_detections:
                    det = self._ensure_track_tuple(det)
                    processed.append(det)

                # Apply ByteTracking if available
                if self._byte_tracker is not None and processed:
                    # Note: frame_shape not available in batch context, using cached dimensions
                    frame_shape_cached = (self._last_height or 720, self._last_width or 1280, 3)
                    tracked = self._apply_byte_tracking(processed, frame_shape_cached)
                else:
                    tracked = processed

                all_results.append(tracked)

        elapsed = time.perf_counter() - start_time
        log.info(
            "detector.batch.complete",
            total_frames=len(frames),
            batch_size=batch_size,
            elapsed_ms=round(elapsed * 1000, 2),
            avg_ms_per_frame=round(elapsed * 1000 / len(frames), 2) if frames else 0,
        )

        return all_results

    def _point_in_polygon(
        self,
        point: tuple[float, float],
        polygon: np.ndarray,
    ) -> bool:
        """Check if a point is inside a polygon.

        Args:
            point: (x, y) coordinates.
            polygon: Polygon vertices as numpy array.

        Returns:
            True if point is inside or on boundary of polygon.
        """
        if polygon.size == 0:
            return False
        return cv2.pointPolygonTest(polygon, point, False) >= 0

    def _apply_byte_tracking_multi(
        self,
        detections: list[tuple],
        tracker: BYTETracker,
    ) -> list[tuple]:
        """Apply ByteTracker to a list of detections for multi-aquarium mode.

        Args:
            detections: List of (x1, y1, x2, y2, conf, track_id, class_id) tuples.
            tracker: ByteTracker instance to use.

        Returns:
            List of detections with updated track_ids.
        """
        if not detections:
            return []

        # Convert to numpy array format for ByteTracker (only 5 columns: x1, y1, x2, y2, conf)
        det_array = np.array(
            [
                [d[0], d[1], d[2], d[3], d[4]]  # x1, y1, x2, y2, conf
                for d in detections
            ]
        )

        # Update tracker
        online_targets = tracker.update(
            det_array,
            [self._last_height or 720, self._last_width or 1280],
            [self._last_height or 720, self._last_width or 1280],
        )

        # Convert back to tuple format
        tracked = []
        for track in online_targets:
            tlbr = track.tlbr
            x1, y1, x2, y2 = int(tlbr[0]), int(tlbr[1]), int(tlbr[2]), int(tlbr[3])
            track_id = track.track_id
            conf = track.score

            # Find original class_id from closest detection
            class_id = self.animal_class_id
            for det in detections:
                if abs(det[0] - x1) < 10 and abs(det[1] - y1) < 10:
                    class_id = det[6]
                    break

            tracked.append((x1, y1, x2, y2, conf, track_id, class_id))

        return tracked

    def reset_multi_aquarium_tracking(
        self,
        aquarium_id: int | None = None,
    ) -> None:
        """Reset tracking state for one or all aquariums.

        Args:
            aquarium_id: Specific aquarium to reset, or None for all.
        """
        tracker_args = SimpleNamespace(
            track_thresh=self._get_track_threshold(),
            match_thresh=self._get_match_threshold(),
            track_buffer=self._get_track_buffer(),
            mot20=False,
        )

        # Get processing_interval from settings
        if self.settings and hasattr(self.settings, "video_processing"):
            processing_interval = (
                getattr(self.settings.video_processing, "processing_interval", 1) or 1
            )
        else:
            processing_interval = 1

        # Get FPS from settings
        if self.settings and hasattr(self.settings, "video_processing"):
            frame_rate = getattr(self.settings.video_processing, "fps", 30) or 30
        else:
            frame_rate = 30

        if aquarium_id is not None:
            if aquarium_id in self._byte_trackers_multi:
                self._byte_trackers_multi[aquarium_id] = BYTETracker(
                    args=tracker_args,
                    frame_rate=frame_rate,
                    use_hybrid_matching=True,
                    max_center_distance=self._get_max_center_distance(),
                    processing_interval=processing_interval,
                    iou_threshold=self._get_iou_threshold(),
                    single_animal_mode=True,  # Each aquarium has exactly 1 animal
                )
                log.debug(
                    "detector.multi_aquarium.tracking_reset",
                    aquarium_id=aquarium_id,
                    single_animal_mode=True,
                )
        else:
            for aq_id in list(self._byte_trackers_multi.keys()):
                self._byte_trackers_multi[aq_id] = BYTETracker(
                    args=tracker_args,
                    frame_rate=frame_rate,
                    use_hybrid_matching=True,
                    max_center_distance=self._get_max_center_distance(),
                    processing_interval=processing_interval,
                    iou_threshold=self._get_iou_threshold(),
                    single_animal_mode=True,  # Each aquarium has exactly 1 animal
                )
            log.debug(
                "detector.multi_aquarium.tracking_reset_all",
                aquarium_count=len(self._byte_trackers_multi),
                single_animal_mode=True,
            )

    def is_multi_aquarium_mode(self) -> bool:
        """Check if detector is in multi-aquarium mode.

        Returns:
            True if multi-aquarium mode is enabled.
        """
        return self._multi_aquarium_mode

    def get_aquarium_polygon(self, aquarium_id: int) -> np.ndarray | None:
        """Get scaled polygon for a specific aquarium.

        Args:
            aquarium_id: Aquarium ID (0 or 1).

        Returns:
            Scaled polygon as numpy array, or None if not found.
        """
        return self._scaled_aquarium_polygons.get(aquarium_id)

    def get_aquarium_roi_polygons(self, aquarium_id: int) -> list[np.ndarray]:
        """Get scaled ROI polygons for a specific aquarium.

        Args:
            aquarium_id: Aquarium ID (0 or 1).

        Returns:
            List of scaled ROI polygons.
        """
        return self._scaled_aquarium_roi_polygons.get(aquarium_id, [])

    def get_multi_aquarium_data(self) -> list[AquariumData]:
        """Get the configured aquarium data.

        Returns:
            List of AquariumData objects.
        """
        return self._aquariums

    def draw_multi_aquarium_overlay(
        self,
        frame: np.ndarray,
        partitioned_detections: dict[int, list[tuple]],
    ) -> np.ndarray:
        """Draw detection overlays for multi-aquarium mode.

        Draws each aquarium's polygon and ROIs with distinct colors,
        plus detection bounding boxes with aquarium-specific coloring.

        Args:
            frame: Input BGR frame (modified in-place).
            partitioned_detections: Detection results from detect_partitioned().

        Returns:
            Frame with overlays drawn.
        """
        # Colors for each aquarium
        aquarium_colors = {
            0: (0, 255, 0),  # Green for aquarium 0 (left)
            1: (255, 165, 0),  # Orange for aquarium 1 (right)
        }

        for aq in self._aquariums:
            aq_color = aquarium_colors.get(aq.id, (255, 255, 255))

            # Draw aquarium polygon
            polygon = self._scaled_aquarium_polygons.get(aq.id)
            if polygon is not None and polygon.size > 0:
                cv2.polylines(
                    frame,
                    [polygon],
                    isClosed=True,
                    color=aq_color,
                    thickness=2,
                )

                # Draw aquarium label
                if polygon.size > 0:
                    x, y = polygon[0]
                    label = f"Aquario {aq.id + 1}"
                    if aq.group:
                        label += f" ({aq.group})"
                    cv2.putText(
                        frame,
                        label,
                        (int(x), int(y) - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        aq_color,
                        2,
                    )

            # Draw ROI polygons
            roi_polygons = self._scaled_aquarium_roi_polygons.get(aq.id, [])
            for i, roi_polygon in enumerate(roi_polygons):
                if i < len(aq.roi_colors):
                    roi_color = aq.roi_colors[i]
                else:
                    roi_color = aq_color
                cv2.polylines(
                    frame,
                    [roi_polygon],
                    isClosed=True,
                    color=roi_color,
                    thickness=1,
                )

            # Draw detections for this aquarium
            detections = partitioned_detections.get(aq.id, [])
            for det in detections:
                if len(det) >= 6:
                    x1, y1, x2, y2, conf, track_id = det[:6]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), aq_color, 2)

                    # Label with track ID
                    label = f"ID:{track_id}" if track_id else f"{conf:.0%}"
                    cv2.putText(
                        frame,
                        label,
                        (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        aq_color,
                        1,
                    )

        return frame

    def get_zone_data(self) -> ZoneData:
        """Helper to get current zone configuration as ZoneData object."""
        if hasattr(self.zones, "to_zone_data"):
            # If it's MultiAquariumZoneData, return first aquarium as default
            return self.zones.to_zone_data(0)  # type: ignore[union-attr]
        return self.zones  # type: ignore[return-value]

    def get_multi_aquarium_zone_data(self) -> MultiAquariumZoneData:
        """Helper to get MultiAquariumZoneData from current state."""
        if isinstance(self.zones, MultiAquariumZoneData):
            return self.zones
        # Fallback: wrap single ZoneData into multi-aquarium structure
        return MultiAquariumZoneData(
            aquariums=[
                AquariumData(
                    id=0,
                    polygon=self.polygon,
                    roi_polygons=self.roi_polygons,
                    roi_names=self.roi_names,
                    roi_colors=self.roi_colors,
                )
            ],
            video_width=self.base_width,
            video_height=self.base_height,
        )
