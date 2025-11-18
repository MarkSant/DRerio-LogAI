import textwrap
import unittest
from pathlib import Path
from unittest.mock import mock_open, patch

from zebtrack.settings import Settings, export_schema, load_settings, reload_settings


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
            with patch("builtins.open", mock_open(read_data=self.mock_yaml_content)) as mock_file:
                settings = load_settings()
                self.assertIsInstance(settings, Settings)
                self.assertEqual(settings.camera.index, 1)
                self.assertEqual(settings.yolo_model.path, "test.pt")
                self.assertEqual(settings.recorder.flush_interval_seconds, 3.5)
                self.assertEqual(settings.recorder.flush_row_threshold, 250)
                self.assertAlmostEqual(settings.bytetrack.track_threshold, 0.25)
                self.assertAlmostEqual(settings.bytetrack.match_threshold, 0.15)
                self.assertFalse(settings.tracking.use_single_subject_tracker)
                # Check that default empty values are created
                self.assertEqual(settings.detection_zones.polygon, [])
                self.assertEqual(settings.detection_zones.roi_polygons, [])
                self.assertEqual(settings.detection_zones.roi_names, [])
                self.assertEqual(settings.detection_zones.roi_colors, [])
                # UI feature flags should fall back to defaults when not specified
                # Wizard is now the default (v1.6+)
                self.assertTrue(settings.ui_features.use_wizard_for_project_creation)
                # Event queue is opt-in for staged migration
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
              index: 9
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
                self.assertEqual(settings.camera.index, 9)
                # Check that a non-overridden value from the base is still present
                self.assertEqual(settings.arduino.port, "COM5")
                # Check that a nested value was overridden
                self.assertEqual(settings.yolo_model.confidence_threshold, 0.8)
                # Check that another nested value (not in override) is still present
                self.assertEqual(settings.yolo_model.path, "test.pt")
                # Recorder settings should merge correctly
                self.assertEqual(settings.recorder.flush_interval_seconds, 4.0)
                self.assertEqual(settings.recorder.flush_row_threshold, 250)

    def test_bytetrack_override(self):
        base_yaml = self.mock_yaml_content
        override_yaml = textwrap.dedent(
            """
            bytetrack:
              track_threshold: 0.35
              match_threshold: 0.65
            """
        )

        def mock_open_side_effect(path, *args, **kwargs):
            if "local" in str(path):
                return mock_open(read_data=override_yaml)()
            return mock_open(read_data=base_yaml)()

        with patch("pathlib.Path.is_file", side_effect=[True, True]):
            with patch("builtins.open", side_effect=mock_open_side_effect):
                settings = load_settings()

        self.assertAlmostEqual(settings.bytetrack.track_threshold, 0.35)
        self.assertAlmostEqual(settings.bytetrack.match_threshold, 0.65)

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

    def test_tracking_settings_override(self):
        base_yaml = self.mock_yaml_content
        override_yaml = """
tracking:
  use_single_subject_tracker: true
"""

        def mock_open_side_effect(path, *args, **kwargs):
            if "local" in str(path):
                return mock_open(read_data=override_yaml)()
            return mock_open(read_data=base_yaml)()

        with patch("pathlib.Path.is_file", side_effect=[True, True]):
            with patch("builtins.open", side_effect=mock_open_side_effect):
                loaded = load_settings()

        self.assertTrue(loaded.tracking.use_single_subject_tracker)

    def test_trajectory_smoothing_validation(self):
        invalid_yaml = (
            self.mock_yaml_content
            + """
trajectory_smoothing:
  window_length: 6
  polyorder: 5
"""
        )

        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=invalid_yaml)):
                with self.assertRaises(ValueError):
                    load_settings()

    def test_processing_offset_must_be_less_than_interval(self):
        invalid_yaml = (
            self.mock_yaml_content
            + """
video_processing:
  fps: 30
  processing_interval: 5
  processing_offset: 5
"""
        )

        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=invalid_yaml)):
                with self.assertRaises(ValueError):
                    load_settings()

    def test_processing_interval_must_be_positive(self):
        invalid_yaml = (
            self.mock_yaml_content
            + """
video_processing:
  fps: 30
  processing_interval: 0
  processing_offset: 0
"""
        )

        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=invalid_yaml)):
                with self.assertRaises(ValueError):
                    load_settings()

    def test_buffer_radius_requires_positive_value_for_buffered_rule(self):
        invalid_yaml = (
            self.mock_yaml_content
            + """
roi_inclusion_rule: "centroid_in_on_buffered_roi"
roi_buffer_radius_value: 0
"""
        )

        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=invalid_yaml)):
                with self.assertRaises(ValueError):
                    load_settings()

    def test_overlap_ratio_bounds_respected(self):
        invalid_yaml = (
            self.mock_yaml_content
            + """
roi_inclusion_rule: "bbox_intersects"
roi_min_bbox_overlap_ratio: 1.5
"""
        )

        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=invalid_yaml)):
                with self.assertRaises(ValueError):
                    load_settings()

    def test_reload_settings(self):
        """Test that reload_settings() works as expected."""
        base_yaml = self.mock_yaml_content
        override_yaml = """
camera:
  index: 8
"""

        def mock_open_side_effect(path, *args, **kwargs):
            if "local" in str(path):
                return mock_open(read_data=override_yaml)()
            return mock_open(read_data=base_yaml)()

        with patch("pathlib.Path.is_file", side_effect=[True, True]):
            with patch("builtins.open", side_effect=mock_open_side_effect):
                settings = reload_settings()
                self.assertEqual(settings.camera.index, 8)

    def test_export_schema(self):
        """Test that export_schema() generates valid JSON Schema."""
        schema = export_schema()

        # Check that basic schema structure exists
        self.assertIn("properties", schema)
        self.assertIn("$defs", schema)
        self.assertIn("camera", schema["properties"])
        self.assertIn("yolo_model", schema["properties"])

        # Check that CameraSettings is defined in $defs
        self.assertIn("CameraSettings", schema["$defs"])
        camera_def = schema["$defs"]["CameraSettings"]
        self.assertIn("properties", camera_def)
        self.assertIn("index", camera_def["properties"])
        self.assertIn("description", camera_def["properties"]["index"])

    def test_export_schema_to_file(self):
        """Test that export_schema() can write to a file."""
        import json
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            temp_path = Path(f.name)

        try:
            schema = export_schema(temp_path)

            # Verify file was created and contains valid JSON
            self.assertTrue(temp_path.exists())
            with open(temp_path) as f:
                loaded_schema = json.load(f)

            # Should match the returned schema
            self.assertEqual(schema, loaded_schema)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_configdict_forbids_extra_fields(self):
        """Test that extra='forbid' in ConfigDict prevents unknown fields."""
        invalid_yaml = (
            self.mock_yaml_content
            + """
camera:
  index: 1
  unknown_field: "should fail"
"""
        )

        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=invalid_yaml)):
                with self.assertRaises(ValueError) as context:
                    load_settings()
                # Should mention the extra field in the error
                self.assertIn("unknown_field", str(context.exception).lower())

    def test_deep_merge_preserves_nested_values(self):
        """Test that deep merge correctly handles nested dictionaries."""
        base_yaml = self.mock_yaml_content
        # Override only one nested value, others should be preserved
        override_yaml = """
video_processing:
  fps: 60
"""

        def mock_open_side_effect(path, *args, **kwargs):
            if "local" in str(path):
                return mock_open(read_data=override_yaml)()
            return mock_open(read_data=base_yaml)()

        with patch("pathlib.Path.is_file", side_effect=[True, True]):
            with patch("builtins.open", side_effect=mock_open_side_effect):
                settings = load_settings()
                # Overridden value
                self.assertEqual(settings.video_processing.fps, 60)
                # Preserved values from base
                self.assertEqual(settings.video_processing.processing_interval, 10)
                self.assertEqual(settings.video_processing.processing_offset, 1)


if __name__ == "__main__":
    unittest.main()
