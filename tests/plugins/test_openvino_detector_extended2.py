"""Extended unit tests for plugins/openvino_detector.py."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from zebtrack.plugins.openvino_detector import (
    OPENVINO_AVAILABLE,
    TORCH_AVAILABLE,
    _resolve_openvino_cache_dir,
    _scale_image,
)


class TestOpenvinoDetectorExtended2:
    """Test OpenVINO cache resolution and image scaling helpers."""

    def test_availability_flags_boolean(self):
        assert isinstance(OPENVINO_AVAILABLE, bool)
        assert isinstance(TORCH_AVAILABLE, bool)

    def test_resolve_openvino_cache_dir_none(self):
        assert _resolve_openvino_cache_dir(None) is None
        assert _resolve_openvino_cache_dir("") is None

    def test_resolve_openvino_cache_dir_absolute(self, tmp_path: Path):
        cache_dir = tmp_path / "ov_cache"
        resolved = _resolve_openvino_cache_dir(cache_dir)
        assert resolved == str(cache_dir)
        assert cache_dir.exists()

    def test_resolve_openvino_cache_dir_relative(self):
        resolved = _resolve_openvino_cache_dir("openvino_model_cache")
        assert resolved is not None
        assert "openvino_model_cache" in resolved

    def test_scale_image_resizing(self):
        mask = np.zeros((64, 64), dtype=np.float32)
        scaled = _scale_image(mask, (128, 128))
        assert scaled.shape == (128, 128)
