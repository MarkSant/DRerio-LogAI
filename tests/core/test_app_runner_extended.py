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


class TestRequireDetectorWeights:
    """The startup pre-flight that fails fast, and by name, without weights.

    It runs BEFORE the hardware benchmark on purpose: the benchmark is the
    slowest step in startup, and without weights the run is doomed anyway. The
    user used to wait through it and a 95%-complete splash only to be told "a
    fatal error occurred".
    """

    def _settings_pointing_at(self, folder):
        settings = load_settings()
        settings.weights.source_dir = str(folder)
        return settings

    def test_raises_when_the_folder_holds_no_weights(self, tmp_path):
        from zebtrack.core.app_runner import _require_detector_weights
        from zebtrack.core.exceptions import MissingDetectorWeightsError

        empty = tmp_path / "weights"
        empty.mkdir()

        with pytest.raises(MissingDetectorWeightsError) as excinfo:
            _require_detector_weights(self._settings_pointing_at(empty), MagicMock())

        assert empty == excinfo.value.weights_dir

    def test_raises_when_the_folder_does_not_exist(self, tmp_path):
        from zebtrack.core.app_runner import _require_detector_weights
        from zebtrack.core.exceptions import MissingDetectorWeightsError

        with pytest.raises(MissingDetectorWeightsError):
            _require_detector_weights(self._settings_pointing_at(tmp_path / "absent"), MagicMock())

    def test_passes_when_a_weight_is_present(self, tmp_path):
        from zebtrack.core.app_runner import _require_detector_weights

        folder = tmp_path / "weights"
        folder.mkdir()
        (folder / "best_seg_lateral.pt").write_bytes(b"not really a checkpoint")

        # Must not raise: the pre-flight is deliberately conservative and leaves
        # every subtler judgement (wrong type, wrong perspective) to the
        # bootstrapper, which has the catalogue loaded.
        _require_detector_weights(self._settings_pointing_at(folder), MagicMock())

    def test_ignores_non_weight_files(self, tmp_path):
        from zebtrack.core.app_runner import _require_detector_weights
        from zebtrack.core.exceptions import MissingDetectorWeightsError

        folder = tmp_path / "weights"
        folder.mkdir()
        (folder / "README.md").write_text("put the models here")
        (folder / "best_seg_lateral.pt.part").write_bytes(b"interrupted download")

        with pytest.raises(MissingDetectorWeightsError):
            _require_detector_weights(self._settings_pointing_at(folder), MagicMock())


class TestMissingWeightsDialog:
    """The dialog must say what is missing, where, and how to fix it."""

    def _shown(self, tmp_path):
        from zebtrack.core.app_runner import _handle_missing_weights
        from zebtrack.core.exceptions import MissingDetectorWeightsError

        exc = MissingDetectorWeightsError(
            str(tmp_path / "weights"),
            ("best_seg_lateral.pt", "best_det_lateral.pt"),
        )
        messagebox = MagicMock()

        with pytest.raises(SystemExit) as excinfo:
            _handle_missing_weights(messagebox, MagicMock(), exc, root=None, splash=None)

        assert excinfo.value.code == 1
        messagebox.showerror.assert_called_once()
        args = messagebox.showerror.call_args[0]
        return args[0], args[1]

    def test_names_the_folder_and_the_missing_files(self, tmp_path):
        _title, body = self._shown(tmp_path)

        assert str(tmp_path / "weights") in body
        assert "best_seg_lateral.pt" in body
        assert "best_det_lateral.pt" in body

    def test_gives_the_command_that_fixes_it(self, tmp_path):
        _title, body = self._shown(tmp_path)

        assert "fetch-weights" in body

    def test_does_not_fall_back_to_the_generic_wording(self, tmp_path):
        title, body = self._shown(tmp_path)

        assert "fatal error" not in body.lower()
        assert "fatal error" not in title.lower()

    def test_falls_back_to_the_naming_pattern_when_no_names_are_known(self, tmp_path):
        from zebtrack.core.app_runner import _handle_missing_weights
        from zebtrack.core.exceptions import MissingDetectorWeightsError

        exc = MissingDetectorWeightsError(str(tmp_path / "weights"), ())
        messagebox = MagicMock()

        with pytest.raises(SystemExit):
            _handle_missing_weights(messagebox, MagicMock(), exc, root=None, splash=None)

        body = messagebox.showerror.call_args[0][1]
        assert "best_*_lateral.pt" in body

    def test_a_dead_tk_does_not_swallow_the_message(self, tmp_path, capsys):
        """With Tk already broken the console is the only channel left."""
        from zebtrack.core.app_runner import _handle_missing_weights
        from zebtrack.core.exceptions import MissingDetectorWeightsError

        exc = MissingDetectorWeightsError(str(tmp_path / "weights"), ("best_seg_lateral.pt",))
        messagebox = MagicMock()
        messagebox.showerror.side_effect = RuntimeError("no display")

        with pytest.raises(SystemExit):
            _handle_missing_weights(messagebox, MagicMock(), exc, root=None, splash=None)

        assert "fetch-weights" in capsys.readouterr().err
