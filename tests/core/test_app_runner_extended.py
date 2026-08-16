"""
Extended unit tests for app_runner startup helpers in core/app_runner.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from zebtrack.core.app_runner import (
    _detect_first_launch,
    _load_settings_or_exit,
    _select_language_on_first_run,
    _set_windows_app_id,
    _setup_logging,
)
from zebtrack.settings import load_settings


class TestAppRunnerExtended:
    """Test app_runner logging setup, language selection, settings loader, and hardware helpers."""

    def test_setup_logging_no_overrides(self):
        mock_cfg = MagicMock()
        configure_levels = _setup_logging(None, mock_cfg)
        mock_cfg.assert_called_once()
        assert callable(configure_levels)

    def test_setup_logging_with_overrides(self):
        mock_cfg = MagicMock()
        overrides = ["zebtrack.core.detector=DEBUG", "zebtrack.io=INFO"]
        configure_levels = _setup_logging(overrides, mock_cfg)
        mock_cfg.assert_called_once()
        assert callable(configure_levels)

    def test_load_settings_or_exit_success(self):
        mock_load = MagicMock(return_value=load_settings())
        mock_configure_levels = MagicMock()
        mock_root = MagicMock()
        mock_mb = MagicMock()
        mock_log = MagicMock()

        res = _load_settings_or_exit(
            load_settings=mock_load,
            configure_logging_levels=mock_configure_levels,
            root=mock_root,
            messagebox_module=mock_mb,
            log=mock_log,
        )
        assert res is not None
        mock_load.assert_called_once()
        mock_configure_levels.assert_called_once_with(res)
        mock_mb.showerror.assert_not_called()

    def test_load_settings_or_exit_file_not_found_exits(self):
        mock_load = MagicMock(side_effect=FileNotFoundError("config.yaml missing"))
        mock_configure_levels = MagicMock()
        mock_root = MagicMock()
        mock_mb = MagicMock()
        mock_log = MagicMock()

        with pytest.raises(SystemExit) as exc_info:
            _load_settings_or_exit(
                load_settings=mock_load,
                configure_logging_levels=mock_configure_levels,
                root=mock_root,
                messagebox_module=mock_mb,
                log=mock_log,
            )
        assert exc_info.value.code == 1
        mock_mb.showerror.assert_called_once()

    def test_load_settings_or_exit_value_error_exits(self):
        mock_load = MagicMock(side_effect=ValueError("Invalid port"))
        mock_configure_levels = MagicMock()
        mock_root = MagicMock()
        mock_mb = MagicMock()
        mock_log = MagicMock()

        with pytest.raises(SystemExit) as exc_info:
            _load_settings_or_exit(
                load_settings=mock_load,
                configure_logging_levels=mock_configure_levels,
                root=mock_root,
                messagebox_module=mock_mb,
                log=mock_log,
            )
        assert exc_info.value.code == 1
        mock_mb.showerror.assert_called_once()

    def test_select_language_on_first_run_skipped_via_env(self, monkeypatch):
        monkeypatch.setenv("ZEBTRACK_SKIP_LANGUAGE_PROMPT", "1")
        mock_root = MagicMock()
        mock_log = MagicMock()

        with patch("zebtrack.ui.language_dialog.ask_language") as mock_ask:
            _select_language_on_first_run(mock_root, log=mock_log)
            mock_ask.assert_not_called()

    def test_detect_first_launch(self):
        mock_settings = MagicMock()
        mock_settings.openvino.auto_benchmark = True
        mock_splash = MagicMock()

        with patch("zebtrack.utils.hardware_benchmark.load_cached_benchmark", return_value=None):
            _detect_first_launch(mock_settings, mock_splash)
            mock_splash.set_first_launch.assert_called_once_with(True)

    def test_set_windows_app_id_safe_execution(self):
        mock_log = MagicMock()
        # Should execute safely without raising exception on any OS
        _set_windows_app_id(mock_log)
