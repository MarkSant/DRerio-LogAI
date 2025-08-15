import unittest
from unittest.mock import mock_open, patch

import yaml

from zebtrack.settings import Settings, load_settings


class TestSettings(unittest.TestCase):
    def test_load_settings_success(self):
        """Test that settings are loaded correctly from a valid YAML file."""
        # This YAML content is carefully structured to be parsed correctly.
        mock_yaml_content = """
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
    - - [0, 0]
      - [1, 1]
  colors:
    - [255, 0, 0]
  enter_commands: [1]
  exit_commands: [2]
"""
        # Use mock_open to simulate the presence of the config file
        with patch("pathlib.Path.is_file", return_value=True):
            with patch(
                "builtins.open", mock_open(read_data=mock_yaml_content)
            ) as mock_file:
                settings = load_settings()
                self.assertIsInstance(settings, Settings)
                self.assertEqual(settings.camera.index, 1)
                self.assertEqual(settings.yolo_model.path, "test.pt")
                # Ensure the complex structure is parsed correctly
                self.assertEqual(settings.detection_zones.squares[0], ((0, 0), (1, 1)))
                mock_file.assert_called_once()

    def test_load_settings_file_not_found(self):
        """Test that a FileNotFoundError is raised if the config file is missing."""
        with patch("pathlib.Path.is_file", return_value=False):
            with self.assertRaises(FileNotFoundError):
                load_settings()

    def test_load_settings_validation_error(self):
        """Test that a ValueError is raised for invalid config data."""
        # YAML content is missing the required 'camera' section
        mock_yaml_content = """
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
  polygon: [[0, 0]]
  squares: [[(0,0), (1,1)]]
  colors: [[255,0,0]]
  enter_commands: [1]
  exit_commands: [2]
"""
        with patch("pathlib.Path.is_file", return_value=True):
            with patch("builtins.open", mock_open(read_data=mock_yaml_content)):
                with self.assertRaises(ValueError):
                    load_settings()


if __name__ == "__main__":
    unittest.main()
