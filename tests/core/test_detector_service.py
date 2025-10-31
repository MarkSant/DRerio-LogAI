"""
Tests for DetectorService - Phase 6
"""

import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from zebtrack.core.detector import ZoneData
from zebtrack.core.detector_service import DetectorService
from zebtrack.plugins.base import DetectorPlugin


class MockDetectorPlugin(DetectorPlugin):
    """Mock detector plugin for testing."""

    def __init__(self, model_path: str, expected_hash: str | None = None, settings_obj=None):
        self.model_path = model_path
        self.expected_hash = expected_hash
        self.settings = settings_obj
        self.conf_threshold = 0.25
        self.nms_threshold = 0.45
        self.track_threshold = 0.25
        self.match_threshold = 0.15
        self._context = "tracking"
        self._aquarium_region_defined = False

    def detect(self, frame: np.ndarray):
        return []

    @staticmethod
    def get_name() -> str:
        return "MockPlugin"

    @property
    def model_input_shape(self):
        return (640, 480)

    def set_context(self, context: str):
        self._context = context

    def set_aquarium_region_defined(self, defined: bool):
        self._aquarium_region_defined = defined

    def set_tracking_parameters(self, *, track_threshold=None, match_threshold=None):
        if track_threshold is not None:
            self.track_threshold = float(track_threshold)
        if match_threshold is not None:
            self.match_threshold = float(match_threshold)

    def get_context_info(self):
        return {"context": self._context}

    def reset_tracking_state(self):
        pass


class TestDetectorService(unittest.TestCase):
    """Test suite for DetectorService"""

    def setUp(self):
        """Set up test fixtures."""
        # Create mocks
        self.state_manager = MagicMock()
        self.project_manager = MagicMock()
        self.weight_manager = MagicMock()
        self.model_service = MagicMock()
        self.settings = MagicMock()

        # Create service
        self.service = DetectorService(
            state_manager=self.state_manager,
            project_manager=self.project_manager,
            weight_manager=self.weight_manager,
            model_service=self.model_service,
            settings_obj=self.settings,
        )

        # Setup mock detector plugins with correct names
        self.mock_plugins = {
            "YOLO (Ultralytics)": MockDetectorPlugin,
            "OpenVINO": MockDetectorPlugin,
            "MockPlugin": MockDetectorPlugin,
        }

    def test_initialization(self):
        """Test service initialization."""
        self.assertIsNotNone(self.service)
        self.assertIsNone(self.service.detector)
        self.assertEqual(self.service.state_manager, self.state_manager)
        self.assertEqual(self.service.project_manager, self.project_manager)

    @patch("zebtrack.core.detector_service.Detector")
    def test_initialize_detector_success(self, mock_detector_class):
        """Test successful detector initialization."""
        # Setup mocks
        self.settings.model_selection.animal_method = "det"
        self.settings.camera.desired_width = 1280
        self.settings.camera.desired_height = 720
        self.settings.tracking.use_single_subject_tracker = False

        self.weight_manager.get_weight_path_by_method.return_value = "/path/to/model.pt"
        self.model_service.find_weight_by_path.return_value = (
            "test_weight",
            {"path": "/path/to/model.pt"},
        )

        # Mock detector instance
        mock_detector_instance = MagicMock()
        mock_detector_class.return_value = mock_detector_instance

        # Execute
        with patch("os.path.exists", return_value=True):
            success, error = self.service.initialize_detector(
                animal_method="det",
                use_openvino=False,
                active_weight_name="test_weight",
                detector_plugins=self.mock_plugins,
            )

        # Verify
        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertIsNotNone(self.service.detector)
        self.state_manager.update_detector_state.assert_called_once()

    def test_initialize_detector_no_model_path(self):
        """Test detector initialization fails when no model path found."""
        self.settings.model_selection.animal_method = "det"
        self.weight_manager.get_weight_path_by_method.return_value = None

        # Execute
        success, error = self.service.initialize_detector(
            animal_method="det",
            use_openvino=False,
            detector_plugins=self.mock_plugins,
        )

        # Verify
        self.assertFalse(success)
        self.assertIsNotNone(error)
        self.assertIn("Nenhum modelo", error)

    def test_initialize_detector_weight_not_found(self):
        """Test detector initialization fails when weight not found."""
        self.settings.model_selection.animal_method = "det"
        self.weight_manager.get_weight_path_by_method.return_value = "/path/to/model.pt"
        self.model_service.find_weight_by_path.return_value = (None, None)

        # Execute
        success, error = self.service.initialize_detector(
            animal_method="det",
            use_openvino=False,
            detector_plugins=self.mock_plugins,
        )

        # Verify
        self.assertFalse(success)
        self.assertIsNotNone(error)
        self.assertIn("peso correspondente", error)

    @patch("zebtrack.core.detector_service.Detector")
    def test_initialize_detector_with_openvino(self, mock_detector_class):
        """Test detector initialization with OpenVINO."""
        # Setup mocks
        self.settings.model_selection.animal_method = "det"
        self.settings.camera.desired_width = 1280
        self.settings.camera.desired_height = 720
        self.settings.tracking.use_single_subject_tracker = False

        self.weight_manager.get_weight_path_by_method.return_value = "/path/to/model.pt"
        self.model_service.find_weight_by_path.return_value = (
            "test_weight",
            {"path": "/path/to/model.pt", "openvino_hash": "abc123"},
        )
        self.model_service.get_model_path_for_inference.return_value = (
            "/path/to/openvino",
            {"openvino_hash": "abc123"},
        )

        # Mock detector plugins with OpenVINO
        mock_openvino_plugin = MockDetectorPlugin
        plugins_with_openvino = {
            "OpenVINO": mock_openvino_plugin,
            "YOLO (Ultralytics)": MockDetectorPlugin,
        }

        # Execute
        success, error = self.service.initialize_detector(
            animal_method="det",
            use_openvino=True,
            active_weight_name="test_weight",
            detector_plugins=plugins_with_openvino,
        )

        # Verify
        self.assertTrue(success)
        self.assertIsNone(error)

    @patch("zebtrack.core.detector_service.Detector")
    def test_initialize_detector_openvino_path_not_found(self, mock_detector_class):
        """Test detector initialization fails when OpenVINO path not found."""
        self.settings.model_selection.animal_method = "det"
        self.weight_manager.get_weight_path_by_method.return_value = "/path/to/model.pt"
        self.model_service.find_weight_by_path.return_value = (
            "test_weight",
            {"path": "/path/to/model.pt"},
        )
        self.model_service.get_model_path_for_inference.return_value = (None, None)

        # Execute
        success, error = self.service.initialize_detector(
            animal_method="det",
            use_openvino=True,
            detector_plugins=self.mock_plugins,
        )

        # Verify
        self.assertFalse(success)
        self.assertIsNotNone(error)

    def test_configure_zones_no_detector(self):
        """Test configure zones fails when no detector."""
        zone_data = ZoneData(polygon=[[0, 0], [100, 100]])

        # Execute
        result = self.service.configure_zones(zone_data, 1280, 720)

        # Verify
        self.assertFalse(result)

    def test_configure_zones_with_detector(self):
        """Test configure zones with detector."""
        # Setup
        self.settings.camera.desired_width = 1280
        self.settings.camera.desired_height = 720

        mock_detector = MagicMock()
        mock_plugin = MagicMock()
        mock_plugin.get_name.return_value = "TestPlugin"
        mock_detector.plugin = mock_plugin

        self.service.detector = mock_detector
        zone_data = ZoneData(polygon=[[0, 0], [100, 100]])

        # Execute
        result = self.service.configure_zones(zone_data, 1280, 720)

        # Verify
        self.assertTrue(result)
        mock_detector.set_zones.assert_called_once_with(zone_data, 1280, 720)
        mock_detector.set_aquarium_region_defined.assert_called_once_with(True)

    def test_configure_zones_loads_from_project(self):
        """Test configure zones loads from project when not provided."""
        self.settings.camera.desired_width = 1280
        self.settings.camera.desired_height = 720

        mock_detector = MagicMock()
        self.service.detector = mock_detector

        zone_data = ZoneData(polygon=[[0, 0], [100, 100]])
        self.project_manager.get_zone_data.return_value = zone_data

        # Execute (no zone_data provided)
        result = self.service.configure_zones()

        # Verify
        self.assertTrue(result)
        self.project_manager.get_zone_data.assert_called_once()
        mock_detector.set_zones.assert_called_once()

    def test_update_tracking_parameters_no_detector(self):
        """Test update parameters works without detector."""
        self.project_manager.project_data = {}

        # Execute
        result = self.service.update_tracking_parameters(
            params={"conf_threshold": 0.5, "track_threshold": 0.3}
        )

        # Verify
        self.assertTrue(result)

    def test_update_tracking_parameters_with_detector(self):
        """Test update parameters with detector."""
        # Setup
        mock_detector = MagicMock()
        mock_plugin = MockDetectorPlugin("/path/to/model.pt")
        mock_detector.plugin = mock_plugin
        self.service.detector = mock_detector

        self.project_manager.save_detector_state.return_value = True

        # Execute
        result = self.service.update_tracking_parameters(
            conf_threshold=0.5, nms_threshold=0.7, track_threshold=0.3, match_threshold=0.2
        )

        # Verify
        self.assertTrue(result)
        self.assertEqual(mock_plugin.conf_threshold, 0.5)
        self.assertEqual(mock_plugin.nms_threshold, 0.7)
        self.assertEqual(mock_plugin.track_threshold, 0.3)
        self.assertEqual(mock_plugin.match_threshold, 0.2)

    def test_update_tracking_parameters_invalid_values(self):
        """Test update parameters validates threshold ranges."""
        # Execute and verify each parameter
        with self.assertRaises(ValueError):
            self.service.update_tracking_parameters(conf_threshold=1.5)

        with self.assertRaises(ValueError):
            self.service.update_tracking_parameters(nms_threshold=-0.1)

        with self.assertRaises(ValueError):
            self.service.update_tracking_parameters(track_threshold=2.0)

    def test_reset_tracking_state_no_detector(self):
        """Test reset tracking state with no detector."""
        # Should not raise error
        self.service.reset_tracking_state()

    def test_reset_tracking_state_with_detector(self):
        """Test reset tracking state with detector."""
        mock_detector = MagicMock()
        self.service.detector = mock_detector

        # Execute
        self.service.reset_tracking_state()

        # Verify
        mock_detector.reset_tracking_state.assert_called_once()

    def test_set_single_subject_mode_no_detector(self):
        """Test set single subject mode with no detector."""
        # Should not raise error
        self.service.set_single_subject_mode(True)

    def test_set_single_subject_mode_with_detector(self):
        """Test set single subject mode with detector."""
        mock_detector = MagicMock()
        self.service.detector = mock_detector

        # Execute
        self.service.set_single_subject_mode(True)

        # Verify
        mock_detector.set_single_subject_mode.assert_called_once_with(True)

    def test_get_detector_parameters_defaults(self):
        """Test get detector parameters returns defaults."""
        self.settings.yolo_model.confidence_threshold = 0.25
        self.settings.yolo_model.nms_threshold = 0.45
        mock_bytetrack = MagicMock()
        mock_bytetrack.track_threshold = 0.25
        mock_bytetrack.match_threshold = 0.15
        self.settings.bytetrack = mock_bytetrack

        self.project_manager.project_data = {}

        # Execute
        params = self.service.get_detector_parameters()

        # Verify
        self.assertEqual(params["conf_threshold"], 0.25)
        self.assertEqual(params["nms_threshold"], 0.45)
        self.assertEqual(params["track_threshold"], 0.25)
        self.assertEqual(params["match_threshold"], 0.15)

    def test_get_detector_parameters_with_overrides(self):
        """Test get detector parameters with project overrides."""
        self.settings.yolo_model.confidence_threshold = 0.25
        self.settings.yolo_model.nms_threshold = 0.45

        self.project_manager.project_data = {
            "detector_state": {
                "conf_threshold": 0.5,
                "track_threshold": 0.3,
            }
        }

        # Execute
        params = self.service.get_detector_parameters()

        # Verify
        self.assertEqual(params["conf_threshold"], 0.5)
        self.assertEqual(params["track_threshold"], 0.3)

    def test_get_factory_detector_parameters(self):
        """Test get factory detector parameters."""
        self.settings.yolo_model.confidence_threshold = 0.25
        self.settings.yolo_model.nms_threshold = 0.45
        mock_bytetrack = MagicMock()
        mock_bytetrack.track_threshold = 0.25
        mock_bytetrack.match_threshold = 0.15
        self.settings.bytetrack = mock_bytetrack

        # Execute
        params = self.service.get_factory_detector_parameters()

        # Verify
        self.assertEqual(params["conf_threshold"], 0.25)
        self.assertEqual(params["nms_threshold"], 0.45)
        self.assertEqual(params["track_threshold"], 0.25)
        self.assertEqual(params["match_threshold"], 0.15)

    def test_restore_detector_settings_no_detector(self):
        """Test restore settings with no detector."""
        # Should not raise error
        self.service.restore_detector_settings({})

    def test_restore_detector_settings_with_detector(self):
        """Test restore detector settings with detector."""
        # Setup
        mock_detector = MagicMock()
        mock_plugin = MockDetectorPlugin("/path/to/model.pt")
        mock_detector.plugin = mock_plugin
        self.service.detector = mock_detector

        config = {
            "confidence_threshold": 0.6,
            "nms_threshold": 0.5,
            "track_threshold": 0.4,
            "match_threshold": 0.2,
        }

        # Execute
        self.service.restore_detector_settings(config)

        # Verify
        self.assertEqual(mock_plugin.conf_threshold, 0.6)
        self.assertEqual(mock_plugin.nms_threshold, 0.5)
        self.assertEqual(mock_plugin.track_threshold, 0.4)
        self.assertEqual(mock_plugin.match_threshold, 0.2)

    def test_build_detector_config(self):
        """Test build detector config."""
        mock_plugin = MockDetectorPlugin("/path/to/model.pt")
        mock_plugin.conf_threshold = 0.5
        mock_plugin.nms_threshold = 0.7
        mock_plugin.track_threshold = 0.3
        mock_plugin.match_threshold = 0.2

        # Execute
        config = self.service._build_detector_config(mock_plugin, use_openvino=False)

        # Verify
        self.assertEqual(config["plugin_name"], "YOLO (Ultralytics)")
        self.assertEqual(config["confidence_threshold"], 0.5)
        self.assertEqual(config["nms_threshold"], 0.7)
        self.assertEqual(config["track_threshold"], 0.3)
        self.assertEqual(config["match_threshold"], 0.2)
        self.assertEqual(config["context"], "tracking")

    def test_build_detector_config_openvino(self):
        """Test build detector config for OpenVINO."""
        mock_plugin = MockDetectorPlugin("/path/to/model.xml")

        # Execute
        config = self.service._build_detector_config(mock_plugin, use_openvino=True)

        # Verify
        self.assertEqual(config["plugin_name"], "OpenVINO")

    def test_persist_global_detector_defaults(self):
        """Test persist global detector defaults."""
        self.settings.yolo_model = MagicMock()
        mock_bytetrack = MagicMock()
        self.settings.bytetrack = mock_bytetrack

        config = {
            "conf_threshold": 0.5,
            "nms_threshold": 0.6,
            "track_threshold": 0.3,
            "match_threshold": 0.2,
        }

        # Execute
        self.service._persist_global_detector_defaults(config, reset=False)

        # Verify
        self.assertEqual(self.settings.yolo_model.confidence_threshold, 0.5)
        self.assertEqual(self.settings.yolo_model.nms_threshold, 0.6)
        self.assertEqual(mock_bytetrack.track_threshold, 0.3)
        self.assertEqual(mock_bytetrack.match_threshold, 0.2)

    def test_persist_global_detector_defaults_reset(self):
        """Test persist global detector defaults with reset."""
        self.settings.yolo_model = MagicMock()
        self.settings.yolo_model.confidence_threshold = 0.25
        self.settings.yolo_model.nms_threshold = 0.45
        mock_bytetrack = MagicMock()
        mock_bytetrack.track_threshold = 0.25
        mock_bytetrack.match_threshold = 0.15
        self.settings.bytetrack = mock_bytetrack

        # Execute
        self.service._persist_global_detector_defaults({}, reset=True)

        # Verify reset was called (values should be factory defaults)
        # The method should have called get_factory_detector_parameters()

    def test_resolve_single_subject_tracker_preference_no_project(self):
        """Test resolve tracker preference with no project."""
        self.project_manager.project_data = None

        # Execute
        pref = self.service._resolve_single_subject_tracker_preference(None)

        # Verify
        self.assertIsNone(pref)

    def test_resolve_single_subject_tracker_preference_from_project(self):
        """Test resolve tracker preference from project."""
        self.project_manager.project_data = {"use_single_subject_tracker": True}

        # Execute
        pref = self.service._resolve_single_subject_tracker_preference(None)

        # Verify
        self.assertTrue(pref)

    def test_resolve_single_subject_tracker_preference_single_video(self):
        """Test resolve tracker preference for single video project."""
        self.project_manager.project_data = {}

        # Execute
        pref = self.service._resolve_single_subject_tracker_preference("single-video")

        # Verify
        self.assertTrue(pref)


if __name__ == "__main__":
    unittest.main()
