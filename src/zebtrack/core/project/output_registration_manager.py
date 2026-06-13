"""Output registration manager for ZebTrack-AI.

Handles registration of processing outputs, results directory resolution,
multi-aquarium output management, and batch report tracking.

Phase 4.2: Extracted from ProjectManager to reduce god-class complexity.
All methods are stateless — they receive project_data, project_path, and
callbacks as parameters from the ProjectManager facade.
"""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from collections.abc import Callable

log = structlog.get_logger()

# Frame de referência capturado na calibração de câmera ao vivo. As zonas
# desenhadas sobre ele não pertencem a grupo/dia/sujeito algum, então seus
# parquets vão para uma pasta dedicada na raiz do projeto em vez do fallback
# hierárquico "Grupo_Sem_Grupo/Dia_Indefinido/Sujeito_Indefinido".
LIVE_REFERENCE_FRAME_FILENAME = "live_camera_reference_frame.png"
LIVE_REFERENCE_FRAME_STEM = "live_camera_reference_frame"
REFERENCE_ZONES_DIRNAME = "Zonas_Referencia"

# Componentes legados do fallback hierárquico — mantidos para leitura de
# projetos antigos que ainda guardam as zonas de referência nesse caminho.
LEGACY_NO_GROUP_DIRNAME = "Grupo_Sem_Grupo"
LEGACY_NO_DAY_DIRNAME = "Dia_Indefinido"
LEGACY_NO_SUBJECT_DIRNAME = "Sujeito_Indefinido"


class OutputRegistrationManager:
    """Manages processing output registration and results directory resolution.

    Phase 4.2: Extracted from ProjectManager. This class is stateless;
    all project state (project_path, project_data) is passed as parameters.
    """

    def __init__(self) -> None:
        """Initialize OutputRegistrationManager."""

    # ------------------------------------------------------------------
    # Results directory resolution
    # ------------------------------------------------------------------

    def resolve_results_directory(
        self,
        experiment_id: str,
        *,
        project_path: Path | str | None,
        video_path: str | None = None,
        metadata: dict | None = None,
        get_metadata_for_experiment_fn: Callable[..., dict] | None = None,
        derive_processing_metadata_fn: Callable[..., dict] | None = None,
    ) -> Path:
        """Compute the destination directory for analysis artifacts.

        For projects with metadata, returns: project/group/day/subject/
        All files for a given subject are stored together in the subject folder.

        Args:
            experiment_id: Experiment identifier (usually video stem).
            project_path: Path to the project root directory.
            video_path: Optional path to the video file.
            metadata: Optional pre-resolved metadata dict.
            get_metadata_for_experiment_fn: Callback to look up metadata by experiment_id.
            derive_processing_metadata_fn: Callback to derive metadata from video path.

        Returns:
            Path to the resolved results directory.
        """
        experiment_source = experiment_id or (metadata or {}).get("experiment_id")
        experiment_component = self._sanitize_path_component(
            experiment_source,
            fallback="experimento",
        )

        if project_path:
            # Zonas do frame de referência live: pasta dedicada na raiz do
            # projeto (sem hierarquia artificial de grupo/dia/sujeito).
            is_reference_frame = (
                bool(video_path and Path(video_path).name == LIVE_REFERENCE_FRAME_FILENAME)
                or str(experiment_source or "") == LIVE_REFERENCE_FRAME_STEM
            )
            if is_reference_frame:
                return Path(project_path) / REFERENCE_ZONES_DIRNAME

            meta_lookup = metadata or {}

            if not meta_lookup and get_metadata_for_experiment_fn:
                meta_lookup = get_metadata_for_experiment_fn(experiment_id) or {}

            if not meta_lookup and video_path and derive_processing_metadata_fn:
                meta_lookup = derive_processing_metadata_fn(
                    experiment_id,
                    video_path,
                )

            group_component = self._format_group_component(meta_lookup)
            day_component = self._format_day_component(meta_lookup)
            subject_component = self._format_subject_component(meta_lookup)

            # Simplified structure: group/day/subject (no per-video subfolder)
            return Path(project_path) / group_component / day_component / subject_component

        base_dir = Path(video_path).parent if video_path else Path.cwd()

        # Non-project workflows must align exactly with the worker/recorder naming
        # (``<video_stem>_results`` ao lado do vídeo). Exceção: quando um
        # ``experiment_id`` explícito é passado e difere do stem — caso do
        # processamento sequencial multi-aquário, que passa ``<stem>_aqN`` — ele é
        # respeitado para que cada aquário receba sua própria pasta de resultados
        # (senão o 2º aquário sobrescreveria os relatórios do 1º). Mantém-se o raw
        # ``experiment_id`` para casar com o fallback do worker (``f"{experiment_id}_results"``).
        video_stem = Path(video_path).stem if video_path else None
        explicit_id = str(experiment_source) if experiment_source else None

        raw_component: str | None
        if explicit_id and explicit_id != video_stem:
            raw_component = explicit_id
        elif video_stem:
            raw_component = video_stem
        else:
            raw_component = explicit_id

        safe_component = raw_component if raw_component else experiment_component
        return base_dir / f"{safe_component}_results"

    @staticmethod
    def _sanitize_path_component(value: Any, *, fallback: str) -> str:
        """Sanitize a string for safe use as a filesystem path component."""
        candidate = fallback if value is None else str(value).strip()
        if not candidate:
            candidate = fallback

        normalized = unicodedata.normalize("NFKD", candidate)
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))

        sanitized = re.sub(r"[<>:\"/\\|?*]", "_", normalized)
        sanitized = re.sub(r"\s+", "_", sanitized)
        sanitized = re.sub(r"_+", "_", sanitized)
        sanitized = sanitized.strip("._")

        return sanitized or fallback

    def _format_group_component(self, metadata: dict | None) -> str:
        """Format group name for use as a directory path component."""
        if metadata:
            for key in (
                "group_display_name",
                "group_label",
                "group_name",
                "group",
            ):
                value = metadata.get(key)
                if value not in (None, ""):
                    return "Grupo_" + self._sanitize_path_component(value, fallback="Sem_Grupo")

        return "Grupo_" + self._sanitize_path_component(None, fallback="Sem_Grupo")

    def _format_day_component(self, metadata: dict | None) -> str:
        """Format day value for use as a directory path component."""
        candidate = None
        if metadata:
            for key in ("day", "dia", "day_id"):
                value = metadata.get(key)
                if value not in (None, ""):
                    candidate = value
                    break

        if candidate is None:
            suffix = "Indefinido"
        else:
            candidate_str = str(candidate)
            if candidate_str.lower().startswith(("dia", "day")):
                match = re.search(r"\d+", candidate_str)
                if match:
                    try:
                        day_number = int(match.group(0))
                        suffix = f"{day_number:02d}"
                    except (TypeError, ValueError):
                        suffix = self._sanitize_path_component(candidate_str, fallback="Indefinido")
                else:
                    suffix = self._sanitize_path_component(candidate_str, fallback="Indefinido")
            else:
                try:
                    day_float = float(candidate)
                    if day_float.is_integer():
                        suffix = f"{int(day_float):02d}"
                    else:
                        suffix = self._sanitize_path_component(candidate, fallback="Indefinido")
                except (TypeError, ValueError):
                    suffix = self._sanitize_path_component(candidate, fallback="Indefinido")

        return f"Dia_{suffix}"

    def _format_subject_component(self, metadata: dict | None) -> str:
        """Format subject value for use as a directory path component."""
        candidate = None
        if metadata:
            for key in ("subject", "subject_id", "animal", "sujeito"):
                value = metadata.get(key)
                if value not in (None, ""):
                    candidate = value
                    break

        if candidate is None:
            suffix = "Indefinido"
        else:
            try:
                subject_number = float(candidate)
                if subject_number.is_integer():
                    suffix = f"{int(subject_number):02d}"
                else:
                    suffix = self._sanitize_path_component(candidate, fallback="Indefinido")
            except (TypeError, ValueError):
                suffix = self._sanitize_path_component(candidate, fallback="Indefinido")

        return f"Sujeito_{suffix}"

    # ------------------------------------------------------------------
    # Derive processing metadata
    # ------------------------------------------------------------------

    def derive_processing_metadata(
        self,
        experiment_id: str,
        video_path: Path | str | None = None,
        *,
        project_data: dict[str, Any],
        find_video_entry_fn: Callable[..., dict | None],
        get_available_groups_fn: Callable[[], list[str]],
    ) -> dict:
        """Construct metadata for processing when metadata.csv has no entry.

        Args:
            experiment_id: Experiment identifier (usually video stem).
            video_path: Optional path to the video file.
            project_data: The project data dictionary.
            find_video_entry_fn: Callback to find a video entry by path/experiment_id.
            get_available_groups_fn: Callback to get available group names.

        Returns:
            Metadata dictionary with experiment_id, group, day, subject, etc.
        """
        if video_path is not None:
            video_path = Path(video_path) if isinstance(video_path, str) else video_path
        metadata: dict = {}

        video_entry = find_video_entry_fn(path=video_path, experiment_id=experiment_id)
        if video_entry:
            metadata.update(dict(video_entry.get("metadata") or {}))

            for key in ("group", "group_display_name", "day", "subject"):
                value = video_entry.get(key)
                if (
                    value is not None
                    and (value != "" or isinstance(value, int | float))
                    and key not in metadata
                ):
                    metadata[key] = value

        # Fallback: Use custom regex from wizard if metadata is still empty
        if not metadata.get("group") or not metadata.get("subject"):
            wizard_meta = project_data.get("_wizard_metadata", {})
            patterns = wizard_meta.get("custom_regex_patterns")
            if patterns and isinstance(patterns, dict) and video_path:
                from zebtrack.ui.wizard.models import MultiAquariumData

                try:
                    combined = MultiAquariumData.build_combined_regex_pattern(
                        group_pattern=patterns.get("group_pattern"),
                        day_pattern=patterns.get("day_pattern"),
                        subject_pattern=patterns.get("subject_pattern"),
                    )
                    if combined:
                        temp_config = MultiAquariumData(
                            enabled=True, regex_pattern=combined, aquarium_configs=[]
                        )
                        filename = Path(video_path).name
                        matches = temp_config.extract_metadata(filename)
                        if matches:
                            match = matches[0]
                            available_groups = get_available_groups_fn()

                            for key in ("group", "day", "subject"):
                                val = match.get(key)
                                if val and not metadata.get(key):
                                    if key == "group":
                                        metadata[key] = self.resolve_group_name(
                                            val, available_groups
                                        )
                                    else:
                                        metadata[key] = val
                            log.info(
                                "project.metadata.derived_from_regex",
                                video=filename,
                                metadata=metadata,
                            )
                except (re.error, ValueError, KeyError) as e:
                    log.debug("project.metadata.regex_derivation_failed", error=str(e))

        metadata.setdefault("experiment_id", experiment_id)
        metadata.setdefault("video_name", experiment_id)

        if metadata.get("group") and not metadata.get("group_id"):
            metadata["group_id"] = metadata["group"]
        if metadata.get("group_display_name") and not metadata.get("group_label"):
            metadata["group_label"] = metadata["group_display_name"]

        return metadata

    @staticmethod
    def resolve_group_name(regex_value: str, available_groups: list[str]) -> str:
        """Resolve raw regex value to match project group names (e.g., '1' -> 'G01')."""
        if not regex_value or not available_groups:
            return regex_value or "Sem_Grupo"

        if regex_value in available_groups:
            return regex_value

        # Try numeric matching
        regex_digits = re.search(r"\d+", str(regex_value))
        if regex_digits:
            try:
                val = int(regex_digits.group())
                for group in available_groups:
                    group_digits = re.search(r"\d+", str(group))
                    if group_digits and int(group_digits.group()) == val:
                        return group
            except (ValueError, TypeError):
                log.debug(
                    "project.resolve_group.parse_error",
                    regex_value=regex_value,
                    exc_info=True,
                )
        return regex_value

    # ------------------------------------------------------------------
    # Output registration
    # ------------------------------------------------------------------

    def register_processing_outputs(
        self,
        video_path: Path | str,
        *,
        project_path: Path | str | None,
        find_video_entry_fn: Callable[..., dict | None],
        add_video_batch_fn: Callable[..., None],
        get_zone_data_fn: Callable[..., Any],
        save_project_fn: Callable[[], None],
        results_dir: str | None = None,
        trajectory_path: str | None = None,
        summary_parquet: str | None = None,
        summary_excel: str | None = None,
        report_path: str | None = None,
        experiment_id: str | None = None,
        group: str | None = None,
        day: str | None = None,
        subject_id: str | None = None,
        polygon_source: str | None = None,
    ) -> bool:
        """Update project metadata with freshly generated analysis artifacts.

        Args:
            video_path: Path to the video file.
            project_path: Path to the project root directory.
            find_video_entry_fn: Callback to find a video entry.
            add_video_batch_fn: Callback to add a video batch.
            get_zone_data_fn: Callback to get zone data for a video.
            save_project_fn: Callback to save the project.
            results_dir: Directory containing analysis results.
            trajectory_path: Path to trajectory parquet file.
            summary_parquet: Path to summary parquet file.
            summary_excel: Path to summary Excel file.
            report_path: Path to report file.
            experiment_id: Experiment identifier.
            group: Experimental group.
            day: Experiment day.
            subject_id: Subject identifier.

        Returns:
            True if registration successful, False otherwise.
        """
        video_path_str = Path(video_path).as_posix()
        video_entry = find_video_entry_fn(path=video_path_str, experiment_id=experiment_id)
        if not video_entry:
            log.info(
                "project.outputs.adding_missing_video",
                video_path=video_path_str,
            )
            video_info: dict[str, Any] = {"path": video_path_str, "status": "processing"}
            if group:
                video_info["group"] = group
            if day:
                video_info["day"] = day
            if subject_id:
                video_info["subject"] = subject_id
            add_video_batch_fn([video_info], save_project=False)
            video_entry = find_video_entry_fn(path=video_path_str)
            if not video_entry:
                log.warning(
                    "project.outputs.video_still_not_found",
                    video_path=video_path_str,
                )
                return False

        # Update metadata if provided and not already set
        metadata = video_entry.setdefault("metadata", {})
        if group and not metadata.get("group"):
            metadata["group"] = group
        if day and not metadata.get("day"):
            metadata["day"] = day
        if subject_id and not metadata.get("subject"):
            metadata["subject"] = subject_id
        if polygon_source:
            # Always overwrite — the source reflects the most recent recording.
            metadata["polygon_source"] = polygon_source

        # Update flags, parquet mapping and persist as needed using helpers.
        # Pass results_dir so the disk-fallback can pick up the arena/ROI
        # parquet files written by the live recorder under
        # ``live_analysis_sessions/<session>/`` even when in-memory zones are
        # keyed by the reference-frame path rather than the recorded MP4 path.
        self._update_entry_zone_flags(
            video_entry,
            video_path_str,
            get_zone_data_fn,
            results_dir=results_dir,
        )
        if results_dir:
            video_entry["results_dir"] = Path(results_dir).as_posix()

        # Standardize all paths to POSIX before saving
        safe_traj = Path(trajectory_path).as_posix() if trajectory_path else None
        safe_sum_p = Path(summary_parquet).as_posix() if summary_parquet else None
        safe_sum_e = Path(summary_excel).as_posix() if summary_excel else None
        safe_report = Path(report_path).as_posix() if report_path else None

        changed = self._update_parquet_files_and_status(
            video_entry,
            trajectory_path=safe_traj,
            summary_parquet=safe_sum_p,
            summary_excel=safe_sum_e,
            report_path=safe_report,
        )

        if changed:
            log.info(
                "project.outputs.registered",
                video=os.path.basename(video_path_str),
                trajectory=bool(trajectory_path),
                summary=bool(summary_parquet or summary_excel or report_path),
                status=video_entry.get("status"),
            )
            if project_path:
                save_project_fn()

        return True

    @staticmethod
    def _update_entry_zone_flags(
        video_entry: dict,
        video_path: Path | str,
        get_zone_data_fn: Callable[..., Any],
        results_dir: Path | str | None = None,
    ) -> None:
        """Update has_arena/has_rois flags from zone data when missing.

        For live recordings, ``get_zone_data(video_path)`` returns nothing
        because the zones were saved under the ``live_camera_reference_frame.png``
        key, not under the freshly-recorded MP4 path. As a fallback, scan
        ``results_dir`` for the ``1_ProcessingArea_*.parquet`` /
        ``2_AreasOfInterest_*.parquet`` files the recorder writes — audit
        Erro 3 follow-up (2026-05-25). Without this, "Controle Principal"
        keeps showing 🧭 trajectory but no 🏟 arena even after a successful
        live recording.
        """
        video_path = str(video_path) if isinstance(video_path, Path) else video_path
        zone_data = get_zone_data_fn(video_path, fallback_to_global=False)
        if zone_data:
            if zone_data.polygon and not video_entry.get("has_arena"):
                video_entry["has_arena"] = True
                log.info("project.outputs.arena_flag_updated", video=video_path)
            if zone_data.roi_polygons and not video_entry.get("has_rois"):
                video_entry["has_rois"] = True
                log.info("project.outputs.rois_flag_updated", video=video_path)

        # Disk-based fallback for live recordings (and any case where the
        # zone_data lookup misses but the parquet was already written).
        if results_dir and not (video_entry.get("has_arena") and video_entry.get("has_rois")):
            results_path = Path(results_dir)
            if results_path.exists():
                if not video_entry.get("has_arena"):
                    arena_hits = list(results_path.glob("1_ProcessingArea_*.parquet"))
                    if arena_hits:
                        video_entry["has_arena"] = True
                        video_entry.setdefault("parquet_files", {})["arena"] = arena_hits[
                            0
                        ].as_posix()
                        log.info(
                            "project.outputs.arena_flag_from_disk",
                            video=video_path,
                            arena_parquet=arena_hits[0].as_posix(),
                        )
                if not video_entry.get("has_rois"):
                    roi_hits = list(results_path.glob("2_AreasOfInterest_*.parquet"))
                    if roi_hits:
                        video_entry["has_rois"] = True
                        video_entry.setdefault("parquet_files", {})["rois"] = roi_hits[0].as_posix()
                        log.info(
                            "project.outputs.rois_flag_from_disk",
                            video=video_path,
                            rois_parquet=roi_hits[0].as_posix(),
                        )

    @staticmethod
    def _update_parquet_files_and_status(
        video_entry: dict,
        *,
        trajectory_path: str | None = None,
        summary_parquet: str | None = None,
        summary_excel: str | None = None,
        report_path: str | None = None,
    ) -> bool:
        """Update parquet file references and derived flags/status.

        Returns True if any field changed.
        """
        parquet_files = video_entry.setdefault("parquet_files", {})
        changed = False

        if trajectory_path:
            if parquet_files.get("trajectory") != trajectory_path:
                parquet_files["trajectory"] = trajectory_path
                changed = True
            if not video_entry.get("has_trajectory"):
                video_entry["has_trajectory"] = True
                changed = True

        if summary_parquet:
            if parquet_files.get("summary") != summary_parquet:
                parquet_files["summary"] = summary_parquet
                changed = True
            if not video_entry.get("has_summary"):
                video_entry["has_summary"] = True
                changed = True

        if summary_excel:
            if parquet_files.get("summary_excel") != summary_excel:
                parquet_files["summary_excel"] = summary_excel
                changed = True
            if not video_entry.get("has_summary"):
                video_entry["has_summary"] = True
                changed = True

        if report_path:
            if parquet_files.get("report_docx") != report_path:
                parquet_files["report_docx"] = report_path
                changed = True

        if (
            video_entry.get("has_arena")
            and video_entry.get("has_rois")
            and video_entry.get("has_trajectory")
            and not video_entry.get("has_complete_data")
        ):
            video_entry["has_complete_data"] = True
            changed = True

        if video_entry.get("has_trajectory") and video_entry.get("status") != "processed":
            video_entry["status"] = "processed"
            changed = True

        return changed

    # ------------------------------------------------------------------
    # Multi-aquarium methods
    # ------------------------------------------------------------------

    def resolve_multi_aquarium_results_directories(
        self,
        experiment_id: str,
        aquarium_configs: list[dict],
        *,
        project_path: Path | str | None,
    ) -> dict[int, Path]:
        """Resolve results directories for multiple aquariums.

        Creates hierarchical structure:
            {project_root}/Grupo_{group}/Dia_{day}/Sujeito_{subject_id}/

        Args:
            experiment_id: Experiment/video identifier.
            aquarium_configs: List of aquarium config dicts with aquarium_id, group, etc.
            project_path: Path to the project root directory.

        Returns:
            Dict mapping aquarium_id to Path for each aquarium's results directory.
        """
        if not project_path:
            log.warning("project.multi_aquarium.no_project_path")
            return {}

        result: dict[int, Path] = {}

        for config in aquarium_configs:
            aq_id = config.get("aquarium_id", 0)
            group = config.get("group", "")
            subject_id = config.get("subject_id", "")
            day = config.get("day", 1)

            group_component = self._format_group_component({"group": group})
            day_component = self._format_day_component({"day": day})
            subject_component = self._format_subject_component({"subject_id": subject_id})

            results_dir = Path(project_path) / group_component / day_component / subject_component

            # Não cria a pasta ANSIOSAMENTE quando o grupo está ausente/vazio.
            # Antes, um grupo vazio caía no fallback ``Grupo_Sem_Grupo`` e o
            # ``mkdir`` deixava uma pasta fantasma na raiz do projeto mesmo
            # quando nenhum dado era escrito (ex.: sessão live cujo aquário
            # auto-detectado não carrega o grupo). Quando o grupo existe, a
            # pasta é criada como antes; quando falta, o diretório é deixado
            # para ser criado sob demanda pelos escritores (recorder/reporters
            # fazem mkdir do próprio destino) — assim só existe se houver dados.
            group_missing = group is None or str(group).strip() == ""
            if group_missing:
                log.warning(
                    "project.multi_aquarium.group_missing_dir_deferred",
                    aquarium_id=aq_id,
                    path=str(results_dir),
                    experiment=experiment_id,
                )
            else:
                results_dir.mkdir(parents=True, exist_ok=True)

            result[aq_id] = results_dir

            log.info(
                "project.multi_aquarium.directory_resolved",
                aquarium_id=aq_id,
                path=str(results_dir),
                experiment=experiment_id,
                created=not group_missing,
            )

        return result

    def register_multi_aquarium_outputs(
        self,
        video_path: Path | str,
        outputs_by_aquarium: dict[int, dict],
        *,
        project_path: Path | str | None,
        find_video_entry_fn: Callable[..., dict | None],
        save_project_fn: Callable[[], None],
    ) -> bool:
        """Register outputs from multiple aquariums in the project.

        Args:
            video_path: Path to the video file.
            outputs_by_aquarium: Dict mapping aquarium_id to output info.
            project_path: Path to the project root directory.
            find_video_entry_fn: Callback to find a video entry.
            save_project_fn: Callback to save the project.

        Returns:
            True if registration was successful, False otherwise.
        """
        video_path_str = str(Path(video_path) if isinstance(video_path, str) else video_path)
        video_entry = find_video_entry_fn(path=video_path_str)

        if not video_entry:
            log.warning(
                "project.multi_aquarium.video_not_found",
                video_path=video_path_str,
            )
            return False

        # Store multi-aquarium outputs in video entry
        video_entry["multi_aquarium_mode"] = True
        if "multi_aquarium_outputs" not in video_entry:
            video_entry["multi_aquarium_outputs"] = {}

        for aq_id, output_info in outputs_by_aquarium.items():
            aq_key = str(aq_id)

            # Standardize parquet paths to POSIX
            pf_orig = output_info.get("parquet_files", {})
            pf_safe = {k: Path(v).as_posix() if v else None for k, v in pf_orig.items()}

            video_entry["multi_aquarium_outputs"][aq_key] = {
                "results_dir": Path(output_info.get("results_dir", "")).as_posix(),
                "parquet_files": pf_safe,
                "group": output_info.get("group", ""),
                "subject_id": output_info.get("subject_id", ""),
                "day": output_info.get("day", 1),
                "frame_crop_box": output_info.get("frame_crop_box"),
            }

        # Update status if all aquariums have trajectory data
        expected_aq_count = video_entry.get(
            "num_aquariums", len(video_entry["multi_aquarium_outputs"])
        )

        all_have_trajectory = len(
            video_entry["multi_aquarium_outputs"]
        ) >= expected_aq_count and all(
            aq_output.get("parquet_files", {}).get("trajectory")
            for aq_output in video_entry["multi_aquarium_outputs"].values()
        )
        if all_have_trajectory:
            video_entry["status"] = "processed"
            video_entry["has_trajectory"] = True

        # Update has_summary if any aquarium has summary files
        any_have_summary = any(
            aq_output.get("parquet_files", {}).get("summary")
            or aq_output.get("parquet_files", {}).get("summary_excel")
            for aq_output in video_entry["multi_aquarium_outputs"].values()
        )
        if any_have_summary:
            video_entry["has_summary"] = True

        log.info(
            "project.multi_aquarium.outputs_registered",
            video=os.path.basename(video_path_str),
            aquarium_count=len(outputs_by_aquarium),
        )

        if project_path:
            save_project_fn()

        return True

    def get_multi_aquarium_outputs(
        self,
        video_path: Path | str,
        *,
        find_video_entry_fn: Callable[..., dict | None],
    ) -> dict[int, dict] | None:
        """Get multi-aquarium outputs for a video.

        Args:
            video_path: Path to the video file.
            find_video_entry_fn: Callback to find a video entry.

        Returns:
            Dict mapping aquarium_id to output info, or None if not found.
        """
        video_path_str = str(Path(video_path) if isinstance(video_path, str) else video_path)
        video_entry = find_video_entry_fn(path=video_path_str)

        if not video_entry:
            return None

        if not video_entry.get("multi_aquarium_mode"):
            return None

        return video_entry.get("multi_aquarium_outputs")

    # ------------------------------------------------------------------
    # Batch reports
    # ------------------------------------------------------------------

    def register_batch_outputs(
        self,
        batch_id: str,
        unified_excel: str,
        session_count: int,
        *,
        project_data: dict[str, Any],
        project_path: Path | str | None,
        save_project_fn: Callable[[], None],
        group: str | None = None,
        day: str | None = None,
        subject_id: str | None = None,
    ) -> bool:
        """Register unified batch report outputs.

        Args:
            batch_id: Unique batch identifier.
            unified_excel: Path to unified Excel report.
            session_count: Number of sessions in batch.
            project_data: The project data dictionary.
            project_path: Path to the project root directory.
            save_project_fn: Callback to save the project.
            group: Optional experimental group.
            day: Optional day identifier.
            subject_id: Optional subject identifier.

        Returns:
            True if registration successful.
        """
        if not project_data:
            log.warning("project.batch_outputs.no_project")
            return False

        # Ensure batch_reports section exists
        if "batch_reports" not in project_data:
            project_data["batch_reports"] = {}

        # Register batch
        project_data["batch_reports"][batch_id] = {
            "unified_excel": Path(unified_excel).as_posix(),
            "session_count": session_count,
            "group": group,
            "day": day,
            "subject_id": subject_id,
            "created_at": datetime.now().isoformat(),
        }

        log.info(
            "project.batch_outputs.registered",
            batch_id=batch_id,
            session_count=session_count,
        )

        if project_path:
            save_project_fn()

        return True

    @staticmethod
    def get_batch_reports(project_data: dict[str, Any]) -> dict[str, dict]:
        """Get all registered batch reports.

        Args:
            project_data: The project data dictionary.

        Returns:
            Dictionary mapping batch_id to batch metadata.
        """
        if not project_data:
            return {}
        return project_data.get("batch_reports", {})
