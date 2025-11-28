"""Analysis orchestration logic extracted from MainViewModel.

Sprint 25 - Extracted to reduce MainViewModel complexity.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
import pandas as pd
import structlog
from shapely.geometry import Polygon

from zebtrack.analysis.reporter import Reporter
from zebtrack.analysis.roi import ROI
from zebtrack.core.aquarium_detector import AquariumDetector
from zebtrack.core.calibration import Calibration
from zebtrack.core.processing_mode import ProcessingMode
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.core.main_view_model import MainViewModel

logger = structlog.get_logger()


class AnalysisOrchestrator:
    """Orchestrates analysis workflows.

    Extracted from MainViewModel in Sprint 25 to reduce its size.
    Maintains reference to MainViewModel for delegation during gradual extraction.
    """

    def __init__(self, main_view_model: MainViewModel):
        """Initialize with MainViewModel reference.

        Args:
            main_view_model: Reference to MainViewModel for delegation
        """
        self.main_view_model = main_view_model

        # Cache frequently used attributes from MainViewModel
        self.state_manager = main_view_model.state_manager
        self.project_manager = main_view_model.project_manager
        self.view = main_view_model.view
        self.ui_event_bus = main_view_model.ui_event_bus
        self.root = main_view_model.root
        self.settings = main_view_model.settings
        self.weight_manager = main_view_model.weight_manager

    def run_aquarium_detection(
        self,
        video_path: Path | str | None = None,
        stabilization_frames: int = 10,
        temp_aquarium_method: str | None = None,
    ):
        """Run the aquarium detection model on the specified or first project video.

        Args:
            video_path: Path to video file, if None uses next project video
            stabilization_frames: Number of frames to analyze for stabilization
            temp_aquarium_method: Temporary override for aquarium detection method
                ('det' or 'seg'). If None, uses global self.settings.
        """
        if video_path is not None:
            video_path = Path(video_path) if isinstance(video_path, str) else video_path
        logger.info("controller.aquarium_detection.start")
        self.ui_event_bus.publish_event(
            Events.UI_SET_STATUS,
            {"message": "Detectando aquário, por favor aguarde..."},
        )
        self.main_view_model._publish_processing_mode(
            source="calibration.aquarium.start",
            force=True,
            mode_override=ProcessingMode.SINGLE_SUBJECT,
        )

        try:
            if video_path is None:
                video_path = self.project_manager.get_next_video()

            if not video_path:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Aviso",
                        "message": "Nenhum vídeo foi encontrado para a detecção.",
                    },
                )
                return

            self.project_manager.set_active_zone_video(video_path)

            # Display the first frame of the video as a preview background
            self.ui_event_bus.publish_event(
                Events.UI_DISPLAY_VIDEO_FRAME, {"video_path": video_path}
            )

            # Use selected aquarium method and get appropriate weight
            # Use temporary override if provided, otherwise use global settings
            aquarium_method = temp_aquarium_method or self.settings.model_selection.aquarium_method
            model_path = self.weight_manager.get_weight_path_by_method(aquarium_method, "aquarium")

            if not model_path:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro",
                        "message": f"Não foi possível encontrar um modelo {aquarium_method} para "
                        "detecção do aquário.",
                    },
                )
                return

            detector = AquariumDetector(model_path=model_path, mode=aquarium_method)
            polygons = detector.detect_aquariums(
                video_path, stabilization_frames=stabilization_frames
            )

            if not polygons:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Detecção Automática Falhou",
                        "message": "Não foi possível identificar uma área de aquário estável "
                        "no vídeo. Isso pode ocorrer devido a reflexos, pouca luz ou "
                        "movimento excessivo da câmera.\n\nPor favor, defina a área "
                        "do aquário manualmente utilizando a ferramenta 'Desenhar "
                        "Polígono Principal'.",
                    },
                )
                return

            main_polygon = polygons[0]
            logger.info(
                "controller.aquarium_detection.success",
                polygon_points=len(main_polygon),
            )
            # The view will handle drawing this polygon interactively
            self.ui_event_bus.publish_event(
                Events.UI_SETUP_INTERACTIVE_POLYGON, {"polygon": main_polygon}
            )

        except Exception as e:
            logger.error("controller.aquarium_detection.error", exc_info=True)
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro na Detecção",
                    "message": f"Ocorreu um erro ao detectar o aquário: {e}",
                },
            )
        finally:
            self.main_view_model._publish_processing_mode(
                source="calibration.aquarium.complete",
                force=True,
            )
            self.ui_event_bus.publish_event(Events.UI_SET_STATUS, {"message": "Pronto."})

    def _generate_parquet_summaries_worker(self, target_videos: list[dict], settings_obj) -> None:
        """Worker method to generate parquet summaries for a list of videos.

        Separated to reduce complexity in the public API method.
        """
        completed: list[str] = []
        skipped: list[str] = []
        details: list[str] = []
        data_changed = False

        for video in target_videos:
            # Reuse the same logic previously extracted inlined; keep small and focused
            state = None
            try:
                # Simplified wrapper calling existing logic for each video. Defer to the
                # per-video helper implemented earlier.
                state, info_msg, _ppath, changed = self._process_summary_video(
                    video,
                    settings_obj,
                )
            except Exception as exc:  # pragma: no cover - defensive
                state, info_msg, _ppath, changed = "failed", str(exc), None, False

            if state == "completed":
                completed.append(info_msg or "(desconhecido)")
                data_changed = data_changed or bool(changed)
            else:
                skipped.append(info_msg.split(":")[0] if info_msg else "(desconhecido)")
                details.append(f"• {info_msg}")

        if data_changed:
            self.project_manager.save_project()

        def finalize() -> None:
            if completed:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Sumários Gerados",
                        "message": "Sumários parquet atualizados para "
                        f"{len(completed)} vídeo(s).\n"
                        + "\n".join(f"• {item}" for item in completed),
                    },
                )
                status_msg = f"Σ Sumários atualizados: {len(completed)} vídeo(s)."
            else:
                status_msg = "Nenhum sumário foi atualizado."

            if details:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Vídeos ignorados",
                        "message": "Alguns sumários não puderam ser gerados:\n"
                        + "\n".join(details),
                    },
                )

            self.ui_event_bus.publish_event(Events.UI_SET_STATUS, {"message": status_msg})
            self.main_view_model.ui_state_controller.refresh_project_views(
                reason=status_msg, append_summary=True
            )
            self.main_view_model.processing_thread = None

        self.root.after(0, finalize)

    def _process_summary_video(
        self,
        video: dict,
        settings_obj,
    ) -> tuple[str, str | None, str | None, bool]:
        """Process a single video for summary generation. Extracted from the main method."""
        path = video.get("path")
        if not isinstance(path, str) or not path:
            return "skipped", "Caminho do vídeo não definido.", None, False

        experiment_id = os.path.splitext(os.path.basename(path))[0]
        metadata_hint = dict(video.get("metadata") or {})
        results_path = self.project_manager.resolve_results_directory(
            experiment_id, video_path=path, metadata=metadata_hint
        )
        results_dir = str(results_path)

        parquet_info = video.get("parquet_files") or {}
        trajectory_path = parquet_info.get("trajectory")
        if trajectory_path and not os.path.exists(trajectory_path):
            trajectory_path = None

        if not trajectory_path:
            candidates = [
                os.path.join(results_dir, f"3_CoordMovimento_{experiment_id}.parquet"),
                os.path.join(os.path.dirname(path), f"3_CoordMovimento_{experiment_id}.parquet"),
            ]
            for candidate in candidates:
                if os.path.exists(candidate):
                    trajectory_path = candidate
                    break

        if not trajectory_path:
            return (
                "skipped",
                f"{experiment_id}: arquivo de trajetória ausente.",
                None,
                False,
            )

        try:
            trajectory_df = pd.read_parquet(trajectory_path)
        except Exception as exc:  # pragma: no cover - I/O defensive
            return (
                "skipped",
                f"{experiment_id}: falha ao ler trajetória ({exc}).",
                None,
                False,
            )

        if trajectory_df.empty:
            return (
                "skipped",
                f"{experiment_id}: trajetória vazia, sumário não gerado.",
                None,
                False,
            )

        self.project_manager.set_active_zone_video(path)
        try:
            zone_data = self.project_manager.get_zone_data(video_path=path)

            arena_polygon_px = list(zone_data.polygon or [])

            if not arena_polygon_px:
                cap = cv2.VideoCapture(path)
                if not cap.isOpened():
                    return (
                        "skipped",
                        f"{experiment_id}: não foi possível abrir o vídeo.",
                        None,
                        False,
                    )
                frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()
                arena_polygon_px = [
                    [0, 0],
                    [frame_width, 0],
                    [frame_width, frame_height],
                    [0, frame_height],
                ]

            calib_data = self.project_manager.project_data.get("calibration", {})
            width_cm = calib_data.get("aquarium_width_cm")
            height_cm = calib_data.get("aquarium_height_cm")
            if not width_cm or not height_cm:
                return "skipped", f"{experiment_id}: calibração incompleta (px/cm).", None, False

            cal = Calibration(np.array(arena_polygon_px), width_cm, height_cm)
            _, video_height_px = cal.target_dims_px
            pixelcm_x, pixelcm_y = cal.pixel_per_cm_ratio
            arena_polygon_warped = cal.transform_points(arena_polygon_px)

            roi_polygons = list(zone_data.roi_polygons or [])
            roi_names = list(zone_data.roi_names or [])
            roi_colors_list = list(zone_data.roi_colors or [])

            rois: list[ROI] = []
            for idx, roi_points in enumerate(roi_polygons):
                warped_points = cal.transform_points(roi_points)
                roi_polygon_px = [(float(x), float(y)) for x, y in warped_points]
                roi_name = roi_names[idx] if idx < len(roi_names) else f"ROI {idx + 1}"
                rois.append(
                    ROI(
                        name=roi_name,
                        geometry=Polygon(roi_polygon_px),
                        coordinate_space="px",
                    )
                )

            roi_colors = {
                (roi_names[i] if i < len(roi_names) else f"ROI {i + 1}"): roi_colors_list[i]
                for i in range(len(roi_colors_list))
            }

            metadata = self.project_manager.get_metadata_for_experiment(experiment_id) or {
                "experiment_id": experiment_id,
                "video_name": experiment_id,
            }

            reporter = Reporter(
                trajectory_df=trajectory_df,
                metadata=metadata,
                pixelcm_x=pixelcm_x,
                pixelcm_y=pixelcm_y,
                video_height_px=video_height_px,
                arena_polygon_px=arena_polygon_warped,
                rois=rois,
                fps=settings_obj.video_processing.fps,
                roi_colors=roi_colors,
                video_path=path,
                calibration=cal,
                sharp_turn_threshold=settings_obj.video_processing.sharp_turn_threshold_deg_s,
                freezing_threshold=settings_obj.video_processing.freezing_velocity_threshold,
                freezing_duration=settings_obj.video_processing.freezing_min_duration_s,
                smoothing_window_length=settings_obj.trajectory_smoothing.window_length,
                smoothing_polyorder=settings_obj.trajectory_smoothing.polyorder,
            )

            os.makedirs(results_dir, exist_ok=True)
            parquet_path = os.path.join(results_dir, f"{experiment_id}_summary.parquet")
            reporter.export_summary_data(parquet_path, format="parquet")

            video.setdefault("parquet_files", {})["summary"] = parquet_path
            video["has_complete_data"] = True
            return "completed", experiment_id, parquet_path, True
        except Exception as exc:  # pragma: no cover - defensive
            return "failed", f"{experiment_id}: erro inesperado ({exc}).", None, False
        finally:
            self.project_manager.set_active_zone_video(None)
