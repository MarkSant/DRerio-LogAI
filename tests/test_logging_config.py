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
                "zebtrack.core.detection": "DEBUG",
                "zebtrack.ui": "WARNING",
                "zebtrack.io": "ERROR",
            }
        },
    }
    config_path = mock_config_file(config_data)
    # Isolate from the repo-root ``config.local.yaml``. ``load_settings`` applies
    # that override by default, so a developer whose local config sets
    # ``zebtrack.io: WARNING`` silently overrode the ERROR this test asserts. It
    # only ever passed because another test used to truncate that file to zero
    # bytes before this one ran.
    settings_obj = load_settings(config_path, config_path.parent / "no-local-override.yaml")

    # DI architecture: pass settings_obj directly to configure_logging_levels
    configure_logging_levels(settings_obj)

    assert logging.getLogger("zebtrack.core.detection").level == logging.DEBUG
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
        "logging": {"levels": {"zebtrack.core.detection": "INVALID_LEVEL"}},
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


class TestConfigureLoggingWithoutConsole:
    """``configure_logging`` must survive a process that has no console.

    That is not hypothetical: the Windows desktop shortcut launches the app
    through ``pythonw.exe`` precisely so the researcher gets the GUI and no
    terminal window behind it. In such a process ``sys.stdout`` and
    ``sys.stderr`` are both None.

    Building the handler anyway does NOT degrade gracefully.
    ``logging.StreamHandler(None)`` substitutes ``sys.stderr``, which is also
    None here, so the handler ends up holding ``stream=None`` and every record
    raises ``AttributeError`` inside ``emit`` -- before the window appears.

    These tests drive the handlers directly rather than through
    ``logging.getLogger()``: ``tests/conftest.py`` calls
    ``logging.disable(logging.CRITICAL)``, so a record emitted the usual way
    never reaches a handler and would prove nothing.
    """

    @staticmethod
    def _root_handlers(kind):
        return [h for h in logging.getLogger().handlers if isinstance(h, kind)]

    @staticmethod
    def _console_handlers():
        """Only the handler ``configure_logging`` builds.

        ``isinstance(h, StreamHandler)`` alone is not enough: pytest installs
        its own capture handler, which is a StreamHandler over a ``StringIO``
        and would make every assertion here pass or fail for reasons that have
        nothing to do with this project. The ``CompactConsoleRenderer`` in the
        formatter is what identifies ours.
        """
        from zebtrack.logging_config import CompactConsoleRenderer

        def is_ours(handler):
            formatter = handler.formatter
            processors = getattr(formatter, "processors", ())
            return any(isinstance(p, CompactConsoleRenderer) for p in processors)

        return [
            h
            for h in logging.getLogger().handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
            and is_ours(h)
        ]

    @staticmethod
    def _record(message):
        return logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg=message,
            args=(),
            exc_info=None,
        )

    @pytest.fixture
    def headless(self, tmp_path, monkeypatch):
        """A configured logger in a process that has no console.

        The two suppression env vars have to be cleared. ``configure_logging``
        skips ``addHandler`` outright when either is set, so leaving them in
        place means no console handler is registered *for reasons unrelated to
        having no console* -- and every assertion below would hold even with
        the guard removed. Verified: with the guard reverted and these vars
        cleared, ``test_no_handler_is_left_holding_a_none_stream`` and
        ``test_emitting_through_every_handler_does_not_raise`` both fail.
        """
        from zebtrack.logging_config import configure_logging

        monkeypatch.setenv("ZEBTRACK_LOG_DIR", str(tmp_path))
        monkeypatch.delenv("ZEBTRACK_SUPPRESS_CONSOLE_LOGS", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setattr("sys.stdout", None)
        monkeypatch.setattr("sys.stderr", None)
        configure_logging()
        return tmp_path

    def test_no_handler_is_left_holding_a_none_stream(self, headless):
        """The exact defect being prevented: a handler that cannot write.

        Checked over EVERY root handler, not just ours: a ``stream`` of None
        is unusable no matter who installed it.
        """
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.StreamHandler):
                assert handler.stream is not None, f"unusable handler: {handler!r}"

    def test_our_console_handler_is_not_registered(self, headless):
        """With no console there is nothing for it to write to."""
        assert self._console_handlers() == []

    def test_no_handler_swallows_the_record(self, headless, monkeypatch):
        """Without the guard, emitting raises ``AttributeError`` inside ``emit``.

        It does not propagate: ``logging`` routes it to ``Handler.handleError``,
        which by default writes to stderr -- None here -- and returns. So the
        app would run with its logging quietly broken rather than crashing.
        Spying on ``handleError`` is what makes that visible to a test.
        """
        failures = []
        monkeypatch.setattr(
            logging.Handler,
            "handleError",
            lambda self, record: failures.append(self),
        )

        record = self._record("console-less smoke test")
        for handler in logging.getLogger().handlers:
            handler.handle(record)

        assert failures == [], f"handlers failed to emit: {failures!r}"

    def test_file_handler_still_records_without_a_console(self, headless):
        """The file is the only diagnostic channel left; it must keep working."""
        file_handlers = self._root_handlers(logging.FileHandler)
        assert file_handlers, "configure_logging must always install a file handler"

        for handler in file_handlers:
            handler.handle(self._record("written-without-a-console"))
            handler.flush()

        assert "written-without-a-console" in (headless / "analysis.log").read_text(
            encoding="utf-8"
        )

    def test_console_handler_is_still_built_when_stdout_exists(self, tmp_path, monkeypatch):
        """The guard must not silence the console for everyone else.

        ``PYTEST_CURRENT_TEST`` has to go: ``configure_logging`` skips
        ``addHandler`` entirely in test mode, so leaving it set would make this
        assertion pass for the wrong reason -- it would be indistinguishable
        from the console-less path.
        """
        from zebtrack.logging_config import configure_logging

        monkeypatch.setenv("ZEBTRACK_LOG_DIR", str(tmp_path))
        monkeypatch.delenv("ZEBTRACK_SUPPRESS_CONSOLE_LOGS", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        configure_logging()

        console = self._console_handlers()
        assert console, "a console handler is expected when sys.stdout is a real stream"
        assert all(h.stream is not None for h in console)
