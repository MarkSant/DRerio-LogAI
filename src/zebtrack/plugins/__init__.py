"""Detector plugin implementations and registry.

This package contains plugin implementations for different detection backends
(YOLO, OpenVINO) with graceful dependency handling.

The registry is built on first access, not at import (#643). Importing a
submodule such as ``zebtrack.plugins.base`` runs this ``__init__`` first, and
building the registry eagerly made every such import pay for torch, ultralytics
and openvino. ``DETECTOR_PLUGINS``, the ``*_PLUGIN_AVAILABLE`` flags and the
plugin classes are still module attributes, resolved by ``__getattr__``.
"""

from __future__ import annotations

from typing import Any

from zebtrack.plugins.base import DetectorPlugin

# A simple plugin registry. The keys are the user-facing names.
# The main application can use this to discover and instantiate plugins.
DETECTOR_PLUGINS: dict[str, type[DetectorPlugin]]
UltralyticsDetectorPlugin: type[DetectorPlugin] | None
OpenVINOPlugin: type[DetectorPlugin] | None
ULTRALYTICS_PLUGIN_AVAILABLE: bool
OPENVINO_PLUGIN_AVAILABLE: bool

_REGISTRY_NAMES = frozenset(
    {
        "DETECTOR_PLUGINS",
        "UltralyticsDetectorPlugin",
        "OpenVINOPlugin",
        "ULTRALYTICS_PLUGIN_AVAILABLE",
        "OPENVINO_PLUGIN_AVAILABLE",
    }
)


def _load_registry() -> None:
    """Import the plugin modules and publish the registry as module attributes.

    Values already present (a test that patched one) are left untouched.
    """
    registry: dict[str, type[DetectorPlugin]] = {}
    namespace = globals()

    ultralytics_cls: type[DetectorPlugin] | None
    try:
        from zebtrack.plugins.ultralytics_detector import UltralyticsDetectorPlugin as _Ultra

        ultralytics_cls = _Ultra
        registry[_Ultra.get_name()] = _Ultra
    except ImportError:
        ultralytics_cls = None

    openvino_cls: type[DetectorPlugin] | None
    try:
        from zebtrack.plugins.openvino_detector import OpenVINOPlugin as _OpenVINO

        openvino_cls = _OpenVINO
        registry[_OpenVINO.get_name()] = _OpenVINO
    except ImportError:
        openvino_cls = None

    namespace.setdefault("DETECTOR_PLUGINS", registry)
    namespace.setdefault("UltralyticsDetectorPlugin", ultralytics_cls)
    namespace.setdefault("OpenVINOPlugin", openvino_cls)
    namespace.setdefault("ULTRALYTICS_PLUGIN_AVAILABLE", ultralytics_cls is not None)
    namespace.setdefault("OPENVINO_PLUGIN_AVAILABLE", openvino_cls is not None)


def __getattr__(name: str) -> Any:
    """Build the registry the first time one of its names is read."""
    if name in _REGISTRY_NAMES:
        _load_registry()
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
