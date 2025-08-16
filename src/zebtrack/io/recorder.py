import csv
import os
import time

import cv2
import numpy as np
import structlog

from zebtrack.settings import settings

log = structlog.get_logger()


class Recorder:
    """
    Manages the recording of analysis data, including video and CSV files.
    """

    def __init__(self):
        """Initializes the recorder with its default state."""
        self.is_recording = False
        self.video_writer = None
        self.csv_writer = None
        self.csv_file = None
        self.base_name = ""
        self.start_time = 0
        self.frame_count = 0
        self.recording_start_frame = 0

    def start_recording(
        self, output_folder, frame_width, frame_height, is_video_file=False
    ):
        """
        Prepares and starts a new recording session.

        Args:
            output_folder (str): The folder where files will be saved.
            frame_width (int): The width of the video frames.
            frame_height (int): The height of the video frames.
            is_video_file (bool): If True, skips video file creation.

        Returns:
            bool: True if recording started successfully, False otherwise.
        """
        if self.is_recording:
            log.warning("recorder.start.already_recording")
            return False

        os.makedirs(output_folder, exist_ok=True)
        self.base_name = os.path.basename(output_folder)
        log_context = log.bind(
            output_folder=output_folder, base_name=self.base_name
        )

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

        csv_filename = os.path.join(
            output_folder, f"3_CoordMovimento_{self.base_name}.csv"
        )
        try:
            self.csv_file = open(csv_filename, "w", newline="")
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(
                ["timestamp", "frame", "x1", "y1", "x2", "y2", "confidence"]
            )
            self.csv_file.flush()
        except IOError as e:
            log.error("recorder.csv.open_error", path=csv_filename, exc_info=e)
            if self.video_writer:
                self.video_writer.release()
            return False

        self._save_area_definitions(output_folder)

        self.is_recording = True
        self.start_time = time.time()
        log_context.info("recorder.start.success")
        return True

    def stop_recording(self):
        """Stops the recording and releases all file handlers."""
        if not self.is_recording:
            return

        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None

        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
            self.csv_writer = None

        self.is_recording = False
        log.info("recorder.stop.success", base_name=self.base_name)

    def write_video_frame(self, frame):
        """Writes a single frame to the video file."""
        if self.is_recording and self.video_writer:
            self.video_writer.write(frame)

    def write_detection_data(self, timestamp, frame_number, detections):
        """Writes detection data to the CSV file."""
        if self.is_recording and self.csv_writer:
            for x1, y1, x2, y2, confidence in detections:
                self.csv_writer.writerow(
                    [
                        f"{timestamp:.4f}",
                        frame_number,
                        x1,
                        y1,
                        x2,
                        y2,
                        int(confidence * 100),
                    ]
                )
            self.csv_file.flush()
            log.debug(
                "recorder.detections.wrote",
                count=len(detections),
                frame=frame_number,
            )

    def _save_area_definitions(self, folder_path):
        """Saves processing and interest area definitions to CSVs."""
        processing_area_filename = os.path.join(
            folder_path, f"1_ProcessingArea_{self.base_name}.csv"
        )
        with open(processing_area_filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["x", "y"])
            writer.writerows(settings.detection_zones.polygon)
            f.flush()
            os.fsync(f.fileno())

        areas_of_interest_filename = os.path.join(
            folder_path, f"2_AreasOfInterest_{self.base_name}.csv"
        )
        with open(areas_of_interest_filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["area", "x1", "y1", "x2", "y2"])
            for i, ((x1, y1), (x2, y2)) in enumerate(settings.detection_zones.squares):
                writer.writerow([f"Area {i + 1}", x1, y1, x2, y2])
            f.flush()
            os.fsync(f.fileno())

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
                detections = [(100 + i, 150, 200 + i, 250, 0.95)]
                recorder.write_detection_data(time.time(), frame_num, detections)

            time.sleep(0.1)

        print("\nFinished writing test data.")

        # Test stop recording
        recorder.stop_recording()

        print(f"\nCheck the '{test_output_dir}' directory for output files.")

    else:
        print("\nFailed to start recording.")

    print("\nRecorder test finished.")
