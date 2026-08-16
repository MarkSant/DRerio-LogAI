"""Extended unit tests for OpenVINOPlugin, _letterbox, _scale_image, and _OutputProxy."""

from __future__ import annotations

import numpy as np
import pytest

from zebtrack.plugins.openvino_detector import (
    _letterbox,
    _OutputProxy,
    _scale_image,
)


class TestLetterboxAndScaleImage:
    """Test letterbox resizing, padding, and mask scaling functions."""

    def test_scale_image_2d(self):
        mask_2d = np.ones((50, 50), dtype=np.float32)
        scaled = _scale_image(mask_2d, (100, 120))
        assert scaled.shape == (100, 120)

    def test_scale_image_3d(self):
        mask_3d = np.ones((50, 50, 2), dtype=np.float32)
        scaled = _scale_image(mask_3d, (100, 120))
        assert scaled.shape == (100, 120, 2)

    def test_letterbox_valid_image(self):
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        boxed, ratio, (dw, dh) = _letterbox(img, new_shape=(640, 640), auto=False)
        assert boxed.shape == (640, 640, 3)
        assert ratio[0] == pytest.approx(640 / 200)

    def test_letterbox_with_int_shape(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        # _letterbox supports int or tuple
        boxed, ratio, (dw, dh) = _letterbox(img, new_shape=(320, 320), auto=False)
        assert boxed.shape == (320, 320, 3)

    def test_letterbox_scale_fill(self):
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        boxed, ratio, (dw, dh) = _letterbox(img, new_shape=(300, 300), auto=False, scaleFill=True)
        assert boxed.shape == (300, 300, 3)
        assert dw == 0.0
        assert dh == 0.0

    def test_letterbox_no_scaleup(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        boxed, ratio, (dw, dh) = _letterbox(img, new_shape=(640, 640), scaleup=False, auto=False)
        assert boxed.shape == (640, 640, 3)
        assert ratio[0] == 1.0

    def test_letterbox_custom_color_and_stride(self):
        img = np.zeros((100, 150, 3), dtype=np.uint8)
        boxed, ratio, (dw, dh) = _letterbox(
            img, new_shape=(320, 320), color=(50, 50, 50), auto=True, stride=64
        )
        assert boxed.shape[0] % 64 == 0
        assert boxed.shape[1] % 64 == 0

    def test_letterbox_invalid_inputs_raise(self):
        with pytest.raises(ValueError, match="cannot be None or empty"):
            _letterbox(None)  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="cannot be None or empty"):
            _letterbox(np.array([]))

        with pytest.raises(ValueError, match="at least 2 dimensions"):
            _letterbox(np.zeros((10,)))


class TestOutputProxy:
    """Test _OutputProxy dictionary emulation."""

    def test_output_proxy_with_proto(self):
        det = np.zeros((1, 6, 100))
        proto = np.zeros((1, 32, 160, 160))
        proxy = _OutputProxy(
            det_tensor=det,
            proto_tensor=proto,
            det_key="det_out",
            proto_key="proto_out",
        )

        assert "det_out" in proxy
        assert "proto_out" in proxy
        assert "unknown" not in proxy
        assert proxy["det_out"] is det
        assert proxy["proto_out"] is proto

    def test_output_proxy_without_proto(self):
        det = np.zeros((1, 6, 100))
        proxy = _OutputProxy(
            det_tensor=det,
            proto_tensor=None,
            det_key="det_out",
            proto_key=None,
        )

        assert "det_out" in proxy
        assert None not in proxy
        assert proxy["det_out"] is det
