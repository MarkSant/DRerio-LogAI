"""Report generation coordinator for video processing outputs.

Phase 4: Extracted from ProcessingCoordinator.
Handles unified report generation, individual video reports (Word/Excel),
parquet summary generation, and all supporting geometry/calibration helpers.

Estimated size: ~1000 lines (target <800, acceptable at ~1000 due to
report complexity and many private helpers).
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np
import pandas as pd
import structlog
from shapely.geometry import Polygon

from zebtrack.analysis.roi import ROI
from zebtrack.coordinators.base_coordinator import BaseCoordinator
from zebtrack.core.calibration import Calibration
from zebtrack.core.detector import MultiAquariumZoneData, ZoneData
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.analysis.analysis_service import AnalysisService
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


class ReportGenerationCoordinator(BaseCoordinator):
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
        event_bus: EventBus | None = None,
    ) -> None:
        super().__init__(state_manager, event_bus)
        self.project_manager = project_manager
        self.settings = settings_obj
        self.analysis_service = analysis_service

        # Cross-coordinator references (set post-construction)
        self._progress_coordinator: Any = None

        log.info("report_generation_coordinator.initialized")

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
    # Unified Report Generation
    # ========================================================================

    def generate_unified_report(
        self,
        video_paths: list[str] | None = None,
        *,
        replace_existing: bool = False,
        report_scope: str = "all",
    ) -> None:
        """Generate a unified report aggregating data from multiple videos."""
        if not video_paths:
            return

        scope = "selected" if report_scope == "selected" else "all"
        log.info(
            "workflow.unified_report.start",
            count=len(video_paths),
            scope=scope,
            replace_existing=replace_existing,
        )
        self._publish_event(Events.UI_SET_STATUS, {"message": "Gerando relatório unificado..."})

        project_path = self.project_manager.project_path
        if not project_path:
            return

        unified_dir = Path(project_path) / "unified_reports"
        unified_dir.mkdir(parents=True, exist_ok=True)

        if replace_existing:
            self._cleanup_unified_reports(unified_dir)

        dfs = []
        roi_colors_map: dict = {}

        for path in video_paths:
            entry = self.project_manager.find_video_entry(path=path)
            if not entry:
                continue

            # Collect ROI colors from zone data
            try:
                zone_data = self.project_manager.get_zone_data(video_path=path)
                if zone_data and zone_data.roi_names and zone_data.roi_colors:
                    for roi_name, color in zip(
                        zone_data.roi_names, zone_data.roi_colors, strict=True
                    ):
                        if roi_name not in roi_colors_map:
                            roi_colors_map[roi_name] = color
            except (OSError, KeyError, ValueError) as e:
                log.debug(
                    "workflow.unified_report.color_collection_failed", path=path, error=str(e)
                )

            # Handle multi-aquarium entries
            multi_outputs = entry.get("multi_aquarium_outputs")
            entries_to_process = []

            if multi_outputs:
                exp_id = entry.get("experiment_id", os.path.splitext(os.path.basename(path))[0])
                fresh_meta = self.project_manager.get_metadata_for_experiment(
                    exp_id, video_path=path
                )
                for aq_id, out_info in multi_outputs.items():
                    entries_to_process.append(
                        {
                            "parquet_files": out_info.get("parquet_files", {}),
                            "metadata": {
                                "group": out_info.get("group") or fresh_meta.get("group"),
                                "group_id": out_info.get("group") or fresh_meta.get("group_id"),
                                "subject": (
                                    out_info.get("subject_id") or fresh_meta.get("subject")
                                ),
                                "day": out_info.get("day") or fresh_meta.get("day"),
                                "experiment_id": (
                                    f"{os.path.splitext(os.path.basename(path))[0]}_aq{aq_id}"
                                ),
                                "aquarium_id": aq_id,
                            },
                            "is_multi": True,
                        }
                    )
            else:
                exp_id = entry.get("experiment_id", os.path.splitext(os.path.basename(path))[0])
                fresh_meta = self.project_manager.get_metadata_for_experiment(
                    exp_id, video_path=path
                )
                entries_to_process.append(
                    {
                        "parquet_files": entry.get("parquet_files", {}),
                        "metadata": fresh_meta,
                        "experiment_id": exp_id,
                        "is_multi": False,
                    }
                )

            for process_entry in entries_to_process:
                parquet_files = process_entry.get("parquet_files", {})
                summary_path = parquet_files.get("summary")
                entry_meta = process_entry.get("metadata", {})

                if summary_path and os.path.exists(summary_path):
                    try:
                        df = pd.read_parquet(summary_path)
                        if entry_meta:
                            df = self._enrich_unified_report_metadata(df, entry_meta, process_entry)
                        dfs.append(df)
                    except Exception as e:
                        log.warning(
                            "workflow.unified_report.read_failed",
                            file=summary_path,
                            error=str(e),
                        )

        if not dfs:
            self._publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Dados insuficientes",
                    "message": ("Não foi possível encontrar sumários para os vídeos selecionados."),
                },
            )
            return

        try:
            final_df, schema_mismatch, all_columns = self._align_and_concatenate_unified_dfs(dfs)
            self._export_unified_reports(
                final_df,
                unified_dir,
                roi_colors_map,
                schema_mismatch,
                all_columns,
                report_scope=scope,
            )
        except Exception as e:
            log.error("workflow.unified_report.failed", error=str(e), exc_info=True)
            self._publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro no Relatório", "message": f"{e}"},
            )
        finally:
            self._publish_event(Events.UI_SET_STATUS, {"message": "Pronto."})
            self._publish_event(Events.UI_REFRESH_PROJECT_VIEWS, {})

    def _align_and_concatenate_unified_dfs(self, dfs: list) -> tuple:
        """Align and concatenate multiple summary DataFrames with different schemas."""
        if not dfs:
            return pd.DataFrame(), False, []

        if len(dfs) == 1:
            return dfs[0], False, list(dfs[0].columns)

        from zebtrack.analysis.data_transformer import DataTransformer

        standardized_dfs = []
        for df in dfs:
            rename_map = {}
            for col in df.columns:
                translated = DataTransformer.translate_column_name(col)
                if translated != col:
                    rename_map[col] = translated
            if rename_map:
                df = df.rename(columns=rename_map)
            if df.columns.duplicated().any():
                df = df.loc[:, ~df.columns.duplicated()]
            standardized_dfs.append(df)

        dfs = standardized_dfs

        all_columns_set: set[str] = set()
        for df in dfs:
            all_columns_set.update(df.columns)

        priority_cols = [
            "group",
            "subject",
            "day",
            "experiment_id",
            "aquarium_id",
            "is_multi_aquarium",
        ]
        priority_present = [c for c in priority_cols if c in all_columns_set]
        other_cols = sorted(c for c in all_columns_set if c not in priority_cols)
        all_columns = priority_present + other_cols

        reference_cols = set(dfs[0].columns)
        schema_mismatch = any(set(df.columns) != reference_cols for df in dfs[1:])

        aligned_dfs = [df.reindex(columns=all_columns) for df in dfs]
        non_empty_dfs = [df for df in aligned_dfs if not df.empty]

        if not non_empty_dfs:
            final_df = pd.DataFrame(columns=all_columns)
        else:
            import warnings

            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    category=FutureWarning,
                    message=".*concatenation with empty or all-NA entries.*",
                )
                final_df = pd.concat(non_empty_dfs, ignore_index=True)

        return final_df, schema_mismatch, all_columns

    def _cleanup_unified_reports(self, unified_dir: Path) -> None:
        """Remove previous unified report artifacts before a fresh export run."""
        patterns = [
            "*.docx",
            "*.xlsx",
            "*.parquet",
            "unified_run_*.json",
            "latest_unified_run.json",
        ]
        removed = 0
        for pattern in patterns:
            for artifact in unified_dir.glob(pattern):
                if not artifact.is_file():
                    continue
                try:
                    artifact.unlink(missing_ok=True)
                    removed += 1
                except OSError:
                    log.warning(
                        "workflow.unified_report.cleanup_failed",
                        file=str(artifact),
                        exc_info=True,
                    )
        log.info(
            "workflow.unified_report.cleanup_completed",
            removed=removed,
            dir=str(unified_dir),
        )

    def _export_unified_reports(
        self,
        final_df,
        unified_dir: Path,
        roi_colors_map: dict,
        schema_mismatch: bool,
        all_columns: list,
        *,
        report_scope: str = "all",
    ) -> None:
        """Export unified reports (Parquet, Excel, and Word)."""
        from zebtrack.analysis.reporter import Reporter

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        scope_prefix = "unified_partial" if report_scope == "selected" else "unified"

        exported_artifacts: list[str] = []
        export_failures: list[str] = []
        exported_paths: dict[str, str] = {}

        # 1. Export Parquet
        parquet_path = unified_dir / f"{scope_prefix}_summary_{run_id}.parquet"
        try:
            final_df.to_parquet(parquet_path, index=False)
            exported_artifacts.append(parquet_path.name)
            exported_paths["parquet"] = str(parquet_path)
            log.info("workflow.unified_report.parquet_exported", path=str(parquet_path))
        except (OSError, ValueError) as e:
            export_failures.append(f"Parquet: {e}")
            log.error("workflow.unified_report.parquet_failed", error=str(e), exc_info=True)

        # 2. Export Excel
        excel_path = unified_dir / f"{scope_prefix}_summary_{run_id}.xlsx"
        try:
            from zebtrack.analysis.data_transformer import DataTransformer

            display_df = DataTransformer().prepare_for_display(final_df)
            display_df.to_excel(excel_path, index=False, engine="openpyxl")
            exported_artifacts.append(excel_path.name)
            exported_paths["excel"] = str(excel_path)
            log.info("workflow.unified_report.excel_exported", path=str(excel_path))
        except Exception as e:
            export_failures.append(f"Excel: {e}")
            log.error("workflow.unified_report.excel_failed", error=str(e), exc_info=True)

        # 3. Export Word
        word_path = unified_dir / f"{scope_prefix}_report_{run_id}"
        try:
            word_df = final_df.copy()
            for col in word_df.columns:
                word_df[col] = (
                    word_df[col].where(word_df[col].notna(), np.nan).infer_objects(copy=False)
                )
            Reporter.export_project_report(
                aggregated_df=word_df,
                output_path=word_path,
                roi_colors=roi_colors_map if roi_colors_map else None,
                detector_params=None,
            )
            exported_artifacts.append(f"{word_path.name}.docx")
            exported_paths["word"] = f"{word_path}.docx"
            log.info("workflow.unified_report.word_exported", path=str(word_path) + ".docx")
        except Exception as e:
            export_failures.append(f"Word: {e}")
            log.error("workflow.unified_report.word_failed", error=str(e), exc_info=True)

        if not exported_artifacts:
            failure_details = "\n".join(f"• {item}" for item in export_failures[:3])
            raise RuntimeError(
                "Não foi possível gerar nenhum arquivo do relatório unificado."
                + (f"\n\nDetalhes:\n{failure_details}" if failure_details else "")
            )

        if export_failures:
            self._publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Relatório Unificado Parcial",
                    "message": (
                        "Alguns arquivos não puderam ser gerados.\n"
                        "Gerados: "
                        + ", ".join(exported_artifacts)
                        + "\n\nFalhas:\n"
                        + "\n".join(f"• {item}" for item in export_failures[:3])
                    ),
                },
            )

        self._write_unified_run_manifest(
            unified_dir=unified_dir,
            run_id=run_id,
            report_scope=report_scope,
            exported_paths=exported_paths,
            export_failures=export_failures,
            row_count=len(final_df),
        )

        if schema_mismatch:
            log.warning(
                "workflow.unified_report.schema_mismatch",
                message="DataFrames had different column sets; missing values filled with NA",
                columns=all_columns,
            )
            if not self.settings.ui_features.suppress_roi_mismatch_warning:
                self._publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "ROIs Diferentes",
                        "message": (
                            "Os vídeos selecionados possuem ROIs diferentes.\n"
                            "Colunas ausentes foram preenchidas com valores vazios (NA)."
                        ),
                    },
                )

        if not self._is_batch_processing():
            self._publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": (
                        "Relatório Unificado Parcial"
                        if report_scope == "selected"
                        else "Relatório Unificado"
                    ),
                    "message": (
                        f"Relatório unificado gerado com sucesso em:\n{unified_dir}\n\n"
                        f"Arquivos: {', '.join(exported_artifacts)}"
                    ),
                },
            )

    def _write_unified_run_manifest(
        self,
        *,
        unified_dir: Path,
        run_id: str,
        report_scope: str,
        exported_paths: dict[str, str],
        export_failures: list[str],
        row_count: int,
    ) -> None:
        """Persist a run manifest for unified report consistency."""
        manifest = {
            "run_id": run_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "scope": report_scope,
            "row_count": row_count,
            "artifacts": exported_paths,
            "failures": export_failures,
        }

        manifest_path = unified_dir / f"unified_run_{run_id}.json"
        latest_path = unified_dir / "latest_unified_run.json"

        with manifest_path.open("w", encoding="utf-8") as fp:
            json.dump(manifest, fp, ensure_ascii=False, indent=2)

        with latest_path.open("w", encoding="utf-8") as fp:
            json.dump(manifest, fp, ensure_ascii=False, indent=2)

        log.info(
            "workflow.unified_report.manifest_written",
            run_id=run_id,
            path=str(manifest_path),
            artifacts=list(exported_paths.keys()),
        )

    # ========================================================================
    # Individual Video Reports
    # ========================================================================

    def generate_project_reports(self, video_paths: list[str] | None = None) -> None:
        """Generate reports (Word, Excel, Parquet) for specified videos."""
        if not video_paths:
            return

        log.info("workflow.reports.start", count=len(video_paths))
        self._publish_event(Events.UI_SET_STATUS, {"message": "Gerando relatórios detalhados..."})

        entries = [self.project_manager.find_video_entry(path=p) for p in video_paths]
        self.generate_parquet_summaries([e for e in entries if e], self.settings)

        count, errors = 0, []
        self._ensure_analysis_service_ready()

        for path in video_paths:
            try:
                self._generate_single_video_reports(path)
                count += 1
            except Exception as e:
                log.exception("workflow.reports.video_failed", video=path, error=str(e))
                errors.append(f"{os.path.basename(path)}: {e}")

        self._finalize_report_generation(count, errors)

    def _generate_single_video_reports(self, path: str) -> None:
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
        self, path: str, exp_id: str, entry: dict, multi_outputs: dict
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
        self, path, exp_id, entry, aq_id, output_info, zone_data, calib, fps, p_w, p_h, params
    ) -> None:
        """Process a single aquarium within a multi-aquarium video for report generation."""
        aq_results_dir = output_info.get("results_dir")
        aq_parquet_files = output_info.get("parquet_files", {})
        trajectory_path = aq_parquet_files.get("trajectory")

        if not trajectory_path or not os.path.exists(trajectory_path):
            log.warning("workflow.reports.multi_aquarium.missing_trajectory", video=path, aq=aq_id)
            return

        df = pd.read_parquet(trajectory_path)
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
        self, path: str, exp_id: str, entry: dict, metadata: dict
    ) -> None:
        """Generate report for a standard (single aquarium) video."""
        metadata = dict(metadata) if isinstance(metadata, dict) else {}
        metadata.setdefault("experiment_id", exp_id)
        metadata.setdefault("video_name", exp_id)
        metadata.setdefault("group", "single_video")
        metadata.setdefault("day", "1")
        metadata.setdefault("subject", "1")

        results_path = self.project_manager.resolve_results_directory(
            exp_id, video_path=path, metadata=metadata
        )
        os.makedirs(results_path, exist_ok=True)

        traj_path = os.path.join(results_path, f"3_CoordMovimento_{exp_id}.parquet")
        if not os.path.exists(traj_path):
            log.warning("workflow.reports.missing_trajectory", video=path)
            return

        df = pd.read_parquet(traj_path)
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
        video_path_report = self._prepare_background_image(path, exp_id, results_path, frame_crop)

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

        report_paths = self._export_individual_outputs(analysis_result, results_path, exp_id)
        self.project_manager.register_processing_outputs(
            video_path=path,
            report_path=report_paths["docx"],
            summary_excel=report_paths["xlsx"],
        )

    def _finalize_report_generation(self, count: int, errors: list[str]) -> None:
        """Finalize report generation UI feedback."""
        self._publish_event(Events.UI_SET_STATUS, {"message": "Relatórios gerados."})

        if self._is_batch_processing():
            return

        if errors:
            self._publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Erros na Geração",
                    "message": "Falhas em:\n" + "\n".join(errors[:5]),
                },
            )
        elif count > 0:
            self._publish_event(
                Events.UI_SHOW_INFO,
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
            status, msg, summary_path, changed = self._process_summary_video(
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
        self, video, exp_id, path, multi_outputs, settings, expected_rois
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
        except Exception as e:
            log.error("processing.multi_summary_failed", error=str(e))
            return "failed", f"{exp_id}: erro multi-aquário {e}", None, False

    def _process_one_aquarium_summary(
        self, video, exp_id, path, aq_id, out, multi_zone, settings, expected
    ):
        """Process summary for a single aquarium in multi-aquarium mode."""
        from zebtrack.analysis.reporter import Reporter

        aq_results_dir = out.get("results_dir")
        traj_path = out.get("parquet_files", {}).get("trajectory")
        if not traj_path or not os.path.exists(traj_path):
            return None

        aq_zone = next((a for a in multi_zone.aquariums if getattr(a, "id", None) == aq_id), None)
        if not aq_zone:
            return None

        df = pd.read_parquet(traj_path)
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

        reporter = Reporter(
            trajectory_df=df,
            metadata=aq_meta,
            pixelcm_x=px_x,
            pixelcm_y=px_y,
            video_height_px=video_h,
            arena_polygon_px=poly_warped,
            rois=rois,
            fps=settings.video_processing.fps,
            roi_colors=colors,
            video_path=path,
            calibration=cal,
            frame_crop_box=out.get("frame_crop_box"),
            behavioral_config=behavioral_config,
            settings_obj=settings,
        )

        os.makedirs(aq_results_dir, exist_ok=True)
        s_path = os.path.join(aq_results_dir, f"{exp_id}_aq{aq_id}_summary.parquet")
        reporter.export_summary_data(s_path, format="parquet", expected_roi_names=expected)
        video["multi_aquarium_outputs"][str(aq_id)]["parquet_files"]["summary"] = s_path
        return s_path

    def _process_standard_summary_video(self, video, exp_id, path, settings, expected):
        """Process standard single-aquarium video for summary generation."""
        from zebtrack.analysis.reporter import Reporter

        res_path = self.project_manager.resolve_results_directory(exp_id, video_path=path)
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

        df = pd.read_parquet(traj_path)
        if df.empty:
            return "skipped", f"{exp_id}: trajetória vazia.", None, False

        self.project_manager.set_active_zone_video(path)
        try:
            zone_data = self.project_manager.get_zone_data(video_path=path)
            calib = self.project_manager.project_data.get("calibration", {}) or {}
            px_x, px_y, poly_warped, video_h, rois, colors, cal = self._prepare_summary_geometry(
                zone_data.polygon or [],
                zone_data.roi_polygons,
                zone_data.roi_names,
                zone_data.roi_colors,
                calib,
            )

            meta = self.project_manager.get_metadata_for_experiment(exp_id, video_path=path) or {
                "experiment_id": exp_id
            }
            behavioral_config = {}
            service = self.analysis_service
            if service:
                behavioral_config = service.collect_analysis_parameters(
                    self.project_manager.project_data
                ).get("behavioral_config", {})

            reporter = Reporter(
                trajectory_df=df,
                metadata=meta,
                pixelcm_x=px_x,
                pixelcm_y=px_y,
                video_height_px=video_h,
                arena_polygon_px=poly_warped,
                rois=rois,
                fps=settings.video_processing.fps,
                roi_colors=colors,
                video_path=path,
                calibration=cal,
                behavioral_config=behavioral_config,
                settings_obj=settings,
            )

            os.makedirs(res_dir, exist_ok=True)
            s_path = os.path.join(res_dir, f"{exp_id}_summary.parquet")
            reporter.export_summary_data(s_path, format="parquet", expected_roi_names=expected)
            video.setdefault("parquet_files", {})["summary"] = s_path
            video["has_complete_data"] = True
            return "completed", exp_id, s_path, True
        except Exception as e:
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
            settings_snapshot.video_processing.analysis_interval_frames = int(
                project_data["analysis_interval_frames"]
            )
        if "display_interval_frames" in project_data:
            settings_snapshot.video_processing.display_interval_frames = int(
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
                    if len(translated_poly) >= 3:
                        rois.append(
                            ROI(
                                name=name,
                                geometry=Polygon(translated_poly),
                                coordinate_space="px",
                            )
                        )
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
                if len(translated_poly) >= 3:
                    rois.append(
                        ROI(
                            name=name,
                            geometry=Polygon(translated_poly),
                            coordinate_space="px",
                        )
                    )
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
        video_file: str,
        exp_id: str,
        results_dir: str,
        crop_box: tuple | None,
    ) -> str:
        """Extract and save a cropped frame for report backgrounds."""
        if crop_box:
            frame = self._extract_cropped_background_frame(video_file, crop_box)
            if frame is not None:
                try:
                    bg_path = os.path.join(results_dir, f"{exp_id}_bg.png")
                    cv2.imwrite(bg_path, frame)
                    return bg_path
                except OSError:
                    log.warning(
                        "processing_coordinator.save_background_frame.failed",
                        exc_info=True,
                    )
        return video_file

    def _export_individual_outputs(
        self, analysis_result: Any, results_dir: str, exp_id: str
    ) -> dict[str, str]:
        """Export individual Word and Excel reports."""
        from zebtrack.analysis.reporter import Reporter

        reporter = Reporter.from_analysis(analysis_result)
        os.makedirs(results_dir, exist_ok=True)
        report_base = os.path.join(results_dir, f"4_Relatorio_{exp_id}")
        docx_path = f"{report_base}.docx"
        xlsx_path = f"{report_base}.xlsx"
        reporter.export_individual_report(docx_path)
        reporter.export_summary_data(xlsx_path, format="excel")
        return {"docx": docx_path, "xlsx": xlsx_path}

    def _probe_video_dimensions(self, video_file: str) -> tuple[int, int]:
        """Probe video width and height."""
        cap = cv2.VideoCapture(video_file)
        if not cap.isOpened():
            return (0, 0)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        return w, h

    def _compute_local_space_geometry(
        self, polygon: list, fb_w: int, fb_h: int
    ) -> tuple[int, int, int, int]:
        """Compute local space geometry for an aquarium."""
        if not polygon:
            return 0, 0, max(fb_w, 1), max(fb_h, 1)
        xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
        min_x, min_y = int(np.floor(min(xs))), int(np.floor(min(ys)))
        max_x, max_y = int(np.ceil(max(xs))), int(np.ceil(max(ys)))
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
        cap = cv2.VideoCapture(video_file)
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            log.warning("workflow.report.frame_read_failed", video_file=str(video_file))
            return None

        frame_h, frame_w = frame.shape[:2]
        x, y, w, h = map(int, crop_box)

        original_crop = (x, y, w, h)
        x = max(0, min(x, frame_w - 1))
        y = max(0, min(y, frame_h - 1))
        w = min(w, frame_w - x)
        h = min(h, frame_h - y)

        if w <= 0 or h <= 0:
            log.warning(
                "workflow.report.crop_box_invalid",
                original_crop=original_crop,
                frame_size=(frame_w, frame_h),
                reason="crop_box results in empty region after clamping",
            )
            return None

        if (x, y, w, h) != original_crop:
            log.info(
                "workflow.report.crop_box_adjusted",
                original=original_crop,
                adjusted=(x, y, w, h),
                frame_size=(frame_w, frame_h),
            )

        return frame[y : y + h, x : x + w].copy()

    def _prepare_summary_geometry(
        self,
        poly: list,
        r_polys: list,
        r_names: list,
        r_colors: list,
        calib: dict,
    ) -> tuple:
        """Common geometry preparation for summary generation."""
        w_cm = calib.get("aquarium_width_cm", 0)
        h_cm = calib.get("aquarium_height_cm", 0)
        cal = Calibration(np.array(poly), w_cm, h_cm)
        _, video_h = cal.target_dims_px
        px_x, px_y = cal.pixel_per_cm_ratio
        poly_warped = cal.transform_points(poly)

        rois: list[ROI] = []
        for i, r_poly in enumerate(r_polys):
            wp = cal.transform_points(r_poly)
            name = r_names[i] if i < len(r_names) else f"ROI {i + 1}"
            rois.append(
                ROI(
                    name=name,
                    geometry=Polygon([(float(x), float(y)) for x, y in wp]),
                    coordinate_space="px",
                )
            )

        colors = {
            (r_names[i] if i < len(r_names) else f"ROI {i + 1}"): r_colors[i]
            for i in range(len(r_colors))
        }
        return px_x, px_y, poly_warped, video_h, rois, colors, cal
