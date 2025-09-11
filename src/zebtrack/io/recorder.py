import os
import time

import cv2
import numpy as np
import pandas as pd
import pyarrow as pa
import structlog
from pyarrow import parquet as pq

from zebtrack.core.detector import ZoneData
from zebtrack.settings import settings

log = structlog.get_logger()


class Recorder:
    """
    Manages the recording of analysis data, including video and Parquet files.
    """

    def __init__(self):
        """Initializes the recorder with its default state."""
        self.is_recording = False
        self.video_writer = None
        self.base_name = ""
        self.output_folder = ""
        self.start_time = 0
        self.frame_count = 0
        self.recording_start_frame = 0
        self.detection_data = []
        self.pixel_per_cm_ratio = None

    def start_recording(
        self,
        output_folder,
        frame_width,
        frame_height,
        zones: ZoneData,
        is_video_file=False,
        pixel_per_cm_ratio=None,
        base_name: str | None = None,
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

        Returns:
            bool: True if recording started successfully, False otherwise.
        """
        self.pixel_per_cm_ratio = pixel_per_cm_ratio
        if self.is_recording:
            log.warning("recorder.start.already_recording")
            return False

        os.makedirs(output_folder, exist_ok=True)
        self.output_folder = output_folder
        self.base_name = base_name or os.path.basename(output_folder)
        self.detection_data = []
        log_context = log.bind(output_folder=output_folder, base_name=self.base_name)

        if not is_video_file:
            video_filename = os.path.join(output_folder, f"{self.base_name}.mp4")
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self.video_writer = cv2.VideoWriter(
                video_filename,
                fourcc,
                settings.video_processing.fps,
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
        log_context.info("recorder.start.success")
        return True

    def stop_recording(self):
        """Stops the recording, releases file handlers, and saves tracking data."""
        if not self.is_recording:
            return

        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None

        self._save_detection_data()

        self.is_recording = False
        log.info("recorder.stop.success", base_name=self.base_name)

    def write_video_frame(self, frame):
        """Writes a single frame to the video file."""
        if self.is_recording and self.video_writer:
            self.video_writer.write(frame)

    def write_detection_data(self, timestamp, frame_number, detections):
        """Appends detection data to an in-memory list."""
        if not self.is_recording:
            return

        for x1, y1, x2, y2, confidence, track_id in detections:
            data_point = {
                "timestamp": timestamp,
                "frame": frame_number,
                "track_id": track_id,
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "confidence": confidence,
            }
            # Calculate center point and add cm conversion if ratio is available
            if self.pixel_per_cm_ratio:
                x_center = (x1 + x2) / 2
                y_center = (y1 + y2) / 2
                data_point["x_center_px"] = x_center
                data_point["y_center_px"] = y_center
                data_point["x_cm"] = x_center / self.pixel_per_cm_ratio[0]
                data_point["y_cm"] = y_center / self.pixel_per_cm_ratio[1]

            self.detection_data.append(data_point)
        log.debug(
            "recorder.detections.appended",
            count=len(detections),
            frame=frame_number,
        )

    def _save_detection_data(self):
        """Saves the collected detection data to a Parquet file."""
        if not self.detection_data:
            log.info("recorder.save_parquet.no_data")
            return

        parquet_filename = os.path.join(
            self.output_folder, f"3_CoordMovimento_{self.base_name}.parquet"
        )
        try:
            df = pd.DataFrame(self.detection_data)
            table = pa.Table.from_pandas(df)
            pq.write_table(table, parquet_filename)
            log.info("recorder.save_parquet.success", path=parquet_filename)
        except Exception as e:
            log.error("recorder.save_parquet.error", path=parquet_filename, exc_info=e)

    def _save_area_definitions(self, folder_path: str, zones: ZoneData):
        """Saves processing and interest area definitions to Parquet files."""
        # Save processing area
        processing_area_filename = os.path.join(
            folder_path, f"1_ProcessingArea_{self.base_name}.parquet"
        )
        try:
            processing_df = pd.DataFrame(zones.polygon, columns=["x", "y"])
            table = pa.Table.from_pandas(processing_df)
            pq.write_table(table, processing_area_filename)
            log.info(
                "recorder.save_processing_area.success", path=processing_area_filename
            )
        except Exception as e:
            log.error(
                "recorder.save_processing_area.error",
                path=processing_area_filename,
                exc_info=e,
            )

        # Save areas of interest (polygons)
        areas_of_interest_filename = os.path.join(
            folder_path, f"2_AreasOfInterest_{self.base_name}.parquet"
        )
        try:
            poly_data = []
            for i, polygon_points in enumerate(zones.roi_polygons):
                roi_name = zones.roi_names[i] if i < len(zones.roi_names) else f"ROI_{i+1}"
                for j, (x, y) in enumerate(polygon_points):
                    poly_data.append([roi_name, j, x, y])

            if poly_data:
                areas_df = pd.DataFrame(
                    poly_data, columns=["roi_name", "point_index", "x", "y"]
                )
                table = pa.Table.from_pandas(areas_df)
                pq.write_table(table, areas_of_interest_filename)
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


if __name__ == "__main__":
    # Example usage for testing the Recorder module
    print("Testing Recorder module...")

    # Dummy data
    test_output_dir = "test_project/group1_cobaia1"
    frame_width, frame_height = 640, 480

    # Create a dummy frame
    dummy_frame = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)

    recorder = Recorder()

    # Test start recording
    success = recorder.start_recording(test_output_dir, frame_width, frame_height)

    if success:
        print("\nRecording started successfully.")

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

        print("\nFinished writing test data.")

        # Test stop recording
        recorder.stop_recording()

        print(f"\nCheck the '{test_output_dir}' directory for output files.")

    else:
        print("\nFailed to start recording.")

    print("\nRecorder test finished.")
