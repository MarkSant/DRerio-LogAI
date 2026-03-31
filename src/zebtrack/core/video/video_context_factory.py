"""Video context factory mixin — VideoCapture lifecycle, results dir, and trajectory I/O.

Extracted from VideoProcessingService (Phase 2.3 decomposition).
Methods:
    _create_video_context, _seek_to_frame, display_initial_frame,
    resolve_results_path, ensure_arena_polygon, load_trajectory_dataframe,
    _snapshot_results_dir, _cleanup_cancelled_results, _prepare_results_directory
"""

from __future__ import annotations

import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np
import pandas as pd
import structlog

if TYPE_CHECKING:
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.ui_scheduler import UIScheduler
    from zebtrack.io.recorder import Recorder
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2

from zebtrack.ui.event_bus_v2 import Event, UIEvents
from zebtrack.ui.payloads import FrameDisplayPayload

log = structlog.get_logger()


class VideoContextFactoryMixin:
    """Mixin providing video context creation, results directory management, and trajectory I/O."""

    # ── Attribute stubs for type checkers (provided by the facade __init__) ──
    project_manager: ProjectManager
    state_manager: StateManager
    ui_coordinator: UIScheduler
    ui_event_bus: EventBusV2
    settings: Settings
    detector: Any
    recorder: Recorder | None

    # ── VideoContext import (deferred to avoid circular) ──

    def _create_video_context(self, video_path: Path | str) -> Any:
        """Open a video once and cache metadata/first frame for downstream steps.

        v2.2: Dynamic frame skip calibration with warm-up + 1 seek measurement.
        """
        from zebtrack.core.video.video_processing_service import VideoContext

        normalized_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        cap = cv2.VideoCapture(normalized_path)
        if not cap.isOpened():
            log.error("video_processing.video_open_failed", path=normalized_path)
            return None

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or getattr(self.settings.video_processing, "fps", 30.0)

        # v2.2: Dynamic frame skip calibration
        # Warm-up seek to reset internal state
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        cap.read()  # Discard warm-up frame

        # Measure single seek to frame 100
        t0 = time.perf_counter()
        cap.set(cv2.CAP_PROP_POS_FRAMES, 100)
        cap.read()  # Execute seek
        seek_time_ms = (time.perf_counter() - t0) * 1000

        # Calculate optimal skip threshold
        if seek_time_ms < 10:
            skip_threshold = 120  # Fast seek - use larger skip
        elif seek_time_ms < 50:
            skip_threshold = 80  # Medium seek
        else:
            skip_threshold = 60  # Slow seek - conservative skip

        log.info(
            "video_processing.frame_skip_calibrated",
            path=Path(normalized_path).name,
            seek_time_ms=round(seek_time_ms, 2),
            skip_threshold=skip_threshold,
        )

        # Reset to beginning for first frame capture
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        first_frame = None
        ret, frame = cap.read()
        if ret:
            first_frame = frame.copy()
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        else:
            log.debug("video_processing.initial_frame_missing", path=normalized_path)

        return VideoContext(
            path=normalized_path,
            cap=cap,
            width=width,
            height=height,
            fps=fps,
            first_frame=first_frame,
            skip_threshold=skip_threshold,
        )

    def _seek_to_frame(
        self,
        cap: cv2.VideoCapture,
        target_frame: int,
        current_frame: int,
        skip_threshold: int = 60,
    ) -> bool:
        """Optimized frame seeking using hybrid grab()/set() strategy.

        v2.2: Uses calibrated skip_threshold to choose between:
        - grab() for small sequential gaps (< threshold)
        - set() for large jumps (>= threshold)

        Args:
            cap: OpenCV VideoCapture object
            target_frame: Destination frame number
            current_frame: Current position
            skip_threshold: Gap threshold for set() vs grab() decision

        Returns:
            True if seek succeeded, False otherwise
        """
        gap = target_frame - current_frame

        if gap <= 0:
            # Backward seek always uses set()
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            return True
        elif gap < skip_threshold:
            # Small gap - use grab() for sequential advance
            for _ in range(gap):
                if not cap.grab():
                    return False
            return True
        else:
            # Large gap - use set() for direct seek
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            return True

    def display_initial_frame(
        self, video_path: Path | str, frame: np.ndarray | None = None
    ) -> None:
        """Display first frame of video in UI.

        Args:
            video_path: Path to video file
            frame: Optional pre-loaded frame
        """
        if frame is not None:
            self.ui_event_bus.publish(
                Event(type=UIEvents.UI_DISPLAY_FRAME, data=FrameDisplayPayload(frame=frame))
            )
            return

        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        cap = None
        try:
            cap = cv2.VideoCapture(video_path)
            ret, frame = cap.read()
            if ret:
                self.ui_event_bus.publish(
                    Event(
                        type=UIEvents.UI_DISPLAY_FRAME,
                        data=FrameDisplayPayload(frame=frame),
                    )
                )
        # except Exception justified: cv2 VideoCapture frame display — poorly-typed errors
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
    ) -> tuple[Path, bool]:
        """Resolve output directory for processing results.

        Args:
            experiment_id: Unique experiment identifier
            video_path: Path to source video
            metadata_context: Optional metadata dictionary
            single_video_config: Config for single video mode (non-project)
            output_base_dir: Base directory for output (fallback)

        Returns:
            Tuple with the resolved path and whether it existed prior to the call.
        """
        if self.project_manager.project_path and not single_video_config:
            results_path = self.project_manager.resolve_results_directory(
                experiment_id,
                video_path=video_path,
                metadata=metadata_context,
            )
        else:
            results_path = Path(output_base_dir)

        existed_before = results_path.exists()
        results_path.mkdir(parents=True, exist_ok=True)
        return results_path, existed_before

    def ensure_arena_polygon(
        self,
        arena_polygon_px: list | None,
        video_path: Path | str | None = None,
        video_context: Any | None = None,
    ) -> list[list[int]] | list | None:
        """Ensure arena polygon exists, using full frame as fallback.

        Args:
            arena_polygon_px: Existing polygon or None
            video_path: Path to video (for extracting dimensions)
            video_context: Optional VideoContext with cached dimensions

        Returns:
            Arena polygon (existing or full-frame fallback)
        """
        if arena_polygon_px:
            return arena_polygon_px

        if video_context is not None:
            return [
                [0, 0],
                [video_context.width, 0],
                [video_context.width, video_context.height],
                [0, video_context.height],
            ]

        if video_path is None:
            return None

        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)

        cap = None
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None

            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            return [[0, 0], [width, 0], [width, height], [0, height]]
        finally:
            if cap is not None and cap.isOpened():
                cap.release()

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
        trajectory_path = (
            Path(trajectory_path) if isinstance(trajectory_path, str) else trajectory_path
        )

        def _publish_error(payload: dict[str, str]) -> None:
            if self.ui_event_bus is None:
                return
            self.ui_event_bus.publish(
                Event(
                    type=UIEvents.SHOW_ERROR,
                    data=payload,
                    source="VideoProcessingService.load_trajectory_dataframe",
                )
            )

        if not trajectory_path.exists():
            _publish_error(
                {
                    "title": "Erro de Processamento",
                    "message": (f"Falha ao gerar arquivo de trajetória para {experiment_id}."),
                    "details": f"Arquivo não encontrado: {trajectory_path}",
                }
            )
            return None

        try:
            return pd.read_parquet(trajectory_path)
        # except Exception justified: pandas parquet read — heterogeneous data errors
        except Exception as exc:
            log.error(
                "video_processing.trajectory_read_failed",
                path=trajectory_path,
                error=str(exc),
            )
            _publish_error(
                {
                    "title": "Erro de Processamento",
                    "message": f"Falha ao ler arquivo de trajetória para {experiment_id}.",
                    "details": str(exc),
                }
            )
            return None

    def _snapshot_results_dir(self, results_path: Path) -> set[str]:
        """Capture the initial state of a results directory for later cleanup."""
        if not results_path.exists():
            return set()
        try:
            return {item.name for item in results_path.iterdir()}
        except Exception:  # pragma: no cover - best effort snapshot
            log.warning(
                "controller.results.snapshot_failed",
                results_dir=str(results_path),
                exc_info=True,
            )
            return set()

    def _cleanup_cancelled_results(self, results_dir: Path | str, baseline_items: set[str]) -> None:
        """Remove artifacts created during a cancelled analysis run."""
        results_path = Path(results_dir)
        if not results_path.exists():
            return

        try:
            for item in list(results_path.iterdir()):
                if item.name in baseline_items:
                    continue
                try:
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink(missing_ok=True)
                except FileNotFoundError:
                    continue
                except OSError:
                    log.warning(
                        "controller.results.cleanup_failed",
                        path=str(item),
                        exc_info=True,
                    )

            remaining = {child.name for child in results_path.iterdir()}
            if not baseline_items and not remaining:
                results_path.rmdir()
                log.info("controller.results.cleanup_removed_directory", path=str(results_path))
        except Exception:  # pragma: no cover - defensive cleanup
            log.warning(
                "controller.results.cleanup_unexpected_error",
                results_dir=str(results_dir),
                exc_info=True,
            )

    def _prepare_results_directory(self, results_dir: Path | str) -> None:
        """Keep per-video results folders clean and archive older runs."""
        path = Path(results_dir)
        path.mkdir(parents=True, exist_ok=True)

        existing_items = [item for item in path.iterdir() if item.name != "history"]
        if not existing_items:
            return

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        history_root = path / "history"
        archive_dir = history_root / timestamp
        archive_dir.mkdir(parents=True, exist_ok=True)

        for item in existing_items:
            target = archive_dir / item.name
            shutil.move(str(item), str(target))

        log.info(
            "controller.results.archive_previous_run",
            results_dir=str(path),
            archive_dir=str(archive_dir),
            item_count=len(existing_items),
        )
