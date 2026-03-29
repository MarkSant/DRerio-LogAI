"""Report generation coordinator for video processing outputs.

Phase 4: Extracted from ProcessingCoordinator.
Handles unified report generation, individual video reports (Word/Excel),
parquet summary generation, and all supporting geometry/calibration helpers.

Estimated size: ~1000 lines (target <800, acceptable at ~1000 due to
report complexity and many private helpers).
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.analysis.roi import ROI
from zebtrack.analysis.roi_builder import build_roi_from_polygon
from zebtrack.coordinators._unified_report_mixin import UnifiedReportMixin
from zebtrack.coordinators.base_coordinator import BaseCoordinator
from zebtrack.core.detection import MultiAquariumZoneData, ZoneData
from zebtrack.core.detection.calibration import Calibration
from zebtrack.ui.event_bus_v2 import UIEvents

if TYPE_CHECKING:
    import pandas as pd

    from zebtrack.analysis.analysis_service import AnalysisService
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.services.trajectory_data_service import TrajectoryDataService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.video.video_metadata_service import VideoMetadataService
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2
    from zebtrack.utils.video_frame_extractor import VideoFrameExtractor

log = structlog.get_logger()


class ReportGenerationCoordinator(BaseCoordinator, UnifiedReportMixin):
    """Coordinator for all report generation workflows.

    Responsibilities:
        - Unified report generation (aggregated across multiple videos)
        - Individual video report generation (Word/Excel per video)
        - Parquet summary generation
        - Report geometry computation (local space, calibration)
        - Background frame extraction and preparation
        - Multi-aquarium report orchestration

    Phase 4: All methods moved from ProcessingCoordinator without logic changes.
    """

    def __init__(
        self,
        state_manager: StateManager,
        project_manager: ProjectManager,
        settings_obj: Settings,
        analysis_service: AnalysisService | None = None,
        event_bus: EventBusV2 | None = None,
        video_metadata_service: VideoMetadataService | None = None,
        trajectory_data_service: TrajectoryDataService | None = None,
        video_frame_extractor: VideoFrameExtractor | None = None,
    ) -> None:
        super().__init__(state_manager, event_bus)
        self.project_manager = project_manager
        self.settings = settings_obj
        self.analysis_service = analysis_service
        self._video_metadata_service = video_metadata_service
        self._trajectory_data_service = trajectory_data_service
        self._frame_extractor = video_frame_extractor

        # Cross-coordinator references (set post-construction)
        self._progress_coordinator: Any = None

        log.info("report_generation_coordinator.initialized")

    # ========================================================================
    # Internal helpers — delegated I/O
    # ========================================================================

    def _read_trajectory(self, path: Path | str) -> pd.DataFrame:
        """Read a trajectory Parquet file via injected service or fallback."""
        if self._trajectory_data_service is not None:
            return self._trajectory_data_service.load_trajectory(str(path))
        import pandas as _pd  # pragma: no cover — fallback only

        return _pd.read_parquet(path)  # pragma: no cover

    # ========================================================================
    # Batch context delegation
    # ========================================================================

    def _is_batch_processing(self) -> bool:
        """Check if batch processing is active (delegates to progress coordinator)."""
        ptc = self._progress_coordinator
        if ptc and hasattr(ptc, "_is_batch_processing"):
            return ptc._is_batch_processing()
        return False

    # ========================================================================
    # Individual Video Reports
    # ========================================================================

    def generate_project_reports(self, video_paths: list[str] | None = None) -> None:
        """Generate reports (Word, Excel, Parquet) for specified videos."""
        if not video_paths:
            return

        log.info("workflow.reports.start", count=len(video_paths))
        self._publish_event(UIEvents.UI_SET_STATUS, {"message": "Gerando relatórios detalhados..."})

        entries = [self.project_manager.find_video_entry(path=p) for p in video_paths]
        self.generate_parquet_summaries([e for e in entries if e], self.settings)

        count, errors = 0, []
        self._ensure_analysis_service_ready()

        for path in video_paths:
            try:
                self._generate_single_video_reports(path)
                count += 1
            except Exception as e:  # except Exception justified: per-video error isolation in batch
                log.exception("workflow.reports.video_failed", video=path, error=str(e))
                errors.append(f"{os.path.basename(path)}: {e}")

        self._finalize_report_generation(count, errors)

    def _generate_single_video_reports(self, path: Path | str) -> None:
        """Orchestrate report generation for a single video path."""
        experiment_id = os.path.splitext(os.path.basename(path))[0]
        entry = self.project_manager.find_video_entry(path=path)
        if not entry:
            return

        metadata = entry.get("metadata", {})
        multi_outputs = entry.get("multi_aquarium_outputs")

        if multi_outputs:
            self._generate_multi_aquarium_reports(path, experiment_id, entry, multi_outputs)
        else:
            self._generate_standard_report(path, experiment_id, entry, metadata)

    def _generate_multi_aquarium_reports(
        self, path: Path | str, exp_id: str, entry: dict, multi_outputs: dict
    ) -> None:
        """Generate reports for multi-aquarium videos."""
        project_data = getattr(self.project_manager, "project_data", {}) or {}

        self._ensure_analysis_service_ready()
        if not self.analysis_service:
            log.error("workflow.reports.service_not_ready")
            return

        analysis_params = self.analysis_service.collect_analysis_parameters(project_data)
        calib = project_data.get("calibration", {})
        fps = float(self.settings.video_processing.fps)
        probed_w, probed_h = self._probe_video_dimensions(str(path))

        zone_data: ZoneData | MultiAquariumZoneData | None = (
            self.project_manager.get_multi_aquarium_zone_data(video_path=path)
        )
        if not zone_data:
            zone_data = self.project_manager.get_zone_data(video_path=path)

        for aq_id_str, output_info in multi_outputs.items():
            aq_id = int(aq_id_str)
            self._process_single_aquarium_in_multi(
                path,
                exp_id,
                entry,
                aq_id,
                output_info,
                zone_data,
                calib,
                fps,
                probed_w,
                probed_h,
                analysis_params,
            )

    def _process_single_aquarium_in_multi(
        self,
        path: Path | str,
        exp_id,
        entry,
        aq_id,
        output_info,
        zone_data,
        calib,
        fps,
        p_w,
        p_h,
        params,
    ) -> None:
        """Process a single aquarium within a multi-aquarium video for report generation."""
        aq_results_dir = output_info.get("results_dir")
        aq_parquet_files = output_info.get("parquet_files", {})
        trajectory_path = aq_parquet_files.get("trajectory")

        if not trajectory_path or not os.path.exists(trajectory_path):
            log.warning("workflow.reports.multi_aquarium.missing_trajectory", video=path, aq=aq_id)
            return

        df = self._read_trajectory(trajectory_path)
        aq_metadata = {
            **entry.get("metadata", {}),
            "aquarium_id": aq_id,
            "experiment_id": exp_id,
            "group": output_info.get("group", entry.get("metadata", {}).get("group")),
            "subject": output_info.get("subject_id", entry.get("metadata", {}).get("subject")),
        }

        # Geometry
        arena_polygon: list[tuple[float, float]] = []
        if hasattr(zone_data, "aquariums") and zone_data.aquariums:
            for aq in zone_data.aquariums:
                if aq.id == aq_id:
                    arena_polygon = aq.polygon if aq.polygon else []
                    break
        elif zone_data:
            arena_polygon = zone_data.polygon if zone_data.polygon else []

        fb_w = getattr(zone_data, "video_width", p_w) or p_w
        fb_h = getattr(zone_data, "video_height", p_h) or p_h

        off_x, off_y, loc_w, loc_h = self._compute_local_space_geometry(arena_polygon, fb_w, fb_h)
        arena_poly_local = [(float(x) - off_x, float(y) - off_y) for x, y in arena_polygon]
        if not arena_poly_local:
            arena_poly_local = [
                (0.0, 0.0),
                (float(loc_w), 0.0),
                (float(loc_w), float(loc_h)),
                (0.0, float(loc_h)),
            ]

        rois, roi_colors_map = self._collect_rois_for_aquarium(zone_data, aq_id, off_x, off_y)
        df = self._normalize_df_to_local_space(df, off_x, off_y, loc_w, loc_h)

        px_x, px_y = self._resolve_pixel_cm(aq_metadata, calib, loc_w, loc_h)

        frame_crop = (off_x, off_y, loc_w, loc_h) if arena_polygon else None
        video_path_report = self._prepare_background_image(path, exp_id, aq_results_dir, frame_crop)

        if video_path_report and video_path_report.endswith(".png"):
            frame_crop_for_viz = None
        else:
            frame_crop_for_viz = frame_crop

        service = self.analysis_service
        if not service:
            return

        analysis_result = service.run_full_analysis_as_dto(
            trajectory_df=df,
            pixelcm_x=px_x,
            pixelcm_y=px_y,
            video_height_px=int(loc_h or p_h or 720),
            arena_polygon_px=arena_poly_local,
            rois=rois,
            fps=fps,
            metadata=aq_metadata,
            roi_colors=roi_colors_map,
            freezing_vel_threshold=self.settings.video_processing.freezing_velocity_threshold,
            freezing_min_duration=self.settings.video_processing.freezing_min_duration_s,
            video_path=video_path_report,
            frame_crop_box=frame_crop_for_viz,
            behavioral_config=params.get("behavioral_config"),
        )

        self._export_individual_outputs(analysis_result, aq_results_dir, f"{exp_id}_aq{aq_id}")

    def _generate_standard_report(
        self, path: Path | str, exp_id: str, entry: dict, metadata: dict
    ) -> None:
        """Generate report for a standard (single aquarium) video."""
        metadata = dict(metadata) if isinstance(metadata, dict) else {}
        metadata.setdefault("experiment_id", exp_id)
        metadata.setdefault("video_name", exp_id)
        metadata.setdefault("group", "single_video")
        metadata.setdefault("day", "1")
        metadata.setdefault("subject", "1")

        results_path = self.project_manager.resolve_results_directory(
            exp_id, video_path=str(path), metadata=metadata
        )
        os.makedirs(results_path, exist_ok=True)

        traj_path = os.path.join(results_path, f"3_CoordMovimento_{exp_id}.parquet")
        if not os.path.exists(traj_path):
            log.warning("workflow.reports.missing_trajectory", video=path)
            return

        df = self._read_trajectory(traj_path)
        zone_data = self.project_manager.get_zone_data(video_path=path)
        project_data = getattr(self.project_manager, "project_data", {}) or {}

        service = self.analysis_service
        if service:
            analysis_params = service.collect_analysis_parameters(project_data)
        else:
            analysis_params = {}
        calib = project_data.get("calibration", {})
        px_x_orig, px_y_orig = (
            float(calib.get("pixel_per_cm_x", 1.0)),
            float(calib.get("pixel_per_cm_y", 1.0)),
        )

        p_w, p_h = self._probe_video_dimensions(str(path))
        fb_w = getattr(zone_data, "video_width", p_w) or p_w
        fb_h = getattr(zone_data, "video_height", p_h) or p_h

        arena_poly_px = list(zone_data.polygon or [])
        if not arena_poly_px:
            arena_poly_px = [[0, 0], [fb_w, 0], [fb_w, fb_h], [0, fb_h]]

        off_x, off_y, loc_w, loc_h = self._compute_local_space_geometry(arena_poly_px, fb_w, fb_h)
        arena_poly_local = [(float(x) - off_x, float(y) - off_y) for x, y in arena_poly_px]

        rois, roi_colors_map = self._collect_rois_for_standard(zone_data, off_x, off_y)
        df = self._normalize_df_to_local_space(df, off_x, off_y, loc_w, loc_h)

        px_x, px_y = self._resolve_pixel_cm(metadata, calib, loc_w, loc_h, px_x_orig, px_y_orig)

        frame_crop = (off_x, off_y, loc_w, loc_h)
        video_path_report = self._prepare_background_image(
            path, exp_id, str(results_path), frame_crop
        )

        service = self.analysis_service
        if not service:
            return

        analysis_result = service.run_full_analysis_as_dto(
            trajectory_df=df,
            pixelcm_x=px_x,
            pixelcm_y=px_y,
            video_height_px=int(loc_h),
            arena_polygon_px=arena_poly_local,
            rois=rois,
            fps=float(self.settings.video_processing.fps),
            metadata=metadata,
            roi_colors=roi_colors_map,
            freezing_vel_threshold=self.settings.video_processing.freezing_velocity_threshold,
            freezing_min_duration=self.settings.video_processing.freezing_min_duration_s,
            video_path=video_path_report,
            frame_crop_box=None,
            behavioral_config=analysis_params.get("behavioral_config"),
        )

        report_paths = self._export_individual_outputs(analysis_result, str(results_path), exp_id)
        self.project_manager.register_processing_outputs(
            video_path=path,
            report_path=report_paths["docx"],
            summary_excel=report_paths["xlsx"],
        )

    def _finalize_report_generation(self, count: int, errors: list[str]) -> None:
        """Finalize report generation UI feedback."""
        self._publish_event(UIEvents.UI_SET_STATUS, {"message": "Relatórios gerados."})

        if self._is_batch_processing():
            return

        if errors:
            self._publish_event(
                UIEvents.UI_SHOW_WARNING,
                {
                    "title": "Erros na Geração",
                    "message": "Falhas em:\n" + "\n".join(errors[:5]),
                },
            )
        elif count > 0:
            self._publish_event(
                UIEvents.UI_SHOW_INFO,
                {
                    "title": "Relatórios Gerados",
                    "message": f"Gerados relatórios para {count} vídeos.",
                },
            )

    # ========================================================================
    # Parquet Summary Generation
    # ========================================================================

    def generate_parquet_summaries(
        self,
        video_entries: list[dict],
        settings_obj: Any = None,
    ) -> None:
        """Generate parquet summaries for video entries.

        Args:
            video_entries: List of video entry dicts from ProjectManager.
            settings_obj: Settings instance (uses self.settings if None).
        """
        if not video_entries:
            return

        settings = settings_obj or self.settings

        # Find expected ROI names for schema consistency
        video_paths = [v.get("path", "") for v in video_entries if v.get("path")]
        expected_roi_names = self._find_project_roi_names(video_paths)

        completed, failed, skipped = 0, 0, 0
        for video in video_entries:
            status, msg, _summary_path, _changed = self._process_summary_video(
                video, settings, expected_roi_names
            )
            if status == "completed":
                completed += 1
            elif status == "failed":
                failed += 1
                log.warning("processing.summary.failed", message=msg)
            else:
                skipped += 1

        if completed > 0 and self.project_manager.project_path:
            self.project_manager.save_project()

        log.info(
            "processing.summaries.done",
            completed=completed,
            failed=failed,
            skipped=skipped,
        )

    def _find_project_roi_names(self, video_paths: list[str]) -> list[str] | None:
        """Find ROI names from the first video with zone data."""
        for path in video_paths:
            try:
                zone_data = self.project_manager.get_zone_data(video_path=path)
                if zone_data and (zone_data.roi_names or zone_data.polygon):
                    if zone_data.roi_names:
                        log.info(
                            "processing_coordinator.found_project_rois",
                            video=path,
                            roi_count=len(zone_data.roi_names),
                            roi_names=zone_data.roi_names,
                        )
                        return list(zone_data.roi_names)
            except (OSError, KeyError, ValueError) as e:
                log.debug("processing_coordinator.zone_lookup_failed", video=path, error=str(e))
                continue

        log.warning("processing_coordinator.no_project_rois_found")
        return None

    def _process_summary_video(
        self,
        video: dict,
        settings_obj: Any,
        expected_roi_names: list[str] | None = None,
    ) -> tuple[str, str | None, str | None, bool]:
        """Process a single video for summary generation."""
        self._ensure_analysis_service_ready()

        path = video.get("path")
        if not isinstance(path, str) or not path:
            return "skipped", "Caminho do vídeo não definido.", None, False

        experiment_id = os.path.splitext(os.path.basename(path))[0]
        multi_outputs = video.get("multi_aquarium_outputs")

        # Create project-specific settings snapshot
        settings_snapshot = self._create_project_settings_snapshot()

        if multi_outputs:
            return self._process_multi_summary_video(
                video, experiment_id, path, multi_outputs, settings_snapshot, expected_roi_names
            )

        return self._process_standard_summary_video(
            video, experiment_id, path, settings_snapshot, expected_roi_names
        )

    def _process_multi_summary_video(
        self, video, exp_id, path: Path | str, multi_outputs, settings, expected_rois
    ):
        """Process multi-aquarium video for summary generation."""

        try:
            multi_zone = self.project_manager.get_multi_aquarium_zone_data(path)
            if not multi_zone:
                return "skipped", f"{exp_id}: dados multi-aquário ausentes.", None, False

            processed_count, summary_paths = 0, []
            for aq_id_str, output_info in multi_outputs.items():
                aq_id = int(aq_id_str)
                s_path = self._process_one_aquarium_summary(
                    video,
                    exp_id,
                    path,
                    aq_id,
                    output_info,
                    multi_zone,
                    settings,
                    expected_rois,
                )
                if s_path:
                    summary_paths.append(s_path)
                    processed_count += 1

            if processed_count > 0:
                video["has_complete_data"] = True
                return (
                    "completed",
                    f"{exp_id} ({processed_count} aquários)",
                    summary_paths[-1],
                    True,
                )
            return "skipped", f"{exp_id}: nenhum aquário processado.", None, False
        except Exception as e:  # except Exception justified: multi-aquarium summary pipeline
            log.error("processing.multi_summary_failed", error=str(e))
            return "failed", f"{exp_id}: erro multi-aquário {e}", None, False

    def _process_one_aquarium_summary(
        self, video, exp_id, path: Path | str, aq_id, out, multi_zone, settings, expected
    ):
        """Process summary for a single aquarium in multi-aquarium mode."""
        from zebtrack.analysis.reporters import ParquetSummaryReporter, ReporterContext

        aq_results_dir = out.get("results_dir")
        traj_path = out.get("parquet_files", {}).get("trajectory")
        if not traj_path or not os.path.exists(traj_path):
            return None

        aq_zone = next((a for a in multi_zone.aquariums if getattr(a, "id", None) == aq_id), None)
        if not aq_zone:
            return None

        df = self._read_trajectory(traj_path)
        if df.empty:
            return None

        calib = self.project_manager.project_data.get("calibration", {})
        px_x, px_y, poly_warped, video_h, rois, colors, cal = self._prepare_summary_geometry(
            aq_zone.polygon,
            aq_zone.roi_polygons,
            aq_zone.roi_names,
            aq_zone.roi_colors,
            calib,
        )

        aq_meta = {
            "experiment_id": f"{exp_id}_aq{aq_id}",
            "video_name": exp_id,
            "group": out.get("group"),
            "subject": out.get("subject_id"),
            "day": out.get("day"),
            "aquarium_id": aq_id,
        }

        behavioral_config = {}
        if self.analysis_service:
            behavioral_config = self.analysis_service.collect_analysis_parameters(
                self.project_manager.project_data
            ).get("behavioral_config", {})

        ctx = ReporterContext(
            trajectory_df=df,
            metadata=aq_meta,
            pixelcm_x=px_x,
            pixelcm_y=px_y,
            video_height_px=video_h,
            arena_polygon_px=poly_warped,
            rois=rois,
            fps=settings.video_processing.fps,
            roi_colors=colors,
            video_path=str(path),
            calibration=cal,
            frame_crop_box=out.get("frame_crop_box"),
            behavioral_config=behavioral_config,
            settings_obj=settings,
        )

        os.makedirs(aq_results_dir, exist_ok=True)
        s_path = os.path.join(aq_results_dir, f"{exp_id}_aq{aq_id}_summary.parquet")
        ParquetSummaryReporter(ctx).export_summary(s_path, expected_roi_names=expected)
        video["multi_aquarium_outputs"][str(aq_id)]["parquet_files"]["summary"] = s_path
        return s_path

    def _process_standard_summary_video(self, video, exp_id, path: Path | str, settings, expected):
        """Process standard single-aquarium video for summary generation."""
        from zebtrack.analysis.reporters import ParquetSummaryReporter, ReporterContext

        res_path = self.project_manager.resolve_results_directory(exp_id, video_path=str(path))
        res_dir = str(res_path)
        traj_path = video.get("parquet_files", {}).get("trajectory")
        if not traj_path or not os.path.exists(traj_path):
            candidates = [
                os.path.join(res_dir, f"3_CoordMovimento_{exp_id}.parquet"),
                os.path.join(os.path.dirname(path), f"3_CoordMovimento_{exp_id}.parquet"),
            ]
            traj_path = next((c for c in candidates if os.path.exists(c)), None)
        if not traj_path:
            return "skipped", f"{exp_id}: trajetória ausente.", None, False

        df = self._read_trajectory(traj_path)
        if df.empty:
            return "skipped", f"{exp_id}: trajetória vazia.", None, False

        self.project_manager.set_active_zone_video(path)
        try:
            zone_data = self.project_manager.get_zone_data(video_path=path)
            calib = self.project_manager.project_data.get("calibration", {}) or {}
            px_x, px_y, poly_warped, video_h, rois, colors, cal = self._prepare_summary_geometry(
                list(zone_data.polygon or []),
                list(zone_data.roi_polygons),
                list(zone_data.roi_names),
                list(zone_data.roi_colors),
                calib,
            )

            meta = self.project_manager.get_metadata_for_experiment(
                exp_id, video_path=str(path)
            ) or {"experiment_id": exp_id}
            behavioral_config = {}
            service = self.analysis_service
            if service:
                behavioral_config = service.collect_analysis_parameters(
                    self.project_manager.project_data
                ).get("behavioral_config", {})

            ctx = ReporterContext(
                trajectory_df=df,
                metadata=meta,
                pixelcm_x=px_x,
                pixelcm_y=px_y,
                video_height_px=video_h,
                arena_polygon_px=poly_warped,
                rois=rois,
                fps=settings.video_processing.fps,
                roi_colors=colors,
                video_path=str(path),
                behavioral_config=behavioral_config,
                settings_obj=settings,
            )

            os.makedirs(res_dir, exist_ok=True)
            s_path = os.path.join(res_dir, f"{exp_id}_summary.parquet")
            ParquetSummaryReporter(ctx).export_summary(s_path, expected_roi_names=expected)
            video.setdefault("parquet_files", {})["summary"] = s_path
            video["has_complete_data"] = True
            return "completed", exp_id, s_path, True
        except Exception as e:  # except Exception justified: single-video summary I/O + transforms
            return "failed", f"{exp_id}: erro {e}", None, False
        finally:
            self.project_manager.set_active_zone_video(None)

    # ========================================================================
    # Supporting Methods (Metadata, Geometry, Background)
    # ========================================================================

    def _extract_metadata_from_config(self, config: dict) -> dict:
        """Extract metadata from single video config."""
        metadata: dict[str, Any] = {}
        if config:
            for key in ["group", "group_display_name", "day", "subject"]:
                if key in config:
                    metadata[key] = config[key]

            for dim_key in ("aquarium_width_cm", "aquarium_height_cm"):
                if dim_key in config:
                    val = config.get(dim_key)
                    if val not in (None, ""):
                        try:
                            metadata[dim_key] = float(str(val))
                        except (TypeError, ValueError):
                            log.debug(
                                "processing_coordinator.metadata_dim_parse.suppressed",
                                dim_key=dim_key,
                                exc_info=True,
                            )

        if "group" not in metadata:
            metadata["group"] = "single_video"
        if "group_display_name" not in metadata:
            metadata["group_display_name"] = "Vídeo Único"
        if "day" not in metadata:
            metadata["day"] = "1"
        if "subject" not in metadata:
            metadata["subject"] = "1"

        return metadata

    def _enrich_unified_report_metadata(
        self, df: pd.DataFrame, entry_meta: dict, process_entry: dict
    ) -> pd.DataFrame:
        """Enrich DataFrame with metadata columns for unified report."""
        df = df.copy()

        g_val = entry_meta.get("group") or entry_meta.get("group_id")
        df["group_id"] = g_val or "N/A"

        if "group" in df.columns:
            df.drop(columns=["group"], inplace=True)

        df["subject"] = entry_meta.get("subject") or "N/A"
        df["day"] = entry_meta.get("day") or "N/A"

        auth_exp_id = entry_meta.get("experiment_id") or process_entry.get("experiment_id")
        if auth_exp_id:
            df["experiment_id"] = auth_exp_id
        elif "experiment_id" not in df.columns:
            df["experiment_id"] = "N/A"

        if "aquarium_id" in entry_meta:
            df["aquarium_id"] = entry_meta["aquarium_id"]

        if process_entry.get("is_multi"):
            df["is_multi_aquarium"] = True

        return df

    def _ensure_analysis_service_ready(self) -> None:
        """Ensure AnalysisService is initialized with current settings."""
        if not self.analysis_service:
            from zebtrack.analysis.analysis_service import AnalysisService

            self.analysis_service = AnalysisService(settings_obj=self.settings)
        elif self.analysis_service.settings is None:
            self.analysis_service.settings = self.settings

    def _create_project_settings_snapshot(self) -> Any:
        """Create a settings snapshot with project-level overrides applied."""
        # Import here to avoid circular imports during module loading
        import copy

        settings_snapshot = copy.deepcopy(self.settings)

        project_data = getattr(self.project_manager, "project_data", {}) or {}

        # Apply project overrides
        if "analysis_interval_frames" in project_data:
            settings_snapshot.video_processing.processing_interval = int(
                project_data["analysis_interval_frames"]
            )
        if "display_interval_frames" in project_data:
            settings_snapshot.video_processing.display_interval = int(
                project_data["display_interval_frames"]
            )
        if "single_animal_per_aquarium" in project_data:
            settings_snapshot.video_processing.single_animal_per_aquarium = bool(
                project_data["single_animal_per_aquarium"]
            )

        return settings_snapshot

    def _collect_rois_for_aquarium(
        self, zone_data: Any, aq_id: int, off_x: float, off_y: float
    ) -> tuple[list[ROI], dict]:
        """Extract ROIs for a specific aquarium in multi-aquarium data."""
        rois: list[ROI] = []
        roi_colors_map: dict = {}
        if hasattr(zone_data, "aquariums") and zone_data.aquariums:
            for aq in zone_data.aquariums:
                if aq.id != aq_id:
                    continue
                for i, poly in enumerate(aq.roi_polygons):
                    translated_poly = [(float(px) - off_x, float(py) - off_y) for px, py in poly]
                    name = aq.roi_names[i] if i < len(aq.roi_names) else f"ROI_{i}"
                    roi = build_roi_from_polygon(name, translated_poly)
                    if roi is not None:
                        rois.append(roi)
                    if i < len(aq.roi_colors):
                        roi_colors_map[name] = aq.roi_colors[i]
                break
        return rois, roi_colors_map

    def _collect_rois_for_standard(
        self, zone_data: Any, off_x: float, off_y: float
    ) -> tuple[list[ROI], dict]:
        """Extract ROIs for standard single-aquarium data."""
        rois: list[ROI] = []
        roi_colors_map: dict = {}
        if zone_data:
            for i, poly in enumerate(zone_data.roi_polygons):
                translated_poly = [(float(px) - off_x, float(py) - off_y) for px, py in poly]
                name = zone_data.roi_names[i] if i < len(zone_data.roi_names) else f"ROI_{i}"
                roi = build_roi_from_polygon(name, translated_poly)
                if roi is not None:
                    rois.append(roi)
                if i < len(zone_data.roi_colors):
                    roi_colors_map[name] = zone_data.roi_colors[i]
        return rois, roi_colors_map

    def _resolve_pixel_cm(
        self,
        metadata: dict,
        calib: dict,
        loc_w: float,
        loc_h: float,
        px_x_orig: float = 1.0,
        px_y_orig: float = 1.0,
    ) -> tuple[float, float]:
        """Resolve pixel/cm ratio using project calibration or metadata fallbacks."""
        w_cm = metadata.get("aquarium_width_cm") or calib.get("aquarium_width_cm")
        h_cm = metadata.get("aquarium_height_cm") or calib.get("aquarium_height_cm")

        px_x = (
            px_x_orig if px_x_orig > 1.0 else (loc_w / float(w_cm) if (w_cm and loc_w > 0) else 1.0)
        )
        px_y = (
            px_y_orig if px_y_orig > 1.0 else (loc_h / float(h_cm) if (h_cm and loc_h > 0) else 1.0)
        )
        return px_x, px_y

    def _prepare_background_image(
        self,
        video_file: Path | str,
        exp_id: str,
        results_dir: Path | str,
        crop_box: tuple | None,
    ) -> str:
        """Extract and save a cropped frame for report backgrounds."""
        if crop_box:
            frame = self._extract_cropped_background_frame(str(video_file), crop_box)
            if frame is not None:
                try:
                    bg_path = os.path.join(results_dir, f"{exp_id}_bg.png")
                    if self._frame_extractor is not None:
                        self._frame_extractor.save_frame(frame, bg_path)
                    else:
                        import cv2 as _cv2  # pragma: no cover

                        _cv2.imwrite(bg_path, frame)  # pragma: no cover
                    return bg_path
                except OSError:
                    log.warning(
                        "processing_coordinator.save_background_frame.failed",
                        exc_info=True,
                    )
        return str(video_file)

    def _export_individual_outputs(
        self, analysis_result: Any, results_dir: Path | str, exp_id: str
    ) -> dict[str, str]:
        """Export individual Word and Excel reports."""
        from zebtrack.analysis.reporters import (
            ExcelReporter,
            ReporterContext,
            WordReporter,
        )

        ctx = ReporterContext.from_analysis(analysis_result)
        os.makedirs(results_dir, exist_ok=True)
        report_base = os.path.join(results_dir, f"4_Relatorio_{exp_id}")
        docx_path = f"{report_base}.docx"
        xlsx_path = f"{report_base}.xlsx"
        WordReporter(ctx).export_individual_report(docx_path)
        ExcelReporter(ctx).export_summary(xlsx_path)
        return {"docx": docx_path, "xlsx": xlsx_path}

    def _probe_video_dimensions(self, video_file: str) -> tuple[int, int]:
        """Probe video width and height."""
        if self._video_metadata_service is not None:
            dims = self._video_metadata_service.get_video_dimensions(video_file)
            if dims is not None:
                return dims
            return (0, 0)
        # Fallback when service not injected
        import cv2 as _cv2  # pragma: no cover

        cap = _cv2.VideoCapture(video_file)  # pragma: no cover
        if not cap.isOpened():  # pragma: no cover
            return (0, 0)  # pragma: no cover
        w = int(cap.get(_cv2.CAP_PROP_FRAME_WIDTH))  # pragma: no cover
        h = int(cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))  # pragma: no cover
        cap.release()  # pragma: no cover
        return w, h  # pragma: no cover

    def _compute_local_space_geometry(
        self, polygon: list, fb_w: int, fb_h: int
    ) -> tuple[int, int, int, int]:
        """Compute local space geometry for an aquarium."""
        if not polygon:
            return 0, 0, max(fb_w, 1), max(fb_h, 1)
        xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
        min_x, min_y = math.floor(min(xs)), math.floor(min(ys))
        max_x, max_y = math.ceil(max(xs)), math.ceil(max(ys))
        return min_x, min_y, max(max_x - min_x, 1), max(max_y - min_y, 1)

    def _normalize_df_to_local_space(
        self, df: pd.DataFrame, offset_x: float, offset_y: float, w: float, h: float
    ) -> pd.DataFrame:
        """Normalize dataframe coordinates to local aquarium space."""
        if offset_x == 0 and offset_y == 0:
            return df.copy()
        local_df = df.copy()
        cols_to_drop = ["x_cm", "y_cm", "x_center_cm", "y_center_cm"]
        local_df = local_df.drop(columns=[c for c in cols_to_drop if c in local_df.columns])
        for col in ("x_center_px", "x1", "x2"):
            if col in local_df.columns:
                local_df[col] = (local_df[col] - offset_x).clip(lower=0, upper=w)
        for col in ("y_center_px", "y1", "y2"):
            if col in local_df.columns:
                local_df[col] = (local_df[col] - offset_y).clip(lower=0, upper=h)
        return local_df

    def _extract_cropped_background_frame(self, video_file: str, crop_box: tuple) -> Any | None:
        """Extract a single cropped frame from video."""
        if not crop_box:
            return None
        if self._frame_extractor is not None:
            return self._frame_extractor.extract_and_crop_frame(video_file, crop_box)
        # Fallback when service not injected
        import cv2 as _cv2  # pragma: no cover

        cap = _cv2.VideoCapture(video_file)  # pragma: no cover
        ret, frame = cap.read()  # pragma: no cover
        cap.release()  # pragma: no cover
        if not ret or frame is None:  # pragma: no cover
            log.warning(  # pragma: no cover
                "workflow.report.frame_read_failed",
                video_file=str(video_file),
            )
            return None  # pragma: no cover
        frame_h, frame_w = frame.shape[:2]  # pragma: no cover
        x, y, w, h = map(int, crop_box)  # pragma: no cover
        x = max(0, min(x, frame_w - 1))  # pragma: no cover
        y = max(0, min(y, frame_h - 1))  # pragma: no cover
        w = min(w, frame_w - x)  # pragma: no cover
        h = min(h, frame_h - y)  # pragma: no cover
        if w <= 0 or h <= 0:  # pragma: no cover
            return None  # pragma: no cover
        return frame[y : y + h, x : x + w].copy()  # pragma: no cover

    def _prepare_summary_geometry(
        self,
        poly: list,
        r_polys: list,
        r_names: list,
        r_colors: list,
        calib: dict,
    ) -> tuple:
        """Common geometry preparation for summary generation."""
        import numpy as _np  # lazy: only needed for Calibration constructor

        w_cm = calib.get("aquarium_width_cm", 0)
        h_cm = calib.get("aquarium_height_cm", 0)
        cal = Calibration(_np.array(poly), w_cm, h_cm)
        _, video_h = cal.target_dims_px
        px_x, px_y = cal.pixel_per_cm_ratio
        poly_warped = cal.transform_points(poly)

        rois: list[ROI] = []
        for i, r_poly in enumerate(r_polys):
            wp = cal.transform_points(r_poly)
            name = r_names[i] if i < len(r_names) else f"ROI {i + 1}"
            roi = build_roi_from_polygon(
                name, [(float(x), float(y)) for x, y in wp], coordinate_space="px"
            )
            if roi is not None:
                rois.append(roi)

        colors = {
            (r_names[i] if i < len(r_names) else f"ROI {i + 1}"): r_colors[i]
            for i in range(len(r_colors))
        }
        return px_x, px_y, poly_warped, video_h, rois, colors, cal
