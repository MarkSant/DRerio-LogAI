"""Tests for OpenVINO AsyncInferQueue batch inference (Phase 7).

Validates that ``OpenVINOPlugin.detect_batch()`` correctly:
- Delegates single frames to ``detect()``
- Pipelines multiple frames through ``AsyncInferQueue``
- Preserves frame ordering in results
- Falls back to sequential on error
- Respects ``batch_nireq`` from settings
- Handles edge cases (empty input, None frames)
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers — build a lightweight OpenVINOPlugin without __init__
# ---------------------------------------------------------------------------


def _make_plugin(
    *,
    nireq: int = 4,
    conf_threshold: float = 0.25,
    nms_threshold: float = 0.45,
    target_h: int = 640,
    target_w: int = 640,
    num_classes: int = 2,
    has_settings: bool = True,
) -> Any:
    """Construct a minimal ``OpenVINOPlugin`` via ``object.__new__``.

    Avoids calling ``__init__`` (which requires a real OpenVINO model) and
    manually sets the attributes that ``detect_batch`` / ``_run_async_batch``
    rely on.
    """
    # Ensure openvino module mock is available
    if "openvino" not in sys.modules:
        sys.modules["openvino"] = MagicMock()

    from zebtrack.plugins.openvino_detector import OpenVINOPlugin

    plugin: Any = object.__new__(OpenVINOPlugin)
    plugin.conf_threshold = conf_threshold
    plugin.nms_threshold = nms_threshold
    plugin._target_h = target_h
    plugin._target_w = target_w
    plugin.class_names = {i: f"class_{i}" for i in range(num_classes)}
    plugin._context = "tracking"
    plugin._aquarium_region_defined = False
    plugin._use_embedded_preprocessing = False

    # Mock model artifacts
    plugin.compiled_model = MagicMock()
    plugin.infer_request = MagicMock()
    plugin.input_layer = MagicMock()
    plugin.input_layer.any_name = "images"
    plugin.input_layer.shape = [1, 3, target_h, target_w]
    plugin.output_det = MagicMock(name="output_det")
    plugin.output_proto = None  # no segmentation masks

    # Settings with batch_nireq
    if has_settings:
        ov_settings = SimpleNamespace(batch_nireq=nireq)
        plugin._settings = SimpleNamespace(openvino=ov_settings)
    else:
        plugin._settings = None

    return plugin


def _make_fake_detection_tensor(
    num_detections: int = 1,
    num_classes: int = 2,
) -> np.ndarray:
    """Create a plausible detection output tensor ``[1, 4+nc, 8400]``.

    The tensor has ``num_detections`` confident detections embedded in the
    first ``num_detections`` anchors; everything else is near-zero.
    """
    channels = 4 + num_classes  # bbox (4) + class scores
    tensor = np.zeros((1, channels, 8400), dtype=np.float32)

    for i in range(min(num_detections, 8400)):
        # cx, cy, w, h (normalised-ish)
        tensor[0, 0, i] = 320.0  # cx
        tensor[0, 1, i] = 320.0  # cy
        tensor[0, 2, i] = 100.0  # w
        tensor[0, 3, i] = 100.0  # h
        # class scores — make class 0 confident
        tensor[0, 4, i] = 0.9

    return tensor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_frame() -> np.ndarray:
    """720p BGR frame filled with zeros."""
    return np.zeros((720, 1280, 3), dtype=np.uint8)


@pytest.fixture
def sample_frames(sample_frame: np.ndarray) -> list[np.ndarray]:
    """4 identical 720p frames."""
    return [sample_frame.copy() for _ in range(4)]


# ---------------------------------------------------------------------------
# Tests — detect_batch entry point
# ---------------------------------------------------------------------------


class TestDetectBatchEntryPoint:
    """Validate the public ``detect_batch`` contract."""

    def test_empty_frames_returns_empty(self) -> None:
        plugin = _make_plugin()
        result = plugin.detect_batch([])
        assert result == []

    def test_single_frame_delegates_to_detect(self, sample_frame: np.ndarray) -> None:
        """A single-frame batch should call ``detect()`` directly."""
        plugin = _make_plugin()
        expected = [(10, 20, 50, 60, 0.9, None, 0)]
        plugin.detect = MagicMock(return_value=expected)

        result = plugin.detect_batch([sample_frame])

        plugin.detect.assert_called_once_with(sample_frame, conf_threshold=None)
        assert result == [expected]

    def test_single_frame_with_conf_override(self, sample_frame: np.ndarray) -> None:
        plugin = _make_plugin()
        plugin.detect = MagicMock(return_value=[])

        plugin.detect_batch([sample_frame], conf_threshold=0.5)

        plugin.detect.assert_called_once_with(sample_frame, conf_threshold=0.5)

    def test_multiple_frames_calls_run_async_batch(self, sample_frames: list[np.ndarray]) -> None:
        """Multiple frames should route through ``_run_async_batch``."""
        plugin = _make_plugin(nireq=2)
        expected = [[] for _ in sample_frames]
        plugin._run_async_batch = MagicMock(return_value=expected)

        result = plugin.detect_batch(sample_frames)

        plugin._run_async_batch.assert_called_once_with(sample_frames, 2)
        assert result == expected

    def test_nireq_capped_at_frame_count(self) -> None:
        """nireq should not exceed the number of frames."""
        plugin = _make_plugin(nireq=8)
        frames = [np.zeros((100, 100, 3), dtype=np.uint8) for _ in range(3)]
        plugin._run_async_batch = MagicMock(return_value=[[], [], []])

        plugin.detect_batch(frames)

        # nireq should be min(8, 3) = 3
        plugin._run_async_batch.assert_called_once_with(frames, 3)

    def test_nireq_defaults_when_no_settings(self) -> None:
        """Without settings, nireq defaults to 4."""
        plugin = _make_plugin(has_settings=False)
        frames = [np.zeros((100, 100, 3), dtype=np.uint8) for _ in range(10)]
        plugin._run_async_batch = MagicMock(return_value=[[] for _ in range(10)])

        plugin.detect_batch(frames)

        plugin._run_async_batch.assert_called_once_with(frames, 4)

    def test_conf_threshold_override_applied_and_restored(
        self, sample_frames: list[np.ndarray]
    ) -> None:
        """Confidence threshold should be temporarily overridden and restored."""
        plugin = _make_plugin(conf_threshold=0.25)
        plugin._run_async_batch = MagicMock(return_value=[[] for _ in sample_frames])

        plugin.detect_batch(sample_frames, conf_threshold=0.7)

        # After the call, original threshold must be restored
        assert plugin.conf_threshold == 0.25

    def test_conf_threshold_restored_even_on_error(self, sample_frames: list[np.ndarray]) -> None:
        """Threshold must be restored even when _run_async_batch raises."""
        plugin = _make_plugin(conf_threshold=0.25)
        plugin._run_async_batch = MagicMock(side_effect=RuntimeError("boom"))
        # Fallback detect also mocked
        plugin.detect = MagicMock(return_value=[])

        plugin.detect_batch(sample_frames, conf_threshold=0.8)

        assert plugin.conf_threshold == 0.25

    def test_fallback_to_sequential_on_error(self, sample_frames: list[np.ndarray]) -> None:
        """If _run_async_batch fails, fall back to sequential detect()."""
        plugin = _make_plugin()
        plugin._run_async_batch = MagicMock(side_effect=RuntimeError("GPU error"))
        plugin.detect = MagicMock(return_value=[(1, 2, 3, 4, 0.5, None, 0)])

        result = plugin.detect_batch(sample_frames)

        assert len(result) == len(sample_frames)
        assert plugin.detect.call_count == len(sample_frames)


# ---------------------------------------------------------------------------
# Tests — _run_async_batch inner implementation
# ---------------------------------------------------------------------------


class TestRunAsyncBatch:
    """Test the internal ``_run_async_batch`` method with mocked AsyncInferQueue."""

    def _patch_async_queue(
        self,
        plugin: Any,
        num_frames: int,
        detections_per_frame: int = 1,
    ) -> MagicMock:
        """Set up mocks so _run_async_batch exercises the full code path.

        Returns the patched ``ov.AsyncInferQueue`` constructor mock.
        """
        import openvino as ov_mock

        # Create a fake detection tensor for each frame
        det_tensor = _make_fake_detection_tensor(detections_per_frame)

        # Track submitted requests and their callbacks
        submitted: list[tuple[dict, int]] = []
        callback_fn = None

        class FakeAsyncQueue:
            """Simulates ov.AsyncInferQueue behaviour."""

            def __init__(self, compiled_model: Any, nireq: int) -> None:
                self.nireq = nireq
                self._compiled_model = compiled_model

            def set_callback(self, fn: Any) -> None:
                nonlocal callback_fn
                callback_fn = fn

            def start_async(self, inputs: dict, userdata: int) -> None:
                submitted.append((inputs, userdata))

            def wait_all(self) -> None:
                """Simulate completion of all requests."""
                assert callback_fn is not None
                for _inputs, userdata in submitted:
                    request = MagicMock()
                    request.results = {plugin.output_det: det_tensor.copy()}
                    callback_fn(request, userdata)

        ov_mock.AsyncInferQueue = FakeAsyncQueue

        # Mock _preprocess to return a tensor with correct shape
        def fake_preprocess(frame: np.ndarray) -> np.ndarray:
            return np.zeros((1, 3, 640, 640), dtype=np.float32)

        plugin._preprocess = fake_preprocess

        # Mock _postprocess to return detections matching det count
        def fake_postprocess(
            results: Any,
            original_shape: tuple,
            input_shape: tuple,
            decode_masks: bool = True,
        ) -> tuple[np.ndarray, list | None]:
            dets = []
            for i in range(detections_per_frame):
                dets.append([100 + i, 100 + i, 200 + i, 200 + i, 0.9, 0])
            if not dets:
                return np.empty((0, 6)), None
            return np.array(dets), None

        plugin._postprocess = fake_postprocess

        return submitted

    def test_returns_correct_count(self, sample_frames: list[np.ndarray]) -> None:
        plugin = _make_plugin(nireq=2)
        self._patch_async_queue(plugin, len(sample_frames), detections_per_frame=1)

        result = plugin._run_async_batch(sample_frames, nireq=2)

        assert len(result) == len(sample_frames)

    def test_each_frame_has_detection_list(self, sample_frames: list[np.ndarray]) -> None:
        plugin = _make_plugin(nireq=2)
        self._patch_async_queue(plugin, len(sample_frames), detections_per_frame=2)

        result = plugin._run_async_batch(sample_frames, nireq=2)

        for frame_dets in result:
            assert isinstance(frame_dets, list)
            assert len(frame_dets) == 2
            for det in frame_dets:
                assert len(det) == 7  # (x1, y1, x2, y2, conf, track_id, class_id)
                assert det[5] is None  # track_id is always None from plugin

    def test_preserves_frame_order(self) -> None:
        """Results must correspond to their input frame index."""
        plugin = _make_plugin(nireq=2)

        # Create frames with distinct sizes so we can verify ordering
        frames = [
            np.zeros((100, 200, 3), dtype=np.uint8),
            np.zeros((200, 300, 3), dtype=np.uint8),
            np.zeros((300, 400, 3), dtype=np.uint8),
        ]

        # Custom _postprocess that encodes the original frame size into x1
        captured_shapes: list[tuple] = []

        def tracking_postprocess(
            results: Any, original_shape: tuple, input_shape: tuple, decode_masks: bool = True
        ) -> tuple[np.ndarray, list | None]:
            captured_shapes.append(original_shape)
            h = original_shape[0]
            return np.array([[h, 0, h + 50, 50, 0.9, 0]]), None

        import openvino as ov_mock

        submitted: list[tuple[dict, int]] = []
        callback_fn_holder: list = []

        class FakeQueue:
            def __init__(self, cm: Any, nireq: int) -> None:
                pass

            def set_callback(self, fn: Any) -> None:
                callback_fn_holder.append(fn)

            def start_async(self, inputs: dict, userdata: int) -> None:
                submitted.append((inputs, userdata))

            def wait_all(self) -> None:
                # Complete in REVERSE order to test ordering robustness
                for _inputs, userdata in reversed(submitted):
                    req = MagicMock()
                    req.results = {plugin.output_det: np.zeros((1, 6, 8400), dtype=np.float32)}
                    callback_fn_holder[0](req, userdata)

        ov_mock.AsyncInferQueue = FakeQueue
        plugin._preprocess = lambda f: np.zeros((1, 3, 640, 640), dtype=np.float32)
        plugin._postprocess = tracking_postprocess

        result = plugin._run_async_batch(frames, nireq=2)

        # Results should match frame indices
        assert len(result) == 3
        assert result[0][0][0] == 100  # first frame h=100, x1=100
        assert result[1][0][0] == 200  # second frame h=200, x1=200
        assert result[2][0][0] == 300  # third frame h=300, x1=300

    def test_none_frames_produce_empty_detections(self) -> None:
        """None or empty frames should yield empty detection lists."""
        plugin = _make_plugin(nireq=2)

        frames = [
            np.zeros((100, 200, 3), dtype=np.uint8),
            np.array([], dtype=np.uint8),  # empty frame
        ]

        import openvino as ov_mock

        submitted: list[tuple[dict, int]] = []
        callback_fn_holder: list = []

        class FakeQueue:
            def __init__(self, cm: Any, nireq: int) -> None:
                pass

            def set_callback(self, fn: Any) -> None:
                callback_fn_holder.append(fn)

            def start_async(self, inputs: dict, userdata: int) -> None:
                submitted.append((inputs, userdata))

            def wait_all(self) -> None:
                for _inputs, userdata in submitted:
                    req = MagicMock()
                    req.results = {plugin.output_det: np.zeros((1, 6, 8400), dtype=np.float32)}
                    callback_fn_holder[0](req, userdata)

        ov_mock.AsyncInferQueue = FakeQueue
        plugin._preprocess = lambda f: np.zeros((1, 3, 640, 640), dtype=np.float32)
        plugin._postprocess = lambda r, os, is_, decode_masks=True: (
            np.array([[10, 10, 50, 50, 0.9, 0]]),
            None,
        )

        result = plugin._run_async_batch(frames, nireq=2)

        assert len(result) == 2
        # The valid frame should have detections
        assert len(result[0]) >= 1
        # The empty frame should be empty
        assert result[1] == []

    def test_no_detections_frame(self) -> None:
        """Frames with no detections should return empty lists."""
        plugin = _make_plugin(nireq=2)
        self._patch_async_queue(plugin, 3, detections_per_frame=0)

        frames = [np.zeros((100, 200, 3), dtype=np.uint8) for _ in range(3)]
        result = plugin._run_async_batch(frames, nireq=2)

        assert len(result) == 3
        for frame_dets in result:
            assert frame_dets == []


# ---------------------------------------------------------------------------
# Tests — _OutputProxy
# ---------------------------------------------------------------------------


class TestOutputProxy:
    """Validate the lightweight results proxy used by batch post-processing."""

    def test_getitem_returns_det_tensor(self) -> None:
        from zebtrack.plugins.openvino_detector import _OutputProxy

        det_key = MagicMock(name="det_output")
        tensor = np.array([1, 2, 3])
        proxy = _OutputProxy(det_tensor=tensor, proto_tensor=None, det_key=det_key, proto_key=None)

        result = proxy[det_key]
        np.testing.assert_array_equal(result, tensor)

    def test_getitem_returns_proto_tensor(self) -> None:
        from zebtrack.plugins.openvino_detector import _OutputProxy

        det_key = MagicMock(name="det_output")
        proto_key = MagicMock(name="proto_output")
        det_t = np.array([1])
        proto_t = np.array([2])
        proxy = _OutputProxy(
            det_tensor=det_t, proto_tensor=proto_t, det_key=det_key, proto_key=proto_key
        )

        np.testing.assert_array_equal(proxy[det_key], det_t)
        np.testing.assert_array_equal(proxy[proto_key], proto_t)

    def test_contains_det_key(self) -> None:
        from zebtrack.plugins.openvino_detector import _OutputProxy

        det_key = MagicMock(name="det_output")
        proxy = _OutputProxy(
            det_tensor=np.array([1]),
            proto_tensor=None,
            det_key=det_key,
            proto_key=None,
        )

        assert det_key in proxy
        assert MagicMock(name="other") not in proxy

    def test_contains_proto_key(self) -> None:
        from zebtrack.plugins.openvino_detector import _OutputProxy

        det_key = MagicMock(name="det_output")
        proto_key = MagicMock(name="proto_output")
        proxy = _OutputProxy(
            det_tensor=np.array([1]),
            proto_tensor=np.array([2]),
            det_key=det_key,
            proto_key=proto_key,
        )

        assert proto_key in proxy

    def test_proto_key_none_not_in_store(self) -> None:
        from zebtrack.plugins.openvino_detector import _OutputProxy

        det_key = MagicMock(name="det_output")
        proxy = _OutputProxy(
            det_tensor=np.array([1]),
            proto_tensor=None,
            det_key=det_key,
            proto_key=None,
        )

        # proto_key is None so nothing extra is stored
        assert len(proxy._store) == 1


# ---------------------------------------------------------------------------
# Tests — settings integration
# ---------------------------------------------------------------------------


class TestBatchNireqSettings:
    """Validate that batch_nireq is respected from OpenVINOSettings."""

    def test_batch_nireq_read_from_settings(self) -> None:
        plugin = _make_plugin(nireq=6)
        frames = [np.zeros((100, 100, 3), dtype=np.uint8) for _ in range(10)]
        plugin._run_async_batch = MagicMock(return_value=[[] for _ in range(10)])

        plugin.detect_batch(frames)

        plugin._run_async_batch.assert_called_once_with(frames, 6)

    def test_batch_nireq_clamped_to_frame_count(self) -> None:
        plugin = _make_plugin(nireq=16)
        frames = [np.zeros((100, 100, 3), dtype=np.uint8) for _ in range(3)]
        plugin._run_async_batch = MagicMock(return_value=[[], [], []])

        plugin.detect_batch(frames)

        plugin._run_async_batch.assert_called_once_with(frames, 3)

    def test_batch_nireq_minimum_is_one(self) -> None:
        """Even if settings has nireq=0 somehow, clamp to 1."""
        plugin = _make_plugin(nireq=0)
        # Force nireq=0 to bypass Field validator (testing runtime clamp)
        plugin._settings.openvino.batch_nireq = 0
        frames = [np.zeros((100, 100, 3), dtype=np.uint8) for _ in range(5)]
        plugin._run_async_batch = MagicMock(return_value=[[] for _ in range(5)])

        plugin.detect_batch(frames)

        plugin._run_async_batch.assert_called_once_with(frames, 1)

    def test_settings_validation_rejects_out_of_range(self) -> None:
        """Pydantic should reject batch_nireq outside [1, 16]."""
        from pydantic import ValidationError

        from zebtrack.settings import OpenVINOSettings

        with pytest.raises(ValidationError):
            OpenVINOSettings(batch_nireq=0)

        with pytest.raises(ValidationError):
            OpenVINOSettings(batch_nireq=17)

    def test_settings_accepts_valid_range(self) -> None:
        from zebtrack.settings import OpenVINOSettings

        for n in (1, 4, 8, 16):
            s = OpenVINOSettings(batch_nireq=n)
            assert s.batch_nireq == n
