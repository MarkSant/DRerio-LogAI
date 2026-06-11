"""Unified report generation mixin for ReportGenerationCoordinator.

Phase 4 size reduction: Extracted from ReportGenerationCoordinator to keep
the main coordinator under 800 lines.

This mixin provides:
- Unified report generation (multi-video aggregation)
- Schema alignment and DataFrame concatenation
- Report cleanup and export (Parquet, Excel, Word)
- Run manifest persistence
"""

from __future__ import annotations

import json
import os
import warnings
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import structlog

from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import UIEvents

if TYPE_CHECKING:
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2

log = structlog.get_logger()


class UnifiedReportMixin:
    """Mixin providing unified report generation.

    Must be composed with a coordinator that satisfies
    :class:`~zebtrack.coordinators._protocols.UnifiedReportHost`.

    Host-provided attributes (declared for mypy, set by coordinator __init__):
    """

    # Declare host-provided attributes for mypy (set by coordinator __init__)
    project_manager: ProjectManager
    settings: Settings
    event_bus: EventBusV2 | None

    # Host-provided methods (declared for mypy, implemented by coordinator)
    _publish_event: Any  # (event: Any, data: Any) -> None
    _is_batch_processing: Any  # () -> bool
    _enrich_unified_report_metadata: Any  # (df, meta, entry) -> pd.DataFrame

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
        self._publish_event(
            UIEvents.UI_SET_STATUS,
            payloads.StatusPayload(message="Gerando relatório unificado..."),
        )

        project_path = self.project_manager.project_path
        if not project_path:
            return

        # Cada escopo grava em sua própria subpasta para não colidir: gerar o
        # relatório total não apaga mais os parciais (selecionados) e vice-versa.
        scope_dir = "selecionados" if scope == "selected" else "total"
        unified_dir = Path(project_path) / "unified_reports" / scope_dir
        unified_dir.mkdir(parents=True, exist_ok=True)

        if replace_existing:
            self._cleanup_unified_reports(unified_dir)

        # Garante um sumário resolvível em disco para cada vídeo selecionado,
        # regenerando a partir da trajetória quando necessário. Corrige o erro de
        # "sumário não encontrado" quando o caminho salvo está defasado (projeto
        # sincronizado via OneDrive entre máquinas) ou os sumários nunca foram
        # exportados, mas a trajetória 3_CoordMovimento existe em disco.
        missing_ids = self._ensure_unified_summaries(video_paths)

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
                    "workflow.unified_report.color_collection_failed",
                    path=path,
                    error=str(e),
                )

            # Handle multi-aquarium entries
            multi_outputs = entry.get("multi_aquarium_outputs")
            entries_to_process: list[dict[str, Any]] = []

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
                                "subject": out_info.get("subject_id") or fresh_meta.get("subject"),
                                "day": out_info.get("day") or fresh_meta.get("day"),
                                "experiment_id": (
                                    f"{os.path.splitext(os.path.basename(path))[0]}"
                                    f"_aq{int(aq_id) + 1}"
                                ),
                                "aquarium_id": int(aq_id) + 1,
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
                    except (OSError, ValueError) as e:
                        log.warning(
                            "workflow.unified_report.read_failed",
                            file=summary_path,
                            error=str(e),
                        )

        if not dfs:
            if missing_ids:
                detail = ", ".join(missing_ids[:10])
                extra = "" if len(missing_ids) <= 10 else f" (+{len(missing_ids) - 10})"
                message = (
                    f"Sem sumário/trajetória para: {detail}{extra}.\n\n"
                    "Gere as trajetórias desses vídeos antes de criar o relatório."
                )
            else:
                message = "Não foi possível encontrar sumários para os vídeos selecionados."
            self._publish_event(
                UIEvents.UI_SHOW_WARNING,
                payloads.MessagePayload(title="Dados insuficientes", message=message),
            )
            return

        if missing_ids:
            log.warning(
                "workflow.unified_report.partial_missing",
                missing=missing_ids,
                included=len(dfs),
            )

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
        # except Exception justified: DataFrame alignment + multi-format export
        except Exception as e:
            log.error("workflow.unified_report.failed", error=str(e), exc_info=True)
            self._publish_event(
                UIEvents.UI_SHOW_ERROR,
                payloads.MessagePayload(title="Erro no Relatório", message=f"{e}"),
            )
        finally:
            self._publish_event(UIEvents.UI_SET_STATUS, payloads.StatusPayload(message="Pronto."))
            self._publish_event(
                UIEvents.UI_REFRESH_PROJECT_VIEWS,
                payloads.ProjectViewsRefreshRequestedPayload(),
            )

    # ------------------------------------------------------------------
    # Summary resolution / regeneration
    # ------------------------------------------------------------------

    # Host-provided method (implemented by ReportGenerationCoordinator)
    generate_parquet_summaries: Any  # (entries: list[dict], settings) -> None

    def _ensure_unified_summaries(self, video_paths: list[str]) -> list[str]:
        """Garante sumários resolvíveis em disco para os vídeos do relatório.

        Para cada vídeo: usa o caminho salvo se existir; senão procura o
        ``{exp_id}_summary.parquet`` na pasta de resultados (reparando caminhos
        absolutos defasados); se ainda faltar mas houver trajetória, regenera o
        sumário via ``generate_parquet_summaries`` — a mesma infra do relatório
        por-vídeo, que já tem fallback em disco para a trajetória.

        Returns:
            Lista de ``experiment_id`` que permanecem sem dados (sem sumário e
            sem trajetória) após a tentativa de regeneração.
        """
        to_regen: list[dict] = []
        regen_paths: list[str] = []
        for path in video_paths:
            entry = self.project_manager.find_video_entry(path=path)
            if not entry:
                continue
            if self._entry_summary_resolved(entry, path):
                continue
            to_regen.append(entry)
            regen_paths.append(path)

        if to_regen:
            log.info("workflow.unified_report.summary_regenerating", count=len(to_regen))
            self.generate_parquet_summaries(to_regen, self.settings)

        missing: list[str] = []
        for path, entry in zip(regen_paths, to_regen, strict=True):
            if not self._entry_summary_resolved(entry, path):
                missing.append(
                    entry.get("experiment_id") or os.path.splitext(os.path.basename(path))[0]
                )
        return missing

    def _entry_summary_resolved(self, entry: dict, video_path: Path | str) -> bool:
        """Verifica/repara o caminho do sumário de um entry (standard ou multi).

        Registra em ``parquet_files['summary']`` qualquer ``_summary.parquet``
        encontrado em disco e retorna ``True`` se houver ao menos um.
        """
        exp_id = entry.get("experiment_id") or os.path.splitext(os.path.basename(video_path))[0]

        multi_outputs = entry.get("multi_aquarium_outputs")
        if multi_outputs:
            resolved_any = False
            for aq_id_str, out_info in multi_outputs.items():
                if not isinstance(out_info, dict):
                    continue
                pf = out_info.setdefault("parquet_files", {})
                summary_path = pf.get("summary")
                if summary_path and os.path.exists(summary_path):
                    resolved_any = True
                    continue
                aq_dir = out_info.get("results_dir")
                try:
                    aq_id = int(aq_id_str)
                except (TypeError, ValueError):
                    continue
                if aq_dir:
                    candidate = os.path.join(str(aq_dir), f"{exp_id}_aq{aq_id + 1}_summary.parquet")
                    if os.path.exists(candidate):
                        pf["summary"] = candidate
                        resolved_any = True
            return resolved_any

        pf = entry.get("parquet_files", {})
        summary_path = pf.get("summary")
        if summary_path and os.path.exists(summary_path):
            return True

        disk_candidate = self._summary_candidate_on_disk(exp_id, video_path)
        if disk_candidate:
            entry.setdefault("parquet_files", {})["summary"] = disk_candidate
            log.info(
                "workflow.unified_report.summary_resolved",
                experiment_id=exp_id,
                path=disk_candidate,
            )
            return True
        return False

    def _summary_candidate_on_disk(self, exp_id: str, video_path: Path | str) -> str | None:
        """Procura ``{exp_id}_summary.parquet`` na pasta de resultados ou ao lado do vídeo."""
        try:
            res_path = self.project_manager.resolve_results_directory(
                exp_id, video_path=str(video_path)
            )
        # except Exception justified: resolução de pasta tolerante a falhas de I/O
        except Exception:
            log.debug("workflow.unified_report.resolve_results_failed", exc_info=True)
            return None

        candidates = [
            os.path.join(str(res_path), f"{exp_id}_summary.parquet"),
            os.path.join(os.path.dirname(str(video_path)), f"{exp_id}_summary.parquet"),
        ]
        return next((c for c in candidates if os.path.exists(c)), None)

    # ------------------------------------------------------------------
    # DataFrame alignment
    # ------------------------------------------------------------------

    def _align_and_concatenate_unified_dfs(self, dfs: list) -> tuple:
        """Align and concatenate summary DataFrames with different schemas."""
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
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    category=FutureWarning,
                    message=".*concatenation with empty or all-NA entries.*",
                )
                final_df = pd.concat(non_empty_dfs, ignore_index=True)

            # Row-level deduplication: remove exact duplicate rows that arise when
            # multi-aquarium entries cause the same summary to be loaded twice.
            before_count = len(final_df)
            final_df = final_df.drop_duplicates(keep="last")
            final_df = final_df.reset_index(drop=True)
            after_count = len(final_df)
            if before_count != after_count:
                log.info(
                    "workflow.unified_report.duplicates_removed",
                    before=before_count,
                    after=after_count,
                )

        return final_df, schema_mismatch, all_columns

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _cleanup_unified_reports(self, unified_dir: Path) -> None:
        """Remove previous unified report artifacts before a fresh export."""
        patterns = [
            "*.docx",
            "*.xlsx",
            "*.csv",
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

    @staticmethod
    def _close_excel_writer_safely(writer: Any) -> None:
        """Close Excel writer and low-level handles, even after close failures.

        In failure paths (for example, ``to_excel`` raising before workbook setup
        is complete), ``writer.close()`` may raise and leave file handles open.
        This helper guarantees handles are closed to avoid ResourceWarning.
        """
        try:
            writer.close()
        except Exception:
            log.debug("workflow.unified_report.excel_writer_close_failed", exc_info=True)

        handles = getattr(writer, "_handles", None)
        if handles is not None:
            try:
                handles.close()
            except Exception:
                log.debug(
                    "workflow.unified_report.excel_writer_handles_close_failed",
                    exc_info=True,
                )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

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
        from zebtrack.analysis.reporters import export_project_report

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        scope_prefix = "unified_partial" if report_scope == "selected" else "unified"

        exported_artifacts: list[str] = []
        export_failures: list[str] = []
        exported_paths: dict[str, str] = {}
        display_df: pd.DataFrame | None = None
        desc_stats_df: pd.DataFrame | None = None

        # 1. Export Parquet
        parquet_path = unified_dir / f"{scope_prefix}_summary_{run_id}.parquet"
        try:
            final_df.to_parquet(parquet_path, index=False)
            exported_artifacts.append(parquet_path.name)
            exported_paths["parquet"] = str(parquet_path)
            log.info(
                "workflow.unified_report.parquet_exported",
                path=str(parquet_path),
            )
        except (OSError, ValueError) as e:
            export_failures.append(f"Parquet: {e}")
            log.error(
                "workflow.unified_report.parquet_failed",
                error=str(e),
                exc_info=True,
            )

        # 2. Export Excel (with descriptive statistics sheet)
        excel_path = unified_dir / f"{scope_prefix}_summary_{run_id}.xlsx"
        writer = None
        try:
            from zebtrack.analysis.data_transformer import DataTransformer

            display_df = DataTransformer().prepare_for_display(final_df)

            desc_stats_df = self._generate_descriptive_stats(final_df)

            writer = pd.ExcelWriter(excel_path, engine="openpyxl")
            display_df.to_excel(writer, sheet_name="Data", index=False)
            if desc_stats_df is not None and not desc_stats_df.empty:
                desc_stats_df.to_excel(writer, sheet_name="Descriptive Stats")

            exported_artifacts.append(excel_path.name)
            exported_paths["excel"] = str(excel_path)
            log.info("workflow.unified_report.excel_exported", path=str(excel_path))
        except (OSError, ImportError, ValueError) as e:
            export_failures.append(f"Excel: {e}")
            log.error(
                "workflow.unified_report.excel_failed",
                error=str(e),
                exc_info=True,
            )
        finally:
            if writer is not None:
                self._close_excel_writer_safely(writer)

        # 2b. Export CSV (same display-friendly columns as Excel)
        csv_path = unified_dir / f"{scope_prefix}_summary_{run_id}.csv"
        try:
            csv_display_df = display_df if display_df is not None else final_df
            csv_display_df.to_csv(csv_path, index=False)
            exported_artifacts.append(csv_path.name)
            exported_paths["csv"] = str(csv_path)
            log.info("workflow.unified_report.csv_exported", path=str(csv_path))
        except (OSError, ValueError, NameError) as e:
            export_failures.append(f"CSV: {e}")
            log.error(
                "workflow.unified_report.csv_failed",
                error=str(e),
                exc_info=True,
            )

        # 3. Export Word
        word_path = unified_dir / f"{scope_prefix}_report_{run_id}"
        try:
            word_df = final_df.copy()
            for col in word_df.columns:
                word_df[col] = (
                    word_df[col].where(word_df[col].notna(), float("nan")).infer_objects(copy=False)
                )
            export_project_report(
                aggregated_df=word_df,
                output_path=word_path,
                roi_colors=roi_colors_map if roi_colors_map else None,
                detector_params=None,
                descriptive_stats_df=desc_stats_df if desc_stats_df is not None else None,
            )
            exported_artifacts.append(f"{word_path.name}.docx")
            exported_paths["word"] = f"{word_path}.docx"
            log.info(
                "workflow.unified_report.word_exported",
                path=str(word_path) + ".docx",
            )
        except (OSError, PermissionError, ImportError, ValueError) as e:
            export_failures.append(f"Word: {e}")
            log.error(
                "workflow.unified_report.word_failed",
                error=str(e),
                exc_info=True,
            )

        if not exported_artifacts:
            failure_details = "\n".join(f"• {item}" for item in export_failures[:3])
            raise RuntimeError(
                "Não foi possível gerar nenhum arquivo do relatório unificado."
                + (f"\n\nDetalhes:\n{failure_details}" if failure_details else "")
            )

        if export_failures:
            self._publish_event(
                UIEvents.UI_SHOW_WARNING,
                payloads.MessagePayload(
                    title="Relatório Unificado Parcial",
                    message=(
                        "Alguns arquivos não puderam ser gerados.\n"
                        "Gerados: "
                        + ", ".join(exported_artifacts)
                        + "\n\nFalhas:\n"
                        + "\n".join(f"• {item}" for item in export_failures[:3])
                    ),
                ),
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
                message=("DataFrames had different column sets; missing values filled with NA"),
                columns=all_columns,
            )
            if not self.settings.ui_features.suppress_roi_mismatch_warning:
                self._publish_event(
                    UIEvents.UI_SHOW_WARNING,
                    payloads.MessagePayload(
                        title="ROIs Diferentes",
                        message=(
                            "Os vídeos selecionados possuem ROIs diferentes.\n"
                            "Colunas ausentes foram preenchidas com valores vazios (NA)."
                        ),
                    ),
                )

        if not self._is_batch_processing():
            self._publish_event(
                UIEvents.UI_SHOW_INFO,
                payloads.MessagePayload(
                    title=(
                        "Relatório Unificado Parcial"
                        if report_scope == "selected"
                        else "Relatório Unificado"
                    ),
                    message=(
                        f"Relatório unificado gerado com sucesso em:\n"
                        f"{unified_dir}\n\n"
                        f"Arquivos: {', '.join(exported_artifacts)}"
                    ),
                ),
            )

    # ------------------------------------------------------------------
    # Descriptive Statistics
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_descriptive_stats(final_df: pd.DataFrame) -> pd.DataFrame | None:
        """Generate descriptive statistics grouped by group_id and day.

        Returns a pivot table with mean, std, count, min, max for numeric columns.
        Returns None if the DataFrame lacks the required grouping columns.
        """
        group_cols = [c for c in ("group_id", "day") if c in final_df.columns]
        if not group_cols:
            return None

        numeric_cols = final_df.select_dtypes(include="number").columns.tolist()
        # Exclude internal/validation columns from summary
        exclude_prefixes = ("validation_", "roi_color_")
        numeric_cols = [
            c for c in numeric_cols if not any(c.startswith(p) for p in exclude_prefixes)
        ]
        if not numeric_cols:
            return None

        try:
            stats_df = final_df.groupby(group_cols, dropna=False)[numeric_cols].agg(
                ["mean", "std", "count", "min", "max"]
            )
            # Flatten MultiIndex columns: ("total_distance_cm", "mean") -> "total_distance_cm_mean"
            stats_df.columns = [f"{col}_{stat}" for col, stat in stats_df.columns]
            return stats_df
        except Exception:
            log.warning("workflow.unified_report.descriptive_stats_failed", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Manifest
    # ------------------------------------------------------------------

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
