import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import ANY, MagicMock, patch

import cv2

from zebtrack.core.controller import AppController
from zebtrack.core.detector import ZoneData
from zebtrack.io.arduino_manager import ArduinoManager
from zebtrack.settings import settings


class TestAppController(unittest.TestCase):
    @patch("zebtrack.core.controller.WeightManager")
    @patch("zebtrack.core.controller.ProjectManager")
    @patch("zebtrack.core.controller.ApplicationGUI")
    def setUp(self, mock_gui, mock_pm, mock_wm):
        """Set up a test environment before each test."""
        self.root = MagicMock()
        self.root.after = MagicMock()
        self.root.after_cancel = MagicMock()

        # The patched classes are passed as arguments to setUp
        self.mock_view = mock_gui.return_value
        self.mock_pm = mock_pm.return_value
        self.mock_wm = mock_wm.return_value

        self._single_animal_original = (
            settings.video_processing.single_animal_per_aquarium
        )
        self._event_queue_flag_original = (
            settings.ui_features.enable_event_queue
            if settings and settings.ui_features
            else False
        )
        if settings and settings.ui_features:
            settings.ui_features.enable_event_queue = False

        # Configure the mock WeightManager to return a predictable default weight
        self.mock_wm.get_default_weight.return_value = (
            "best_seg.pt",
            "/fake/path/best_seg.pt",
        )
        self.mock_wm.get_all_weights.return_value = [
            "best_seg.pt",
            "backup.pt",
        ]

        self.controller = AppController(self.root)

        # The controller now has MOCK instances for its dependencies
        self.controller.project_manager = self.mock_pm
        self.controller.view = self.mock_view
        self.controller.weight_manager = self.mock_wm

        self.mock_pm.project_path = None
        self.mock_pm.project_data = {}
        self.mock_pm.get_metadata_for_experiment.return_value = {}
        self.mock_pm.derive_processing_metadata.side_effect = (
            lambda experiment_id, video_path=None: {
                "experiment_id": experiment_id,
                "video_name": experiment_id,
            }
        )
        self.mock_pm.register_processing_outputs.return_value = True
        self.mock_pm.get_project_name.return_value = "Projeto Teste"

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

        self.mock_view.show_pending_videos_dialog.return_value = {
            "confirmed": True,
            "include_arena_only": True,
        }

    def tearDown(self):
        """Clean up after each test."""
        settings.video_processing.single_animal_per_aquarium = (
            self._single_animal_original
        )
        if settings and settings.ui_features:
            settings.ui_features.enable_event_queue = self._event_queue_flag_original

    def test_resolve_single_animal_mode_single_video_config(self):
        result = self.controller._resolve_single_animal_mode(
            {"animals_per_aquarium": 1}
        )

        self.assertTrue(result)

    def test_resolve_single_animal_mode_project_data(self):
        self.mock_pm.project_data = {"calibration": {"animals_per_aquarium": 3}}

        result = self.controller._resolve_single_animal_mode(None)

        self.assertFalse(result)

    def test_resolve_single_animal_mode_returns_none_when_unset(self):
        self.mock_pm.project_data = {}

        result = self.controller._resolve_single_animal_mode(None)

        self.assertIsNone(result)

    def test_prepare_results_directory_archives_existing_run(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            results_dir = Path(tmp_dir) / "video_results"
            results_dir.mkdir()
            (results_dir / "summary.xlsx").write_text("data")
            nested_dir = results_dir / "nested"
            nested_dir.mkdir()
            (nested_dir / "trajectory.parquet").write_text("trajectory")

            self.controller._prepare_results_directory(str(results_dir))

            history_dir = results_dir / "history"
            self.assertTrue(history_dir.exists())

            history_runs = list(history_dir.iterdir())
            self.assertEqual(len(history_runs), 1)
            archived_run = history_runs[0]
            self.assertTrue((archived_run / "summary.xlsx").exists())
            self.assertTrue(
                (archived_run / "nested" / "trajectory.parquet").exists()
            )

            remaining_items = [p for p in results_dir.iterdir() if p.name != "history"]
            self.assertEqual(remaining_items, [])

            # Second invocation should be a no-op because only history remains
            self.controller._prepare_results_directory(str(results_dir))
            self.assertEqual(len(list(history_dir.iterdir())), 1)

    def test_get_calibration_scope_info_global_without_project(self):
        info = self.controller.get_calibration_scope_info()
        self.assertEqual(info["scope"], "global")
        self.assertFalse(info["project_loaded"])

    def test_get_calibration_scope_info_project_inheriting(self):
        self.mock_pm.project_path = "/project"
        self.mock_pm.project_data = {}
        self.controller._using_project_overrides = True

        info = self.controller.get_calibration_scope_info()
        self.assertEqual(info["scope"], "project")
        self.assertTrue(info["inheriting_globals"])
        self.assertFalse(info["overrides_active"])

    def test_get_current_detector_parameters_with_plugin(self):
        class DummyPlugin:
            def __init__(self):
                self.conf_threshold = 0.33
                self.nms_threshold = 0.44
                self.track_threshold = 0.25
                self.match_threshold = 0.6

            @staticmethod
            def get_name():
                return "dummy"

        detector = MagicMock()
        detector.plugin = DummyPlugin()
        self.controller.detector = detector

        params = self.controller.get_current_detector_parameters()

        self.assertAlmostEqual(params["confidence_threshold"], 0.33)
        self.assertAlmostEqual(params["nms_threshold"], 0.44)
        self.assertAlmostEqual(params["track_threshold"], 0.25)
        self.assertAlmostEqual(params["match_threshold"], 0.6)

    def test_update_detector_parameters_updates_plugin_and_saves(self):
        class DummyPlugin:
            def __init__(self):
                self.conf_threshold = 0.2
                self.nms_threshold = 0.5
                self.track_threshold = 0.25
                self.match_threshold = 0.6
                self._context = "tracking"

            @staticmethod
            def get_name():
                return "dummy"

            def set_tracking_parameters(
                self, *, track_threshold=None, match_threshold=None
            ):
                if track_threshold is not None:
                    self.track_threshold = track_threshold
                if match_threshold is not None:
                    self.match_threshold = match_threshold

        plugin = DummyPlugin()
        detector = MagicMock()
        detector.plugin = plugin
        self.controller.detector = detector
        self.mock_pm.save_detector_state.return_value = True

        updated = self.controller.update_detector_parameters(
            {
                "confidence_threshold": 0.3,
                "nms_threshold": 0.55,
                "track_threshold": 0.35,
                "match_threshold": 0.7,
            }
        )

        self.assertTrue(updated)
        self.assertAlmostEqual(plugin.conf_threshold, 0.3)
        self.assertAlmostEqual(plugin.nms_threshold, 0.55)
        self.assertAlmostEqual(plugin.track_threshold, 0.35)
        self.assertAlmostEqual(plugin.match_threshold, 0.7)
        self.mock_pm.save_detector_state.assert_called_once()
        saved_config = self.mock_pm.save_detector_state.call_args.args[0]
        self.assertAlmostEqual(saved_config["confidence_threshold"], 0.3)
        self.assertAlmostEqual(saved_config["nms_threshold"], 0.55)
        self.assertAlmostEqual(saved_config["track_threshold"], 0.35)
        self.assertAlmostEqual(saved_config["match_threshold"], 0.7)

    def test_get_project_data_dict_normalizes_non_dict(self):
        self.mock_pm.project_data = None

        project_data = self.controller._get_project_data_dict()

        self.assertIsInstance(project_data, dict)
        self.assertIs(self.mock_pm.project_data, project_data)

    def test_ensure_project_overrides_record_initializes_defaults(self):
        self.mock_pm.project_data = {}

        overrides = self.controller._ensure_project_overrides_record()

        self.assertEqual(
            overrides,
            {"active_weight": None, "use_openvino": None},
        )
        self.assertIs(
            self.controller.project_manager.project_data["model_overrides"],
            overrides,
        )

    def test_copy_global_model_settings_to_project(self):
        self.mock_pm.project_path = "/project"
        self.mock_pm.project_data = {}
        self.controller._global_model_defaults["active_weight"] = "best_seg.pt"
        self.controller._global_model_defaults["use_openvino"] = True
        self.mock_pm.save_project.reset_mock()

        with patch.object(self.controller, "refresh_project_views") as refresh_mock:
            result = self.controller.copy_global_model_settings_to_project()

        self.assertEqual(result, ("best_seg.pt", True))
        project_data = getattr(self.controller.project_manager, "project_data", {})
        overrides = project_data["model_overrides"]
        self.assertEqual(overrides["active_weight"], "best_seg.pt")
        self.assertTrue(overrides["use_openvino"])
        self.assertEqual(project_data["active_weight"], "best_seg.pt")
        self.assertTrue(project_data["use_openvino"])
        self.mock_pm.save_project.assert_called()
        refresh_mock.assert_called()

    def test_save_current_calibration_to_project(self):
        self.mock_pm.project_path = "/project"
        self.mock_pm.project_data = {}
        self.controller.active_weight_name = "backup.pt"
        self.controller.use_openvino = False
        self.mock_pm.save_project.reset_mock()

        with patch.object(self.controller, "refresh_project_views") as refresh_mock:
            result = self.controller.save_current_calibration_to_project()

        self.assertEqual(result, ("backup.pt", False))
        project_data = getattr(self.controller.project_manager, "project_data", {})
        overrides = project_data["model_overrides"]
        self.assertEqual(overrides["active_weight"], "backup.pt")
        self.assertFalse(overrides["use_openvino"])
        self.assertEqual(project_data["active_weight"], "backup.pt")
        self.assertFalse(project_data["use_openvino"])
        self.mock_pm.save_project.assert_called()
        refresh_mock.assert_called()

    def test_schedule_on_ui_uses_event_bus_when_enabled(self):
        if not settings or not settings.ui_features:
            self.skipTest("UI feature settings unavailable")

        class StubGUI:
            def __init__(self, root, controller, event_bus=None):
                self.root = root
                self.controller = controller
                self.event_bus = event_bus

            def process_events(self):
                if self.event_bus is None:
                    return
                for event in self.event_bus.drain():
                    payload = event.payload
                    if hasattr(payload, "execute"):
                        payload.execute()

            def stop_event_bus_polling(self):
                pass

        with (
            patch("zebtrack.core.controller.ProjectManager", return_value=self.mock_pm),
            patch("zebtrack.core.controller.WeightManager", return_value=self.mock_wm),
            patch("zebtrack.core.controller.ApplicationGUI", new=StubGUI),
        ):
            settings.ui_features.enable_event_queue = True
            controller = AppController(self.root)

        self.assertIsNotNone(controller.ui_event_bus)
        event_bus = controller.ui_event_bus
        self.assertIsInstance(controller.view, StubGUI)
        mock_callback = MagicMock()

        self.root.after.reset_mock()
        controller._schedule_on_ui(mock_callback, 42, example="test")
        self.root.after.assert_not_called()
        assert event_bus is not None
        self.assertEqual(event_bus.size(), 1)
        stub_view = cast(StubGUI, controller.view)
        stub_view.process_events()
        self.assertEqual(event_bus.size(), 0)
        mock_callback.assert_called_once_with(42, example="test")

    @patch("zebtrack.core.controller.Recorder")
    @patch("zebtrack.core.controller.cv2.VideoCapture")
    def test_run_tracking_uses_project_calibration(
        self, mock_capture, mock_recorder_cls
    ):
        self.mock_pm.project_data = {
            "calibration": {
                "aquarium_width_cm": 50.0,
                "aquarium_height_cm": 25.0,
            }
        }
        zone_data = ZoneData(
            polygon=[[0, 0], [800, 0], [800, 400], [0, 400]],
            roi_polygons=[],
        )
        self.mock_pm.get_zone_data.return_value = zone_data

        recorder_instance = mock_recorder_cls.return_value
        recorder_instance.start_recording.return_value = True
        recorder_instance.write_detection_data.return_value = None

        cap_instance = mock_capture.return_value
        cap_instance.isOpened.return_value = True

        def fake_get(prop):
            if prop in (cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT):
                return 800 if prop == cv2.CAP_PROP_FRAME_WIDTH else 400
            if prop == cv2.CAP_PROP_FRAME_COUNT:
                return 1
            if prop == cv2.CAP_PROP_POS_MSEC:
                return 0
            return 0

        cap_instance.get.side_effect = fake_get
        cap_instance.read.side_effect = [(False, None)]

        detector_stub = MagicMock()
        detector_stub.process_frame.return_value = ([], None)
        detector_stub.draw_overlay.return_value = None
        detector_stub.set_zones.return_value = None
        detector_stub.plugin = MagicMock()
        detector_stub.plugin.get_name.return_value = "stub"
        self.controller.detector = detector_stub

        with tempfile.TemporaryDirectory() as tmp_dir:
            success, _ = self.controller._run_tracking_if_needed(
                video_path="dummy.mp4",
                results_dir=tmp_dir,
                experiment_id="exp1",
            )

        self.assertTrue(success)
        kwargs = recorder_instance.start_recording.call_args.kwargs
        self.assertIsNotNone(kwargs.get("pixel_per_cm_ratio"))
        self.assertIsNotNone(kwargs.get("calibration"))

    def test_refresh_project_views_schedules_on_ui(self):
        refresh_mock = MagicMock()
        self.mock_view.refresh_project_views = refresh_mock

        with patch.object(self.controller, "_schedule_on_ui") as schedule_mock:
            self.controller.refresh_project_views(
                "Atualizado",
                append_summary=True,
                immediate=True,
            )

        schedule_mock.assert_called_once()
        scheduled_fn, reason = schedule_mock.call_args.args[:2]
        self.assertIs(scheduled_fn, refresh_mock)
        self.assertEqual(reason, "Atualizado")
        self.assertEqual(
            schedule_mock.call_args.kwargs,
            {"append_summary": True, "immediate": True},
        )

    def test_refresh_project_views_noop_without_view_method(self):
        self.mock_view.refresh_project_views = None

        with patch.object(self.controller, "_schedule_on_ui") as schedule_mock:
            self.controller.refresh_project_views("ignored")

        schedule_mock.assert_not_called()

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

    def test_open_project_workflow_success_loads_view_and_zones(self):
        project_path = "/fake/project"
        self.mock_pm.load_project.return_value = True
        self.mock_pm.get_detector_state.return_value = None
        self.mock_pm.get_zone_data.return_value = ZoneData(
            polygon=[[0, 0], [1, 0], [1, 1], [0, 1]],
            roi_polygons=[[[0, 0], [1, 0], [1, 1]]],
            roi_names=["ROI"],
            roi_colors=[(255, 0, 0)],
        )
        self.mock_pm.get_all_videos.return_value = [
            {"path": "video1.mp4", "status": "pending"}
        ]

        with (
            patch.object(
                self.controller,
                "apply_project_model_overrides",
                return_value=("best_seg.pt", False),
            ) as apply_overrides,
            patch.object(self.controller, "setup_detector", return_value=True),
            patch.object(self.controller, "setup_detector_zones") as setup_zones,
            patch.object(self.controller, "update_openvino_status") as update_status,
        ):
            result = self.controller.open_project_workflow(project_path)

        self.assertTrue(result)
        self.mock_pm.load_project.assert_called_once_with(project_path)
        apply_overrides.assert_called_once()
        update_status.assert_called_once()
        self.mock_view.update_openvino_checkbox.assert_called_once_with(
            self.controller.use_openvino
        )
        self.mock_view.set_active_weight_in_dropdown.assert_called_once_with(
            self.controller.active_weight_name
        )
        self.mock_view._load_project_view.assert_called_once()
        setup_zones.assert_called_once()
        self.mock_view.redraw_zones_from_project_data.assert_called_once()
        self.mock_view.update_zone_listbox.assert_called_once()
        self.mock_view.show_info.assert_called_once()

    def test_save_project_model_overrides_applies_settings(self):
        self.mock_pm.project_data = {
            "model_overrides": {"active_weight": None, "use_openvino": None},
            "active_weight": None,
            "use_openvino": False,
        }
        self.mock_pm.project_path = "/fake/project"
        self.mock_pm.save_project.return_value = True

        resolved_weight, resolved_openvino = (
            self.controller.save_project_model_overrides("backup.pt", True)
        )

        self.assertEqual(resolved_weight, "backup.pt")
        self.assertTrue(resolved_openvino)
        self.assertEqual(
            self.mock_pm.project_data["model_overrides"],
            {"active_weight": "backup.pt", "use_openvino": True},
        )
        self.assertEqual(self.controller.active_weight_name, "backup.pt")
        self.assertTrue(self.controller.use_openvino)
        self.assertTrue(self.controller.are_project_overrides_active)
        self.mock_pm.save_project.assert_called()

    def test_global_calibration_session_reapplies_project_overrides(self):
        self.mock_pm.project_data = {
            "model_overrides": {"active_weight": "backup.pt", "use_openvino": False},
            "active_weight": "backup.pt",
            "use_openvino": False,
        }
        self.mock_pm.project_path = "/fake/project"
        self.mock_pm.save_project.return_value = True

        self.controller.apply_project_model_overrides()
        self.assertEqual(self.controller.active_weight_name, "backup.pt")
        self.assertFalse(self.controller.use_openvino)

        with self.controller.global_calibration_session():
            self.controller.set_active_weight("best_seg.pt")
            self.controller.set_openvino_usage(True)

        # Overrides should be reapplied after the global session ends
        self.assertEqual(self.controller.active_weight_name, "backup.pt")
        self.assertFalse(self.controller.use_openvino)

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

        @patch("zebtrack.core.controller.threading.Thread")
        @patch("zebtrack.core.controller.ProjectManager.load_zones_from_parquet")
        @patch("zebtrack.core.controller.ProjectManager.scan_input_paths")
        def test_process_pending_project_videos_runs_workflow(
            self, mock_scan, mock_load_zones, mock_thread
        ):
            self.mock_view.reset_mock()
            self.mock_pm.reset_mock()

            self.mock_pm.project_path = "/project"
            self.mock_pm.get_all_videos.return_value = [
                {"path": "/videos/full.mp4", "status": "pending"},
                {"path": "/videos/arena.mp4", "status": "pending"},
            ]

            mock_scan.return_value = [
                {
                    "path": "/videos/full.mp4",
                    "has_arena": True,
                    "has_rois": True,
                    "has_trajectory": True,
                    "has_complete_data": True,
                },
                {
                    "path": "/videos/arena.mp4",
                    "has_arena": True,
                    "has_rois": False,
                    "has_trajectory": False,
                    "has_complete_data": False,
                },
            ]

            mock_load_zones.return_value = ZoneData(
                polygon=[[0, 0], [1, 0], [1, 1], [0, 1]]
            )

            thread_instance = MagicMock()
            mock_thread.return_value = thread_instance

            self.mock_view.show_pending_videos_dialog.return_value = {
                "confirmed": True,
                "include_arena_only": True,
            }

            self.controller.process_pending_project_videos()

            mock_scan.assert_called_once_with(["/videos/full.mp4", "/videos/arena.mp4"])
            self.mock_view.show_pending_videos_dialog.assert_called_once()

            kwargs = mock_thread.call_args.kwargs
            eligible = kwargs["args"][0]
            self.assertEqual(len(eligible), 2)
            self.assertTrue(thread_instance.start.called)

            self.mock_pm.save_zone_data.assert_called()
            self.mock_pm.update_video_status.assert_any_call(
                "/videos/full.mp4",
                "complete",
            )
            self.mock_pm.update_video_status.assert_any_call(
                "/videos/arena.mp4",
                "complete",
            )

            self.mock_view.show_info.assert_any_call(
                "Processamento Iniciado",
                ANY,
            )

        @patch("zebtrack.core.controller.threading.Thread")
        @patch("zebtrack.core.controller.ProjectManager.load_zones_from_parquet")
        @patch("zebtrack.core.controller.ProjectManager.scan_input_paths")
        def test_process_pending_project_videos_excludes_arena_only_when_not_selected(
            self, mock_scan, mock_load_zones, mock_thread
        ):
            self.mock_view.reset_mock()
            self.mock_pm.reset_mock()

            self.mock_pm.project_path = "/project"
            self.mock_pm.get_all_videos.return_value = [
                {"path": "/videos/full.mp4", "status": "pending"},
                {"path": "/videos/arena.mp4", "status": "pending"},
            ]

            mock_scan.return_value = [
                {
                    "path": "/videos/full.mp4",
                    "has_arena": True,
                    "has_rois": True,
                    "has_trajectory": True,
                    "has_complete_data": True,
                },
                {
                    "path": "/videos/arena.mp4",
                    "has_arena": True,
                    "has_rois": False,
                    "has_trajectory": False,
                    "has_complete_data": False,
                },
            ]

            mock_load_zones.return_value = ZoneData(
                polygon=[[0, 0], [1, 0], [1, 1], [0, 1]]
            )

            thread_instance = MagicMock()
            mock_thread.return_value = thread_instance

            self.mock_view.show_pending_videos_dialog.return_value = {
                "confirmed": True,
                "include_arena_only": False,
            }

            self.controller.process_pending_project_videos()

            mock_scan.assert_called_once()
            self.mock_view.show_pending_videos_dialog.assert_called_once()

            mock_thread.assert_called_once()
            self.assertTrue(thread_instance.start.called)

            eligible = mock_thread.call_args.kwargs["args"][0]
            self.assertEqual(len(eligible), 1)
            self.assertEqual(eligible[0]["path"], "/videos/full.mp4")

            self.mock_pm.update_video_status.assert_called_once_with(
                "/videos/full.mp4", "complete"
            )

            self.mock_view.show_info.assert_any_call(
                "Processamento Iniciado",
                ANY,
            )

        @patch("zebtrack.core.controller.threading.Thread")
        @patch("zebtrack.core.controller.ProjectManager.load_zones_from_parquet")
        @patch("zebtrack.core.controller.ProjectManager.scan_input_paths")
        def test_process_pending_project_videos_skip_dialog_for_selection(
            self, mock_scan, mock_load_zones, mock_thread
        ):
            self.mock_view.reset_mock()
            self.mock_pm.reset_mock()

            self.mock_pm.project_path = "/project"
            self.mock_pm.get_all_videos.return_value = [
                {"path": "/videos/full.mp4", "status": "pending"},
                {"path": "/videos/arena.mp4", "status": "pending"},
            ]

            mock_scan.return_value = [
                {
                    "path": "/videos/full.mp4",
                    "has_arena": True,
                    "has_rois": True,
                    "has_trajectory": False,
                    "has_complete_data": False,
                },
                {
                    "path": "/videos/arena.mp4",
                    "has_arena": True,
                    "has_rois": False,
                    "has_trajectory": False,
                    "has_complete_data": False,
                },
            ]

            mock_load_zones.return_value = ZoneData(
                polygon=[[0, 0], [1, 0], [1, 1], [0, 1]]
            )

            thread_instance = MagicMock()
            mock_thread.return_value = thread_instance

            self.controller.process_pending_project_videos(
                ["/videos/full.mp4", "/videos/arena.mp4"]
            )

            self.mock_view.show_pending_videos_dialog.assert_not_called()

            self.mock_view.show_warning.assert_any_call("Processamento", ANY)

            eligible = mock_thread.call_args.kwargs["args"][0]
            self.assertEqual(len(eligible), 1)
            self.assertEqual(eligible[0]["path"], "/videos/full.mp4")

            self.mock_pm.update_video_status.assert_called_once_with(
                "/videos/full.mp4", "complete"
            )

            self.mock_view.show_info.assert_any_call(
                "Processamento Iniciado",
                ANY,
            )

        def test_process_pending_project_videos_without_pending(self):
            self.mock_view.reset_mock()
            self.mock_pm.reset_mock()

            self.mock_pm.project_path = "/project"
            self.mock_pm.get_all_videos.return_value = [
                {"path": "/videos/full.mp4", "status": "complete"}
            ]

            with patch(
                "zebtrack.core.controller.ProjectManager.scan_input_paths"
            ) as mock_scan:
                self.controller.process_pending_project_videos()
                mock_scan.assert_not_called()

            self.mock_view.show_info.assert_called_once()
            title, message = self.mock_view.show_info.call_args[0]
            self.assertEqual(title, "Processamento")
            self.assertIn("Nenhum vídeo pendente", message)

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

            self.mock_arduino_manager.is_connected.side_effect = (
                is_connected_side_effect
            )

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

            self.mock_arduino_manager.is_connected.side_effect = (
                is_connected_side_effect
            )

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
