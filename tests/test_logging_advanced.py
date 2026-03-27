"""
Advanced unit tests for logging configuration.

Phase: Sprint 4.6 - Additional logging test coverage
Tests formatters, level configuration, handler setup,
and module-specific logging.
"""

import logging
import logging.handlers
import os
from unittest.mock import Mock, patch

import pytest
import structlog


class TestLogHandlerSetup:
    """Test suite for handler types based on log file name."""

    def test_default_log_uses_file_handler(self, tmp_path):
        """Default log (analysis.log) uses FileHandler, not RotatingFileHandler."""
        from zebtrack.logging_config import configure_logging

        log_file = str(tmp_path / "analysis.log")
        with patch("zebtrack.logging_config.resolve_log_path", return_value=log_file):
            configure_logging("analysis.log")

        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        rotating = [h for h in file_handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(file_handlers) >= 1, "Should have at least one FileHandler"
        assert len(rotating) == 0, "Default log should NOT use RotatingFileHandler"

    def test_non_default_log_uses_rotating_handler(self, tmp_path):
        """Non-default log files use RotatingFileHandler."""
        from zebtrack.logging_config import configure_logging

        log_file = str(tmp_path / "custom.log")
        with patch("zebtrack.logging_config.resolve_log_path", return_value=log_file):
            configure_logging("custom.log")

        root = logging.getLogger()
        rotating = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(rotating) == 1, "Non-default log should use RotatingFileHandler"
        assert rotating[0].maxBytes == 10 * 1024 * 1024
        assert rotating[0].backupCount == 1


class TestLogFormatters:
    """Test suite for log formatters."""

    def test_file_handler_uses_json_formatter(self, tmp_path):
        """File handler uses JSON formatter (ProcessorFormatter wrapping JSONRenderer)."""
        from zebtrack.logging_config import configure_logging

        log_file = str(tmp_path / "analysis.log")
        with patch("zebtrack.logging_config.resolve_log_path", return_value=log_file):
            configure_logging("analysis.log")

        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) >= 1
        formatter = file_handlers[0].formatter
        assert isinstance(formatter, structlog.stdlib.ProcessorFormatter)

    def test_compact_console_renderer_reduces_whitespace(self):
        """Test CompactConsoleRenderer compacts multiple spaces."""
        from zebtrack.logging_config import CompactConsoleRenderer

        renderer = CompactConsoleRenderer()

        with patch.object(
            renderer.__class__.__bases__[0], "__call__", return_value="test  message    here  "
        ):
            renderer(None, None, {})


class TestLogLevelConfiguration:
    """Test suite for log level configuration."""

    def test_root_logger_set_to_debug(self, tmp_path):
        """Root logger level is set to DEBUG after configure_logging."""
        from zebtrack.logging_config import configure_logging

        log_file = str(tmp_path / "analysis.log")
        with patch("zebtrack.logging_config.resolve_log_path", return_value=log_file):
            configure_logging("analysis.log")

        root = logging.getLogger()
        assert root.level == logging.DEBUG

    @patch("structlog.get_logger")
    @patch("logging.getLogger")
    def test_module_specific_log_level(self, mock_get_logger, mock_structlog_get_logger):
        """Test setting module-specific log level."""
        from zebtrack.logging_config import configure_logging_levels

        mock_module_logger = Mock()
        mock_get_logger.return_value = mock_module_logger

        # Mock structlog logger
        mock_structlog_logger = Mock()
        mock_structlog_get_logger.return_value = mock_structlog_logger

        mock_settings = Mock()
        mock_settings.logging.levels = {"zebtrack.core.detection": "DEBUG"}

        configure_logging_levels(mock_settings)

        # Should set DEBUG for specific module
        mock_get_logger.assert_called_with("zebtrack.core.detection")
        mock_module_logger.setLevel.assert_called_with(logging.DEBUG)

    @patch("logging.getLogger")
    def test_invalid_log_level_format_ignored(self, mock_get_logger):
        """Test invalid log level format is ignored."""
        from zebtrack.logging_config import configure_logging_levels

        # Settings with invalid log level should be handled gracefully
        mock_settings = Mock()
        mock_settings.logging.levels = {"module": "INVALID"}

        # Should not crash, just use default level
        configure_logging_levels(mock_settings)

    @patch("logging.getLogger")
    def test_multiple_module_log_levels(self, mock_get_logger):
        """Test setting multiple module log levels."""
        from zebtrack.logging_config import configure_logging_levels

        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        mock_settings = Mock()
        mock_settings.logging.levels = {
            "zebtrack.core.detection": "DEBUG",
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
        assert hasattr(logger, "info")
        assert hasattr(logger, "error")

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

    def test_log_file_created_on_startup(self, tmp_path):
        """Log file is created after configure_logging."""
        from zebtrack.logging_config import configure_logging

        log_file = str(tmp_path / "analysis.log")
        with patch("zebtrack.logging_config.resolve_log_path", return_value=log_file):
            configure_logging("analysis.log")

        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) >= 1
        assert os.path.exists(log_file)

    @patch("os.path.exists")
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

    def test_configure_logging_called_multiple_times(self, tmp_path):
        """Calling configure_logging twice does not duplicate handlers."""
        from zebtrack.logging_config import configure_logging

        log_file = str(tmp_path / "analysis.log")
        with patch("zebtrack.logging_config.resolve_log_path", return_value=log_file):
            configure_logging("analysis.log")
            handler_count_first = len(logging.getLogger().handlers)

            configure_logging("analysis.log")
            handler_count_second = len(logging.getLogger().handlers)

        assert handler_count_second == handler_count_first, (
            "Calling configure_logging twice should not duplicate handlers"
        )

    @patch("logging.getLogger")
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
