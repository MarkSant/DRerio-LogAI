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

if TYPE_CHECKING:
    from zebtrack.analysis.analysis_service import AnalysisService
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus import EventBus

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
        event_bus: EventBus | None = None,
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
            # Include microseconds for uniqueness when multiple batches created in same second
            batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
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

        self.logger.info(
            "live_batch.session_registered",
            batch_id=batch.batch_id,
            experiment_id=experiment_id,
            session_count=batch.session_count,
        )

        return batch.batch_id

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
                self.event_bus.publish_event(
                    "BATCH_ANALYSIS_COMPLETED",
                    {
                        "batch_id": batch_id,
                        "session_count": batch.session_count,
                        "group": batch.group,
                        "day": batch.day,
                        "subject_id": batch.subject_id,
                    },
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

    def _create_batch_key(
        self, group: str | None, day: str | None, subject_id: str | None
    ) -> str:
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
            project_root = (
                self.project_manager.project_root
                if hasattr(self.project_manager, "project_root")
                else self.project_manager.project_path.parent
                if hasattr(self.project_manager, "project_path")
                else None
            )
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

            # TODO: Implement cross-session aggregation in AnalysisService
            # For now, generate individual reports and aggregate manually
            all_summaries = []
            for video_path in video_paths:
                video_entry = self.project_manager.find_video_entry(path=video_path)
                if not video_entry:
                    self.logger.warning(
                        "live_batch.unified_report.video_not_found",
                        video_path=video_path,
                    )
                    continue

                # Check if has analysis results
                if "summary_excel" not in video_entry:
                    self.logger.warning(
                        "live_batch.unified_report.no_analysis",
                        video_path=video_path,
                    )
                    continue

                summary_path = video_entry["summary_excel"]
                all_summaries.append(Path(summary_path))

            if not all_summaries:
                self.logger.error(
                    "live_batch.unified_report.no_summaries",
                    batch_id=batch.batch_id,
                )
                return False

            # Aggregate summaries into unified Excel
            unified_excel = unified_dir / f"UnifiedReport_{batch.batch_id}.xlsx"
            self._aggregate_summaries(all_summaries, unified_excel)

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

        except Exception as e:
            self.logger.error(
                "live_batch.unified_report.exception",
                batch_id=batch.batch_id,
                error=str(e),
                exc_info=True,
            )
            return False

    def _aggregate_summaries(self, summary_paths: list[Path], output_path: Path) -> None:
        """Aggregate individual session summaries into unified Excel.

        Args:
            summary_paths: List of individual summary Excel files
            output_path: Path for unified output
        """
        import pandas as pd

        self.logger.info(
            "live_batch.aggregate_summaries.start",
            summary_count=len(summary_paths),
        )

        all_data = []
        for i, summary_path in enumerate(summary_paths, 1):
            try:
                df = pd.read_excel(summary_path)
                df["session_number"] = i
                df["session_file"] = summary_path.stem
                all_data.append(df)
            except Exception as e:
                self.logger.warning(
                    "live_batch.aggregate_summaries.read_failed",
                    summary_path=str(summary_path),
                    error=str(e),
                )

        if not all_data:
            raise ValueError("No valid summary data to aggregate")

        # Concatenate all session data
        unified_df = pd.concat(all_data, ignore_index=True)

        # Write to Excel
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            # Sheet 1: All sessions combined
            unified_df.to_excel(writer, sheet_name="All Sessions", index=False)

            # Sheet 2: Summary statistics across sessions
            if len(all_data) > 1:
                summary_stats = unified_df.groupby("session_number").agg(
                    {
                        "total_distance_cm": "mean",
                        "average_speed_cm_s": "mean",
                        "time_in_center_s": "mean",
                        "entries_to_center": "sum",
                    }
                )
                summary_stats.to_excel(writer, sheet_name="Session Summary")

        self.logger.info(
            "live_batch.aggregate_summaries.success",
            output=str(output_path),
            total_rows=len(unified_df),
        )
