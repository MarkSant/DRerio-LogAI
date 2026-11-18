"""Extended unit tests for ui/components/global_model_configuration_panel.py."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

from tests.utils.deferring_tk import bind_deferring_tk

from zebtrack.ui.components.global_model_configuration_panel import (
    _CONVERSION_POLL_INTERVAL_MS,
    GlobalModelConfigurationPanel,
    _method_labels,
    _openvino_status_labels,
    _perspective_labels,
    _target_labels,
)


class TestGlobalModelConfigurationPanelExtended:
    def test_constants_and_target_labels(self):
        assert _CONVERSION_POLL_INTERVAL_MS == 1500

        targets = _target_labels()
        assert "aquarium" in targets
        assert "zebrafish" in targets

    def test_method_and_perspective_labels(self):
        methods = _method_labels()
        assert "seg" in methods
        assert "det" in methods

        perspectives = _perspective_labels()
        assert "lateral" in perspectives
        assert "top_down" in perspectives

    def test_openvino_status_labels(self):
        statuses = _openvino_status_labels()
        assert "ready" in statuses
        assert "converting" in statuses
        assert "failed" in statuses
        assert "not_converted" in statuses

    def test_set_weight_refresh_callback(self):
        panel = object.__new__(GlobalModelConfigurationPanel)
        panel._refresh_weight_choices = None

        mock_cb = MagicMock()
        panel.set_weight_refresh_callback(mock_cb)
        assert panel._refresh_weight_choices is mock_cb


class TestGlobalModelConfigurationPanelExtended7:
    def test_conversion_poll_interval_constant(self):
        assert _CONVERSION_POLL_INTERVAL_MS == 1500

    def test_openvino_status_labels_keys(self):
        labels = _openvino_status_labels()
        assert set(labels.keys()) == {"ready", "converting", "failed", "not_converted"}

    def test_perspective_labels_keys(self):
        labels = _perspective_labels()
        assert set(labels.keys()) == {"lateral", "top_down"}

    def test_target_labels_keys(self):
        labels = _target_labels()
        assert set(labels.keys()) == {"aquarium", "zebrafish"}

    def test_method_labels_keys(self):
        labels = _method_labels()
        assert set(labels.keys()) == {"seg", "det"}


class TestClearOpenVinoCacheOffTk:
    """A6-10: deleting OpenVINO caches runs on a worker; dialogs stay on Tk."""

    @staticmethod
    def _panel(clear_cache):
        panel = cast(Any, GlobalModelConfigurationPanel.__new__(GlobalModelConfigurationPanel))
        panel._cache_clear_pending = False
        panel.controller = SimpleNamespace(
            hardware_vm=SimpleNamespace(clear_openvino_cache=clear_cache)
        )
        events: list = []
        panel._show_cache_clear_report = lambda report, *, scope: events.append(
            ("report", report, scope, threading.current_thread())
        )
        panel._populate_weights_treeview = lambda: events.append(("refresh",))
        return panel, bind_deferring_tk(panel), events

    def test_selected_weight_cache_is_cleared_off_tk(self, monkeypatch):
        threads: list = []
        report = {"cleared": ["yolo"], "locked": [], "orphans_locked": []}

        def clear(name):
            threads.append((name, threading.current_thread()))
            return report

        panel, tk_loop, events = self._panel(clear)
        panel._selected_weight_name = lambda: "yolo"
        monkeypatch.setattr(
            "zebtrack.ui.components.global_model_configuration_panel.messagebox.askyesno",
            lambda *a, **k: True,
        )

        panel._on_clear_cache_selected()
        assert events == []

        tk_loop.run_until_idle()

        assert len(threads) == 1
        assert threads[0][0] == "yolo"
        assert threads[0][1] is not threading.main_thread()
        assert events == [
            ("report", report, "yolo", threading.main_thread()),
            ("refresh",),
        ]
        assert panel._cache_clear_pending is False

    def test_clear_all_passes_none_and_ignores_a_second_request(self, monkeypatch):
        release = threading.Event()
        names: list = []

        def clear(name):
            names.append(name)
            release.wait(5)
            return {"cleared": [], "locked": ["a"], "orphans_locked": []}

        panel, tk_loop, events = self._panel(clear)
        monkeypatch.setattr(
            "zebtrack.ui.components.global_model_configuration_panel.messagebox.askyesno",
            lambda *a, **k: True,
        )

        panel._on_clear_cache_all()
        panel._on_clear_cache_all()
        release.set()
        tk_loop.run_until_idle()

        assert names == [None]
        assert [e[0] for e in events] == ["report", "refresh"]
        assert events[0][2] is None

    def test_a_failure_refreshes_the_list_and_unlocks_the_buttons(self):
        def clear(_name):
            raise OSError("cache root unreadable")

        panel, tk_loop, events = self._panel(clear)

        panel._clear_cache_in_background("yolo")
        tk_loop.run_until_idle()

        assert events == [("refresh",)]
        assert panel._cache_clear_pending is False

    def test_declining_the_confirmation_deletes_nothing(self, monkeypatch):
        calls: list = []
        panel, tk_loop, events = self._panel(calls.append)
        panel._selected_weight_name = lambda: "yolo"
        monkeypatch.setattr(
            "zebtrack.ui.components.global_model_configuration_panel.messagebox.askyesno",
            lambda *a, **k: False,
        )

        panel._on_clear_cache_selected()
        tk_loop.run_until_idle()

        assert calls == []
        assert events == []
