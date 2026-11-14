"""Tests for the lazy detector-plugin registry in ``zebtrack/plugins/__init__.py``.

The registry is built the first time one of its names is read, and a backend
whose import fails must simply be absent — never take the other one down with
it. That the import itself stays cheap is covered separately, in a fresh
interpreter, by ``tests/test_lazy_heavy_imports.py``.
"""

from __future__ import annotations

import sys

import pytest

import zebtrack.plugins as plugins_pkg
from zebtrack.plugins.base import DetectorPlugin

pytestmark = pytest.mark.unit

REGISTRY_NAMES = (
    "DETECTOR_PLUGINS",
    "UltralyticsDetectorPlugin",
    "OpenVINOPlugin",
    "ULTRALYTICS_PLUGIN_AVAILABLE",
    "OPENVINO_PLUGIN_AVAILABLE",
)


@pytest.fixture
def unbuilt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Forget the registry so the next attribute read builds it again."""
    for name in REGISTRY_NAMES:
        monkeypatch.delitem(vars(plugins_pkg), name, raising=False)


def _hide(monkeypatch: pytest.MonkeyPatch, module: str) -> None:
    """Make ``import zebtrack.plugins.<module>`` raise ImportError."""
    monkeypatch.setitem(sys.modules, f"zebtrack.plugins.{module}", None)


@pytest.mark.usefixtures("unbuilt")
class TestRegistry:
    def test_the_declared_names_are_exactly_the_lazy_ones(self) -> None:
        assert set(REGISTRY_NAMES) == plugins_pkg._REGISTRY_NAMES

    def test_reading_one_name_publishes_all_of_them(self) -> None:
        assert not set(REGISTRY_NAMES) & set(vars(plugins_pkg))

        registry = plugins_pkg.DETECTOR_PLUGINS

        assert set(REGISTRY_NAMES) <= set(vars(plugins_pkg))
        assert registry is plugins_pkg.DETECTOR_PLUGINS  # built once, then a plain attribute

    def test_plugins_are_registered_under_the_name_they_report(self) -> None:
        registry = plugins_pkg.DETECTOR_PLUGINS

        assert set(registry) == {"YOLO (Ultralytics)", "OpenVINO"}
        for name, plugin_cls in registry.items():
            assert issubclass(plugin_cls, DetectorPlugin)
            assert plugin_cls.get_name() == name
        assert registry["YOLO (Ultralytics)"] is plugins_pkg.UltralyticsDetectorPlugin
        assert registry["OpenVINO"] is plugins_pkg.OpenVINOPlugin
        assert plugins_pkg.ULTRALYTICS_PLUGIN_AVAILABLE is True
        assert plugins_pkg.OPENVINO_PLUGIN_AVAILABLE is True

    def test_a_missing_openvino_backend_leaves_ultralytics_registered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hide(monkeypatch, "openvino_detector")

        assert set(plugins_pkg.DETECTOR_PLUGINS) == {"YOLO (Ultralytics)"}
        assert plugins_pkg.OPENVINO_PLUGIN_AVAILABLE is False
        assert plugins_pkg.OpenVINOPlugin is None
        assert plugins_pkg.ULTRALYTICS_PLUGIN_AVAILABLE is True

    def test_a_missing_ultralytics_backend_leaves_openvino_registered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hide(monkeypatch, "ultralytics_detector")

        assert set(plugins_pkg.DETECTOR_PLUGINS) == {"OpenVINO"}
        assert plugins_pkg.ULTRALYTICS_PLUGIN_AVAILABLE is False
        assert plugins_pkg.UltralyticsDetectorPlugin is None
        assert plugins_pkg.OPENVINO_PLUGIN_AVAILABLE is True

    def test_with_no_backend_the_registry_is_empty_not_an_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hide(monkeypatch, "openvino_detector")
        _hide(monkeypatch, "ultralytics_detector")

        assert plugins_pkg.DETECTOR_PLUGINS == {}
        assert plugins_pkg.ULTRALYTICS_PLUGIN_AVAILABLE is False
        assert plugins_pkg.OPENVINO_PLUGIN_AVAILABLE is False

    def test_a_value_already_set_is_not_overwritten_by_the_build(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A test (or a caller) that pinned one name before the first read keeps it.
        monkeypatch.setitem(vars(plugins_pkg), "OPENVINO_PLUGIN_AVAILABLE", False)

        assert "OpenVINO" in plugins_pkg.DETECTOR_PLUGINS
        assert plugins_pkg.OPENVINO_PLUGIN_AVAILABLE is False


def test_an_unknown_attribute_is_an_attribute_error() -> None:
    with pytest.raises(AttributeError, match="has no attribute 'NoSuchPlugin'"):
        _ = plugins_pkg.NoSuchPlugin
