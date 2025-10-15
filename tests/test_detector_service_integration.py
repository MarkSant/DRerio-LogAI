"""
Integration tests for DetectorService + Controller.

Phase 6: Tests the integration between DetectorService and Controller
to ensure proper communication and workflow execution.

These tests verify:
- Full detector initialization workflow through controller
- Zone configuration propagation
- Parameter update coordination
- State synchronization between services
"""

import unittest
from unittest.mock import MagicMock, patch

from zebtrack.core.controller import AppController
from zebtrack.core.detector import ZoneData


class MockDetectorPlugin:
    """Mock detector plugin for integration testing."""

    def __init__(self, model_path: str, expected_hash: str | None = None):
        self.model_path = model_path
        self.expected_hash = expected_hash
        self.conf_threshold = 0.25
        self.nms_threshold = 0.45
        self.track_threshold = 0.25
        self.match_threshold = 0.15
        self._context = "tracking"
        self._aquarium_region_defined = False

    @staticmethod
    def get_name():
        return "MockPlugin"

    def set_context(self, context: str):
        self._context = context

    def set_tracking_parameters(self, *, track_threshold=None, match_threshold=None):
        if track_threshold is not None:
            self.track_threshold = track_threshold
        if match_threshold is not None:
            self.match_threshold = match_threshold

    def set_aquarium_region_defined(self, defined: bool):
        self._aquarium_region_defined = defined

    def get_context_info(self):
        return {"context": self._context}


class TestDetectorServiceIntegration(unittest.TestCase):
    """Integration tests for DetectorService and Controller."""

    @patch("zebtrack.core.controller.WeightManager")
    @patch("zebtrack.core.controller.ProjectManager")
    @patch("zebtrack.core.controller.ApplicationGUI")
    def setUp(self, mock_gui, mock_pm, mock_wm):
        """Set up test environment."""
        self.root = MagicMock()
        self.root.after = MagicMock()
        self.root.after_cancel = MagicMock()

        # Configure mocks
        self.mock_view = mock_gui.return_value
        self.mock_pm = mock_pm.return_value
        self.mock_wm = mock_wm.return_value

        # Configure WeightManager
        self.mock_wm.get_default_weight.return_value = ("best_seg.pt", "/fake/path/best_seg.pt")
        self.mock_wm.get_all_weights.return_value = ["best_seg.pt"]
        self.mock_wm.get_weight_path_by_method.return_value = "/fake/path/best_seg.pt"
        self.mock_wm.get_weight_details.return_value = {
            "path": "/fake/path/best_seg.pt",
            "type": "seg",
        }

        # Configure ProjectManager
        self.mock_pm.project_path = None
        self.mock_pm.project_data = {}
        self.mock_pm.save_detector_state.return_value = True

        # Create controller
        self.controller = AppController(self.root)
        self.controller.project_manager = self.mock_pm
        self.controller.view = self.mock_view
        self.controller.weight_manager = self.mock_wm

        # Mock detector plugins
        self.mock_detector_plugins = {
            "YOLO (Ultralytics)": MockDetectorPlugin,
            "OpenVINO": MockDetectorPlugin,
        }

    def test_detector_initialization_workflow(self):
        """Test complete detector initialization through controller."""
        with (
            patch("os.path.exists", return_value=True),
            patch.object(
                self.controller.model_service,
                "find_weight_by_path",
                return_value=("best_seg.pt", {"path": "/fake/path/best_seg.pt", "type": "seg"}),
            ),
        ):
            # Initialize detector through controller
            success, error = self.controller.detector_service.initialize_detector(
                animal_method="seg",
                use_openvino=False,
                active_weight_name="best_seg.pt",
                detector_plugins=self.mock_detector_plugins,
            )

        # Verify success
        self.assertTrue(success)
        self.assertIsNone(error)

        # Verify detector was created
        self.assertIsNotNone(self.controller.detector)
        self.assertIsNotNone(self.controller.detector.plugin)

        # Verify plugin configuration
        plugin = self.controller.detector.plugin
        self.assertEqual(plugin.get_name(), "MockPlugin")
        self.assertEqual(plugin._context, "tracking")

        # Verify state was updated
        detector_state = self.controller.state_manager.get_detector_state()
        self.assertTrue(detector_state.detector_initialized)
        self.assertEqual(detector_state.active_weight_name, "best_seg.pt")
        self.assertFalse(detector_state.use_openvino)

        # Verify detector state was saved to project
        self.mock_pm.save_detector_state.assert_called_once()
        saved_config = self.mock_pm.save_detector_state.call_args.args[0]
        self.assertEqual(saved_config["plugin_name"], "YOLO (Ultralytics)")
        self.assertIn("confidence_threshold", saved_config)

    def test_zone_configuration_propagation(self):
        """Test zone configuration propagates to detector plugin."""
        # Initialize detector first
        with (
            patch("os.path.exists", return_value=True),
            patch.object(
                self.controller.model_service,
                "find_weight_by_path",
                return_value=("best_seg.pt", {"path": "/fake/path/best_seg.pt", "type": "seg"}),
            ),
        ):
            self.controller.detector_service.initialize_detector(
                animal_method="seg",
                use_openvino=False,
                active_weight_name="best_seg.pt",
                detector_plugins=self.mock_detector_plugins,
            )

        # Configure zones
        zone_data = ZoneData(
            polygon=[[0, 0], [800, 0], [800, 600], [0, 600]],
            roi_polygons=[[[100, 100], [200, 100], [200, 200], [100, 200]]],
            roi_names=["ROI1"],
            roi_colors=[(255, 0, 0)],
        )

        success = self.controller.detector_service.configure_zones(
            zone_data=zone_data, width=800, height=600
        )

        # Verify success
        self.assertTrue(success)

        # Verify plugin was notified about aquarium region
        plugin = self.controller.detector.plugin
        self.assertTrue(plugin._aquarium_region_defined)

    def test_parameter_update_coordination(self):
        """Test parameter updates coordinate between controller and service."""
        # Initialize detector
        with (
            patch("os.path.exists", return_value=True),
            patch.object(
                self.controller.model_service,
                "find_weight_by_path",
                return_value=("best_seg.pt", {"path": "/fake/path/best_seg.pt", "type": "seg"}),
            ),
        ):
            self.controller.detector_service.initialize_detector(
                animal_method="seg",
                use_openvino=False,
                active_weight_name="best_seg.pt",
                detector_plugins=self.mock_detector_plugins,
            )

        # Update parameters through controller
        new_params = {
            "confidence_threshold": 0.35,
            "nms_threshold": 0.55,
            "track_threshold": 0.30,
            "match_threshold": 0.20,
        }

        success = self.controller.update_detector_parameters(new_params)

        # Verify success
        self.assertTrue(success)

        # Verify plugin was updated
        plugin = self.controller.detector.plugin
        self.assertAlmostEqual(plugin.conf_threshold, 0.35)
        self.assertAlmostEqual(plugin.nms_threshold, 0.55)
        self.assertAlmostEqual(plugin.track_threshold, 0.30)
        self.assertAlmostEqual(plugin.match_threshold, 0.20)

        # Verify changes were saved to project
        self.assertEqual(
            self.mock_pm.save_detector_state.call_count, 2
        )  # Once on init, once on update

    def test_get_parameters_returns_plugin_values(self):
        """Test get_current_detector_parameters returns actual plugin values."""
        # Initialize detector
        with (
            patch("os.path.exists", return_value=True),
            patch.object(
                self.controller.model_service,
                "find_weight_by_path",
                return_value=("best_seg.pt", {"path": "/fake/path/best_seg.pt", "type": "seg"}),
            ),
        ):
            self.controller.detector_service.initialize_detector(
                animal_method="seg",
                use_openvino=False,
                active_weight_name="best_seg.pt",
                detector_plugins=self.mock_detector_plugins,
            )

        # Manually change plugin values
        plugin = self.controller.detector.plugin
        plugin.conf_threshold = 0.42
        plugin.nms_threshold = 0.62
        plugin.track_threshold = 0.32
        plugin.match_threshold = 0.22

        # Get parameters through controller
        params = self.controller.get_current_detector_parameters()

        # Verify we get the actual plugin values (with long-form names)
        self.assertAlmostEqual(params["confidence_threshold"], 0.42)
        self.assertAlmostEqual(params["nms_threshold"], 0.62)
        self.assertAlmostEqual(params["track_threshold"], 0.32)
        self.assertAlmostEqual(params["match_threshold"], 0.22)

    def test_detector_property_delegation(self):
        """Test detector property properly delegates to DetectorService."""
        # Initially no detector
        self.assertIsNone(self.controller.detector)

        # Initialize detector
        with (
            patch("os.path.exists", return_value=True),
            patch.object(
                self.controller.model_service,
                "find_weight_by_path",
                return_value=("best_seg.pt", {"path": "/fake/path/best_seg.pt", "type": "seg"}),
            ),
        ):
            self.controller.detector_service.initialize_detector(
                animal_method="seg",
                use_openvino=False,
                active_weight_name="best_seg.pt",
                detector_plugins=self.mock_detector_plugins,
            )

        # Verify detector property works
        self.assertIsNotNone(self.controller.detector)
        self.assertEqual(self.controller.detector.plugin.get_name(), "MockPlugin")

        # Verify setter works (for testing)
        mock_detector = MagicMock()
        self.controller.detector = mock_detector
        self.assertEqual(self.controller.detector_service.detector, mock_detector)

    def test_single_subject_mode_configuration(self):
        """Test single-subject mode configuration through service."""
        # Initialize detector
        with (
            patch("os.path.exists", return_value=True),
            patch.object(
                self.controller.model_service,
                "find_weight_by_path",
                return_value=("best_seg.pt", {"path": "/fake/path/best_seg.pt", "type": "seg"}),
            ),
        ):
            self.controller.detector_service.initialize_detector(
                animal_method="seg",
                use_openvino=False,
                active_weight_name="best_seg.pt",
                detector_plugins=self.mock_detector_plugins,
            )

        # Configure single-subject mode
        self.controller.detector_service.set_single_subject_mode(True)

        # Verify mode was set on detector
        self.assertTrue(self.controller.detector.is_single_subject_mode())

        # Change to multi-subject mode
        self.controller.detector_service.set_single_subject_mode(False)
        self.assertFalse(self.controller.detector.is_single_subject_mode())

    def test_reset_tracking_state(self):
        """Test reset tracking state through service."""
        # Initialize detector
        with (
            patch("os.path.exists", return_value=True),
            patch.object(
                self.controller.model_service,
                "find_weight_by_path",
                return_value=("best_seg.pt", {"path": "/fake/path/best_seg.pt", "type": "seg"}),
            ),
        ):
            self.controller.detector_service.initialize_detector(
                animal_method="seg",
                use_openvino=False,
                active_weight_name="best_seg.pt",
                detector_plugins=self.mock_detector_plugins,
            )

        # Mock the detector's reset method
        self.controller.detector.reset_tracking_state = MagicMock()

        # Reset tracking state
        self.controller.detector_service.reset_tracking_state()

        # Verify reset was called
        self.controller.detector.reset_tracking_state.assert_called_once()

    def test_parameter_updates_without_detector(self):
        """Test parameter updates work even without detector."""
        # No detector initialized
        self.assertIsNone(self.controller.detector)

        # Update parameters
        new_params = {
            "confidence_threshold": 0.35,
            "nms_threshold": 0.55,
            "track_threshold": 0.30,
            "match_threshold": 0.20,
        }

        success = self.controller.update_detector_parameters(new_params)

        # Verify success
        self.assertTrue(success)

        # Parameters should be retrievable (from defaults)
        params = self.controller.get_current_detector_parameters()
        self.assertIn("confidence_threshold", params)
        self.assertIn("nms_threshold", params)


if __name__ == "__main__":
    unittest.main()
