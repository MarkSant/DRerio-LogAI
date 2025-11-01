"""
RecordingFacade: Isola lógica de gravação do MainViewModel.

Responsabilidades:
- Gerenciar ciclo de vida de gravação (start/stop/pause)
- Coordenar Recorder com StateManager
- Publicar eventos de gravação via EventBus
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from zebtrack.core.state_manager import StateManager
    from zebtrack.io.recorder import Recorder
    from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


class RecordingFacade:
    """Facade para operações de gravação."""

    def __init__(
        self,
        recorder: "Recorder",
        state_manager: "StateManager",
        event_bus: "EventBus",
    ):
        """
        Initialize RecordingFacade.

        Args:
            recorder: Recorder instance for video/data persistence
            state_manager: StateManager for state tracking
            event_bus: EventBus for publishing events
        """
        self.recorder = recorder
        self.state_manager = state_manager
        self.event_bus = event_bus

        log.info("recording_facade.initialized")

    def start_recording(
        self,
        video_path: Path,
        output_dir: Path,
        fps: float = 30.0,
        record_video: bool = False,
    ) -> bool:
        """
        Start recording session.

        Args:
            video_path: Path to input video
            output_dir: Directory for output files
            fps: Frames per second
            record_video: Whether to record overlay video

        Returns:
            True if started successfully, False otherwise
        """
        try:
            # Validate inputs
            if not video_path.exists():
                log.error("recording_facade.start.video_not_found", path=str(video_path))
                return False

            output_dir.mkdir(parents=True, exist_ok=True)

            # Start recorder
            self.recorder.start_recording(
                output_folder=str(output_dir),
                frame_width=1920,  # Default values, should be provided by caller
                frame_height=1080,
                zones=None,  # Zones should be provided by caller
                is_video_file=True,
                pixel_per_cm_ratio=None,
                base_name=video_path.stem,
                calibration=None,
            )

            # Update state
            self.state_manager.update_recording_state(
                source="recording_facade.start",
                is_recording=True,
                output_path=output_dir,
            )

            # Publish event
            self.event_bus.publish_event(
                "recording.started",
                data={
                    "video_path": str(video_path),
                    "output_dir": str(output_dir),
                },
            )

            log.info(
                "recording_facade.start.success",
                video=str(video_path),
                output=str(output_dir),
            )
            return True

        except Exception as e:
            log.error("recording_facade.start.failed", error=str(e), exc_info=True)
            return False

    def stop_recording(self) -> bool:
        """
        Stop current recording session.

        Returns:
            True if stopped successfully, False otherwise
        """
        try:
            # Check if recording
            if not self.state_manager.get_recording_state().is_recording:
                log.warning("recording_facade.stop.not_recording")
                return False

            # Stop recorder
            self.recorder.stop_recording()

            # Update state
            self.state_manager.update_recording_state(
                source="recording_facade.stop",
                is_recording=False,
            )

            # Publish event
            self.event_bus.publish_event("recording.stopped")

            log.info("recording_facade.stop.success")
            return True

        except Exception as e:
            log.error("recording_facade.stop.failed", error=str(e), exc_info=True)
            return False

    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self.state_manager.get_recording_state().is_recording

    def get_output_files(self) -> dict[str, Path]:
        """
        Get paths to output files from current/last recording.

        Returns:
            Dict with keys: 'parquet', 'video' (if recorded), 'metadata'
        """
        recording_state = self.state_manager.get_recording_state()

        if recording_state.output_path is None:
            return {}

        output_dir = Path(recording_state.output_path)
        if not output_dir.exists():
            return {}

        files = {}

        # Find parquet file
        parquet_files = list(output_dir.glob("*_trajectory.parquet"))
        if parquet_files:
            files["parquet"] = parquet_files[0]

        # Find video file
        video_files = list(output_dir.glob("*_tracked.mp4"))
        if video_files:
            files["video"] = video_files[0]

        # Find metadata
        metadata_files = list(output_dir.glob("metadata.csv"))
        if metadata_files:
            files["metadata"] = metadata_files[0]

        return files
