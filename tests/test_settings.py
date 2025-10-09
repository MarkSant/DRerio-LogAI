import textwrap
import unittest
from unittest.mock import mock_open, patch

from zebtrack.settings import Settings, load_settings


class TestSettings(unittest.TestCase):
    def setUp(self):
        """Prepare a generic, valid YAML content for tests."""
        self.mock_yaml_content = """
camera:
  index: 1
  desired_width: 1280
  desired_height: 720
arduino:
  port: 'COM5'
  baud_rate: 9600
recorder:
  flush_interval_seconds: 3.5
  flush_row_threshold: 250
yolo_model:
  path: 'test.pt'
  confidence_threshold: 0.5
  nms_threshold: 0.5
video_processing:
  fps: 30
  processing_interval: 10
  processing_offset: 1
reproducibility:
  seed: 123
roi_inclusion_rule: "bbox_intersects"
roi_buffer_radius_value: 0.5
roi_min_bbox_overlap_ratio: 0.10
trajectory_smoothing:
  window_length: 7
  polyorder: 3
"""

    def test_load_settings_success_without_zones(self):
        """Test that settings load with default empty zones if section is missing."""
        # Simulate only config.yaml existing
        with patch("pathlib.Path.is_file", side_effect=[True, False]) as mock_is_file:
            with patch(
                "builtins.open", mock_open(read_data=self.mock_yaml_content)
            ) as mock_file:
                settings = load_settings()
                self.assertIsInstance(settings, Settings)
                self.assertEqual(settings.camera.index, 1)
                self.assertEqual(settings.yolo_model.path, "test.pt")
                self.assertEqual(settings.recorder.flush_interval_seconds, 3.5)
                self.assertEqual(settings.recorder.flush_row_threshold, 250)
                # Check that default empty values are created
                self.assertEqual(settings.detection_zones.polygon, [])
                self.assertEqual(settings.detection_zones.roi_polygons, [])
                self.assertEqual(settings.detection_zones.roi_names, [])
                self.assertEqual(settings.detection_zones.roi_colors, [])
                # UI feature flags should fall back to defaults when not specified
                self.assertFalse(
                    settings.ui_features.use_wizard_for_project_creation
                )
                self.assertFalse(settings.ui_features.enable_event_queue)
                # Should check for both default and override files
                self.assertEqual(mock_is_file.call_count, 2)
                # Should only open the default file
                mock_file.assert_called_once()

    def test_load_settings_with_zones(self):
        """Test that settings are loaded correctly when zones are present."""
        yaml_with_zones = """
camera:
  index: 1
  desired_width: 1280
  desired_height: 720
arduino:
  port: 'COM5'
  baud_rate: 9600
recorder:
  flush_interval_seconds: 2.0
  flush_row_threshold: 100
yolo_model:
  path: 'test.pt'
  confidence_threshold: 0.5
  nms_threshold: 0.5
video_processing:
  fps: 30
  processing_interval: 10
  processing_offset: 1
detection_zones:
  polygon:
    - [0, 0]
    - [1, 1]
  roi_polygons:
    - [[10, 20], [30, 40], [15, 30]]
  roi_names: ["ROI1"]
  roi_colors:
    - [255, 0, 0]
reproducibility:
  seed: 123
"""
        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=yaml_with_zones)):
                settings = load_settings()
                self.assertEqual(len(settings.detection_zones.polygon), 2)
                self.assertEqual(
                    settings.detection_zones.roi_polygons[0],
                    [[10, 20], [30, 40], [15, 30]],
                )
                self.assertEqual(settings.detection_zones.roi_names[0], "ROI1")
        self.assertEqual(settings.recorder.flush_interval_seconds, 2.0)
        self.assertEqual(settings.recorder.flush_row_threshold, 100)

    def test_load_settings_file_not_found(self):
        """Test that a FileNotFoundError is raised if the default config is missing."""
        with patch("pathlib.Path.is_file", return_value=False):
            with self.assertRaises(FileNotFoundError):
                load_settings()

    def test_load_settings_validation_error(self):
        """Test that a ValueError is raised for invalid config data."""
        invalid_yaml = """
yolo_model:
  path: 'test.pt'
"""  # Missing several required fields
        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=invalid_yaml)):
                with self.assertRaises(ValueError):
                    load_settings()

    def test_load_settings_with_override(self):
        """Test that override config correctly merges with base config."""
        base_yaml = self.mock_yaml_content
        override_yaml = textwrap.dedent(
            """
            camera:
              index: 99
            yolo_model:
              confidence_threshold: 0.8
            recorder:
              flush_interval_seconds: 4.0
            """
        )

        # This mock handles opening either the base or override file
        def mock_open_side_effect(path, *args, **kwargs):
            if "local" in str(path):
                return mock_open(read_data=override_yaml).return_value
            return mock_open(read_data=base_yaml).return_value

        # Simulate both config.yaml and config.local.yaml existing
        with patch("pathlib.Path.is_file", side_effect=[True, True]):
            with patch("builtins.open", side_effect=mock_open_side_effect):
                settings = load_settings()

                # Check that the override value was applied
                self.assertEqual(settings.camera.index, 99)
                # Check that a non-overridden value from the base is still present
                self.assertEqual(settings.arduino.port, "COM5")
                # Check that a nested value was overridden
                self.assertEqual(settings.yolo_model.confidence_threshold, 0.8)
                # Check that another nested value (not in override) is still present
                self.assertEqual(settings.yolo_model.path, "test.pt")
                # Recorder settings should merge correctly
                self.assertEqual(settings.recorder.flush_interval_seconds, 4.0)
                self.assertEqual(settings.recorder.flush_row_threshold, 250)

    def test_roi_inclusion_settings_defaults(self):
        """Test that ROI inclusion settings have correct defaults."""
        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=self.mock_yaml_content)):
                settings = load_settings()

                # Check default values for ROI inclusion settings
                self.assertEqual(settings.roi_inclusion_rule, "bbox_intersects")
                self.assertEqual(settings.roi_buffer_radius_value, 0.5)
                self.assertEqual(settings.roi_min_bbox_overlap_ratio, 0.10)
                self.assertEqual(settings.trajectory_smoothing.window_length, 7)
                self.assertEqual(settings.trajectory_smoothing.polyorder, 3)

    def test_roi_inclusion_settings_override(self):
        """Test that ROI inclusion settings can be overridden."""
        base_yaml = self.mock_yaml_content
        override_yaml = """
roi_inclusion_rule: "centroid_in"
roi_buffer_radius_value: 1.5
roi_min_bbox_overlap_ratio: 0.25
trajectory_smoothing:
  window_length: 9
  polyorder: 3
"""

        def mock_open_side_effect(path, *args, **kwargs):
            if "local" in str(path):
                return mock_open(read_data=override_yaml)()
            else:
                return mock_open(read_data=base_yaml)()

        with patch("pathlib.Path.is_file", side_effect=[True, True]):
            with patch("builtins.open", side_effect=mock_open_side_effect):
                settings = load_settings()

                # Check overridden values
                self.assertEqual(settings.roi_inclusion_rule, "centroid_in")
                self.assertEqual(settings.roi_buffer_radius_value, 1.5)
                self.assertEqual(settings.roi_min_bbox_overlap_ratio, 0.25)
                self.assertEqual(settings.trajectory_smoothing.window_length, 9)
                self.assertEqual(settings.trajectory_smoothing.polyorder, 3)

    def test_ui_feature_flag_override(self):
        base_yaml = self.mock_yaml_content
        override_yaml = """
ui_features:
  use_wizard_for_project_creation: true
  enable_event_queue: true
"""

        def mock_open_side_effect(path, *args, **kwargs):
            if "local" in str(path):
                return mock_open(read_data=override_yaml)()
            return mock_open(read_data=base_yaml)()

        with patch("pathlib.Path.is_file", side_effect=[True, True]):
            with patch("builtins.open", side_effect=mock_open_side_effect):
                loaded = load_settings()

        self.assertTrue(loaded.ui_features.use_wizard_for_project_creation)
        self.assertTrue(loaded.ui_features.enable_event_queue)

    def test_trajectory_smoothing_validation(self):
        invalid_yaml = self.mock_yaml_content + """
trajectory_smoothing:
  window_length: 6
  polyorder: 5
"""

        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=invalid_yaml)):
                with self.assertRaises(ValueError):
                    load_settings()


if __name__ == "__main__":
    unittest.main()
