"""Lazy loaders for the heavy optional deep-learning dependencies (#643).

Importing ``torch`` / ``ultralytics`` costs several seconds per process. Until
v8.0 several modules imported them at module level, so importing ANY module of
``zebtrack.core.services`` or ``zebtrack.core.detection`` paid that cost, even
pure-logic ones (``external_trigger_gate``), every worker, and every mutant of
``scripts/mutation_check.py``.

The rule: no zebtrack module imports torch, torchvision, ultralytics or
openvino at import time. Modules that used to expose the result as module
attributes (``YOLO``, ``ULTRALYTICS_AVAILABLE``, ``torch``, ``TORCH_AVAILABLE``,
``DETECTOR_PLUGINS``) still do, through a PEP 562 ``__getattr__`` that calls
these loaders on first access. Guarded by ``tests/test_lazy_heavy_imports.py``.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, MutableMapping
from functools import cache
from types import ModuleType
from typing import Any

import structlog

log = structlog.get_logger()


@cache
def load_torch() -> ModuleType | None:
    """Return the ``torch`` module, or ``None`` when it is not installed."""
    try:
        return importlib.import_module("torch")
    except ImportError:
        log.debug("optional_deps.torch.unavailable")
        return None


@cache
def load_yolo() -> Any | None:
    """Return the ``ultralytics.YOLO`` class, or ``None`` when unavailable."""
    try:
        module = importlib.import_module("ultralytics")
    except ImportError:
        log.debug("optional_deps.ultralytics.unavailable")
        return None
    return getattr(module, "YOLO", None)


def resolve_lazy_attribute(
    namespace: MutableMapping[str, Any],
    name: str,
    loaders: dict[str, Callable[[MutableMapping[str, Any]], None]],
) -> Any:
    """Return ``namespace[name]``, populating it with its loader first if needed.

    ``namespace`` is a module's ``globals()``. A value already present wins, so
    a test that patched or assigned the module attribute keeps control; the
    loader only runs for a name that was never set.
    """
    if name not in namespace:
        loader = loaders.get(name)
        if loader is None:
            raise AttributeError(name)
        loader(namespace)
    return namespace[name]


def install_yolo(namespace: MutableMapping[str, Any]) -> None:
    """Populate ``YOLO`` / ``ULTRALYTICS_AVAILABLE`` without overriding patches."""
    yolo = load_yolo()
    namespace.setdefault("YOLO", yolo)
    namespace.setdefault("ULTRALYTICS_AVAILABLE", yolo is not None)


def install_torch(namespace: MutableMapping[str, Any]) -> None:
    """Populate ``torch`` / ``TORCH_AVAILABLE`` without overriding patches."""
    torch = load_torch()
    namespace.setdefault("torch", torch)
    namespace.setdefault("TORCH_AVAILABLE", torch is not None)


YOLO_LOADERS: dict[str, Callable[[MutableMapping[str, Any]], None]] = {
    "YOLO": install_yolo,
    "ULTRALYTICS_AVAILABLE": install_yolo,
}
TORCH_LOADERS: dict[str, Callable[[MutableMapping[str, Any]], None]] = {
    "torch": install_torch,
    "TORCH_AVAILABLE": install_torch,
}
