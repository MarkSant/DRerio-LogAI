import logging
from unittest.mock import patch

import pytest
import yaml

from zebtrack.logging_config import configure_logging_levels
from zebtrack.settings import load_settings


@pytest.fixture
def mock_config_file(tmp_path):
    """Create a temporary config.yaml file."""
    config_path = tmp_path / "config.yaml"

    def _create_config(data):
        with open(config_path, "w") as f:
            yaml.dump(data, f)
        return config_path

    return _create_config


@pytest.mark.skip(reason="Needs refactoring for DI architecture - settings is no longer a module variable")
def test_configure_logging_levels_from_settings(mock_config_file):
    """Test that loggers are configured correctly based on settings."""
    config_data = {
        "camera": {"index": 0, "desired_width": 1, "desired_height": 1},
        "arduino": {"port": "COM1", "baud_rate": 9600},
        "yolo_model": {
            "path": "test.pt",
            "confidence_threshold": 0.5,
            "nms_threshold": 0.5,
        },
        "video_processing": {"fps": 30, "processing_interval": 1, "processing_offset": 0},
        "reproducibility": {"seed": 42},
        "logging": {
            "levels": {
                "zebtrack.core.detector": "DEBUG",
                "zebtrack.ui": "WARNING",
                "zebtrack.io": "ERROR",
            }
        },
    }
    config_path = mock_config_file(config_data)
    settings = load_settings(config_path)

    with patch("zebtrack.logging_config.settings", settings):
        configure_logging_levels()

        assert logging.getLogger("zebtrack.core.detector").level == logging.DEBUG
        assert logging.getLogger("zebtrack.ui").level == logging.WARNING
        assert logging.getLogger("zebtrack.io").level == logging.ERROR
        assert logging.getLogger("zebtrack.analysis").level in (
            logging.INFO,
            logging.NOTSET,
        )


def test_validate_invalid_log_level(mock_config_file):
    """Test that settings validation fails with an invalid log level string."""
    config_data = {
        "camera": {"index": 0, "desired_width": 1, "desired_height": 1},
        "arduino": {"port": "COM1", "baud_rate": 9600},
        "yolo_model": {
            "path": "test.pt",
            "confidence_threshold": 0.5,
            "nms_threshold": 0.5,
        },
        "video_processing": {"fps": 30, "processing_interval": 1, "processing_offset": 0},
        "reproducibility": {"seed": 42},
        "logging": {"levels": {"zebtrack.core.detector": "INVALID_LEVEL"}},
    }
    config_path = mock_config_file(config_data)

    with pytest.raises(ValueError) as excinfo:
        load_settings(config_path)
    assert "Invalid log level 'INVALID_LEVEL'" in str(excinfo.value)


@pytest.mark.skip(reason="Needs refactoring for DI architecture - settings is no longer a module variable")
@patch("sys.argv", ["__main__.py", "--log-level", "zebtrack.core.detector=DEBUG"])
def test_cli_override(mock_config_file):
    """Test that CLI argument overrides the config file setting."""
    config_data = {
        "camera": {"index": 0, "desired_width": 1, "desired_height": 1},
        "arduino": {"port": "COM1", "baud_rate": 9600},
        "yolo_model": {
            "path": "test.pt",
            "confidence_threshold": 0.5,
            "nms_threshold": 0.5,
        },
        "video_processing": {"fps": 30, "processing_interval": 1, "processing_offset": 0},
        "reproducibility": {"seed": 42},
        "logging": {"levels": {"zebtrack.core.detector": "INFO"}},
    }
    config_path = mock_config_file(config_data)
    settings = load_settings(config_path)

    with patch("zebtrack.__main__.settings", settings):
        from zebtrack.__main__ import main

        with patch("zebtrack.__main__.tk.Tk"), patch("zebtrack.__main__.MainViewModel"):
            main()

        assert logging.getLogger("zebtrack.core.detector").level == logging.DEBUG
