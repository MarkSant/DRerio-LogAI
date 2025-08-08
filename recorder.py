import os
import cv2
import csv
import time
from datetime import datetime
import config

class Recorder:
    def __init__(self):
        self.is_recording = False
        self.video_writer = None
        self.csv_writer = None
        self.csv_file = None
        self.base_name = ""
        self.start_time = 0
        self.frame_count = 0
        self.recording_start_frame = 0

    def start_recording(self, output_folder, frame_width, frame_height):
        """
        Initializes video and CSV recording.
        """
        if self.is_recording:
            print("Already recording.")
            return False

        # Create the full path for the output folder if it doesn't exist
        os.makedirs(output_folder, exist_ok=True)

        self.base_name = os.path.basename(output_folder)

        # 1. Setup Video Writer
        video_filename = os.path.join(output_folder, f"{self.base_name}.mp4")
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.video_writer = cv2.VideoWriter(video_filename, fourcc, config.FPS, (frame_width, frame_height))
        if not self.video_writer.isOpened():
            print(f"Error: Could not open video writer for {video_filename}")
            return False

        # 2. Setup CSV Writer for movement data
        csv_filename = os.path.join(output_folder, f"3_CoordMovimento_{self.base_name}.csv")
        try:
            self.csv_file = open(csv_filename, 'w', newline='')
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(['timestamp', 'frame', 'x1', 'y1', 'x2', 'y2', 'confidence'])
        except IOError as e:
            print(f"Error: Could not open CSV file {csv_filename}. {e}")
            self.video_writer.release() # clean up video writer
            return False

        # 3. Save area definitions
        self._save_area_definitions(output_folder)

        self.is_recording = True
        self.start_time = time.time()
        print(f"Started recording. Output folder: {output_folder}")
        return True

    def stop_recording(self):
        """
        Stops the recording and releases all file handlers.
        """
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
        print(f"Stopped recording for {self.base_name}.")

    def write_video_frame(self, frame):
        if self.is_recording and self.video_writer:
            self.video_writer.write(frame)

    def write_detection_data(self, timestamp, frame_number, detections):
        """
        Writes a row of detection data to the CSV file.
        Timestamp and frame_number are now passed in directly.
        """
        if self.is_recording and self.csv_writer:
            for (x1, y1, x2, y2, confidence) in detections:
                self.csv_writer.writerow([f"{timestamp:.4f}", frame_number, x1, y1, x2, y2, int(confidence * 100)])

    def _save_area_definitions(self, folder_path):
        """
        Saves the processing area and areas of interest to CSV files.
        """
        # Save Processing Area (Polygon)
        processing_area_filename = os.path.join(folder_path, f"1_ProcessingArea_{self.base_name}.csv")
        with open(processing_area_filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['x', 'y'])
            writer.writerows(config.POLYGON)

        # Save Areas of Interest (Squares)
        areas_of_interest_filename = os.path.join(folder_path, f"2_AreasOfInterest_{self.base_name}.csv")
        with open(areas_of_interest_filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['area', 'x1', 'y1', 'x2', 'y2'])
            for i, ((x1, y1), (x2, y2)) in enumerate(config.SQUARES):
                writer.writerow([f'Area {i+1}', x1, y1, x2, y2])

        print(f"Saved area definitions to {folder_path}")

if __name__ == '__main__':
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
        recorder.recording_start_frame = 100 # Simulate starting mid-stream
        for i in range(10): # Simulate 10 frames
            frame_num = 100 + i
            # Add some changing element to the frame
            cv2.putText(dummy_frame, f"Frame {frame_num}", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            recorder.write_video_frame(dummy_frame)

            # Simulate a detection
            if i % 2 == 0:
                detections = [(100+i, 150, 200+i, 250, 0.95)]
                recorder.write_detection_data(frame_num, detections)

            time.sleep(0.1)

        print("\nFinished writing test data.")

        # Test stop recording
        recorder.stop_recording()

        print(f"\nCheck the '{test_output_dir}' directory for output files.")

    else:
        print("\nFailed to start recording.")

    print("\nRecorder test finished.")
