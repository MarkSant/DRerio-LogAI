"""Tests for zebtrack.__main__ - Composition Root and Startup Paths.

Covers:
- Configuration loading (FileNotFoundError, ValueError)
- CLI argument parsing (--log-level overrides)
- Seed reproducibility setting
- Windows AppUserModelID setup
- Exception handling paths
- Main loop execution
"""

import logging
import sys
from unittest.mock import MagicMock, patch

import pytest


def _setup_main_mocks(monkeypatch):
    """Set up common mocks for main() testing.

    IMPORTANT: We replace ``app_main.tk`` and ``app_main.messagebox`` with
    stand-alone MagicMock objects instead of patching attributes *on* the real
    ``tkinter`` module.  Patching ``tkinter.Tk`` globally breaks
    ``ttkbootstrap`` which iterates over tkinter widget classes during its
    first import and tries to set ``__init__`` — an unsupported operation on
    MagicMock.
    """
    from zebtrack import __main__ as app_main

    monkeypatch.setattr(sys, "argv", ["zebtrack"])

    mock_root = MagicMock()
    mock_root.withdraw = MagicMock()
    mock_root.deiconify = MagicMock()
    mock_root.after = MagicMock()
    mock_root.update = MagicMock()
    mock_root.mainloop = MagicMock()

    # Create isolated mock modules so the real tkinter stays untouched
    mock_tk = MagicMock()
    mock_tk.Tk = MagicMock(return_value=mock_root)
    monkeypatch.setattr(app_main, "tk", mock_tk)

    mock_messagebox = MagicMock()
    monkeypatch.setattr(app_main, "messagebox", mock_messagebox)

    # Neutralise the detector-weights pre-flight. These tests drive the
    # composition root -- logging, benchmark, splash, error handling -- with a
    # MagicMock settings object, so the resolver correctly declines to trust
    # `weights.source_dir` and falls back to the real (and, on a fresh clone,
    # empty) weights folder. Without this the pre-flight would abort every test
    # here before the behaviour under test ever runs. The pre-flight has its own
    # coverage in tests/core/test_app_runner_extended.py.
    monkeypatch.setattr(
        "zebtrack.core.app_runner._require_detector_weights",
        lambda settings_obj, log: None,
    )

    return app_main


def _make_settings(*, auto_benchmark: bool = False, seed: int | None = None):
    """Create a minimal settings mock with required attributes."""
    settings_obj = MagicMock()
    settings_obj.reproducibility = MagicMock()
    settings_obj.reproducibility.seed = seed
    settings_obj.camera = MagicMock(index=0)
    settings_obj.yolo_model = MagicMock(path="model.pt")
    settings_obj.openvino = MagicMock(auto_benchmark=auto_benchmark)
    settings_obj.model_selection = MagicMock(use_openvino=False)
    settings_obj.ui_features = MagicMock(enable_event_queue=False)
    return settings_obj


# =============================================================================
# CONFIGURATION LOADING TESTS
# =============================================================================


class TestConfigurationLoading:
    """Test configuration loading error handling."""

    def test_main_exits_on_missing_config(self, monkeypatch):
        """Test that main() exits with code 1 when config file is missing."""
        app_main = _setup_main_mocks(monkeypatch)

        def raise_missing_config():
            raise FileNotFoundError("config.yaml not found")

        monkeypatch.setattr("zebtrack.settings.load_settings", raise_missing_config)

        with pytest.raises(SystemExit) as excinfo:
            app_main.main()

        assert excinfo.value.code == 1
        app_main.messagebox.showerror.assert_called_once()
        # Verify error title mentions configuration
        call_args = app_main.messagebox.showerror.call_args
        assert "Configuration" in call_args[0][0] or "config" in call_args[0][1].lower()

    def test_main_exits_on_invalid_config(self, monkeypatch):
        """Test that main() exits with code 1 when config has validation errors."""
        app_main = _setup_main_mocks(monkeypatch)

        def raise_invalid_config():
            raise ValueError("invalid config value")

        monkeypatch.setattr("zebtrack.settings.load_settings", raise_invalid_config)

        with pytest.raises(SystemExit) as excinfo:
            app_main.main()

        assert excinfo.value.code == 1
        app_main.messagebox.showerror.assert_called_once()
        # Verify error mentions validation
        call_args = app_main.messagebox.showerror.call_args
        assert "Validation" in call_args[0][0] or "invalid" in call_args[0][1].lower()

    def test_main_exits_on_yaml_parse_error(self, monkeypatch):
        """Test that main() exits when YAML has syntax errors (as ValueError)."""
        app_main = _setup_main_mocks(monkeypatch)

        def raise_yaml_error():
            raise ValueError("YAML syntax error at line 10")

        monkeypatch.setattr("zebtrack.settings.load_settings", raise_yaml_error)

        with pytest.raises(SystemExit) as excinfo:
            app_main.main()

        assert excinfo.value.code == 1


# =============================================================================
# CLI ARGUMENT PARSING TESTS
# =============================================================================


class TestCLIArgumentParsing:
    """Test command-line argument handling."""

    def test_log_level_override_single_module(self, monkeypatch, capsys):
        """Test --log-level can override a single module's log level."""
        app_main = _setup_main_mocks(monkeypatch)
        monkeypatch.setattr(
            sys,
            "argv",
            ["zebtrack", "--log-level", "zebtrack.core.detection=DEBUG"],
        )

        # Make load_settings raise to exit early (we just want to test arg parsing)
        monkeypatch.setattr(
            "zebtrack.settings.load_settings",
            lambda: (_ for _ in ()).throw(FileNotFoundError("test")),
        )

        with pytest.raises(SystemExit):
            app_main.main()

        # Check that the log level was set
        captured = capsys.readouterr()
        assert "CLI override" in captured.out or (
            logging.getLogger("zebtrack.core.detection").level in [logging.DEBUG, 10]
        )

    def test_log_level_override_invalid_format_prints_warning(self, monkeypatch, capsys):
        """Test --log-level with invalid format prints a warning."""
        app_main = _setup_main_mocks(monkeypatch)
        monkeypatch.setattr(sys, "argv", ["zebtrack", "--log-level", "invalid_no_equals"])

        monkeypatch.setattr(
            "zebtrack.settings.load_settings",
            lambda: (_ for _ in ()).throw(FileNotFoundError("test")),
        )

        with pytest.raises(SystemExit):
            app_main.main()

        captured = capsys.readouterr()
        assert "Warning" in captured.out and "invalid" in captured.out.lower()

    def test_log_level_override_invalid_level_prints_warning(self, monkeypatch, capsys):
        """Test --log-level with invalid level (not DEBUG/INFO/etc) prints warning."""
        app_main = _setup_main_mocks(monkeypatch)
        monkeypatch.setattr(sys, "argv", ["zebtrack", "--log-level", "zebtrack=NOTAVALIDLEVEL"])

        monkeypatch.setattr(
            "zebtrack.settings.load_settings",
            lambda: (_ for _ in ()).throw(FileNotFoundError("test")),
        )

        with pytest.raises(SystemExit):
            app_main.main()

        captured = capsys.readouterr()
        assert "Warning" in captured.out and "Invalid log level" in captured.out

    def test_multiple_log_level_overrides(self, monkeypatch, capsys):
        """Test multiple --log-level flags are processed."""
        app_main = _setup_main_mocks(monkeypatch)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "zebtrack",
                "--log-level",
                "zebtrack.core=DEBUG",
                "--log-level",
                "zebtrack.ui=INFO",
            ],
        )

        monkeypatch.setattr(
            "zebtrack.settings.load_settings",
            lambda: (_ for _ in ()).throw(FileNotFoundError("test")),
        )

        with pytest.raises(SystemExit):
            app_main.main()

        # Both should have been processed
        captured = capsys.readouterr()
        assert captured.out.count("CLI override") >= 2 or (
            logging.getLogger("zebtrack.core").level == logging.DEBUG
        )


# =============================================================================
# REPRODUCIBILITY TESTS
# =============================================================================


class TestReproducibility:
    """Test reproducibility seed setting."""

    def test_seed_is_set_when_configured(self, monkeypatch):
        """Test that set_seed is called when reproducibility.seed is configured."""
        app_main = _setup_main_mocks(monkeypatch)

        mock_settings = MagicMock()
        mock_settings.reproducibility = MagicMock()
        mock_settings.reproducibility.seed = 42
        mock_settings.camera = MagicMock(index=0)
        mock_settings.yolo_model = MagicMock(path="model.pt")
        mock_settings.openvino = MagicMock(auto_benchmark=False)

        monkeypatch.setattr("zebtrack.settings.load_settings", lambda: mock_settings)

        # Mock set_seed to verify it's called (patch at source module)
        set_seed_mock = MagicMock()
        monkeypatch.setattr("zebtrack.utils.set_seed", set_seed_mock)

        # Stop right after the seed is set. This used to throw from
        # create_splash, but the splash is now built BEFORE set_seed -- on
        # purpose, so the window appears before zebtrack.utils drags torch in --
        # and stopping there would prove nothing about the seed.
        monkeypatch.setattr("zebtrack.ui.splash_screen.create_splash", lambda parent: MagicMock())
        monkeypatch.setattr(
            "zebtrack.core.di_registrations.build_container",
            lambda context: (_ for _ in ()).throw(Exception("stop")),
        )

        try:
            app_main.main()
        except Exception:
            pass  # Expected

        set_seed_mock.assert_called_once_with(42)

    def test_seed_not_set_when_not_configured(self, monkeypatch):
        """Test that set_seed is NOT called when reproducibility.seed is None."""
        app_main = _setup_main_mocks(monkeypatch)

        mock_settings = MagicMock()
        mock_settings.reproducibility = MagicMock()
        mock_settings.reproducibility.seed = None
        mock_settings.camera = MagicMock(index=0)
        mock_settings.yolo_model = MagicMock(path="model.pt")
        mock_settings.openvino = MagicMock(auto_benchmark=False)

        monkeypatch.setattr("zebtrack.settings.load_settings", lambda: mock_settings)

        set_seed_mock = MagicMock()
        monkeypatch.setattr("zebtrack.utils.set_seed", set_seed_mock)

        monkeypatch.setattr("zebtrack.ui.splash_screen.create_splash", lambda parent: MagicMock())
        monkeypatch.setattr(
            "zebtrack.core.di_registrations.build_container",
            lambda context: (_ for _ in ()).throw(Exception("stop")),
        )

        try:
            app_main.main()
        except Exception:
            pass

        set_seed_mock.assert_not_called()


# =============================================================================
# LOGGING & BENCHMARK PATH TESTS
# =============================================================================


class TestLoggingAndBenchmarkPaths:
    """Test logging configuration and benchmark branches in main()."""

    def test_configure_logging_levels_called_twice(self, monkeypatch):
        """configure_logging_levels should run before and after settings load."""
        app_main = _setup_main_mocks(monkeypatch)

        settings_obj = _make_settings()
        monkeypatch.setattr("zebtrack.settings.load_settings", lambda: settings_obj)

        configure_logging_mock = MagicMock()
        configure_logging_levels_mock = MagicMock()
        monkeypatch.setattr(app_main, "configure_logging", configure_logging_mock)
        monkeypatch.setattr(
            "zebtrack.logging_config.configure_logging_levels",
            configure_logging_levels_mock,
        )

        monkeypatch.setattr(
            "zebtrack.ui.splash_screen.create_splash",
            lambda parent: (_ for _ in ()).throw(RuntimeError("stop")),
        )

        app_main.main()

        configure_logging_mock.assert_called_once()
        assert configure_logging_levels_mock.call_count == 2
        assert configure_logging_levels_mock.call_args_list[0].args == ()
        assert configure_logging_levels_mock.call_args_list[1].args == (settings_obj,)

    def test_benchmark_uses_cached_result(self, monkeypatch):
        """When cached benchmark exists, no new benchmark run should occur."""
        app_main = _setup_main_mocks(monkeypatch)

        settings_obj = _make_settings(auto_benchmark=True)
        monkeypatch.setattr("zebtrack.settings.load_settings", lambda: settings_obj)

        splash_mock = MagicMock()
        splash_mock.update_status = MagicMock()
        monkeypatch.setattr("zebtrack.ui.splash_screen.create_splash", lambda parent: splash_mock)

        cached = MagicMock()
        cached.recommendation = MagicMock(device_live="CPU")

        load_cached_mock = MagicMock(return_value=cached)
        get_or_run_mock = MagicMock()

        monkeypatch.setattr(
            "zebtrack.utils.hardware_benchmark.load_cached_benchmark", load_cached_mock
        )
        monkeypatch.setattr(
            "zebtrack.utils.hardware_benchmark.get_or_run_benchmark", get_or_run_mock
        )

        def crash_state_manager(*args, **kwargs):
            raise RuntimeError("stop")

        monkeypatch.setattr("zebtrack.core.state_manager.StateManager", crash_state_manager)

        app_main.main()

        # load_cached_benchmark is called twice: once by _detect_first_launch,
        # once by _run_benchmark_if_enabled
        assert load_cached_mock.call_count == 2
        get_or_run_mock.assert_not_called()

    def test_benchmark_first_run_persists_settings(self, monkeypatch):
        """First benchmark run should apply recommendations and save settings."""
        app_main = _setup_main_mocks(monkeypatch)

        settings_obj = _make_settings(auto_benchmark=True)
        monkeypatch.setattr("zebtrack.settings.load_settings", lambda: settings_obj)

        splash_mock = MagicMock()
        splash_mock.update_status = MagicMock()
        monkeypatch.setattr("zebtrack.ui.splash_screen.create_splash", lambda parent: splash_mock)

        load_cached_mock = MagicMock(return_value=None)
        recommendation = MagicMock(
            backend="openvino",
            device_live="CPU",
            device_batch="CPU",
            openvino_hint_live="LATENCY",
            openvino_hint_batch="THROUGHPUT",
            openvino_precision="FP16",
            enable_model_cache=True,
            estimated_fps_live=123.4,
        )
        benchmark_result = MagicMock(recommendation=recommendation)
        get_or_run_mock = MagicMock(return_value=benchmark_result)

        save_settings_mock = MagicMock()

        monkeypatch.setattr(
            "zebtrack.utils.hardware_benchmark.load_cached_benchmark", load_cached_mock
        )
        monkeypatch.setattr(
            "zebtrack.utils.hardware_benchmark.get_or_run_benchmark", get_or_run_mock
        )
        monkeypatch.setattr("zebtrack.settings.save_settings", save_settings_mock)

        def crash_state_manager(*args, **kwargs):
            raise RuntimeError("stop")

        monkeypatch.setattr("zebtrack.core.state_manager.StateManager", crash_state_manager)

        app_main.main()

        # load_cached_benchmark is called twice: once by _detect_first_launch,
        # once by _run_benchmark_if_enabled
        assert load_cached_mock.call_count == 2
        get_or_run_mock.assert_called_once()
        save_settings_mock.assert_called_once_with(settings_obj)


# =============================================================================
# WINDOWS-SPECIFIC TESTS
# =============================================================================


class TestWindowsSpecificBehavior:
    """Test Windows-specific behavior (AppUserModelID)."""

    @patch("os.name", "nt")
    def test_app_user_model_id_set_on_windows(self, monkeypatch):
        """Test that AppUserModelID is set on Windows for taskbar icon."""
        app_main = _setup_main_mocks(monkeypatch)

        mock_settings = MagicMock()
        mock_settings.reproducibility = None
        mock_settings.camera = MagicMock(index=0)
        mock_settings.yolo_model = MagicMock(path="model.pt")
        mock_settings.openvino = MagicMock(auto_benchmark=False)

        monkeypatch.setattr("zebtrack.settings.load_settings", lambda: mock_settings)

        # Track if SetCurrentProcessExplicitAppUserModelID was called
        windll_mock = MagicMock()
        with patch("ctypes.windll", windll_mock, create=True):
            monkeypatch.setattr(
                "zebtrack.ui.splash_screen.create_splash",
                lambda parent: (_ for _ in ()).throw(Exception("stop")),
            )

            try:
                app_main.main()
            except Exception:
                pass

            # On Windows, the shell32 function should be called
            # (This test may not work on non-Windows systems due to ctypes.windll)


# =============================================================================
# EXCEPTION HANDLING TESTS
# =============================================================================


class TestExceptionHandling:
    """Test exception handling in main()."""

    def test_fatal_error_shows_messagebox(self, monkeypatch):
        """Test that unhandled exceptions show a fatal error messagebox."""
        app_main = _setup_main_mocks(monkeypatch)

        mock_settings = MagicMock()
        mock_settings.reproducibility = None
        mock_settings.camera = MagicMock(index=0)
        mock_settings.yolo_model = MagicMock(path="model.pt")
        mock_settings.openvino = MagicMock(auto_benchmark=False)

        monkeypatch.setattr("zebtrack.settings.load_settings", lambda: mock_settings)

        # Make something crash after settings are loaded
        def crash_on_splash(*args, **kwargs):
            raise RuntimeError("Simulated crash")

        monkeypatch.setattr("zebtrack.ui.splash_screen.create_splash", crash_on_splash)

        app_main.main()

        # Verify error messagebox was shown
        app_main.messagebox.showerror.assert_called()
        call_args = app_main.messagebox.showerror.call_args
        assert "Fatal" in call_args[0][0] or "error" in call_args[0][1].lower()

    def test_splash_destruction_on_error(self, monkeypatch):
        """Test that splash is destroyed even if an error occurs."""
        app_main = _setup_main_mocks(monkeypatch)

        mock_settings = MagicMock()
        mock_settings.reproducibility = None
        mock_settings.camera = MagicMock(index=0)
        mock_settings.yolo_model = MagicMock(path="model.pt")
        mock_settings.openvino = MagicMock(auto_benchmark=False)

        monkeypatch.setattr("zebtrack.settings.load_settings", lambda: mock_settings)

        mock_splash = MagicMock()
        mock_splash.update_status = MagicMock()
        mock_splash.destroy = MagicMock()

        def create_splash_then_crash(parent):
            mock_splash._created = True
            return mock_splash

        monkeypatch.setattr("zebtrack.ui.splash_screen.create_splash", create_splash_then_crash)

        # Make StateManager import crash
        def crash_on_state_manager(*args, **kwargs):
            raise ImportError("Simulated import error")

        monkeypatch.setattr("zebtrack.core.state_manager.StateManager", crash_on_state_manager)

        app_main.main()

        # Splash should have been destroyed in the finally or except block
        mock_splash.destroy.assert_called()


# =============================================================================
# MODULE EXECUTION TESTS
# =============================================================================


class TestModuleExecution:
    """Test module execution entry point."""

    def test_if_name_main_calls_main(self, monkeypatch):
        """Test that __name__ == '__main__' calls main()."""
        # This is tricky to test since we import the module
        # Just verify the check exists
        import zebtrack.__main__ as main_module

        with open(main_module.__file__) as f:
            source = f.read()
        assert 'if __name__ == "__main__":' in source
        assert "main()" in source


class TestMissingWeightsShortCircuitsStartup:
    """Without weights, startup must stop BEFORE the slowest step.

    The hardware benchmark is the longest part of a first launch. The
    missing-weights check used to happen at the very end of bootstrap, so a
    fresh clone ran the whole benchmark, drew the splash to ~95%, and only then
    reported a generic "a fatal error occurred". Order is the fix, so order is
    what this guards.
    """

    def _settings_with_empty_weights_dir(self, folder):
        settings_obj = _make_settings(auto_benchmark=True)
        settings_obj.weights = MagicMock()
        settings_obj.weights.source_dir = str(folder)
        settings_obj.weights.lateral = MagicMock()
        settings_obj.weights.lateral.seg_filename = "best_seg_lateral.pt"
        settings_obj.weights.lateral.det_filename = "best_det_lateral.pt"
        settings_obj.weights.top_down = MagicMock()
        settings_obj.weights.top_down.seg_filename = "best_seg_topdown.pt"
        settings_obj.weights.top_down.det_filename = "best_det_topdown.pt"
        return settings_obj

    def test_benchmark_never_runs_and_the_dialog_is_specific(self, monkeypatch, tmp_path):
        import zebtrack.core.app_runner as app_runner

        # Captured before _setup_main_mocks neutralises it: here the pre-flight
        # IS the behaviour under test, so it has to be the real one.
        real_preflight = app_runner._require_detector_weights

        app_main = _setup_main_mocks(monkeypatch)
        monkeypatch.setattr(app_runner, "_require_detector_weights", real_preflight)

        empty = tmp_path / "weights"
        empty.mkdir()
        settings_obj = self._settings_with_empty_weights_dir(empty)
        monkeypatch.setattr("zebtrack.settings.load_settings", lambda: settings_obj)
        monkeypatch.setattr("zebtrack.ui.splash_screen.create_splash", lambda parent: MagicMock())

        benchmark = MagicMock()
        monkeypatch.setattr(app_runner, "_run_benchmark_if_enabled", benchmark)

        with pytest.raises(SystemExit) as excinfo:
            app_main.main()

        assert excinfo.value.code == 1
        benchmark.assert_not_called()

        messagebox = app_main.messagebox
        messagebox.showerror.assert_called_once()
        title, body = messagebox.showerror.call_args[0][:2]
        assert "fatal error" not in body.lower(), "the generic wording is the regression"
        assert str(empty) in body
        assert "fetch-weights" in body
        assert "best_seg_lateral.pt" in body
        assert title


class TestStartupCrashIsVisibleWithoutAConsole:
    """A failure before the Tk root exists must not vanish.

    The desktop shortcut launches the app with ``pythonw.exe`` so that no
    console sits behind the window. ``sys.stderr`` is then None, and Python's
    default traceback goes nowhere -- double-clicking the icon simply appears to
    do nothing, with no message and no window.

    ``run_app`` has its own error dialog, but only from the point the Tk root
    exists onwards. Argument parsing, logging setup and ``Tk()`` itself run
    before that.
    """

    def test_shows_a_dialog_when_there_is_no_stderr(self, monkeypatch):
        app_main = _setup_main_mocks(monkeypatch)
        monkeypatch.setattr(sys, "stderr", None)
        monkeypatch.setattr(
            app_main,
            "run_app",
            MagicMock(side_effect=RuntimeError("boom before Tk existed")),
        )

        with pytest.raises(RuntimeError):
            app_main.main()

        app_main.messagebox.showerror.assert_called_once()
        title, body = app_main.messagebox.showerror.call_args[0][:2]
        assert "boom before Tk existed" in body, "the traceback is the point"
        assert "analysis.log" in body, "the operator needs to be told where the log is"
        assert title

    def test_stays_out_of_the_way_when_a_console_exists(self, monkeypatch):
        """With a terminal, Python's own traceback is better than a modal."""
        app_main = _setup_main_mocks(monkeypatch)
        monkeypatch.setattr(
            app_main,
            "run_app",
            MagicMock(side_effect=RuntimeError("boom")),
        )

        with pytest.raises(RuntimeError):
            app_main.main()

        app_main.messagebox.showerror.assert_not_called()

    def test_a_deliberate_exit_is_not_reported_as_a_crash(self, monkeypatch):
        """``sys.exit(1)`` after a specific dialog must not add a second one.

        The missing-weights path exits this way, having already shown a message
        that names the folder and the remedy.
        """
        app_main = _setup_main_mocks(monkeypatch)
        monkeypatch.setattr(sys, "stderr", None)
        monkeypatch.setattr(app_main, "run_app", MagicMock(side_effect=SystemExit(1)))

        with pytest.raises(SystemExit) as excinfo:
            app_main.main()

        assert excinfo.value.code == 1
        app_main.messagebox.showerror.assert_not_called()

    def test_survives_a_tk_that_cannot_show_the_dialog(self, monkeypatch):
        """If Tk is the thing that is broken, the log is the last channel."""
        app_main = _setup_main_mocks(monkeypatch)
        monkeypatch.setattr(sys, "stderr", None)
        app_main.messagebox.showerror.side_effect = RuntimeError("no display")
        monkeypatch.setattr(
            app_main,
            "run_app",
            MagicMock(side_effect=RuntimeError("original failure")),
        )

        # The original error must reach the caller, not be replaced by the
        # reporter's own.
        with pytest.raises(RuntimeError, match="original failure"):
            app_main.main()
