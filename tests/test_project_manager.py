import json
import os
import shutil
import sys
import unittest
from unittest.mock import MagicMock

from zebtrack.core.project_manager import CONFIG_FILE_NAME, ProjectManager


class TestProjectManager(unittest.TestCase):
    def setUp(self):
        """Set up a temporary directory for testing."""
        self.test_dir = "temp_test_project_dir"
        os.makedirs(self.test_dir, exist_ok=True)
        # Suppress messagebox popups during tests
        self.original_showerror = sys.modules["tkinter.messagebox"].showerror
        sys.modules["tkinter.messagebox"].showerror = (  # type: ignore[attr-defined]
            lambda title, message: None
        )

    def tearDown(self):
        """Clean up the temporary directory after tests."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        sys.modules["tkinter.messagebox"].showerror = self.original_showerror  # type: ignore[attr-defined]

    def test_copy_zone_parquet_files_replicates_artifacts(self):
        pm = ProjectManager()
        pm.project_path = self.test_dir

        source_video = os.path.join(self.test_dir, "source.mp4")
        target_video = os.path.join(self.test_dir, "target.mp4")

        with open(source_video, "wb") as handle:
            handle.write(b"")
        with open(target_video, "wb") as handle:
            handle.write(b"")

        source_results_dir = os.path.join(self.test_dir, "source_results")
        os.makedirs(source_results_dir, exist_ok=True)

        arena_src = os.path.join(source_results_dir, "1_ProcessingArea_source.parquet")
        rois_src = os.path.join(source_results_dir, "2_AreasOfInterest_source.parquet")
        for path in (arena_src, rois_src):
            with open(path, "wb") as handle:
                handle.write(b"test")

        pm.project_data = {
            "batches": [
                {
                    "videos": [
                        {
                            "path": source_video,
                            "parquet_files": {
                                "arena": arena_src,
                                "rois": rois_src,
                            },
                            "has_arena": True,
                            "has_rois": True,
                        },
                        {
                            "path": target_video,
                            "parquet_files": {},
                            "has_arena": False,
                            "has_rois": False,
                        },
                    ]
                }
            ]
        }

        copied = pm.copy_zone_parquet_files(source_video, target_video, persist=False)

        target_parent = os.path.dirname(target_video)
        expected_parent_arena = os.path.join(
            target_parent, "1_ProcessingArea_target.parquet"
        )
        expected_parent_rois = os.path.join(
            target_parent, "2_AreasOfInterest_target.parquet"
        )
        target_results_dir = os.path.join(target_parent, "target_results")
        expected_results_arena = os.path.join(
            target_results_dir, "1_ProcessingArea_target.parquet"
        )
        expected_results_rois = os.path.join(
            target_results_dir, "2_AreasOfInterest_target.parquet"
        )

        # Files should be duplicated to the parent directory
        self.assertTrue(os.path.exists(expected_parent_arena))
        self.assertTrue(os.path.exists(expected_parent_rois))
        # And also to the mirrored _results directory when the source lived there
        self.assertTrue(os.path.exists(expected_results_arena))
        self.assertTrue(os.path.exists(expected_results_rois))

        self.assertIn("arena", copied)
        self.assertIn("rois", copied)
        self.assertEqual(
            os.path.normpath(copied["arena"]), os.path.normpath(expected_results_arena)
        )
        self.assertEqual(
            os.path.normpath(copied["rois"]), os.path.normpath(expected_results_rois)
        )

        target_entry = pm.find_video_entry(path=target_video)
        self.assertIsNotNone(target_entry)
        assert target_entry is not None
        parquet_map = target_entry.get("parquet_files", {})
        self.assertEqual(
            os.path.normpath(parquet_map.get("arena", "")),
            os.path.normpath(expected_results_arena),
        )
        self.assertEqual(
            os.path.normpath(parquet_map.get("rois", "")),
            os.path.normpath(expected_results_rois),
        )

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
            self.assertEqual(
                data["batches"][0]["videos"][0]["path"], video_files[0]["path"]
            )
            self.assertEqual(data["batches"][0]["videos"][0]["status"], "pending")
            self.assertEqual(data["batches"][0]["videos"][1]["status"], "processed")

    def test_create_new_project_initial_model_overrides(self):
        """Project creation should initialize model overrides as inherited defaults."""
        pm = ProjectManager()
        project_path = os.path.join(self.test_dir, "overrides_project")
        success = pm.create_new_project(project_path, "live")

        self.assertTrue(success)
        config_path = os.path.join(project_path, CONFIG_FILE_NAME)
        with open(config_path, "r") as f:
            data = json.load(f)

        self.assertIn("model_overrides", data)
        self.assertEqual(
            data["model_overrides"], {"active_weight": None, "use_openvino": None}
        )
        self.assertEqual(
            pm.project_data["model_overrides"],
            {"active_weight": None, "use_openvino": None},
        )

    def test_add_video_batch_persists_metadata(self):
        """Video batches should persist experimental metadata and flags."""
        pm = ProjectManager()
        pm.project_path = self.test_dir
        pm.project_data = {"batches": []}

        video_path = os.path.join(self.test_dir, "metadata_sample.mp4")
        with open(video_path, "wb") as handle:
            handle.write(b"sample")

        video_files = [
            {
                "path": video_path,
                "has_data": True,
                "group": "Control",
                "group_display_name": "Veiculo",
                "day": "Day01",
                "subject": "S01",
                "has_arena": True,
                "has_rois": False,
                "has_trajectory": True,
            }
        ]

        pm.add_video_batch(video_files, save_project=False)

        videos = pm.get_all_videos()
        self.assertEqual(len(videos), 1)
        video_entry = videos[0]
        self.assertEqual(video_entry["metadata"]["group"], "Control")
        self.assertEqual(video_entry["metadata"]["subject"], "S01")
        self.assertTrue(video_entry["has_arena"])
        self.assertTrue(video_entry["has_trajectory"])
        self.assertTrue(video_entry["has_complete_data"])

    def test_create_project_with_animals_per_aquarium(self):
        """Test creating a project with animals_per_aquarium field."""
        pm = ProjectManager()
        project_path = os.path.join(self.test_dir, "animals_test_project")
        video_files = [{"path": "video1.mp4", "has_data": False}]

        success = pm.create_new_project(
            project_path,
            "pre-recorded",
            video_files=video_files,
            num_aquariums=2,
            animals_per_aquarium=3,
            aquarium_width_cm=15.0,
            aquarium_height_cm=20.0,
        )

        self.assertTrue(success)
        config_path = os.path.join(project_path, CONFIG_FILE_NAME)
        self.assertTrue(os.path.exists(config_path))

        with open(config_path, "r") as f:
            data = json.load(f)
            self.assertEqual(data["calibration"]["num_aquariums"], 2)
            self.assertEqual(data["calibration"]["animals_per_aquarium"], 3)
            self.assertEqual(data["calibration"]["aquarium_width_cm"], 15.0)
            self.assertEqual(data["calibration"]["aquarium_height_cm"], 20.0)

    def test_create_project_default_animals_per_aquarium(self):
        """Test creating a project with default animals_per_aquarium value."""
        pm = ProjectManager()
        project_path = os.path.join(self.test_dir, "default_animals_project")

        success = pm.create_new_project(
            project_path,
            "live",
        )

        self.assertTrue(success)
        config_path = os.path.join(project_path, CONFIG_FILE_NAME)
        self.assertTrue(os.path.exists(config_path))

        with open(config_path, "r") as f:
            data = json.load(f)
            # Check default values
            self.assertEqual(data["calibration"]["num_aquariums"], 1)
            self.assertEqual(data["calibration"]["animals_per_aquarium"], 1)

    def test_create_project_persists_camera_and_arduino_settings(self):
        """Projects should persist camera index and Arduino configuration."""
        pm = ProjectManager()
        project_path = os.path.join(self.test_dir, "io_settings_project")

        success = pm.create_new_project(
            project_path,
            "live",
            camera_index=3,
            use_arduino=True,
            arduino_port="COM7",
        )

        self.assertTrue(success)
        config_path = os.path.join(project_path, CONFIG_FILE_NAME)
        with open(config_path, "r") as f:
            data = json.load(f)

        self.assertEqual(data["camera_index"], 3)
        self.assertTrue(data["use_arduino"])
        self.assertEqual(data["arduino_port"], "COM7")

    def test_load_project_backward_compatibility(self):
        """Test loading a project without animals_per_aquarium field."""
        pm = ProjectManager()
        project_path = os.path.join(self.test_dir, "backward_compat_project")
        os.makedirs(project_path, exist_ok=True)

        # Create a project config WITHOUT animals_per_aquarium field
        # (simulates old project)
        old_project_data = {
            "project_name": "backward_compat_project",
            "project_type": "live",
            "calibration": {
                "num_aquariums": 2,
                "aquarium_width_cm": 15.0,
                "aquarium_height_cm": 20.0,
                # Missing animals_per_aquarium field
            },
            "use_openvino": False,
            "active_weight": None,
            "batches": [],
        }

        config_path = os.path.join(project_path, CONFIG_FILE_NAME)
        with open(config_path, "w") as f:
            json.dump(old_project_data, f, indent=2)

        # Load the project - should add default animals_per_aquarium value
        success = pm.load_project(project_path)

        self.assertTrue(success)
        self.assertEqual(pm.project_data["calibration"]["num_aquariums"], 2)
        self.assertEqual(
            pm.project_data["calibration"]["animals_per_aquarium"], 1
        )  # Default value added
        self.assertEqual(
            pm.project_data["model_overrides"],
            {"active_weight": None, "use_openvino": None},
        )

    def test_load_project_migrates_missing_camera_and_interval_fields(self):
        """Legacy projects missing interval/camera fields should gain safe defaults."""
        pm = ProjectManager()
        project_path = os.path.join(self.test_dir, "legacy_project")
        os.makedirs(project_path, exist_ok=True)

        legacy_data = {
            "project_name": "legacy_project",
            "project_type": "live",
            "calibration": {
                "num_aquariums": 1,
                "aquarium_width_cm": 10.0,
                "aquarium_height_cm": 10.0,
            },
            "use_openvino": False,
            "active_weight": None,
            "batches": [],
        }

        config_path = os.path.join(project_path, CONFIG_FILE_NAME)
        with open(config_path, "w") as f:
            json.dump(legacy_data, f, indent=2)

        success = pm.load_project(project_path)

        self.assertTrue(success)
        self.assertEqual(pm.project_data["analysis_interval_frames"], 10)
        self.assertEqual(pm.project_data["display_interval_frames"], 10)
        self.assertEqual(pm.project_data["camera_index"], 0)
        self.assertFalse(pm.project_data["use_arduino"])
        self.assertEqual(pm.project_data["arduino_port"], "")
        self.assertEqual(pm.project_data["calibration"]["animals_per_aquarium"], 1)
        self.assertIn("file_hash", pm.project_data)

        with open(config_path, "r") as f:
            saved_data = json.load(f)

        for field in [
            "analysis_interval_frames",
            "display_interval_frames",
            "camera_index",
            "use_arduino",
            "arduino_port",
        ]:
            self.assertIn(field, saved_data)

        self.assertEqual(saved_data["arduino_port"], "")
        self.assertIn("file_hash", saved_data)
        self.assertEqual(
            pm.project_data["model_overrides"],
            {"active_weight": None, "use_openvino": None},
        )

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

        # Now there should be no pending videos
        self.assertIsNone(pm.get_next_video())

    def test_project_manager_script(self):
        """Test the ProjectManager using the original script-based test."""
        # Setup test directory
        test_dir = os.path.join(self.test_dir, "pm_test_project")
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)

        pm = ProjectManager()

        # 1. Test creating a new pre-recorded project
        # Using a platform-independent path for testing
        video_files = [
            {"path": os.path.join("C:", "videos", "vid1.mp4"), "has_data": False},
            {"path": os.path.join("C:", "videos", "vid2.mp4"), "has_data": False},
        ]
        success = pm.create_new_project(
            test_dir, "pre-recorded", video_files=video_files
        )
        self.assertTrue(success)

        # 2. Test loading an existing project
        pm_loader = ProjectManager()
        success = pm_loader.load_project(test_dir)
        self.assertTrue(success)

        # 3. Test updating and getting next video
        next_vid = pm_loader.get_next_video()
        self.assertIsNotNone(next_vid)

        pm_loader.update_video_status(next_vid, "complete")

        next_vid_after_update = pm_loader.get_next_video()
        self.assertNotEqual(next_vid, next_vid_after_update)

    def test_register_processing_outputs_updates_flags(self):
        pm = ProjectManager()
        pm.project_path = self.test_dir
        video_path = os.path.join(self.test_dir, "metadata_sample.mp4")
        pm.project_data = {
            "batches": [
                {
                    "videos": [
                        {
                            "path": video_path,
                            "status": "pending",
                            "has_arena": True,
                            "has_rois": True,
                            "has_trajectory": False,
                            "has_complete_data": False,
                            "parquet_files": {},
                        }
                    ]
                }
            ]
        }

        pm.save_project = MagicMock(return_value=True)

        results_dir = os.path.join(self.test_dir, "metadata_sample_results")
        trajectory_path = os.path.join(
            results_dir, "3_CoordMovimento_metadata_sample.parquet"
        )
        summary_path = os.path.join(results_dir, "metadata_sample_summary.parquet")
        excel_path = os.path.join(results_dir, "metadata_sample_summary.xlsx")
        report_path = os.path.join(results_dir, "metadata_sample_report.docx")

        updated = pm.register_processing_outputs(
            video_path,
            results_dir=results_dir,
            trajectory_path=trajectory_path,
            summary_parquet=summary_path,
            summary_excel=excel_path,
            report_path=report_path,
        )

        self.assertTrue(updated)
        video_entry = pm.project_data["batches"][0]["videos"][0]
        self.assertTrue(video_entry.get("has_trajectory"))
        self.assertTrue(video_entry.get("has_summary"))
        self.assertTrue(video_entry.get("has_complete_data"))
        self.assertEqual(video_entry.get("results_dir"), results_dir)
        self.assertEqual(
            video_entry["parquet_files"].get("trajectory"), trajectory_path
        )
        self.assertEqual(video_entry["parquet_files"].get("summary"), summary_path)
        self.assertEqual(
            video_entry["parquet_files"].get("summary_excel"), excel_path
        )
        self.assertEqual(
            video_entry["parquet_files"].get("report_docx"), report_path
        )
        pm.save_project.assert_called_once()

    def test_derive_processing_metadata_falls_back_to_project_entry(self):
        pm = ProjectManager()
        video_path = os.path.join(self.test_dir, "GroupA_subject4.mp4")
        pm.project_data = {
            "batches": [
                {
                    "videos": [
                        {
                            "path": video_path,
                            "metadata": {"group": "GroupA"},
                            "day": 2,
                            "subject": "4",
                        }
                    ]
                }
            ]
        }

        metadata = pm.derive_processing_metadata(
            "GroupA_subject4",
            video_path,
        )

        self.assertEqual(metadata["experiment_id"], "GroupA_subject4")
        self.assertEqual(metadata["video_name"], "GroupA_subject4")
        self.assertEqual(metadata["group"], "GroupA")
        self.assertEqual(metadata["day"], 2)
        self.assertEqual(metadata["subject"], "4")
        self.assertEqual(metadata["group_id"], "GroupA")

    def test_derive_processing_metadata_defaults_when_missing(self):
        pm = ProjectManager()
        pm.project_data = {"batches": []}

        metadata = pm.derive_processing_metadata("CECT_4", None)

        self.assertEqual(metadata["experiment_id"], "CECT_4")
        self.assertEqual(metadata["video_name"], "CECT_4")
        self.assertNotIn("group", metadata)

    def test_detector_state_persistence(self):
        """Test detector state save and retrieve functionality."""
        pm = ProjectManager()
        project_path = os.path.join(self.test_dir, "detector_state_project")

        # Create a new project first
        success = pm.create_new_project(project_path, "live")
        self.assertTrue(success)

        # Test saving detector state
        detector_config = {
            "plugin_name": "YOLO (Ultralytics)",
            "confidence_threshold": 0.7,
            "nms_threshold": 0.5,
            "context": "tracking"
        }

        save_result = pm.save_detector_state(detector_config)
        self.assertTrue(save_result)

        # Test retrieving detector state
        retrieved_config = pm.get_detector_state()
        self.assertIsNotNone(retrieved_config)
        self.assertEqual(retrieved_config["plugin_name"], "YOLO (Ultralytics)")
        self.assertEqual(retrieved_config["confidence_threshold"], 0.7)
        self.assertEqual(retrieved_config["nms_threshold"], 0.5)
        self.assertEqual(retrieved_config["context"], "tracking")
        self.assertIn("last_updated", retrieved_config)

        # Test loading project and verifying detector state persists
        loader_pm = ProjectManager()
        load_success = loader_pm.load_project(project_path)
        self.assertTrue(load_success)

        loaded_config = loader_pm.get_detector_state()
        self.assertEqual(loaded_config["plugin_name"], "YOLO (Ultralytics)")
        self.assertEqual(loaded_config["confidence_threshold"], 0.7)
        self.assertEqual(loaded_config["context"], "tracking")

    def test_detector_state_empty_project(self):
        """Test detector state retrieval from empty project returns empty dict."""
        pm = ProjectManager()
        project_path = os.path.join(self.test_dir, "empty_detector_project")

        # Create a new project without detector config
        success = pm.create_new_project(project_path, "live")
        self.assertTrue(success)

        # Should return empty dict when no detector config exists
        config = pm.get_detector_state()
        self.assertEqual(config, {})

    def test_detector_state_save_without_project(self):
        """Test detector state saving fails without project data."""
        pm = ProjectManager()

        detector_config = {
            "plugin_name": "OpenVINO",
            "confidence_threshold": 0.6
        }

        # Should fail when no project data exists
        result = pm.save_detector_state(detector_config)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
