"""
Extended unit tests for OpenVINOPlugin and helper functions in plugins/openvino_detector.py.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from zebtrack.plugins.openvino_detector import (
    OPENVINO_AVAILABLE,
    TORCH_AVAILABLE,
    OpenVINOPlugin,
    _resolve_openvino_cache_dir,
    _scale_image,
)
from zebtrack.utils import IntegrityError


class TestOpenVINOHelpersExtended:
    def test_resolve_openvino_cache_dir_none(self):
        assert _resolve_openvino_cache_dir(None) is None
        assert _resolve_openvino_cache_dir("") is None

    def test_resolve_openvino_cache_dir_valid(self, tmp_path):
        cache_dir = tmp_path / "ov_cache"
        resolved = _resolve_openvino_cache_dir(cache_dir)
        assert resolved == str(cache_dir)
        assert cache_dir.exists()

    def test_resolve_openvino_cache_dir_relative(self):
        resolved = _resolve_openvino_cache_dir("scratch_ov_cache_test")
        assert resolved is not None
        assert Path(resolved).is_absolute()

    def test_scale_image(self):
        mask = np.zeros((20, 20), dtype=np.float32)
        mask[5:15, 5:15] = 1.0
        resized = _scale_image(mask, target_hw=(40, 40))
        assert resized.shape == (40, 40)


class TestOpenVINOPluginExtended:
    def test_missing_xml_file_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Could not find a .xml model file"):
            OpenVINOPlugin(tmp_path)

    def test_hash_mismatch_raises_integrity_error(self, tmp_path):
        xml_file = tmp_path / "model.xml"
        xml_file.write_text("<net></net>")
        bin_file = tmp_path / "model.bin"
        bin_file.write_bytes(b"\x00" * 10)

        with pytest.raises(IntegrityError, match="integrity of model file"):
            OpenVINOPlugin(tmp_path, expected_hash="0000000000000000000000000000000000000000")

    def test_get_name_static_method(self):
        assert OpenVINOPlugin.get_name() == "OpenVINO"


class TestOpenvinoDetectorExtended2:
    def test_availability_flags_boolean(self):
        assert isinstance(OPENVINO_AVAILABLE, bool)
        assert isinstance(TORCH_AVAILABLE, bool)

    def test_resolve_openvino_cache_dir_none(self):
        assert _resolve_openvino_cache_dir(None) is None
        assert _resolve_openvino_cache_dir("") is None

    def test_resolve_openvino_cache_dir_relative(self):
        resolved = _resolve_openvino_cache_dir("openvino_model_cache")
        assert resolved is not None
        assert "openvino_model_cache" in resolved

    def test_scale_image_resizing(self):
        mask = np.zeros((64, 64), dtype=np.float32)
        scaled = _scale_image(mask, (128, 128))
        assert scaled.shape == (128, 128)
