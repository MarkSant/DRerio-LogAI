"""Tests for the granular CLI reset flags in :mod:`zebtrack.core.app_runner`."""

from __future__ import annotations

import pytest

import zebtrack.paths
from zebtrack.core.app_runner import _perform_reset


@pytest.fixture
def reset_workspace(tmp_path, monkeypatch):
    """Create a fake project layout: benchmark + config + weights + cache.

    The layout is anchored by patching :func:`zebtrack.paths.repo_root`, not by
    ``chdir``: ``_perform_reset`` resolves its targets against the repository
    root precisely so the launch directory stops mattering. Deliberately leaves
    the working directory alone, so every test here also proves the reset does
    not depend on it.
    """
    (tmp_path / "config.local.yaml").write_text("camera: {index: 0}\n")
    (tmp_path / "weights_config.json").write_text("{}")
    cache = tmp_path / "openvino_model_cache"
    cache.mkdir()
    (cache / "system_benchmark.json").write_text("{}")
    sample_model = cache / "sample_openvino_model"
    sample_model.mkdir()
    (sample_model / "model.xml").write_text("<x/>")

    monkeypatch.setattr(zebtrack.paths, "repo_root", lambda: tmp_path)
    return tmp_path


def test_default_reset_only_touches_benchmark_and_config(reset_workspace):
    """``--reset`` (legacy) wipes benchmark + config.local but leaves the rest."""
    _perform_reset(benchmark_and_config=True)

    root = reset_workspace
    assert not (root / "config.local.yaml").exists()
    assert not (root / "openvino_model_cache" / "system_benchmark.json").exists()
    # Untouched
    assert (root / "weights_config.json").exists()
    assert (root / "openvino_model_cache" / "sample_openvino_model").exists()


def test_reset_weights_only_removes_registry(reset_workspace):
    """``--reset-weights`` deletes only weights_config.json."""
    _perform_reset(benchmark_and_config=False, weights_registry=True, openvino_cache=False)

    root = reset_workspace
    assert not (root / "weights_config.json").exists()
    assert (root / "config.local.yaml").exists()
    assert (root / "openvino_model_cache" / "system_benchmark.json").exists()
    assert (root / "openvino_model_cache" / "sample_openvino_model").exists()


def test_reset_openvino_cache_only_removes_cache_dir(reset_workspace):
    """``--reset-openvino-cache`` removes the entire openvino_model_cache/ folder."""
    _perform_reset(benchmark_and_config=False, weights_registry=False, openvino_cache=True)

    root = reset_workspace
    assert not (root / "openvino_model_cache").exists()
    assert (root / "config.local.yaml").exists()
    assert (root / "weights_config.json").exists()


def test_reset_all_wipes_everything(reset_workspace):
    """``--reset-all`` is a true factory reset (all flags ON)."""
    _perform_reset(benchmark_and_config=True, weights_registry=True, openvino_cache=True)

    root = reset_workspace
    assert not (root / "config.local.yaml").exists()
    assert not (root / "weights_config.json").exists()
    assert not (root / "openvino_model_cache").exists()


def test_reset_ignores_the_working_directory(reset_workspace, tmp_path_factory, monkeypatch):
    """Running from an unrelated folder still resets the project root.

    The regression this guards: while the targets were bare relative paths, a
    reset launched from anywhere but the repository root matched nothing,
    deleted nothing, and still reported "Reset complete".
    """
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    (elsewhere / "config.local.yaml").write_text("decoy\n")
    monkeypatch.chdir(elsewhere)

    _perform_reset(benchmark_and_config=True, weights_registry=True, openvino_cache=True)

    root = reset_workspace
    assert not (root / "config.local.yaml").exists()
    assert not (root / "weights_config.json").exists()
    assert not (root / "openvino_model_cache").exists()
    # The look-alike next to the working directory is not what gets deleted.
    assert (elsewhere / "config.local.yaml").exists()


def test_perform_reset_handles_missing_files(tmp_path, monkeypatch):
    """Reset is idempotent: missing targets just print 'skip', no exception."""
    monkeypatch.setattr(zebtrack.paths, "repo_root", lambda: tmp_path)
    # Should not raise even though no files exist.
    _perform_reset(benchmark_and_config=True, weights_registry=True, openvino_cache=True)
