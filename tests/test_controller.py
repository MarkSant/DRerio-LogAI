import tempfile
import unittest
from typing import cast
from unittest.mock import MagicMock, patch

from zebtrack.core.controller import AppController
from zebtrack.io.arduino_manager import ArduinoManager
from zebtrack.settings import settings


class TestAppController(unittest.TestCase):
    @patch("zebtrack.core.controller.WeightManager")
    @patch("zebtrack.core.controller.ProjectManager")
    @patch("zebtrack.core.controller.ApplicationGUI")
    def setUp(self, mock_gui, mock_pm, mock_wm):
        """Set up a test environment before each test."""
        self.root = MagicMock()

        # The patched classes are passed as arguments to setUp
        self.mock_view = mock_gui.return_value
        self.mock_pm = mock_pm.return_value
        self.mock_wm = mock_wm.return_value

        # Configure the mock WeightManager to return a predictable default weight
        self.mock_wm.get_default_weight.return_value = (
            "best_seg.pt",
            "/fake/path/best_seg.pt",
        )

        self.controller = AppController(self.root)

        # The controller now has MOCK instances for its dependencies
        self.controller.project_manager = self.mock_pm
        self.controller.view = self.mock_view
        self.controller.weight_manager = self.mock_wm

        # Stub Arduino manager factory for tests
        self.mock_arduino_manager = MagicMock()
        self.mock_arduino_manager.connect.return_value = True
        self.mock_arduino_manager.is_connected.return_value = False
        self.mock_arduino_manager.current_port.return_value = None
        self.mock_arduino_manager.send_command.return_value = True
        self.mock_arduino_manager.arduino = MagicMock()

        self.mock_arduino_manager_cls = MagicMock(
            return_value=self.mock_arduino_manager
        )
        self.controller._arduino_manager_cls = cast(
            type[ArduinoManager], self.mock_arduino_manager_cls
        )
        self.controller.arduino_manager = None

    def tearDown(self):
        """Clean up after each test."""
        pass

    def test_create_project_workflow_success(self):
        """
        Test the successful creation of a new project through the controller.
        """
        # --- Arrange ---
        self.mock_pm.create_new_project.return_value = True
        with patch.object(self.controller, "setup_detector", return_value=True):
            # --- Act ---
            self.controller.create_project_workflow(
                project_path="/fake/parent/fake_project",
                project_type="live",
                use_openvino=False,
                video_files=[],
                num_aquariums=1,
                animals_per_aquarium=1,
                aquarium_width_cm=10.0,
                aquarium_height_cm=10.0,
            )

        # --- Assert ---
        self.mock_pm.create_new_project.assert_called_once_with(
            project_path="/fake/parent/fake_project",
            project_type="live",
            use_openvino=False,
            video_files=[],
            num_aquariums=1,
            animals_per_aquarium=1,
            aquarium_width_cm=10.0,
            aquarium_height_cm=10.0,
            active_weight="best_seg.pt",
        )
        self.mock_view._load_project_view.assert_called_once()

    def test_create_project_workflow_failure(self):
        """
        Test the project creation workflow when the project manager fails.
        """
        # --- Arrange ---
        self.mock_pm.create_new_project.return_value = False

        # --- Act ---
        self.controller.create_project_workflow(
            project_path="/fake/parent/fake_project",
            project_type="live",
            use_openvino=False,
            video_files=[],
            num_aquariums=1,
            animals_per_aquarium=1,
            aquarium_width_cm=10.0,
            aquarium_height_cm=10.0,
        )

        # --- Assert ---
        self.mock_view.show_error.assert_called_once_with(
            "Erro", "Falha ao criar o novo projeto."
        )
        self.mock_view._load_project_view.assert_not_called()

    def test_run_tracking_with_intervals(self):
        """Test that _run_tracking_if_needed accepts and uses analysis/display
        intervals."""
        # --- Arrange ---
        with (
            patch("cv2.VideoCapture") as mock_cap,
            patch.object(self.controller, "detector") as mock_detector,
            patch("zebtrack.core.controller.Recorder") as mock_recorder_class,
        ):
            # Configure mocks
            mock_cap_instance = mock_cap.return_value
            mock_cap_instance.isOpened.return_value = True
            mock_cap_instance.get.side_effect = lambda prop: {
                0: 640,  # CAP_PROP_FRAME_WIDTH
                1: 480,  # CAP_PROP_FRAME_HEIGHT
                2: 100,  # CAP_PROP_FRAME_COUNT
                3: 1000,  # CAP_PROP_POS_MSEC
            }.get(prop, 30.0)

            # Mock frame reading - return 5 frames then stop
            mock_cap_instance.read.side_effect = [
                (True, "frame1"),
                (True, "frame2"),
                (True, "frame3"),
                (True, "frame4"),
                (True, "frame5"),
                (False, None),
            ]

            mock_detector.process_frame.return_value = ([], None)
            mock_detector.draw_overlay.return_value = None

            # Mock project manager
            self.mock_pm.get_zone_data.return_value = MagicMock()
            self.mock_pm.get_zone_data.return_value.polygon = [
                [0, 0],
                [640, 0],
                [640, 480],
                [0, 480],
            ]

            mock_recorder_instance = mock_recorder_class.return_value

            # Mock progress callback to track calls
            progress_callback = MagicMock()

            # --- Act ---
            success, polygon = self.controller._run_tracking_if_needed(
                video_path="/fake/video.mp4",
                results_dir="/fake/results",
                experiment_id="test_exp",
                progress_callback=progress_callback,
                analysis_interval_frames=2,  # Process every 2nd frame
                display_interval_frames=3,  # Display every 3rd processed frame
            )

            # --- Assert ---
            self.assertTrue(success)
            # With 5 frames and analysis_interval=2, should process frames 0, 2, 4
            # (3 times)
            self.assertEqual(mock_detector.process_frame.call_count, 3)
            # Should call recorder write for each processed frame
            self.assertEqual(mock_recorder_instance.write_detection_data.call_count, 3)
            # Progress callback should be called for each PROCESSED frame (3 times)
            # Note: callback is only invoked when frame is actually processed
            # to avoid sending frames without detection overlays
            self.assertEqual(progress_callback.call_count, 3)

    def test_process_videos_interval_resolution(self):
        """Test that _process_videos correctly resolves analysis and display
        intervals."""
        # --- Arrange ---
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                self.controller, "_run_tracking_if_needed"
            ) as mock_tracking:
                mock_tracking.return_value = (
                    True,
                    [[0, 0], [100, 0], [100, 100], [0, 100]],
                )

                # Set up project data with intervals
                self.mock_pm.project_data = {
                    "analysis_interval_frames": 15,
                    "display_interval_frames": 20,
                }

                videos_to_process = [{"path": "/fake/video1.mp4", "has_data": False}]

                # --- Act ---
                self.controller._process_videos(
                    videos_to_process=videos_to_process,
                    output_base_dir=temp_dir,
                    single_video_config=None,  # This should use project data
                )

                # --- Assert ---
                mock_tracking.assert_called_once()
                call_args = mock_tracking.call_args
                self.assertEqual(call_args.kwargs["analysis_interval_frames"], 15)
                self.assertEqual(call_args.kwargs["display_interval_frames"], 20)

    def test_process_videos_single_video_config_intervals(self):
        """Test that single video config intervals take precedence over project data."""
        # --- Arrange ---
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                self.controller, "_run_tracking_if_needed"
            ) as mock_tracking:
                mock_tracking.return_value = (
                    True,
                    [[0, 0], [100, 0], [100, 100], [0, 100]],
                )

                # Set up project data with different intervals
                self.mock_pm.project_data = {
                    "analysis_interval_frames": 15,
                    "display_interval_frames": 20,
                }

                videos_to_process = [{"path": "/fake/video1.mp4", "has_data": False}]

                single_video_config = {
                    "analysis_interval_frames": 5,
                    "display_interval_frames": 7,
                }

                # --- Act ---
                self.controller._process_videos(
                    videos_to_process=videos_to_process,
                    output_base_dir=temp_dir,
                    single_video_config=single_video_config,
                )

                # --- Assert ---
                mock_tracking.assert_called_once()
                call_args = mock_tracking.call_args
                # Should use single video config values, not project data
                self.assertEqual(call_args.kwargs["analysis_interval_frames"], 5)
                self.assertEqual(call_args.kwargs["display_interval_frames"], 7)

    def test_setup_arduino_success(self):
        """Ensure setup_arduino connects when project requests Arduino support."""

        self.mock_pm.project_data = {
            "use_arduino": True,
            "arduino_port": "COM9",
        }

        result = self.controller.setup_arduino()

        self.assertTrue(result)
        self.mock_arduino_manager_cls.assert_called_once_with(self.controller)
        self.mock_arduino_manager.connect.assert_called_once_with(
            "COM9", settings.arduino.baud_rate
        )
        self.assertIs(self.controller.arduino_manager, self.mock_arduino_manager)
        self.assertIs(self.controller.arduino, self.mock_arduino_manager.arduino)

    def test_start_and_stop_recording_send_arduino_commands(self):
        """Verify Arduino start/stop commands fire during recording lifecycle."""

        with tempfile.TemporaryDirectory() as temp_dir:
            # Project configuration enabling Arduino controls
            self.mock_pm.project_path = temp_dir
            self.mock_pm.project_data = {
                "use_timed_recording": False,
                "recording_duration_s": 0,
                "use_countdown": False,
                "countdown_duration_s": 0,
                "use_arduino": True,
                "arduino_port": "COM7",
            }
            self.mock_pm.get_project_type.return_value = "live"

            zone_data = MagicMock()
            zone_data.polygon = [[0, 0], [1, 0], [1, 1], [0, 1]]
            self.mock_pm.get_zone_data.return_value = zone_data

            # Detector already initialised for the test scenario
            self.controller.detector = MagicMock()
            self.controller.setup_detector_zones = MagicMock()

            # Recorder behaves successfully
            self.controller.recorder = MagicMock()
            self.controller.recorder.start_recording.return_value = True

            # UI dependencies
            self.mock_view.ask_recording_details_unified.return_value = {
                "day": 1,
                "group": "A",
                "cobaia": "2",
            }
            self.mock_view.camera = MagicMock(actual_width=640, actual_height=480)

            # Reset and configure Arduino manager mock for this scenario
            self.mock_arduino_manager_cls.reset_mock()
            self.mock_arduino_manager.connect.reset_mock()
            self.mock_arduino_manager.send_command.reset_mock()
            self.mock_arduino_manager.arduino = MagicMock()
            self.mock_arduino_manager.current_port.return_value = "COM7"

            def is_connected_side_effect(*_args, **_kwargs):
                return self.mock_arduino_manager.connect.call_count > 0

            self.mock_arduino_manager.is_connected.side_effect = is_connected_side_effect

            # --- Act: start recording triggers Arduino start command
            self.controller.start_recording()

            self.mock_arduino_manager_cls.assert_called_once_with(self.controller)
            self.mock_arduino_manager.connect.assert_called_once_with(
                "COM7", settings.arduino.baud_rate
            )
            self.mock_arduino_manager.send_command.assert_any_call(
                2, source="manual-start"
            )

            # --- Act: stopping recording triggers stop command
            self.controller.is_recording = True
            self.controller.stop_recording()

            self.mock_arduino_manager.send_command.assert_any_call(
                0, source="manual-stop"
            )
            self.controller.recorder.stop_recording.assert_called_once()

    def test_external_trigger_waits_for_event_before_starting(self):
        """External trigger mode defers recording until Arduino event arrives."""

        with tempfile.TemporaryDirectory() as temp_dir:
            self.mock_pm.project_path = temp_dir
            self.mock_pm.project_data = {
                "use_timed_recording": False,
                "recording_duration_s": 0,
                "use_countdown": False,
                "countdown_duration_s": 0,
                "use_arduino": True,
                "arduino_port": "COM8",
                "external_trigger_mode": True,
            }
            self.mock_pm.get_project_type.return_value = "live"

            zone_data = MagicMock()
            zone_data.polygon = [[0, 0], [1, 0], [1, 1], [0, 1]]
            self.mock_pm.get_zone_data.return_value = zone_data

            self.controller.detector = MagicMock()
            self.controller.setup_detector_zones = MagicMock()
            self.controller.recorder = MagicMock()
            self.controller.recorder.start_recording.return_value = True

            self.mock_view.ask_recording_details_unified.return_value = {
                "day": 1,
                "group": "B",
                "cobaia": "3",
            }
            self.mock_view.camera = MagicMock(actual_width=640, actual_height=480)

            self.mock_arduino_manager_cls.reset_mock()
            self.mock_arduino_manager.connect.reset_mock()
            self.mock_arduino_manager.send_command.reset_mock()
            self.mock_arduino_manager.arduino = MagicMock()
            self.mock_arduino_manager.current_port.return_value = "COM8"

            def is_connected_side_effect(*_args, **_kwargs):
                return self.mock_arduino_manager.connect.call_count > 0

            self.mock_arduino_manager.is_connected.side_effect = is_connected_side_effect

            # Execute scheduled UI callbacks immediately in tests
            self.controller._schedule_on_ui = lambda func, *a, **k: func(*a, **k)

            self.controller.start_recording()

            # Should be waiting for external trigger
            self.assertIsNotNone(self.controller._pending_external_trigger)
            self.controller.recorder.start_recording.assert_not_called()
            self.mock_arduino_manager.send_command.assert_not_called()
            self.assertTrue(self.mock_view.show_external_trigger_notice.called)

            # Simulate Arduino event to trigger recording
            self.controller.on_arduino_event(1)

            self.controller.recorder.start_recording.assert_called_once()
            self.mock_arduino_manager.send_command.assert_any_call(
                3, source="external-start"
            )
            self.assertIsNone(self.controller._pending_external_trigger)
            self.assertTrue(self.mock_view.clear_external_trigger_notice.called)


if __name__ == "__main__":
    unittest.main()
