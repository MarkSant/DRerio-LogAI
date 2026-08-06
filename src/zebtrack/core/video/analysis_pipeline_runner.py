"""Analysis pipeline runner mixin — report generation, calibration, and social analysis.

Extracted from VideoProcessingService (Phase 2.3 decomposition).
Methods:
    _collect_params_from_single_video, _collect_params_from_project,
    _collect_analysis_parameters, _prepare_analysis_calibration_context,
    _generate_reports_for_video, _filter_trajectory_by_tracks,
    _enrich_metadata_with_profile, _create_reporter_instance,
    _analyze_social_proximity, _compute_social_outcome, _resolve_social_config,
    _resolve_social_radius_cm, _record_social_outcome_warning,
    _register_project_outputs, _run_analysis_pipeline
"""

from __future__ import annotations

import os
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import structlog
from shapely.geometry import Polygon

if TYPE_CHECKING:
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.ui_scheduler import UIScheduler
    from zebtrack.io.recorder import Recorder
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2

from zebtrack.analysis.reporters import (
    ExcelReporter,
    ParquetSummaryReporter,
    ReporterContext,
    WordReporter,
)
from zebtrack.analysis.roi import ROI, ROIAnalyzer
from zebtrack.core.detection import ZoneData
from zebtrack.core.detection.calibration import Calibration
from zebtrack.core.video.social_analysis_outcome import (
    DEFAULT_SOCIAL_RADIUS_CM,
    SocialAnalysisOutcome,
)
from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import Event, UIEvents

log = structlog.get_logger()


class AnalysisPipelineRunnerMixin:
    """Mixin providing analysis pipeline, report generation, and social analysis."""

    # ── Attribute stubs (provided by the facade __init__) ──
    project_manager: ProjectManager
    state_manager: StateManager
    ui_coordinator: UIScheduler
    ui_event_bus: EventBusV2
    cancel_event: threading.Event
    settings: Settings
    detector: Any
    recorder: Recorder | None

    # ── Cross-mixin method stubs ──
    def ensure_arena_polygon(
        self,
        arena_polygon_px: list | None,
        video_path: Path | str | None = None,
        video_context: Any | None = None,
    ) -> list[list[int]] | list | None: ...

    def load_trajectory_dataframe(
        self, trajectory_path: Path | str, experiment_id: str
    ) -> pd.DataFrame | None: ...

    def _collect_params_from_single_video(
        self, config: dict, experiment_id: str
    ) -> tuple[dict, Any, Any, Any, Any, Any, Any, Any]:
        """Extract parameters from single video config."""
        metadata = dict(config)
        metadata.setdefault("experiment_id", experiment_id)
        metadata.setdefault("video_name", experiment_id)
        if not metadata.get("group_id"):
            metadata["group_id"] = "single_video"

        return (
            metadata,
            config.get("aquarium_width_cm"),
            config.get("aquarium_height_cm"),
            config.get(
                "sharp_turn_threshold_deg_s",
                self.settings.video_processing.sharp_turn_threshold_deg_s,
            ),
            config.get(
                "freezing_velocity_threshold",
                self.settings.video_processing.freezing_velocity_threshold,
            ),
            config.get(
                "freezing_min_duration_s", self.settings.video_processing.freezing_min_duration_s
            ),
            config.get("smoothing_window_length", self.settings.trajectory_smoothing.window_length),
            config.get("smoothing_polyorder", self.settings.trajectory_smoothing.polyorder),
        )

    def _collect_params_from_project(
        self, metadata_context: dict | None, experiment_id: str, video_path: Path | str
    ) -> tuple[dict, Any, Any, Any, Any, Any, Any, Any]:
        """Extract parameters from project data."""
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        project_data = getattr(self.project_manager, "project_data", {}) or {}
        calibration = project_data.get("calibration", {})

        metadata = dict(metadata_context or {})
        csv_metadata = self.project_manager.get_metadata_for_experiment(experiment_id)
        if csv_metadata:
            metadata.update(csv_metadata)
        if not metadata:
            metadata = self.project_manager.derive_processing_metadata(experiment_id, video_path)
            log.info(
                "controller.processing.metadata_fallback",
                experiment_id=experiment_id,
                fields=list(metadata.keys()),
            )

        return (
            metadata,
            calibration.get("aquarium_width_cm"),
            calibration.get("aquarium_height_cm"),
            self.settings.video_processing.sharp_turn_threshold_deg_s,
            self.settings.video_processing.freezing_velocity_threshold,
            self.settings.video_processing.freezing_min_duration_s,
            self.settings.trajectory_smoothing.window_length,
            self.settings.trajectory_smoothing.polyorder,
        )

    def _collect_analysis_parameters(
        self,
        *,
        single_video_config: dict | None,
        metadata_context: dict | None,
        experiment_id: str,
        video_path: str,
    ) -> tuple[dict, float | None, float | None, float, float, float, int, int]:
        """Collect analysis parameters from config or project."""
        if single_video_config:
            return self._collect_params_from_single_video(single_video_config, experiment_id)
        else:
            return self._collect_params_from_project(metadata_context, experiment_id, video_path)

    def _prepare_analysis_calibration_context(
        self,
        *,
        arena_polygon_px: Sequence[Sequence[float]],
        width_cm: float | None,
        height_cm: float | None,
        zone_data: ZoneData,
    ) -> tuple[
        Calibration | None,
        Sequence[tuple[float, float]] | None,
        list[ROI],
        dict[str, tuple[int, int, int]],
        float | None,
        float | None,
    ]:
        """Prepare calibration context for analysis."""
        if not all([width_cm, height_cm, arena_polygon_px]):
            return None, None, [], {}, None, None

        assert width_cm is not None
        assert height_cm is not None

        cal = Calibration(np.array(arena_polygon_px), width_cm, height_cm)
        _video_width_px, _video_height_px = cal.target_dims_px
        pixelcm_x, pixelcm_y = cal.pixel_per_cm_ratio

        warped_points = cal.transform_points(list(arena_polygon_px))
        arena_polygon_warped = [(float(point[0]), float(point[1])) for point in warped_points]
        rois: list[ROI] = []
        for i, polygon in enumerate(zone_data.roi_polygons):
            warped_points = cal.transform_points(list(polygon))
            roi_points_px = [(float(x), float(y)) for x, y in warped_points]
            roi_name = zone_data.roi_names[i] if i < len(zone_data.roi_names) else f"ROI {i + 1}"
            rois.append(
                ROI(
                    name=roi_name,
                    geometry=Polygon(roi_points_px),
                    coordinate_space="px",
                )
            )

        roi_colors = {
            (zone_data.roi_names[i] if i < len(zone_data.roi_names) else f"ROI {i + 1}"): color
            for i, color in enumerate(zone_data.roi_colors)
        }

        return cal, arena_polygon_warped, rois, roi_colors, pixelcm_x, pixelcm_y

    def _generate_reports_for_video(
        self,
        *,
        ctx: ReporterContext,
        experiment_id: str,
        results_dir: str,
        progress_callback,
        cancel_event: threading.Event | None = None,
    ) -> tuple[str, str, str] | None:
        """Generate analysis reports for video."""
        if cancel_event and cancel_event.is_set():
            log.info(
                "controller.analysis.reports.skipped",
                video=experiment_id,
                reason="cancelled",
            )
            return None

        summary_parquet_path = os.path.join(results_dir, f"{experiment_id}_summary.parquet")
        summary_excel_path = os.path.join(results_dir, f"{experiment_id}_summary.xlsx")
        report_docx_path = os.path.join(results_dir, f"{experiment_id}_report.docx")

        if cancel_event and cancel_event.is_set():
            log.info(
                "controller.analysis.reports.skipped",
                video=experiment_id,
                reason="cancelled_before_write",
            )
            return None

        ParquetSummaryReporter(ctx).export_summary(summary_parquet_path)
        if cancel_event and cancel_event.is_set():
            log.info(
                "controller.analysis.reports.partial_skip",
                video=experiment_id,
                reason="cancelled_after_parquet",
            )
            return None
        ExcelReporter(ctx).export_summary(summary_excel_path)
        if cancel_event and cancel_event.is_set():
            log.info(
                "controller.analysis.reports.partial_skip",
                video=experiment_id,
                reason="cancelled_after_excel",
            )
            return None
        WordReporter(ctx).export_individual_report_step_by_step(report_docx_path, progress_callback)

        return summary_parquet_path, summary_excel_path, report_docx_path

    def _filter_trajectory_by_tracks(
        self,
        *,
        trajectory_df: pd.DataFrame,
        analysis_profile: dict | None,
        experiment_id: str,
    ) -> tuple[pd.DataFrame, list[str]]:
        """Filter trajectory dataframe by requested track IDs from analysis profile.

        Returns:
            Tuple of (filtered_df, resolved_track_ids)
        """
        profile_dict = analysis_profile if isinstance(analysis_profile, dict) else {}
        requested_track_ids_raw = profile_dict.get("track_ids", [])

        if isinstance(requested_track_ids_raw, list | tuple | set):
            requested_track_ids = list(requested_track_ids_raw)
        elif requested_track_ids_raw in (None, ""):
            requested_track_ids = []
        else:
            requested_track_ids = [requested_track_ids_raw]

        filtered_df = trajectory_df
        resolved_track_ids: list[str] = []

        if "track_id" in trajectory_df.columns:
            resolved_track_ids = sorted(
                {str(track) for track in trajectory_df["track_id"].dropna().unique().tolist()}
            )

            if requested_track_ids:
                requested_str = {
                    str(track).strip() for track in requested_track_ids if track not in (None, "")
                }

                mask = trajectory_df["track_id"].astype(str).isin(requested_str)
                narrowed = trajectory_df[mask]
                if narrowed.empty:
                    log.warning(
                        "controller.analysis.profile_track_miss",
                        video=experiment_id,
                        requested=list(requested_str),
                    )
                else:
                    filtered_df = narrowed
                    resolved_track_ids = sorted(requested_str)
        elif requested_track_ids:
            log.warning(
                "controller.analysis.profile_track_column_missing",
                video=experiment_id,
            )

        return filtered_df, resolved_track_ids

    def _enrich_metadata_with_profile(
        self,
        *,
        metadata: dict,
        analysis_profile: dict | None,
    ) -> dict:
        """Enrich metadata with analysis profile information.

        Returns:
            Enriched metadata dictionary
        """
        profile_dict = analysis_profile if isinstance(analysis_profile, dict) else {}

        if isinstance(profile_dict, dict):
            profile_name = profile_dict.get("name")
            if profile_name and isinstance(metadata, dict):
                metadata.setdefault("analysis_profile", profile_name)
            track_list = profile_dict.get("track_ids")
            if track_list and isinstance(metadata, dict):
                metadata.setdefault("analysis_profile_tracks", list(track_list))

        return metadata

    def _create_reporter_instance(
        self,
        *,
        filtered_df: pd.DataFrame,
        metadata: dict,
        calibration: Calibration,
        arena_polygon_warped: list,
        rois: list,
        roi_colors: dict,
        video_path: str,
        pixelcm_x: float,
        pixelcm_y: float,
        sharp_turn_threshold: float,
        freezing_threshold: float,
        freezing_duration: float,
        smoothing_window: int,
        smoothing_polyorder: int,
    ) -> ReporterContext:
        """Create ReporterContext instance with all required parameters."""
        return ReporterContext(
            trajectory_df=filtered_df,
            metadata=metadata,
            pixelcm_x=pixelcm_x,
            pixelcm_y=pixelcm_y,
            video_height_px=calibration.target_dims_px[1],
            arena_polygon_px=arena_polygon_warped,
            rois=rois,
            fps=self.settings.video_processing.fps,
            roi_colors=roi_colors,
            video_path=video_path,
            calibration=calibration,
            sharp_turn_threshold=sharp_turn_threshold,
            freezing_threshold=freezing_threshold,
            freezing_duration=freezing_duration,
            smoothing_window_length=smoothing_window,
            smoothing_polyorder=smoothing_polyorder,
        )

    def _analyze_social_proximity(
        self,
        *,
        filtered_df: pd.DataFrame,
        analysis_profile: dict | None,
        pixelcm_x: float | None,
        pixelcm_y: float | None,
        experiment_id: str,
    ) -> SocialAnalysisOutcome:
        """Analyze social proximity if enabled in analysis profile.

        Nunca devolve ``None`` mudo nem levanta: quando a análise não roda, o
        motivo vem explícito em ``SocialAnalysisOutcome.skipped_reason`` e —
        exceto para ``disabled`` — vira aviso no relatório. A proximidade social
        é opcional; nenhuma falha aqui pode derrubar a geração dos relatórios.

        Returns:
            Outcome with the social metrics or an explicit skip reason.
        """
        try:
            return self._compute_social_outcome(
                filtered_df=filtered_df,
                analysis_profile=analysis_profile,
                pixelcm_x=pixelcm_x,
                pixelcm_y=pixelcm_y,
                experiment_id=experiment_id,
            )
        except Exception as exc:
            # except Exception justified: fronteira da análise social opcional.
            # Nada aqui (schema inesperado da trajetória, shapely/networkx) pode
            # abortar o pipeline que já produziu trajetória e relatórios; o motivo
            # `failed` chega ao relatório com a mensagem, então nada fica mudo.
            log.warning(
                "controller.analysis.social_failed_unexpected",
                video=experiment_id,
                error=str(exc),
                exc_info=True,
            )
            return SocialAnalysisOutcome.skipped("failed", detail=f"technical detail: {exc}")

    def _compute_social_outcome(
        self,
        *,
        filtered_df: pd.DataFrame,
        analysis_profile: dict | None,
        pixelcm_x: float | None,
        pixelcm_y: float | None,
        experiment_id: str,
    ) -> SocialAnalysisOutcome:
        """Corpo da análise social — um motivo explícito por saída antecipada."""
        social_config = self._resolve_social_config(
            analysis_profile=analysis_profile,
            experiment_id=experiment_id,
        )
        if social_config is None:
            return SocialAnalysisOutcome.skipped("malformed_config")

        if not bool(social_config.get("enabled")):
            # Escolha deliberada do usuário: log informativo, sem aviso no relatório.
            log.info("controller.analysis.social_disabled", video=experiment_id)
            return SocialAnalysisOutcome.skipped("disabled")

        if pixelcm_x is None or pixelcm_y is None:
            log.warning("controller.analysis.social_no_calibration", video=experiment_id)
            return SocialAnalysisOutcome.skipped("no_calibration")

        if "track_id" not in filtered_df.columns:
            log.warning("controller.analysis.social_no_track_id_column", video=experiment_id)
            return SocialAnalysisOutcome.skipped("no_track_id_column")

        active_tracks = filtered_df["track_id"].dropna().unique().tolist()
        if len(active_tracks) <= 1:
            log.warning(
                "controller.analysis.social_single_track",
                video=experiment_id,
                track_count=len(active_tracks),
            )
            return SocialAnalysisOutcome.skipped(
                "single_track",
                detail=f"{len(active_tracks)} track(s) available",
            )

        radius_cm, radius_notes = self._resolve_social_radius_cm(
            social_config=social_config,
            experiment_id=experiment_id,
        )

        try:
            summary = ROIAnalyzer.analyze_social_proximity(
                filtered_df,
                radius_cm,
                pixelcm_x,
                pixelcm_y,
            )
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            # Falhas esperadas de dados: coluna ausente, tipo inválido, geometria
            # degenerada. O relatório segue sendo gerado, mas diz por que a seção
            # social sumiu.
            log.warning(
                "controller.analysis.social_failed",
                video=experiment_id,
                error=str(exc),
                exc_info=True,
            )
            return SocialAnalysisOutcome.skipped("failed", detail=f"technical detail: {exc}")

        return SocialAnalysisOutcome.success(summary, notes=radius_notes)

    def _resolve_social_config(
        self,
        *,
        analysis_profile: dict | None,
        experiment_id: str,
    ) -> dict | None:
        """Extrai a seção ``social`` do perfil.

        Returns:
            O dicionário de configuração social (vazio quando ausente), ou
            ``None`` quando o perfil está malformado — malformação NÃO pode ser
            confundida com ``disabled``, que é escolha deliberada do usuário.
        """
        if analysis_profile is None:
            return {}

        if not isinstance(analysis_profile, dict):
            log.warning(
                "controller.analysis.social_malformed_profile",
                video=experiment_id,
                profile_type=type(analysis_profile).__name__,
            )
            return None

        raw_social_config = analysis_profile.get("social")
        if raw_social_config is None:
            return {}

        if not isinstance(raw_social_config, dict):
            log.warning(
                "controller.analysis.social_malformed_config",
                video=experiment_id,
                social_type=type(raw_social_config).__name__,
            )
            return None

        return raw_social_config

    def _resolve_social_radius_cm(
        self,
        *,
        social_config: dict,
        experiment_id: str,
    ) -> tuple[float, tuple[str, ...]]:
        """Resolve o raio de proximidade, avisando quando cai no default.

        O raio é a definição operacional de "contato social": um valor
        inconversível não pode virar 5.0 cm em silêncio, senão o relatório fica
        cientificamente errado e com cara de certo.

        Returns:
            O raio em cm e as notas de degradação para o relatório.
        """
        raw_radius = social_config.get("radius_cm", DEFAULT_SOCIAL_RADIUS_CM)
        try:
            return float(raw_radius), ()
        except (TypeError, ValueError):
            log.warning(
                "controller.analysis.social_radius_invalid",
                video=experiment_id,
                raw_radius=repr(raw_radius),
            )
            note = (
                f"Social proximity used the default {DEFAULT_SOCIAL_RADIUS_CM} cm radius "
                f"because the configured value ({raw_radius!r}) could not be read as a number."
            )
            return DEFAULT_SOCIAL_RADIUS_CM, (note,)

    def _record_social_outcome_warning(
        self,
        *,
        ctx: ReporterContext,
        outcome: SocialAnalysisOutcome,
    ) -> None:
        """Propaga o motivo do skip social para os avisos do relatório.

        ``disabled`` é escolha deliberada do usuário e não gera aviso; os demais
        motivos (mais as notas de degradação) entram em
        ``ctx.validation_warnings``, que o ``WordReporter`` imprime no apêndice
        de validação e que também alimenta ``report["validacao"]["avisos"]``.

        Nota: hoje apenas o relatório Word imprime esses avisos; o resumo Excel
        não lê ``validation_warnings``.
        """
        messages = outcome.warning_messages
        if not messages:
            return

        warnings_list = getattr(ctx, "validation_warnings", None)
        if not isinstance(warnings_list, list):
            # Contexto malformado é bug de construção do ReporterContext: reparar
            # em silêncio esconderia o bug, então registra antes de seguir.
            log.warning(
                "controller.analysis.social_warning_list_missing",
                warnings_type=type(warnings_list).__name__,
            )
            warnings_list = []
            ctx.validation_warnings = warnings_list
        warnings_list.extend(messages)

        # Mantém report["validacao"]["avisos"] em sincronia com o contexto para
        # consumidores que leem o dicionário do relatório em vez do ctx. Na
        # construção real as duas listas são o MESMO objeto (reporter_context.py),
        # daí o guard de duplicata.
        report = getattr(ctx, "report", None)
        if not isinstance(report, dict):
            return

        validation_section = report.setdefault("validacao", {})
        if not isinstance(validation_section, dict):
            log.warning(
                "controller.analysis.social_report_validation_malformed",
                section_type=type(validation_section).__name__,
            )
            return

        report_warnings = validation_section.setdefault("avisos", [])
        if not isinstance(report_warnings, list):
            log.warning(
                "controller.analysis.social_report_warnings_malformed",
                warnings_type=type(report_warnings).__name__,
            )
            return

        for message in messages:
            if message not in report_warnings:
                report_warnings.append(message)

    def _register_project_outputs(
        self,
        *,
        video_path: str,
        results_dir: str,
        trajectory_path: str,
        summary_parquet: str,
        summary_excel: str,
        report_path: str,
    ) -> None:
        """Register processing outputs with project manager."""
        self.project_manager.register_processing_outputs(
            video_path,
            results_dir=results_dir,
            trajectory_path=trajectory_path,
            summary_parquet=summary_parquet,
            summary_excel=summary_excel,
            report_path=report_path,
        )
        if self.ui_event_bus:
            self.ui_event_bus.publish(
                Event(
                    type=UIEvents.UI_REFRESH_PROJECT_VIEWS,
                    data=payloads.ProjectViewsRefreshRequestedPayload(reason="processing_complete"),
                )
            )

    def _run_analysis_pipeline(
        self,
        *,
        experiment_id: str,
        video_path: str,
        results_dir: str,
        arena_polygon_px: list | None,
        metadata_context: dict | None,
        single_video_config: dict | None,
        progress_callback,
        analysis_profile: dict | None,
        video_context: Any | None = None,
    ) -> bool:
        """Run complete analysis pipeline for a tracked video."""
        # Load trajectory data
        trajectory_path = os.path.join(results_dir, f"3_CoordMovimento_{experiment_id}.parquet")
        trajectory_df = self.load_trajectory_dataframe(trajectory_path, experiment_id)
        if trajectory_df is None:
            return False

        if self.cancel_event.is_set():
            log.info("controller.analysis.cancelled_before_pipeline", video=experiment_id)
            return False

        # Filter trajectory by requested tracks
        filtered_df, resolved_track_ids = self._filter_trajectory_by_tracks(
            trajectory_df=trajectory_df,
            analysis_profile=analysis_profile,
            experiment_id=experiment_id,
        )

        # Collect analysis parameters
        (
            metadata,
            width_cm,
            height_cm,
            sharp_turn_threshold,
            freezing_threshold,
            freezing_duration,
            smoothing_window,
            smoothing_polyorder,
        ) = self._collect_analysis_parameters(
            single_video_config=single_video_config,
            metadata_context=metadata_context,
            experiment_id=experiment_id,
            video_path=video_path,
        )

        # Enrich metadata with profile information
        metadata = self._enrich_metadata_with_profile(
            metadata=metadata,
            analysis_profile=analysis_profile,
        )

        # Validate calibration data
        zone_data = self.project_manager.get_zone_data()
        arena_polygon_px = self.ensure_arena_polygon(
            arena_polygon_px,
            video_path,
            video_context=video_context,
        )
        if not all([width_cm, height_cm, arena_polygon_px]):
            self.ui_event_bus.publish(
                Event(
                    type=UIEvents.SHOW_ERROR,
                    data=payloads.ErrorOccurredPayload(
                        title="Erro de Processamento",
                        message="Dados de calibração incompletos.",
                    ),
                )
            )
            return False

        assert arena_polygon_px is not None

        # Prepare calibration context
        (
            calibration,
            arena_polygon_warped,
            rois,
            roi_colors,
            pixelcm_x,
            pixelcm_y,
        ) = self._prepare_analysis_calibration_context(
            arena_polygon_px=arena_polygon_px,
            width_cm=width_cm,
            height_cm=height_cm,
            zone_data=zone_data,
        )

        if (
            not calibration
            or arena_polygon_warped is None
            or pixelcm_x is None
            or pixelcm_y is None
        ):
            self.ui_event_bus.publish(
                Event(
                    type=UIEvents.SHOW_ERROR,
                    data=payloads.ErrorOccurredPayload(
                        title="Erro de Processamento",
                        message="Falha ao preparar dados de calibração.",
                    ),
                )
            )
            return False

        arena_polygon_warped_list = list(arena_polygon_warped)

        # Create ReporterContext instance
        ctx = self._create_reporter_instance(
            filtered_df=filtered_df,
            metadata=metadata,
            calibration=calibration,
            arena_polygon_warped=arena_polygon_warped_list,
            rois=rois,
            roi_colors=roi_colors,
            video_path=video_path,
            pixelcm_x=pixelcm_x,
            pixelcm_y=pixelcm_y,
            sharp_turn_threshold=sharp_turn_threshold,
            freezing_threshold=freezing_threshold,
            freezing_duration=freezing_duration,
            smoothing_window=smoothing_window,
            smoothing_polyorder=smoothing_polyorder,
        )

        if self.cancel_event.is_set():
            log.info("controller.analysis.cancelled_before_reports", video=experiment_id)
            return False

        # Analyze social proximity BEFORE generating the reports: quando a análise
        # é pulada, o motivo precisa estar em ctx.validation_warnings a tempo de
        # entrar no apêndice de validação do relatório.
        social_outcome = self._analyze_social_proximity(
            filtered_df=filtered_df,
            analysis_profile=analysis_profile,
            pixelcm_x=pixelcm_x,
            pixelcm_y=pixelcm_y,
            experiment_id=experiment_id,
        )
        self._record_social_outcome_warning(ctx=ctx, outcome=social_outcome)

        # Generate reports
        generated_outputs = self._generate_reports_for_video(
            ctx=ctx,
            experiment_id=experiment_id,
            results_dir=results_dir,
            progress_callback=progress_callback,
            cancel_event=self.cancel_event,
        )

        if generated_outputs is None:
            return False

        summary_parquet_path, summary_excel_path, report_docx_path = generated_outputs

        # Publish social summary
        social_summary = social_outcome.result
        profile_dict = analysis_profile if isinstance(analysis_profile, dict) else {}
        profile_name = profile_dict.get("name", "default")
        self.ui_event_bus.publish(
            Event(
                type=UIEvents.UI_UPDATE_SOCIAL_SUMMARY,
                data=payloads.SocialSummaryPayload(
                    profile=profile_name,
                    stats=social_summary,
                    tracks=resolved_track_ids,
                ),
            )
        )

        # Register outputs
        self._register_project_outputs(
            video_path=video_path,
            results_dir=results_dir,
            trajectory_path=trajectory_path,
            summary_parquet=summary_parquet_path,
            summary_excel=summary_excel_path,
            report_path=report_docx_path,
        )

        return True
