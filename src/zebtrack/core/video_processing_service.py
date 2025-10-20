"""Video Processing Service for ZebTrack-AI.

Phase 7.2: Extracts video processing logic from MainViewModel to dedicated service.

This service handles:
- Video tracking orchestration (_run_tracking_if_needed)
- Single video processing workflow (_process_single_video)
- Progress callbacks and UI notifications
- Result path resolution and metadata handling

Responsibilities:
- Coordinate detector, recorder, and project_manager for video processing
- Manage progress callbacks and cancellation events
- Handle initial frame display and trajectory validation
- Resolve output directories based on project context

Dependencies (injected):
- detector: Detector instance for object detection
- recorder: Recorder instance for trajectory writing
- project_manager: ProjectManager for project state
- state_manager: StateManager for centralized state
- ui_coordinator: UICoordinator for UI updates
- root: Tkinter root for scheduling UI updates
- view: ApplicationGUI for direct UI access (minimized)
- cancel_event: threading.Event for cancellation signaling
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import cv2
import pandas as pd
import structlog

if TYPE_CHECKING:
    from zebtrack.core.detector import Detector
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.ui_coordinator import UICoordinator
    from zebtrack.io.recorder import Recorder

log = structlog.get_logger()


class VideoProcessingService:
    """Service for video processing orchestration.

    Phase 7.2: Consolidates video processing logic previously scattered
    in MainViewModel into a cohesive service layer.
    """

    def __init__(
        self,
        *,
        detector: Detector | None,
        recorder: Recorder,
        project_manager: ProjectManager,
        state_manager: StateManager,
        ui_coordinator: UICoordinator,
        root,  # tkinter.Tk
        view,  # ApplicationGUI
        cancel_event,  # threading.Event
    ):
        """Initialize VideoProcessingService with injected dependencies.

        Args:
            detector: Detector instance (can be None if not initialized)
            recorder: Recorder instance for trajectory writing
            project_manager: ProjectManager for project state
            state_manager: StateManager for centralized state
            ui_coordinator: UICoordinator for UI updates
            root: Tkinter root for scheduling UI updates
            view: ApplicationGUI for direct UI access
            cancel_event: Threading event for cancellation signaling
        """
        self.detector = detector
        self.recorder = recorder
        self.project_manager = project_manager
        self.state_manager = state_manager
        self.ui_coordinator = ui_coordinator
        self.root = root
        self.view = view
        self.cancel_event = cancel_event

        log.info("video_processing_service.init.complete")

    def display_initial_frame(self, video_path: Path | str) -> None:
        """Display first frame of video in UI.

        Args:
            video_path: Path to video file
        """
        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        cap = None
        try:
            cap = cv2.VideoCapture(video_path)
            ret, frame = cap.read()
            if ret:
                self.ui_coordinator.display_frame(self.view, frame)
        except Exception as exc:
            log.warning("video_processing.frame_display_error", error=str(exc))
        finally:
            if cap is not None:
                cap.release()

    def resolve_results_path(
        self,
        *,
        experiment_id: str,
        video_path: str,
        metadata_context: dict | None,
        single_video_config: dict | None,
        output_base_dir: str,
    ) -> Path:
        """Resolve output directory for processing results.

        Args:
            experiment_id: Unique experiment identifier
            video_path: Path to source video
            metadata_context: Optional metadata dictionary
            single_video_config: Config for single video mode (non-project)
            output_base_dir: Base directory for output (fallback)

        Returns:
            Path to results directory (created if needed)
        """
        if self.project_manager.project_path and not single_video_config:
            results_path = self.project_manager.resolve_results_directory(
                experiment_id,
                video_path=video_path,
                metadata=metadata_context,
            )
        else:
            results_path = Path(output_base_dir)

        results_path.mkdir(parents=True, exist_ok=True)
        return results_path

    def ensure_arena_polygon(self, arena_polygon_px: list | None, video_path: Path | str) -> list | None:
        """Ensure arena polygon exists, using full frame as fallback.

        Args:
            arena_polygon_px: Existing polygon or None
            video_path: Path to video (for extracting dimensions)

        Returns:
            Arena polygon (existing or full-frame fallback)
        """
        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        if arena_polygon_px:
            return arena_polygon_px

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        return [[0, 0], [width, 0], [width, height], [0, height]]

    def load_trajectory_dataframe(
        self, trajectory_path: Path | str, experiment_id: str
    ) -> pd.DataFrame | None:
        """Load trajectory parquet file with error handling.

        Args:
            trajectory_path: Path to parquet file
            experiment_id: Experiment ID (for error messages)

        Returns:
            DataFrame or None if load failed
        """
        trajectory_path = Path(trajectory_path) if isinstance(trajectory_path, str) else trajectory_path
        if not trajectory_path.exists():
            self.root.after(
                0,
                lambda: self.view.show_error(
                    "Erro de Processamento",
                    f"Falha ao gerar arquivo de trajetória para {experiment_id}.",
                ),
            )
            return None

        try:
            return pd.read_parquet(trajectory_path)
        except Exception as exc:
            log.error(
                "video_processing.trajectory_read_failed",
                path=trajectory_path,
                error=str(exc),
            )
            self.root.after(
                0,
                lambda: self.view.show_error(
                    "Erro de Processamento",
                    f"Falha ao ler arquivo de trajetória para {experiment_id}.",
                ),
            )
            return None

    def create_progress_callback(
        self, *, index: int, total_videos: int, experiment_id: str
    ) -> Callable:
        """Create progress callback for video processing.

        Phase 7.2: Extracted from controller to centralize progress handling.

        Args:
            index: Current video index (1-based)
            total_videos: Total number of videos
            experiment_id: Experiment identifier

        Returns:
            Callable that accepts progress stats dict
        """
        # TODO: Implement in next sub-step (7.2c)
        raise NotImplementedError("Será implementado na sub-etapa 7.2c")

    def run_tracking_if_needed(
        self,
        video_path: Path | str,
        results_dir: str,
        experiment_id: str,
        progress_callback=None,
        calibration_data: dict | None = None,
        analysis_interval_frames: int = 10,
        display_interval_frames: int = 10,
    ) -> tuple[bool, list | None]:
        """Run tracking process if trajectory doesn't exist.

        Args:
            video_path: Path to video file

        Phase 7.2: Core tracking orchestration method (~183 lines).

        Args:
            video_path: Path to video file
            results_dir: Output directory for results
            experiment_id: Unique experiment identifier
            progress_callback: Optional progress update callback
            calibration_data: Optional calibration configuration
            analysis_interval_frames: Frame interval for analysis
            display_interval_frames: Frame interval for display

        Returns:
            Tuple of (success: bool, arena_polygon: list | None)
        """
        # TODO: Implement in sub-step 7.2c
        raise NotImplementedError("Será implementado na sub-etapa 7.2c")

    def process_single_video(
        self,
        *,
        index: int,
        total_videos: int,
        video_info: dict,
        single_video_config: dict | None,
        analysis_interval_frames: int,
        display_interval_frames: int,
        output_base_dir: str,
        experiment_id: str,
        metadata_context: dict | None,
        analysis_profile: dict | None,
    ) -> tuple[bool, str | None]:
        """Process a single video: tracking + analysis.

        Phase 7.2: Complete single-video workflow (~86 lines).

        Args:
            index: Current video index (1-based)
            total_videos: Total number of videos
            video_info: Video metadata dict
            single_video_config: Config for single video mode
            analysis_interval_frames: Frame interval for analysis
            display_interval_frames: Frame interval for display
            output_base_dir: Base output directory
            experiment_id: Unique experiment identifier
            metadata_context: Optional metadata dictionary
            analysis_profile: Optional analysis profile configuration

        Returns:
            Tuple of (success: bool, results_dir: str | None)
        """
        # TODO: Implement in sub-step 7.2d
        raise NotImplementedError("Será implementado na sub-etapa 7.2d")
