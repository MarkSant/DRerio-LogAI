"""Tests for src/zebtrack/utils.py module loaded directly.

This module is shadowed by the zebtrack.utils package, so we load it by path
to ensure the file is executed and covered.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest


def _load_utils_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "src" / "zebtrack" / "utils.py"
    spec = importlib.util.spec_from_file_location("zebtrack._utils_module", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def utils_module():
    return _load_utils_module()


def test_calculate_sha256_module(utils_module, tmp_path):
    test_file = tmp_path / "hash.txt"
    test_file.write_bytes(b"hello")

    result = utils_module.calculate_sha256(test_file)
    assert isinstance(result, str)
    assert len(result) == 64


def test_calculate_sha256_module_missing_file(utils_module, tmp_path):
    missing = tmp_path / "missing.txt"
    assert utils_module.calculate_sha256(missing) == ""


def test_set_seed_module(utils_module):
    utils_module.TORCH_AVAILABLE = False
    utils_module.torch = None

    utils_module.set_seed(123)
    first = np.random.rand(5)

    utils_module.set_seed(123)
    second = np.random.rand(5)

    np.testing.assert_array_equal(first, second)


def test_polygon_centroid_module(utils_module):
    triangle = [(0.0, 0.0), (10.0, 0.0), (5.0, 10.0)]
    centroid = utils_module.polygon_centroid(triangle)
    assert centroid is not None
    cx, cy = centroid
    assert abs(cx - 5.0) < 0.001
    assert abs(cy - (10.0 / 3.0)) < 0.001


def test_snap_point_to_axes_module(utils_module):
    point = (50.0, 103.0)
    anchors = [(10.0, 100.0)]
    snapped = utils_module.snap_point_to_axes(point, anchors=anchors, threshold=5.0)
    assert snapped == (50.0, 100.0)
