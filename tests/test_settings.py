import unittest
from unittest.mock import mock_open, patch

import yaml

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
  squares:
    - [[0, 0], [1, 1]]
  colors:
    - [255, 0, 0]
  enter_commands: [1]
  exit_commands: [2]
reproducibility:
  seed: 123
"""

    def test_load_settings_success(self):
        """Test that settings are loaded correctly from a single valid YAML file."""
        # Simulate only config.yaml existing
        with patch("pathlib.Path.is_file", side_effect=[True, False]) as mock_is_file:
            with patch(
                "builtins.open", mock_open(read_data=self.mock_yaml_content)
            ) as mock_file:
                settings = load_settings()
                self.assertIsInstance(settings, Settings)
                self.assertEqual(settings.camera.index, 1)
                self.assertEqual(settings.yolo_model.path, "test.pt")
                self.assertEqual(
                    settings.detection_zones.squares[0], ((0, 0), (1, 1))
                )
                # Should check for both default and override files
                self.assertEqual(mock_is_file.call_count, 2)
                # Should only open the default file
                mock_file.assert_called_once()

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
        override_yaml = """
camera:
  index: 99
yolo_model:
  confidence_threshold: 0.8
"""

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


if __name__ == "__main__":
    unittest.main()
