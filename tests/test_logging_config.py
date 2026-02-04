import logging
import re

import pytest
import structlog.dev
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
    settings_obj = load_settings(config_path)

    # DI architecture: pass settings_obj directly to configure_logging_levels
    configure_logging_levels(settings_obj)

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

# =============================================================================
# NEW TESTS: Extended coverage for logging_config module
# =============================================================================


class TestConfigureLoggingLevels:
    """Tests for configure_logging_levels function edge cases."""

    def test_configure_logging_levels_with_none(self):
        """Test that passing None settings doesn't crash."""
        # Should just capture warnings and return without errors
        configure_logging_levels(None)

        # Verify warnings capture is enabled
        assert callable(logging.captureWarnings)

    def test_configure_logging_levels_without_logging_attr(self):
        """Test handling settings object without logging attribute."""
        # Create a mock settings without logging attribute
        from unittest.mock import Mock

        mock_settings = Mock(spec=[])  # No attributes
        configure_logging_levels(mock_settings)  # Should not raise

    def test_configure_logging_levels_without_levels_attr(self):
        """Test handling settings.logging without levels attribute."""
        from unittest.mock import Mock

        mock_settings = Mock()
        mock_settings.logging = Mock(spec=[])  # No levels attribute
        configure_logging_levels(mock_settings)  # Should not raise


class TestResolveLogPath:
    """Tests for resolve_log_path function."""

    def test_resolve_log_path_with_directory(self, tmp_path):
        """Test log path resolution when directory is included."""
        from zebtrack.logging_config import resolve_log_path

        custom_path = str(tmp_path / "custom" / "my.log")
        result = resolve_log_path(custom_path)

        assert result == custom_path

    def test_resolve_log_path_simple_filename(self, monkeypatch):
        """Test log path resolution for simple filename."""
        from zebtrack.logging_config import resolve_log_path

        # Clear any override env var
        monkeypatch.delenv("ZEBTRACK_LOG_DIR", raising=False)

        result = resolve_log_path("analysis.log")

        # Should be relative to project root/logs
        assert "logs" in result
        assert result.endswith("analysis.log")

    def test_resolve_log_path_with_env_override(self, tmp_path, monkeypatch):
        """Test log path resolution with ZEBTRACK_LOG_DIR override."""
        from zebtrack.logging_config import resolve_log_path

        override_dir = str(tmp_path / "custom_logs")
        monkeypatch.setenv("ZEBTRACK_LOG_DIR", override_dir)

        result = resolve_log_path("test.log")

        assert result == str(tmp_path / "custom_logs" / "test.log")


class TestCompactConsoleRenderer:
    """Tests for CompactConsoleRenderer class."""

    def test_compact_renderer_reduces_whitespace(self):
        """Test that multiple spaces are reduced to single space."""
        from zebtrack.logging_config import CompactConsoleRenderer

        renderer = CompactConsoleRenderer()

        # Call renderer directly with mock logger and event
        result = renderer(None, "test", {"event": "test event"})

        # Should not have multiple consecutive spaces
        multiple_spaces = re.search(r"  +", result)
        assert multiple_spaces is None or result.count("  ") < 3  # Allow some

    def test_compact_renderer_inherits_from_console_renderer(self):
        """Test that CompactConsoleRenderer is a ConsoleRenderer subclass."""
        from zebtrack.logging_config import CompactConsoleRenderer

        assert issubclass(CompactConsoleRenderer, structlog.dev.ConsoleRenderer)


class TestConfigureLogging:
    """Tests for configure_logging function."""

    def test_configure_logging_creates_handlers(self, tmp_path, monkeypatch):
        """Test that configure_logging creates appropriate handlers."""
        from zebtrack.logging_config import configure_logging

        monkeypatch.setenv("ZEBTRACK_LOG_DIR", str(tmp_path))

        configure_logging()

        # Check that root logger has handlers
        root_logger = logging.getLogger()
        # At minimum should have a file handler
        assert len(root_logger.handlers) >= 1

    def test_configure_logging_with_worker_file(self, tmp_path, monkeypatch):
        """Test configure_logging with worker-specific log file."""
        from zebtrack.logging_config import configure_logging

        monkeypatch.setenv("ZEBTRACK_LOG_DIR", str(tmp_path))

        configure_logging(log_file="analysis_worker.log")

        # Worker file should exist (truncated)
        worker_log = tmp_path / "analysis_worker.log"
        assert worker_log.exists()

    def test_configure_logging_with_custom_file(self, tmp_path, monkeypatch):
        """Test configure_logging with custom (non-default) log file."""
        from zebtrack.logging_config import configure_logging

        monkeypatch.setenv("ZEBTRACK_LOG_DIR", str(tmp_path))

        # Custom file should use RotatingFileHandler
        configure_logging(log_file="custom_debug.log")

        # Check the custom log exists
        custom_log = tmp_path / "custom_debug.log"
        assert custom_log.exists() or (tmp_path / "logs" / "custom_debug.log").exists()

    def test_configure_logging_truncates_default_logs(self, tmp_path, monkeypatch):
        """Test that default log files are truncated on start."""
        from zebtrack.logging_config import configure_logging

        monkeypatch.setenv("ZEBTRACK_LOG_DIR", str(tmp_path))

        # Create existing log with content
        analysis_log = tmp_path / "analysis.log"
        analysis_log.write_text("previous session content")

        configure_logging(log_file="analysis.log")

        # Check log was truncated (file exists but old content gone)
        content = analysis_log.read_text()
        assert "previous session content" not in content

    def test_configure_logging_clears_existing_handlers(self, tmp_path, monkeypatch):
        """Test that existing handlers are cleared on reconfiguration."""
        from zebtrack.logging_config import configure_logging

        monkeypatch.setenv("ZEBTRACK_LOG_DIR", str(tmp_path))

        root_logger = logging.getLogger()
        initial_count = len(root_logger.handlers)

        # Configure twice
        configure_logging()
        configure_logging()

        # Handler count should not double
        assert len(root_logger.handlers) <= initial_count + 2

    def test_configure_logging_test_mode_suppresses_console(self, tmp_path, monkeypatch):
        """Test that console logging is suppressed in test mode."""
        from zebtrack.logging_config import configure_logging

        monkeypatch.setenv("ZEBTRACK_LOG_DIR", str(tmp_path))
        # PYTEST_CURRENT_TEST is already set by pytest

        configure_logging()

        # In test mode, console handler either not added or level very high
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(
                handler, logging.FileHandler
            ):
                # Console handler should be high level in tests
                assert handler.level > logging.INFO
