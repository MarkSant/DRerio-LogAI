import os
import shutil
import unittest

import numpy as np
import pandas as pd

from zebtrack.io.recorder import Recorder
from zebtrack.settings import settings


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
        """Test that start_recording creates metadata Parquet files and video file."""
        success = self.recorder.start_recording(
            self.output_folder, self.frame_width, self.frame_height
        )
        self.assertTrue(success)

        base_name = os.path.basename(self.output_folder)

        # Check if metadata files were created
        video_file = os.path.join(self.output_folder, f"{base_name}.mp4")
        processing_area_parquet = os.path.join(
            self.output_folder, f"1_ProcessingArea_{base_name}.parquet"
        )
        areas_of_interest_parquet = os.path.join(
            self.output_folder, f"2_AreasOfInterest_{base_name}.parquet"
        )
        # The detection data file is only created on stop_recording
        coord_movimento_file = os.path.join(
            self.output_folder, f"3_CoordMovimento_{base_name}.parquet"
        )

        self.assertTrue(os.path.exists(video_file))
        self.assertTrue(os.path.exists(processing_area_parquet))
        self.assertTrue(os.path.exists(areas_of_interest_parquet))
        self.assertFalse(os.path.exists(coord_movimento_file))

        self.recorder.stop_recording()

    def test_metadata_parquet_content(self):
        """Test that the metadata Parquet files have the correct content."""
        self.recorder.start_recording(
            self.output_folder, self.frame_width, self.frame_height
        )
        base_name = os.path.basename(self.output_folder)

        # Test Processing Area Parquet
        processing_area_parquet = os.path.join(
            self.output_folder, f"1_ProcessingArea_{base_name}.parquet"
        )
        self.assertTrue(os.path.exists(processing_area_parquet))
        df_proc = pd.read_parquet(processing_area_parquet)
        self.assertEqual(list(df_proc.columns), ["x", "y"])
        self.assertEqual(len(df_proc), len(settings.detection_zones.polygon))
        # Optional: More detailed content check if necessary

        # Test Areas of Interest Parquet
        areas_of_interest_parquet = os.path.join(
            self.output_folder, f"2_AreasOfInterest_{base_name}.parquet"
        )
        self.assertTrue(os.path.exists(areas_of_interest_parquet))
        df_areas = pd.read_parquet(areas_of_interest_parquet)
        self.assertEqual(list(df_areas.columns), ["area", "x1", "y1", "x2", "y2"])
        self.assertEqual(len(df_areas), len(settings.detection_zones.squares))
        # Optional: More detailed content check if necessary

        self.recorder.stop_recording()

    def test_write_detection_data_saves_parquet(self):
        """Test that detection data is written correctly to a Parquet file."""
        self.recorder.start_recording(
            self.output_folder, self.frame_width, self.frame_height
        )

        # Write some data
        timestamp = 1.23456
        frame_number = 101
        detections = [(10, 20, 30, 40, 0.987, 1)]  # Added track_id
        self.recorder.write_detection_data(timestamp, frame_number, detections)

        # Stop recording to trigger Parquet file save
        self.recorder.stop_recording()

        # Check the content of the Parquet file
        base_name = os.path.basename(self.output_folder)
        coord_movimento_parquet = os.path.join(
            self.output_folder, f"3_CoordMovimento_{base_name}.parquet"
        )
        self.assertTrue(os.path.exists(coord_movimento_parquet))

        df = pd.read_parquet(coord_movimento_parquet)
        self.assertEqual(len(df), 1)
        row = df.iloc[0]

        self.assertEqual(row["timestamp"], timestamp)
        self.assertEqual(row["frame"], frame_number)
        self.assertEqual(row["track_id"], 1)
        self.assertEqual(row["x1"], 10)
        self.assertEqual(row["y1"], 20)
        self.assertEqual(row["x2"], 30)
        self.assertEqual(row["y2"], 40)
        self.assertAlmostEqual(row["confidence"], 0.987, places=5)

    def test_video_writing(self):
        """Test that writing video frames increases file size."""
        self.recorder.start_recording(
            self.output_folder, self.frame_width, self.frame_height
        )
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


if __name__ == "__main__":
    unittest.main()
