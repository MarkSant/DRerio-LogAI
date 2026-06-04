"""Live batch coordinator for unified report generation.

This coordinator tracks live camera sessions that belong to the same experimental
batch (same group/day/subject_id) and automatically generates unified reports
after the last session completes.

Architecture:
- Monitors project_data.json for live session metadata
- Detects batch completion (user indication or timeout)
- Triggers unified analysis via AnalysisService
- Persists outputs via ProjectManager

Version: 2.2.0
Author: ZebTrack-AI Team
Date: January 2026
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from zebtrack.utils.report_files import find_summary_excel_file, has_summary_excel_output

if TYPE_CHECKING:
    from zebtrack.analysis.analysis_service import AnalysisService
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2

logger = structlog.get_logger(__name__)


@dataclass
class BatchMetadata:
    """Metadata for a batch of live sessions."""

    batch_id: str
    group: str | None
    day: str | None
    subject_id: str | None
    session_count: int = 0
    completed_sessions: list[str] = field(default_factory=list)
    session_paths: list[Path] = field(default_factory=list)
    is_complete: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    @property
    def batch_key(self) -> str:
        """Unique key for batch identification."""
        parts = [
            self.group or "no_group",
            self.day or "no_day",
            self.subject_id or "no_subject",
        ]
        return "_".join(parts)


class LiveBatchCoordinator:
    """Coordinates batch processing for live camera sessions.

    Responsibilities:
    - Track sessions belonging to same experimental batch
    - Detect batch completion
    - Generate unified reports automatically
    - Publish BATCH_ANALYSIS_COMPLETED events
    - Handle cross-session aggregation

    Usage:
        coordinator = LiveBatchCoordinator(...)
        coordinator.register_session(experiment_id, metadata)
        # ... after last session ...
        coordinator.mark_batch_complete(batch_id)
        # → Automatically generates unified report
    """

    def __init__(
        self,
        project_manager: ProjectManager,
        analysis_service: AnalysisService,
        state_manager: StateManager,
        settings_obj: Settings,
        event_bus: EventBusV2 | None = None,
    ):
        """Initialize coordinator.

        Args:
            project_manager: Project data access
            analysis_service: Analysis pipeline coordinator
            state_manager: Application state manager
            settings_obj: Application settings
            event_bus: Optional event bus for notifications
        """
        self.project_manager = project_manager
        self.analysis_service = analysis_service
        self.state_manager = state_manager
        self.settings = settings_obj
        self.event_bus = event_bus

        self._active_batches: dict[str, BatchMetadata] = {}
        self.logger = logger.bind(domain="live_batch_coordinator")

    @staticmethod
    def _resolve_summary_excel_path(video_entry: dict) -> Path | None:
        """Resolve the registered or on-disk Excel summary/report for a video entry."""
        summary_path = video_entry.get("summary_excel")
        if summary_path:
            return Path(summary_path)

        parquet_files = video_entry.get("parquet_files") or {}
        summary_path = parquet_files.get("summary_excel")
        if summary_path:
            return Path(summary_path)

        return find_summary_excel_file(video_entry.get("results_dir"))

    def register_session(
        self,
        experiment_id: str,
        video_path: Path,
        metadata: dict,
    ) -> str:
        """Register a live session to a batch.

        Args:
            experiment_id: Unique experiment identifier
            video_path: Path to recorded video
            metadata: Session metadata (group, day, subject_id, etc.)

        Returns:
            Batch ID for this session
        """
        # Extract batch identifiers
        group = metadata.get("group")
        day = metadata.get("day")
        subject_id = metadata.get("subject_id")

        # Create batch metadata if not exists
        batch_key = self._create_batch_key(group, day, subject_id)

        if batch_key not in self._active_batches:
            # Include microseconds AND batch_key hash for uniqueness when multiple batches
            # are created in same second (common in multi-aquarium scenarios)
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            key_hash = abs(hash(batch_key)) % 10000  # 4-digit suffix from batch_key
            batch_id = f"batch_{timestamp_str}_{key_hash:04d}"
            self._active_batches[batch_key] = BatchMetadata(
                batch_id=batch_id,
                group=group,
                day=day,
                subject_id=subject_id,
            )
            self.logger.info(
                "live_batch.created",
                batch_id=batch_id,
                batch_key=batch_key,
                group=group,
                day=day,
                subject_id=subject_id,
            )

        batch = self._active_batches[batch_key]
        batch.session_count += 1
        batch.completed_sessions.append(experiment_id)
        batch.session_paths.append(video_path)

        # Audit Erro 2/3 round 6 (2026-05-25): persist the live session into
        # ``project_data["batches"]`` so that downstream consumers (Progresso
        # do Experimento, listbox "Selecionar Vídeo para Desenho", any view
        # that calls ``ProjectManager.get_all_videos``) actually SEE the
        # recorded session. Previously this coordinator only mutated the
        # in-memory ``_active_batches`` dict, so the canonical project data
        # never knew the recording existed and every grupo×dia×sujeito kept
        # showing "Sessão planejada" forever (Audit Erro 4 / item B4).
        try:
            self._persist_session_to_project_data(
                experiment_id=experiment_id,
                video_path=video_path,
                metadata=metadata,
            )
        # except Exception justified: persistence failure must not break
        # in-memory batch tracking — log and continue.
        except Exception as exc:
            self.logger.error(
                "live_batch.persist_to_project_data.failed",
                error=str(exc),
                experiment_id=experiment_id,
                exc_info=True,
            )

        self.logger.info(
            "live_batch.session_registered",
            batch_id=batch.batch_id,
            experiment_id=experiment_id,
            session_count=batch.session_count,
        )

        return batch.batch_id

    def _persist_session_to_project_data(
        self,
        *,
        experiment_id: str,
        video_path: Path,
        metadata: dict,
    ) -> None:
        """Append the recorded live session to ``project_data["batches"]``.

        Mirrors the shape produced by ``VideoManager.add_video_batch`` for
        pre-recorded videos so that ``VideoManager.get_all_videos`` (the
        sole source for the Progresso grid and the Zonas listbox) returns
        a uniform record regardless of whether the session was pre-recorded
        or captured live. Skips the operation when the session was
        cancelled (``.cancelled`` marker in the output directory).
        """
        if not self.project_manager:
            self.logger.debug("live_batch.persist.no_project_manager")
            return

        project_data = self.project_manager.project_data
        if project_data is None:
            self.logger.debug("live_batch.persist.no_project_data")
            return

        results_dir = video_path.parent if video_path else None
        if results_dir and (results_dir / ".cancelled").exists():
            self.logger.info(
                "live_batch.persist.skipped_cancelled",
                experiment_id=experiment_id,
                results_dir=str(results_dir),
            )
            return

        # Build canonical video_entry. Disk flags are populated from the
        # session folder by reusing OutputRegistrationManager logic.
        video_path_str = video_path.as_posix() if isinstance(video_path, Path) else str(video_path)

        normalized_metadata = {
            "group": metadata.get("group"),
            "group_display_name": metadata.get("group"),
            "day": metadata.get("day"),
            "subject": metadata.get("subject_id"),
            "subject_id": metadata.get("subject_id"),
            "experiment_id": experiment_id,
            "timestamp": metadata.get("timestamp"),
            "is_live_session": True,
        }
        # Drop empties to keep the JSON compact (but preserve booleans).
        normalized_metadata = {
            k: v
            for k, v in normalized_metadata.items()
            if v is not None and (v != "" or isinstance(v, bool | int | float))
        }

        # Probe the session folder for parquet outputs to set the flags.
        has_arena = has_rois = has_trajectory = False
        if results_dir and results_dir.exists():
            has_arena = bool(list(results_dir.glob("1_ProcessingArea_*.parquet")))
            has_rois = bool(list(results_dir.glob("2_AreasOfInterest_*.parquet")))
            has_trajectory = bool(list(results_dir.glob("3_CoordMovimento_*.parquet")))
        has_summary = has_summary_excel_output(results_dir) if results_dir else False

        video_entry: dict = {
            "path": video_path_str,
            "status": "processed" if has_trajectory else "recorded",
            "has_arena": has_arena,
            "has_rois": has_rois,
            "has_trajectory": has_trajectory,
            "has_complete_data": has_arena and has_rois and has_trajectory,
            "has_summary": has_summary,
            "zones_finalized": True,
            "metadata": normalized_metadata,
            "filename": (
                video_path.name if isinstance(video_path, Path) else Path(video_path_str).name
            ),
        }

        # Try to find an existing entry for this video path (idempotent).
        existing = None
        for batch in project_data.get("batches", []):
            for entry in batch.get("videos", []):
                if entry.get("path") == video_path_str:
                    existing = entry
                    break
            if existing:
                break

        if existing:
            # Merge: keep older bool=True, update from current scan.
            existing.update(
                {
                    "status": video_entry["status"],
                    "has_arena": existing.get("has_arena") or video_entry["has_arena"],
                    "has_rois": existing.get("has_rois") or video_entry["has_rois"],
                    "has_trajectory": existing.get("has_trajectory")
                    or video_entry["has_trajectory"],
                    "has_summary": existing.get("has_summary") or video_entry["has_summary"],
                    "zones_finalized": True,
                }
            )
            existing["has_complete_data"] = bool(
                existing.get("has_arena")
                and existing.get("has_rois")
                and existing.get("has_trajectory")
            )
            existing.setdefault("metadata", {}).update(normalized_metadata)
            self.logger.info(
                "live_batch.persist.entry_updated",
                experiment_id=experiment_id,
                path=video_path_str,
            )
        else:
            new_batch: dict = {
                "timestamp": datetime.now().isoformat(),
                "source": "live_camera",
                "videos": [video_entry],
            }
            project_data.setdefault("batches", []).append(new_batch)
            self.logger.info(
                "live_batch.persist.entry_added",
                experiment_id=experiment_id,
                path=video_path_str,
                has_arena=has_arena,
                has_trajectory=has_trajectory,
            )

        # Persist to disk so the next ``get_all_videos`` call sees it.
        try:
            self.project_manager.save_project()
            self.logger.info(
                "live_batch.persist.project_saved",
                experiment_id=experiment_id,
            )
        # except Exception justified: best-effort persistence; the in-memory
        # mutation is still visible to consumers that read project_data
        # directly within the same session.
        except Exception as exc:
            self.logger.warning(
                "live_batch.persist.save_failed",
                error=str(exc),
                experiment_id=experiment_id,
            )

    def mark_batch_complete(self, batch_id: str) -> bool:
        """Mark batch as complete and trigger unified report generation.

        Args:
            batch_id: Batch identifier to complete

        Returns:
            True if unified report generated successfully
        """
        batch = self._find_batch_by_id(batch_id)
        if not batch:
            self.logger.warning("live_batch.complete.not_found", batch_id=batch_id)
            return False

        if batch.is_complete:
            self.logger.info("live_batch.complete.already_done", batch_id=batch_id)
            return True

        self.logger.info(
            "live_batch.complete.start",
            batch_id=batch_id,
            session_count=batch.session_count,
        )

        # Generate unified report
        success = self._generate_unified_report(batch)

        if success:
            batch.is_complete = True
            batch.completed_at = datetime.now()
            self.logger.info("live_batch.complete.success", batch_id=batch_id)

            # Publish event
            if self.event_bus:
                from zebtrack.ui import payloads
                from zebtrack.ui.event_bus_v2 import Event, UIEvents

                self.event_bus.publish(
                    Event(
                        type=UIEvents.BATCH_ANALYSIS_COMPLETED,
                        data=payloads.LiveBatchCompletedPayload(
                            batch_id=batch_id,
                            session_count=batch.session_count,
                            group=batch.group,
                            day=batch.day,
                            subject_id=batch.subject_id,
                        ),
                    )
                )
        else:
            self.logger.error("live_batch.complete.failed", batch_id=batch_id)

        return success

    def get_active_batches(self) -> list[BatchMetadata]:
        """Get list of all active (incomplete) batches.

        Returns:
            List of active batch metadata
        """
        return [b for b in self._active_batches.values() if not b.is_complete]

    def get_batch_for_session(self, experiment_id: str) -> BatchMetadata | None:
        """Find batch containing a specific session.

        Args:
            experiment_id: Experiment ID to search for

        Returns:
            Batch metadata or None if not found
        """
        for batch in self._active_batches.values():
            if experiment_id in batch.completed_sessions:
                return batch
        return None

    def _create_batch_key(self, group: str | None, day: str | None, subject_id: str | None) -> str:
        """Create unique batch key from metadata.

        Args:
            group: Experimental group
            day: Day identifier
            subject_id: Subject identifier

        Returns:
            Batch key string
        """
        parts = [
            group or "no_group",
            day or "no_day",
            subject_id or "no_subject",
        ]
        return "_".join(parts)

    def _find_batch_by_id(self, batch_id: str) -> BatchMetadata | None:
        """Find batch by ID.

        Args:
            batch_id: Batch identifier

        Returns:
            Batch metadata or None
        """
        for batch in self._active_batches.values():
            if batch.batch_id == batch_id:
                return batch
        return None

    def _generate_unified_report(self, batch: BatchMetadata) -> bool:
        """Generate unified report for batch.

        Args:
            batch: Batch metadata

        Returns:
            True if report generated successfully
        """
        try:
            self.logger.info(
                "live_batch.unified_report.start",
                batch_id=batch.batch_id,
                session_count=batch.session_count,
            )

            # Collect all session video paths
            video_paths = [str(p) for p in batch.session_paths]

            if not video_paths:
                self.logger.warning(
                    "live_batch.unified_report.no_videos",
                    batch_id=batch.batch_id,
                )
                return False

            # Get project root
            project_root = None
            if hasattr(self.project_manager, "project_root") and self.project_manager.project_root:
                project_root = self.project_manager.project_root
            elif (
                hasattr(self.project_manager, "project_path") and self.project_manager.project_path
            ):
                project_root = Path(self.project_manager.project_path).parent
            if not project_root:
                self.logger.error("live_batch.unified_report.no_project")
                return False

            # Create unified results directory
            unified_dir = project_root / "unified_batch_reports" / batch.batch_id
            unified_dir.mkdir(parents=True, exist_ok=True)

            # Run unified analysis (aggregate all sessions)
            self.logger.info(
                "live_batch.unified_report.analyzing",
                batch_id=batch.batch_id,
                video_count=len(video_paths),
            )

            # Collect summaries for aggregation
            all_summaries = []
            for video_path in video_paths:
                video_entry = self.project_manager.find_video_entry(path=video_path)
                if not video_entry:
                    self.logger.warning(
                        "live_batch.unified_report.video_not_found",
                        video_path=video_path,
                    )
                    continue

                summary_path = self._resolve_summary_excel_path(video_entry)
                if summary_path is None:
                    self.logger.warning(
                        "live_batch.unified_report.no_analysis",
                        video_path=video_path,
                    )
                    continue

                all_summaries.append(summary_path)

            if not all_summaries:
                self.logger.error(
                    "live_batch.unified_report.no_summaries",
                    batch_id=batch.batch_id,
                )
                return False

            # Aggregate summaries into unified Excel
            unified_excel = unified_dir / f"UnifiedReport_{batch.batch_id}.xlsx"
            self.analysis_service.aggregate_session_summaries(all_summaries, unified_excel)

            # Register unified output
            self.project_manager.register_batch_outputs(
                batch_id=batch.batch_id,
                unified_excel=str(unified_excel),
                session_count=batch.session_count,
                group=batch.group,
                day=batch.day,
                subject_id=batch.subject_id,
            )

            self.logger.info(
                "live_batch.unified_report.success",
                batch_id=batch.batch_id,
                output=str(unified_excel),
            )

            return True

        except Exception as e:  # except Exception justified: complex multi-subsystem pipeline
            self.logger.error(
                "live_batch.unified_report.exception",
                batch_id=batch.batch_id,
                error=str(e),
                exc_info=True,
            )
            return False
