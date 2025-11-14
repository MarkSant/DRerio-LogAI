"""Zone and arena management orchestration logic extracted from MainViewModel.

Sprint 30 - Extracted to reduce MainViewModel complexity.
"""

from __future__ import annotations

import tempfile
from typing import TYPE_CHECKING

import cv2
import numpy as np
import structlog

from zebtrack.core.detector import ZoneData
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.core.main_view_model import MainViewModel

log = structlog.get_logger()


class ZoneArenaOrchestrator:
    """Orchestrates zone and arena polygon management.

    Extracted from MainViewModel in Sprint 30 to reduce its size.
    Maintains reference to MainViewModel for delegation during gradual extraction.

    This class handles:
    - Main arena polygon configuration and validation
    - ROI polygon addition with overlap detection
    - Manual arena adjustment and saving
    - Zone data validation and persistence
    """

    def __init__(self, main_view_model: MainViewModel):
        """Initialize with MainViewModel reference.

        Args:
            main_view_model: Reference to MainViewModel for delegation
        """
        self.main_view_model = main_view_model

        # Cache frequently used attributes from MainViewModel
        self.view = main_view_model.view
        self.project_manager = main_view_model.project_manager
        self.ui_event_bus = main_view_model.ui_event_bus

    def set_main_arena_polygon(self, points: list) -> bool:
        """Salva polígono com validações robustas."""
        try:
            # Validação 1: Pontos válidos
            if not points or len(points) < 3:
                log.error(
                    "controller.polygon.invalid_points",
                    count=len(points) if points else 0,
                )
                return False

            # Validação 2: Projeto existe
            if not self.project_manager.project_path:
                log.error("controller.polygon.no_project")
                # Para single video workflow, cria projeto temporário
                if (
                    hasattr(self.view, "pending_single_video_path")
                    and self.view.pending_single_video_path
                ):
                    temp_dir = tempfile.mkdtemp(prefix="zebtrack_temp_")
                    self.project_manager.project_path = temp_dir
                    self.project_manager.project_data = {
                        "project_name": "Temporary Single Video Project",
                        "project_type": "single_video",
                        "detection_zones": {},
                    }
                    log.warning("controller.polygon.created_temp_project", path=temp_dir)
                else:
                    return False

            # Validação 3: Estrutura de dados
            if "detection_zones" not in self.project_manager.project_data:
                self.project_manager.save_zone_data(ZoneData(), persist=False)
                log.info("controller.polygon.initialized_detection_zones")

            # Salva
            self.project_manager.update_main_polygon(points)

            # Força atualização visual
            self.ui_event_bus.publish_event(Events.UI_REDRAW_ZONES, {})

            log.info("controller.polygon.saved", points=len(points))
            return True

        except Exception as e:
            log.error("controller.polygon.save_error", error=str(e))
            return False

    def save_manual_arena(self, polygon_points: list[list[int]]):
        """
        Save the manually adjusted arena and updates the detector.

        Delegates to ProjectService for persistence (Phase 2.1).
        MainViewModel handles UI coordination and detector updates.
        """
        log.info("controller.arena.save_manual", points_count=len(polygon_points))
        self.main_view_model.update_main_arena(polygon_points)

    def add_roi_polygon(self, roi_points: list[list[int]], name: str, color: tuple[int, int, int]):
        """Adiciona ROI com validação de sobreposição."""
        try:
            log.info("controller.zone.add_roi", name=name, points=len(roi_points))

            # Critical Fix #4: Add project validation before saving ROI
            if not self.project_manager.project_path:
                log.error("controller.zone.add_roi.no_project", name=name)
                return False

            zone_data = self.project_manager.get_zone_data()

            # Validação 1: Verifica se está dentro da arena principal
            if zone_data.polygon and len(zone_data.polygon) >= 3:
                arena_poly = np.array(zone_data.polygon, dtype=np.float32)

                # First pass: adjust points that are slightly outside (likely from
                # snapping)
                adjusted_points = []
                # Calculate arena centroid once (convert to native Python float)
                centroid_x = float(np.mean(arena_poly[:, 0]))
                centroid_y = float(np.mean(arena_poly[:, 1]))

                for point in roi_points:
                    px, py = float(point[0]), float(point[1])
                    # True returns signed distance
                    result = cv2.pointPolygonTest(arena_poly, (px, py), True)

                    # If point is slightly outside (within 3 pixels), nudge it inside
                    if -3.0 <= result < 0:
                        # Move point toward centroid by 3 pixels
                        dx = centroid_x - px
                        dy = centroid_y - py
                        length = float(np.sqrt(dx * dx + dy * dy))
                        if length > 0:
                            px += (dx / length) * 3.0
                            py += (dy / length) * 3.0

                    # Ensure values are native Python float, not numpy types
                    adjusted_points.append([float(px), float(py)])

                # Second pass: validate adjusted points
                points_outside = 0
                for point in adjusted_points:
                    result = cv2.pointPolygonTest(arena_poly, tuple(point), False)
                    if result < 0:  # Ponto está fora
                        points_outside += 1

                # If adjustment worked, use adjusted points
                if points_outside == 0:
                    roi_points = adjusted_points

                if points_outside > 0:
                    outside_percent = (points_outside / len(roi_points)) * 100
                    log.warning(
                        "controller.roi.outside_arena",
                        name=name,
                        points_outside=points_outside,
                        percent=outside_percent,
                    )

                    if not self.view.ask_ok_cancel(
                        "ROI Fora da Arena",
                        (
                            f"A ROI '{name}' tem {points_outside} pontos "
                            f"({outside_percent:.1f}%) "
                            "fora da arena principal.\n\nDeseja continuar mesmo assim?"
                        ),
                    ):
                        return False

            # Validação 2: Verifica sobreposição com outras ROIs
            for i, existing_roi in enumerate(zone_data.roi_polygons):
                if len(existing_roi) >= 3:
                    # Calcula sobreposição simples verificando pontos
                    overlapping_points = 0

                    existing_poly = np.array(existing_roi, dtype=np.int32)

                    for point in roi_points:
                        result = cv2.pointPolygonTest(existing_poly, tuple(point), False)
                        if result >= 0:  # Ponto está dentro ou na borda
                            overlapping_points += 1

                    if overlapping_points > 0:
                        overlap_percent = (overlapping_points / len(roi_points)) * 100

                        if overlap_percent > 20:  # Mais de 20% de sobreposição
                            existing_name = (
                                zone_data.roi_names[i]
                                if i < len(zone_data.roi_names)
                                else f"ROI_{i + 1}"
                            )
                            log.warning(
                                "controller.roi.overlap",
                                name=name,
                                existing=existing_name,
                                percent=overlap_percent,
                            )

                            if not self.view.ask_ok_cancel(
                                "ROIs Sobrepostas",
                                f"A nova ROI '{name}' tem {overlap_percent:.1f}% de "
                                f"sobreposição com '{existing_name}'.\n\n"
                                "Deseja continuar?",
                            ):
                                return False

            # Adiciona a ROI após validações
            zone_data.roi_polygons.append(roi_points)
            zone_data.roi_names.append(name)
            zone_data.roi_colors.append(color)

            # Save the project and reload the zones in the active detector
            self.project_manager.save_zone_data(zone_data)
            self.main_view_model.setup_detector_zones()
            log.info("controller.zone.add_roi.success", name=name)
            return True

        except Exception as e:
            log.error("controller.zone.add_roi.error", name=name, error=str(e))
            return False
