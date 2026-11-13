"""Tests for ``zebtrack.utils.optional_deps`` (#643): lazy, cached, patch-friendly."""

from __future__ import annotations

from typing import Any

import pytest

from zebtrack.utils import optional_deps


@pytest.fixture(autouse=True)
def _fresh_loader_cache():
    optional_deps.load_torch.cache_clear()
    optional_deps.load_yolo.cache_clear()
    yield
    optional_deps.load_torch.cache_clear()
    optional_deps.load_yolo.cache_clear()


def _missing(name: str) -> Any:
    raise ImportError(f"No module named {name!r}")


def test_missing_torch_degrades_to_none(monkeypatch):
    monkeypatch.setattr(optional_deps.importlib, "import_module", _missing)

    assert optional_deps.load_torch() is None


def test_missing_ultralytics_degrades_to_none(monkeypatch):
    monkeypatch.setattr(optional_deps.importlib, "import_module", _missing)

    assert optional_deps.load_yolo() is None


def test_loaders_import_once(monkeypatch):
    calls: list[str] = []

    class _Ultralytics:
        YOLO = object()

    def _import(name: str) -> Any:
        calls.append(name)
        return _Ultralytics

    monkeypatch.setattr(optional_deps.importlib, "import_module", _import)

    first = optional_deps.load_yolo()
    second = optional_deps.load_yolo()

    assert first is second is _Ultralytics.YOLO
    assert calls == ["ultralytics"]


def test_unavailable_dependency_sets_the_flag_false(monkeypatch):
    monkeypatch.setattr(optional_deps.importlib, "import_module", _missing)
    namespace: dict[str, Any] = {}

    assert (
        optional_deps.resolve_lazy_attribute(
            namespace, "TORCH_AVAILABLE", optional_deps.TORCH_LOADERS
        )
        is False
    )
    assert namespace["torch"] is None
    assert (
        optional_deps.resolve_lazy_attribute(
            namespace, "ULTRALYTICS_AVAILABLE", optional_deps.YOLO_LOADERS
        )
        is False
    )
    assert namespace["YOLO"] is None


def test_a_value_already_set_wins_over_the_loader(monkeypatch):
    monkeypatch.setattr(optional_deps.importlib, "import_module", _missing)
    sentinel = object()
    namespace: dict[str, Any] = {"YOLO": sentinel}

    # Resolving the flag runs the loader, which must not clobber the patched class.
    assert (
        optional_deps.resolve_lazy_attribute(
            namespace, "ULTRALYTICS_AVAILABLE", optional_deps.YOLO_LOADERS
        )
        is False
    )
    assert (
        optional_deps.resolve_lazy_attribute(namespace, "YOLO", optional_deps.YOLO_LOADERS)
        is sentinel
    )


def test_unknown_name_raises_attribute_error():
    with pytest.raises(AttributeError):
        optional_deps.resolve_lazy_attribute({}, "nope", optional_deps.YOLO_LOADERS)
