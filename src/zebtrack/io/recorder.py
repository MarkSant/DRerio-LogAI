import os
import time
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, FrozenSet  # noqa: UP035

import cv2
import numpy as np
import pandas as pd
import pyarrow as pa
import structlog
from pyarrow import parquet as pq

from zebtrack.core.detector import ZoneData
from zebtrack.utils.validation import validate_calibration

if TYPE_CHECKING:
    from zebtrack.settings import Settings

log = structlog.get_logger()


class Recorder:
    """
    Manages the recording of analysis data, including video and Parquet files.

    Supports context manager protocol for automatic file closure.
    Supports multi-aquarium mode for recording data from multiple aquariums
    simultaneously with separate output folders per aquarium.

    Example:
        recorder = Recorder(settings_obj=settings)
        with recorder:
            recorder.start_recording(...)
            recorder.write_detection_data(timestamp, frame_num, detections)
        # Files automatically closed and saved on exit

    Multi-aquarium Example:
        recorder = Recorder(settings_obj=settings)
        recorder.start_recording_multi_aquarium(
            output_folder="results/",
            width=1280,
            height=720,
            zones_by_aquarium={0: zone_data_0, 1: zone_data_1}
        )
        recorder.write_partitioned_detection_data(
            timestamp, frame_num,
            {0: detections_aq0, 1: detections_aq1}
        )
        recorder.stop_recording_multi_aquarium()
    """

    def __init__(self, settings_obj: "Settings | None" = None):
        """Initializes the recorder with its default state.

        Args:
            settings_obj: Settings instance (optional, uses defaults if None).
        """
        self.is_recording = False
        self.video_writer = None
        self.base_name = ""
        self.output_folder = ""
        self.start_time = 0
        self.frame_count = 0
        self.recording_start_frame = 0
        self.detection_data = []
        # BUG FIX #3: Use private attributes for protected properties
        self._pixel_per_cm_ratio = None
        self._calibration = None
        self._parquet_writer: pq.ParquetWriter | None = None
        self._parquet_schema: pa.Schema | None = None
        self._parquet_columns: list[str] = []
        self._initial_schema_columns: FrozenSet[str] | None = None  # noqa: UP006
        self._parquet_filename: str = ""
        self._last_flush_time: float = 0.0

        # Multi-aquarium support (Phase 7)
        self._multi_aquarium_mode: bool = False
        self._aquarium_recorders: dict[int, Recorder] = {}
        self._aquarium_id: int | None = None  # Set when this recorder is for a specific aquarium
        self._settings_obj = settings_obj  # Store for creating sub-recorders

        # Uncertainty tracking (Phase 1.2)
        self._last_detections_by_track: dict[int, tuple[float, float, float, float]] = {}

        # Pause/Resume support (v2.2.0) for camera disconnect recovery
        self._is_paused: bool = False
        self._pause_start_time: float | None = None
        self._total_paused_duration: float = 0.0

        # Extract settings with defaults
        self._fps = 30.0  # Default fps
        if settings_obj:
            recorder_settings = getattr(settings_obj, "recorder", None)
            performance_settings = getattr(settings_obj, "performance", None)

            self._flush_interval_seconds: float = float(
                getattr(recorder_settings, "flush_interval_seconds", 5.0)
                if recorder_settings
                else 5.0
            )
            self._flush_row_threshold: int = int(
                getattr(recorder_settings, "flush_row_threshold", 500) if recorder_settings else 500
            )

            # Phase 8: Performance settings for compression
            self._parquet_compression: str = str(
                getattr(performance_settings, "parquet_compression", "snappy")
                if performance_settings
                else "snappy"
            )

            # Store fps from settings
            if hasattr(settings_obj, "video_processing"):
                self._fps = float(getattr(settings_obj.video_processing, "fps", 30.0))
        else:
            # Use defaults if no settings provided
            self._flush_interval_seconds = 5.0
            self._flush_row_threshold = 500
            self._parquet_compression = "snappy"

    @property
    def pixel_per_cm_ratio(self):
        """Get pixel-to-cm calibration ratio."""
        return self._pixel_per_cm_ratio

    @pixel_per_cm_ratio.setter
    def pixel_per_cm_ratio(self, value):
        """
        Set pixel-to-cm calibration ratio.

        BUG FIX #3: Prevent calibration change during active recording to avoid
        schema inconsistencies in the Parquet file.
        """
        if self.is_recording and self._initial_schema_columns is not None:
            current_has_calib = "x_cm" in self._initial_schema_columns
            new_has_calib = value is not None

            if current_has_calib != new_has_calib:
                raise ValueError(
                    "Cannot change calibration during active recording "
                    "(Parquet schema would be inconsistent). Stop recording first."
                )

        self._pixel_per_cm_ratio = value

    @property
    def calibration(self):
        """Get calibration object."""
        return self._calibration

    @calibration.setter
    def calibration(self, value):
        """
        Set calibration object.

        BUG FIX #3: Prevent calibration change during active recording.
        """
        if self.is_recording and self._initial_schema_columns is not None:
            # Calibration change would affect coordinate transformation
            if (self._calibration is None) != (value is None):
                raise ValueError(
                    "Cannot add/remove calibration during active recording "
                    "(coordinate transformation would be inconsistent)."
                )

        self._calibration = value

    @staticmethod
    def _calculate_iou(
        box1: tuple[float, float, float, float],
        box2: tuple[float, float, float, float],
    ) -> float:
        """Calculate Intersection over Union between two bounding boxes.

        Args:
            box1: First bounding box (x1, y1, x2, y2).
            box2: Second bounding box (x1, y1, x2, y2).

        Returns:
            IoU value between 0.0 and 1.0.
        """
        # Calculate intersection
        x1_inter = max(box1[0], box2[0])
        y1_inter = max(box1[1], box2[1])
        x2_inter = min(box1[2], box2[2])
        y2_inter = min(box1[3], box2[3])

        inter_width = max(0, x2_inter - x1_inter)
        inter_height = max(0, y2_inter - y1_inter)
        inter_area = inter_width * inter_height

        # Calculate union
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union_area = area1 + area2 - inter_area

        if union_area <= 0:
            return 0.0

        return inter_area / union_area

    def start_recording(
        self,
        output_folder,
        frame_width,
        frame_height,
        zones: ZoneData,
        is_video_file=False,
        pixel_per_cm_ratio=None,
        base_name: str | None = None,
        calibration=None,
    ):
        """
        Prepares and starts a new recording session.

        Args:
            output_folder (str): The folder where files will be saved.
            frame_width (int): The width of the video frames.
            frame_height (int): The height of the video frames.
            zones (ZoneData): The zone definitions to save.
            is_video_file (bool): If True, skips video file creation.
            pixel_per_cm_ratio (tuple, optional): Tuple containing (x_ratio, y_ratio).
            base_name (str, optional): Explicit base name for output files.
                If None, it's derived from the output_folder.
            calibration (Calibration, optional): Calibration object for perspective
                transformation. Required to transform detection coordinates from
                original video space to warped space before saving.

        Returns:
            bool: True if recording started successfully, False otherwise.
        """
        validate_calibration(pixel_per_cm_ratio)
        if frame_width <= 0 or frame_height <= 0:
            log.error(
                "recorder.start.invalid_dimensions",
                frame_width=frame_width,
                frame_height=frame_height,
            )
            raise ValueError("frame_width and frame_height must be positive numbers")

        self.pixel_per_cm_ratio = pixel_per_cm_ratio
        self.calibration = calibration
        if self.is_recording:
            log.warning("recorder.start.already_recording")
            return False

        os.makedirs(output_folder, exist_ok=True)
        self.output_folder = output_folder
        self.base_name = base_name or os.path.basename(output_folder)
        self.detection_data = []
        log_context = log.bind(output_folder=output_folder, base_name=self.base_name)
        self._parquet_writer = None
        self._parquet_schema = None
        self._parquet_columns = self._determine_parquet_columns()
        self._initial_schema_columns = frozenset(self._parquet_columns)
        self._parquet_filename = os.path.join(
            self.output_folder, f"3_CoordMovimento_{self.base_name}.parquet"
        )
        self._last_flush_time = time.time()

        if not is_video_file:
            video_filename = os.path.join(output_folder, f"{self.base_name}.mp4")
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # type: ignore[attr-defined]
            self.video_writer = cv2.VideoWriter(
                video_filename,
                fourcc,
                self._fps,
                (frame_width, frame_height),
            )
            if not self.video_writer.isOpened():
                log.error("recorder.video_writer.open_error", path=video_filename)
                return False
        else:
            self.video_writer = None

        self._save_area_definitions(output_folder, zones)

        self.is_recording = True
        self.start_time = time.time()
        # Phase 1.2: Clear previous detection cache for new recording
        self._last_detections_by_track.clear()
        log_context.info("recorder.start.success")
        return True

    def pause_recording(self) -> bool:
        """Pause recording during camera disconnect.

        Prevents writing frames/detections until resumed.
        Tracks pause duration for metadata.

        Returns:
            True if paused successfully, False if not recording or already paused
        """
        if not self.is_recording:
            log.warning("recorder.pause.not_recording")
            return False

        if self._is_paused:
            log.warning("recorder.pause.already_paused")
            return False

        self._is_paused = True
        self._pause_start_time = time.time()

        log.info(
            "recorder.pause.success",
            base_name=self.base_name,
            frame_count=self.frame_count,
        )
        return True

    def resume_recording(self) -> bool:
        """Resume recording after camera reconnect.

        Accumulates pause duration and continues recording.

        Returns:
            True if resumed successfully, False if not paused
        """
        if not self._is_paused:
            log.warning("recorder.resume.not_paused")
            return False

        if self._pause_start_time is not None:
            pause_duration = time.time() - self._pause_start_time
            self._total_paused_duration += pause_duration

            log.info(
                "recorder.resume.success",
                base_name=self.base_name,
                pause_duration_s=f"{pause_duration:.1f}",
                total_paused_s=f"{self._total_paused_duration:.1f}",
            )

        self._is_paused = False
        self._pause_start_time = None
        return True

    def is_paused(self) -> bool:
        """Check if recorder is currently paused.

        Returns:
            True if paused
        """
        return self._is_paused

    def get_pause_metadata(self) -> dict:
        """Get pause/resume metadata for session report.

        Returns:
            Dict with pause statistics
        """
        return {
            "is_paused": self._is_paused,
            "total_paused_duration_s": self._total_paused_duration,
            "pause_start_time": self._pause_start_time,
        }

    def stop_recording(self, force_stop: bool = False, reason: str | None = None):
        """
        Stops the recording, releases file handlers, and saves tracking data.

        Args:
            force_stop (bool): If True, forces cleanup without saving data,
                               useful in an error state.
        """
        if not self.is_recording:
            return

        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None

        if not force_stop:
            self._save_detection_data()
        else:
            # If forcing stop due to an error, just close writers and clear buffers.
            self._close_parquet_writer()
            self.detection_data.clear()
            message = reason or "Error during recording."
            if reason and reason.lower().startswith("cancel"):
                log.info("recorder.stop.forced", reason=message)
            else:
                log.warning("recorder.stop.forced", reason=message)

        self.is_recording = False
        log.info("recorder.stop.success", base_name=self.base_name)

    # =========================================================================
    # Multi-Aquarium Recording Methods (Phase 7)
    # =========================================================================

    def start_recording_multi_aquarium(
        self,
        output_folder: str,
        width: int,
        height: int,
        zones_by_aquarium: dict[int, ZoneData],
        base_name: str | None = None,
        fps: float = 30.0,
        write_video: bool = True,
        pixel_per_cm_ratio: tuple[float, float] | None = None,
        calibration: Any = None,
        calibration_by_aquarium: dict[int, Any] | None = None,
        output_folders_by_aquarium: dict[int, str] | None = None,
    ) -> bool:
        """
        Start recording for multiple aquariums with separate output folders.

        Creates structure (default):
            output_folder/
            ├── aquarium_0/
            │   ├── 1_ProcessingArea_*.parquet
            │   ├── 2_AreasOfInterest_*.parquet
            │   └── 3_CoordMovimento_*.parquet
            └── aquarium_1/
                ├── 1_ProcessingArea_*.parquet
                ├── 2_AreasOfInterest_*.parquet
                └── 3_CoordMovimento_*.parquet

        Or with output_folders_by_aquarium (project structure):
            output_folders_by_aquarium[0]/  (e.g., Grupo_G1/Dia_D1/Sujeito_S01/)
            output_folders_by_aquarium[1]/  (e.g., Grupo_G1/Dia_D1/Sujeito_S02/)

        Args:
            output_folder: Base folder for all aquarium outputs (fallback).
            width: Frame width in pixels.
            height: Frame height in pixels.
            zones_by_aquarium: Dict mapping aquarium_id to ZoneData.
            base_name: Optional base name for output files.
            fps: Frames per second (default: 30.0).
            write_video: If True, also writes video files per aquarium.
            pixel_per_cm_ratio: Optional calibration ratio (x_ratio, y_ratio).
            calibration: Optional global calibration object (fallback).
            calibration_by_aquarium: Optional dict mapping aquarium_id to Calibration.
            output_folders_by_aquarium: Optional dict mapping aquarium_id to output folder path.
                If provided, uses these paths instead of creating aquarium_N subfolders.

        Returns:
            True if all recordings started successfully, False otherwise.
        """
        if self.is_recording or self._multi_aquarium_mode:
            log.warning("recorder.multi_aquarium.already_recording")
            return False

        if len(zones_by_aquarium) > 2:
            log.error(
                "recorder.multi_aquarium.max_exceeded",
                count=len(zones_by_aquarium),
                max_allowed=2,
            )
            return False

        self._multi_aquarium_mode = True
        base_folder = Path(output_folder)
        base_folder.mkdir(parents=True, exist_ok=True)

        for aq_id, zone_data in zones_by_aquarium.items():
            # Use custom output folder if provided, otherwise use default aquarium_N subfolder
            if output_folders_by_aquarium and aq_id in output_folders_by_aquarium:
                aq_folder = Path(output_folders_by_aquarium[aq_id])
                log.info(
                    "recorder.multi_aquarium.using_custom_folder",
                    aquarium_id=aq_id,
                    folder=str(aq_folder),
                )
            else:
                aq_folder = base_folder / f"aquarium_{aq_id}"
            aq_folder.mkdir(parents=True, exist_ok=True)

            # Create sub-recorder for this aquarium
            aq_recorder = Recorder(settings_obj=self._settings_obj)
            aq_recorder._aquarium_id = aq_id  # Mark this recorder for specific aquarium
            aq_recorder._fps = fps

            # Construct base name for sub-recorder
            aq_base_name = f"{base_name}_aquarium_{aq_id}" if base_name else f"aquarium_{aq_id}"

            # Determine calibration for this aquarium
            aq_calibration = calibration
            aq_ratio = pixel_per_cm_ratio

            if calibration_by_aquarium and aq_id in calibration_by_aquarium:
                aq_calibration = calibration_by_aquarium[aq_id]
                if hasattr(aq_calibration, "pixel_per_cm_ratio"):
                    aq_ratio = aq_calibration.pixel_per_cm_ratio

            try:
                success = aq_recorder.start_recording(
                    output_folder=str(aq_folder),
                    frame_width=width,
                    frame_height=height,
                    zones=zone_data,
                    is_video_file=not write_video,
                    pixel_per_cm_ratio=aq_ratio,
                    base_name=aq_base_name,
                    calibration=aq_calibration,
                )

                if success:
                    self._aquarium_recorders[aq_id] = aq_recorder
                    log.info(
                        "recorder.multi_aquarium.recorder_started",
                        aquarium_id=aq_id,
                        folder=str(aq_folder),
                    )
                else:
                    log.error(
                        "recorder.multi_aquarium.recorder_failed",
                        aquarium_id=aq_id,
                    )
                    # Cleanup already started recorders
                    self._cleanup_aquarium_recorders()
                    return False

            except Exception as e:
                log.error(
                    "recorder.multi_aquarium.recorder_error",
                    aquarium_id=aq_id,
                    error=str(e),
                    exc_info=True,
                )
                self._cleanup_aquarium_recorders()
                return False

        log.info(
            "recorder.multi_aquarium.started",
            aquarium_count=len(self._aquarium_recorders),
            output_folder=str(base_folder),
        )
        return True

    def write_partitioned_detection_data(
        self,
        timestamp: float,
        frame_number: int,
        partitioned_detections: dict[int, list[tuple]],
    ) -> None:
        """
        Write detection data partitioned by aquarium.

        Args:
            timestamp: Current timestamp in seconds.
            frame_number: Current frame number.
            partitioned_detections: Dict mapping aquarium_id to list of detections.
                Each detection is a tuple of (x1, y1, x2, y2, conf, track_id, class_id).

        Raises:
            RuntimeError: If not in multi-aquarium mode.
        """
        if not self._multi_aquarium_mode:
            raise RuntimeError("Recorder not in multi-aquarium mode")

        for aq_id, detections in partitioned_detections.items():
            if aq_id in self._aquarium_recorders:
                recorder = self._aquarium_recorders[aq_id]
                recorder.write_detection_data(timestamp, frame_number, detections)
            else:
                log.warning(
                    "recorder.multi_aquarium.unknown_aquarium",
                    aquarium_id=aq_id,
                    known_ids=list(self._aquarium_recorders.keys()),
                )

    def write_video_frame_multi_aquarium(
        self,
        aquarium_id: int,
        frame: np.ndarray,
    ) -> None:
        """
        Write a video frame for a specific aquarium.

        Args:
            aquarium_id: The aquarium ID to write the frame for.
            frame: The video frame to write.
        """
        if not self._multi_aquarium_mode:
            log.warning("recorder.multi_aquarium.write_frame.not_active")
            return

        if aquarium_id in self._aquarium_recorders:
            self._aquarium_recorders[aquarium_id].write_video_frame(frame)

    def stop_recording_multi_aquarium(self, force_stop: bool = False) -> None:
        """
        Stop recording for all aquariums.

        Args:
            force_stop: If True, forces cleanup without saving data.
        """
        if not self._multi_aquarium_mode:
            log.warning("recorder.multi_aquarium.stop.not_active")
            return

        for aq_id, recorder in list(self._aquarium_recorders.items()):
            try:
                recorder.stop_recording(force_stop=force_stop)
                log.info(
                    "recorder.multi_aquarium.recorder_stopped",
                    aquarium_id=aq_id,
                )
            except Exception as e:
                log.error(
                    "recorder.multi_aquarium.stop_failed",
                    aquarium_id=aq_id,
                    error=str(e),
                    exc_info=True,
                )

        self._aquarium_recorders.clear()
        self._multi_aquarium_mode = False
        log.info("recorder.multi_aquarium.stopped")

    def is_multi_aquarium_mode(self) -> bool:
        """Check if recorder is in multi-aquarium mode."""
        return self._multi_aquarium_mode

    def get_aquarium_recorders(self) -> dict[int, "Recorder"]:
        """Get all aquarium recorders (for testing/debugging)."""
        return self._aquarium_recorders.copy()

    def _cleanup_aquarium_recorders(self) -> None:
        """Cleanup all aquarium recorders on error."""
        for aq_id, recorder in list(self._aquarium_recorders.items()):
            try:
                recorder.stop_recording(force_stop=True, reason="Cleanup on error")
            except Exception:
                pass  # Best effort cleanup
        self._aquarium_recorders.clear()
        self._multi_aquarium_mode = False

    # =========================================================================
    # Standard Recording Methods
    # =========================================================================

    def write_video_frame(self, frame):
        """Writes a single frame to the video file."""
        # Skip writing if paused (camera disconnected)
        if self._is_paused:
            return

        if self.is_recording and self.video_writer:
            self.video_writer.write(frame)

    def write_detection_data(self, timestamp, frame_number, detections):
        """Appends detection data to an in-memory list."""
        if not self.is_recording:
            log.warning(
                "recorder.write_detection_data.not_recording",
                frame=frame_number,
                num_detections=len(detections),
            )
            return

        # Skip writing if paused (camera disconnected)
        if self._is_paused:
            log.debug(
                "recorder.write_detection_data.paused",
                frame=frame_number,
                num_detections=len(detections),
            )
            return

        # 🔍 INFO: Log incoming detection data
        log.debug(
            "recorder.write_detection_data.start",
            frame=frame_number,
            num_detections=len(detections),
            buffer_size_before=len(self.detection_data),
        )

        for detection in detections:
            # Support both 6-element (old) and 7-element (new) tuples
            if len(detection) == 6:
                x1, y1, x2, y2, confidence, track_id = detection
            else:
                x1, y1, x2, y2, confidence, track_id, _class_id = detection
            normalised_track = self._normalise_track_id(track_id)
            # Transform coordinates from original video space to warped space
            # This aligns with COORDINATE_SYSTEMS.md: Original → Warped → CM
            if self.calibration:
                x1, y1, x2, y2 = self.calibration.transform_bbox(x1, y1, x2, y2)
                # Now coordinates are in warped space (e.g., 600×266 px)

            data_point = {
                "timestamp": timestamp,
                "frame": frame_number,
                "track_id": normalised_track,
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "confidence": confidence,
            }

            # Phase 1.2: Add uncertainty metrics
            # Uncertainty = 1 - confidence (higher = less certain)
            data_point["uncertainty"] = 1.0 - float(confidence)

            # Calculate bbox IoU with previous detection for same track
            current_bbox = (float(x1), float(y1), float(x2), float(y2))
            if normalised_track is not None:
                prev_bbox = self._last_detections_by_track.get(normalised_track)
                if prev_bbox is not None:
                    data_point["bbox_iou"] = self._calculate_iou(prev_bbox, current_bbox)
                else:
                    data_point["bbox_iou"] = 1.0  # First detection, assume stable
                # Update last detection for this track
                self._last_detections_by_track[normalised_track] = current_bbox
            else:
                data_point["bbox_iou"] = None

            # Add aquarium_id if this is an aquarium-specific recorder
            if self._aquarium_id is not None:
                data_point["aquarium_id"] = self._aquarium_id

            # Calculate center point and add cm conversion if ratio is available
            x_center = (x1 + x2) / 2
            y_center = (y1 + y2) / 2
            data_point["x_center_px"] = x_center
            data_point["y_center_px"] = y_center
            if self.pixel_per_cm_ratio:
                # Convert warped pixels to cm using the configured ratio
                data_point["x_cm"] = x_center / self.pixel_per_cm_ratio[0]
                data_point["y_cm"] = y_center / self.pixel_per_cm_ratio[1]

            self.detection_data.append(data_point)

        # 🔍 INFO: Log buffer state after append (changed from DEBUG to INFO)
        log.debug(
            "recorder.detections.appended",
            count=len(detections),
            frame=frame_number,
            buffer_size_after=len(self.detection_data),
        )

        self._flush_detection_data()

    @staticmethod
    def _normalise_track_id(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, (np.integer, int)):
            return int(value)
        if isinstance(value, (float, np.floating)):
            if np.isnan(value):  # type: ignore[arg-type]
                return None
            return int(value)
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            try:
                return int(float(stripped))
            except ValueError:
                return None
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    def _determine_parquet_columns(self, include_aquarium_id: bool = False) -> list[str]:
        """Determine columns for Parquet schema.

        Args:
            include_aquarium_id: If True, includes aquarium_id column after track_id.

        Returns:
            List of column names.
        """
        columns = [
            "timestamp",
            "frame",
            "track_id",
        ]

        # Add aquarium_id for multi-aquarium mode
        if include_aquarium_id or self._aquarium_id is not None:
            columns.append("aquarium_id")

        columns.extend(
            [
                "x1",
                "y1",
                "x2",
                "y2",
                "confidence",
                "uncertainty",  # Phase 1.2: 1 - confidence
                "bbox_iou",  # Phase 1.2: IoU with previous detection
                "x_center_px",
                "y_center_px",
            ]
        )

        if self.pixel_per_cm_ratio:
            columns.extend(
                [
                    "x_cm",
                    "y_cm",
                ]
            )
        return columns

    def _validate_unique_detections(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Remove duplicate detections (same frame + track_id).

        BUG FIX #2: Prevents inflated metrics caused by duplicate detections
        of the same object in the same frame, which can occur due to ByteTracker
        errors or model issues.

        Args:
            df: DataFrame with detection data

        Returns:
            DataFrame with duplicates removed (keeps first occurrence)
        """
        if df.empty:
            return df

        # Check if required columns exist
        if "frame" not in df.columns or "track_id" not in df.columns:
            log.warning(
                "recorder.duplicate_check_skipped",
                reason="missing_columns",
                available_columns=list(df.columns),
            )
            return df

        # Identify duplicates
        duplicates = df.duplicated(subset=["frame", "track_id"], keep="first")
        num_duplicates = duplicates.sum()

        if num_duplicates > 0:
            # Get some examples for logging
            duplicate_examples = df[duplicates][["frame", "track_id"]].head(5).to_dict("records")

            log.warning(
                "recorder.duplicate_detections_removed",
                count=int(num_duplicates),
                total_rows=len(df),
                percentage=f"{(num_duplicates / len(df)) * 100:.2f}%",
                examples=duplicate_examples,
                message=(
                    "Duplicate detections detected and removed. "
                    "This may indicate ByteTracker issues or model problems."
                ),
            )

            # Remove duplicates
            df = df[~duplicates].copy()

        return df

    def _should_flush(self) -> bool:
        if not self.detection_data:
            return False
        if self._flush_row_threshold > 0 and len(self.detection_data) >= self._flush_row_threshold:
            return True
        if self._flush_interval_seconds <= 0:
            return False
        return (time.time() - self._last_flush_time) >= self._flush_interval_seconds

    def _flush_detection_data(self, force: bool = False) -> None:
        # 🔍 INFO: Log flush attempt
        log.debug(
            "recorder.flush.attempt",
            buffer_size=len(self.detection_data),
            force=force,
            should_flush=self._should_flush() if not force else True,
        )

        if not self.detection_data:
            log.debug("recorder.flush.skipped_empty_buffer")
            return
        if not force and not self._should_flush():
            log.debug(
                "recorder.flush.skipped_threshold",
                buffer_size=len(self.detection_data),
                threshold=self._flush_row_threshold,
            )
            return

        try:
            current_cols = set(self._determine_parquet_columns())
            schema_is_defined = self._initial_schema_columns is not None
            schema_has_changed = current_cols != self._initial_schema_columns

            if schema_is_defined and schema_has_changed:
                log.error(
                    "recorder.schema_mismatch",
                    initial=self._initial_schema_columns,
                    current=current_cols,
                )
                raise ValueError("Parquet schema cannot change during recording")

            df = pd.DataFrame(self.detection_data)
            if df.empty:
                self.detection_data.clear()
                self._last_flush_time = time.time()
                log.info("recorder.flush.skipped_empty_dataframe")
                return

            # BUG FIX #2: Remove duplicate detections (same frame + track_id)
            df = self._validate_unique_detections(df)

            if not self._parquet_columns:
                self._parquet_columns = self._determine_parquet_columns()

            df = df.reindex(columns=self._parquet_columns)

            if self._parquet_schema is None:
                table = pa.Table.from_pandas(df, preserve_index=False)
                self._parquet_schema = table.schema
                self._parquet_writer = pq.ParquetWriter(
                    self._parquet_filename,
                    self._parquet_schema,
                    compression=self._parquet_compression,
                )
                log.info(
                    "recorder.parquet_writer.created",
                    path=self._parquet_filename,
                    schema=str(self._parquet_schema),
                )
            else:
                table = pa.Table.from_pandas(df, schema=self._parquet_schema, preserve_index=False)
                if self._parquet_writer is None:
                    self._parquet_writer = pq.ParquetWriter(
                        self._parquet_filename,
                        self._parquet_schema,
                        compression=self._parquet_compression,
                    )

            assert self._parquet_writer is not None
            self._parquet_writer.write_table(table)
            self.detection_data.clear()
            self._last_flush_time = time.time()
            # Log flush success (debug level - only goes to file, not terminal)
            log.debug(
                "recorder.flush.success",
                rows=table.num_rows,
                force=force,
                path=self._parquet_filename,
            )
        except ValueError as e:
            # Critical error, stop recording to clean up resources
            log.error("recorder.flush.critical_error", exc_info=e)
            self.stop_recording(force_stop=True)
            raise  # Re-raise the exception to notify the caller
        except Exception as e:  # pragma: no cover - unexpected failures logged
            log.error(
                "recorder.flush.error",
                path=self._parquet_filename,
                exc_info=e,
            )

    def _close_parquet_writer(self) -> None:
        if self._parquet_writer is None:
            return
        try:
            # Close the writer (this handles file closure internally)
            self._parquet_writer.close()
            log.info("recorder.parquet_writer.closed", path=self._parquet_filename)
        except Exception as e:  # pragma: no cover - best effort close
            log.error(
                "recorder.parquet_writer.close_error",
                path=self._parquet_filename,
                exc_info=e,
            )
        finally:
            self._parquet_writer = None
            self._parquet_schema = None
            self._parquet_columns = []

    def _save_detection_data(self):
        """Saves the collected detection data to a Parquet file."""
        if not self.detection_data and self._parquet_writer is None:
            if not self._parquet_filename:
                log.info("recorder.save_parquet.no_data")
                return

            # Create an empty Parquet file so downstream consumers find the expected schema
            empty_columns = self._parquet_columns or self._determine_parquet_columns()
            empty_df = pd.DataFrame(columns=empty_columns)
            try:
                table = pa.Table.from_pandas(empty_df, preserve_index=False)
                pq.write_table(table, self._parquet_filename, compression=self._parquet_compression)
                log.info(
                    "recorder.save_parquet.empty",
                    path=self._parquet_filename,
                )
            except Exception as e:
                log.error(
                    "recorder.save_parquet.error",
                    path=self._parquet_filename,
                    exc_info=e,
                )
                # Task 2.1: Log failure to create empty parquet
                # Not critical since no data to lose, but warns user
                log.warning(
                    "recorder.empty_parquet.failed",
                    message="Could not create empty Parquet file, but no data was lost",
                )
            finally:
                self.detection_data.clear()
                self._parquet_columns = []
                self._parquet_schema = None
                self._parquet_filename = ""
            return

        self._flush_detection_data(force=True)

        if self._parquet_writer:
            parquet_path = self._parquet_filename
            self._close_parquet_writer()
            log.info("recorder.save_parquet.success", path=parquet_path)
            self._parquet_filename = ""
            return

        if self.detection_data:
            parquet_path = self._parquet_filename
            try:
                df = pd.DataFrame(self.detection_data)
                if df.empty:
                    log.info("recorder.save_parquet.no_data")
                else:
                    df = df.reindex(
                        columns=self._parquet_columns or self._determine_parquet_columns()
                    )
                    table = pa.Table.from_pandas(df, preserve_index=False)
                    # Phase 8: Use configured compression
                    pq.write_table(table, parquet_path, compression=self._parquet_compression)
                    log.info("recorder.save_parquet.success", path=parquet_path)
            except Exception as e:
                log.error(
                    "recorder.save_parquet.error",
                    path=parquet_path,
                    exc_info=e,
                )
                # Task 2.1: Backup data to JSON when Parquet save fails
                # This prevents data loss and allows recovery
                backup_path = parquet_path.replace(".parquet", "_BACKUP.json")
                try:
                    import json

                    with open(backup_path, "w", encoding="utf-8") as f:
                        json.dump(self.detection_data, f, indent=2, default=str)
                    log.warning(
                        "recorder.backup.saved",
                        path=backup_path,
                        rows=len(self.detection_data),
                        message=(
                            "Detection data backed up to JSON. "
                            "You can manually convert this to Parquet if needed."
                        ),
                    )
                except Exception as backup_error:
                    log.critical(
                        "recorder.backup.failed",
                        backup_path=backup_path,
                        error=str(backup_error),
                        message="Failed to save backup - DATA MAY BE LOST",
                        exc_info=True,
                    )
                # Re-raise original error after backup attempt
                raise
            finally:
                self.detection_data.clear()
                self._parquet_columns = []
                self._parquet_schema = None
                self._parquet_filename = ""
            return

        log.info("recorder.save_parquet.no_data")

    def _save_area_definitions(self, folder_path: Path | str, zones: ZoneData):
        """Saves processing and interest area definitions to Parquet files."""
        folder_path = Path(folder_path) if isinstance(folder_path, str) else folder_path
        # Save processing area
        processing_area_filename = folder_path / f"1_ProcessingArea_{self.base_name}.parquet"
        try:
            processing_df = pd.DataFrame(zones.polygon, columns=["x", "y"])
            table = pa.Table.from_pandas(processing_df)
            # Phase 8: Use configured compression
            pq.write_table(table, processing_area_filename, compression=self._parquet_compression)
            log.info("recorder.save_processing_area.success", path=processing_area_filename)
        except Exception as e:
            log.error(
                "recorder.save_processing_area.error",
                path=processing_area_filename,
                exc_info=e,
            )

        # Save areas of interest (polygons)
        areas_of_interest_filename = folder_path / f"2_AreasOfInterest_{self.base_name}.parquet"
        try:
            poly_data = []
            for i, polygon_points in enumerate(zones.roi_polygons):
                roi_name = zones.roi_names[i] if i < len(zones.roi_names) else f"ROI_{i + 1}"
                for j, (x, y) in enumerate(polygon_points):
                    poly_data.append([roi_name, j, x, y])

            if poly_data:
                areas_df = pd.DataFrame(poly_data, columns=["roi_name", "point_index", "x", "y"])
                table = pa.Table.from_pandas(areas_df)
                # Phase 8: Use configured compression
                pq.write_table(
                    table, areas_of_interest_filename, compression=self._parquet_compression
                )
                log.info(
                    "recorder.save_areas_of_interest.success",
                    path=areas_of_interest_filename,
                )
        except Exception as e:
            log.error(
                "recorder.save_areas_of_interest.error",
                path=areas_of_interest_filename,
                exc_info=e,
            )

        log.info("recorder.area_definitions.saved", path=folder_path)

    def __enter__(self) -> "Recorder":
        """Enter context manager."""
        # Resources are managed by start_recording/stop_recording
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        """
        Exit context manager - close all files and save data.

        Args:
            exc_type: Exception type if raised
            exc_val: Exception value if raised
            exc_tb: Exception traceback if raised

        Returns:
            False to propagate exceptions
        """
        try:
            if self.is_recording:
                # If exception occurred, force stop without saving
                if exc_type is not None:
                    self.stop_recording(force_stop=True, reason=f"Exception: {exc_val}")
                else:
                    # Normal cleanup
                    self.stop_recording()
        except Exception as e:
            log.error("recorder.cleanup.failed", error=str(e))
        return False  # Don't suppress exceptions


if __name__ == "__main__":
    # Example usage for testing the Recorder module
    # Note: Use pytest for proper testing - this is for quick manual verification only
    import logging

    logging.basicConfig(level=logging.INFO)
    _test_log = logging.getLogger(__name__)

    _test_log.info("Testing Recorder module...")

    # Dummy data
    test_output_dir = "test_project/group1_cobaia1"
    frame_width, frame_height = 640, 480

    # Create a dummy frame
    dummy_frame = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)

    recorder = Recorder()

    # Test start recording
    mock_zones = ZoneData()
    success = recorder.start_recording(test_output_dir, frame_width, frame_height, zones=mock_zones)

    if success:
        _test_log.info("Recording started successfully.")

        # Test writing data
        recorder.recording_start_frame = 100
        for i in range(10):
            frame_num = 100 + i
            cv2.putText(
                dummy_frame,
                f"Frame {frame_num}",
                (50, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (255, 255, 255),
                2,
            )
            recorder.write_video_frame(dummy_frame)

            if i % 2 == 0:
                # Add a dummy track_id for testing purposes
                detections = [(100 + i, 150, 200 + i, 250, 0.95, 1)]
                recorder.write_detection_data(time.time(), frame_num, detections)

            time.sleep(0.1)

        _test_log.info("Finished writing test data.")

        # Test stop recording
        recorder.stop_recording()

        _test_log.info("Check '%s' directory for output files.", test_output_dir)

    else:
        _test_log.warning("Failed to start recording.")

    _test_log.info("Recorder test finished.")
