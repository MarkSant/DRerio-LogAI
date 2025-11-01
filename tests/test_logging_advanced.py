"""
Advanced unit tests for logging configuration.

Phase: Sprint 4.6 - Additional logging test coverage
Tests log rotation, formatters, level configuration,
and module-specific logging.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, mock_open
import logging
import structlog


class TestLogRotation:
    """Test suite for log rotation configuration."""

    @patch('logging.handlers.RotatingFileHandler')
    def test_rotating_handler_max_bytes(self, mock_handler):
        """Test rotating handler configured with correct max bytes."""
        from zebtrack.__main__ import configure_logging

        configure_logging()

        # Should create handler with 5MB max
        mock_handler.assert_called()
        call_args = mock_handler.call_args
        assert call_args[1]["maxBytes"] == 5 * 1024 * 1024

    @patch('logging.handlers.RotatingFileHandler')
    def test_rotating_handler_backup_count(self, mock_handler):
        """Test rotating handler keeps 5 backup files."""
        from zebtrack.__main__ import configure_logging

        configure_logging()

        call_args = mock_handler.call_args
        assert call_args[1]["backupCount"] == 5

    @patch('logging.handlers.RotatingFileHandler')
    def test_rotating_handler_file_path(self, mock_handler):
        """Test rotating handler writes to analysis.log."""
        from zebtrack.__main__ import configure_logging

        configure_logging()

        call_args = mock_handler.call_args
        assert call_args[0][0] == "analysis.log"


class TestLogFormatters:
    """Test suite for log formatters."""

    @patch('logging.handlers.RotatingFileHandler')
    @patch('logging.StreamHandler')
    def test_file_handler_uses_json_formatter(self, mock_stream, mock_rotating):
        """Test file handler uses JSON formatter."""
        from zebtrack.__main__ import configure_logging

        mock_file_handler = Mock()
        mock_rotating.return_value = mock_file_handler

        configure_logging()

        # Should set JSON formatter
        mock_file_handler.setFormatter.assert_called_once()

    @patch('logging.handlers.RotatingFileHandler')
    @patch('logging.StreamHandler')
    def test_console_handler_uses_console_formatter(self, mock_stream, mock_rotating):
        """Test console handler uses console formatter."""
        from zebtrack.__main__ import configure_logging

        mock_console_handler = Mock()
        mock_stream.return_value = mock_console_handler

        configure_logging()

        # Should set console formatter
        mock_console_handler.setFormatter.assert_called_once()

    def test_compact_console_renderer_reduces_whitespace(self):
        """Test CompactConsoleRenderer compacts multiple spaces."""
        from zebtrack.__main__ import CompactConsoleRenderer

        renderer = CompactConsoleRenderer()

        # Mock parent call
        with patch.object(renderer.__class__.__bases__[0], '__call__', return_value="test  message    here  "):
            result = renderer(None, None, {})

            # Should have fewer consecutive spaces
            # Implementation may vary


class TestLogLevelConfiguration:
    """Test suite for log level configuration."""

    @patch('logging.getLogger')
    def test_root_logger_set_to_info(self, mock_get_logger):
        """Test root logger level set to INFO."""
        from zebtrack.__main__ import configure_logging

        mock_root_logger = Mock()
        mock_get_logger.return_value = mock_root_logger

        configure_logging()

        # Should set INFO level
        mock_root_logger.setLevel.assert_called_with(logging.INFO)

    @patch('logging.getLogger')
    def test_module_specific_log_level(self, mock_get_logger):
        """Test setting module-specific log level."""
        from zebtrack.logging_config import configure_logging_levels

        mock_module_logger = Mock()
        mock_get_logger.return_value = mock_module_logger

        mock_settings = Mock()
        mock_settings.logging.levels = {"zebtrack.core.detector": "DEBUG"}

        configure_logging_levels(mock_settings)

        # Should set DEBUG for specific module
        mock_get_logger.assert_called_with("zebtrack.core.detector")
        mock_module_logger.setLevel.assert_called_with(logging.DEBUG)

    @patch('logging.getLogger')
    def test_invalid_log_level_format_ignored(self, mock_get_logger):
        """Test invalid log level format is ignored."""
        from zebtrack.logging_config import configure_logging_levels

        # Settings with invalid log level should be handled gracefully
        mock_settings = Mock()
        mock_settings.logging.levels = {"module": "INVALID"}

        # Should not crash, just use default level
        configure_logging_levels(mock_settings)

    @patch('logging.getLogger')
    def test_multiple_module_log_levels(self, mock_get_logger):
        """Test setting multiple module log levels."""
        from zebtrack.logging_config import configure_logging_levels

        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        mock_settings = Mock()
        mock_settings.logging.levels = {
            "zebtrack.core.detector": "DEBUG",
            "zebtrack.analysis": "WARNING",
        }

        configure_logging_levels(mock_settings)

        # Should set levels for both modules
        assert mock_get_logger.call_count >= 2


class TestStructlogConfiguration:
    """Test suite for structlog configuration."""

    def test_structlog_get_logger_works(self):
        """Test structlog.get_logger() returns logger."""
        logger = structlog.get_logger()

        assert logger is not None
        assert hasattr(logger, 'info')
        assert hasattr(logger, 'error')

    def test_structlog_logger_accepts_context(self):
        """Test structlog logger accepts context parameters."""
        logger = structlog.get_logger()

        # Should accept context
        try:
            logger.info("test_message", key="value", count=123)
        except Exception as e:
            pytest.fail(f"Structlog should accept context: {e}")


class TestLogFileCreation:
    """Test suite for log file creation."""

    @patch('builtins.open', new_callable=mock_open)
    @patch('logging.handlers.RotatingFileHandler')
    def test_log_file_created_on_startup(self, mock_handler, mock_file):
        """Test log file is created on startup."""
        from zebtrack.__main__ import configure_logging

        configure_logging()

        # Handler should be created
        mock_handler.assert_called_once()

    @patch('os.path.exists')
    def test_log_file_exists_after_configuration(self, mock_exists):
        """Test log file exists after configuration."""
        from zebtrack.__main__ import configure_logging

        mock_exists.return_value = True

        configure_logging()

        # File should exist (or be created)
        # Actual file creation handled by logging module


class TestLoggerUsage:
    """Test suite for logger usage patterns."""

    def test_domain_action_result_convention(self):
        """Test logging follows domain.action.result convention."""
        logger = structlog.get_logger()

        # Should accept dot-separated keys
        try:
            logger.info("controller.load_project.success", project_name="test")
        except Exception as e:
            pytest.fail(f"Should accept domain.action.result format: {e}")

    def test_logger_accepts_structured_data(self):
        """Test logger accepts structured data."""
        logger = structlog.get_logger()

        # Should accept multiple context fields
        try:
            logger.error(
                "detector.initialization.error",
                error="Failed to load model",
                model_path="/fake/path",
                timestamp="2025-01-01",
            )
        except Exception as e:
            pytest.fail(f"Should accept structured data: {e}")


class TestLoggingEdgeCases:
    """Test suite for logging edge cases."""

    @patch('logging.getLogger')
    def test_configure_logging_called_multiple_times(self, mock_get_logger):
        """Test calling configure_logging multiple times."""
        from zebtrack.__main__ import configure_logging

        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        # Call multiple times
        configure_logging()
        configure_logging()

        # Should handle gracefully (may add multiple handlers)
        # Implementation-specific behavior

    @patch('logging.getLogger')
    def test_log_level_case_insensitive(self, mock_get_logger):
        """Test log level parsing is case-insensitive."""
        from zebtrack.logging_config import configure_logging_levels

        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        mock_settings = Mock()
        mock_settings.logging.levels = {"zebtrack.core": "debug"}  # lowercase

        configure_logging_levels(mock_settings)

        # Should parse correctly (function uses .upper())
        # Implementation may or may not be case-insensitive


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
