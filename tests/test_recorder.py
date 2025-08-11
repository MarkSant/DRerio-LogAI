import unittest
import os
import csv
import shutil
import sys
import cv2
import numpy as np

# Add the root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from recorder import Recorder
import config # To get polygon and squares definitions

class TestRecorder(unittest.TestCase):

    def setUp(self):
        """Set up a temporary directory for test outputs."""
        self.test_dir = "temp_recorder_test_dir"
        os.makedirs(self.test_dir, exist_ok=True)
        self.recorder = Recorder()
        self.output_folder = os.path.join(self.test_dir, "test_run_1")
        self.frame_width = 100
        self.frame_height = 100

    def tearDown(self):
        """Clean up the temporary directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_start_recording_creates_files(self):
        """Test that start_recording creates all necessary directories and files."""
        success = self.recorder.start_recording(self.output_folder, self.frame_width, self.frame_height)
        self.assertTrue(success)

        base_name = os.path.basename(self.output_folder)

        # Check if all expected files were created
        video_file = os.path.join(self.output_folder, f"{base_name}.mp4")
        processing_area_csv = os.path.join(self.output_folder, f"1_ProcessingArea_{base_name}.csv")
        areas_of_interest_csv = os.path.join(self.output_folder, f"2_AreasOfInterest_{base_name}.csv")
        coord_movimento_csv = os.path.join(self.output_folder, f"3_CoordMovimento_{base_name}.csv")

        self.assertTrue(os.path.exists(video_file))
        self.assertTrue(os.path.exists(processing_area_csv))
        self.assertTrue(os.path.exists(areas_of_interest_csv))
        self.assertTrue(os.path.exists(coord_movimento_csv))

        self.recorder.stop_recording()

    def test_csv_headers_and_content(self):
        """Test that the CSV files have the correct headers and initial content."""
        self.recorder.start_recording(self.output_folder, self.frame_width, self.frame_height)
        base_name = os.path.basename(self.output_folder)

        # Test Processing Area CSV
        processing_area_csv = os.path.join(self.output_folder, f"1_ProcessingArea_{base_name}.csv")
        with open(processing_area_csv, 'r') as f:
            reader = csv.reader(f)
            header = next(reader)
            self.assertEqual(header, ['x', 'y'])
            content = list(reader)
            self.assertEqual(len(content), len(config.POLYGON))

        # Test Areas of Interest CSV
        areas_of_interest_csv = os.path.join(self.output_folder, f"2_AreasOfInterest_{base_name}.csv")
        with open(areas_of_interest_csv, 'r') as f:
            reader = csv.reader(f)
            header = next(reader)
            self.assertEqual(header, ['area', 'x1', 'y1', 'x2', 'y2'])
            content = list(reader)
            self.assertEqual(len(content), len(config.SQUARES))

        # Test Movement Coordinates CSV
        coord_movimento_csv = os.path.join(self.output_folder, f"3_CoordMovimento_{base_name}.csv")
        with open(coord_movimento_csv, 'r') as f:
            reader = csv.reader(f)
            header = next(reader)
            self.assertEqual(header, ['timestamp', 'frame', 'x1', 'y1', 'x2', 'y2', 'confidence'])

        self.recorder.stop_recording()

    def test_write_detection_data(self):
        """Test that detection data is written correctly to the CSV."""
        self.recorder.start_recording(self.output_folder, self.frame_width, self.frame_height)

        # Write some data
        timestamp = 1.23456
        frame_number = 101
        detections = [(10, 20, 30, 40, 0.987)]
        self.recorder.write_detection_data(timestamp, frame_number, detections)

        # Stop recording to ensure file is flushed and closed
        self.recorder.stop_recording()

        # Check the content of the CSV
        base_name = os.path.basename(self.output_folder)
        coord_movimento_csv = os.path.join(self.output_folder, f"3_CoordMovimento_{base_name}.csv")
        with open(coord_movimento_csv, 'r') as f:
            reader = csv.reader(f)
            header = next(reader) # Skip header
            rows = list(reader)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0], ["1.2346", "101", "10", "20", "30", "40", "98"])

    def test_video_writing(self):
        """Test that writing video frames increases file size."""
        self.recorder.start_recording(self.output_folder, self.frame_width, self.frame_height)
        base_name = os.path.basename(self.output_folder)
        video_file = os.path.join(self.output_folder, f"{base_name}.mp4")

        initial_size = os.path.getsize(video_file)

        # Create a dummy frame and write it
        dummy_frame = np.zeros((self.frame_height, self.frame_width, 3), dtype=np.uint8)
        self.recorder.write_video_frame(dummy_frame)
        self.recorder.write_video_frame(dummy_frame)

        # Stop recording to flush the writer
        self.recorder.stop_recording()

        final_size = os.path.getsize(video_file)
        self.assertGreater(final_size, initial_size)

if __name__ == '__main__':
    unittest.main()
