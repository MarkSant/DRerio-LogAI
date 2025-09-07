import json
import os
import shutil
import sys
import unittest

from zebtrack.core.project_manager import CONFIG_FILE_NAME, ProjectManager


class TestProjectManager(unittest.TestCase):
    def setUp(self):
        """Set up a temporary directory for testing."""
        self.test_dir = "temp_test_project_dir"
        os.makedirs(self.test_dir, exist_ok=True)
        # Suppress messagebox popups during tests
        self.original_showerror = sys.modules["tkinter.messagebox"].showerror
        sys.modules["tkinter.messagebox"].showerror = lambda title, message: None

    def tearDown(self):
        """Clean up the temporary directory after tests."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        sys.modules["tkinter.messagebox"].showerror = self.original_showerror

    def test_create_new_live_project(self):
        """Test the creation of a new 'live' project."""
        pm = ProjectManager()
        project_path = os.path.join(self.test_dir, "live_project")
        success = pm.create_new_project(project_path, "live")

        self.assertTrue(success)
        self.assertTrue(os.path.exists(os.path.join(project_path, CONFIG_FILE_NAME)))

        with open(os.path.join(project_path, CONFIG_FILE_NAME), "r") as f:
            data = json.load(f)
            self.assertEqual(data["project_name"], "live_project")
            self.assertEqual(data["project_type"], "live")
            self.assertEqual(data["batches"], [])

    def test_create_new_prerecorded_project(self):
        """Test the creation of a new 'pre-recorded' project."""
        pm = ProjectManager()
        project_path = os.path.join(self.test_dir, "prerecorded_project")
        # Mock the structure that scan_input_paths would create
        video_files = [
            {"path": "/path/to/video1.mp4", "has_data": False},
            {"path": "/path/to/video2.mp4", "has_data": True},
        ]
        success = pm.create_new_project(
            project_path, "pre-recorded", video_files=video_files
        )

        self.assertTrue(success)
        config_path = os.path.join(project_path, CONFIG_FILE_NAME)
        self.assertTrue(os.path.exists(config_path))

        with open(config_path, "r") as f:
            data = json.load(f)
            self.assertEqual(data["project_type"], "pre-recorded")
            self.assertEqual(len(data["batches"]), 1)
            self.assertEqual(len(data["batches"][0]["videos"]), 2)
            self.assertEqual(data["batches"][0]["videos"][0]["path"], video_files[0]["path"])
            self.assertEqual(data["batches"][0]["videos"][0]["status"], "pending")
            self.assertEqual(data["batches"][0]["videos"][1]["status"], "processed")

    def test_load_project(self):
        """Test loading an existing project configuration."""
        pm = ProjectManager()
        project_path = os.path.join(self.test_dir, "load_test_project")
        video_files = [{"path": "vid1.mp4", "has_data": False}]
        pm.create_new_project(project_path, "pre-recorded", video_files=video_files)

        loader_pm = ProjectManager()
        success = loader_pm.load_project(project_path)

        self.assertTrue(success)
        self.assertEqual(loader_pm.get_project_name(), "load_test_project")
        self.assertEqual(loader_pm.get_project_type(), "pre-recorded")
        self.assertEqual(len(loader_pm.get_all_videos()), 1)

    def test_load_nonexistent_project(self):
        """Test loading from a directory with no config file."""
        pm = ProjectManager()
        project_path = os.path.join(self.test_dir, "nonexistent_project")
        os.makedirs(project_path, exist_ok=True)  # Create dir but no config

        success = pm.load_project(project_path)
        self.assertFalse(success)

    def test_update_video_status_and_get_next(self):
        """Test updating video status and getting the next pending video."""
        pm = ProjectManager()
        project_path = os.path.join(self.test_dir, "status_project")
        video_files = [
            {"path": "video1.mp4", "has_data": False},
            {"path": "video2.mp4", "has_data": False},
            {"path": "video3.mp4", "has_data": False},
        ]
        pm.create_new_project(project_path, "pre-recorded", video_files=video_files)

        # First pending video should be video1.mp4
        next_video = pm.get_next_video()
        self.assertEqual(next_video, "video1.mp4")

        # Update status of video1 to complete
        pm.update_video_status("video1.mp4", "complete")

        # Now the next pending video should be video2.mp4
        next_video = pm.get_next_video()
        self.assertEqual(next_video, "video2.mp4")

        # Verify that the change was saved by loading it into a new instance
        loader_pm = ProjectManager()
        loader_pm.load_project(project_path)
        all_videos = loader_pm.get_all_videos()
        self.assertEqual(all_videos[0]["status"], "complete")
        self.assertEqual(loader_pm.get_next_video(), "video2.mp4")

        # Mark all as complete
        pm.update_video_status("video2.mp4", "complete")
        pm.update_video_status("video3.mp4", "complete")

        # Now there should be no pending videos
        self.assertIsNone(pm.get_next_video())


if __name__ == "__main__":
    unittest.main()
